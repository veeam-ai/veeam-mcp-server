# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

from typing import Any, Literal
from uuid import UUID

from vbr_mcp.models.shared import SessionResult
from vbr_mcp.pagination import fetch_all
from vbr_mcp.server import mcp, vbr_client
from vbr_mcp.tool_annotations import DESTRUCTIVE, READ_ONLY, WRITE

# These types carry a copy-specific schedule, not a standard `BackupScheduleModel`.
_COPY_JOB_TYPES = frozenset({"BackupCopy", "LegacyBackupCopy", "FileBackupCopy", "EntraIDTenantBackupCopy"})

# `EJobType`
JobType = Literal[
    "Unknown",
    "VSphereBackup",
    "HyperVBackup",
    "VSphereReplica",
    "CloudDirectorBackup",
    "EntraIDTenantBackup",
    "EntraIDAuditLogBackup",
    "FileBackupCopy",
    "LegacyBackupCopy",
    "BackupCopy",
    "WindowsAgentBackup",
    "LinuxAgentBackup",
    "FileBackup",
    "ObjectStorageBackup",
    "EntraIDTenantBackupCopy",
    "SureBackupContentScan",
    "CloudBackupAzure",
    "CloudBackupAWS",
    "CloudBackupGoogle",
    "WindowsAgentBackupWorkstationPolicy",
    "LinuxAgentBackupWorkstationPolicy",
    "WindowsAgentBackupServerPolicy",
    "LinuxAgentBackupServerPolicy",
    "NutanixAHVBackupJob",
    "ProxmoxBackupJob",
    "IrisBackup",
    "WindowsAgentBackupFailoverCluster",
]

# `EJobStatus`
JobStatus = Literal["Running", "Inactive", "Disabled", "Enabled", "Stopping", "Stopped", "Starting"]


@mcp.tool(annotations=READ_ONLY)
async def list_jobs(
    id: UUID | None = None,
    name_filter: str | None = None,
    type_filter: JobType | None = None,
    max_items: int | None = None,
) -> list[dict[str, Any]] | dict[str, Any]:
    """List backup job configuration, or - with `id` - one job's configuration.

    Covers type/platform, encryption, retention/GFS, full-backup strategy, schedule. `JobModel` is polymorphic on
    `type` - most fields are read from a different
    subtree per job type (e.g. the VM backup family keeps retention/encryption
    under `storage.*`, `FileBackup`/`ObjectStorageBackup` under
    `backupRepository.*`, `BackupCopy` under `target.*`). Every job also carries
    `scheduleKind` (`daily`/`monthly`/`periodically`/`continuously`/`chained`/
    `copy`/`none`), the resolved active schedule kind. For **live status** (is
    it running, last result, throughput) use `get_job_states` instead - this
    tool is configuration only.
    """
    if id is not None:
        job = await vbr_client.get(f"/api/v1/jobs/{id}")
        return {**job, "scheduleKind": _schedule_kind(job)}
    rows = await fetch_all(
        vbr_client, "/api/v1/jobs", nameFilter=name_filter, typeFilter=type_filter, max_items=max_items
    )
    return [{**job, "scheduleKind": _schedule_kind(job)} for job in rows]


def _schedule_kind(job: dict[str, Any]) -> str:
    if job.get("type") in _COPY_JOB_TYPES:
        return "copy"
    schedule = job.get("schedule") or {}
    if (schedule.get("afterThisJob") or {}).get("isEnabled"):
        return "chained"
    if (schedule.get("continuously") or {}).get("isEnabled"):
        return "continuously"
    if (schedule.get("periodically") or {}).get("isEnabled"):
        return "periodically"
    if (schedule.get("monthly") or {}).get("isEnabled"):
        return "monthly"
    if (schedule.get("daily") or {}).get("isEnabled"):
        return "daily"
    return "none"


@mcp.tool(annotations=READ_ONLY)
async def get_job_states(
    name_filter: str | None = None,
    status_filter: JobStatus | None = None,
    last_result_filter: SessionResult | None = None,
    max_items: int | None = None,
) -> list[dict[str, Any]]:
    """List jobs' live operational state: running/idle status, last-run result, progress/throughput, bottleneck.

    `status`: only `"Running"` (and the transitional `"Starting"`/`"Stopping"`)
    means a session is active now. `"Stopped"`, `"Inactive"` and `"Enabled"` are
    normal idle states, not a fault - `"Stopped"` is how a job reads after its
    run finished, not a sign that someone stopped it. On an idle job,
    `progressPercent`/`sessionProgress` describe its last run (100 = that run
    completed), not current activity. `lastResult == "None"` means never run (or
    running for the first time). When
    `status == "Running"`, read `sessionProgress` for `progressPercent` and the
    raw volumes (`processedSize`/`readSize`/`transferredSize`, bytes) -
    `processingRate` is already-humanized text (e.g. `"120 MB/s"`) and can be
    empty; never compute a rate yourself from size/duration. `bottleneck` names
    the busiest pipeline stage (`Source`/`Proxy`/`Network`/`Target`/`TargetDisk`)
    when meaningful.
    """
    return await fetch_all(
        vbr_client,
        "/api/v1/jobs/states",
        nameFilter=name_filter,
        statusFilter=status_filter,
        lastResultFilter=last_result_filter,
        max_items=max_items,
    )


@mcp.tool(annotations=WRITE)
async def start_job(
    job_id: UUID,
    perform_active_full: bool = False,
    start_chained_jobs: bool = False,
    sync_restore_points: Literal["All", "Latest"] | None = None,
) -> None:
    """Start a job now.

    A backup copy job in immediate copy mode (`type == "BackupCopy"` with
    `mode == "Immediate"` in `list_jobs`, `backupCopyMode == "Immediate"` in
    `get_job_states`) starts as a sync of either all existing restore points
    (`sync_restore_points="All"`) or only the latest available one
    (`"Latest"`), and VBR refuses to start it without that choice ("Please
    provide 'SyncRestorePoints' for Immediate Backup Copy Job."), even with
    `perform_active_full=True`. Every other job ignores `sync_restore_points`.
    """
    body: dict[str, Any] = {"performActiveFull": perform_active_full, "startChainedJobs": start_chained_jobs}
    if sync_restore_points is not None:
        body["syncRestorePoints"] = sync_restore_points
    await vbr_client.post(f"/api/v1/jobs/{job_id}/start", json=body)


@mcp.tool(annotations=DESTRUCTIVE)
async def stop_job(job_id: UUID, graceful_stop: bool = True) -> None:
    """Stop a running job.

    `graceful_stop=True` finishes a restore point for objects already/being processed before stopping; `False`
    aborts immediately. It cannot cancel the job's chained jobs (VBR's `cancelChainedJobs` is not exposed): a job
    chained after this one still starts.
    """
    await vbr_client.post(f"/api/v1/jobs/{job_id}/stop", json={"gracefulStop": graceful_stop})


@mcp.tool(annotations=WRITE)
async def retry_job(job_id: UUID, start_chained_jobs: bool = False) -> None:
    """Retry a job's last run, reprocessing only the objects that previously failed."""
    await vbr_client.post(f"/api/v1/jobs/{job_id}/retry", json={"startChainedJobs": start_chained_jobs})


@mcp.tool(annotations=WRITE)
async def enable_job(job_id: UUID) -> None:
    """Enable a disabled job so its schedule resumes."""
    await vbr_client.post(f"/api/v1/jobs/{job_id}/enable")


@mcp.tool(annotations=DESTRUCTIVE)
async def disable_job(job_id: UUID) -> None:
    """Disable a job so it no longer runs on its schedule.

    A running instance is not stopped by this - use `stop_job` for that.
    """
    await vbr_client.post(f"/api/v1/jobs/{job_id}/disable")
