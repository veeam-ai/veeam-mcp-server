# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

from fastmcp import Client
from pytest_httpx import HTTPXMock

from tests.conftest import tool_data

BASE = "https://localhost:9419"
SESSION_ID = "00000000-0000-4000-8000-000000000013"


def _add_token_response(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE}/api/oauth2/token", json={"access_token": "t", "refresh_token": "r"})


async def test_list_sessions_with_id_reads_one_session(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(url=f"{BASE}/api/v1/sessions/{SESSION_ID}", json={"id": SESSION_ID, "state": "Stopped"})

    result = await mcp_client.call_tool("list_sessions", {"id": SESSION_ID})

    assert result.data == {"id": SESSION_ID, "state": "Stopped"}


async def test_list_sessions_count_only_reads_just_the_total(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/sessions?resultFilter=Failed&limit=1",
        json={"data": [{"id": SESSION_ID}], "pagination": {"total": 37}},
    )

    result = await mcp_client.call_tool("list_sessions", {"result_filter": ["Failed"], "count_only": True})

    assert result.data == {"total": 37}


async def test_list_sessions_pages_with_its_filters(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/sessions?orderColumn=CreationTime&orderAsc=false&typeFilter=BackupJob&skip=0&limit=200",
        json={"data": [{"id": SESSION_ID}], "pagination": {"total": 1}},
    )

    result = await mcp_client.call_tool(
        "list_sessions", {"type_filter": ["BackupJob"], "order_column": "CreationTime", "order_asc": False}
    )

    assert tool_data(result) == [{"id": SESSION_ID}]


async def test_list_task_sessions_scopes_by_session_id(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/taskSessions?sessionIdFilter={SESSION_ID}&skip=0&limit=200",
        json={"data": [{"id": "t1", "name": "vm1"}], "pagination": {"total": 1}},
    )

    result = await mcp_client.call_tool("list_task_sessions", {"session_id_filter": SESSION_ID})

    assert tool_data(result) == [{"id": "t1", "name": "vm1"}]


async def test_get_session_failure_details_joins_session_and_task_logs(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/sessions/{SESSION_ID}/logs",
        json={"records": [{"status": "Failed", "title": "job failed"}, {"status": "Success", "title": "ok"}]},
    )
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/sessions/{SESSION_ID}/taskSessions?skip=0&limit=200",
        json={
            "data": [
                {"id": "t1", "name": "vm1", "result": {"result": "Failed", "message": "disk error"}},
                {"id": "t2", "name": "vm2", "result": {"result": "Success"}},
            ],
            "pagination": {"total": 2},
        },
    )
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/taskSessions/t1/logs",
        json={"records": [{"status": "Failed", "title": "disk read error"}]},
    )

    result = await mcp_client.call_tool("get_session_failure_details", {"session_id": SESSION_ID})

    data = result.data
    assert data["sessionId"] == SESSION_ID
    assert data["records"] == [{"status": "Failed", "title": "job failed"}]
    assert len(data["tasks"]) == 1
    assert data["tasks"][0]["id"] == "t1"
    assert data["tasks"][0]["logs"] == [{"status": "Failed", "title": "disk read error"}]
    assert data["tasksTruncated"] is False
