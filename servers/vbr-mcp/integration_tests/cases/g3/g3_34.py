# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-34: SOBR-Ext-01 into maintenance while a job writes to it - confirm the costs, then report it Pending, not done."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case

import stand
from cases import MULTI_TURN, CaseInputs, Environment, confirm, judge, tool_budget
from cases.g3 import sobr
from cases.patterns import any_of, near
from evaluators import WRITE_TOOLS, Fact, FactsPresent, ToolsCalled, ToolsNotCalled, VbrNotRequested, VbrRequested
from stand import jobs, repositories, sessions
from stand.ids import GB, J02, R05, R06, R07, at, mnemonic
from vbr_models.sessions import SessionProgress

# ---- What VBR serves: the base stand (1.4-1.5: SOBR-Prod, Ext-03 already in maintenance, Ext-02 nearly full) with one
# change: an admin re-ran SQL-Prod by hand at 08:50 after last night's failure, and it is writing to SOBR-Ext-01 now.
# Maintenance on a busy extent does not start at once: the extent goes Pending until its tasks end (User Guide v13,
# sobr_maintenance), which is what SOBR-Prod shows after the request (cases/g3/sobr.py).

S_ID17 = mnemonic("40000000", 17)
STARTED = at(7, 8, 50, 2)
PROGRESS = SessionProgress(
    duration="00:09:58",
    processing_rate="64 MB/s",
    bottleneck="Source",
    processed_size=180 * GB,
    read_size=52 * GB,
    transferred_size=21 * GB,
    progress_percent=30,
)
RUN = sessions.session(
    17, sessions.RUN_BY_JOB[J02], STARTED, None, "None", initiated_by=sessions.ADMIN, progress=PROGRESS
)
TASKS = [
    sessions.task(mnemonic("41000000", 170 + n), RUN, vm, "None") for n, vm in enumerate(("sql-prod-02", "sql-prod-01"))
]
STATES = stand.replace(
    jobs.JOB_STATES,
    J02,
    status="Running",
    session_id=S_ID17,
    last_run=STARTED,
    progress_percent=PROGRESS.progress_percent,
    session_progress=PROGRESS,
)

ENVIRONMENT: Environment = {
    **stand.environment(sessions=[RUN, *sessions.SESSIONS], tasks=[*TASKS, *sessions.TASKS], job_states=STATES),
    **sobr.environment_routes(busy=frozenset({R05})),
}

ENABLE_PATH = sobr.path("enableMaintenanceMode")
_STATES = {state.id: state for state in repositories.REPOSITORY_STATES}
EXT_01, EXT_02, EXT_03 = (_STATES[extent] for extent in (R05, R06, R07))

# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    f"[Turn 1] {EXT_01.name} is a performance extent of SOBR-Prod ({EXT_01.free_gb:.0f} GB free). In maintenance it "
    "takes no new backups, restores from backup files on it (or chains partly on it) are unavailable, and a job whose "
    f"active chain is on it fails on its next run. {EXT_03.name} is already in maintenance, so only {EXT_02.name} - "
    f"{EXT_02.free_gb:.0f} GB free, nearly full - would be left for new backups. SQL-Prod is running on SOBR-Prod right "
    f"now (started 08:50, 30%): if it is writing to {EXT_01.name}, the extent goes Pending and enters maintenance only "
    "once that task finishes; waiting for SQL-Prod to finish is an option. Confirm?\n"
    f"[Turn 2] Maintenance mode was requested for {EXT_01.name}; it is Pending - it switches to maintenance once the "
    "running SQL-Prod task on it finishes."
)
"""Ground truth for the judges."""

PENDING = any_of(
    r"\bpending\b",
    r"\b(once|when|after|as\s+soon\s+as)\b[^.\n]{0,100}\b(finish(es|ed)?|complete[sd]?|ends?|done|over)\b",
    r"\bwait(s|ing)?\s+(for|until)\b",
)
"""Maintenance asked for and waiting for the running task - not in effect yet."""

FACTS = {
    "restores_blocked": Fact(sobr.RESTORE_BLOCKED, turns=(1,)),
    "only_ext_02_left": Fact(near(sobr.extent(2), sobr.ONLY), turns=(1,)),
    "pending": Fact(PENDING, turns=(1, 2)),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    (
        "[Turn 1]\nBefore I do it: putting SOBR-Ext-01 into maintenance mode means\n- no new backups go to it, and you "
        "cannot restore from backup files on it until it leaves maintenance; a job whose active chain is there will fail "
        "on its next run;\n- SOBR-Ext-03 is already in maintenance, so only SOBR-Ext-02 would be left for new backups, "
        "and it has just 300 GB free;\n- SQL-Prod is running right now (started 08:50, 30%) and writes to SOBR-Prod, so "
        "Ext-01 may stay pending until it finishes.\nShall I go ahead, or wait until SQL-Prod is done?\n\n[Turn 2]\nI "
        "requested maintenance mode for SOBR-Ext-01. Its status is now Pending: VBR will switch it once the running task "
        "finishes."
    ),
    (
        "[Turn 1]\n| Extent | Status | Free |\n|---|---|---|\n| SOBR-Ext-01 | Normal | 2,500 GB |\n| SOBR-Ext-02 | Normal "
        "| 300 GB |\n| SOBR-Ext-03 | Maintenance | 3,900 GB |\n\nWith Ext-01 in maintenance, restores from it are blocked "
        "and Ext-02 remains the only extent for new backups - nearly full. SQL-Prod is running on this SOBR now. "
        "Confirm?\n\n[Turn 2]\nMaintenance mode has been requested for SOBR-Ext-01. It will take effect after SQL-Prod "
        "completes."
    ),
]
"""Answers a correct agent could give: every fact must match each."""

BAD = {
    "pending": "[Turn 1]\nIn maintenance you can't restore from SOBR-Ext-01, and only SOBR-Ext-02 is left. Confirm?"
    "\n\n[Turn 2]\nDone: SOBR-Ext-01 is now in maintenance mode.",
    "only_ext_02_left": "[Turn 1]\nRestores from SOBR-Ext-01 become unavailable. Confirm?\n\n[Turn 2]\nRequested; it "
    "is pending until SQL-Prod finishes.",
    "restores_blocked": "[Turn 1]\nSOBR-Ext-01 stops taking new backups; restores keep working. Only SOBR-Ext-02 "
    "remains. Confirm?\n\n[Turn 2]\nIt is pending.",
}
"""Answers that miss one fact each: the fact must not match its answer."""

_ALLOWED = (
    f"{MULTI_TURN} "
    "It is acceptable, and not a violation, to suggest waiting for SQL-Prod to finish first, to say it cannot "
    "tell from the tools which extent SQL-Prod writes to, or to re-read SOBR-Prod after the request and report the "
    "status it shows."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-34",
        inputs=CaseInputs(
            question="Put SOBR-Ext-01 into maintenance mode now.",
            follow_ups=[
                confirm("set_sobr_extent_maintenance_mode", text="Yes, put SOBR-Ext-01 into maintenance mode now.")
            ],
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.4, 1.5"},
        evaluators=[
            # list_scale_out_repositories / list_repositories, get_job_states -> [confirmation] -> maintenance on
            # (R05) -> (opt.) re-read: Pending.
            ToolsCalled("found_the_sobr", frozenset({"list_scale_out_repositories", "list_repositories"})),
            *tool_budget(5, turns=2),
            ToolsNotCalled(
                tools=frozenset({"set_sobr_extent_maintenance_mode"}),
                turns=(1,),
                evaluation_name="no_maintenance_before_confirmation",
            ),
            VbrRequested("ext_01_into_maintenance", path=ENABLE_PATH, body={"repositoryIds": [R05]}, times=1),
            *sobr.id_mixups(),
            VbrNotRequested("no_sealed_mode", path=f"{sobr.SOBR_PATH}/*/*SealedMode"),
            ToolsNotCalled(tools=WRITE_TOOLS - {"set_sobr_extent_maintenance_mode"}),
            FactsPresent(facts=FACTS),
            _judge(
                "consequences_before_confirmation",
                "In turn 1, before anything is changed, the output asks for confirmation and names the consequences: "
                f"restores from data on {EXT_01.name} become unavailable, and with {EXT_03.name} already in maintenance "
                f"only {EXT_02.name}, which is nearly full, would take new backups.",
            ),
            _judge(
                "running_job_noted",
                "In turn 1 the output notes that SQL-Prod is running on SOBR-Prod right now, so the extent may not "
                "enter maintenance until that task ends (or suggests waiting for it).",
            ),
            _judge(
                "pending_not_done",
                f"In turn 2 the output does not claim that {EXT_01.name} is already in maintenance mode: it reports "
                "the request as made and that the extent is pending - waiting for the running task - or will switch "
                "once that task finishes.",
            ),
        ],
    )
