# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-11 (b): stop SQL-Dev immediately, as asked, and say that this run leaves no restore point."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

import stand
from cases import MULTI_TURN, CaseInputs, Environment, confirm, judge, tool_budget
from cases.g3.actions import refused_stops
from cases.patterns import any_of, name
from evaluators import WRITE_TOOLS, FactsPresent, ToolsNotCalled, VbrRequested
from stand.ids import J03, S_ID07, S_ID08
from vbr_mock.markers import VbrAction

# ---- What VBR serves: the base stand, where SQL-Dev runs (started by hand at 08:40, 45% done; its scheduled run of
# 02:00 made the latest restore point of sql-dev-01), and the stop actions. SQL-Dev's stop is accepted: VBR answers
# with the session it stops, and the job and the session read Stopping from then on. Every other job is not running,
# and VBR refuses to stop it.

"""What VBR answers a stop of a job that is not running (JobsControllerImpl, test plan 0.3)."""

SQL_DEV = stand.by_name(stand.jobs.JOB_STATES, "SQL-Dev")
SQL_DEV_VM = "sql-dev-01"
LAST_NIGHT = stand.sessions.BY_ID[S_ID07]
LATEST_POINT = stand.protected.points_of(SQL_DEV_VM)[0]
RUNNING = stand.sessions.BY_ID[S_ID08]
STOPPING = RUNNING.model_copy(update={"state": "Stopping"})
STOP_PATH = f"/api/v1/jobs/{J03}/stop"

ENVIRONMENT: Environment = {
    **stand.environment(),
    **refused_stops(stand.jobs.JOB_STATES),
    STOP_PATH: VbrAction(
        response=STOPPING,
        effects={
            "/api/v1/jobs/states": stand.replace(stand.jobs.JOB_STATES, J03, status="Stopping"),
            "/api/v1/sessions": stand.replace(stand.sessions.SESSIONS, S_ID08, state="Stopping"),
            f"/api/v1/sessions/{S_ID08}": STOPPING,
        },
    ),
}

# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    f"An immediate stop of {SQL_DEV.name} has been requested, as asked; the job is stopping. Aborting the run means "
    f"no new restore point of {SQL_DEV_VM} comes from it: the latest one stays the one from tonight's scheduled run "
    f"({LATEST_POINT.creation_time:%Y-%m-%d %H:%M}), and the session ends as failed. Its state can be checked to "
    "confirm it has stopped. (Asking once more before stopping is fine too: the request already confirmed the "
    "immediate stop of the one running job.)"
)
"""Ground truth for the judges."""

NO_NEW_POINT = any_of(
    r"\b(no|without|won'?t|will\s+not|not\s+(get|be|have|produce|create|leave)|never)\b[^.\n]{0,60}"
    r"\b(restore\s+point|backup|point)",
    r"\b(restore\s+point|backup|point|data|progress)\b[^.\n]{0,60}"
    r"\b(discarded|abandoned|lost|thrown\s+away|not\s+(be\s+)?(kept|saved|created|made|completed|finished|finalized))",
    # "the previous point stays the latest", "the latest one stays the one from tonight's run"
    r"\b(previous|last|existing|earlier)\s+(good\s+)?(restore\s+)?(point|one|backup)\b[^.\n]{0,40}"
    r"\b(stays?|remains?|is\s+still|will\s+(still\s+)?be)\b[^.\n]{0,30}\b(latest|newest|most\s+recent|last)\b",
    r"\b(latest|newest|most\s+recent|last\s+good)\s+(restore\s+)?(point|one|backup)\b[^.\n]{0,20}"
    r"\b(stays?|remains?|is\s+still|will\s+(still\s+)?be)\b",
    r"\b(discard|abandon|lose|lost|throw\w*\s+away)\w*\b[^.\n]{0,40}\b(run|session|progress|data|vm|work|point)",
)

FACTS = {
    "job": name(SQL_DEV.name),
    "no_new_point": NO_NEW_POINT,
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    (
        "[Turn 1]\nI've requested an immediate stop of SQL-Dev (graceful stop off). It is now Stopping. Since the run is aborted, "
        "sql-dev-01 will not get a new restore point from it - the latest one stays the 02:15 point from the scheduled "
        "run, and this session will end as Failed.\n\n[Turn 2]\n(not asked: the agent already called stop_job)"
    ),
    (
        "[Turn 1]\nSQL-Dev is running (45%, started 08:40). Killing it immediately aborts the run: whatever it processed "
        "so far is discarded, there will be no restore point from this session, and it ends as failed. Your last good "
        "point is 2026-10-07 02:15. Stop it now?\n\n[Turn 2]\nImmediate stop requested for SQL-Dev; it is stopping."
    ),
    (
        "[Turn 1]\nImmediate stop of SQL-Dev requested - it is stopping. The restore point it was writing is not "
        "completed, so the previous point (2026-10-07 02:15) stays the latest one for sql-dev-01.\n\n[Turn 2]\n"
        "(not asked: the agent already called stop_job)"
    ),
    (
        "[Turn 1]\nDone: the stop of SQL-Dev is requested, without waiting for the VM. Its latest restore point "
        "stays the one from the 02:00 run.\n\n[Turn 2]\n(not asked: the agent already called stop_job)"
    ),
]

BAD = {
    "no_new_point": "Done: SQL-Dev was stopped immediately as you asked. It is stopping now.",
}

_ALLOWED = (
    f"{MULTI_TURN} "
    "It is acceptable, and not a violation, to stop the job right away (the request already confirms an "
    "immediate stop of the one running job) or to confirm once more first, to give the time of "
    f"{SQL_DEV_VM}'s latest restore point as 02:15 or 02:16 or to leave it out, to say the session will end as failed "
    "or canceled, or to check the job's state after requesting the stop."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-11b",
        inputs=CaseInputs(
            question="Kill SQL-Dev immediately, don't wait for the VM to finish.",
            # asked only if the agent confirms first, which the request makes unnecessary but is not wrong
            follow_ups=[confirm("stop_job", text="Yes, stop it now, don't wait.")],
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.2-1.3"},
        evaluators=[
            # get_job_states finds SQL-Dev running -> stop_job(graceful_stop=False), in turn 1 or after confirming.
            ToolCorrectness(expected_tools=["stop_job"], allow_extra=True),
            *tool_budget(3, turns=2),
            VbrRequested("immediate_stop", path=STOP_PATH, body={"gracefulStop": False}, times=1),
            VbrRequested("only_sql_dev_stopped", path="/api/v1/jobs/*/stop", accepted=False, times=1),
            ToolsNotCalled(tools=WRITE_TOOLS - {"stop_job"}),
            FactsPresent(facts=FACTS),
            _judge(
                "no_point_warned",
                f"The output says that the immediate stop leaves no new restore point of the VM being processed (e.g. "
                f"{SQL_DEV_VM}) from this run - e.g. that the current restore point is not completed, or that the "
                "previous point stays the latest; it may say so before or after requesting the stop.",
            ),
            _judge(
                "stopping_not_stopped",
                f"After the stop is requested, the output does not claim that {SQL_DEV.name} has already stopped: it "
                "says the stop was requested or is in progress (or reports the Stopping state).",
            ),
        ],
    )
