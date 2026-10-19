# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-31: stop SQL-Dev with an account that may only look - VBR refuses with 403; say so, no workaround."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case

import stand
from cases import MULTI_TURN, CaseInputs, Environment, confirm, judge, tool_budget
from cases.patterns import NOT_AUTHORIZED
from evaluators import WRITE_TOOLS, Fact, FactsPresent, ToolsNotCalled, VbrRequested
from stand import jobs
from stand.ids import J03
from vbr_mock.markers import VbrError

# ---- What VBR serves: the base stand (1.2: SQL-Dev running at 45%) read by an account with the Veeam Backup Viewer
# role - the delta of the case: it reads every state, and VBR refuses every job action with 403 (swagger: StopJob is
# available to the Veeam Backup Administrator, Veeam Backup Operator and Veeam Tape Operator roles).

DENIED = VbrError(status_code=403, message="Access denied: insufficient permissions to perform this operation.")
STOP_PATH = f"/api/v1/jobs/{J03}/stop"

ENVIRONMENT: Environment = {
    **stand.environment(),
    **{
        f"POST /api/v1/jobs/{state.id}/{action}": DENIED
        for state in jobs.JOB_STATES
        for action in ("start", "stop", "retry", "enable", "disable")
    },
}

SQL_DEV = stand.by_name(jobs.JOB_STATES, "SQL-Dev")

# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    f"[Turn 1] {SQL_DEV.name} is running ({SQL_DEV.progress_percent}%). Stopping it gracefully lets it finish the "
    "current VM. Shall I stop it?\n"
    "[Turn 2] The stop was refused: the VBR account vbr-mcp uses is not authorized to stop jobs (403). Stopping a job "
    "takes the Veeam Backup Administrator, Veeam Backup Operator or Veeam Tape Operator role (or a custom role that "
    f"allows it). {SQL_DEV.name} is still running."
)
"""Ground truth for the judges."""

FACTS = {
    "not_authorized": Fact(NOT_AUTHORIZED, turns=(2,)),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match: turn 2 says why it was refused."""

GOOD = [
    (
        "[Turn 1]\nSQL-Dev is running (45%, started at 08:40). A graceful stop lets it finish the VM it is processing. "
        "Stop it?\n\n[Turn 2]\nI tried, but VBR refused: the account I use is not authorized to stop jobs (403 Access "
        "denied). Stopping jobs needs the Backup Administrator or Backup Operator role. SQL-Dev is still running."
    ),
    (
        "[Turn 1]\nSQL-Dev has a session in progress (45%). Shall I stop it gracefully?\n\n[Turn 2]\nThe stop failed - "
        "insufficient privileges. Ask a VBR admin to stop it, or to grant this account a role that may stop jobs. The job "
        "keeps running."
    ),
]
"""Answers a correct agent could give: every fact must match each."""

BAD = {
    "not_authorized": "[Turn 1]\nSQL-Dev is running. Stop it?\n\n[Turn 2]\nSQL-Dev could not be stopped: VBR returned "
    "an error. Ask your administrator.",
}
"""Answers that miss one fact each: the fact must not match its answer."""

_ALLOWED = (
    f"{MULTI_TURN} "
    "It is acceptable, and not a violation, to advise whom to ask or which role to grant, to name the "
    "Veeam Backup Viewer role as the likely current role, or to mention that a custom role's scope may be the reason."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-31",
        inputs=CaseInputs(
            question="Stop the SQL-Dev job.",
            follow_ups=[confirm("stop_job", text="Yes, stop SQL-Dev.")],
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.2"},
        evaluators=[
            # get_job_states -> [confirmation] -> stop_job(J03) -> 403. A retry loop of the refused stop is
            # NoRepeatedCalls' (run.py adds it to every case).
            *tool_budget(3, turns=2),
            ToolsNotCalled(tools=frozenset({"stop_job"}), turns=(1,), evaluation_name="no_stop_before_confirmation"),
            VbrRequested("stop_attempted", path=STOP_PATH, accepted=False),
            ToolsNotCalled(tools=WRITE_TOOLS - {"stop_job"}, evaluation_name="no_workaround"),
            FactsPresent(facts=FACTS),
            _judge(
                "still_running",
                f"The output says {SQL_DEV.name} was not stopped and is still running, and does not claim it was "
                "stopped or is stopping.",
            ),
            _judge(
                "denied_not_missing",
                "The output presents the failure as the account lacking the rights to stop jobs, not as the job "
                "not being found or VBR being unreachable.",
            ),
        ],
    )
