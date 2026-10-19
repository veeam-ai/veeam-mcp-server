# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""The single pagination seam every list tool rides."""

from __future__ import annotations

import asyncio

from vbr_mcp.vbr_client import VbrClient

DEFAULT_PAGE_SIZE = 200
MAX_CONCURRENT_PAGE_REQUESTS = 8


def _extend_unique(data: list, seen_ids: set, rows: list, target: int) -> None:
    """Append ``rows`` to ``data`` up to ``target``, skipping ids already received.

    Rows without a usable ``id`` are always kept - dropping them could lose distinct
    data.
    """
    for row in rows:
        if len(data) >= target:
            return
        key = row.get("id") if isinstance(row, dict) else None
        if isinstance(key, (str, int)):
            if key in seen_ids:
                continue
            seen_ids.add(key)
        data.append(row)


def _plan_wave(offset: int, remaining: int, page_size: int) -> list[tuple[int, int]]:
    plan: list[tuple[int, int]] = []
    while remaining > 0:
        limit = min(page_size, remaining)
        plan.append((offset, limit))
        offset += limit
        remaining -= limit
    return plan


async def fetch_all(
    client: VbrClient,
    path: str,
    *,
    page_size: int = DEFAULT_PAGE_SIZE,
    skip: int = 0,
    max_items: int | None = None,
    **filters: object,
) -> list[dict]:
    """Fetch ``data`` rows of a VBR list endpoint from ``skip``, capped at ``max_items``.

    Filter kwargs are threaded onto every page request (``None`` dropped, lists as
    repeated params); a ``limit`` kwarg is an alias for ``max_items``. Rows already
    received are never returned twice (keyed by ``id``).
    """
    base = {k: v for k, v in filters.items() if v is not None}
    legacy_limit = base.pop("limit", None)
    if max_items is None and legacy_limit is not None:
        max_items = int(legacy_limit)  # ty: ignore[invalid-argument-type]

    def _params(offset: int, limit: int) -> dict[str, object]:
        return {**base, "skip": offset, "limit": limit}

    first_limit = page_size if max_items is None else min(page_size, max_items)
    first = await client.get(path, params=_params(skip, first_limit))
    if isinstance(first, list):
        return first

    data = list(first.get("data", []))
    total = first.get("pagination", {}).get("total")
    available = max(total - skip, 0) if isinstance(total, int) else len(data)
    target = available if max_items is None else min(max_items, available)

    seen_ids = {row["id"] for row in data if isinstance(row, dict) and isinstance(row.get("id"), (str, int))}

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_PAGE_REQUESTS)

    async def _fetch_page(offset: int, limit: int) -> list:
        async with semaphore:
            response = await client.get(path, params=_params(offset, limit))
        return response.get("data", []) if isinstance(response, dict) else response

    while len(data) < target:
        fetched_count = len(data)
        plan = _plan_wave(skip + len(data), target - len(data), page_size)

        pages = await asyncio.gather(*(_fetch_page(o, lim) for o, lim in plan))
        for (_, limit), page_data in zip(plan, pages, strict=True):
            if not page_data:
                return data
            _extend_unique(data, seen_ids, page_data, target)
            if len(page_data) != limit:
                # The server did not honor the requested limit, so the offsets
                # planned after this page are stale; replan the wave from the
                # rows actually received.
                break
        if len(data) == fetched_count:
            return data

    return data[:target]


async def fetch_total(client: VbrClient, path: str, **filters: object) -> int:
    """Return the full matching count of a VBR list endpoint via one ``limit=1`` request."""
    base = {k: v for k, v in filters.items() if v is not None}
    response = await client.get(path, params={**base, "limit": 1})
    if isinstance(response, list):
        return len(response)
    total = response.get("pagination", {}).get("total")
    return total if isinstance(total, int) else len(response.get("data", []))
