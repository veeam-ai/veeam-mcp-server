# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.


from fastmcp import Client
from pytest_httpx import HTTPXMock

from tests.conftest import tool_data

BASE = "https://localhost:9419"
INSTANCE_ID = "00000000-0000-4000-8000-000000000099"


def _add_token_response(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE}/api/oauth2/token", json={"access_token": "t", "refresh_token": "r"})


async def test_get_license_status_merges_the_four_endpoints(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(url=f"{BASE}/api/v1/serverTime", json={"serverTime": "2026-09-21T00:00:00.0000000Z"})
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/license", json={"status": "Valid", "expirationDate": "2026-11-20T00:00:00.0000000Z"}
    )
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/license/sockets?skip=0&limit=200",
        json={"data": [{"id": "host-1"}], "pagination": {"total": 1}},
    )
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/license/instances?skip=0&limit=200",
        json={"data": [], "pagination": {"total": 0}},
    )
    httpx_mock.add_response(url=f"{BASE}/api/v1/license/capacity", json={"workloads": []})

    result = await mcp_client.call_tool("get_license_status", {})

    assert result.data == {
        "status": "Valid",
        "expirationDate": "2026-11-20T00:00:00.0000000Z",
        "socketWorkloads": [{"id": "host-1"}],
        "instanceWorkloads": [],
        "capacityWorkloads": [],
        "daysToExpiry": 60,
        "daysToSupportExpiry": None,
    }


async def test_create_license_report_flattens_products(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    report = {
        "products": [
            {
                "productVersion": "13.1.0.379",
                "edition": "Enterprise Plus",
                "package": "Advanced",
                "installationId": "inst-1",
                "data": [
                    {
                        "instances": {
                            "supportId": "sup-1",
                            "licenseId": "lic-1",
                            "licenseType": "Subscription",
                            "counters": [{"counterType": "VBR-VBR-VM", "numberOfObjects": 2}],
                        }
                    }
                ],
            }
        ]
    }
    httpx_mock.add_response(url=f"{BASE}/api/v1/license/createReport", json=report)

    result = await mcp_client.call_tool("create_license_report", {})

    assert tool_data(result) == [
        {
            "productVersion": "13.1.0.379",
            "edition": "Enterprise Plus",
            "package": "Advanced",
            "installationId": "inst-1",
            "counters": [
                {
                    "supportId": "sup-1",
                    "licenseId": "lic-1",
                    "licenseType": "Subscription",
                    "counterType": "VBR-VBR-VM",
                    "numberOfObjects": 2,
                }
            ],
        }
    ]


async def test_revoke_license_dispatches_to_the_matching_path(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(url=f"{BASE}/api/v1/license/instances/{INSTANCE_ID}/revoke", status_code=204)

    await mcp_client.call_tool("revoke_license", {"license_type": "instance", "id": INSTANCE_ID})

    posted = next(r for r in httpx_mock.get_requests() if "revoke" in r.url.path)
    assert posted.url.path == f"/api/v1/license/instances/{INSTANCE_ID}/revoke"
    assert posted.method == "POST"
