# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

import json

from fastmcp import Client
from pytest_httpx import HTTPXMock

from tests.conftest import tool_data

BASE = "https://localhost:9419"
PROXY_ID = "00000000-0000-4000-8000-000000000002"
REPOSITORY_ID = "00000000-0000-4000-8000-000000000003"
REPOSITORY_ID_2 = "00000000-0000-4000-8000-000000000004"
SOBR_ID = "00000000-0000-4000-8000-000000000005"


def _add_token_response(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE}/api/oauth2/token", json={"access_token": "t", "refresh_token": "r"})


async def test_list_proxies_joins_inventory_and_state(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/backupInfrastructure/proxies?skip=0&limit=200",
        json={"data": [{"id": PROXY_ID, "name": "Proxy1", "type": "ViProxy"}], "pagination": {"total": 1}},
    )
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/backupInfrastructure/proxies/states?skip=0&limit=200",
        json={"data": [{"id": PROXY_ID, "isOnline": True, "isDisabled": False}], "pagination": {"total": 1}},
    )

    result = await mcp_client.call_tool("list_proxies", {})

    assert tool_data(result) == [
        {"id": PROXY_ID, "name": "Proxy1", "type": "ViProxy", "isOnline": True, "isDisabled": False}
    ]


async def test_set_proxy_enabled_true_calls_enable(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(url=f"{BASE}/api/v1/backupInfrastructure/proxies/{PROXY_ID}/enable", status_code=204)

    await mcp_client.call_tool("set_proxy_enabled", {"proxy_id": PROXY_ID, "enabled": True})

    posted = next(r for r in httpx_mock.get_requests() if f"proxies/{PROXY_ID}" in r.url.path)
    assert posted.url.path == f"/api/v1/backupInfrastructure/proxies/{PROXY_ID}/enable"


async def test_list_repositories_computes_reconciliation(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/backupInfrastructure/repositories?skip=0&limit=200",
        json={"data": [{"id": REPOSITORY_ID, "name": "Repo1", "type": "LinuxLocal"}], "pagination": {"total": 1}},
    )
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/backupInfrastructure/repositories/states?skip=0&limit=200",
        json={
            "data": [{"id": REPOSITORY_ID, "capacityGB": 1000.0, "freeGB": 100.0, "usedSpaceGB": 850.0}],
            "pagination": {"total": 1},
        },
    )

    result = await mcp_client.call_tool("list_repositories", {})

    row = tool_data(result)[0]
    assert row["freePercent"] == 10.0
    assert row["usedSpaceGBDerived"] == 900.0
    assert row["unidentifiedDataGB"] == 50.0
    assert row["phantomDataGB"] == 0.0


async def test_list_repositories_leaves_unreported_object_storage_capacity_unknown(
    mcp_client: Client, httpx_mock: HTTPXMock
):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/backupInfrastructure/repositories?skip=0&limit=200",
        json={"data": [{"id": REPOSITORY_ID, "name": "S3", "type": "AmazonS3"}], "pagination": {"total": 1}},
    )
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/backupInfrastructure/repositories/states?skip=0&limit=200",
        json={
            "data": [{"id": REPOSITORY_ID, "capacityGB": -1.0, "freeGB": -1.0, "usedSpaceGB": 5400.0}],
            "pagination": {"total": 1},
        },
    )

    result = await mcp_client.call_tool("list_repositories", {})

    row = tool_data(result)[0]
    assert row["freePercent"] is None
    assert row["usedSpaceGBDerived"] == 5400.0
    assert row["unidentifiedDataGB"] is None


async def test_rescan_repositories_posts_the_ids(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(url=f"{BASE}/api/v1/backupInfrastructure/repositories/rescan", status_code=204)

    await mcp_client.call_tool("rescan_repositories", {"repository_ids": [REPOSITORY_ID, REPOSITORY_ID_2]})

    posted = next(r for r in httpx_mock.get_requests() if r.url.path.endswith("/repositories/rescan"))
    assert json.loads(posted.read()) == {"repositoryIds": [REPOSITORY_ID, REPOSITORY_ID_2]}


async def test_set_sobr_extent_maintenance_mode_posts_extent_ids(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/backupInfrastructure/scaleOutRepositories/{SOBR_ID}/enableMaintenanceMode",
        status_code=204,
    )

    await mcp_client.call_tool(
        "set_sobr_extent_maintenance_mode",
        {"sobr_id": SOBR_ID, "extent_repository_ids": [REPOSITORY_ID], "enabled": True},
    )

    posted = next(r for r in httpx_mock.get_requests() if "enableMaintenanceMode" in r.url.path)
    assert json.loads(posted.read()) == {"repositoryIds": [REPOSITORY_ID]}
