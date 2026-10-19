# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-12: "stop all running jobs" - the targets listed first, and a partial failure on the immediate copy."""

from functools import partial
from uuid import UUID

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

import stand
from cases import MULTI_TURN, CaseInputs, Environment, confirm, judge, tool_budget
from cases.g3.actions import refused_stops, updated
from cases.patterns import name
from evaluators import WRITE_TOOLS, FactsPresent, ToolsCalled, ToolsNotCalled, VbrNotRequested, VbrRequested, matching
from stand.ids import J03, J04, J10, S_ID08, S_ID21, S_ID22, at
from stand.sessions import ADMIN, RUN_BY_JOB
from vbr_mock.markers import VbrAction, VbrError
from vbr_models.jobs import JobState
from vbr_models.sessions import Session, SessionProgress

# ---- What VBR serves: the base stand with the case's delta - three jobs are running: SQL-Dev (the base stand's
# manual run), S3-Docs (started by hand at 08:45) and Copy-to-DR, the immediate copy of Daily-VMs, copying web-02's
# point that missed last night's copy interval. Stopping SQL-Dev or S3-Docs is accepted. An immediate backup copy can
# only be disabled, not stopped (User Guide v13, backup_copy_manual_start_stop), so VBR refuses its stop; the text of
# that refusal is not known, so the mock's is neutral rather than a hint. Every other job is not running. Disabling
# is a separate action the user has not agreed to; VBR would accept it.

"""What VBR answers a stop of a job that is not running (JobsControllerImpl, test plan 0.3)."""
COPY_NOT_STOPPED = VbrError(status_code=400, message="Unable to stop the specified job.")

SQL_DEV = stand.by_name(stand.jobs.JOB_STATES, "SQL-Dev")
COPY_TO_DR = stand.by_name(stand.jobs.JOB_STATES, "Copy-to-DR")
S3_DOCS = stand.by_name(stand.jobs.JOB_STATES, "S3-Docs")

S3_STARTED, COPY_STARTED = at(7, 8, 45, 0), at(7, 8, 52, 10)
S3_PROGRESS = SessionProgress(
    duration="00:15:00",
    processing_rate="40 MB/s",
    bottleneck="Source",
    processed_size=42_949_672_960,
    read_size=36_507_222_016,
    transferred_size=30_064_771_072,
    progress_percent=60,
)
COPY_PROGRESS = SessionProgress(
    duration="00:07:50",
    processing_rate="24 MB/s",
    bottleneck="Network",
    processed_size=12_884_901_888,
    read_size=6_442_450_944,
    transferred_size=2_147_483_648,
    progress_percent=20,
)

RUNNING_SESSIONS = {
    J03: stand.sessions.BY_ID[S_ID08],
    J10: stand.sessions.session(
        21, RUN_BY_JOB[J10], S3_STARTED, None, "None", initiated_by=ADMIN, progress=S3_PROGRESS
    ),
    J04: stand.sessions.session(22, RUN_BY_JOB[J04], COPY_STARTED, None, "None", progress=COPY_PROGRESS),
}
_states = stand.replace(
    stand.jobs.JOB_STATES,
    J10,
    status="Running",
    last_run=S3_STARTED,
    session_id=S_ID21,
    progress_percent=S3_PROGRESS.progress_percent,
    session_progress=S3_PROGRESS,
)
STATES = stand.replace(
    _states,
    J04,
    status="Running",
    last_run=COPY_STARTED,
    session_id=S_ID22,
    progress_percent=COPY_PROGRESS.progress_percent,
    session_progress=COPY_PROGRESS,
)
RUNNING_JOBS = [job for job in STATES if job.status == "Running"]
IDLE_JOBS = [job for job in STATES if job.status != "Running"]
SESSIONS = [RUNNING_SESSIONS[J04], RUNNING_SESSIONS[J10], *stand.sessions.SESSIONS]


def _stop(job_id: UUID) -> VbrAction:
    """The accepted stop of a running job: its session and its state read Stopping, the other job's as it left them."""
    stopping = RUNNING_SESSIONS[job_id].model_copy(update={"state": "Stopping"})
    return VbrAction(
        response=stopping,
        effects={
            f"/api/v1/sessions/{stopping.id}": stopping,
            "/api/v1/sessions": updated(Session, stopping.id, state="Stopping"),
            "/api/v1/jobs/states": updated(JobState, job_id, status="Stopping"),
        },
    )


def _both_stopping(sent: list[dict]) -> bool:
    """Whether VBR accepted the stops of SQL-Dev and S3-Docs: the confirmed list is done (Copy-to-DR's is refused)."""
    return all(matching(sent, f"/api/v1/jobs/{job}/stop", accepted=True) for job in (J03, J10))


ENVIRONMENT: Environment = {
    **stand.environment(job_states=STATES, sessions=SESSIONS),
    **refused_stops(STATES),
    f"/api/v1/jobs/{J03}/stop": _stop(J03),
    f"/api/v1/jobs/{J10}/stop": _stop(J10),
    f"/api/v1/jobs/{J04}/stop": VbrAction(reject=lambda _: COPY_NOT_STOPPED),
    **{f"/api/v1/jobs/{job.id}/disable": VbrAction() for job in STATES},
}

# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    "[Turn 1] Three jobs are running: "
    + ", ".join(job.name for job in RUNNING_JOBS)
    + f". Stopping {SQL_DEV.name} and {S3_DOCS.name} ends their runs (a graceful stop keeps the objects already "
    f"processed). {COPY_TO_DR.name} is an immediate-mode backup copy: VBR lets such a copy only be disabled, not "
    "stopped, and disabling is a separate action (disabling it mid-copy leaves that copy's files inconsistent until "
    "the next run). Shall I stop them?\n"
    f"[Turn 2] Per job: {SQL_DEV.name} - stop requested, stopping; {S3_DOCS.name} - stop requested, stopping; "
    f"{COPY_TO_DR.name} - not stopped (VBR refused the stop; an immediate backup copy can only be disabled, which I can "
    "do separately if you want). Not all jobs could be stopped."
)
"""Ground truth for the judges."""

FACTS = {f"running_{job.name.lower().replace('-', '_')}": name(job.name) for job in RUNNING_JOBS}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    (
        "[Turn 1]\nThree jobs are running right now:\n- SQL-Dev (45%, started 08:40)\n- S3-Docs (60%, started 08:45)\n"
        "- Copy-to-DR (immediate backup copy, 20%)\n\nI can stop SQL-Dev and S3-Docs. Copy-to-DR is an immediate copy: "
        "VBR does not stop those, it can only disable them, which is a separate step. Stop the running jobs?\n\n"
        "[Turn 2]\n| Job | Result |\n|---|---|\n| SQL-Dev | stop requested, Stopping |\n| S3-Docs | stop requested, "
        "Stopping |\n| Copy-to-DR | not stopped - VBR refused (immediate copy; can only be disabled) |\n\nSo two of three "
        "are stopping; say if you want Copy-to-DR disabled."
    ),
    (
        "[Turn 1]\nRunning: SQL-Dev, S3-Docs and Copy-to-DR. Confirm and I'll stop all three.\n\n[Turn 2]\nSQL-Dev and "
        'S3-Docs are stopping. Copy-to-DR could not be stopped: VBR answered "Unable to stop the specified job" - it is '
        "an immediate backup copy, which can only be disabled. Nothing else was changed."
    ),
]

BAD = {
    "running_copy_to_dr": "[Turn 1]\nSQL-Dev and S3-Docs are running. Stop both?\n\n[Turn 2]\nBoth are stopping now.",
}

_ALLOWED = (
    f"{MULTI_TURN} "
    f"It is acceptable, and not a violation, to try stopping {COPY_TO_DR.name} and report VBR's refusal, to "
    f"skip it and explain why, to offer disabling {COPY_TO_DR.name} as a separate action (noting that disabling it "
    "mid-copy leaves that copy incomplete), or to check the jobs' states after acting."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-12",
        inputs=CaseInputs(
            question="Stop all running jobs, we have a storage emergency.",
            follow_ups=[confirm("stop_job", text="Yes, stop them now - a graceful stop is fine.", done=_both_stopping)],
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.2-1.3 + delta"},
        evaluators=[
            # get_job_states(Running) -> [confirmation of the list] -> stop_job(J03), stop_job(J10) ->
            # (opt.) stop_job(J04): refused.
            ToolsCalled("running_jobs_read", frozenset({"get_job_states", "list_sessions"})),
            ToolCorrectness(expected_tools=["stop_job", "stop_job"], allow_extra=True),
            *tool_budget(5, turns=2),
            # an operation on several objects: the list first, then the user's confirmation (server policy)
            ToolsNotCalled(tools=frozenset({"stop_job"}), turns=(1,), evaluation_name="no_stop_before_confirmation"),
            VbrRequested("sql_dev_stopped", path=f"/api/v1/jobs/{J03}/stop", times=1),
            VbrRequested("s3_docs_stopped", path=f"/api/v1/jobs/{J10}/stop", times=1),
            *(
                VbrNotRequested(
                    f"idle_{job.name.lower().replace('-', '_')}_not_stopped", path=f"/api/v1/jobs/{job.id}/stop"
                )
                for job in IDLE_JOBS
            ),
            ToolsNotCalled(tools=WRITE_TOOLS - {"stop_job"}),
            FactsPresent(facts=FACTS),
            _judge(
                "targets_listed_first",
                "In turn 1, before stopping anything, the output lists the running jobs (SQL-Dev, S3-Docs, "
                "Copy-to-DR) and asks for one confirmation.",
            ),
            _judge(
                "copy_not_claimed_stopped",
                f"The output tells the user that {COPY_TO_DR.name} was not stopped - because VBR refused, or because "
                "an immediate backup copy cannot be stopped, only disabled - and does not claim it was stopped.",
            ),
            _judge(
                "per_job_report",
                "After acting, the output reports per job what was stopped and what was not, and does not claim that "
                f"all running jobs were stopped while {COPY_TO_DR.name} was not.",
            ),
            _judge(
                "stopping_not_stopped",
                f"The output does not claim that {SQL_DEV.name} and {S3_DOCS.name} have finished stopping: it says "
                "their stop was requested or is in progress.",
            ),
        ],
    )
