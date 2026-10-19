# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

import ssl

import httpx
import pytest
from fastmcp.exceptions import ToolError
from pytest_httpx import HTTPXMock

from vbr_mcp.vbr_client import VbrClient

TOKEN_URL = "https://vbr.example.com:9419/api/oauth2/token"


def _add_token_response(httpx_mock: HTTPXMock, access_token: str = "token-1", refresh_token: str = "refresh-1"):
    httpx_mock.add_response(
        url=TOKEN_URL, json={"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}
    )


async def test_get_authenticates_then_sends_bearer_token(vbr_client: VbrClient, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock, access_token="token-1")
    httpx_mock.add_response(url="https://vbr.example.com:9419/api/v1/serverInfo", json={"name": "vbr-01"})

    result = await vbr_client.get("/api/v1/serverInfo")

    assert result == {"name": "vbr-01"}
    requests = httpx_mock.get_requests()
    login_request = requests[0]
    assert login_request.url == TOKEN_URL
    assert "grant_type=password" in login_request.read().decode()
    data_request = requests[1]
    assert data_request.headers["Authorization"] == "Bearer token-1"
    assert data_request.headers["x-api-version"] == "1.3-rev2"


async def test_get_reuses_cached_token_across_calls(vbr_client: VbrClient, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(url="https://vbr.example.com:9419/api/v1/serverInfo", json={"name": "vbr-01"})
    httpx_mock.add_response(url="https://vbr.example.com:9419/api/v1/serverTime", json={"serverTime": "now"})

    await vbr_client.get("/api/v1/serverInfo")
    await vbr_client.get("/api/v1/serverTime")

    login_requests = [r for r in httpx_mock.get_requests() if r.url == TOKEN_URL]
    assert len(login_requests) == 1


async def test_get_on_expired_token_reauthenticates_and_retries(vbr_client: VbrClient, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock, access_token="token-1")
    httpx_mock.add_response(
        url="https://vbr.example.com:9419/api/v1/serverInfo", status_code=401, json={"error": "unauthorized"}
    )
    _add_token_response(httpx_mock, access_token="token-2")
    httpx_mock.add_response(url="https://vbr.example.com:9419/api/v1/serverInfo", json={"name": "vbr-01"})

    result = await vbr_client.get("/api/v1/serverInfo")

    assert result == {"name": "vbr-01"}
    data_requests = [r for r in httpx_mock.get_requests() if r.url != TOKEN_URL]
    assert data_requests[-1].headers["Authorization"] == "Bearer token-2"


async def test_get_with_bad_credentials_raises_tool_error(vbr_client: VbrClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=TOKEN_URL, status_code=400, json={"error": "invalid_grant"})

    with pytest.raises(ToolError, match=r"check credentials \(VBR_USERNAME, VBR_PASSWORD\)"):
        await vbr_client.get("/api/v1/serverInfo")


async def test_get_on_missing_object_raises_not_found_tool_error(vbr_client: VbrClient, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(url="https://vbr.example.com:9419/api/v1/jobs/unknown", status_code=404)

    with pytest.raises(ToolError, match="not found"):
        await vbr_client.get("/api/v1/jobs/unknown")


async def test_post_rejected_by_vbr_surfaces_its_error_message(vbr_client: VbrClient, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(
        url="https://vbr.example.com:9419/api/v1/restore/vmRestore/vSphere",
        status_code=400,
        json={"errorCode": "UnexpectedContent", "message": "Restore point ID is not valid."},
    )

    with pytest.raises(ToolError, match=r"HTTP 400\)\. UnexpectedContent: Restore point ID is not valid\.$"):
        await vbr_client.post("/api/v1/restore/vmRestore/vSphere", json={})


async def test_post_rejected_with_non_json_body_keeps_the_generic_message(vbr_client: VbrClient, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(
        url="https://vbr.example.com:9419/api/v1/restore/vmRestore/vSphere", status_code=500, text="<html>oops</html>"
    )

    with pytest.raises(ToolError, match=r"^The VBR server returned an error \(HTTP 500\)\.$"):
        await vbr_client.post("/api/v1/restore/vmRestore/vSphere", json={})


async def test_post_on_network_error_raises_tool_error(vbr_client: VbrClient, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_exception(httpx.ConnectError("connection refused"))

    with pytest.raises(ToolError, match="Could not reach"):
        await vbr_client.post("/api/v1/jobs/job-1/start")


async def test_network_error_names_the_url_and_the_setting(vbr_client: VbrClient, httpx_mock: HTTPXMock):
    httpx_mock.add_exception(httpx.ConnectError("connection refused"))

    with pytest.raises(ToolError, match=r"https://vbr\.example\.com:9419\. Check VBR_BASE_URL"):
        await vbr_client.get("/api/v1/serverInfo")


def _certificate_error(verify_code: int, verify_message: str) -> httpx.ConnectError:
    """A failed certificate check as httpcore raises it: only the context of the ConnectError, not in its message."""
    error = httpx.ConnectError("TLS handshake failed")
    cause = ssl.SSLCertVerificationError(
        1, f"[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: {verify_message}"
    )
    cause.verify_code = verify_code
    cause.verify_message = verify_message
    error.__context__ = cause
    return error


async def test_untrusted_certificate_says_how_to_trust_it(vbr_client: VbrClient, httpx_mock: HTTPXMock):
    httpx_mock.add_exception(_certificate_error(18, "self-signed certificate"))

    with pytest.raises(ToolError) as raised:
        await vbr_client.get("/api/v1/serverInfo")

    message = str(raised.value)
    assert "not trusted on this machine (often a self-signed certificate)" in message
    # httpx verifies against certifi, not the OS store: SSL_CERT_FILE is what makes it trust a certificate
    assert "point SSL_CERT_FILE at a PEM file" in message
    assert message.endswith("or set VBR_VERIFY_TLS=false if you trust this server.")


@pytest.mark.parametrize(
    ("verify_code", "verify_message"),
    [
        (62, "Hostname mismatch, certificate is not valid for 'vbr.example.com'."),
        (64, "IP address mismatch, certificate is not valid for '10.0.0.5'."),
    ],
)
async def test_certificate_for_another_name_says_to_use_its_name(
    vbr_client: VbrClient, httpx_mock: HTTPXMock, verify_code: int, verify_message: str
):
    httpx_mock.add_exception(_certificate_error(verify_code, verify_message))

    with pytest.raises(
        ToolError, match=r"is not issued for vbr\.example\.com: set VBR_BASE_URL to a host name"
    ) as raised:
        await vbr_client.get("/api/v1/serverInfo")

    assert "self-signed" not in str(raised.value)


async def test_expired_certificate_says_so(vbr_client: VbrClient, httpx_mock: HTTPXMock):
    httpx_mock.add_exception(_certificate_error(10, "certificate has expired"))

    with pytest.raises(
        ToolError, match=r"TLS certificate of the VBR server at https://vbr\.example\.com:9419 has expired"
    ):
        await vbr_client.get("/api/v1/serverInfo")


async def test_certificate_not_valid_yet_points_at_the_clocks(vbr_client: VbrClient, httpx_mock: HTTPXMock):
    httpx_mock.add_exception(_certificate_error(9, "certificate is not yet valid"))

    with pytest.raises(ToolError, match=r"is not valid yet: check the clock of this machine and of the server"):
        await vbr_client.get("/api/v1/serverInfo")


async def test_other_certificate_failure_names_openssl_reason(vbr_client: VbrClient, httpx_mock: HTTPXMock):
    httpx_mock.add_exception(_certificate_error(26, "unsuitable certificate purpose"))

    with pytest.raises(ToolError, match=r"\(unsuitable certificate purpose\): fix the server's certificate"):
        await vbr_client.get("/api/v1/serverInfo")


async def test_timeout_names_the_limit(vbr_client: VbrClient, httpx_mock: HTTPXMock):
    httpx_mock.add_exception(httpx.ReadTimeout("timed out"))

    with pytest.raises(ToolError, match=r"did not respond within 30 s \(VBR_REQUEST_TIMEOUT_SEC\)") as raised:
        await vbr_client.get("/api/v1/serverInfo")

    assert "may have carried it out" not in str(raised.value)  # a read changes nothing


async def test_action_that_timed_out_after_it_was_sent_may_have_run(vbr_client: VbrClient, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_exception(httpx.ReadTimeout("timed out"), url="https://vbr.example.com:9419/api/v1/jobs/job-1/start")

    with pytest.raises(ToolError, match=r"did not respond within 30 s .* VBR may have carried it out"):
        await vbr_client.post("/api/v1/jobs/job-1/start")


async def test_action_whose_connection_broke_after_it_was_sent_may_have_run(
    vbr_client: VbrClient, httpx_mock: HTTPXMock
):
    _add_token_response(httpx_mock)
    httpx_mock.add_exception(
        httpx.RemoteProtocolError("Server disconnected without sending a response."),
        url="https://vbr.example.com:9419/api/v1/jobs/job-1/start",
    )

    with pytest.raises(ToolError) as raised:
        await vbr_client.post("/api/v1/jobs/job-1/start")

    message = str(raised.value)
    assert "broke before it answered (Server disconnected without sending a response)." in message
    assert "VBR may have carried it out: check the state of what it changes before repeating it." in message
    assert "Could not reach" not in message


async def test_read_whose_connection_broke_says_to_try_again(vbr_client: VbrClient, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_exception(httpx.ReadError("connection reset"), url="https://vbr.example.com:9419/api/v1/serverInfo")

    with pytest.raises(ToolError, match=r"broke before it answered \(connection reset\)\. Try again") as raised:
        await vbr_client.get("/api/v1/serverInfo")

    assert "may have carried it out" not in str(raised.value)


async def test_connection_break_over_plain_http_points_at_https(httpx_mock: HTTPXMock):
    client = VbrClient(base_url="http://vbr.example.com:9419", username="admin", password="secret")
    httpx_mock.add_exception(httpx.ReadError(""))

    try:
        with pytest.raises(ToolError, match=r"\(ReadError\)\. VBR_BASE_URL starts with http://, but the VBR REST API"):
            await client.get("/api/v1/serverInfo")
    finally:
        await client.aclose()


@pytest.mark.parametrize(
    "login_answer",
    [{"text": "<html><body>Welcome</body></html>"}, {"json": {"token_type": "bearer"}}],
    ids=["html page", "json without a token"],
)
async def test_login_answered_without_a_token_points_at_the_base_url(
    vbr_client: VbrClient, httpx_mock: HTTPXMock, login_answer: dict
):
    httpx_mock.add_response(url=TOKEN_URL, **login_answer)

    with pytest.raises(
        ToolError, match=r"answered the login with something other than a VBR access token: check that VBR_BASE_URL"
    ):
        await vbr_client.get("/api/v1/serverInfo")


async def test_answer_that_is_not_json_points_at_the_base_url(vbr_client: VbrClient, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(url="https://vbr.example.com:9419/api/v1/serverInfo", text="<html>portal</html>")

    with pytest.raises(ToolError, match=r"answered with something other than JSON: check that VBR_BASE_URL"):
        await vbr_client.get("/api/v1/serverInfo")


async def test_post_with_no_content_response_returns_none(vbr_client: VbrClient, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(url="https://vbr.example.com:9419/api/v1/jobs/job-1/start", status_code=204)

    result = await vbr_client.post("/api/v1/jobs/job-1/start")

    assert result is None


async def test_post_read_timeout_warns_the_action_may_still_run(vbr_client: VbrClient, httpx_mock: HTTPXMock):
    # VBR received the request: telling the caller "no response" alone invites a retry that starts the action twice.
    _add_token_response(httpx_mock)
    httpx_mock.add_exception(httpx.ReadTimeout("read timed out"))

    with pytest.raises(ToolError, match=r"VBR may have carried it out: .* `list_sessions` shows the actions"):
        await vbr_client.post("/api/v1/restore/instantRecovery/vSphere/vm/m1/migrate", json={})


async def test_post_connect_timeout_does_not_warn_the_action_may_have_run(vbr_client: VbrClient, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_exception(httpx.ConnectTimeout("connect timed out"))

    with pytest.raises(ToolError, match=r"did not respond within 30 s") as raised:
        await vbr_client.post("/api/v1/jobs/j1/start", json={})

    assert "may have carried it out" not in str(raised.value)  # it never reached VBR


@pytest.mark.parametrize("as_text", [False, True], ids=["post", "post_text"])
async def test_read_only_post_timeout_does_not_warn_the_action_may_have_run(
    vbr_client: VbrClient, httpx_mock: HTTPXMock, as_text: bool
):
    _add_token_response(httpx_mock)
    httpx_mock.add_exception(httpx.ReadTimeout("read timed out"))

    query = (
        vbr_client.post_text("/api/v1/license/createReport", json={}, read_only=True)
        if as_text
        else vbr_client.post("/api/v1/inventory", json={}, read_only=True)
    )

    with pytest.raises(ToolError, match=r"did not respond within 30 s") as raised:
        await query

    assert "may have carried it out" not in str(raised.value)  # a query changes nothing


async def test_timeout_override_is_the_limit_the_error_names(vbr_client: VbrClient, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_exception(httpx.ReadTimeout("read timed out"))

    with pytest.raises(ToolError, match=r"did not respond within 600 s\. ") as raised:
        await vbr_client.post("/api/v1/restore/vmRestore/vSphere", json={}, timeout=600.0)

    assert "VBR_REQUEST_TIMEOUT_SEC" not in str(raised.value)  # the setting does not govern this request


async def test_post_timeout_override_reaches_the_request(vbr_client: VbrClient, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(url="https://vbr.example.com:9419/api/v1/restore/vmRestore/vSphere", json={"id": "s1"})

    await vbr_client.post("/api/v1/restore/vmRestore/vSphere", json={}, timeout=600.0)

    posted = next(r for r in httpx_mock.get_requests() if r.url.path == "/api/v1/restore/vmRestore/vSphere")
    assert posted.extensions["timeout"] == {"connect": 600.0, "read": 600.0, "write": 600.0, "pool": 600.0}
