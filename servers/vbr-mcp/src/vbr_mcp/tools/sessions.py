# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

import asyncio
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from vbr_mcp.models.shared import SessionResult
from vbr_mcp.pagination import fetch_all, fetch_total
from vbr_mcp.server import mcp, vbr_client
from vbr_mcp.tool_annotations import READ_ONLY

# ETaskLogRecordStatus / ESessionResult values that mean "something went wrong".
_FAILURE_STATUSES: tuple[str, ...] = ("Failed", "Warning")

# EAntivirusScanResult values worth drilling on a malware-detection fan-out: the scan
# errored (`Failed`) or found something (`Infected`). Antivirus task sessions carry
# `scanResult` instead of `result`, so they need their own set.
_ANTIVIRUS_FAILURE_RESULTS: frozenset[str] = frozenset({"Failed", "Infected"})

# Cap the per-object drill-down so a session that fanned out over hundreds of failing
# objects can't launch hundreds of task-log reads.
_MAX_FAILING_TASKS = 50
_MAX_CONCURRENT_LOG_FETCHES = 5


@mcp.tool(annotations=READ_ONLY)
async def list_sessions(
    id: UUID | None = None,
    name_filter: str | None = None,
    job_id_filter: UUID | None = None,
    type_filter: list[str] | None = None,
    result_filter: list[SessionResult] | None = None,
    created_after_filter: datetime | None = None,
    created_before_filter: datetime | None = None,
    order_column: Literal["Name", "SessionType", "CreationTime", "EndTime", "State", "Result", "InitiatedBy"]
    | None = None,
    order_asc: bool | None = None,
    max_items: int | None = None,
    count_only: bool = False,
) -> list[dict[str, Any]] | dict[str, Any]:
    """List sessions (the run history of any VBR operation), or - with `id` - one session.

    `count_only=True` returns just `{"total": n}`, the number of sessions the
    filters match, without fetching them - for counting sessions over long
    periods instead of paging every one into the conversation. It counts
    sessions, not jobs or runs: every retry is a session of its own, and a
    canceled run (`result.isCanceled`) counts under whatever result it ended
    with. So it answers "how many sessions", not "how many jobs failed" - for
    that, list the sessions and collapse each retry chain (`originalSessionId`)
    to its final attempt, or read each job's last result in `get_job_states`.

    A session's real outcome must be derived: `result.isCanceled` marks a
    canceled run (there is no `Canceled` enum value in `result.result`); a
    session with `endTime == null` is still running. Retries share
    `originalSessionId` - collapse a chain to its final attempt rather than
    counting each retry as a separate failure. For **why** a session failed,
    use `get_session_failure_details` instead of reading `result.message`
    alone (it is usually just a pointer to "check the log").

    `type_filter` takes VBR `ESessionType` values (100+); the common ones are
    `BackupJob`, `BackupCopyJob`, `ReplicaJob`, `AgentBackup`, `RestoreVm`,
    `InstantRecovery`, `QuickMigration`, `FileLevelRestore`, `NasRestore`,
    `MalwareDetection`, `SureBackup`, `ConfigurationBackup`. A malware Scan
    Backup runs as a `SureBackup` session: its `Failed` result means malware was
    found, unless its antivirus/YARA task sessions report the scan itself as
    `Failed`/`Inconclusive` (then nothing was verified). Timestamps without an
    offset are treated as UTC.
    """
    if id is not None:
        return await vbr_client.get(f"/api/v1/sessions/{id}")
    filters: dict[str, Any] = {
        "nameFilter": name_filter,
        "jobIdFilter": job_id_filter,
        "typeFilter": type_filter,
        "resultFilter": result_filter,
        "createdAfterFilter": created_after_filter,
        "createdBeforeFilter": created_before_filter,
    }
    if count_only:
        return {"total": await fetch_total(vbr_client, "/api/v1/sessions", **filters)}
    return await fetch_all(
        vbr_client, "/api/v1/sessions", orderColumn=order_column, orderAsc=order_asc, max_items=max_items, **filters
    )


@mcp.tool(annotations=READ_ONLY)
async def list_task_sessions(
    session_id_filter: UUID | None = None,
    name_filter: str | None = None,
    result_filter: SessionResult | None = None,
    max_items: int | None = None,
) -> list[dict[str, Any]]:
    """List task sessions - the per-object fan-out of a session. Use `session_id_filter` to scope to one session.

    The outcome/workload-name fields live on the polymorphic subtype: `result`
    (with `.message`, the field to trust) on Backup/Restore/Replica tasks,
    `scanResult`/`scanState` on Antivirus tasks (no `result`).
    """
    return await fetch_all(
        vbr_client,
        "/api/v1/taskSessions",
        sessionIdFilter=session_id_filter,
        nameFilter=name_filter,
        resultFilter=result_filter,
        max_items=max_items,
    )


@mcp.tool(annotations=READ_ONLY)
async def get_session_failure_details(session_id: UUID) -> dict[str, Any]:
    """One-shot "why did this session fail" drill-down.

    Joins the session's own failing (Failed/Warning) log records with, for each
    failing task session, the raw task plus its own failing log records under
    `logs`. Restore-session errors sit in the session-level log; backup/replica
    job errors sit in the per-object task-session log; either way this covers
    both. Truncated to the 50 worst-affected tasks (`tasksTruncated=True` past
    the cap).
    """
    keep = set(_FAILURE_STATUSES)
    session_log = await vbr_client.get(f"/api/v1/sessions/{session_id}/logs")
    session_records = [r for r in _records(session_log) if r.get("status") in keep]

    all_tasks = await fetch_all(vbr_client, f"/api/v1/sessions/{session_id}/taskSessions")
    failing = [t for t in all_tasks if t.get("id") and _is_failing_task(t, keep)]
    tasks_truncated = len(failing) > _MAX_FAILING_TASKS
    failing = failing[:_MAX_FAILING_TASKS]

    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_LOG_FETCHES)
    task_logs = await asyncio.gather(*(_bounded_task_log(t["id"], semaphore) for t in failing))
    tasks = [_task_entry(task, log, keep) for task, log in zip(failing, task_logs, strict=True)]

    return {
        "sessionId": str(session_id),
        "records": session_records,
        "tasks": tasks,
        "tasksTruncated": tasks_truncated,
    }


def _records(log_result: object) -> list[dict[str, Any]]:
    if not isinstance(log_result, dict):
        return []
    records = log_result.get("records", [])
    return records if isinstance(records, list) else []


def _is_failing_task(task: dict[str, Any], keep: set[str]) -> bool:
    result = task.get("result")
    if isinstance(result, dict) and result.get("result") in keep:
        return True
    return task.get("scanResult") in _ANTIVIRUS_FAILURE_RESULTS


async def _bounded_task_log(task_session_id: str, semaphore: asyncio.Semaphore) -> list[dict[str, Any]]:
    async with semaphore:
        return _records(await vbr_client.get(f"/api/v1/taskSessions/{task_session_id}/logs"))


def _task_entry(task: dict[str, Any], log: list[dict[str, Any]], keep: set[str]) -> dict[str, Any]:
    return {**task, "logs": [r for r in log if r.get("status") in keep]}
