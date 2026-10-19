# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

from fastmcp import Client
from pytest_httpx import HTTPXMock

BASE = "https://localhost:9419"


def _add_token_response(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE}/api/oauth2/token", json={"access_token": "t", "refresh_token": "r"})


async def test_get_config_backup_status_returns_the_raw_model(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(url=f"{BASE}/api/v1/configBackup", json={"isEnabled": True})

    result = await mcp_client.call_tool("get_config_backup_status", {})

    assert result.data == {"isEnabled": True}


async def test_start_config_backup_posts_to_the_backup_endpoint(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(url=f"{BASE}/api/v1/configBackup/backup", status_code=204)

    await mcp_client.call_tool("start_config_backup", {})

    posted = [r for r in httpx_mock.get_requests() if r.url.path == "/api/v1/configBackup/backup"]
    assert len(posted) == 1
    assert posted[0].method == "POST"
