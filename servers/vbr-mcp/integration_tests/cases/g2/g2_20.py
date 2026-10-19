# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G2-20: SQL-Dev failed this morning and did not retry - why, and what to do.

The run that failed was started by hand, and "Veeam Backup & Replication does not perform automatic retry for jobs
that were started or stopped manually" (User Guide v13, job_retry); SQL-Dev's scheduled runs keep their three
automatic retries. A forum favourite (forums.veeam.com t25554, "automatic retry jobs not working"): the agent must read
who started the run (``initiatedBy``) and say so, rather than blame the retry settings, and still give the cause of
the failure from the task log.
"""

from datetime import timedelta
from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case

import stand
from cases import CaseInputs, Environment, judge, tool_budget
from cases.patterns import any_of, near
from evaluators import FactsPresent, ToolsCalled, ToolsNotCalled
from stand.ids import J03, S_ID07, S_ID08, at
from stand.jobs import JOB_STATES
from stand.protected import points_of
from stand.sessions import ADMIN, BY_ID, SESSIONS, TASKS
from vbr_models.sessions import SessionProgress, SessionResult

# ---- What VBR serves: the base stand, but SQL-Dev's run started by LAB\admin at 08:40 ended at 08:52 Failed: the
# VM snapshot of sql-dev-01 could not be made, its datastore being out of space. No retry follows a manual run.

FAILED_AT = at(7, 8, 52, 30)
JOB_FAILED = "Failed to process 1 of 1 VMs. See the session log for details."
SNAPSHOT_ERROR = (
    "Failed to create VM snapshot. Error: CreateSnapshot failed, vmRef vm-1048, timeout 1800000, snName VEEAM BACKUP "
    "TEMPORARY SNAPSHOT, snDescription Please do not delete this snapshot. It is being used by Veeam Backup., memory "
    "False, quiesce True An error occurred while saving the snapshot: Insufficient disk space on datastore "
    "'esx02-ds1'."
)

_RUN = BY_ID[S_ID08].model_copy(
    update={
        "end_time": FAILED_AT,
        "state": "Stopped",
        "progress_percent": 100,
        "result": SessionResult(result="Failed", message=JOB_FAILED, is_canceled=False),
        "progress": None,
    }
)
_TASK = next(task for task in TASKS if task.session_id == S_ID08)
_FAILED_TASK = _TASK.model_copy(
    update={
        "end_time": FAILED_AT - timedelta(seconds=20),
        "state": "Stopped",
        "result": SessionResult(result="Failed", message=SNAPSHOT_ERROR, is_canceled=False),
        "progress": None,
    }
)
_STATE = stand.replace(
    JOB_STATES,
    J03,
    status="Stopped",
    last_result="Failed",
    progress_percent=100,
    session_progress=SessionProgress(
        duration="00:12:19",
        processing_rate="N/A",
        bottleneck="NotDefined",
        processed_size=0,
        read_size=0,
        transferred_size=0,
        progress_percent=100,
    ),
)

ENVIRONMENT: Environment = stand.environment(
    sessions=[_RUN if s.id == S_ID08 else s for s in SESSIONS],
    tasks=[_FAILED_TASK if t.id == _TASK.id else t for t in TASKS],
    job_states=_STATE,
)

# ---- What a correct answer says, derived from the data above.

_SCHEDULED = BY_ID[S_ID07]
_LATEST_POINT = points_of("sql-dev-01")[0]
assert _LATEST_POINT.creation_time < _RUN.creation_time and _RUN.initiated_by == ADMIN

EXPECTED = (
    f"The run that failed was not a scheduled one: it was started manually by {ADMIN} at "
    f"{_RUN.creation_time:%H:%M} and failed at {FAILED_AT:%H:%M}. VBR does not retry automatically a job run that "
    "was started (or stopped) manually, so no retries is expected - the job's automatic retry (3 times, 10 minutes "
    f"apart) applies to scheduled runs. The scheduled run at {_SCHEDULED.creation_time:%H:%M} succeeded, so "
    f"sql-dev-01's latest restore point is {_LATEST_POINT.creation_time:%Y-%m-%d %H:%M}. Why it failed: the VM "
    "snapshot of sql-dev-01 could not be created - insufficient disk space on datastore esx02-ds1. What to do: free "
    "space on esx02-ds1 (or move the VM's disks or the snapshot location), then retry the job (it reprocesses only "
    "the failed VM) or start it again - or wait for tonight's scheduled 02:00 run, which has its automatic retries."
)
"""Ground truth for the judges."""

FACTS = {
    "manual": any_of(
        r"\bmanual",
        r"by\s+hand",
        r"started\s+by\s+(an?\s+)?(user|admin|administrator|lab)",
        r"lab\\admin",
        r"initiated\s+by",
    ),
    "cause_space": any_of(
        r"insufficient\s+(disk\s+)?space", near(r"datastore", r"full|space|capacity", 80), r"esx02-ds1"
    ),
    "fix_space": any_of(
        r"free\s+(up\s+)?(some\s+)?(disk\s+)?space",
        r"(add|increase|expand|extend|grow)\w*\s+([\w'-]+\s+){0,3}(space|capacity|datastore|esx02-ds1)",
        r"(clean\s+up|delete|remove|consolidate)\w*\s+([\w'-]+\s+){0,4}(snapshots?|files?|vms?|space|datastores?|esx02-ds1)",
        r"(move|migrate|relocate)\w*\s+([\w'-]+\s+){0,5}(datastore|disks?|vm|snapshot)",
        r"storage\s+v?motion",
    ),
    "fix_retry": any_of(
        r"\bretry",
        r"re-?run",
        r"(start|run)\s+(it|the\s+job|sql-dev)\s+(again|manually)",
        r"next\s+(scheduled\s+)?run",
        r"tonight",
    ),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

_ALLOWED = (
    "It is acceptable, and not a violation, to mention the snapshot settings or vSphere-side checks, to note that "
    "sql-dev-01 is still protected by the 02:15 point, to quote the error, or to offer to retry or start the job "
    "after the space is freed, as long as the output does not claim it retried or started anything."
)

GOOD = [
    (
        "**Why no retries:** this morning's SQL-Dev run was **started manually** (by LAB\\admin at 08:40). VBR never "
        "runs automatic retries for jobs that were started or stopped manually - the job's retry setting (3 retries, 10 "
        "minutes apart) applies to its scheduled runs only. The scheduled run at 02:00 succeeded, so sql-dev-01 has a "
        "restore point from 02:15 today.\n\n**Why it failed:** the VM snapshot couldn't be created: *Insufficient disk "
        "space on datastore 'esx02-ds1'*.\n\n**What to do:**\n1. Free up space on datastore esx02-ds1.\n2. Then retry "
        "the job, or just let tonight's 02:00 run do it."
    ),
    (
        "| | |\n|---|---|\n| Failed run | 08:40, initiated by LAB\\admin (manual) |\n| Error | snapshot failed - "
        "datastore esx02-ds1 is full |\n| Retries | none: VBR doesn't auto-retry manual runs |\n\nExtend the datastore or "
        "delete old snapshots on it, then re-run SQL-Dev."
    ),
    (
        "It didn't retry because it was a manual run - automatic retry only covers scheduled sessions. The cause was "
        "insufficient space on esx02-ds1 for the VM snapshot. Clean up that datastore, then start SQL-Dev again "
        "manually (and retry if needed)."
    ),
]

BAD = {
    "manual": "SQL-Dev failed at 08:52 because datastore esx02-ds1 is out of space for the snapshot. The automatic "
    "retry seems to be disabled - turn it on, free up space and retry the job.",
    "cause_space": "The 08:40 run was started manually, so VBR did not retry it. Retry the job now.",
    "fix_space": "The 08:40 run was started manually, so VBR did not retry it. It failed on insufficient disk space "
    "on datastore esx02-ds1. Retry the job.",
}


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G2-20",
        inputs=CaseInputs(
            question=(
                "SQL-Dev failed this morning and I don't see any retries. Why didn't it retry, and what should I do?"
            ),
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G2", "base_stand": "1.2-1.3 (S-ID08 failed)"},
        evaluators=[
            # Who started the run is in the session (initiatedBy); the error in the failing task (the failure
            # details or the task session's result.message).
            ToolsCalled("run_read", frozenset({"list_sessions", "get_job_states"})),
            ToolsCalled("error_read", frozenset({"get_session_failure_details", "list_task_sessions"})),
            *tool_budget(4),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "retry_rule_explained",
                f"The output explains that VBR does not retry automatically a run that was started manually: this "
                f"morning's run was started by {ADMIN} at 08:40, so no automatic retries is expected behaviour, not a "
                "fault of the job's retry settings.",
            ),
            _judge(
                "cause_from_log",
                "The output gives the cause from the failed task: the VM snapshot of sql-dev-01 could not be created "
                "because datastore esx02-ds1 is out of space. It does not invent another cause.",
            ),
            _judge(
                "scheduled_run_fine",
                "The output does not claim that sql-dev-01 has no backup from today or that the scheduled 02:00 run "
                "failed: the 02:00 run succeeded.",
            ),
            _judge(
                "next_steps",
                "The output tells the user to free space on the datastore (or move the VM's disks or snapshots) "
                "and then retry or re-run the job, or to let the next scheduled run pick it up.",
            ),
            _judge(
                "no_action_taken",
                "The output does not claim that it retried, started or changed anything; offering to do it is fine.",
            ),
        ],
    )
