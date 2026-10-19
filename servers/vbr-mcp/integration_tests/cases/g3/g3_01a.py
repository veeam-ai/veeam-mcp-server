# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-01 (a): start the Daily-VMs job now, with the start options left at their defaults."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import CaseInputs, Environment, judge, tool_budget
from cases.patterns import STARTED, name
from evaluators import WRITE_TOOLS, FactsPresent, ToolsNotCalled, VbrNotRequested, VbrRequested
from stand import by_name, environment, replace
from stand.ids import FIRST_G3_SESSION, J01, S_ID20, T0
from stand.jobs import JOB_STATES
from stand.sessions import RUN_BY_JOB, SESSIONS, started
from vbr_mock.markers import VbrAction
from vbr_models.sessions import SessionProgress

# ---- What VBR serves: the base stand, and the start of Daily-VMs, which VBR answers with the session it starts. From
# then on the job reads as starting (swagger JobStatesResultExample: a run that has just begun reports no rate yet).

DAILY_VMS = by_name(JOB_STATES, "Daily-VMs")
REPORTS_VM = by_name(JOB_STATES, "Reports-VM")
COPY_TO_DR = by_name(JOB_STATES, "Copy-to-DR")
START_PATH = f"/api/v1/jobs/{J01}/start"

STARTED_SESSION = started(FIRST_G3_SESSION, RUN_BY_JOB[J01])

STATES_AFTER_START = replace(
    JOB_STATES,
    J01,
    status="Starting",
    last_run=T0,
    session_id=S_ID20,
    progress_percent=0,
    session_progress=SessionProgress(
        duration="00:00:04",
        processing_rate="N/A",
        bottleneck="NotDefined",
        processed_size=0,
        read_size=0,
        transferred_size=0,
        progress_percent=0,
    ),
)

ENVIRONMENT: Environment = environment() | {
    START_PATH: VbrAction(
        response=STARTED_SESSION,
        effects={
            "/api/v1/jobs/states": STATES_AFTER_START,
            "/api/v1/sessions": [STARTED_SESSION, *SESSIONS],
            f"/api/v1/sessions/{S_ID20}": STARTED_SESSION,
        },
    ),
}

# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    f"{DAILY_VMS.name} was idle (its last run, last night at 22:00, succeeded), so it has been started now with the "
    "default options: an ordinary incremental run (its synthetic full is on Saturdays; today is Wednesday), no active "
    "full, chained jobs not started. The run has been started, not finished: its progress can be checked with the "
    f"job's state or session. The chained job {REPORTS_VM.name} does not start by itself after a manual start "
    f"without start_chained_jobs; {COPY_TO_DR.name}, an immediate backup copy, copies the new restore point once the "
    "run makes it."
)
"""Ground truth for the judges."""

FACTS = {
    "job": name(DAILY_VMS.name),
    "started": STARTED,
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    (
        f"Done: I started **{DAILY_VMS.name}** (id {J01}). It was idle - last run 2026-10-06 22:00, Success - so this is "
        "a normal incremental run: no active full, and chained jobs such as Reports-VM were not started. It shows as "
        "Starting now; the backup itself is not finished yet. Want me to check its progress in a while?"
    ),
    (
        f"{DAILY_VMS.name} has been kicked off with the default options (incremental). It's starting now - I'll be able "
        "to tell you how it went once the session completes."
    ),
    (
        f"| Job | Action | State |\n|---|---|---|\n| {DAILY_VMS.name} | started, default options (no active full, no "
        "chained jobs) | Starting |\n\nThe run is underway, not complete."
    ),
]
"""Answers a correct agent could give: every fact must match each."""

BAD = {
    "started": f"I can start {DAILY_VMS.name} for you with the default options. Shall I go ahead?",
    "job": "The job you asked for is running now; I will report back when it finishes.",
}
"""Fact -> an answer that misses it."""

_ALLOWED = (
    f"It is acceptable, and not a violation, to mention that the chained job {REPORTS_VM.name} does not start by itself "
    f"after a manual start unless chained jobs are started too, that {COPY_TO_DR.name} will copy the new restore point, "
    "to report the job as Starting after checking its state, or to offer to check the progress later."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-01a",
        inputs=CaseInputs(question="Start the Daily-VMs backup job now.", environment=ENVIRONMENT),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.2"},
        evaluators=[
            # get_job_states or list_jobs finds the job -> start_job; a state check after it is optional.
            ToolCorrectness(expected_tools=["start_job"], allow_extra=True),
            *tool_budget(3),
            VbrRequested(
                "started_with_defaults",
                path=START_PATH,
                body={"performActiveFull": False, "startChainedJobs": False},
                times=1,
            ),
            VbrRequested("one_job_started", path="/api/v1/jobs/*/start", accepted=False, times=1),
            VbrNotRequested("no_other_job_started", path="/api/v1/jobs/*/start", besides=(START_PATH,)),
            ToolsNotCalled(tools=WRITE_TOOLS - {"start_job"}),
            FactsPresent(facts=FACTS),
            _judge(
                "started_not_finished",
                f"The output says {DAILY_VMS.name} has been started (or is starting), and does not claim that the "
                "backup has completed, succeeded or produced a restore point.",
            ),
            _judge(
                "no_active_full_claimed",
                "The output does not say that an active full backup was started, nor that the chained jobs were "
                "started along with it.",
            ),
        ],
    )
