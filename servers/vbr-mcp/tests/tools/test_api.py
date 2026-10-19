# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

import json

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from pytest_httpx import HTTPXMock

BASE = "https://localhost:9419"


def _add_token_response(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE}/api/oauth2/token", json={"access_token": "t", "refresh_token": "r"})


async def test_api_get_sends_the_path_and_query_params(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/restorePoints/rp-1/disks?limit=5", json={"data": [{"name": "web01"}], "pagination": {}}
    )

    result = await mcp_client.call_tool("api_get", {"path": "/api/v1/restorePoints/rp-1/disks", "params": {"limit": 5}})

    assert result.structured_content == {"data": [{"name": "web01"}], "pagination": {}}


@pytest.mark.parametrize(
    "path",
    [
        "/api/oauth2/token",
        "https://evil.example.com/api/v1/jobs",
        "/api/v1/../oauth2/token",
        "/api/v1/jobs?limit=1",
        "/api/v1//jobs",
    ],
)
async def test_api_get_refuses_paths_outside_the_rest_api(mcp_client: Client, path: str):
    with pytest.raises(ToolError, match=r"Path must start with /api/v1/|Invalid path"):
        await mcp_client.call_tool("api_get", {"path": path})


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/inventory",
        "/api/v1/inventory/vc01.lab.local",
        "/api/v1/inventory/physical/all",
        "/api/v1/inventory/retrieveMachineDetails",
        "/api/v1/restorePoints/rp-1/networkInfo",
        "/api/v1/acl",
    ],
)
async def test_api_post_query_allows_read_only_query_endpoints(mcp_client: Client, httpx_mock: HTTPXMock, path: str):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(url=f"{BASE}{path}", json={"data": []})

    await mcp_client.call_tool("api_post_query", {"path": path, "body": {"pagination": {"limit": 1}}})

    posted = next(r for r in httpx_mock.get_requests() if r.url.path == path)
    assert json.loads(posted.read()) == {"pagination": {"limit": 1}}


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/jobs/job-1/start",
        "/api/v1/restore/vmRestore/vSphere",
        # Matches the `{hostname}` shape, but adds an unstructured data server.
        "/api/v1/inventory/unstructuredDataServers",
        "/api/v1/inventory/vc01.lab.local/rescan",
        "/api/v1/automation/credentials/export",
        "/api/v1/cloudBrowser",
    ],
)
async def test_api_post_query_refuses_endpoints_that_change_state(mcp_client: Client, path: str):
    with pytest.raises(ToolError, match="not an allowed read-only query endpoint"):
        await mcp_client.call_tool("api_post_query", {"path": path})


async def test_api_post_query_description_names_the_allowed_endpoints(mcp_client: Client):
    # The caller cannot see the code: the allowlist has to reach it through the tool description.
    tools = {tool.name: tool for tool in await mcp_client.list_tools()}
    description = tools["api_post_query"].description or ""

    for path in ("/api/v1/inventory/{hostname}", "/api/v1/acl", "/api/v1/restorePoints/{id}/networkInfo"):
        assert f"`{path}`" in description
    assert "_READ_ONLY_POST_PATHS" not in description
