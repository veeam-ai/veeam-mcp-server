# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

from fastmcp import Client
from pytest_httpx import HTTPXMock

BASE = "https://localhost:9419"


async def test_get_general_options_returns_the_raw_model(mcp_client: Client, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE}/api/oauth2/token", json={"access_token": "t", "refresh_token": "r"})
    httpx_mock.add_response(url=f"{BASE}/api/v1/generalOptions", json={"notificationEnabled": False})

    result = await mcp_client.call_tool("get_general_options", {})

    assert result.data == {"notificationEnabled": False}
