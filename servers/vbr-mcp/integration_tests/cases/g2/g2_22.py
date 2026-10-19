# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G2-22: a job that fails because part of its backup chain is on an extent in maintenance mode."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import CaseInputs, judge, tool_budget
from cases.patterns import any_of, near
from evaluators import FactsPresent, ToolsCalled, ToolsNotCalled
from stand import environment, replace, sessions
from stand.ids import T01, T03, T04
from vbr_models.sessions import SessionResult

# ---- What VBR serves: the base stand, with another reason for tonight's SQL-Prod failure. SOBR-Prod's extent
# SOBR-Ext-03 is in maintenance mode (1.5), and part of sql-prod-01's active chain is on it: "If an extent contains a
# part of an active backup chain ... do NOT put this extent into the Maintenance mode. Otherwise, the backup job ...
# will fail" (User Guide v13, sobr_maintenance). So the run and both automatic retries fail for sql-prod-01 with the
# error VBR gives for a file on such an extent (forum p=506368: "Backup file cannot be accessed because it is located
# on extent in maintenance mode"); sql-prod-02's chain is elsewhere and it backs up fine.

MAINTENANCE_ERROR = "Error: Backup file cannot be accessed because it is located on extent in maintenance mode."

_FAILED = SessionResult(result="Failed", message=MAINTENANCE_ERROR, is_canceled=False)
TASKS = sessions.TASKS
for _task in (T01, T03, T04):  # sql-prod-01 in the run (S-ID04) and in its retries (S-ID05, S-ID06)
    TASKS = replace(TASKS, _task, result=_FAILED)

ENVIRONMENT = environment(tasks=TASKS)

# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    "SQL-Prod's run at 00:00 and both automatic retries (00:31 and 00:46) failed for sql-prod-01 with \"Backup file "
    'cannot be accessed because it is located on extent in maintenance mode"; sql-prod-02 backed up fine. SQL-Prod '
    "writes to the scale-out repository SOBR-Prod, whose extent SOBR-Ext-03 is in Maintenance mode: part of "
    "sql-prod-01's active backup chain is on it, so VBR cannot continue that chain, and a plain retry fails the same "
    "way. Safe fixes: if the maintenance work on SOBR-Ext-03 is done, take it out of maintenance mode and let "
    "SQL-Prod run (or retry it); if SOBR-Ext-03 has to stay in maintenance, start a new chain for sql-prod-01 with an "
    "active full, which lands on another extent (SOBR-Ext-01 has 2.5 TB free, SOBR-Ext-02 only 300 GB), or evacuate "
    "SOBR-Ext-03's backups to the other extents. Nothing was changed."
)
"""Ground truth for the judges."""

FACTS = {
    "vm": r"sql-prod-01",
    "cause": near(r"maintenance", r"\bextent", 80),
    "extent": r"SOBR-Ext-03|\bExt-03\b|extent\s*(?:#|no\.?\s*)?3\b",
    "fix": any_of(
        r"\bout\s+of\s+maintenance",
        r"\b(disable|exit|end|leave|turn\s+off|switch\s+off)\w*\s+(the\s+)?maintenance",
        r"\bactive\s+full",
        r"\bnew\s+(backup\s+)?chain",
        r"\bevacuat",
    ),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    """**What happened:** SQL-Prod failed at 00:00 and both automatic retries (00:31, 00:46) failed the same way for **sql-prod-01**: *"Backup file cannot be accessed because it is located on extent in maintenance mode."* sql-prod-02 was backed up successfully.

SQL-Prod targets the scale-out repository SOBR-Prod, and its extent **SOBR-Ext-03 is in Maintenance mode**. Part of sql-prod-01's active backup chain lives on that extent, so VBR can't add to the chain - and retrying won't help while the extent stays in maintenance.

**How to fix it safely:**
1. If the maintenance on SOBR-Ext-03 is finished, take the extent out of maintenance mode, then retry SQL-Prod (or wait for tonight's run).
2. If SOBR-Ext-03 must stay in maintenance (e.g. you're retiring it), run an active full of SQL-Prod so sql-prod-01 starts a new chain on another extent - SOBR-Ext-01 has ~2.5 TB free, SOBR-Ext-02 only 300 GB - or evacuate SOBR-Ext-03's backups first.

I haven't changed anything.""",
    """sql-prod-01 couldn't be backed up because some of its backup files sit on SOBR-Ext-03, which is currently in maintenance mode, and VBR can't access files on such an extent. Options: bring Ext-03 back out of maintenance and rerun the job, or create a new chain with an active full on a healthy extent (Ext-01 has the space). A simple retry would fail again.""",
]

BAD = {
    "cause": (
        "SQL-Prod failed for sql-prod-01 because the guest processing account's password is wrong (Win32 error "
        "1326). Update the credentials of LAB\\svc-sql-veeam and retry the job."
    ),
    "fix": (
        "sql-prod-01 failed: its backup files are on SOBR-Ext-03, an extent in maintenance mode. Just retry the job "
        "in a few minutes."
    ),
}

_ALLOWED = (
    "It is acceptable, and not a violation, to quote the task log, to give the times of the run and its retries, to "
    "mention that Test-NewApp also targets SOBR-Prod, to explain what maintenance mode blocks (new writes, restores "
    "from that extent), to mention VBR's option to perform a full backup when a required extent is offline, or to "
    "offer to take SOBR-Ext-03 out of maintenance or start the active full after the user confirms, as long as the "
    "output does not claim to have done it."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G2-22",
        inputs=CaseInputs(
            question="SQL-Prod failed last night. What happened and how do I fix it safely?",
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G2", "base_stand": "1.2, 1.3, 1.5"},
        evaluators=[
            # the error is in sql-prod-01's task log (get_session_failure_details) or its task's result
            # (list_task_sessions); which extent is in maintenance only list_scale_out_repositories shows
            ToolsCalled("failure_read", frozenset({"get_session_failure_details", "list_task_sessions"})),
            ToolCorrectness(expected_tools=["list_scale_out_repositories"], allow_extra=True),
            *tool_budget(5),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "cause_correct",
                "The output attributes the failure to SOBR-Ext-03 being in maintenance mode while part of "
                "sql-prod-01's backup chain is on it, not to credentials, guest processing, the network or free "
                "space.",
            ),
            _judge(
                "retry_alone_not_a_fix",
                "The output does not present a plain retry or rerun of SQL-Prod, with SOBR-Ext-03 still in "
                "maintenance mode, as the fix.",
            ),
            _judge(
                "sql_prod_02_fine",
                "The output does not claim that sql-prod-02 failed: it was backed up in the first run.",
            ),
            _judge(
                "nothing_changed",
                "The output does not claim to have taken the extent out of maintenance, started a job or changed "
                "anything else; offering to do so is fine.",
            ),
        ],
    )
