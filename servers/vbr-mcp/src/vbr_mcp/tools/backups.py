# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from vbr_mcp.pagination import fetch_all, fetch_total
from vbr_mcp.server import mcp, vbr_client
from vbr_mcp.tool_annotations import READ_ONLY


@mcp.tool(annotations=READ_ONLY)
async def list_backups(
    name_filter: str | None = None,
    job_id_filter: UUID | None = None,
    created_after_filter: datetime | None = None,
    created_before_filter: datetime | None = None,
    max_items: int | None = None,
) -> list[dict[str, Any]]:
    """List backups (the on-disk backup chains, not individual restore points).

    `jobId` (or `policyUniqueId` for agent/policy backups) links a backup to its
    owning job - a null/all-zeros `jobId` means no owning job on this server
    (orphaned, or imported/exported, or a detached chain of a current job; check
    `policyUniqueId` against `list_jobs` ids to tell which). `repositoryId`/
    `repositoryName` is the join key into `list_repositories` for storage-by-
    repository totals. Timestamps without an offset are treated as UTC.
    """
    return await fetch_all(
        vbr_client,
        "/api/v1/backups",
        nameFilter=name_filter,
        jobIdFilter=job_id_filter,
        createdAfterFilter=created_after_filter,
        createdBeforeFilter=created_before_filter,
        max_items=max_items,
    )


@mcp.tool(annotations=READ_ONLY)
async def get_backup_details(
    backup_id: UUID,
    include: list[Literal["objects", "files"]] | None = None,
    max_files: int = 50,
) -> dict[str, Any]:
    """Return one backup's protected objects and/or backup-file storage footprint.

    `include` selects what to fetch (default both): `"objects"` - the protected
    objects contained in the backup; `"files"` - the on-disk files, newest/largest
    first, capped at `max_files` (one backup can hold tens of thousands of files;
    `filesTotal` gives the true count without paging all of them). File
    `dataSize` is logical (pre-dedup/compression) size, `backupSize` is on-disk
    size - both in bytes.
    """
    parts = include or ["objects", "files"]
    result: dict[str, Any] = {"backupId": str(backup_id)}
    if "objects" in parts:
        result["objects"] = await fetch_all(vbr_client, f"/api/v1/backups/{backup_id}/objects")
    if "files" in parts:
        files = await fetch_all(
            vbr_client,
            f"/api/v1/backups/{backup_id}/backupFiles",
            orderColumn="CreationTime",
            orderAsc=False,
            max_items=max_files,
        )
        result["files"] = files
        result["filesTotal"] = (
            len(files)
            if len(files) < max_files
            else await fetch_total(vbr_client, f"/api/v1/backups/{backup_id}/backupFiles")
        )
    return result
