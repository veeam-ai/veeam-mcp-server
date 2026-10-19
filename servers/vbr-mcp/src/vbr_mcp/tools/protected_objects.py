# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from vbr_mcp.models.shared import MalwareStatus
from vbr_mcp.pagination import fetch_all
from vbr_mcp.server import mcp, vbr_client
from vbr_mcp.tool_annotations import READ_ONLY

# `EPlatformType`
PlatformName = Literal[
    "VMware",
    "HyperV",
    "CloudDirector",
    "WindowsPhysical",
    "LinuxPhysical",
    "Tape",
    "CustomPlatform",
    "EntraID",
    "UnstructuredData",
    "Test",
    "MongoDb",
    "Iris",
    "AWSEC2",
    "AzureCompute",
    "GCE",
    "Nutanix",
    "Proxmox",
    "LinuxPhysicalPpc",
]


@mcp.tool(annotations=READ_ONLY)
async def list_protected_objects(
    id: UUID | None = None,
    name_filter: str | None = None,
    platform_name_filter: PlatformName | None = None,
    max_items: int | None = None,
) -> list[dict[str, Any]]:
    """List protected objects, or - with `id` - that one object's restore-point history.

    A protected object is a workload that has at least one backup. Without `id`: the protected-object inventory
    (`GetAllBackupObjects`), deduplicated
    by `id` (this endpoint can repeat the same object across rows). With `id`: that
    object's restore points, newest first.

    This only lists objects that already have a backup - a workload discovered in the
    source inventory but never backed up does not appear here. Each row's `restorePointsCount`
    already gives the point count - use `list_restore_points` with `order_column`/
    `order_asc`/`max_items=1` instead of paging history to find the latest/oldest
    point or check staleness.
    """
    if id is not None:
        return await fetch_all(
            vbr_client,
            f"/api/v1/backupObjects/{id}/restorePoints",
            orderColumn="CreationTime",
            orderAsc=False,
            max_items=max_items,
        )
    rows = await fetch_all(
        vbr_client,
        "/api/v1/backupObjects",
        nameFilter=name_filter,
        platformNameFilter=platform_name_filter,
        max_items=max_items,
    )
    return list({row["id"]: row for row in rows if row.get("id")}.values())


@mcp.tool(annotations=READ_ONLY)
async def list_restore_points(
    backup_object_id_filter: UUID | None = None,
    backup_id_filter: UUID | None = None,
    name_filter: str | None = None,
    created_after_filter: datetime | None = None,
    created_before_filter: datetime | None = None,
    malware_status_filter: list[MalwareStatus] | None = None,
    order_column: Literal["CreationTime", "PlatformId", "BackupId"] | None = None,
    order_asc: bool | None = None,
    max_items: int | None = None,
) -> list[dict[str, Any]]:
    """List restore points across the whole estate (or scoped to one object/backup).

    Use `backup_object_id_filter` to scope to one protected object, or
    `created_after_filter`/`created_before_filter` (UTC when no offset is given) to window a large
    history instead of paging it in full. For "the latest/oldest point", pass
    `order_column="CreationTime"`, `order_asc` (`False` for latest), `max_items=1`
    instead of fetching everything and picking in Python. A `malware_status_filter`
    of `Informative` is not a positive detection. Nor is `Clean` proof a point is
    safe to restore: a point after a Suspicious/Infected one may read Clean only
    because the workload was marked clean (see `list_malware_events`). To pick a
    clean point, list the object's points with their `malwareStatus` and take the
    last one before its earliest Suspicious/Infected point.
    """
    return await fetch_all(
        vbr_client,
        "/api/v1/restorePoints",
        backupObjectIdFilter=backup_object_id_filter,
        backupIdFilter=backup_id_filter,
        nameFilter=name_filter,
        createdAfterFilter=created_after_filter,
        createdBeforeFilter=created_before_filter,
        malwareStatusFilter=malware_status_filter,
        orderColumn=order_column,
        orderAsc=order_asc,
        max_items=max_items,
    )


@mcp.tool(annotations=READ_ONLY)
async def get_restore_point_disks(restore_point_id: UUID) -> list[dict[str, Any]]:
    """List the disks captured by one restore point.

    `restore_point_id` comes from `list_protected_objects`/`list_restore_points`.
    """
    return await fetch_all(vbr_client, f"/api/v1/restorePoints/{restore_point_id}/disks")
