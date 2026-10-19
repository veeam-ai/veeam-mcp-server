# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from pytest_httpx import HTTPXMock

from tests.conftest import tool_data

BASE = "https://localhost:9419"
BACKUP_OBJECT_ID = "00000000-0000-4000-8000-000000000011"
RESTORE_POINT_ID = "00000000-0000-4000-8000-000000000012"


def _add_token_response(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE}/api/oauth2/token", json={"access_token": "t", "refresh_token": "r"})


async def test_list_protected_objects_dedupes_by_id(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/backupObjects?skip=0&limit=200",
        json={"data": [{"id": "1", "name": "vm1"}, {"id": "1", "name": "vm1"}], "pagination": {"total": 2}},
    )

    result = await mcp_client.call_tool("list_protected_objects", {})

    assert tool_data(result) == [{"id": "1", "name": "vm1"}]


async def test_list_protected_objects_with_id_reads_restore_points_newest_first(
    mcp_client: Client, httpx_mock: HTTPXMock
):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/backupObjects/{BACKUP_OBJECT_ID}/restorePoints?orderColumn=CreationTime&orderAsc=false&skip=0&limit=200",
        json={"data": [{"id": RESTORE_POINT_ID}], "pagination": {"total": 1}},
    )

    result = await mcp_client.call_tool("list_protected_objects", {"id": BACKUP_OBJECT_ID})

    assert tool_data(result) == [{"id": RESTORE_POINT_ID}]


async def test_list_restore_points_threads_filters(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/restorePoints?backupObjectIdFilter={BACKUP_OBJECT_ID}&orderColumn=CreationTime&orderAsc=false&skip=0&limit=1",
        json={"data": [{"id": "rp-latest"}], "pagination": {"total": 1}},
    )

    result = await mcp_client.call_tool(
        "list_restore_points",
        {
            "backup_object_id_filter": BACKUP_OBJECT_ID,
            "order_column": "CreationTime",
            "order_asc": False,
            "max_items": 1,
        },
    )

    assert tool_data(result) == [{"id": "rp-latest"}]


async def test_get_restore_point_disks_reads_the_disks_endpoint(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/restorePoints/{RESTORE_POINT_ID}/disks?skip=0&limit=200",
        json={"data": [{"name": "disk1"}], "pagination": {"total": 1}},
    )

    result = await mcp_client.call_tool("get_restore_point_disks", {"restore_point_id": RESTORE_POINT_ID})

    assert tool_data(result) == [{"name": "disk1"}]


async def test_list_restore_points_sends_dates_as_utc_iso_8601(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(json={"data": [], "pagination": {"total": 0}})

    await mcp_client.call_tool(
        "list_restore_points",
        {"created_after_filter": "2024-05-01T10:00:00", "created_before_filter": "2024-05-02T00:00:00+03:00"},
    )

    request = next(r for r in httpx_mock.get_requests() if r.url.path == "/api/v1/restorePoints")
    assert request.url.params["createdAfterFilter"] == "2024-05-01T10:00:00+00:00"
    assert request.url.params["createdBeforeFilter"] == "2024-05-02T00:00:00+03:00"


async def test_list_restore_points_rejects_a_non_date(mcp_client: Client):
    with pytest.raises(ToolError, match="created_after_filter"):
        await mcp_client.call_tool("list_restore_points", {"created_after_filter": "yesterday"})


async def test_list_restore_points_sends_each_malware_status_as_a_repeated_param(
    mcp_client: Client, httpx_mock: HTTPXMock
):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(json={"data": [], "pagination": {"total": 0}})

    await mcp_client.call_tool("list_restore_points", {"malware_status_filter": ["Suspicious", "Infected"]})

    request = next(r for r in httpx_mock.get_requests() if r.url.path == "/api/v1/restorePoints")
    assert request.url.params.get_list("malwareStatusFilter") == ["Suspicious", "Infected"]
