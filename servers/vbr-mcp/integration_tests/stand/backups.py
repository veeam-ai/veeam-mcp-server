# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""Backups (1.9): the chains on disk, what each holds and its files.

``/backups``, ``/backups/{id}/objects`` and ``/backups/{id}/backupFiles``. B10 is orphaned (no owning job, no policy id), B11 imported (a ``policyUniqueId`` no job has). Daily-VMs' 58 files and
the sizes of B10, B11 and B07 are the plan's (G2-09, G3-30 count on them); every other backup gets one file per restore
point. Sizes are bytes: ``dataSize`` logical, ``backupSize`` on disk. The copies in B04 have no restore points of their
own in ``/restorePoints``: the stand does not model the copy's points, only its files, written when Copy-to-DR's copy
task of that night ended. Only Daily-VMs keeps weekly GFS fulls, so only its fulls are flagged ``Weekly``.
"""

from datetime import datetime, timedelta
from uuid import UUID

from stand import repositories, sessions
from stand.agents import LAPTOPS
from stand.ids import (
    B01,
    B02,
    B03,
    B04,
    B05,
    B06,
    B07,
    B08,
    B09,
    B10,
    B11,
    GB,
    J01,
    J02,
    J03,
    J04,
    J05,
    J06,
    J07,
    J08,
    J10,
    R01,
    R02,
    R03,
    R04,
    S01,
    SERVER_TZ,
    WINTER_TZ,
    ZERO,
)
from stand.jobs import DAILY_VMS, JOBS
from stand.protected import BY_NAME, POINTS, point_key
from vbr_models.backups import Backup, BackupFile
from vbr_models.jobs import BackupJob, JobType
from vbr_models.protected_objects import BackupObject, PlatformName, RestorePoint
from vbr_models.sessions import BackupTaskSession


def backup(
    id: UUID,
    name: str,
    job_id: UUID,
    repository_id: UUID,
    job_type: JobType,
    platform_name: PlatformName,
    created: datetime,
    *,
    policy_unique_id: str | None = None,
) -> Backup:
    """A backup chain; ``policyUniqueId`` is the owning job's id unless given."""
    return Backup(
        id=id,
        job_id=job_id,
        policy_unique_id=str(job_id) if policy_unique_id is None else policy_unique_id,
        name=name,
        platform_name=platform_name,
        platform_id=ZERO,
        creation_time=created,
        repository_id=repository_id,
        repository_name=repositories.NAMES[repository_id],
        job_type=job_type,
    )


_CREATED = datetime(2026, 3, 2, 22, 0, 31, tzinfo=WINTER_TZ)

BACKUPS: list[Backup] = [
    backup(B01, "Daily-VMs", J01, R01, "VSphereBackup", "VMware", _CREATED),
    backup(B02, "SQL-Prod", J02, S01, "VSphereBackup", "VMware", _CREATED),
    backup(B03, "SQL-Dev", J03, R01, "VSphereBackup", "VMware", _CREATED),
    backup(B04, "Copy-to-DR", J04, R04, "BackupCopy", "VMware", _CREATED),
    backup(B05, "NAS-Finance", J05, R02, "FileBackup", "UnstructuredData", _CREATED),
    backup(B06, "Agent-Laptops", J06, R02, "WindowsAgentBackupWorkstationPolicy", "WindowsPhysical", _CREATED),
    backup(B07, "Legacy-Archive", J07, R03, "VSphereBackup", "VMware", datetime(2025, 6, 1, 3, 0, 9, tzinfo=SERVER_TZ)),
    backup(B08, "Reports-VM", J08, R02, "VSphereBackup", "VMware", _CREATED),
    backup(B09, "S3-Docs", J10, R02, "ObjectStorageBackup", "UnstructuredData", _CREATED),
    backup(B10, "FileApp-Weekly", ZERO, R01, "VSphereBackup", "VMware",
           datetime(2025, 8, 29, 22, 1, 7, tzinfo=SERVER_TZ), policy_unique_id=""),
    backup(B11, "ERP-Nightly", ZERO, R03, "VSphereBackup", "VMware",
           datetime(2025, 12, 9, 1, 12, 44, tzinfo=WINTER_TZ), policy_unique_id="9f1c2d3e-0000-4000-8000-00000000abcd"),
]  # fmt: skip
"""``GET /api/v1/backups``, B01-B11. Test-NewApp has never run, so it has none. A backup carries the name of the job
that created it (swagger ``BackupModel.name``): the orphaned B10 that of its deleted job, the imported B11 that of the
job on the server it came from - neither name says which it is."""

_HOLDS: dict[UUID, list[str]] = {
    B01: list(DAILY_VMS),
    B02: ["sql-prod-01", "sql-prod-02"],
    B03: ["sql-dev-01"],
    B04: list(DAILY_VMS),
    B05: ["\\\\fs01\\finance"],
    B06: list(LAPTOPS),
    B07: ["legacy-erp-01"],
    B08: ["report-01"],
    B09: ["lab-docs-prod"],
    B10: ["old-fs-01", "old-app-01"],
    B11: ["erp-db-2024"],
}

BACKUP_OBJECTS: dict[UUID, list[BackupObject]] = {
    backup_id: [BY_NAME[name] for name in names] for backup_id, names in _HOLDS.items()
}
"""``GET /api/v1/backups/{id}/objects``: the protected objects each backup holds."""

_FOLDERS = {
    B01: r"D:\Backups\Daily-VMs",
    B02: r"E:\SOBR\SQL-Prod",
    B03: r"D:\Backups\SQL-Dev",
    B04: "/backups/Copy-to-DR",
    B05: "/mnt/veeam/backups/NAS-Finance",
    B06: "/mnt/veeam/backups/Agent-Laptops",
    B07: r"\\nas02\veeam\Legacy-Archive",
    B08: "/mnt/veeam/backups/Reports-VM",
    B09: "/mnt/veeam/backups/S3-Docs",
    B10: r"D:\Backups\FileApp-Weekly",
    B11: r"\\nas02\veeam\ERP-Nightly",
}


def _weekly_gfs(job_id: UUID | None) -> bool:
    """Whether the job keeps weekly GFS fulls: only a backup job's storage sets a GFS policy in the stand."""
    job = next((job for job in JOBS if job.id == job_id), None)
    policy = job.storage.gfs_policy if isinstance(job, BackupJob) else None
    return bool(policy and policy.is_enabled and policy.weekly and policy.weekly.is_enabled)


_WEEKLY_GFS = {backup.id for backup in BACKUPS if _weekly_gfs(backup.job_id)}
"""The backups whose job keeps weekly GFS fulls (Daily-VMs): their fulls carry the ``Weekly`` flag, no other file."""


def backup_file(
    backup_id: UUID,
    obj: BackupObject,
    created: datetime,
    full: bool,
    data_gb: int,
    backup_gb: int,
    point: RestorePoint | None,
) -> BackupFile:
    """One file of a chain: a full (``.vbk``) or an increment (``.vib``) of ``obj``, made at ``created``.

    A full of a job that keeps weekly GFS fulls is flagged ``Weekly``: Daily-VMs makes one full a week, its Saturday
    synthetic full.
    """
    separator = "/" if _FOLDERS[backup_id].startswith("/") else "\\"
    ref = f".{obj.object_id}" if hasattr(obj, "object_id") else ""
    stem = obj.name.replace("\\", "_").strip("_")
    return BackupFile(
        id=UUID(
            f"53000000-0000-{int(str(backup_id)[-2:]):04d}-{point_key(obj):04d}-{int(created.strftime('%y%m%d')):012d}"
        ),
        name=f"{_FOLDERS[backup_id]}{separator}{stem}{ref}D{created:%Y-%m-%dT%H%M%S}.{'vbk' if full else 'vib'}",
        backup_id=backup_id,
        object_ids=[obj.id],
        restore_point_ids=[point.id] if point else [],
        data_size=data_gb * GB,
        backup_size=backup_gb * GB,
        dedup_ratio=80,
        compress_ratio=50,
        creation_time=created,
        gfs_periods=["Weekly"] if full and backup_id in _WEEKLY_GFS else ["None"],
    )


def _daily_vms_files() -> list[BackupFile]:
    """58 files, one per VM per night, newest first. The 50 newest hold 3000 GB of data in 1200 GB on disk."""
    rows = []
    for nights_back in range(15):
        for name in ["app-01", "web-02", "web-01", "fs-01"]:  # the VM backed up last that night first
            points = POINTS[name]
            if nights_back < len(points):
                point: RestorePoint | None = points[nights_back]
                created = points[nights_back].creation_time
            else:  # past retention: the file is still there, its point is not listed
                point = None
                created = points[-1].creation_time - timedelta(days=nights_back - len(points) + 1)
            rows.append((name, created, point))
    rows = rows[:58]
    files = [
        backup_file(B01, BY_NAME[name], created, _is_full(point, created), *((60, 24) if n < 50 else (72, 30)), point)
        for n, (name, created, point) in enumerate(rows)
    ]
    return sorted(files, key=lambda file: file.creation_time, reverse=True)


def _is_full(point: RestorePoint | None, created: datetime) -> bool:
    """A full is the point VBR calls one, or - for a file whose point is past retention - a Saturday's."""
    return point.type == "Full" if point else created.weekday() == 5


# per backup: (GB of data, GB on disk) of a full and of an increment, for the chains the plan gives no files for
_SIZES: dict[UUID, dict[str, tuple[tuple[int, int], tuple[int, int]]]] = {
    B02: {"sql-prod-01": ((380, 150), (20, 8)), "sql-prod-02": ((580, 230), (30, 12))},
    B03: {"sql-dev-01": ((215, 85), (10, 4))},
    B05: {"\\\\fs01\\finance": ((1229, 950), (35, 12))},
    B06: dict.fromkeys(LAPTOPS, ((256, 110), (6, 2))),
    B07: {"legacy-erp-01": ((300, 120), (15, 6))},  # 294 GB on disk in all (G3-30)
    B08: {"report-01": ((250, 100), (22, 9))},
    B09: {"lab-docs-prod": ((300, 240), (6, 2))},
}


def _point_files(backup_id: UUID) -> list[BackupFile]:
    """One file per restore point of each object the backup holds, newest first."""
    files = []
    for name, (full, increment) in _SIZES[backup_id].items():
        for point in POINTS[name]:
            is_full = point.type == "Full"
            files.append(
                backup_file(
                    backup_id, BY_NAME[name], point.creation_time, is_full, *(full if is_full else increment), point
                )
            )
    return sorted(files, key=lambda file: file.creation_time, reverse=True)


def _copied_at(name: str, point: RestorePoint) -> datetime | None:
    """When Copy-to-DR copied ``name``'s ``point``, or ``None`` if it did not.

    It copies Daily-VMs' points as they appear (immediate copy), so the run of the point's night copied it, and its
    copy task ended when the copy was written; a task that did not succeed copied nothing (S-ID03 warned that web-02's
    point of 10-06 was not copied, T05). The nights before the sessions the stand keeps were copied by runs like theirs.
    """
    night = point.creation_time.date()
    run = next((s for s in sessions.SESSIONS if s.job_id == J04 and s.creation_time.date() == night), None)
    if run is None:
        copy_run = sessions.RUN_BY_JOB[J04]
        return datetime.combine(night, copy_run.end, tzinfo=point.creation_time.tzinfo) - timedelta(seconds=20)
    task = next(
        (t for t in sessions.TASKS if isinstance(t, BackupTaskSession) and t.session_id == run.id and t.name == name),
        None,
    )
    if task is None or task.result.result != "Success":
        return None
    return task.end_time


def _copy_files() -> list[BackupFile]:
    """Copy-to-DR's copies of Daily-VMs' 14 nights, without restore points of their own (see the module docstring)."""
    files = [
        backup_file(B04, BY_NAME[name], copied, point.type == "Full",
                    *((60, 24) if point.type != "Full" else (72, 30)), None)
        for name in DAILY_VMS
        for point in POINTS[name]
        if (copied := _copied_at(name, point)) is not None
    ]  # fmt: skip
    return sorted(files, key=lambda file: file.creation_time, reverse=True)


def _old_files(backup_id: UUID, rows: list[tuple[str, datetime, int, int]]) -> list[BackupFile]:
    """The files of a chain no job writes to any more, oldest last and a full."""
    files = []
    for n, (name, created, data_gb, backup_gb) in enumerate(rows):
        point = next((p for p in POINTS[name] if p.creation_time.date() == created.date()), None)
        files.append(backup_file(backup_id, BY_NAME[name], created, n == len(rows) - 1, data_gb, backup_gb, point))
    return files


def _point_time(name: str, index: int) -> datetime:
    return POINTS[name][index].creation_time


BACKUP_FILES: dict[UUID, list[BackupFile]] = {
    B01: _daily_vms_files(),
    B02: _point_files(B02),
    B03: _point_files(B03),
    B04: _copy_files(),
    B05: _point_files(B05),
    B06: _point_files(B06),
    B07: _point_files(B07),
    B08: _point_files(B08),
    B09: _point_files(B09),
    # 1953 GB of data, 640 GB on disk, in 6 files
    B10: _old_files(B10, [
        ("old-app-01", _point_time("old-app-01", 0), 330, 110),
        ("old-fs-01", _point_time("old-fs-01", 0), 330, 110),
        ("old-app-01", _point_time("old-app-01", 1), 323, 105),
        ("old-fs-01", _point_time("old-fs-01", 1), 323, 105),
        ("old-app-01", _point_time("old-app-01", 2), 323, 105),
        ("old-fs-01", _point_time("old-fs-01", 2), 324, 105),
    ]),
    # 420 GB of data, 180 GB on disk
    B11: _old_files(B11, [(("erp-db-2024"), _point_time("erp-db-2024", n), 140, 60) for n in range(3)]),
}  # fmt: skip
"""``GET /api/v1/backups/{id}/backupFiles``, newest first. vbr-mcp asks for them sorted and counts them separately."""
