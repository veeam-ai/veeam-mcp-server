# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""``/api/v1/backupObjects``, ``/api/v1/restorePoints``, ``/api/v1/restorePoints/{id}/disks``."""

from typing import Annotated, Literal
from uuid import UUID

from vbr_mock.markers import MOCK_ONLY
from vbr_models import VbrDateTime, VbrModel
from vbr_models.malware import MalwareSeverity

PlatformName = Literal["VMware", "HyperV", "WindowsPhysical", "LinuxPhysical", "UnstructuredData"]
"""The ``EPlatformType`` values the cases use."""


class BackupObject(VbrModel):
    """``BackupObjectModel``, an item of ``GET /api/v1/backupObjects``: a workload that has a backup."""

    id: UUID
    name: str
    type: str
    platform_name: PlatformName
    platform_id: UUID | None = None
    restore_points_count: int | None = None
    last_run_failed: bool | None = None
    backup_id: UUID | None = None


class ViBackupObject(BackupObject):
    """``ViBackupObjectModel``: the ``VMware`` subtype of ``BackupObjectModel``."""

    platform_name: Literal["VMware"] = "VMware"
    object_id: str
    vi_type: Literal["VirtualMachine"] | None = None
    path: str | None = None


class RestorePoint(VbrModel):
    """``ObjectRestorePointModel``, an item of ``GET /api/v1/restorePoints`` and ``/backupObjects/{id}/restorePoints``."""

    id: UUID
    name: str
    platform_name: PlatformName
    platform_id: UUID
    creation_time: VbrDateTime
    backup_id: UUID
    type: Literal["Increment", "Full", "Rollback", "Snapshot", "Cdp", "Different"] | None = None
    session_id: UUID | None = None
    allowed_operations: list[str]
    malware_status: MalwareSeverity | None = None
    backup_object_id: Annotated[UUID | None, MOCK_ONLY] = None
    """The protected object the point belongs to. Not part of VBR's JSON: VBR answers ``backupObjectIdFilter``
    through a join in its database, and the mock filters by this field and strips it."""


class RestorePointDisk(VbrModel):
    """``VmwareObjectRestorePointDiskModel``, an item of ``GET /api/v1/restorePoints/{id}/disks``."""

    platform: Literal["VMware"] = "VMware"
    uid: str
    type: Literal["Vi"] = "Vi"  # ``EDiskInfoType``
    name: str
    capacity: int
    """Bytes."""
    state: Literal["NotProcessed", "InProcessing", "PartiallyProcessed", "Processed"] = "Processed"


class RestorePointNetwork(VbrModel):
    """``ObjectRestorePointNetworkInfoModel``, an item of ``POST /api/v1/restorePoints/{id}/networkInfo``.

    A network the VM was connected to when it was backed up. ``id`` is VBR's own id of the network in the backup ("192"
    for a VM Network on a VBR 13.1 lab), not the network's inventory ``objectId``.
    """

    id: str
    name: str


class AgentRestorePointDisk(VbrModel):
    """``WindowsPhysicalObjectRestorePointDiskModel``: a disk of a Windows agent backup's restore point."""

    platform: Literal["WindowsPhysical"] = "WindowsPhysical"
    uid: str
    type: Literal["EndPoint"] = "EndPoint"  # ``EDiskInfoType``
    name: str
    capacity: int
    """Bytes."""
    state: Literal["NotProcessed", "InProcessing", "PartiallyProcessed", "Processed"] = "Processed"
