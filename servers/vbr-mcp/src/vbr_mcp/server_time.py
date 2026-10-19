# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""The VBR server clock, the reference clock for staleness and expiry math."""

from __future__ import annotations

from datetime import UTC, datetime

from vbr_mcp.datetimes import parse_vbr_datetime
from vbr_mcp.vbr_client import VbrClient


async def get_server_time(client: VbrClient) -> datetime:
    """Return the VBR server's current time as a timezone-aware datetime.

    Reads ``/api/v1/serverTime``; on any failure (endpoint error, missing or
    unparseable field) falls back to ``datetime.now(UTC)``.
    """
    try:
        response = await client.get("/api/v1/serverTime")
        raw = response.get("serverTime") if isinstance(response, dict) else None
        if raw:
            return parse_vbr_datetime(raw)
    except Exception:
        pass
    return datetime.now(UTC)
