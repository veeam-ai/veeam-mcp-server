# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""Jobs (1.2): their configuration (``/jobs``, ``/jobs/{id}``) and live state (``/jobs/states``).

Two changes to the plan, both because VBR would not hold the plan's version: Reports-VM makes a weekly synthetic full
(it writes to a hardened repository, which does not take forever-forward incremental chains - User Guide v13,
hardened_repository_limitations), and every VM backup job has VBR's default automatic retry (Daily-VMs did retry on
10-05; SQL-Prod is set to two retries). Job states read as VBR 13 reports them (swagger JobStatesResultExample): a job
that has run and is idle is ``Stopped``, with the progress of its last run at 100%; only the job that never ran is
``Inactive``.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from stand import repositories
from stand.agents import LAPTOPS
from stand.ids import (
    ENCRYPTION_PASSWORD,
    GB,
    J01,
    J02,
    J03,
    J04,
    J05,
    J06,
    J07,
    J08,
    J09,
    J10,
    N01,
    N04,
    PG01,
    R01,
    R02,
    R03,
    R04,
    S01,
    W01,
    W02,
    at,
    mnemonic,
)
from stand.inventory import VCENTER_NAME, VMS
from stand.sessions import SESSIONS, SQL_DEV_PROGRESS
from vbr_models.jobs import (
    AgentBackupPolicyAdvancedSettings,
    AgentBackupPolicyRepositoryDestination,
    AgentBackupPolicyStorage,
    AgentObject,
    BackupCopyIncludeObjects,
    BackupCopyJob,
    BackupCopyJobAdvancedSettings,
    BackupCopyJobDataTransfer,
    BackupCopyJobObjects,
    BackupCopyJobTarget,
    BackupJob,
    BackupJobAdvancedSettings,
    BackupJobGuestProcessing,
    BackupJobStorage,
    BackupJobVirtualMachines,
    BackupProxiesSettings,
    BackupSchedule,
    DayOfWeek,
    Encryption,
    FileBackupJob,
    FileBackupJobObject,
    FullsSettings,
    GfsPolicy,
    GfsToggle,
    GfsWeekly,
    ImmediateBackupCopySchedule,
    Job,
    JobObject,
    JobState,
    JobStatus,
    JobType,
    JobWorkload,
    ObjectStorageBackupJob,
    ObjectStorageBackupJobObject,
    RetentionPolicy,
    RunAfterJob,
    ScheduleAfterThisJob,
    ScheduleDaily,
    ScheduleRetry,
    StorageData,
    StorageScheduleWeekly,
    Toggle,
    UnstructuredDataAdvancedSettings,
    UnstructuredDataPrimaryRepository,
    UnstructuredDataRetentionPolicy,
    VmwareObject,
    WanAcceleratorSettings,
    WindowsAgentWorkstationPolicy,
    WorkstationPolicySchedule,
)
from vbr_models.sessions import Session, SessionProgress, SessionResultValue

# ---- Configuration

ENCRYPTED = StorageData(
    compression_level="Optimal",
    encryption=Encryption(
        is_enabled=True, encryption_type="ByUserPassword", encryption_password_id=ENCRYPTION_PASSWORD
    ),
)
NOT_ENCRYPTED = StorageData(compression_level="Optimal", encryption=Encryption(is_enabled=False))

DEFAULT_RETRY = ScheduleRetry(is_enabled=True, retry_count=3, await_minutes=10)
"""VBR's default for a backup job: three retries, ten minutes apart (swagger ScheduleRetryModel)."""


def daily(local_time: str, *, retry: ScheduleRetry | None = DEFAULT_RETRY) -> BackupSchedule:
    """A schedule that runs every day at ``local_time`` on the server's clock."""
    return BackupSchedule(
        run_automatically=True,
        daily=ScheduleDaily(is_enabled=True, local_time=local_time, daily_kind="Everyday"),
        retry=retry,
    )


def vm_job(
    id: UUID,
    name: str,
    vms: list[str],
    repository_id: UUID,
    retention: RetentionPolicy,
    storage_data: StorageData,
    schedule: BackupSchedule,
    *,
    is_disabled: bool = False,
    gfs_policy: GfsPolicy | None = None,
    synthetic_full_days: list[DayOfWeek] | None = None,
    app_aware: bool = False,
    description: str = "",
) -> BackupJob:
    """A vSphere backup job of ``vms``, forward incremental with a synthetic full on ``synthetic_full_days``."""
    return BackupJob(
        id=id,
        name=name,
        is_disabled=is_disabled,
        description=description,
        is_high_priority=False,
        virtual_machines=BackupJobVirtualMachines(
            includes=[
                VmwareObject(host_name=VCENTER_NAME, name=vm, type="VirtualMachine", object_id=VMS[vm].ref)
                for vm in vms
            ]
        ),
        storage=BackupJobStorage(
            backup_repository_id=repository_id,
            backup_proxies=BackupProxiesSettings(auto_select_enabled=True),
            retention_policy=retention,
            gfs_policy=gfs_policy,
            advanced_settings=BackupJobAdvancedSettings(
                backup_mode_type="Incremental",
                synthetic_fulls=(
                    FullsSettings(
                        is_enabled=True, weekly=StorageScheduleWeekly(is_enabled=True, days=synthetic_full_days)
                    )
                    if synthetic_full_days
                    else FullsSettings(is_enabled=False)
                ),
                active_fulls=FullsSettings(is_enabled=False),
                storage_data=storage_data,
            ),
        ),
        guest_processing=BackupJobGuestProcessing(
            app_aware_processing=Toggle(is_enabled=app_aware), guest_fs_indexing=Toggle(is_enabled=False)
        ),
        schedule=schedule,
    )


DAILY_VMS = ("web-01", "web-02", "app-01", "fs-01")
"""The VMs Daily-VMs backs up, as its job lists them."""


def repository_id(job: Job) -> UUID:
    """The repository ``job`` writes to (a SOBR's own id): the setting sits in a different subtree per job type."""
    match job:
        case BackupJob():
            return job.storage.backup_repository_id
        case BackupCopyJob():
            return job.target.backup_repository_id
        case FileBackupJob() | ObjectStorageBackupJob():
            return job.backup_repository.backup_repository_id
        case WindowsAgentWorkstationPolicy():
            return job.storage.destination.backup_repository_id


def storage_data(job: Job) -> StorageData | None:
    """``job``'s storage settings, encryption among them: they sit in a different subtree per job type."""
    match job:
        case BackupJob() | WindowsAgentWorkstationPolicy():
            advanced = job.storage.advanced_settings
        case BackupCopyJob():
            advanced = job.target.advanced_settings
        case FileBackupJob() | ObjectStorageBackupJob():
            advanced = job.backup_repository.advanced_settings
    return advanced.storage_data if advanced else None


JOBS: list[Job] = [
    vm_job(
        J01, "Daily-VMs", list(DAILY_VMS), R01, RetentionPolicy(type="Days", quantity=14),
        ENCRYPTED, daily("22:00"),
        gfs_policy=GfsPolicy(
            is_enabled=True,
            weekly=GfsWeekly(is_enabled=True, keep_for_number_of_weeks=4, desired_time="Sunday"),
            monthly=GfsToggle(is_enabled=False),
            yearly=GfsToggle(is_enabled=False),
        ),
        synthetic_full_days=["Saturday"], app_aware=True,
    ),
    vm_job(
        J02, "SQL-Prod", ["sql-prod-01", "sql-prod-02"], S01, RetentionPolicy(type="RestorePoints", quantity=30),
        ENCRYPTED, daily("00:00", retry=ScheduleRetry(is_enabled=True, retry_count=2, await_minutes=10)),
        app_aware=True,
    ),
    vm_job(
        J03, "SQL-Dev", ["sql-dev-01"], R01, RetentionPolicy(type="RestorePoints", quantity=7), NOT_ENCRYPTED,
        daily("02:00"),
    ),
    BackupCopyJob(
        id=J04,
        name="Copy-to-DR",
        is_disabled=False,
        description="",
        mode="Immediate",
        source_objects=BackupCopyJobObjects(
            includes=BackupCopyIncludeObjects(jobs=[JobObject(id=J01, name="Daily-VMs", type="VSphereBackup")])
        ),
        target=BackupCopyJobTarget(
            backup_repository_id=R04,
            retention_policy=RetentionPolicy(type="RestorePoints", quantity=14),
            advanced_settings=BackupCopyJobAdvancedSettings(storage_data=ENCRYPTED),
        ),
        data_transfer=BackupCopyJobDataTransfer(
            wan_accelerator_settings=WanAcceleratorSettings(
                transfer_mode="WANAccelerator", source_wan_accelerator_id=W01, target_wan_accelerator_id=W02
            )
        ),
        schedule=ImmediateBackupCopySchedule(schedule_mode="Continuous"),
    ),
    FileBackupJob(
        id=J05,
        name="NAS-Finance",
        is_disabled=False,
        description="",
        is_high_priority=False,
        objects=[FileBackupJobObject(path="\\\\fs01\\finance", type="FileServerShare", file_server_id=N01)],
        backup_repository=UnstructuredDataPrimaryRepository(
            backup_repository_id=R02,
            retention_policy=UnstructuredDataRetentionPolicy(type="Days", quantity=28),
            advanced_settings=UnstructuredDataAdvancedSettings(storage_data=NOT_ENCRYPTED),
        ),
        schedule=daily("21:00", retry=None),
    ),
    WindowsAgentWorkstationPolicy(
        id=J06,
        name="Agent-Laptops",
        is_disabled=False,
        description="",
        computers=[
            AgentObject(id=mnemonic("81000000", n), name=name, type="WindowsComputer", protection_group_id=PG01)
            for n, name in enumerate(LAPTOPS, 1)
        ],
        backup_mode="EntireComputer",
        storage=AgentBackupPolicyStorage(
            destination=AgentBackupPolicyRepositoryDestination(backup_server_name="vbr-lab01", backup_repository_id=R02),
            retention_policy=RetentionPolicy(type="RestorePoints", quantity=10),
            advanced_settings=AgentBackupPolicyAdvancedSettings(storage_data=ENCRYPTED),
        ),
        schedule=WorkstationPolicySchedule(
            run_automatically=True, daily=ScheduleDaily(is_enabled=True, local_time="12:00", daily_kind="Everyday")
        ),
    ),
    vm_job(
        J07, "Legacy-Archive", ["legacy-erp-01"], R03, RetentionPolicy(type="RestorePoints", quantity=30),
        NOT_ENCRYPTED, daily("03:00"), is_disabled=True,
    ),
    vm_job(
        J08, "Reports-VM", ["report-01"], R02, RetentionPolicy(type="RestorePoints", quantity=14), NOT_ENCRYPTED,
        BackupSchedule(
            run_automatically=True,
            daily=ScheduleDaily(is_enabled=False),
            after_this_job=ScheduleAfterThisJob(is_enabled=True, job_name="Daily-VMs"),
            retry=DEFAULT_RETRY,
        ),
        synthetic_full_days=["Saturday"],  # the hardened repository takes no forever-forward incremental chain
    ),
    vm_job(
        J09, "Test-NewApp", ["new-app-01"], S01, RetentionPolicy(type="Days", quantity=14), ENCRYPTED, daily("23:30"),
    ),
    ObjectStorageBackupJob(
        id=J10,
        name="S3-Docs",
        is_disabled=False,
        description="",
        is_high_priority=False,
        objects=[ObjectStorageBackupJobObject(type="Container", object_storage_server_id=N04, container="lab-docs-prod")],
        backup_repository=UnstructuredDataPrimaryRepository(
            backup_repository_id=R02,
            retention_policy=UnstructuredDataRetentionPolicy(type="Days", quantity=14),
            advanced_settings=UnstructuredDataAdvancedSettings(storage_data=ENCRYPTED),
        ),
        schedule=daily("21:30", retry=None),
    ),
]  # fmt: skip
"""``GET /api/v1/jobs``: every job's configuration, J01-J10."""

# ---- Live state


def _duration(start: datetime, end: datetime) -> str:
    seconds = int((end - start).total_seconds())
    return f"{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"


class _LastRun:
    """What a job's newest session says about its last run: the session, when the run began, how it went."""

    def __init__(self, job_id: UUID) -> None:
        mine = [s for s in SESSIONS if s.job_id == job_id]
        self.session: Session | None = mine[0] if mine else None  # newest first
        original = self.session.original_session_id if self.session else None
        first = next((s for s in mine if s.id == original), self.session)
        self.started = first.creation_time if first else None


def _ran(processed_gb: int, read_gb: int, transferred_gb: int, rate: str, bottleneck: str) -> SessionProgress:
    return SessionProgress.model_validate({
        "duration": "",  # the last session's, filled in by _progress
        "processingRate": rate,
        "bottleneck": bottleneck,
        "processedSize": processed_gb * GB,
        "readSize": read_gb * GB,
        "transferredSize": transferred_gb * GB,
        "progressPercent": 100,
    })


_LAST_RUN_PROGRESS: dict[UUID, SessionProgress] = {
    J01: _ran(1404, 240, 96, "99 MB/s", "Source"),
    J02: _ran(0, 0, 0, "N/A", "NotDefined"),  # the last attempt failed in guest processing, before reading data
    J04: _ran(240, 96, 38, "52 MB/s", "Network"),
    J05: _ran(1229, 35, 12, "41 MB/s", "Source"),
    J06: _ran(512, 18, 7, "9 MB/s", "Network"),
    J08: _ran(250, 22, 9, "23 MB/s", "Target"),
    J10: _ran(300, 6, 2, "7 MB/s", "Source"),
}
"""What an idle job's state reports about its last run: volumes, rate and bottleneck, at 100%."""


def _progress(job_id: UUID, last: _LastRun) -> SessionProgress | None:
    if job_id == J03:
        return SQL_DEV_PROGRESS
    if job_id not in _LAST_RUN_PROGRESS or last.session is None or last.session.end_time is None:
        return None
    duration = _duration(last.session.creation_time, last.session.end_time)
    return _LAST_RUN_PROGRESS[job_id].model_copy(update={"duration": duration})


def job_state(
    id: UUID,
    name: str,
    type: JobType,
    workload: JobWorkload,
    repository_id: UUID,
    objects_count: int,
    *,
    status: JobStatus | None = None,
    last_result: SessionResultValue | None = None,
    last_run: datetime | None = None,
    next_run: datetime | None = None,
    next_run_policy: str | None = None,
    run_after_job: RunAfterJob | None = None,
    backup_copy_mode: Literal["Immediate", "Periodic"] | None = None,
) -> JobState:
    """A job's live state, read off its newest session unless given: status, last result, last run and progress."""
    last = _LastRun(id)
    result = last.session.result.result if last.session and last.session.result else "None"
    running = last.session is not None and last.session.end_time is None
    progress = _progress(id, last)
    return JobState(
        id=id,
        name=name,
        type=type,
        description="",
        status=status or ("Running" if running else "Stopped" if last.session else "Inactive"),
        last_run=last_run or last.started,
        # a running job's last result is that of its previous run
        last_result=last_result or (_previous_result(id) if running else result),
        next_run=next_run,
        next_run_policy=next_run_policy,
        workload=workload,
        repository_id=repository_id,
        repository_name=repositories.NAMES[repository_id],
        objects_count=objects_count,
        session_id=last.session.id if last.session else None,
        high_priority=False,
        progress_percent=progress.progress_percent if progress else 0,
        session_progress=progress,
        run_after_job=run_after_job,
        backup_copy_mode=backup_copy_mode,
    )


def _previous_result(job_id: UUID) -> SessionResultValue:
    finished = [s for s in SESSIONS if s.job_id == job_id and s.end_time is not None]
    return finished[0].result.result if finished and finished[0].result else "None"


JOB_STATES: list[JobState] = [
    job_state(J01, "Daily-VMs", "VSphereBackup", "Vm", R01, 4, next_run=at(7, 22, 0)),
    job_state(J02, "SQL-Prod", "VSphereBackup", "Vm", S01, 2, next_run=at(8, 0, 0)),
    job_state(J03, "SQL-Dev", "VSphereBackup", "Vm", R01, 1, next_run=at(8, 2, 0)),
    job_state(J04, "Copy-to-DR", "BackupCopy", "Vm", R04, 1, backup_copy_mode="Immediate"),
    job_state(J05, "NAS-Finance", "FileBackup", "File", R02, 1, next_run=at(7, 21, 0)),
    job_state(J06, "Agent-Laptops", "WindowsAgentBackupWorkstationPolicy", "Workstation", R02, 3,
              next_run=at(7, 12, 0)),
    # disabled since its last run 25 days ago; that session is older than the history the stand keeps
    job_state(J07, "Legacy-Archive", "VSphereBackup", "Vm", R03, 1, status="Disabled", last_result="Success",
              last_run=at(12, 3, 0, 2, month=9)),
    job_state(J08, "Reports-VM", "VSphereBackup", "Vm", R02, 1, next_run_policy="After [Daily-VMs]",
              run_after_job=RunAfterJob(job_name="Daily-VMs", job_id=J01)),
    # created an hour before T0 and never run
    job_state(J09, "Test-NewApp", "VSphereBackup", "Vm", S01, 1, next_run=at(7, 23, 30)),
    job_state(J10, "S3-Docs", "ObjectStorageBackup", "File", R02, 1, next_run=at(7, 21, 30)),
]  # fmt: skip
"""``GET /api/v1/jobs/states``. SQL-Prod's ``sessionId`` is its last attempt (S-ID06), ``lastRun`` when the run began
(S-ID04); SQL-Dev runs, started by hand at 08:40."""
