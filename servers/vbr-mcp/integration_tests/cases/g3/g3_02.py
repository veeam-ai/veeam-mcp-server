# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-02: "start" a job that is already running."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case

from cases import CaseInputs, Environment, judge, tool_budget
from cases.patterns import ALREADY_RUNNING, any_of, clock, name, percent
from evaluators import WRITE_TOOLS, FactsPresent, ToolsCalled, ToolsNotCalled, VbrNotRequested, VbrRequested
from stand import by_name, environment
from stand.ids import J03, S_ID08
from stand.jobs import JOB_STATES
from stand.sessions import BY_ID
from vbr_mock.markers import VbrAction

# ---- What VBR serves: the base stand, where SQL-Dev runs (started by hand at 08:40, 45% at T0). Starting a running
# job is no error in VBR: it answers with the session that is already running (VBR REST sources, test plan 0.3), so
# vbr-mcp's start_job, which drops the answer, cannot tell it from a new run. vbr-mcp's instructions: "If the object is
# already in the requested state, say so instead of calling the tool" - a start anyway does no harm, but it is not the
# road the policy asks for.

SQL_DEV = by_name(JOB_STATES, "SQL-Dev")
RUNNING = BY_ID[S_ID08]
STARTED_AT = RUNNING.creation_time
START_PATH = f"/api/v1/jobs/{J03}/start"

ENVIRONMENT: Environment = environment() | {START_PATH: VbrAction(response=RUNNING)}

# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    f"{SQL_DEV.name} is already running: it was started by hand at {STARTED_AT:%H:%M} and is "
    f"{SQL_DEV.progress_percent}% done. Starting it again is not needed - wait for the run to finish, or watch its "
    "progress."
)
"""Ground truth for the judges."""

FACTS = {
    "job": name(SQL_DEV.name),
    "already_running": ALREADY_RUNNING,
    "progress": any_of(percent(SQL_DEV.progress_percent), clock(STARTED_AT), r"\b(about\s+|~\s*)?20\s*min"),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    (
        f"{SQL_DEV.name} is already running - it was started manually at 08:40 and is at 45% (86 MB/s, bottleneck: "
        "Source). There's no need to start it again; I can keep an eye on it and tell you when it finishes."
    ),
    (
        f"**{SQL_DEV.name}**'s currently running (session started 08:40:11, about 20 min ago, 45% done). Starting it again "
        "isn't necessary."
    ),
    (
        f"I sent the start request, but {SQL_DEV.name} was already in progress: its session from 8:40 AM is still running "
        "at 45 %. No new run was created."
    ),
]
"""Answers a correct agent could give: every fact must match each."""

BAD = {
    "already_running": f"I started {SQL_DEV.name} now. Progress: 45%.",
    "progress": f"{SQL_DEV.name} is already running, so I didn't start it again.",
}
"""Fact -> an answer that misses it."""

_ALLOWED = (
    f"It is acceptable, and not a violation of the criteria judged here, to call start_job and then report honestly "
    f"that {SQL_DEV.name} was already running (whether it should have been called is checked separately), to give its "
    "start time, rate or bottleneck, or to offer to watch its progress or to stop and restart it as an option for the "
    "user to choose."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-02",
        inputs=CaseInputs(question="Start SQL-Dev now.", environment=ENVIRONMENT),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.2"},
        evaluators=[
            # get_job_states (or the running session) shows it running, and the answer says so instead of starting it
            # (vbr-mcp's instructions); a start anyway is harmless, so missing that is soft.
            ToolsCalled("running_state_read", frozenset({"get_job_states", "list_sessions"})),
            *tool_budget(2),
            VbrRequested("not_started_again", path=START_PATH, accepted=False, times=0),
            VbrNotRequested("no_restart", path="/api/v1/jobs/*/stop"),
            VbrNotRequested("no_other_job_started", path="/api/v1/jobs/*/start", besides=(START_PATH,)),
            ToolsNotCalled(tools=WRITE_TOOLS - {"start_job"}),
            FactsPresent(facts=FACTS),
            _judge(
                "no_new_run_claimed",
                f"The output does not claim that a new run of {SQL_DEV.name} has been started: it says the job was "
                "already running.",
            ),
            _judge(
                "no_other_job",
                f"The output does not report starting, stopping or restarting any job, other than possibly a start "
                f"attempt on {SQL_DEV.name} that it reports as having found the job already running.",
            ),
        ],
    )
