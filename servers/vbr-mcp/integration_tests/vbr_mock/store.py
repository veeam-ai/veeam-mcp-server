# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

from typing import Any, NamedTuple

from vbr_mock.models import MockEndpoint, RecordedRequest
from vbr_mock.presenters import PRESENTERS, MockedError


class RouteNotFoundError(Exception):
    """Raised when the requested route is not mocked in the environment, or nothing is mocked in it at all."""


class MethodNotAllowedError(Exception):
    """Raised when a mocked route is asked for over a verb it does not answer."""


class Served(NamedTuple):
    """What the mock answers a request with: the status and the body (``None`` for no content)."""

    status_code: int
    body: Any


class EnvironmentStore:
    """Holds any number of environments in memory, each a set of mocked routes and the requests it received.

    Environments are independent: the same route can be mocked differently in each, and mocking a
    route only adds it to its own environment or replaces it there.
    """

    def __init__(self) -> None:
        # environment -> route -> verb (None: either) -> endpoint
        self._environments: dict[str, dict[str, dict[str | None, MockEndpoint]]] = {}
        self._requests: dict[str, list[RecordedRequest]] = {}

    def put(self, environment_id: str, endpoint: MockEndpoint) -> None:
        """Mock ``endpoint`` in the environment, over its verb, or - without one - over every verb (see ``_put``)."""
        _put(self._environments.setdefault(environment_id, {}), endpoint)

    def delete(self, environment_id: str) -> None:
        self._environments.pop(environment_id, None)
        self._requests.pop(environment_id, None)

    def record(self, environment_id: str, request: RecordedRequest) -> None:
        self._requests.setdefault(environment_id, []).append(request)

    def requests(self, environment_id: str) -> list[RecordedRequest]:
        """Every request the environment received so far, oldest first."""
        return list(self._requests.get(environment_id, []))

    def serve(self, environment_id: str, route: str, query_params: dict, method: str, body: Any = None) -> Served:
        by_method = self._environments.get(environment_id, {}).get(_key(route))
        if by_method is None:
            raise RouteNotFoundError(route)
        # "No such route" outranks "wrong verb", so this is checked after the lookup: answering 405
        # for a route the double does not have would imply it exists.
        verb = method.upper()
        slot = verb if verb in by_method else None
        endpoint = by_method.get(slot)
        if endpoint is None:
            served_over = " and ".join(sorted(m for m in by_method if m is not None))
            raise MethodNotAllowedError(f"/{_key(route)} is served over {served_over}")
        if endpoint.then is not None:  # a sequence moves on whether this answer succeeds or not
            by_method[slot] = endpoint.then  # in the slot it was served from, whatever verb its next step names
        if endpoint.reject is not None and (error := endpoint.reject(body)) is not None:
            raise MockedError(error.status_code, error.message)
        if endpoint.respond is not None:
            payload = endpoint.respond(body, query_params)
        else:
            payload = PRESENTERS[endpoint.presenter](endpoint.data, query_params, endpoint.hidden)
        # The state VBR is in once the action is accepted. The effects are applied to a copy of the environment's
        # routes, in order (an update sees the effects before it), and the copy replaces the routes only once all of
        # them applied: an effects_of or a change that raises leaves the environment as it was, not half changed.
        effects = [*endpoint.effects, *(endpoint.effects_of(body) if endpoint.effects_of is not None else [])]
        routes = self._environments[environment_id]
        staged = {key: dict(slots) for key, slots in routes.items()}
        for effect in effects:
            _put(staged, effect)
        self._environments[environment_id] = staged
        return Served(endpoint.status_code, payload)


def _put(routes: dict[str, dict[str | None, MockEndpoint]], endpoint: MockEndpoint) -> None:
    """Mock ``endpoint`` in ``routes``, over its verb, or - without one - over every verb.

    An endpoint without a verb answers either verb, so it replaces what the route answered over any verb: kept
    beside it, an endpoint that names its verb would go on answering that verb, the newer one unseen. An endpoint
    that changes the route's data (``VbrUpdate``) changes what the route serves over its verb (or the verb-less
    slot) and keeps how it is served.
    """
    key = _key(endpoint.route)
    if endpoint.change is not None:
        current = routes.get(key, {}).get(endpoint.method)
        if current is None:
            raise LookupError(f"/{key}: an update of a route the environment does not serve over {endpoint.method}")
        endpoint = current.model_copy(update={"data": endpoint.change(current.data)})
    if endpoint.method is None:
        routes[key] = {None: endpoint}
    else:
        routes.setdefault(key, {})[endpoint.method] = endpoint


def _key(route: str) -> str:
    return route.strip("/")
