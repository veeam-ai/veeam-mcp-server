# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

import json

import httpx
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from pytest_httpx import HTTPXMock

from tests.conftest import tool_data

BASE = "https://localhost:9419"
NAS_SERVER_ID = "00000000-0000-4000-8000-000000000006"


def _add_token_response(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE}/api/oauth2/token", json={"access_token": "t", "refresh_token": "r"})


async def test_list_unstructured_data_servers_without_id_lists_all(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/inventory/unstructuredDataServers?skip=0&limit=200",
        json={"data": [{"id": NAS_SERVER_ID}], "pagination": {"total": 1}},
    )

    result = await mcp_client.call_tool("list_unstructured_data_servers", {})

    assert tool_data(result) == [{"id": NAS_SERVER_ID}]


async def test_list_unstructured_data_servers_with_id_reads_one(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/inventory/unstructuredDataServers/{NAS_SERVER_ID}",
        json={"id": NAS_SERVER_ID, "type": "SMBShare"},
    )

    result = await mcp_client.call_tool("list_unstructured_data_servers", {"id": NAS_SERVER_ID})

    assert result.data == {"id": NAS_SERVER_ID, "type": "SMBShare"}


async def test_browse_inventory_without_server_lists_managed_servers(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/inventory", json={"data": [{"name": "esx01"}], "pagination": {"total": 1}}
    )

    result = await mcp_client.call_tool("browse_inventory", {"hierarchy_type": "HostsAndClusters"})

    assert result.data == {"data": [{"name": "esx01"}], "pagination": {"total": 1}}
    assert _posted_body(httpx_mock, "/api/v1/inventory") == {
        "pagination": {"skip": 0, "limit": 200},
        "hierarchyType": "HostsAndClusters",
    }


async def test_browse_inventory_drills_into_a_server_with_combined_filters(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    path = "/api/v1/inventory/esx02.lab.local"
    httpx_mock.add_response(url=f"{BASE}{path}", json={"data": [], "pagination": {"total": 0}})
    raw_filter = {"type": "PredicateExpression", "property": "hostName", "operation": "Equals", "value": "x"}

    await mcp_client.call_tool(
        "browse_inventory",
        {
            "server_name": "esx02.lab.local",
            "hierarchy_type": "HostsAndDatastores",
            "name_filter": "ydd",
            "object_type": "Datastore",
            "filter": raw_filter,
            "sorting": {"property": "name", "direction": "Ascending"},
            "permission_scope": "Restore",
            "limit": 50,
        },
    )

    assert _posted_body(httpx_mock, path) == {
        "pagination": {"skip": 0, "limit": 50},
        "hierarchyType": "HostsAndDatastores",
        "filter": {
            "type": "GroupExpression",
            "operation": "And",
            "items": [
                {"type": "PredicateExpression", "property": "name", "operation": "Contains", "value": "ydd"},
                {"type": "PredicateExpression", "property": "type", "operation": "Equals", "value": "Datastore"},
                raw_filter,
            ],
        },
        "sorting": {"property": "name", "direction": "Ascending"},
        "permissionScope": "Restore",
    }


async def test_browse_inventory_escapes_the_server_name(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(url=f"{BASE}/api/v1/inventory/a%2Fb", json={"data": []})

    await mcp_client.call_tool("browse_inventory", {"server_name": "a/b"})

    assert any(r.url.raw_path == b"/api/v1/inventory/a%2Fb" for r in httpx_mock.get_requests())


async def test_browse_inventory_timeout_does_not_warn_of_a_change(mcp_client: Client, httpx_mock: HTTPXMock):
    # The browse is a POST, but only reads: a timeout cannot have left anything done in VBR.
    _add_token_response(httpx_mock)
    httpx_mock.add_exception(httpx.ReadTimeout("read timed out"), url=f"{BASE}/api/v1/inventory")

    with pytest.raises(ToolError) as raised:
        await mcp_client.call_tool("browse_inventory", {})

    assert "did not respond" in str(raised.value)
    assert "may have carried it out" not in str(raised.value)


def _posted_body(httpx_mock: HTTPXMock, path: str) -> dict:
    return json.loads(next(r for r in httpx_mock.get_requests() if r.url.path == path and r.method == "POST").read())
