# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""Sessions (1.3): every run of the eight days before T0, with the task sessions and logs VBR keeps for each.

The key sessions S-ID01..S-ID16 are the plan's; every other scheduled run of 09-29..10-06 is routine. Retries follow
swagger ``SessionRetryInfo``: an original run has no ``retryInfo`` and is its own ``originalSessionId``; its retries
share that id and are numbered 1..N without the original (SQL-Prod: S-ID04, then S-ID05 = retry 1, S-ID06 = retry 2,
as its ``retryCount`` of 2 allows).

There is no configuration backup session after 2026-09-27. Job encryption was turned on that day, which put a password
into the Password Manager, and from then on VBR does not start a configuration backup whose own encryption is off
(User Guide v13, config_backup_encrypted). The runs before it finished with the Warning an unencrypted configuration
backup gets ("Skipping credentials backup because the encryption is disabled", forum t74377).
"""

from datetime import date, datetime, time, timedelta
from typing import NamedTuple
from uuid import UUID

from stand.agents import LAPTOPS
from stand.ids import (
    J01,
    J02,
    J03,
    J04,
    J05,
    J06,
    J08,
    J10,
    R01,
    R02,
    R04,
    S01,
    S_CFG_OK,
    S_ID03,
    S_ID04,
    S_ID05,
    S_ID06,
    S_ID08,
    S_ID10,
    S_ID13,
    S_ID14,
    S_ID15,
    S_ID16,
    T0,
    T01,
    T02,
    T03,
    T04,
    T05,
    T06,
    T07,
    T08,
    T09,
    T10,
    T11,
    T12,
    ZERO,
    at,
    mnemonic,
)
from stand.protected import POINTS
from vbr_models.protected_objects import RestorePoint
from vbr_models.sessions import (
    AntivirusTaskSession,
    BackupTaskSession,
    LogRecordStatus,
    PlatformName,
    Session,
    SessionLog,
    SessionLogRecord,
    SessionProgress,
    SessionResult,
    SessionResultValue,
    SessionRetryInfo,
    SessionType,
    TaskSession,
)

# ---- What the sessions and their logs say

SQL_PROD_FAILED = "Failed to process 1 of 2 VMs. See the session log for details."
DAILY_VMS_FAILED = "Failed to process 1 of 4 VMs. See the session log for details."
CANCELED = "Operation was canceled by user: LAB\\admin"
GUEST_ERROR = (
    "Failed to prepare guest for hot backup. Error: Cannot connect to the host's administrative share. "
    "Host: [10.0.20.11]. Account: [LAB\\svc-sql-veeam]. Win32 error:The user name or password is incorrect. Code: 1326"
)
"""Why sql-prod-01 fails (KB3225): the guest processing account's password is wrong."""
SNAPSHOT_ERROR = (
    "Failed to create VM snapshot. Error: CreateSnapshot failed, vmRef vm-1043, timeout 1800000, snName VEEAM BACKUP "
    "TEMPORARY SNAPSHOT, snDescription Please do not delete this snapshot. It is being used by Veeam Backup., memory "
    "False, quiesce True Cannot create a quiesced snapshot because the create snapshot operation exceeded the time "
    "limit for holding off I/O in the frozen virtual machine."
)
"""Why web-02 failed on 10-05 (KB1065); the retry got it."""
COPY_WARNING = (
    "Restore point for web-02 was not copied within the copy interval: source restore point is still being processed."
)
LAPTOP_OFFLINE = "Computer is offline. Backup will be retried when the computer becomes available."
LOW_SPACE = "Backup repository is getting low on free disk space (860 GB free of 20 TB)."
CONFIG_WARNING = "Skipping credentials backup because the encryption is disabled."
SCAN_FOUND = "Malware has been detected in the scanned restore point."
THREAT = "Ransom:Win32/LockBit.SB!MTB"
INFECTED_FILE = r"E:\Shares\finance\Q3\invoice_0912.xlsx.lockbit"
ANTIVIRUS = "Microsoft Defender Antivirus"
ADMIN = "LAB\\admin"
MCP_ACCOUNT = "LAB\\svc-vbr-mcp"
"""The VBR account vbr-mcp logs in with: who a session started by one of its actions is ``initiatedBy``."""

SQL_DEV_PROGRESS = SessionProgress(
    duration="00:19:49",  # 08:40:11 to T0
    processing_rate="86 MB/s",
    bottleneck="Source",
    processed_size=103_724_924_928,
    read_size=44_238_323_712,
    transferred_size=20_293_720_064,
    progress_percent=45,
)
"""SQL-Dev's run, started by hand at 08:40:11 and 45% through at T0."""


class Run(NamedTuple):
    """How a job runs: its session type, platform, the time of day its run starts and ends, what it processes."""

    job_name: str
    job_id: UUID
    session_type: SessionType
    platform: PlatformName
    start: time
    end: time
    objects: tuple[str, ...]
    repository_id: UUID


RUNS: list[Run] = [
    Run("SQL-Prod", J02, "BackupJob", "VMware", time(0, 0, 4), time(0, 21, 30), ("sql-prod-02", "sql-prod-01"), S01),
    Run("SQL-Dev", J03, "BackupJob", "VMware", time(2, 0, 3), time(2, 16, 45), ("sql-dev-01",), R01),
    Run("Agent-Laptops", J06, "AgentBackup", "WindowsPhysical", time(12, 0, 1), time(12, 31, 20), LAPTOPS, R02),
    Run("NAS-Finance", J05, "BackupJob", "UnstructuredData", time(21, 0, 2), time(21, 14, 30), ("\\\\fs01\\finance",), R02),
    Run("S3-Docs", J10, "BackupJob", "UnstructuredData", time(21, 30, 2), time(21, 44, 10), ("lab-docs-prod",), R02),
    Run("Daily-VMs", J01, "BackupJob", "VMware", time(22, 0, 5), time(22, 41, 10), ("fs-01", "web-01", "web-02", "app-01"), R01),
    Run("Reports-VM", J08, "BackupJob", "VMware", time(22, 41, 30), time(22, 58, 2), ("report-01",), R02),
    Run("Copy-to-DR", J04, "BackupCopyJob", "VMware", time(22, 41, 40), time(23, 12, 55),
        ("fs-01", "web-01", "web-02", "app-01"), R04),
]  # fmt: skip
"""Every job that runs on its own; Legacy-Archive is disabled and Test-NewApp has never run. Reports-VM is chained
after Daily-VMs and Copy-to-DR copies its points as they appear, so both start once Daily-VMs is done."""

RUN_BY_JOB = {run.job_id: run for run in RUNS}

FIRST_DAY = date(2026, 9, 29)
"""The oldest day with job sessions: a day before the seven the cases look back on."""

_USN_EPOCH = at(1, 0, 0, month=9)


def _usn(start: datetime) -> int:
    """VBR's update sequence number grows with every change; ordering by start time is enough here."""
    return 51_000_000 + int((start - _USN_EPOCH).total_seconds())


def session(
    number: int,
    run_or_name: Run | str,
    start: datetime,
    end: datetime | None,
    result: SessionResultValue,
    *,
    message: str = "",
    is_canceled: bool = False,
    retry_of: UUID | None = None,
    retry_number: int | None = None,
    initiated_by: str | None = None,
    progress: SessionProgress | None = None,
    session_type: SessionType | None = None,
    job_id: UUID | None = None,
    platform: PlatformName | None = None,
) -> Session:
    """A session as ``/sessions`` lists it. ``retry_of``/``retry_number``: the run it retries, and which retry it is."""
    run = run_or_name if isinstance(run_or_name, Run) else None
    own_id = mnemonic("40000000", number)
    return Session(
        id=own_id,
        name=run.job_name if run else str(run_or_name),
        job_id=run.job_id if run else (job_id or ZERO),
        session_type=run.session_type if run else (session_type or "BackupJob"),
        creation_time=start,
        end_time=end,
        state="Working" if end is None else "Stopped",
        progress_percent=progress.progress_percent if progress else 100,
        result=SessionResult(result=result, message=message, is_canceled=is_canceled),
        usn=_usn(start),
        platform_name=run.platform if run else platform,
        initiated_by=initiated_by,
        progress=progress,
        original_session_id=retry_of or own_id,
        retry_info=SessionRetryInfo(is_recheck_retry=False, retry_number=retry_number) if retry_of else None,
    )


def started(
    number: int,
    run_or_name: Run | str,
    *,
    retry_of: UUID | None = None,
    retry_number: int | None = None,
    session_type: SessionType | None = None,
    job_id: UUID | None = None,
    platform: PlatformName | None = None,
) -> Session:
    """A session one of vbr-mcp's actions started at T0, as VBR answers the action with it: ``Starting``, at 0%."""
    return session(
        number, run_or_name, T0, None, "None", retry_of=retry_of, retry_number=retry_number, initiated_by=MCP_ACCOUNT,
        session_type=session_type, job_id=job_id, platform=platform,
    ).model_copy(update={"state": "Starting", "progress_percent": 0})  # fmt: skip


def _on(day: date, moment: time) -> datetime:
    return at(day.day, moment.hour, moment.minute, moment.second, month=day.month, year=day.year)


_SQL_PROD, _SQL_DEV, _LAPTOPS, _NAS, _S3, _DAILY, _REPORTS, _COPY = RUNS
_OCT_5 = date(2026, 10, 5)

KEY_SESSIONS: list[Session] = [
    session(1, _DAILY, at(6, 22, 0, 5), at(6, 22, 41, 10), "Success"),
    session(2, _REPORTS, at(6, 22, 41, 30), at(6, 22, 58, 2), "Success"),
    session(3, _COPY, at(6, 22, 41, 40), at(6, 23, 12, 55), "Warning"),
    session(4, _SQL_PROD, at(7, 0, 0, 4), at(7, 0, 21, 37), "Failed", message=SQL_PROD_FAILED),
    session(5, _SQL_PROD, at(7, 0, 31, 40), at(7, 0, 36, 2), "Failed", message=SQL_PROD_FAILED,
            retry_of=S_ID04, retry_number=1),
    session(6, _SQL_PROD, at(7, 0, 46, 5), at(7, 0, 50, 31), "Failed", message=SQL_PROD_FAILED,
            retry_of=S_ID04, retry_number=2),
    session(7, _SQL_DEV, at(7, 2, 0, 3), at(7, 2, 16, 45), "Success"),
    session(8, _SQL_DEV, at(7, 8, 40, 11), None, "None", initiated_by=ADMIN, progress=SQL_DEV_PROGRESS),
    session(10, _LAPTOPS, at(6, 12, 0, 1), at(6, 12, 31, 20), "Warning", message=LOW_SPACE),
    session(11, _NAS, at(6, 21, 0, 2), at(6, 21, 14, 30), "Success"),
    session(12, _S3, at(6, 21, 30, 2), at(6, 21, 44, 10), "Success"),
    # The Scan Backup an admin ran on fs-01's newest point: VBR runs it as a SureBackup session named "Scan Backup"
    # (swagger, POST /malwareDetection/scanBackup), and Failed is how it reports that it found malware.
    session(13, "Scan Backup", at(6, 23, 20), at(6, 23, 36, 40), "Failed", message=SCAN_FOUND, initiated_by=ADMIN,
            session_type="SureBackup", platform="VMware"),
    session(14, _DAILY, at(5, 22, 0, 4), at(5, 22, 48, 12), "Failed", message=DAILY_VMS_FAILED),
    session(15, _DAILY, at(5, 22, 58, 15), at(5, 23, 9, 40), "Success", retry_of=S_ID14, retry_number=1),
    # chained: it starts once that night's Daily-VMs run is over (22:41:10), and an admin canceled it
    session(16, _REPORTS, at(4, 22, 41, 31), at(4, 22, 47, 31), "Failed", message=CANCELED, is_canceled=True),
]  # fmt: skip
"""The plan's key sessions (1.3), the ones the cases ask about."""

_KEY_SLOTS = {(s.job_id, s.creation_time.date()) for s in KEY_SESSIONS}

_DELAYED: dict[tuple[UUID, date], tuple[time, time]] = {
    # 10-05: Daily-VMs retried until 23:09:40, so its chained job and its copy started late
    (J08, _OCT_5): (time(23, 10, 5), time(23, 26, 37)),
    (J04, _OCT_5): (time(22, 48, 40), time(23, 21, 15)),
}


def _routine() -> list[Session]:
    """Every other scheduled run from 09-29 on: Success, but Agent-Laptops warns while laptop-fin-01 is offline."""
    sessions = []
    for offset in range((T0.date() - FIRST_DAY).days + 1):
        day = FIRST_DAY + timedelta(days=offset)
        for n, run in enumerate(RUNS):
            start_at, end_at = _DELAYED.get((run.job_id, day), (run.start, run.end))
            start = _on(day, start_at)
            if start >= T0 or (run.job_id, day) in _KEY_SLOTS:
                continue
            offline = run.job_id == J06 and day > date(2026, 10, 1)  # laptop-fin-01 last connected on 10-01
            sessions.append(
                session(
                    300 + 10 * offset + n,
                    run,
                    start,
                    _on(day, end_at),
                    "Warning" if offline else "Success",
                    message=LOW_SPACE if offline else "",
                )
            )
    return sessions


ROUTINE_SESSIONS = _routine()

CONFIG_BACKUP_SESSIONS: list[Session] = [
    session(
        int(str(S_CFG_OK)[-12:]) - (27 - day),
        "Backup Configuration Job",
        at(day, 10, 0, month=9),
        at(day, 10, 3, 41, month=9),
        "Warning",
        message=CONFIG_WARNING,
        session_type="ConfigurationBackup",
    )
    for day in range(18, 28)
]
"""The daily configuration backups up to 2026-09-27 (S-CFG-OK, the last one): unencrypted, so each warned."""

SESSIONS: list[Session] = sorted(
    KEY_SESSIONS + ROUTINE_SESSIONS + CONFIG_BACKUP_SESSIONS, key=lambda s: s.creation_time, reverse=True
)
"""``GET /api/v1/sessions``: newest first, as VBR lists them."""

BY_ID: dict[UUID, Session] = {s.id: s for s in SESSIONS}

# ---- Task sessions: one per object a session processed


def _point(name: str, start: datetime, end: datetime) -> RestorePoint | None:
    """The restore point ``name`` got from a run that went from ``start`` to ``end``, if it has one."""
    return next((p for p in POINTS.get(name, []) if start <= p.creation_time <= end), None)


def task(
    task_id: UUID,
    owner: Session,
    name: str,
    result: SessionResultValue,
    message: str = "",
    *,
    is_canceled: bool = False,
    copy: bool = False,
) -> BackupTaskSession:
    """The task of ``owner`` that processed ``name``; a successful backup task points at the restore point it made."""
    run = RUN_BY_JOB.get(owner.job_id)
    end = owner.end_time
    point = None if copy or result not in ("Success", "Warning") else _point(name, owner.creation_time, end or T0)
    return BackupTaskSession(
        id=task_id,
        session_id=owner.id,
        session_type=owner.session_type,
        creation_time=(point.creation_time - timedelta(seconds=25))
        if point
        else owner.creation_time + timedelta(seconds=35),
        end_time=None if end is None else end - timedelta(seconds=20),
        name=name,
        restore_point_id=point.id if point else None,
        algorithm="Increment",
        repository_id=run.repository_id if run else None,
        state="Working" if end is None else "Stopped",
        result=SessionResult(result=result, message=message, is_canceled=is_canceled),
        platform_type=owner.platform_name,
    )


_FS_01_SCANNED = POINTS["fs-01"][0]

T07_SCAN = AntivirusTaskSession(
    id=T07,
    session_id=S_ID13,
    session_type="SureBackup",
    creation_time=at(6, 23, 20, 20),
    end_time=at(6, 23, 36, 40),
    name="fs-01",
    restore_point_id=_FS_01_SCANNED.id,
    restore_point_reference=f"/api/v1/restorePoints/{_FS_01_SCANNED.id}",
    scan_type="Antivirus",
    scan_result="Infected",
    scan_state="Finished",
    antivirus_name=ANTIVIRUS,
)
"""The Scan Backup's one task: an antivirus task, whose outcome is ``scanResult``, not ``result``."""

_KEY_TASKS: dict[UUID, list[tuple[UUID | None, str, SessionResultValue, str]]] = {
    # session -> (task id, or None to number it from 1000; object; result; message)
    S_ID04: [(T02, "sql-prod-02", "Success", ""), (T01, "sql-prod-01", "Failed", GUEST_ERROR)],
    S_ID05: [(T03, "sql-prod-01", "Failed", GUEST_ERROR)],  # a retry reprocesses only what failed
    S_ID06: [(T04, "sql-prod-01", "Failed", GUEST_ERROR)],
    S_ID03: [(None, "fs-01", "Success", ""), (None, "web-01", "Success", ""), (T05, "web-02", "Warning", COPY_WARNING),
             (None, "app-01", "Success", "")],
    S_ID10: [(None, "laptop-hr-01", "Success", ""), (None, "laptop-hr-02", "Success", ""),
             (T06, "laptop-fin-01", "Warning", LAPTOP_OFFLINE)],
    S_ID14: [(T11, "fs-01", "Success", ""), (T09, "web-01", "Success", ""), (T08, "web-02", "Failed", SNAPSHOT_ERROR),
             (T10, "app-01", "Success", "")],
    S_ID15: [(T12, "web-02", "Success", "")],
    S_ID16: [(None, "report-01", "Failed", CANCELED)],
}  # fmt: skip


def _warned(owner: Session) -> bool:
    return owner.result is not None and owner.result.result == "Warning"


def _tasks() -> list[TaskSession]:
    tasks: list[TaskSession] = [T07_SCAN]
    number = iter(range(1000, 10_000))
    for owner in sorted(SESSIONS, key=lambda s: s.creation_time):
        run = RUN_BY_JOB.get(owner.job_id)
        if run is None:
            continue  # configuration backups have no task sessions; the scan's task is above
        rows: list[tuple[UUID | None, str, SessionResultValue, str]] = []
        if owner.id in _KEY_TASKS:
            rows = _KEY_TASKS[owner.id]
        elif owner.id == S_ID08:  # running: sql-dev-01 is being processed
            rows = [(None, "sql-dev-01", "None", "")]
        else:
            for name in run.objects:
                offline = owner.job_id == J06 and name == "laptop-fin-01" and _warned(owner)
                rows.append((None, name, "Warning" if offline else "Success", LAPTOP_OFFLINE if offline else ""))
        for task_id, name, result, message in rows:
            tasks.append(
                task(
                    task_id or mnemonic("41000000", next(number)),
                    owner,
                    name,
                    result,
                    message,
                    is_canceled=message == CANCELED,
                    copy=run.session_type == "BackupCopyJob",
                )
            )
    return sorted(tasks, key=lambda t: t.creation_time, reverse=True)


TASKS: list[TaskSession] = _tasks()
"""``GET /api/v1/taskSessions``: every session's tasks, newest first."""


# ---- Logs


def log(start: datetime, lines: list[tuple[LogRecordStatus, str]], end: datetime | None = None) -> SessionLog:
    """A log of ``lines``, a second apart from ``start``; the last one at ``end`` when the run is over."""
    records = []
    for n, (status, title) in enumerate(lines, 1):
        moment = end if end is not None and n == len(lines) else start + timedelta(seconds=n)
        records.append(SessionLogRecord(id=n, status=status, start_time=moment, update_time=moment, title=title))
    return SessionLog(total_records=len(records), records=records)


def _console(moment: datetime) -> str:
    """A time as the VBR console writes it in a log: ``10/7/2026 12:46:05 AM``."""
    return f"{moment.month}/{moment.day}/{moment.year} {moment.hour % 12 or 12}:{moment:%M:%S} {moment:%p}"


def session_log(owner: Session) -> SessionLog:
    """What ``/sessions/{id}/logs`` answers: the service records of the run, ending with its outcome."""
    result = owner.result or SessionResult(result="None")
    end = owner.end_time
    if owner.session_type == "ConfigurationBackup":
        lines: list[tuple[LogRecordStatus, str]] = [
            ("Succeeded", "Starting configuration backup"),
            ("Warning", CONFIG_WARNING),
            ("Succeeded", "Configuration database has been backed up"),
            ("Warning", f"Job finished with warning at {_console(end or T0)}"),
        ]
        return log(owner.creation_time, lines, end)
    if owner.session_type == "SureBackup":
        scan: list[tuple[LogRecordStatus, str]] = [
            ("Succeeded", f"Scan Backup started by {owner.initiated_by or ADMIN}")
        ]
        if owner.id == S_ID13:  # the stand's scan of fs-01's newest point, which found LockBit
            scan += [
                ("Succeeded", f"Scanning restore point of fs-01 created {_FS_01_SCANNED.creation_time:%Y-%m-%d %H:%M}"),
                ("Failed", SCAN_FOUND),
            ]
        elif end is None:
            scan.append(("None", "Scanning restore points"))
        elif result.result == "Success":
            scan.append(("Succeeded", "No malware has been detected in the scanned restore points"))
        else:
            scan.append(("Warning" if result.result == "Warning" else "Failed", result.message or SCAN_FOUND))
        return log(owner.creation_time, scan, end)
    listing = "Building VM list" if owner.platform_name == "VMware" else "Building object list"
    run: list[tuple[LogRecordStatus, str]] = [
        ("Succeeded", f"Job started at {_console(owner.creation_time)}"),
        ("Succeeded", listing),
    ]
    if end is None:
        run.append(("None", "Processing sql-dev-01" if owner.id == S_ID08 else "Processing"))
    elif result.is_canceled:
        run.append(("Warning", CANCELED))
    elif result.result == "Success":
        run.append(("Succeeded", f"Job finished at {_console(end)}"))
    elif result.result == "Warning":
        run.append(("Warning", f"Job finished with warning at {_console(end)}"))
    else:
        run.append(("Failed", f"Job finished with error at {_console(end)}"))
    return log(owner.creation_time, run, end)


_SCAN_OUTCOME: dict[str, tuple[LogRecordStatus, str]] = {
    "Clean": ("Succeeded", "No threats found"),
    "Infected": ("Failed", "Restore point is infected"),
    "Failed": ("Failed", "Restore point was not scanned"),
    "Inconclusive": ("Warning", "Scan of the restore point is inconclusive"),
    "Canceled": ("Warning", "Scan was canceled"),
}
"""The last line of an antivirus task's log, by its ``scanResult``: the mock's wording."""


def task_log(owned: TaskSession) -> SessionLog:
    """What ``/taskSessions/{id}/logs`` answers: how the object was processed."""
    lines: list[tuple[LogRecordStatus, str]] = [("Succeeded", "Queued for processing")]
    if isinstance(owned, AntivirusTaskSession):
        lines.append(("Succeeded", f"Scanning restore point with {owned.antivirus_name or ANTIVIRUS}"))
        if owned.id == T07:  # the stand's scan of fs-01's newest point
            lines += [("Failed", f"{THREAT} found in {INFECTED_FILE}"), ("Failed", "Restore point is infected")]
        elif owned.end_time is None or owned.scan_state != "Finished":
            lines.append(("None", "Scanning the mounted disks"))
        else:
            lines.append(_SCAN_OUTCOME.get(owned.scan_result, ("Warning", f"Scan result: {owned.scan_result}")))
        return log(owned.creation_time, lines, owned.end_time)
    if not isinstance(owned, BackupTaskSession):
        return log(owned.creation_time, lines, owned.end_time)
    lines.append(("Succeeded", "Required backup infrastructure resources have been assigned"))
    outcome = owned.result
    if owned.end_time is None:
        lines.append(("None", "Hard disk 2 (135 GB) 44.2 GB read at 86 MB/s"))
    elif outcome.result == "Failed":
        lines += [("Failed" if not outcome.is_canceled else "Warning", outcome.message or "Processing failed")]
        lines.append(("Failed", "Processing finished with errors"))
    elif outcome.result == "Warning":
        lines += [("Warning", outcome.message or ""), ("Warning", "Processing finished with warnings")]
    else:
        lines.append(("Succeeded", "Processing finished"))
    return log(owned.creation_time, lines, owned.end_time)
