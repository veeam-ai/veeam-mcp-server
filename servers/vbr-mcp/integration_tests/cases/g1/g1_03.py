# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G1-03: which jobs failed on their last run."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import CaseInputs, judge, tool_budget
from cases.patterns import any_of, clock, day, name
from evaluators import FactsPresent, ToolsNotCalled
from stand import environment
from stand.ids import T0
from stand.jobs import JOB_STATES
from stand.sessions import BY_ID

# ---- What VBR serves: the base stand. SQL-Prod's run of 00:00 failed and so did its two automatic retries; two jobs
# ended with Warning, Test-NewApp never ran, Legacy-Archive is disabled. Idle jobs read Stopped, as VBR 13 reports them.

ENVIRONMENT = environment()

# ---- What a correct answer says, derived from the stand.

_FAILED = next(state for state in JOB_STATES if state.last_result == "Failed")
assert _FAILED.last_run is not None and _FAILED.session_id is not None
_FAILED_RUN = _FAILED.last_run  # when the run began (00:00:04); its last attempt is the job's sessionId
_LAST_ATTEMPT = BY_ID[_FAILED.session_id].creation_time  # 00:46:05
_WARNING = [state.name for state in JOB_STATES if state.last_result == "Warning"]
_NEVER_RUN = next(state for state in JOB_STATES if state.last_result == "None" and state.status != "Running")
_DISABLED = next(state for state in JOB_STATES if state.status == "Disabled")

EXPECTED = (
    f"Only one job failed on its last run: {_FAILED.name}, whose run of today ({_FAILED_RUN:%Y-%m-%d}) at "
    f"{_FAILED_RUN:%H:%M} failed, its automatic retries too (the last attempt at {_LAST_ATTEMPT:%H:%M}). "
    f"{' and '.join(_WARNING)} ended their last runs with Warning, which is not a failure. {_NEVER_RUN.name} has never "
    f"run (last result None). {_DISABLED.name} is disabled and its last run succeeded. Every other job's last run "
    "succeeded; their status Stopped means idle after the run, not stopped by anyone."
)
"""Ground truth for the judges."""

FACTS = {
    "job": name(_FAILED.name),
    "result": r"\bfail",
    # the last run: its start ("00:00", "12:00 AM", "midnight"), its last attempt, or its day
    "last_run": any_of(
        clock(_FAILED_RUN),
        clock(_LAST_ATTEMPT),
        day(T0, weekday=False),
        r"\b(?:today|tonight|last\s+night|this\s+morning|overnight)\b",
    ),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

_ALLOWED = (
    f"It is acceptable, and not a violation, to mention {' and '.join(_WARNING)} separately as jobs whose last run "
    f"ended with a warning, to mention that {_NEVER_RUN.name} has not run yet and that {_DISABLED.name} is disabled, "
    f"to mention the retries of {_FAILED.name}'s run, or to offer to look into why it failed."
)

GOOD = [
    (
        "Only **SQL-Prod** failed on its last run (today at 00:00; the two automatic retries at 00:31 and 00:46 failed "
        "too). Copy-to-DR and Agent-Laptops ended with warnings, which are not failures. Test-NewApp has never run, and "
        "Legacy-Archive is disabled."
    ),
    (
        "| Job | Last result | Last run |\n|---|---|---|\n| SQL-Prod | Failed | 2026-10-07 00:00 |\n\nEvery other job's "
        "last run succeeded or ended with a warning."
    ),
    (
        "Just one: SQL-Prod - the run that started at midnight failed. The rest are fine (two warnings: Copy-to-DR, "
        "Agent-Laptops)."
    ),
]

BAD = {
    "job": "No job failed on its last run today; Copy-to-DR and Agent-Laptops only had warnings.",
    "result": "SQL-Prod's last run, today at 00:00, ended with errors.",
    "last_run": "SQL-Prod failed.",
}
"""Answers that each miss one fact."""


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G1-03",
        inputs=CaseInputs(question="Which jobs failed on their last run?", environment=ENVIRONMENT),
        expected_output=EXPECTED,
        metadata={"group": "G1", "base_stand": "1.2"},
        evaluators=[
            # get_job_states, filtered by VBR or by the agent; get_server_status (what "today" is) is a read the
            # case allows on top of it.
            ToolCorrectness(expected_tools=["get_job_states"], allow_extra=True),
            *tool_budget(2),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "only_sql_prod_failed",
                f"The output names {_FAILED.name} as the only job whose last run failed, and does not count any "
                "other job as failed.",
            ),
            _judge(
                "never_run_is_not_failed",
                f"The output does not count {_NEVER_RUN.name} as failed: its last result is None because it has "
                "never run.",
            ),
            _judge(
                "disabled_is_not_failed",
                f"The output does not count {_DISABLED.name} as failed: it is disabled and its last run succeeded.",
            ),
            _judge(
                "warning_is_not_failed",
                f"The output does not count {' or '.join(_WARNING)} as failed: their last runs ended with Warning, "
                "which is not Failed. Mentioning them separately as warnings is fine.",
            ),
            _judge(
                "stopped_is_idle",
                "The output does not treat a job's status Stopped as a failure or as a sign that someone stopped "
                "it: it is how VBR reports a job that is idle after its last run.",
            ),
        ],
    )
