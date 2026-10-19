# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-03: retry only the failed VMs of SQL-Prod, whose failure is not fixed yet."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import MULTI_TURN, CaseInputs, Environment, confirm, judge, tool_budget
from cases.patterns import any_of, name
from evaluators import WRITE_TOOLS, FactsPresent, ToolsNotCalled, VbrNotRequested, VbrRequested
from stand import by_name, environment, replace
from stand.ids import FIRST_G3_SESSION, J02, S_ID04, S_ID20
from stand.jobs import JOB_STATES
from stand.sessions import RUN_BY_JOB, SESSIONS, started
from vbr_mock.markers import VbrAction

# ---- What VBR serves: the base stand, where SQL-Prod's run of 00:00 failed with its two automatic retries: guest
# processing of sql-prod-01 cannot log in with LAB\svc-sql-veeam (Win32 error 1326, KB3225), while sql-prod-02 was
# backed up. The retry VBR starts reprocesses only what failed (User Guide v13, retrying_jobs); it is the run's third
# retry, so it shares the run's original session (swagger SessionRetryInfo).

SQL_PROD = by_name(JOB_STATES, "SQL-Prod")
RETRY_PATH = f"/api/v1/jobs/{J02}/retry"
RETRY_SESSION = started(FIRST_G3_SESSION, RUN_BY_JOB[J02], retry_of=S_ID04, retry_number=3)

ENVIRONMENT: Environment = environment() | {
    RETRY_PATH: VbrAction(
        response=RETRY_SESSION,
        effects={
            "/api/v1/jobs/states": replace(
                JOB_STATES, J02, status="Starting", session_id=S_ID20, progress_percent=0, session_progress=None
            ),
            "/api/v1/sessions": [RETRY_SESSION, *SESSIONS],
            f"/api/v1/sessions/{S_ID20}": RETRY_SESSION,
        },
    ),
}

# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    f"A retry of {SQL_PROD.name} reprocesses only the VM that failed, sql-prod-01; sql-prod-02 was backed up fine. "
    "But the cause is not fixed: guest processing logs in to sql-prod-01 as LAB\\svc-sql-veeam, and Windows answers "
    "that the user name or password is incorrect (Win32 error 1326), so the retry will most likely fail again unless "
    "the credentials are corrected first (Credentials Manager or the job's guest processing settings). A retry started "
    "by hand gets no automatic retries of its own. The retry has been started; check its result in the job's sessions."
)
"""Ground truth for the judges."""

FACTS = {
    "failed_vm": name("sql-prod-01"),
    "cause": any_of(r"\b1326\b", r"password", r"credential", r"user\s*name"),
    "retry": r"\bretr(y|ied|ying)\b",
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    (
        f"[Turn 1]\nI retried {SQL_PROD.name}: a retry reprocesses only sql-prod-01, the VM that failed (sql-prod-02 was "
        "backed up fine). Note the cause isn't fixed - guest processing fails with Win32 error 1326, the user name or "
        "password of LAB\\svc-sql-veeam is incorrect - so the retry will most likely fail again until the credentials are "
        "updated. The retry is starting now.\n\n[Turn 2]\n(not asked: the agent already called retry_job)"
    ),
    (
        f"[Turn 1]\nBefore I retry: {SQL_PROD.name}'s failure on **sql-prod-01** comes from a wrong password for the guest "
        "processing account LAB\\svc-sql-veeam (error 1326). A retry would reprocess only sql-prod-01 but would likely "
        "fail again. Retry anyway, or fix the credentials first?\n\n[Turn 2]\nDone - the retry of "
        f"{SQL_PROD.name} has been started; it only processes sql-prod-01. I'll check the session result if you like."
    ),
    (
        "[Turn 1]\n| VM | Last result | Cause |\n|---|---|---|\n| sql-prod-01 | Failed | Win32 1326: bad credentials for "
        "LAB\\svc-sql-veeam |\n| sql-prod-02 | Success | - |\n\nRetrying now reprocesses only sql-prod-01, and it will "
        "fail the same way until the account's password is fixed. Shall I retry?\n\n[Turn 2]\nRetry triggered for "
        "sql-prod-01. It is running; no result yet."
    ),
]
"""Answers a correct agent could give: every fact must match each."""

BAD = {
    "failed_vm": f"I retried {SQL_PROD.name}; it reprocesses the VM that failed. The 1326 error is not fixed yet.",
    "cause": f"I started a retry of {SQL_PROD.name} for sql-prod-01, which failed last night.",
}
"""Fact -> an answer that misses it."""

_ALLOWED = (
    f"{MULTI_TURN} "
    "It is acceptable, and not a violation, to ask first whether to fix the password before retrying, to "
    "name the account LAB\\svc-sql-veeam, to point to KB3225 or the Credentials Manager, to say that a retry started "
    "by hand gets no automatic retries, or to offer to check the retry's result with the sessions."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-03",
        inputs=CaseInputs(
            question="Retry only the failed VMs of the SQL-Prod job.",
            follow_ups=[confirm("retry_job", text="Yes, retry it now.")],  # asking "fix the password first?" is allowed
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.2, 1.3"},
        evaluators=[
            # get_job_states -> (opt.) get_session_failure_details / list_task_sessions -> retry_job(J02)
            ToolCorrectness(expected_tools=["retry_job"], allow_extra=True),
            *tool_budget(4, turns=2),
            VbrRequested("sql_prod_retried", path=RETRY_PATH, times=1),
            VbrNotRequested("not_started_instead", path="/api/v1/jobs/*/start"),
            ToolsNotCalled(tools=WRITE_TOOLS - {"retry_job"}),
            FactsPresent(facts=FACTS),
            _judge(
                "only_failed_vm",
                "The output explains that the retry reprocesses only sql-prod-01, the VM that failed, not sql-prod-02.",
            ),
            _judge(
                "cause_not_fixed",
                "The output warns that the cause of the failure (guest processing cannot log in with the account's "
                "credentials, error 1326) is not fixed, so the retry is likely to fail again unless the credentials "
                "are corrected.",
            ),
            _judge(
                "no_success_promised",
                "The output says the retry has been started (or is starting) and does not promise or claim that it "
                "succeeded.",
            ),
        ],
    )
