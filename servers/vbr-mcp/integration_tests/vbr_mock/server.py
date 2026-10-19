# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

import asyncio
import contextlib
import functools
from collections.abc import Callable, Generator, Sequence
from itertools import pairwise
from pathlib import Path
from types import TracebackType
from typing import Any, Self, cast, get_args

import uvicorn
from pydantic import BaseModel

from vbr_mock import app
from vbr_mock.markers import MockOnly, VbrAction, VbrError, VbrSequence, VbrUpdate
from vbr_mock.models import Method, MockEndpoint, RecordedRequest
from vbr_mock.presenters import PRESENTERS
from vbr_mock.store import EnvironmentStore

Mockable = BaseModel | Sequence[BaseModel] | str | VbrError | VbrSequence | VbrAction | VbrUpdate
"""What a route can be mocked with (see ``VbrMock.mock``); a ``VbrUpdate`` only as an action's effect."""


@functools.cache
def _mock_only(model: type[BaseModel]) -> frozenset[str]:
    """The serialized names of the fields of ``model`` marked ``MOCK_ONLY``."""
    return frozenset(
        info.serialization_alias or info.alias or name
        for name, info in model.model_fields.items()
        if any(isinstance(meta, MockOnly) for meta in info.metadata)
    )


def split_route(route: str) -> tuple[Method | None, str]:
    """A route's verb and path: ``"POST /api/v1/jobs/{id}/start"`` names its verb, a plain path has none."""
    verb, _, path = route.partition(" ")
    if path and verb in get_args(Method):
        return cast("Method", verb), path
    return None, route


class _Server(uvicorn.Server):
    @contextlib.contextmanager
    def capture_signals(self) -> Generator[None]:
        # Ctrl-C belongs to the test run, not to the mock serving it.
        yield


class VbrMock:
    """The VBR mock, served on a free local port for as long as the ``async with`` block runs.

    Routes are mocked straight into its store, under an environment id; a client reads that environment
    when it logs in with the id as its VBR username. A model is served as is, a list of models in VBR's
    paged list envelope. Both are dumped to VBR's JSON here, so the mock itself holds plain JSON. A string is
    served as a plain-text body, for the reads VBR answers with a document rather than JSON (a report).
    """

    PASSWORD = app.PASSWORD
    """The VBR password to log in with; the username is the environment id."""

    def __init__(self, *, tls: tuple[Path, Path] | None = None) -> None:
        """``tls`` is a certificate file and its key: the same mock is then also served over HTTPS (``tls_url``)."""
        self._store = EnvironmentStore()
        vbr = app.create_app(self._store)
        # At "warning", an exception the mock raises (a case's reject or effects_of, a presenter) is logged with its
        # traceback: uvicorn logs it as "Exception in ASGI application" and answers 500.
        self._servers = [_Server(uvicorn.Config(vbr, host="127.0.0.1", port=0, log_level="warning"))]
        if tls is not None:
            cert_file, key_file = tls
            self._servers.append(
                _Server(
                    uvicorn.Config(
                        vbr,
                        host="127.0.0.1",
                        port=0,
                        # uvicorn's loggers are process-wide, so a level set here would apply to both servers (a
                        # "critical" one used to hide every exception of the mock). The HTTPS server leaves them as
                        # the HTTP one set them: a client refusing the certificate logs nothing at "warning" anyway
                        # (asyncio reports a failed handshake only in debug mode).
                        log_config=None,
                        log_level=None,
                        ssl_certfile=str(cert_file),
                        ssl_keyfile=str(key_file),
                    )
                )
            )
        self._tasks: list[asyncio.Task[None]] = []
        self.url = ""
        self.tls_url = ""
        """The mock over HTTPS with the ``tls`` certificate; empty without one."""

    async def __aenter__(self) -> Self:
        for server in self._servers:
            task = asyncio.create_task(server.serve())
            self._tasks.append(task)
            while not server.started:
                if task.done():
                    task.result()  # surfaces why the server could not start
                await asyncio.sleep(0.01)
        ports = [server.servers[0].sockets[0].getsockname()[1] for server in self._servers]
        self.url = f"http://127.0.0.1:{ports[0]}"
        if len(ports) > 1:
            self.tls_url = f"https://127.0.0.1:{ports[1]}"
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        for server in self._servers:
            server.should_exit = True
        for task in self._tasks:
            await task

    def mock(self, environment_id: str, route: str, data: Mockable) -> None:
        """Answer ``route`` in ``environment_id`` with ``data``.

        A model is served as is, a list of models paged like VBR, a string as a plain-text body, a ``VbrError`` as
        that error, a ``VbrSequence`` step by step, and a ``VbrAction`` as the action VBR performs. Fields marked
        ``MOCK_ONLY`` are filtered by but never served.

        ``route`` may name its verb, ``"POST /api/v1/jobs/{id}/start"``; an action is a POST unless it says
        otherwise. Without one the route answers either verb, in place of whatever it answered over any verb before.
        """
        self._store.put(environment_id, endpoint(route, data))

    def requests(self, environment_id: str) -> list[RecordedRequest]:
        """Every request ``environment_id`` received so far, oldest first: what VBR was asked to read and to do."""
        return self._store.requests(environment_id)

    def delete(self, environment_id: str) -> None:
        """Drop everything mocked in ``environment_id``."""
        self._store.delete(environment_id)


def _respond(route: str, compute: Callable[[Any], Mockable]) -> Callable[[Any, dict], Any]:
    """``VbrAction.response_of`` as the store serves it: the answer for a request's body and query.

    The answer is presented as the same data mocked on a route would be: a model without its ``MOCK_ONLY`` fields, a
    list paged like VBR, a string as plain text, a ``VbrError`` as that error.
    """

    def respond(body: Any, query_params: dict) -> Any:
        answer = endpoint(route, compute(body))
        return PRESENTERS[answer.presenter](answer.data, query_params, answer.hidden)

    return respond


def _effects_of(compute: Callable[[Any], dict[str, Any]]) -> Callable[[Any], list[MockEndpoint]]:
    """``VbrAction.effects_of`` as the store applies it: the routes it returns for a body, as endpoints."""
    return lambda body: [endpoint(route, data) for route, data in compute(body).items()]


def endpoint(route: str, data: Mockable, *, method: Method | None = None) -> MockEndpoint:
    """The endpoint that answers ``route`` with ``data`` (see ``VbrMock.mock``)."""
    verb, route = split_route(route)
    method = method or verb
    if isinstance(data, VbrSequence):
        if not data.steps:
            raise ValueError(f"{route}: a VbrSequence needs at least one step")
        steps = [endpoint(route, step, method=method) for step in data.steps]
        for step, following in pairwise(steps):
            step.then = following
        return steps[0]
    if isinstance(data, VbrAction):
        response = data.response.model_dump(mode="json") if data.response is not None else None
        default_status = 200 if data.response_of is not None else 201 if response is not None else 204
        return MockEndpoint(
            route=route,
            presenter="as-is",
            data=response,
            hidden=_mock_only(type(data.response)) if data.response is not None else frozenset(),
            method=method or "POST",
            status_code=data.status_code or default_status,
            respond=_respond(route, data.response_of) if data.response_of is not None else None,
            reject=data.reject,
            effects=[endpoint(effect_route, effect) for effect_route, effect in data.effects.items()],
            effects_of=_effects_of(data.effects_of) if data.effects_of is not None else None,
        )
    if isinstance(data, VbrUpdate):
        return MockEndpoint(route=route, presenter="as-is", data=None, method=method, change=data.change)
    if isinstance(data, VbrError):
        return MockEndpoint(route=route, presenter="error", data=data.model_dump(), method=method)
    if isinstance(data, str):
        return MockEndpoint(route=route, presenter="as-is", data=data, method=method)
    if isinstance(data, BaseModel):
        payload: Any = data.model_dump(mode="json")
        return MockEndpoint(route=route, presenter="as-is", data=payload, hidden=_mock_only(type(data)), method=method)
    payload = [item.model_dump(mode="json") for item in data]
    hidden = frozenset().union(*map(_mock_only, {type(item) for item in data}))
    return MockEndpoint(route=route, presenter="vbr-page", data=payload, hidden=hidden, method=method)
