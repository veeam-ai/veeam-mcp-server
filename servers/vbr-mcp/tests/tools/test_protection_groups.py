# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

from fastmcp import Client
from pytest_httpx import HTTPXMock

from tests.conftest import tool_data

BASE = "https://localhost:9419"
PROTECTION_GROUP_ID = "00000000-0000-4000-8000-000000000010"


def _add_token_response(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE}/api/oauth2/token", json={"access_token": "t", "refresh_token": "r"})


async def test_list_protection_groups_returns_rows(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/agents/protectionGroups?skip=0&limit=200",
        json={"data": [{"id": PROTECTION_GROUP_ID}], "pagination": {"total": 1}},
    )

    result = await mcp_client.call_tool("list_protection_groups", {})

    assert tool_data(result) == [{"id": PROTECTION_GROUP_ID}]


async def test_get_protection_group_entities_narrows_by_agent_status(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/agents/protectionGroups/{PROTECTION_GROUP_ID}/discoveredEntities?agentStatusFilter=NotInstalled&skip=0&limit=200",
        json={"data": [{"id": "c1", "type": "Computer", "agentStatus": "NotInstalled"}], "pagination": {"total": 1}},
    )

    result = await mcp_client.call_tool(
        "get_protection_group_entities",
        {"protection_group_id": PROTECTION_GROUP_ID, "agent_status_filter": "NotInstalled"},
    )

    assert tool_data(result) == [{"id": "c1", "type": "Computer", "agentStatus": "NotInstalled"}]
