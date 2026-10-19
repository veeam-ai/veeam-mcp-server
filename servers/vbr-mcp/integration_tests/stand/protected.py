# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""Protected objects and their restore points (1.8): ``/backupObjects``, ``/restorePoints`` and the points' disks.

Every point the stand's sessions made is here, at the time its job's task wrote it: web-02's point of 10-05 comes
from the retry at 23:00, report-01 has none for 10-04 (that run was canceled) and its 10-05 run waited for the
Daily-VMs retry. Malware status follows the events of 1.10: fs-01's 10-04 point is Suspicious (inline scan), its
10-06 point Infected (the Scan Backup); its 10-05 point is Clean because fs-01 was marked clean on 10-05 before it
was made (EV07) - which leaves the earlier points flagged. web-02's 10-04 point is Informative: the proactive
signature scan that its bulk-deletion event (EV08) triggered found nothing.
"""

from datetime import date, datetime, time, timedelta, timezone
from typing import NamedTuple
from uuid import UUID

from stand.ids import (
    B01,
    B02,
    B03,
    B05,
    B06,
    B07,
    B08,
    B09,
    B10,
    B11,
    GB,
    M02,
    SERVER_TZ,
    WINTER_TZ,
    ZERO,
    mnemonic,
)
from stand.inventory import NETWORKS, VMS
from vbr_mock.markers import VbrError
from vbr_models.malware import MalwareSeverity
from vbr_models.protected_objects import (
    AgentRestorePointDisk,
    BackupObject,
    PlatformName,
    RestorePoint,
    RestorePointDisk,
    RestorePointNetwork,
    ViBackupObject,
)

VMWARE_OPERATIONS = ["StartViVMInstantRecovery", "StartEntireVmRestore", "StartFlrRestore"]
AGENT_OPERATIONS = ["StartFlrRestore"]  # swagger ObjectRestorePointModelExample, an agent backup


class _Protected(NamedTuple):
    number: int
    name: str
    platform: PlatformName
    backup_id: UUID
    newest: date
    at: time
    count: int
    tz: timezone = SERVER_TZ


# (number, name, platform, backup, the newest point's date and time, points); the points are daily unless noted
_OBJECTS: list[_Protected] = [
    _Protected(1, "web-01", "VMware", B01, date(2026, 10, 6), time(22, 6, 12), 14),
    _Protected(2, "web-02", "VMware", B01, date(2026, 10, 6), time(22, 12, 40), 14),
    _Protected(3, "app-01", "VMware", B01, date(2026, 10, 6), time(22, 19, 3), 14),
    _Protected(4, "fs-01", "VMware", B01, date(2026, 10, 6), time(22, 0, 41), 14),
    _Protected(5, "sql-prod-01", "VMware", B02, date(2026, 10, 6), time(0, 14, 22), 30),  # T0-33h: 10-07 failed
    _Protected(6, "sql-prod-02", "VMware", B02, date(2026, 10, 7), time(0, 10, 5), 30),  # T0-9h
    _Protected(7, "sql-dev-01", "VMware", B03, date(2026, 10, 7), time(2, 15, 30), 7),  # T0-7h; a new run is going
    _Protected(8, "report-01", "VMware", B08, date(2026, 10, 6), time(22, 44, 10), 14),  # T0-10h
    _Protected(9, "legacy-erp-01", "VMware", B07, date(2026, 9, 12), time(3, 4, 15), 30),  # T0-25d: J07 is disabled
    _Protected(10, "laptop-hr-01", "WindowsPhysical", B06, date(2026, 10, 6), time(12, 3, 20), 10),  # T0-21h
    _Protected(11, "laptop-hr-02", "WindowsPhysical", B06, date(2026, 10, 6), time(12, 5, 2), 10),
    _Protected(12, "laptop-fin-01", "WindowsPhysical", B06, date(2026, 10, 1), time(12, 4, 47), 10),  # T0-6d, offline
    _Protected(13, "\\\\fs01\\finance", "UnstructuredData", B05, date(2026, 10, 6), time(21, 0, 50), 21),  # T0-12h
    _Protected(14, "lab-docs-prod", "UnstructuredData", B09, date(2026, 10, 6), time(21, 30, 40), 14),  # T0-11.5h
    _Protected(15, "old-fs-01", "VMware", B10, date(2025, 9, 2), time(22, 3, 18), 5),  # T0-400d, orphaned
    _Protected(16, "old-app-01", "VMware", B10, date(2025, 9, 2), time(22, 9, 51), 5),
    _Protected(17, "erp-db-2024", "VMware", B11, date(2025, 12, 11), time(1, 30, 2), 3, WINTER_TZ),  # imported
]

_RUN_EXCEPTIONS: dict[tuple[str, date], time | None] = {
    ("web-02", date(2026, 10, 5)): time(23, 0, 20),  # the first attempt failed; the retry S-ID15 made it
    ("report-01", date(2026, 10, 5)): time(23, 13, 45),  # chained after Daily-VMs, which retried until 23:09
    ("report-01", date(2026, 10, 4)): None,  # S-ID16 was canceled: no point that night
}

_SYNTHETIC_FULL_BACKUPS = {B01, B08}
"""The backups of Daily-VMs and Reports-VM, whose jobs make a synthetic full on Saturday (``weekday() == 5``)."""

MALWARE_STATUS: dict[tuple[str, date], MalwareSeverity] = {
    ("fs-01", date(2026, 10, 6)): "Infected",  # Scan Backup S-ID13: LockBit (EV02)
    ("fs-01", date(2026, 10, 4)): "Suspicious",  # inline scan: encrypted data (EV01)
    ("web-02", date(2026, 10, 4)): "Informative",  # signature scan after EV08 found nothing (EV03)
}
"""Points whose malware status is not Clean, by (object, date of the night)."""


def _object(spec: _Protected) -> BackupObject:
    if spec.platform == "VMware":
        return ViBackupObject(
            id=mnemonic("50000000", spec.number),
            name=spec.name,
            type="VM",
            restore_points_count=spec.count,
            last_run_failed=spec.name == "sql-prod-01",
            backup_id=spec.backup_id,
            object_id=VMS[spec.name].ref,
            vi_type="VirtualMachine",
        )
    kind = (
        "Computer"
        if spec.platform == "WindowsPhysical"
        else "FileShare"
        if spec.name.startswith("\\")
        else "ObjectStorage"
    )
    return BackupObject(
        id=mnemonic("50000000", spec.number),
        name=spec.name,
        type=kind,
        platform_name=spec.platform,
        restore_points_count=spec.count,
        last_run_failed=False,
        backup_id=spec.backup_id,
    )


OBJECTS: list[BackupObject] = [_object(spec) for spec in _OBJECTS]
"""Every protected object once, O01-O17."""

BY_NAME: dict[str, BackupObject] = {obj.name: obj for obj in OBJECTS}

BACKUP_OBJECTS: list[BackupObject] = [*OBJECTS[:4], BY_NAME["fs-01"], *OBJECTS[4:]]
"""``GET /api/v1/backupObjects``: the endpoint repeats fs-01, the same row twice, as the stand has it (1.8)."""


def point_key(obj: BackupObject) -> int:
    """The number a restore point id carries for ``obj``: the VM's reference number, or the object's own number."""
    if isinstance(obj, ViBackupObject):
        return int(obj.object_id.removeprefix("vm-"))
    return int(str(obj.id)[-4:])


def point_id(obj: BackupObject, index: int) -> UUID:
    """The id of ``obj``'s restore point ``index`` points back from its newest (0 = the newest)."""
    return UUID(f"51000000-0000-0000-{point_key(obj):04d}-{index:012d}")


def _nights(spec: _Protected) -> list[datetime]:
    """When each of the object's points was made, newest first."""
    moments, night = [], spec.newest
    while len(moments) < spec.count:
        at = _RUN_EXCEPTIONS.get((spec.name, night), spec.at)
        if at is not None:
            moments.append(datetime.combine(night, at, tzinfo=spec.tz))
        night -= timedelta(days=1)
    return moments


def _points(spec: _Protected) -> list[RestorePoint]:
    obj = BY_NAME[spec.name]
    moments = _nights(spec)
    points = []
    for index, created in enumerate(moments):
        synthetic_full = spec.backup_id in _SYNTHETIC_FULL_BACKUPS and created.weekday() == 5
        operations = (
            VMWARE_OPERATIONS
            if spec.platform == "VMware"
            else AGENT_OPERATIONS
            if spec.platform == "WindowsPhysical"
            else []
        )
        points.append(
            RestorePoint(
                id=point_id(obj, index),
                name=spec.name,
                platform_name=spec.platform,
                platform_id=ZERO,
                creation_time=created,
                backup_id=spec.backup_id,
                type="Full" if index == len(moments) - 1 or synthetic_full else "Increment",
                allowed_operations=operations,
                malware_status=MALWARE_STATUS.get((spec.name, created.date()), "Clean"),
                backup_object_id=obj.id,  # mock-only: how VBR answers backupObjectIdFilter
            )
        )
    return points


POINTS: dict[str, list[RestorePoint]] = {spec.name: _points(spec) for spec in _OBJECTS}
"""Each object's restore points, newest first."""

RESTORE_POINTS: list[RestorePoint] = sorted(
    (point for points in POINTS.values() for point in points), key=lambda point: point.creation_time, reverse=True
)
"""``GET /api/v1/restorePoints``: every object's points in one list, newest first; only a filter scopes it."""
POINT_IDS = {str(point.id) for point in RESTORE_POINTS}
"""Every restore point id VBR has, as a request body carries it: VBR answers any other with a 404."""


def points_of(name: str) -> list[RestorePoint]:
    """The object's restore points, newest first."""
    return POINTS[name]


def vm_uuid(obj: BackupObject) -> str:
    """The VM's own UUID, as its malware events and the ids of its disks carry it."""
    return f"50{point_key(obj):04d}c2-7d3e-4f5a-9b6c-0e1f2a3b4c5d"


def point_on(name: str, night: date) -> RestorePoint:
    """The object's restore point made on the night of ``night`` (its date on the server's clock)."""
    return next(point for point in POINTS[name] if point.creation_time.date() == night)


# ---- Disks of the points: a VM's VMDKs named as VBR reports them (swagger ObjectRestorePointDisksResultExample), a
# laptop's disks as its Windows agent backed them up

DISK_LAYOUT: dict[str, list[int]] = {
    "web-01": [60],
    "web-02": [60],
    "app-01": [80, 120],
    "fs-01": [60, 1024],
    "sql-prod-01": [80, 300],
    "sql-prod-02": [80, 500],  # the 500 GB disk holds the SQL data
    "sql-dev-01": [80, 135],
    "report-01": [60, 190],
    "legacy-erp-01": [80, 200],
    "old-fs-01": [60, 500],
    "old-app-01": [80],
    "erp-db-2024": [80, 400],
}
"""Each VM's disks, GB; named ``<vm>``, ``<vm>_1``, ... as their VMDKs are."""


def disk_name(vm: str, n: int) -> str:
    return vm if n == 0 else f"{vm}_{n}"


Disk = RestorePointDisk | AgentRestorePointDisk
"""A disk of a VM point or of an agent point."""


def _disks(point: RestorePoint) -> list[Disk]:
    instance = vm_uuid(BY_NAME[point.name])
    return [
        RestorePointDisk(uid=f"{M02}:{instance}:{2000 + n}:{point.id}", name=disk_name(point.name, n), capacity=gb * GB)
        for n, gb in enumerate(DISK_LAYOUT[point.name])
    ]


AGENT_DISK_LAYOUT: dict[str, list[int]] = {"laptop-hr-01": [512], "laptop-hr-02": [512], "laptop-fin-01": [512]}
"""Each laptop's disks, GB: the entire computer is backed up (Agent-Laptops' backup mode)."""


def _agent_disks(point: RestorePoint) -> list[Disk]:
    return [
        AgentRestorePointDisk(uid=f"{point.id}:{n}", name=f"Disk {n}", capacity=gb * GB)
        for n, gb in enumerate(AGENT_DISK_LAYOUT[point.name])
    ]


DISKS: dict[UUID, list[Disk]] = {
    point.id: _disks(point) if point.platform_name == "VMware" else _agent_disks(point)
    for point in RESTORE_POINTS
    if point.platform_name in ("VMware", "WindowsPhysical")
}
"""``GET /api/v1/restorePoints/{id}/disks`` for every VM and agent point. VBR answers it for a NAS point with an error
instead (``NAS_DISKS``)."""

NAS_DISKS = VbrError(status_code=400, message="Getting disks is not supported for Nas Backups.")
"""What VBR answers ``GET /api/v1/restorePoints/{id}/disks`` with for a file share or object storage point
(ObjectRestorePointsControllerImpl.GetObjectRestorePointDisks)."""


# ---- Networks of the points: what a VM was connected to, as a restore elsewhere maps it to a target network

VM_NETWORK = next(network for network in NETWORKS if network.name == "Prod-VLAN10")
"""The network every VM of the stand was connected to when it was backed up."""

NETWORK_INFO: dict[UUID, list[RestorePointNetwork]] = {
    point.id: [RestorePointNetwork(id="192", name=VM_NETWORK.name)]
    for point in RESTORE_POINTS
    if point.platform_name == "VMware"
}
"""``POST /api/v1/restorePoints/{id}/networkInfo`` for every VM point: the networks to map in a restore elsewhere."""
