# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""``/api/v1/sessions``."""

from typing import Literal
from uuid import UUID

from vbr_models import VbrDateTime, VbrModel

SessionResultValue = Literal["None", "Success", "Warning", "Failed"]
SessionType = Literal[
    "BackupJob",
    "BackupCopyJob",
    "AgentBackup",
    "ConfigurationBackup",
    "MalwareDetection",
    "SureBackup",
    "RestoreVm",
    "InstantRecovery",
    "QuickMigration",
    "NasRestore",
    "Infrastructure",
    "RepositoryMaintenance",
    "HostComponentsUpdate",
    "ConfigurationResynchronize",
    "VolumesDiscover",
]
"""The ``ESessionType`` values the cases use."""
PlatformName = Literal["VMware", "WindowsPhysical", "UnstructuredData"]
"""The ``EPlatformType`` values the cases use."""


class SessionProgress(VbrModel):
    """``SessionProgress``: progress of a running job session."""

    duration: str
    processing_rate: str
    bottleneck: Literal[
        "NotDefined",
        "None",
        "Throttling",
        "SourceProxy",
        "SourceNetwork",
        "SourceWan",
        "TargetProxy",
        "TargetNetwork",
        "TargetWan",
        "Source",
        "Proxy",
        "Network",
        "Target",
        "TargetDisk",
    ]
    processed_size: int
    read_size: int
    transferred_size: int
    progress_percent: int


class SessionResult(VbrModel):
    """``SessionResultModel``."""

    result: SessionResultValue
    message: str | None = None
    is_canceled: bool | None = None


class SessionRetryInfo(VbrModel):
    """``SessionRetryInfo``: which attempt of a job run a session is."""

    is_recheck_retry: bool
    retry_number: int | None = None


class Session(VbrModel):
    """``SessionModel``, ``GET /api/v1/sessions/{id}`` and an item of ``GET /api/v1/sessions``."""

    id: UUID
    name: str
    job_id: UUID
    session_type: SessionType
    creation_time: VbrDateTime
    end_time: VbrDateTime | None = None
    state: Literal["Stopped", "Starting", "Stopping", "Working", "Pausing", "Resuming", "Idle", "Postprocessing"]
    progress_percent: int | None = None
    result: SessionResult | None = None
    usn: int
    platform_name: PlatformName | None = None
    initiated_by: str | None = None
    progress: SessionProgress | None = None
    original_session_id: UUID | None = None
    """The first attempt of the run this session retries; retries of one run share it."""
    retry_info: SessionRetryInfo | None = None
    resource_id: UUID | None = None
    """What the session works on, e.g. the Instant Recovery mount it creates."""
    resource_reference: str | None = None
    parent_session_id: UUID | None = None


# ---- Task sessions: ``/api/v1/taskSessions``, ``/api/v1/sessions/{id}/taskSessions``

TaskSessionType = Literal["Backup", "Restore", "Antivirus", "Replica"]
"""``ETaskSessionType``, the discriminator of ``TaskSessionModel``."""


class TaskSession(VbrModel):
    """``TaskSessionModel``: what every task session carries, whatever its ``type``."""

    id: UUID
    type: TaskSessionType
    session_id: UUID
    session_type: SessionType
    creation_time: VbrDateTime
    end_time: VbrDateTime | None = None


class BackupTaskSession(TaskSession):
    """``BackupTaskSessionModel``: one object of a backup session. Its outcome is ``result``."""

    type: Literal["Backup"] = "Backup"
    name: str
    restore_point_id: UUID | None = None
    algorithm: Literal["Full", "Increment", "None"] | None = None
    repository_id: UUID | None = None
    usn: int | None = None
    state: Literal["Stopped", "Starting", "Stopping", "Working", "Pausing", "Resuming", "Idle", "Postprocessing"]
    result: SessionResult
    progress: SessionProgress | None = None
    platform_type: PlatformName | None = None
    platform_id: UUID | None = None


class AntivirusTaskSession(TaskSession):
    """``AntivirusTaskSessionModel``: one restore point of a backup scan.

    It has no ``result``: its outcome is ``scanResult``.
    """

    type: Literal["Antivirus"] = "Antivirus"
    name: str
    restore_point_id: UUID | None = None
    restore_point_reference: str | None = None
    scan_type: Literal["Antivirus", "Yara"]
    scan_result: Literal["None", "Clean", "Infected", "Failed", "Canceled", "Inconclusive"]
    scan_state: Literal["NotStarted", "InProgress", "Finished"]
    antivirus_name: str | None = None


# ---- Logs: ``/api/v1/sessions/{id}/logs``, ``/api/v1/taskSessions/{id}/logs``

LogRecordStatus = Literal["None", "Succeeded", "Warning", "Failed"]
"""``ETaskLogRecordStatus``."""


class SessionLogRecord(VbrModel):
    """``SessionLogRecordModel``: one line of a session or task session log."""

    id: int
    status: LogRecordStatus
    start_time: VbrDateTime
    update_time: VbrDateTime
    title: str
    description: str | None = None


class SessionLog(VbrModel):
    """``SessionLogResult``: a whole log, as one document (not paged)."""

    total_records: int
    records: list[SessionLogRecord]
