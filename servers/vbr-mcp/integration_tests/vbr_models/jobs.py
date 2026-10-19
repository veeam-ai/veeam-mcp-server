# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""``/api/v1/jobs``, ``/api/v1/jobs/{id}``, ``/api/v1/jobs/states``."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from vbr_models import VbrDateTime, VbrModel
from vbr_models.sessions import SessionProgress, SessionResultValue

JobStatus = Literal["Running", "Inactive", "Disabled", "Enabled", "Stopping", "Stopped", "Starting"]
JobType = Literal[
    "VSphereBackup", "BackupCopy", "FileBackup", "ObjectStorageBackup", "WindowsAgentBackupWorkstationPolicy"
]  # the ``EJobType`` values the cases use
JobWorkload = Literal["Application", "CloudVm", "File", "Server", "Workstation", "Vm"]


class RunAfterJob(VbrModel):
    """``RunAfterJob``: the job a chained job runs after."""

    job_name: str
    job_id: UUID


class JobState(VbrModel):
    """``JobStateModel``, an item of ``GET /api/v1/jobs/states``."""

    id: UUID
    name: str
    type: JobType
    description: str
    status: JobStatus
    last_run: VbrDateTime | None = None
    last_result: SessionResultValue
    next_run: VbrDateTime | None = None
    next_run_policy: str | None = None
    workload: JobWorkload
    repository_id: UUID | None = None
    repository_name: str | None = None
    objects_count: int
    session_id: UUID | None = None
    high_priority: bool
    progress_percent: int
    session_progress: SessionProgress | None = None
    run_after_job: RunAfterJob | None = None
    backup_copy_mode: Literal["Immediate", "Periodic"] | None = None


# ---- Job configuration, ``JobModel`` (``GET /api/v1/jobs``, ``/api/v1/jobs/{id}``): polymorphic on ``type``, so
# each job type is its own model and keeps its settings in its own subtree.

DayOfWeek = Literal["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class VmwareObject(VbrModel):
    """``VmwareObjectModel``: a vSphere inventory object, the ``VSphere`` subtype of ``InventoryObjectModel``."""

    platform: Literal["VSphere"] = "VSphere"
    host_name: str
    name: str
    type: Literal["VirtualMachine", "vCenterServer", "Datacenter", "Cluster", "Host", "Folder", "Tag"]
    object_id: str | None = None


class BackupProxiesSettings(VbrModel):
    """``BackupProxiesSettingsModel``: automatic proxy selection, or the proxies chosen by hand."""

    auto_select_enabled: bool
    proxy_ids: list[UUID] | None = None


class RetentionPolicy(VbrModel):
    """``BackupJobRetentionPolicySettingsModel``."""

    type: Literal["RestorePoints", "Days"]
    quantity: int


class GfsWeekly(VbrModel):
    """``GFSPolicySettingsWeeklyModel``."""

    is_enabled: bool
    keep_for_number_of_weeks: int | None = None
    desired_time: DayOfWeek | None = None


class GfsToggle(VbrModel):
    """``GFSPolicySettingsMonthlyModel`` / ``GFSPolicySettingsYearlyModel``, as far as switched off."""

    is_enabled: bool


class GfsPolicy(VbrModel):
    """``GFSPolicySettingsModel``."""

    is_enabled: bool
    weekly: GfsWeekly | None = None
    monthly: GfsToggle | None = None
    yearly: GfsToggle | None = None


class StorageScheduleWeekly(VbrModel):
    """``AdvancedStorageScheduleWeeklyModel``."""

    is_enabled: bool
    days: list[DayOfWeek] | None = None
    local_time: str | None = None


class FullsSettings(VbrModel):
    """``SyntheticFullSettingsModel`` / ``ActiveFullSettingsModel``."""

    is_enabled: bool
    weekly: StorageScheduleWeekly | None = None


class Encryption(VbrModel):
    """``BackupStorageSettingsEncryptionModel``."""

    is_enabled: bool
    encryption_type: Literal["ByUserPassword", "ByKms"] | None = None
    encryption_password_id: UUID | None = None


class StorageData(VbrModel):
    """``BackupStorageSettingModel`` and its per-type siblings: compression and encryption of the backup files."""

    compression_level: Literal["Auto", "None", "DedupFriendly", "Optimal", "High", "Extreme"] | None = None
    encryption: Encryption


class BackupJobAdvancedSettings(VbrModel):
    """``BackupJobAdvancedSettingsModel``."""

    backup_mode_type: Literal["Full", "Incremental", "ReverseIncremental", "Transform", "TransformForeverIncremental"]
    synthetic_fulls: FullsSettings | None = None
    active_fulls: FullsSettings | None = None
    storage_data: StorageData | None = None


class BackupJobStorage(VbrModel):
    """``BackupJobStorageModel``."""

    backup_repository_id: UUID
    backup_proxies: BackupProxiesSettings
    retention_policy: RetentionPolicy
    gfs_policy: GfsPolicy | None = None
    advanced_settings: BackupJobAdvancedSettings | None = None


class Toggle(VbrModel):
    """``BackupApplicationAwareProcessingModel`` / ``GuestFileSystemIndexingModel``, as far as on or off."""

    is_enabled: bool


class BackupJobGuestProcessing(VbrModel):
    """``BackupJobGuestProcessingModel``."""

    app_aware_processing: Toggle
    guest_fs_indexing: Toggle


class ScheduleDaily(VbrModel):
    """``ScheduleDailyModel``."""

    is_enabled: bool
    local_time: str | None = None
    daily_kind: Literal["Everyday", "WeekDays", "SelectedDays"] | None = None
    days: list[DayOfWeek] | None = None


class ScheduleAfterThisJob(VbrModel):
    """``ScheduleAfterThisJobModel``."""

    is_enabled: bool
    job_name: str | None = None


class ScheduleRetry(VbrModel):
    """``ScheduleRetryModel``."""

    is_enabled: bool | None = None
    retry_count: int | None = None
    await_minutes: int | None = None


class BackupSchedule(VbrModel):
    """``BackupScheduleModel``."""

    run_automatically: bool
    daily: ScheduleDaily | None = None
    after_this_job: ScheduleAfterThisJob | None = None
    retry: ScheduleRetry | None = None


class BackupJobVirtualMachines(VbrModel):
    """``BackupJobVirtualMachinesModel``."""

    includes: list[VmwareObject]


class BackupJob(VbrModel):
    """``BackupJobModel``: ``type="VSphereBackup"``."""

    id: UUID
    name: str
    type: Literal["VSphereBackup"] = "VSphereBackup"
    is_disabled: bool
    description: str
    is_high_priority: bool
    virtual_machines: BackupJobVirtualMachines
    storage: BackupJobStorage
    guest_processing: BackupJobGuestProcessing
    schedule: BackupSchedule


class JobObject(VbrModel):
    """``JobObjectModel``: a job as the source of a backup copy."""

    id: UUID
    name: str | None = None
    type: JobType | None = None


class BackupCopyIncludeObjects(VbrModel):
    """``BackupCopyIncludeObjectsModel``."""

    jobs: list[JobObject]


class BackupCopyJobObjects(VbrModel):
    """``BackupCopyJobObjectsModel``."""

    includes: BackupCopyIncludeObjects


class BackupCopyJobAdvancedSettings(VbrModel):
    """``BackupCopyJobAdvancedSettingsModel``."""

    storage_data: StorageData | None = None


class BackupCopyJobTarget(VbrModel):
    """``BackupCopyJobTargetModel``."""

    backup_repository_id: UUID
    retention_policy: RetentionPolicy | None = None
    advanced_settings: BackupCopyJobAdvancedSettings | None = None


class WanAcceleratorSettings(VbrModel):
    """``WanAcceleratorSettingsModel``."""

    transfer_mode: Literal["Direct", "WANAccelerator"]
    source_wan_accelerator_id: UUID | None = Field(default=None, alias="sourceWANAcceleratorId")
    target_wan_accelerator_id: UUID | None = Field(default=None, alias="targetWANAcceleratorId")


class BackupCopyJobDataTransfer(VbrModel):
    """``BackupCopyJobDataTransferModel``."""

    wan_accelerator_settings: WanAcceleratorSettings | None = None


class ImmediateBackupCopySchedule(VbrModel):
    """``ImmediateBackupCopyScheduleModel``: the ``Immediate`` subtype of ``BackupCopyJobScheduleModel``."""

    type: Literal["Immediate"] = "Immediate"
    schedule_mode: Literal["Continuous", "BackupWindow"]


class BackupCopyJob(VbrModel):
    """``BackupCopyJobModel``: ``type="BackupCopy"``."""

    id: UUID
    name: str
    type: Literal["BackupCopy"] = "BackupCopy"
    is_disabled: bool
    description: str
    mode: Literal["Immediate", "Periodic"]
    source_objects: BackupCopyJobObjects
    target: BackupCopyJobTarget
    data_transfer: BackupCopyJobDataTransfer | None = None
    schedule: ImmediateBackupCopySchedule | None = None


class UnstructuredDataRetentionPolicy(VbrModel):
    """``UnstructuredDataRetentionPolicySettingsModel``."""

    type: Literal["Days", "Months"]
    quantity: int


class UnstructuredDataAdvancedSettings(VbrModel):
    """``FileBackupJobAdvancedSettingsModel`` / ``ObjectStorageBackupJobAdvancedSettingsModel``."""

    storage_data: StorageData | None = None


class UnstructuredDataPrimaryRepository(VbrModel):
    """``FileBackupJobPrimaryRepositoryModel`` / ``ObjectStorageBackupJobPrimaryRepositoryModel``."""

    backup_repository_id: UUID
    retention_policy: UnstructuredDataRetentionPolicy | None = None
    advanced_settings: UnstructuredDataAdvancedSettings | None = None


class FileBackupJobObject(VbrModel):
    """``FileBackupJobObjectModel``."""

    path: str | None = None
    type: Literal["File", "Directory", "FileServerRoot", "FileServerShare"]
    file_server_id: UUID


class FileBackupJob(VbrModel):
    """``FileBackupJobModel``: ``type="FileBackup"``."""

    id: UUID
    name: str
    type: Literal["FileBackup"] = "FileBackup"
    is_disabled: bool
    description: str
    is_high_priority: bool
    objects: list[FileBackupJobObject]
    backup_repository: UnstructuredDataPrimaryRepository
    schedule: BackupSchedule


class ObjectStorageBackupJobObject(VbrModel):
    """``ObjectStorageBackupJobObjectModel``."""

    path: str | None = None
    type: Literal["Prefix", "Object", "Container", "ObjectStorageRoot"]
    object_storage_server_id: UUID
    container: str | None = None


class ObjectStorageBackupJob(VbrModel):
    """``ObjectStorageBackupJobModel``: ``type="ObjectStorageBackup"``."""

    id: UUID
    name: str
    type: Literal["ObjectStorageBackup"] = "ObjectStorageBackup"
    is_disabled: bool
    description: str
    is_high_priority: bool
    objects: list[ObjectStorageBackupJobObject]
    backup_repository: UnstructuredDataPrimaryRepository
    schedule: BackupSchedule


class AgentObject(VbrModel):
    """``AgentObjectModel``: the ``Agent`` subtype of ``InventoryObjectModel``."""

    platform: Literal["Agent"] = "Agent"
    id: UUID
    name: str
    type: Literal["ProtectionGroup", "WindowsComputer", "LinuxComputer", "WindowsCluster"]
    protection_group_id: UUID


class AgentBackupPolicyRepositoryDestination(VbrModel):
    """``AgentBackupPolicyStorageBackupRepositoryModel``: the ``BackupRepository`` destination of an agent policy."""

    destination_type: Literal["BackupRepository"] = "BackupRepository"
    backup_server_name: str
    backup_repository_id: UUID


class AgentBackupPolicyAdvancedSettings(VbrModel):
    """``AgentBackupPolicyAdvancedSettingsModel``."""

    storage_data: StorageData | None = None


class AgentBackupPolicyStorage(VbrModel):
    """``AgentBackupPolicyStorageModel``."""

    destination: AgentBackupPolicyRepositoryDestination
    retention_policy: RetentionPolicy | None = None
    advanced_settings: AgentBackupPolicyAdvancedSettings | None = None


class WorkstationPolicySchedule(VbrModel):
    """``WindowsAgentBackupPolicyWorkstationScheduleModel``."""

    run_automatically: bool
    daily: ScheduleDaily | None = None


class WindowsAgentWorkstationPolicy(VbrModel):
    """``WindowsAgentManagementBackupWorkstationPolicyModel``: ``type="WindowsAgentBackupWorkstationPolicy"``."""

    id: UUID
    name: str
    type: Literal["WindowsAgentBackupWorkstationPolicy"] = "WindowsAgentBackupWorkstationPolicy"
    is_disabled: bool
    description: str
    computers: list[AgentObject]
    backup_mode: Literal["EntireComputer", "Volumes", "FileLevel"]
    storage: AgentBackupPolicyStorage
    schedule: WorkstationPolicySchedule | None = None


Job = BackupJob | BackupCopyJob | FileBackupJob | ObjectStorageBackupJob | WindowsAgentWorkstationPolicy
"""``JobModel``: one of its subtypes, picked by ``type``."""
