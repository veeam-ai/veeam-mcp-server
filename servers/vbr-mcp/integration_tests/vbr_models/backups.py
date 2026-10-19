# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""``/api/v1/backups``, ``/api/v1/backups/{id}/objects``, ``/api/v1/backups/{id}/backupFiles``."""

from typing import Literal
from uuid import UUID

from vbr_models import VbrDateTime, VbrModel
from vbr_models.jobs import JobType
from vbr_models.malware import MalwareSeverity
from vbr_models.protected_objects import PlatformName


class Backup(VbrModel):
    """``BackupModel``, an item of ``GET /api/v1/backups``: one backup chain on disk."""

    id: UUID
    job_id: UUID | None = None
    """All zeros when no job on this server owns the backup."""
    policy_unique_id: str | None = None
    name: str
    platform_name: PlatformName
    platform_id: UUID
    creation_time: VbrDateTime
    repository_id: UUID
    repository_name: str | None = None
    job_type: JobType


class BackupFile(VbrModel):
    """``BackupFileModel``, an item of ``GET /api/v1/backups/{id}/backupFiles``."""

    id: UUID
    name: str
    backup_id: UUID
    object_ids: list[UUID]
    restore_point_ids: list[UUID] | None = None
    data_size: int
    """Logical size, bytes."""
    backup_size: int
    """Size on disk, bytes."""
    dedup_ratio: int
    compress_ratio: int
    creation_time: VbrDateTime
    gfs_periods: list[Literal["None", "Weekly", "Monthly", "Quarterly", "Yearly"]] | None = None
    severity: MalwareSeverity | None = None
