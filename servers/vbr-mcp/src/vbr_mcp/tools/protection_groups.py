# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

from typing import Any, Literal
from uuid import UUID

from vbr_mcp.pagination import fetch_all
from vbr_mcp.server import mcp, vbr_client
from vbr_mcp.tool_annotations import READ_ONLY


@mcp.tool(annotations=READ_ONLY)
async def list_protection_groups(name_filter: str | None = None, max_items: int | None = None) -> list[dict[str, Any]]:
    """List agent protection groups: the policies that discover and manage Veeam Agent installs across computers.

    For per-group coverage/health, use `get_protection_group_entities`.
    """
    return await fetch_all(vbr_client, "/api/v1/agents/protectionGroups", nameFilter=name_filter, max_items=max_items)


@mcp.tool(annotations=READ_ONLY)
async def get_protection_group_entities(
    protection_group_id: UUID,
    agent_status_filter: Literal[
        "Installed",
        "NotInstalled",
        "UpgradeRequired",
        "Failed",
        "UnsupportedOperatingSystem",
        "Unknown",
        "NotInitialized",
    ]
    | None = None,
    driver_status_filter: Literal[
        "Unknown",
        "Installed",
        "NotInstalled",
        "Stopped",
        "Failed",
        "UpgradeAvailable",
        "InstalledRebootRequired",
        "NotInstalledRebootRequired",
    ]
    | None = None,
    max_items: int | None = None,
) -> list[dict[str, Any]]:
    """List the computers/containers one protection group discovered, with their agent/driver install state.

    Administrator-only endpoint. Compute coverage over `type == "Computer"`
    rows only (`Cluster`/`ActiveDirectory` are containers, not install
    targets): covered = `agentStatus == "Installed"` over total computers.
    `agentStatus`/`driverStatus` of `"UpgradeRequired"`/`"UpgradeAvailable"` is
    version drift, not a missing install. A computer's `lastConnected` older
    than 24h (against the server clock) is a stale agent connection. Use
    `agent_status_filter`/`driver_status_filter` to narrow server-side instead
    of fetching every entity.
    """
    return await fetch_all(
        vbr_client,
        f"/api/v1/agents/protectionGroups/{protection_group_id}/discoveredEntities",
        agentStatusFilter=agent_status_filter,
        driverStatusFilter=driver_status_filter,
        max_items=max_items,
    )
