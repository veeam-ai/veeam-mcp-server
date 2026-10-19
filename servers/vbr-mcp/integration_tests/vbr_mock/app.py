# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""The VBR REST API as the mock serves it.

A client logs in the way it would with VBR, and the username is the environment id: the token it gets back
routes each of its requests to that environment, so environments with the same routes never see each other's
data. The app knows VBR's login, error shape and paging; what the routes hold is the test's business. Every
request it routes is recorded in its environment, with the status it was answered with and, when the mock itself
raised serving it, the exception.
"""

from typing import Any
from urllib.parse import parse_qs

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from vbr_mock.models import RecordedRequest
from vbr_mock.presenters import MockedError
from vbr_mock.store import EnvironmentStore, MethodNotAllowedError, RouteNotFoundError, Served

_TOKEN_PREFIX = "mock-environment:"

PASSWORD = "mock"
"""The one password the mock accepts; any other fails the login the way bad credentials fail it on VBR."""

_ERROR_CODES = {
    400: "UnexpectedContent",
    401: "InvalidToken",
    403: "AccessDenied",
    404: "NotFound",
    405: "MethodNotAllowed",
    500: "UnknownError",
    501: "NotImplemented",
    503: "ServiceUnavailable",
}
"""The ``errorCode`` VBR answers a status with, from the ``Error`` enum of its REST API."""


def create_app(store: EnvironmentStore) -> FastAPI:
    app = FastAPI()

    @app.exception_handler(StarletteHTTPException)
    async def vbr_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # VBR's error body, which vbr-mcp passes on to the model: it must read like VBR's, never like the mock's.
        error_code = _ERROR_CODES.get(exc.status_code, "UnknownError")
        return JSONResponse({"errorCode": error_code, "message": str(exc.detail)}, status_code=exc.status_code)

    @app.post("/api/oauth2/token")
    async def vbr_oauth_token(request: Request):
        # VBR REST OAuth2, as issued by vbr-mcp's VbrClient (a form body). The password grant names the
        # environment through its username; the refresh_token grant carries a token issued here, so it keeps
        # the environment it was issued for. The token is the environment id with a prefix: a test double
        # needs no secret, only something to route by.
        form = {key: values[0] for key, values in parse_qs((await request.body()).decode()).items()}
        environment_id = _login(form)
        if environment_id is None:
            return JSONResponse({"error": "invalid_grant", "error_description": "Invalid credentials"}, 400)
        if not environment_id:
            raise HTTPException(status_code=401, detail="The user name or password is incorrect.")
        token = _TOKEN_PREFIX + environment_id
        return {"access_token": token, "refresh_token": token, "expires_in": 3600, "token_type": "bearer"}

    @app.api_route("/{full_path:path}", methods=["GET", "POST"])
    async def catch(full_path: str, request: Request, authorization: str = Header("")):
        # POST is served for VBR's actions (a job start, a restore) and because some VBR reads are POSTs
        # too: the inventory browser (GetAllInventoryHosts) is POST /api/v1/inventory and pages through the
        # request body. A route that declares which verb VBR serves it over is held to it, so asking with
        # the wrong one gets the 405 a real server gives instead of a 200 that hides the mistake. An action
        # the case does not mock reads as 404.
        scheme, _, token = authorization.partition(" ")
        environment_id = _environment_id(token) if scheme.lower() == "bearer" else ""
        if not environment_id:
            raise HTTPException(status_code=401, detail="The access token is missing or invalid.")
        served = _serve_recorded(store, environment_id, full_path, request, await _json_body(request))
        if served.body is None:
            return Response(status_code=served.status_code)
        if isinstance(served.body, str):
            return PlainTextResponse(served.body, status_code=served.status_code)
        return JSONResponse(served.body, status_code=served.status_code)

    return app


class _UnmockedError(HTTPException):
    """A request for a route the environment does not mock, answered the way VBR answers an unknown object.

    The agent reads the message, so it says what VBR would say and nothing about the mock; the request is recorded
    as ``unmocked`` so the run can report the gap in the environment.
    """


def _serve_recorded(store: EnvironmentStore, environment_id: str, path: str, request: Request, body: Any) -> Served:
    """What the store answers the request with, recorded with its status - and the exception, if the mock raised one."""
    status_code, unmocked, error, method = 500, False, None, request.method
    try:
        served = _serve(store, environment_id, path, effective_query_params(_query_params(request), body), method, body)
        status_code = served.status_code
        return served
    except HTTPException as exc:
        status_code, unmocked = exc.status_code, isinstance(exc, _UnmockedError)
        raise
    except Exception as exc:  # the mock's own bug: uvicorn logs the traceback and answers 500
        error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        store.record(
            environment_id,
            RecordedRequest(
                method=method, path=f"/{path}", body=body, status_code=status_code, unmocked=unmocked, error=error
            ),
        )


def _serve(
    store: EnvironmentStore, environment_id: str, path: str, query_params: dict, method: str, body: Any
) -> Served:
    """What the store answers the request with, or the HTTP error a VBR would answer it with."""
    try:
        return store.serve(environment_id, path, query_params, method, body)
    except RouteNotFoundError:
        raise _UnmockedError(404, f"The requested resource /{path} was not found.")
    except MethodNotAllowedError:
        raise HTTPException(405, f"The {method} method is not allowed for /{path}.")
    except MockedError as exc:
        raise HTTPException(exc.status_code, exc.message)


def _login(form: dict[str, str]) -> str | None:
    """The environment a token request logs in to, or ``None`` when its password is wrong."""
    if form.get("grant_type") == "refresh_token":
        return _environment_id(form.get("refresh_token", ""))
    if form.get("password") != PASSWORD:
        return None
    return form.get("username", "")


def _environment_id(token: str) -> str:
    return token.removeprefix(_TOKEN_PREFIX) if token.startswith(_TOKEN_PREFIX) else ""


def _query_params(request: Request) -> dict:
    """The query as ``name -> value``, or ``name -> [values]`` for a parameter given more than once.

    VBR's list filters take several values as a repeated parameter (``resultFilter=Failed&resultFilter=Warning``)
    and match any of them; keeping only the last value would silently narrow the result.
    """
    params: dict = {}
    for key, value in request.query_params.multi_items():
        if key not in params:
            params[key] = value
        elif isinstance(params[key], list):
            params[key].append(value)
        else:
            params[key] = [params[key], value]
    return params


def effective_query_params(query_params: dict, body: Any) -> dict:
    """Fold a request body's ``pagination`` into the params the presenter sees.

    VBR's inventory browser carries `skip`/`limit` in the body rather than the query, so
    without this the presenter would page every POST from the top. An explicit query parameter
    still wins, which keeps the query the single way to override paging.

    Only whole numbers are carried over. JSON can say `null` — or a float, or a bool — where a
    query string cannot, and the presenter reads these as text it will call ``int()`` on. A
    bound VBR could not use is dropped so the default applies, which is what its own
    ``GetSkip``/``GetLimit`` do with a null.
    """
    pagination = body.get("pagination") if isinstance(body, dict) else None
    if not isinstance(pagination, dict):
        return query_params
    from_body = {
        key: str(value)
        for key, value in pagination.items()
        if key in ("skip", "limit") and isinstance(value, int) and not isinstance(value, bool)
    }
    return from_body | query_params


async def _json_body(request: Request) -> Any:
    """The request's JSON body, or ``None`` when it has none or it is not JSON."""
    if request.method != "POST":
        return None
    try:
        return await request.json()
    except ValueError:
        return None
