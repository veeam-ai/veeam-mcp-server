# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

from fastmcp import Client
from pytest_httpx import HTTPXMock

BASE = "https://localhost:9419"


def _add_token_response(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE}/api/oauth2/token", json={"access_token": "t", "refresh_token": "r"})


async def test_get_server_status_merges_server_info_and_server_time(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(url=f"{BASE}/api/v1/serverInfo", json={"name": "vbr-01", "buildVersion": "13.1.0.379"})
    httpx_mock.add_response(url=f"{BASE}/api/v1/serverTime", json={"serverTime": "2026-09-21T10:00:00.0000000Z"})

    result = await mcp_client.call_tool("get_server_status", {})

    assert result.data == {
        "name": "vbr-01",
        "buildVersion": "13.1.0.379",
        "serverTime": "2026-09-21T10:00:00.0000000Z",
    }
