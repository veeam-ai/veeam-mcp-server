# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

from fastmcp import Client
from pytest_httpx import HTTPXMock

from tests.conftest import tool_data

BASE = "https://localhost:9419"
BACKUP_ID = "00000000-0000-4000-8000-000000000001"


def _add_token_response(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE}/api/oauth2/token", json={"access_token": "t", "refresh_token": "r"})


async def test_list_backups_returns_rows(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/backups?skip=0&limit=200",
        json={"data": [{"id": BACKUP_ID, "jobId": None}], "pagination": {"total": 1}},
    )

    result = await mcp_client.call_tool("list_backups", {})

    assert tool_data(result) == [{"id": BACKUP_ID, "jobId": None}]


async def test_get_backup_details_defaults_to_both_objects_and_files(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/backups/{BACKUP_ID}/objects?skip=0&limit=200",
        json={"data": [{"id": "obj1"}], "pagination": {"total": 1}},
    )
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/backups/{BACKUP_ID}/backupFiles?orderColumn=CreationTime&orderAsc=false&skip=0&limit=50",
        json={"data": [{"name": "file1.vbk"}], "pagination": {"total": 1}},
    )

    result = await mcp_client.call_tool("get_backup_details", {"backup_id": BACKUP_ID})

    assert tool_data(result) == {
        "backupId": BACKUP_ID,
        "objects": [{"id": "obj1"}],
        "files": [{"name": "file1.vbk"}],
        "filesTotal": 1,
    }


async def test_get_backup_details_include_files_only(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/backups/{BACKUP_ID}/backupFiles?orderColumn=CreationTime&orderAsc=false&skip=0&limit=50",
        json={"data": [{"name": "file1.vbk"}], "pagination": {"total": 1}},
    )

    result = await mcp_client.call_tool("get_backup_details", {"backup_id": BACKUP_ID, "include": ["files"]})

    data = tool_data(result)
    assert "objects" not in data
    assert data["files"] == [{"name": "file1.vbk"}]
