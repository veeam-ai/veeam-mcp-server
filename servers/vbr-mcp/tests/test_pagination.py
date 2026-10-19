# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

from pytest_httpx import HTTPXMock

from vbr_mcp.pagination import fetch_all, fetch_total
from vbr_mcp.vbr_client import VbrClient

TOKEN_URL = "https://vbr.example.com:9419/api/oauth2/token"
JOBS_URL = "https://vbr.example.com:9419/api/v1/jobs"


def _add_token_response(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=TOKEN_URL, json={"access_token": "token-1", "refresh_token": "refresh-1"})


async def test_fetch_all_returns_every_row_when_first_page_covers_the_total(
    vbr_client: VbrClient, httpx_mock: HTTPXMock
):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(
        url=f"{JOBS_URL}?skip=0&limit=200",
        json={"data": [{"id": "1"}, {"id": "2"}], "pagination": {"total": 2}},
    )

    result = await fetch_all(vbr_client, "/api/v1/jobs")

    assert result == [{"id": "1"}, {"id": "2"}]


async def test_fetch_all_pages_until_total_is_reached(vbr_client: VbrClient, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(
        url=f"{JOBS_URL}?skip=0&limit=2",
        json={"data": [{"id": "1"}, {"id": "2"}], "pagination": {"total": 3}},
    )
    httpx_mock.add_response(url=f"{JOBS_URL}?skip=2&limit=1", json={"data": [{"id": "3"}]})

    result = await fetch_all(vbr_client, "/api/v1/jobs", page_size=2)

    assert [row["id"] for row in result] == ["1", "2", "3"]


async def test_fetch_all_threads_filter_kwargs_onto_the_request(vbr_client: VbrClient, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(
        url=f"{JOBS_URL}?nameFilter=nightly&skip=0&limit=1",
        json={"data": [{"id": "1", "name": "nightly"}], "pagination": {"total": 1}},
    )

    result = await fetch_all(vbr_client, "/api/v1/jobs", nameFilter="nightly", max_items=1)

    assert result == [{"id": "1", "name": "nightly"}]


async def test_fetch_all_drops_none_valued_filters(vbr_client: VbrClient, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(
        url=f"{JOBS_URL}?skip=0&limit=200",
        json={"data": [{"id": "1"}], "pagination": {"total": 1}},
    )

    result = await fetch_all(vbr_client, "/api/v1/jobs", typeFilter=None)

    assert result == [{"id": "1"}]


async def test_fetch_total_returns_the_server_side_total(vbr_client: VbrClient, httpx_mock: HTTPXMock):
    _add_token_response(httpx_mock)
    httpx_mock.add_response(url=f"{JOBS_URL}?limit=1", json={"data": [{"id": "1"}], "pagination": {"total": 42}})

    result = await fetch_total(vbr_client, "/api/v1/jobs")

    assert result == 42
