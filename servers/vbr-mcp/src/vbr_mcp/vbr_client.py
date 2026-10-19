# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

from __future__ import annotations

import ssl
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
from fastmcp.exceptions import ToolError
from pydantic_core import to_jsonable_python

_TOKEN_PATH = "/api/oauth2/token"


class VbrClient:
    """Async client for the VBR REST API.

    Does OAuth2 password-grant auth with refresh, and exposes JSON GET/POST helpers that raise `ToolError` on any
    failure.
    """

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        *,
        verify_tls: bool = True,
        api_version: str = "1.3-rev2",
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._username = username
        self._password = password
        self._api_version = api_version
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            verify=verify_tls,
            timeout=timeout,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get(self, path: str, params: dict[str, object] | None = None) -> Any:
        return await self._request("GET", path, action=False, params=_encode_query(params))

    async def post(
        self,
        path: str,
        json: dict[str, object] | None = None,
        *,
        timeout: float | None = None,
        read_only: bool = False,
    ) -> Any:
        """POST a JSON body.

        `timeout` (seconds) overrides the client default for endpoints VBR answers slowly. `read_only` marks a query
        that takes its parameters in the body and changes nothing, so a failure after it was sent is not reported as
        an action VBR may have carried out.
        """
        kwargs: dict[str, Any] = {"json": _encode_body(json)}
        if timeout is not None:
            kwargs["timeout"] = timeout
        return await self._request("POST", path, action=not read_only, **kwargs)

    async def post_text(self, path: str, json: dict[str, object] | None = None, *, read_only: bool = False) -> str:
        """POST and return the raw response body as text.

        For endpoints that reply with a non-JSON payload, e.g. a generated report. `read_only` is as in `post`.
        """
        response = await self._request_raw("POST", path, action=not read_only, json=_encode_body(json))
        return response.text

    async def _request(self, method: str, path: str, *, action: bool, **kwargs: Any) -> Any:
        response = await self._request_raw(method, path, action=action, **kwargs)
        return self._parse(response)

    async def _request_raw(self, method: str, path: str, *, action: bool, **kwargs: Any) -> httpx.Response:
        await self._ensure_token()
        response = await self._send(method, path, action=action, **kwargs)
        if response.status_code == 401:
            await self._authenticate()
            response = await self._send(method, path, action=action, **kwargs)
        if response.status_code >= 400:
            self._parse(response)  # raises the matching ToolError
        return response

    async def _send(self, method: str, path: str, *, action: bool, **kwargs: Any) -> httpx.Response:
        headers = {"x-api-version": self._api_version, "Authorization": f"Bearer {self._access_token}"}
        try:
            return await self._client.request(method, path, headers=headers, **kwargs)
        except httpx.TransportError as e:
            raise self._connection_error(e, action=action, timeout=kwargs.get("timeout")) from e

    async def _ensure_token(self) -> None:
        if self._access_token is not None:
            return
        if self._refresh_token is not None:
            try:
                await self._refresh()
                return
            except ToolError:
                self._refresh_token = None
        await self._authenticate()

    async def _authenticate(self) -> None:
        self._access_token = None
        data = {"grant_type": "password", "username": self._username, "password": self._password}
        await self._login(
            data,
            on_failure="Could not authenticate with the VBR server: check credentials (VBR_USERNAME, VBR_PASSWORD).",
        )

    async def _refresh(self) -> None:
        data = {"grant_type": "refresh_token", "refresh_token": self._refresh_token}
        await self._login(data, on_failure="Could not refresh the VBR session.")

    async def _login(self, data: Mapping[str, str | None], *, on_failure: str) -> None:
        try:
            response = await self._client.post(_TOKEN_PATH, data=data, headers={"x-api-version": self._api_version})
        except httpx.TransportError as e:
            raise self._connection_error(e) from e
        if response.status_code >= 400:
            raise ToolError(on_failure)
        payload = _json_or_none(response)
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token:
            raise ToolError(
                f"The server at {self._base_url} answered the login with something other than a VBR access token: "
                "check that VBR_BASE_URL points at the VBR REST API (https://<backup server>:9419 by default)."
            )
        self._access_token = token
        self._refresh_token = payload.get("refresh_token", self._refresh_token)

    def _connection_error(
        self, error: httpx.TransportError, *, action: bool = False, timeout: float | None = None
    ) -> ToolError:
        """Why a request to the VBR server failed in transport, naming what to check.

        A certificate the client does not trust fails the TLS handshake with a `ConnectError` too, but it needs a
        different fix than an unreachable host, so it gets its own message. `action` is a request that changes
        something in VBR: once it went out, a connection that breaks or times out before the answer leaves open whether
        VBR carried it out, and repeating it blindly could do it twice. `timeout` is the request's own limit when it
        overrode the client default.
        """
        if (certificate_error := _certificate_error(error)) is not None:
            return ToolError(self._certificate_message(certificate_error))
        sent = not isinstance(error, _NOT_SENT)
        maybe_done = (
            " The request had already been sent, so VBR may have carried it out: check the state of what it changes "
            "before repeating it. `list_sessions` shows the actions VBR has started."
            if action and sent
            else ""
        )
        if isinstance(error, httpx.TimeoutException):
            limit = f"{self._timeout:g} s (VBR_REQUEST_TIMEOUT_SEC)" if timeout is None else f"{timeout:g} s"
            return ToolError(
                f"The VBR server at {self._base_url} did not respond within {limit}. "
                "It may be overloaded, or a firewall may be dropping the connection." + maybe_done
            )
        if sent:
            detail = str(error).strip().rstrip(".") or type(error).__name__
            plain_http = (
                " VBR_BASE_URL starts with http://, but the VBR REST API is served over https only."
                if httpx.URL(self._base_url).scheme == "http"
                else ""
            )
            retry = " Try again; if it keeps failing, check the server and any proxy or firewall in between."
            return ToolError(
                f"The connection to the VBR server at {self._base_url} broke before it answered ({detail})."
                + plain_http
                + (maybe_done or ("" if plain_http else retry))
            )
        return ToolError(
            f"Could not reach the VBR server at {self._base_url}. Check VBR_BASE_URL, that the host name resolves, "
            "and that the VBR REST API port (9419 by default) is open from this machine."
        )

    def _certificate_message(self, error: ssl.SSLCertVerificationError) -> str:
        """What a failed check of the server's certificate means to fix, by OpenSSL's verify code."""
        server = f"the VBR server at {self._base_url}"
        opt_out = "or set VBR_VERIFY_TLS=false if you trust this server."
        code = getattr(error, "verify_code", None)
        if code in _HOST_MISMATCH:
            return (
                f"The TLS certificate of {server} is not issued for {httpx.URL(self._base_url).host}: set "
                f"VBR_BASE_URL to a host name the certificate names (usually the server's full DNS name), {opt_out}"
            )
        if code == _EXPIRED:
            return f"The TLS certificate of {server} has expired: renew the server's certificate, {opt_out}"
        if code == _NOT_YET_VALID:
            return (
                f"The TLS certificate of {server} is not valid yet: check the clock of this machine and of the server, "
                f"{opt_out}"
            )
        if code in _UNTRUSTED:
            return (
                f"Could not verify the TLS certificate of {server}: it is not trusted on this machine (often a "
                "self-signed certificate). vbr-mcp checks certificates against its own CA bundle, not the operating "
                "system's certificate store: point SSL_CERT_FILE at a PEM file with the server's certificate or its "
                f"CA, {opt_out}"
            )
        reason = getattr(error, "verify_message", None) or str(error)
        return f"Could not verify the TLS certificate of {server} ({reason}): fix the server's certificate, {opt_out}"

    def _parse(self, response: httpx.Response) -> Any:
        if response.status_code == 404:
            raise ToolError("The requested VBR object was not found." + _error_detail(response))
        if response.status_code == 403:
            raise ToolError("The VBR account is not authorized to perform this action." + _error_detail(response))
        if response.status_code >= 400:
            raise ToolError(
                f"The VBR server returned an error (HTTP {response.status_code})." + _error_detail(response)
            )
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError as e:
            raise ToolError(
                f"The server at {self._base_url} answered with something other than JSON: check that VBR_BASE_URL "
                "points at the VBR REST API (https://<backup server>:9419 by default)."
            ) from e


_NOT_SENT = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
    httpx.ProxyError,
    httpx.UnsupportedProtocol,
    httpx.LocalProtocolError,
)
"""Transport errors raised before a request reached the server: it cannot have acted on it."""

# OpenSSL's X509_V_ERR_* verify codes, as `ssl.SSLCertVerificationError.verify_code` carries them.
_HOST_MISMATCH = frozenset({62, 64})  # HOSTNAME_MISMATCH, IP_ADDRESS_MISMATCH
_EXPIRED = 10  # CERT_HAS_EXPIRED
_NOT_YET_VALID = 9  # CERT_NOT_YET_VALID
# UNABLE_TO_GET_ISSUER_CERT, DEPTH_ZERO_SELF_SIGNED_CERT, SELF_SIGNED_CERT_IN_CHAIN,
# UNABLE_TO_GET_ISSUER_CERT_LOCALLY, UNABLE_TO_VERIFY_LEAF_SIGNATURE
_UNTRUSTED = frozenset({2, 18, 19, 20, 21})


def _certificate_error(error: BaseException) -> ssl.SSLCertVerificationError | None:
    """The failed TLS certificate check ``error`` is, or was raised from, if any."""
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        if isinstance(current, ssl.SSLCertVerificationError):
            return current
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return None


def _json_or_none(response: httpx.Response) -> Any:
    """The response's JSON body, or ``None`` when it is not JSON (an HTML page, an empty body)."""
    try:
        return response.json()
    except ValueError:
        return None


def _encode_query(params: Mapping[str, object] | None) -> dict[str, object] | None:
    """Render typed tool arguments as VBR query values; list values stay lists (sent as repeated params)."""
    if params is None:
        return None
    return {
        key: [_encode_query_value(item) for item in value] if isinstance(value, list) else _encode_query_value(value)
        for key, value in params.items()
    }


def _encode_query_value(value: object) -> object:
    if isinstance(value, datetime):
        # Tools treat an offset-less timestamp as UTC, so it is sent with an explicit offset.
        return (value if value.tzinfo else value.replace(tzinfo=UTC)).isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


def _encode_body(body: Mapping[str, object] | None) -> Any:
    """Make a request body JSON-serializable: UUIDs, datetimes and models become their JSON forms."""
    return None if body is None else to_jsonable_python(body)


def _error_detail(response: httpx.Response) -> str:
    """VBR's own explanation from an error response body, as a suffix for the ToolError message.

    VBR replies to a rejected request with `{"errorCode": ..., "message": ...}`; passing the message on lets the
    caller see which field was wrong and fix the request. Empty when the body carries no such message.
    """
    try:
        payload = response.json()
    except ValueError:
        return ""
    message = payload.get("message") if isinstance(payload, dict) else None
    if not isinstance(message, str) or not message.strip():
        return ""
    error_code = payload.get("errorCode")
    prefix = f"{error_code}: " if isinstance(error_code, str) and error_code else ""
    return f" {prefix}{message.strip()}"
