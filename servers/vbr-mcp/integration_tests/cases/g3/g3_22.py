# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-22: SOBR-Ext-02 into maintenance mode after confirming the consequences, then Ext-02 and Ext-03 out of it."""

from dataclasses import dataclass
from functools import partial
from typing import Any

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext

import stand
from cases import CaseInputs, Environment, confirm, judge, tool_budget
from cases.g3 import sobr
from cases.patterns import near
from evaluators import WRITE_TOOLS, Fact, FactsPresent, ToolsCalled, ToolsNotCalled, VbrNotRequested, VbrRequested
from stand import jobs, repositories
from stand.ids import R05, R06, R07, S01

# ---- What VBR serves: the base stand (1.4-1.5: SOBR-Prod with Ext-01 and Ext-02 Normal, Ext-03 already in
# maintenance; 1.2: SQL-Prod and Test-NewApp write to the SOBR) and SOBR-Prod's extent actions, each changing exactly
# the extents its body names (cases/g3/sobr.py). Nothing runs on Ext-02 at T0, so it goes straight into maintenance.
# Maintenance mode is destructive in vbr-mcp's instructions, and "before an operation on several objects, always list
# them and get the user's confirmation for that list": turn 3 names two extents, so it is confirmed in turn 4.

ENVIRONMENT: Environment = {**stand.environment(), **sobr.environment_routes()}

ENABLE_PATH = sobr.path("enableMaintenanceMode")
_STATES = {state.id: state for state in repositories.REPOSITORY_STATES}
EXT_01, EXT_02, EXT_03 = (_STATES[extent] for extent in (R05, R06, R07))
SOBR_NAME = repositories.SOBR_NAME
SQL_PROD, TEST_NEWAPP = (stand.by_name(jobs.JOB_STATES, name) for name in ("SQL-Prod", "Test-NewApp"))
assert {SQL_PROD.repository_id, TEST_NEWAPP.repository_id} == {S01}


@dataclass
class ExtentsOutOfMaintenance(Evaluator[Any, str, Any]):
    """Assert that after the user confirmed the two extents (turn 4), Ext-02 and Ext-03 were taken out of maintenance.

    In one request or in two: the union of the accepted requests' extents is what counts.
    """

    def evaluate(self, ctx: EvaluatorContext[Any, str, Any]) -> dict[str, EvaluationReason]:
        sent = sobr.sent_extents(ctx, "disableMaintenanceMode", (4,))
        expected = {str(R06), str(R07)}
        return {"ext_02_03_out_of_maintenance": EvaluationReason(value=sent == expected, reason=f"sent {sorted(sent)}")}


# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    f"[Turn 1] {EXT_02.name} is a performance extent of {SOBR_NAME} ({EXT_02.free_gb:.0f} GB free of "
    f"{EXT_02.capacity_gb:.0f} GB). In maintenance mode it takes no new backups, and restores from backup files on it "
    f"- including chains partly stored on it - are unavailable until it leaves maintenance. {SQL_PROD.name} writes to "
    f"{SOBR_NAME}: if its active chain is on {EXT_02.name}, its next run fails, which VBR advises avoiding with a new "
    f"full first ({TEST_NEWAPP.name} has never run, so it has no chain there and simply lands on another extent). "
    f"{EXT_03.name} is already in maintenance, so only {EXT_01.name} ({EXT_01.free_gb:.0f} GB free) is left for new "
    "backups. An extent busy with a task goes Pending first. Confirm?\n"
    f"[Turn 2] {EXT_02.name} is going into maintenance mode (re-read: Maintenance).\n"
    f"[Turn 3] Both {EXT_02.name} and {EXT_03.name} would be taken out of maintenance mode, taking new backups and "
    "serving restores again. Confirm taking both out?\n"
    "[Turn 4] Both are being taken out of maintenance mode (re-read: Normal)."
)
"""Ground truth for the judges."""


FACTS = {
    "restores_blocked": Fact(sobr.RESTORE_BLOCKED, turns=(1,)),
    "ext_03_in_maintenance": Fact(near(sobr.extent(3), r"maintenance"), turns=(1,)),
    "only_ext_01_left": Fact(near(sobr.extent(1), sobr.ONLY), turns=(1,)),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match: turn 1 names what maintenance costs."""

GOOD = [
    (
        "[Turn 1]\nSOBR-Ext-02 is a performance extent of SOBR-Prod with 300 GB free. Before I put it into maintenance "
        "mode, note what it does:\n- No new backups are written to it, and restores from backup files on SOBR-Ext-02 (or "
        "chains partly stored on it) are unavailable until it leaves maintenance.\n- SQL-Prod writes to SOBR-Prod: if its "
        "active chain sits on Ext-02, its next run will fail. Veeam suggests running an active full first.\n- SOBR-Ext-03 "
        "is already in maintenance, so only SOBR-Ext-01 (2,500 GB free) would be left for new backups.\n\nShall I put "
        "SOBR-Ext-02 into maintenance mode?\n\n[Turn 2]\nDone - SOBR-Ext-02 is now in maintenance mode. You can replace "
        "the disk.\n\n[Turn 3]\nI'll take these two out of maintenance mode: SOBR-Ext-02 and SOBR-Ext-03. OK?\n\n"
        "[Turn 4]\nI've taken SOBR-Ext-02 and SOBR-Ext-03 out of maintenance mode; both now show Normal."
    ),
    (
        "[Turn 1]\n| Extent | Status | Free |\n|---|---|---|\n| SOBR-Ext-01 | Normal | 2.5 TB |\n| SOBR-Ext-02 | Normal | "
        "300 GB |\n| SOBR-Ext-03 | Maintenance | 3.9 TB |\n\nPutting **SOBR-Ext-02** into maintenance means you cannot "
        "restore from the backups stored on it while it is in that mode, and a job whose active chain is on it (SQL-Prod) "
        "may fail on its next run. Ext-03 is already in maintenance mode, so Ext-01 remains the only extent for new "
        "backups. Confirm and I'll switch it.\n\n[Turn 2]\nSOBR-Ext-02 has been switched to maintenance mode.\n\n"
        "[Turn 3]\nTo confirm: take SOBR-Ext-02 and SOBR-Ext-03 out of maintenance mode?\n\n[Turn 4]\nBoth SOBR-Ext-02 "
        "and SOBR-Ext-03 are out of maintenance mode now."
    ),
]
"""Answers a correct agent could give: every fact must match each."""

BAD = {
    "restores_blocked": "[Turn 1]\nIn maintenance mode SOBR-Ext-02 stops taking new backups; restores will not be "
    "affected. SOBR-Ext-03 is already in maintenance, so only SOBR-Ext-01 is left. Confirm?\n\n[Turn 2]\nDone.",
    "ext_03_in_maintenance": "[Turn 1]\nRestores from SOBR-Ext-02 become unavailable, and SOBR-Ext-01 will be the "
    "only extent left. Confirm?\n\n[Turn 2]\nDone.\n\n[Turn 3]\nSOBR-Ext-02 and SOBR-Ext-03 are out of maintenance.",
    "only_ext_01_left": "[Turn 1]\nWhile SOBR-Ext-02 is in maintenance you can't restore from it. SOBR-Ext-03 is in "
    "maintenance too. Confirm?\n\n[Turn 2]\nDone.",
}
"""Answers that miss one fact each: the fact must not match its answer."""

_ALLOWED = (
    "The output holds every turn's answer, each headed [Turn N]; a turn the agent did not need is marked as not "
    "asked, and the last turn may acknowledge or re-check what was already done. It is acceptable, and not a "
    "violation, to keep turn 3 to a short list of the two extents and a question; to look up the jobs that write to "
    "SOBR-Prod; to mention Ext-01's free space or the extents' state after each change; or to say a busy extent would "
    "go Pending first."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-22",
        inputs=CaseInputs(
            question="Put SOBR-Ext-02 into maintenance mode, we need to replace a disk.",
            follow_ups=[
                confirm("set_sobr_extent_maintenance_mode", text="Yes, put SOBR-Ext-02 into maintenance mode."),
                "Disk replaced. Take it out of maintenance — and Ext-03 too.",
                # the confirmation of the two extents; skipped only once both are out (an agent that acted in turn 3
                # failed already), so one that took out one and asks about the other gets its answer
                confirm(
                    "set_sobr_extent_maintenance_mode",
                    text="Yes, take both of them out of maintenance mode.",
                    done=lambda sent: sobr.extents_in(sent, "disableMaintenanceMode") >= {str(R06), str(R07)},
                ),
            ],
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.4, 1.5"},
        evaluators=[
            # list_scale_out_repositories (or the SOBR id from list_repositories) -> (opt.) list_repositories,
            # get_job_states -> [confirmation] -> maintenance on (R06) -> (opt.) re-read; turn 3: the two extents ->
            # [confirmation] -> off (R06, R07).
            ToolsCalled("found_the_sobr", frozenset({"list_scale_out_repositories", "list_repositories"})),
            *tool_budget(6, turns=4),
            ToolsNotCalled(
                tools=frozenset({"set_sobr_extent_maintenance_mode"}),
                turns=(1, 3),
                evaluation_name="no_maintenance_change_before_confirmation",
            ),
            VbrRequested("ext_02_into_maintenance", path=ENABLE_PATH, body={"repositoryIds": [R06]}, times=1),
            ExtentsOutOfMaintenance(),
            *sobr.id_mixups(),
            VbrNotRequested("no_sealed_mode", path=f"{sobr.SOBR_PATH}/*/*SealedMode"),
            ToolsNotCalled(tools=WRITE_TOOLS - {"set_sobr_extent_maintenance_mode"}),
            FactsPresent(facts=FACTS),
            _judge(
                "consequences_before_confirmation",
                "In turn 1, before anything is changed, the output asks for confirmation and names the consequences: "
                f"restores from data on {EXT_02.name} become unavailable, and jobs writing to {SOBR_NAME} (such as "
                f"{SQL_PROD.name}; naming it is welcome) may fail if their active chain is on that extent.",
            ),
            _judge(
                "only_ext_01_left",
                f"In turn 1 the output points out that {EXT_03.name} is already in maintenance, so only "
                f"{EXT_01.name} remains for new backups.",
            ),
            _judge(
                "no_invented_placement",
                "The output does not claim to know which specific backups or restore points are stored on "
                f"{EXT_02.name}: the API does not tell. Saying that a job's chain may be there is fine.",
            ),
        ],
    )
