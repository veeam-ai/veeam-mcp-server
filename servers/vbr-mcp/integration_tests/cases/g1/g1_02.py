# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G1-02: which jobs are running right now."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import CaseInputs, judge, tool_budget
from cases.patterns import name, percent
from evaluators import FactsPresent, ToolsNotCalled
from stand import environment
from stand.ids import GB, J03, T0
from stand.jobs import JOB_STATES
from stand.sessions import BY_ID

# ---- What VBR serves: the base stand. SQL-Dev runs (45%, started by hand at 08:40); every other job that has run
# reads Stopped with its last run's progress at 100%, as VBR 13 reports an idle job (swagger JobStatesResultExample).

ENVIRONMENT = environment()

# ---- What a correct answer says, derived from the stand.

_RUNNING = next(state for state in JOB_STATES if state.status == "Running")
assert _RUNNING.id == J03 and _RUNNING.session_id is not None and _RUNNING.session_progress is not None
_SESSION = BY_ID[_RUNNING.session_id]
_STARTED = _SESSION.creation_time
_PROGRESS = _RUNNING.session_progress
_MINUTES = round((T0 - _STARTED).total_seconds() / 60)  # 20
_IDLE = [state.name for state in JOB_STATES if state.status == "Stopped"]


def _gb(size: int) -> str:
    return f"{size / GB:.1f} GB"


EXPECTED = (
    f"One job is running: {_RUNNING.name}, started {_MINUTES} minutes ago at {_STARTED:%H:%M} (by "
    f"{_SESSION.initiated_by}, manually). It is {_PROGRESS.progress_percent}% done, processing at "
    f"{_PROGRESS.processing_rate}, bottleneck {_PROGRESS.bottleneck}; processed ≈{_gb(_PROGRESS.processed_size)}, read "
    f"≈{_gb(_PROGRESS.read_size)}, transferred ≈{_gb(_PROGRESS.transferred_size)}. No other job is running: "
    f"{', '.join(_IDLE)} read Stopped with 100% progress, which describes their last finished run - that is how VBR "
    "reports an idle job, not a manual stop; Legacy-Archive is disabled and Test-NewApp has never run."
)
"""Ground truth for the judges."""

FACTS = {
    "job": name(_RUNNING.name),
    "progress": percent(_PROGRESS.progress_percent),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

_ALLOWED = (
    "It is acceptable, and not a violation, to give the rate, the bottleneck or the processed, read and transferred "
    "volumes (rounded or not), to explain that a Source bottleneck means the job is limited by reading from the "
    f"source storage, to mention that the run was started manually by {_SESSION.initiated_by}, or to mention the "
    "other jobs' last results or schedules as they are."
)

GOOD = [
    (
        "Only one job is running right now: **SQL-Dev**. It was started manually by LAB\\admin at 08:40 and is 45% "
        "complete after about 20 minutes, processing at 86 MB/s (bottleneck: Source). All other jobs are idle - their "
        "last runs have finished (Stopped, 100%), Legacy-Archive is disabled and Test-NewApp has never run."
    ),
    (
        "| Job | Status | Progress | Started |\n|---|---|---|---|\n| SQL-Dev | Running | 45% | 2026-10-07 08:40 (manual) |"
        "\n\nNothing else is running; the other jobs are between runs."
    ),
    (
        "SQL-Dev is the only active job - 45 percent done, running for twenty minutes (since 8:40 AM). Processed ~97 GB "
        "so far, read 41 GB and transferred 19 GB at 86 MB/s."
    ),
]

BAD = {
    "job": "No backup job is running at the moment: Daily-VMs, SQL-Prod and the others are all Stopped.",
    "progress": "SQL-Dev is running since 08:40 and is about halfway through.",
}
"""Answers that each miss one fact."""


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G1-02",
        inputs=CaseInputs(
            question="Which backup jobs are running right now and how far along are they?",
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G1", "base_stand": "1.2"},
        evaluators=[
            # get_job_states is the answer; list_sessions (who started it) and get_server_status (what "now" is)
            # are reads the case allows on top of it.
            ToolCorrectness(expected_tools=["get_job_states"], allow_extra=True),
            *tool_budget(3),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "only_sql_dev_running",
                f"The output presents {_RUNNING.name} as the only job that is running now, and does not present any "
                "other job as running or in progress - including jobs whose state shows 100% progress, which is "
                "their last finished run.",
            ),
            _judge(
                "stopped_is_idle",
                "The output does not describe jobs whose status is Stopped as stopped by someone, stuck, broken or "
                "failed because of that status: Stopped with 100% progress is how VBR reports a job that is idle "
                "after its last run. Reporting a job's last result as it is, for example that SQL-Prod's last run "
                "failed, is fine.",
            ),
            _judge(
                "numbers_as_reported",
                f"If the output gives {_RUNNING.name}'s processing rate or its processed, read or transferred "
                f"volumes, they are VBR's: {_PROGRESS.processing_rate}; about {_gb(_PROGRESS.processed_size)}, "
                f"{_gb(_PROGRESS.read_size)} and {_gb(_PROGRESS.transferred_size)} (rounding is fine). The output "
                "does not compute a rate of its own from the sizes and the duration. Leaving them out is fine.",
            ),
            _judge(
                "not_stuck",
                f"The output does not describe {_RUNNING.name} as stuck, hung, stalled or not progressing: it is "
                f"{_PROGRESS.progress_percent}% done.",
            ),
        ],
    )
