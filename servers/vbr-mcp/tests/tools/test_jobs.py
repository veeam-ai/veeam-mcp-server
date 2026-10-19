# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

import json

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from pytest_httpx import HTTPXMock

from tests.conftest import tool_data

BASE = "https://localhost:9419"
JOB_ID = "00000000-0000-4000-8000-000000000007"


def _add_token_response(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{BASE}/api/oauth2/token", json={"access_token": "t", "refresh_token": "r"})


async def test_list_jobs_tags_schedule_kind(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/jobs?skip=0&limit=200",
        json={
            "data": [{"id": JOB_ID, "type": "VSphereBackup", "schedule": {"daily": {"isEnabled": True}}}],
            "pagination": {"total": 1},
        },
    )

    result = await mcp_client.call_tool("list_jobs", {})

    assert tool_data(result) == [
        {"id": JOB_ID, "type": "VSphereBackup", "schedule": {"daily": {"isEnabled": True}}, "scheduleKind": "daily"}
    ]


async def test_list_jobs_copy_job_gets_copy_schedule_kind(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/jobs?skip=0&limit=200",
        json={"data": [{"id": "j2", "type": "BackupCopy"}], "pagination": {"total": 1}},
    )

    result = await mcp_client.call_tool("list_jobs", {})

    assert tool_data(result)[0]["scheduleKind"] == "copy"


async def test_list_jobs_with_id_reads_one_job(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(url=f"{BASE}/api/v1/jobs/{JOB_ID}", json={"id": JOB_ID, "type": "VSphereBackup"})

    result = await mcp_client.call_tool("list_jobs", {"id": JOB_ID})

    assert result.data == {"id": JOB_ID, "type": "VSphereBackup", "scheduleKind": "none"}


async def test_get_job_states_filters_by_status(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(
        url=f"{BASE}/api/v1/jobs/states?statusFilter=Running&skip=0&limit=200",
        json={"data": [{"id": JOB_ID, "status": "Running"}], "pagination": {"total": 1}},
    )

    result = await mcp_client.call_tool("get_job_states", {"status_filter": "Running"})

    assert tool_data(result) == [{"id": JOB_ID, "status": "Running"}]


async def test_start_job_posts_the_start_spec(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(url=f"{BASE}/api/v1/jobs/{JOB_ID}/start", status_code=204)

    await mcp_client.call_tool("start_job", {"job_id": JOB_ID, "perform_active_full": True})

    posted = next(r for r in httpx_mock.get_requests() if r.url.path == f"/api/v1/jobs/{JOB_ID}/start")
    assert json.loads(posted.read()) == {"performActiveFull": True, "startChainedJobs": False}


async def test_start_job_passes_the_sync_choice_of_an_immediate_copy_job(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(url=f"{BASE}/api/v1/jobs/{JOB_ID}/start", status_code=204)

    await mcp_client.call_tool("start_job", {"job_id": JOB_ID, "sync_restore_points": "Latest"})

    posted = next(r for r in httpx_mock.get_requests() if r.url.path == f"/api/v1/jobs/{JOB_ID}/start")
    assert json.loads(posted.read()) == {
        "performActiveFull": False,
        "startChainedJobs": False,
        "syncRestorePoints": "Latest",
    }


async def test_start_job_rejects_a_sync_choice_outside_the_vbr_enum(mcp_client: Client):
    with pytest.raises(ToolError, match="sync_restore_points"):
        await mcp_client.call_tool("start_job", {"job_id": JOB_ID, "sync_restore_points": "Newest"})


async def test_stop_job_posts_graceful_stop(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(url=f"{BASE}/api/v1/jobs/{JOB_ID}/stop", status_code=204)

    await mcp_client.call_tool("stop_job", {"job_id": JOB_ID, "graceful_stop": False})

    posted = next(r for r in httpx_mock.get_requests() if r.url.path == f"/api/v1/jobs/{JOB_ID}/stop")
    assert json.loads(posted.read()) == {"gracefulStop": False}


async def test_enable_and_disable_job_hit_the_right_paths(mcp_client: Client, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(url=f"{BASE}/api/v1/jobs/{JOB_ID}/enable", status_code=204)
    httpx_mock.add_response(url=f"{BASE}/api/v1/jobs/{JOB_ID}/disable", status_code=204)

    await mcp_client.call_tool("enable_job", {"job_id": JOB_ID})
    await mcp_client.call_tool("disable_job", {"job_id": JOB_ID})

    paths = {r.url.path for r in httpx_mock.get_requests()}
    assert f"/api/v1/jobs/{JOB_ID}/enable" in paths
    assert f"/api/v1/jobs/{JOB_ID}/disable" in paths


async def test_get_job_states_rejects_a_status_outside_the_vbr_enum(mcp_client: Client):
    with pytest.raises(ToolError, match="status_filter"):
        await mcp_client.call_tool("get_job_states", {"status_filter": "running"})


async def test_start_job_rejects_a_job_name_passed_as_id(mcp_client: Client):
    with pytest.raises(ToolError, match="job_id"):
        await mcp_client.call_tool("start_job", {"job_id": "Nightly backup"})
