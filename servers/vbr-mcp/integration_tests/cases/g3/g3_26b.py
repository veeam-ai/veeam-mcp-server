# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-26 (b): start a job that does not exist - say so, start nothing."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case

import stand
from cases import CaseInputs, Environment, judge, tool_budget
from cases.g3.actions import START_ACTIONS
from cases.patterns import NOT_FOUND
from evaluators import FactsPresent, ToolsNotCalled, VbrNotRequested
from stand import jobs

# ---- What VBR serves: the base stand (1.2: ten jobs, none called TotallyMissingJob123) and every job's start, accepted
# as VBR would accept it: starting some other job instead would start it.

ENVIRONMENT: Environment = {**stand.environment(), **START_ACTIONS}

MISSING = "TotallyMissingJob123"

# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    f"There is no job called {MISSING} on this server, so nothing was started. The existing jobs are "
    + ", ".join(state.name for state in jobs.JOB_STATES)
    + "."
)
"""Ground truth for the judges."""

FACTS = {"not_found": NOT_FOUND}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    (
        f"I couldn't find a job named {MISSING} - nothing was started. Your jobs are: Daily-VMs, SQL-Prod, SQL-Dev, "
        "Copy-to-DR, NAS-Finance, Agent-Laptops, Legacy-Archive, Reports-VM, Test-NewApp and S3-Docs."
    ),
    (
        f"There is no job called {MISSING} on this VBR server, so I did not start anything. Did you mean one of the "
        "existing jobs, such as SQL-Prod or Daily-VMs?"
    ),
    f"{MISSING} does not exist on this server. Nothing has been started.",
    f"I can't find a job called {MISSING}, so I haven't started anything.",
    f"{MISSING} isn't one of the jobs on this server (Daily-VMs, SQL-Prod, SQL-Dev, ...). Nothing was started.",
]
"""Answers a correct agent could give: every fact must match each."""

BAD = {"not_found": f"Done! The job is running now. I started {MISSING} at 09:00 and will keep an eye on it."}
"""Answers that miss one fact each: the fact must not match its answer."""

_ALLOWED = (
    "It is acceptable, and not a violation, to list the existing jobs or suggest similar names, or to try name "
    "filters with *."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-26b",
        inputs=CaseInputs(question=f"Start the job called {MISSING}.", environment=ENVIRONMENT),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.2"},
        evaluators=[
            *tool_budget(2),
            ToolsNotCalled(),
            VbrNotRequested("nothing_started", path="/api/v1/jobs/*/start"),
            FactsPresent(facts=FACTS),
            _judge(
                "reports_missing",
                f"The output says that no job called {MISSING} exists, and does not claim that any job was started.",
            ),
        ],
    )
