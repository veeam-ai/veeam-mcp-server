# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G1-17: when the latest restore point of sql-prod-01 was created."""

from datetime import timedelta
from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case

from cases import CaseInputs, Environment, judge, tool_budget
from cases.patterns import clock, day
from evaluators import RESTORE_POINT_READS, FactsPresent, ToolsCalled, ToolsNotCalled
from stand import environment, protected
from stand.ids import T0

# ---- What VBR serves: the base stand. sql-prod-01's newest restore point (1.8) is of 2026-10-06 00:14: tonight's
# SQL-Prod run (2026-10-07 00:00) and both its retries failed on that VM (guest processing, Win32 1326), while
# sql-prod-02 did get a point at 00:10. vbr-mcp lists an object's points newest first.

ENVIRONMENT: Environment = environment()

# ---- What a correct answer says, derived from the data above.

POINTS = protected.points_of("sql-prod-01")
LATEST, OLDEST = POINTS[0], POINTS[-1]
_SQL_PROD_02_LATEST = protected.points_of("sql-prod-02")[0]
_HOURS_AGO = round((T0 - LATEST.creation_time) / timedelta(hours=1))
_SQL_PROD_02_AT = f"{_SQL_PROD_02_LATEST.creation_time:%Y-%m-%d %H:%M}"

EXPECTED = (
    f"The latest restore point of sql-prod-01 was created on {LATEST.creation_time:%Y-%m-%d} at "
    f"{LATEST.creation_time:%H:%M}, about {_HOURS_AGO} hours ago. Tonight's SQL-Prod run (2026-10-07 00:00) did not "
    f"process the VM (its last run failed), so there is no newer point. The {_SQL_PROD_02_AT} point belongs to "
    "sql-prod-02, not to sql-prod-01."
)
"""Ground truth for the judges."""

FACTS = {
    "date": day(LATEST.creation_time),
    "time": clock(LATEST.creation_time),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

_ALLOWED = (
    "It is acceptable, and not a violation, to give the point's age in hours, to mention that the SQL-Prod job's "
    "last run failed for this VM (and why), or to offer to look into it."
)

GOOD = [
    (
        "The latest restore point of sql-prod-01 is from 2026-10-06 at 00:14 (about 33 hours ago). Tonight's SQL-Prod "
        "run failed for this VM, so there is nothing newer."
    ),
    (
        "sql-prod-01's newest point was created on Oct 6th, 12:14 AM. Last night's run (Oct 7, 00:00) did not produce a "
        "point for it - the job failed on that VM."
    ),
    "| VM | Latest restore point |\n|---|---|\n| sql-prod-01 | 6 Oct 2026 00:14:22 |",
]
"""Answers a correct agent could give: every fact must match each of them."""

BAD = {
    "date": "The latest restore point of sql-prod-01 was created on 2026-10-07 at 00:14.",
    "time": "sql-prod-01's latest restore point is from 2026-10-06 00:00, when SQL-Prod started.",
}
"""Per fact, an answer that gets that fact wrong: the fact must not match it."""


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G1-17",
        inputs=CaseInputs(
            question="When was the latest restore point of sql-prod-01 created?",
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G1", "base_stand": "1.8"},
        evaluators=[
            # list_protected_objects -> list_restore_points, list_restore_points alone, or list_protected_objects(id)
            # alone: any of them reads the point.
            ToolsCalled("points_read", RESTORE_POINT_READS),
            *tool_budget(3),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "not_sql_prod_02_point",
                f"The output does not give {_SQL_PROD_02_AT} (a point of sql-prod-02) as the time of the latest "
                "restore point of sql-prod-01.",
            ),
            _judge(
                "not_oldest_point",
                f"The output does not give the oldest restore point of sql-prod-01 "
                f"({OLDEST.creation_time:%Y-%m-%d %H:%M}) as its latest one.",
            ),
            _judge(
                "point_not_job_start",
                "The output does not present a job's start time (such as tonight's 00:00 run) as the creation "
                "time of the latest restore point.",
            ),
        ],
    )
