# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

from datetime import UTC, datetime

from pytest_httpx import HTTPXMock

from vbr_mcp.server_time import get_server_time
from vbr_mcp.vbr_client import VbrClient

TOKEN_URL = "https://vbr.example.com:9419/api/oauth2/token"
SERVER_TIME_URL = "https://vbr.example.com:9419/api/v1/serverTime"


def _add_token_response(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=TOKEN_URL, json={"access_token": "token-1", "refresh_token": "refresh-1"})


async def test_get_server_time_parses_the_vbr_clock(vbr_client: VbrClient, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(url=SERVER_TIME_URL, json={"serverTime": "2026-09-21T10:00:00.1234567Z"})

    result = await get_server_time(vbr_client)

    assert result == datetime(2026, 9, 21, 10, 0, 0, 123456, tzinfo=UTC)


async def test_get_server_time_falls_back_to_now_on_endpoint_failure(vbr_client: VbrClient, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(url=SERVER_TIME_URL, status_code=500)

    before = datetime.now(UTC)
    result = await get_server_time(vbr_client)
    after = datetime.now(UTC)

    assert before <= result <= after
