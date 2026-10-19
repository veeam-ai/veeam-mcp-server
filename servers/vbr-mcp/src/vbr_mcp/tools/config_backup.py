# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

from typing import Any

from vbr_mcp.server import mcp, vbr_client
from vbr_mcp.tool_annotations import READ_ONLY, WRITE


@mcp.tool(annotations=READ_ONLY)
async def get_config_backup_status() -> dict[str, Any]:
    """Return the VBR configuration-backup posture: enabled, schedule, retention, encryption, target repository.

    `lastSuccessfulBackup.lastSuccessfulTime` is when it last **succeeded** - it
    says nothing about whether the most recent run failed; for the current
    verdict check the newest `ConfigurationBackup`-type session via `list_sessions`.
    No session newer than the schedule implies means it is not running at all:
    once the Password Manager holds a password (job encryption creates one), VBR
    does not start a configuration backup whose encryption is off. Without such
    passwords an unencrypted run finishes with a Warning ("Skipping credentials
    backup because the encryption is disabled"). An unencrypted config backup
    stores no credentials/keys - after a DR restore from it, encrypted workload
    backups become unrecoverable and every credential must be re-entered by hand.
    It cannot target a scale-out repository.
    """
    return await vbr_client.get("/api/v1/configBackup")


@mcp.tool(annotations=WRITE)
async def start_config_backup() -> dict[str, Any] | None:
    """Start a VBR configuration backup now, using its configured settings."""
    return await vbr_client.post("/api/v1/configBackup/backup")
