# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-26 (a): "the SQL backup job" names two jobs - ask which one, start nothing."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case

import stand
from cases import CaseInputs, Environment, judge, tool_budget
from cases.g3.actions import START_ACTIONS
from cases.patterns import name
from evaluators import FactsPresent, ToolsNotCalled, VbrNotRequested
from stand import jobs

# ---- What VBR serves: the base stand (1.2: SQL-Prod and SQL-Dev, SQL-Dev running) and every job's start, accepted as
# VBR would accept it: a request that picked the wrong job would start it.

ENVIRONMENT: Environment = {**stand.environment(), **START_ACTIONS}

SQL_JOBS = [state for state in jobs.JOB_STATES if "SQL" in state.name]  # SQL-Prod, SQL-Dev
SQL_DEV = stand.by_name(jobs.JOB_STATES, "SQL-Dev")

# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    'Two jobs match "SQL": ' + " and ".join(state.name for state in SQL_JOBS) + ". Which one should be started? "
    f"({SQL_DEV.name} is already running.) Nothing has been started."
)
"""Ground truth for the judges."""

FACTS = {f"candidate_{state.name.lower().replace('-', '_')}": name(state.name) for state in SQL_JOBS}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    (
        "There are two SQL jobs: SQL-Prod and SQL-Dev. Which one do you want me to start? (SQL-Dev is already running - "
        "it started at 08:40.)"
    ),
    (
        "I found two matching jobs:\n\n| Job | Status |\n|---|---|\n| SQL-Prod | Stopped (last run failed) |\n| SQL-Dev "
        "| Running, 45% |\n\nSQL-Dev is already running, so did you mean SQL-Prod? I haven't started anything yet."
    ),
]
"""Answers a correct agent could give: every fact must match each."""

BAD = {
    "candidate_sql_dev": "SQL-Prod is the SQL backup job; should I start it?",
    "candidate_sql_prod": "SQL-Dev is the SQL backup job and it is already running.",
}
"""Answers that miss one fact each: the fact must not match its answer."""

_ALLOWED = (
    "It is acceptable, and not a violation, to note that SQL-Dev is already running, to show the two jobs' states or "
    'last results, to try name filters with *, such as *SQL*, or to propose one of the two as a question ("did you '
    'mean SQL-Prod?") as long as nothing is started.'
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-26a",
        inputs=CaseInputs(question="Start the SQL backup job.", environment=ENVIRONMENT),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.2"},
        evaluators=[
            *tool_budget(2),
            ToolsNotCalled(),
            VbrNotRequested("nothing_started", path="/api/v1/jobs/*/start"),
            FactsPresent(facts=FACTS),
            _judge(
                "asks_which",
                "The output asks the user which of the two SQL jobs (SQL-Prod or SQL-Dev) to start. Suggesting one of "
                "them in the form of a question is fine; picking one and starting it, or saying it will start one "
                "without the user's answer, is not.",
            ),
            _judge("nothing_started_claimed", "The output does not claim that any job was started."),
        ],
    )
