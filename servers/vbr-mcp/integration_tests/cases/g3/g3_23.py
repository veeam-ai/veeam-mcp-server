# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-23: seal SOBR-Ext-02 to retire it, after naming what sealing does and what it costs Ext-01."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case

import stand
from cases import MULTI_TURN, CaseInputs, Environment, confirm, judge, tool_budget
from cases.g3 import sobr
from cases.patterns import any_of
from evaluators import WRITE_TOOLS, Fact, FactsPresent, ToolsCalled, ToolsNotCalled, VbrNotRequested, VbrRequested
from stand import jobs, repositories
from stand.ids import R05, R06, R07

# ---- What VBR serves: the base stand (1.4-1.5: SOBR-Prod, Ext-03 already in maintenance; 1.2: SQL-Prod writes to it)
# and SOBR-Prod's extent actions, each changing exactly the extents its body names (cases/g3/sobr.py).

ENVIRONMENT: Environment = {**stand.environment(), **sobr.environment_routes()}

SEAL_PATH = sobr.path("enableSealedMode")
_STATES = {state.id: state for state in repositories.REPOSITORY_STATES}
EXT_01, EXT_02, EXT_03 = (_STATES[extent] for extent in (R05, R06, R07))
SQL_PROD = stand.by_name(jobs.JOB_STATES, "SQL-Prod")

# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    f"[Turn 1] Sealing {EXT_02.name} stops new backups going to it; restores, merges and deletions from it keep "
    "working, and retention removes its restore points over time. A job whose active backup chain is on "
    f"{EXT_02.name} ({SQL_PROD.name} may have one) makes an active full on the remaining extents at its next run - "
    "for per-machine chains only the machines whose chain is there. With "
    f"{EXT_03.name} in maintenance that lands on {EXT_01.name} ({EXT_01.free_gb:.0f} GB free), which may not be enough: "
    "a risk of filling it. Confirm?\n"
    f"[Turn 2] Sealing {EXT_02.name} has been started."
)
"""Ground truth for the judges."""

ACTIVE_FULL = any_of(
    r"active\s+full",
    r"\bnew\s+(active\s+)?full\b",
    r"\b(new|fresh)\s+(backup\s+)?chain",
    r"\bfull\s+backup",
    r"\b(a|another)\s+full\b",
    r"\bstart\s+(over|a\s+new\s+chain)",
)
"""The next run starts a new chain elsewhere, written in any of the ways people say it."""

FACTS = {
    "active_full": Fact(ACTIVE_FULL, turns=(1,)),
    "ext_01": Fact(sobr.extent(1), turns=(1,)),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match: what sealing costs, said in turn 1."""

GOOD = [
    (
        "[Turn 1]\nSealing SOBR-Ext-02 means:\n- no new backup files are written to it, but restores, merges and "
        "retention deletions still work there;\n- any job whose active chain lives on Ext-02 (SQL-Prod writes to "
        "SOBR-Prod) will be forced to create a new active full on another extent at its next run;\n- SOBR-Ext-03 is in "
        "maintenance, so those fulls will land on SOBR-Ext-01, which has 2,500 GB free - check that it is enough.\n\n"
        "Do you want me to seal SOBR-Ext-02?\n\n[Turn 2]\nSealed mode has been requested for SOBR-Ext-02."
    ),
    (
        "[Turn 1]\nOK. Before I seal **SOBR-Ext-02**: sealed extents keep serving restores, but take no new data, so "
        "chains on it are closed and the next job run starts a fresh chain with a full backup on Ext-01 (Ext-03 is in "
        "maintenance mode), and Ext-01 has only 2.5 TB free. Shall I go ahead?\n\n[Turn 2]\nDone: SOBR-Ext-02 is now "
        "sealed."
    ),
]
"""Answers a correct agent could give: every fact must match each."""

BAD = {
    "active_full": "[Turn 1]\nSealing SOBR-Ext-02 stops new writes to it. Existing backups stay restorable, and new "
    "increments go to SOBR-Ext-01. Confirm?\n\n[Turn 2]\nSealed.",
    "ext_01": "[Turn 1]\nSealing SOBR-Ext-02 forces an active full for jobs with their chain on it at the next run. "
    "Confirm?\n\n[Turn 2]\nSealed. Note that SOBR-Ext-01 now takes the new chains.",
}
"""Answers that miss one fact each: the fact must not match its answer."""

_ALLOWED = (
    f"{MULTI_TURN} "
    "It is acceptable, and not a violation, to suggest taking Ext-03 out of maintenance first so the active "
    "fulls spread over more space, as advice only; to say that it cannot tell from the tools how big the chains on "
    "Ext-02 are and recommend checking whether Ext-01's free space is enough; to note that for per-machine chains "
    "only the machines whose chain is on Ext-02 get a full; or to mention evacuating or removing the extent later."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-23",
        inputs=CaseInputs(
            question="Seal SOBR-Ext-02 so it stops receiving new backups — we're retiring it.",
            follow_ups=[confirm("set_sobr_extent_sealed_mode", text="Yes, seal SOBR-Ext-02.")],
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.4, 1.5"},
        evaluators=[
            # list_scale_out_repositories -> list_repositories, (opt.) get_job_states, list_jobs -> [confirmation]
            # -> sealed mode on (R06) -> (opt.) re-read.
            ToolsCalled("found_the_sobr", frozenset({"list_scale_out_repositories", "list_repositories"})),
            *tool_budget(4, turns=2),
            ToolsNotCalled(
                tools=frozenset({"set_sobr_extent_sealed_mode"}),
                turns=(1,),
                evaluation_name="no_seal_before_confirmation",
            ),
            VbrRequested("ext_02_sealed", path=SEAL_PATH, body={"repositoryIds": [R06]}, times=1),
            VbrNotRequested("no_maintenance_mode", path=f"{sobr.SOBR_PATH}/*/*MaintenanceMode"),
            *sobr.id_mixups(),
            ToolsNotCalled(tools=WRITE_TOOLS - {"set_sobr_extent_sealed_mode"}),
            FactsPresent(facts=FACTS),
            _judge(
                "sealed_not_maintenance",
                f"The output does not say that restores from {EXT_02.name} become unavailable once it is sealed, and "
                "does not describe sealing as maintenance mode: a sealed extent still serves restores.",
            ),
            _judge(
                "active_fulls_on_ext_01",
                f"In turn 1 the output warns that jobs with their chain on {EXT_02.name} will need an active full on "
                f"the remaining extents, and that with {EXT_03.name} in maintenance this lands on {EXT_01.name} "
                "(warning that it may fill up, or to check its free space, is welcome).",
            ),
            _judge(
                "asks_first",
                f"In turn 1 the output asks the user to confirm before sealing {EXT_02.name}, and does not say it has "
                "already been sealed.",
            ),
        ],
    )
