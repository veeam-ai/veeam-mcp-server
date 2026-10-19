# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G2-01: why SQL-Prod failed last night, and what to do about it."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case

import stand
from cases import CaseInputs, Environment, judge, tool_budget
from cases.patterns import any_of, name
from evaluators import FactsPresent, ToolsCalled, ToolsNotCalled
from stand.ids import S_ID04, S_ID05, S_ID06
from stand.sessions import BY_ID, GUEST_ERROR

# ---- What VBR serves: the base stand. SQL-Prod's 00:00 run (S-ID04) and its two automatic retries (S-ID05, S-ID06)
# failed on sql-prod-01 with Win32 error 1326 in guest processing; sql-prod-02 was backed up by the first attempt.

ENVIRONMENT: Environment = stand.environment()

# ---- What a correct answer says, derived from the data above.

_RUN = [BY_ID[S_ID04], BY_ID[S_ID05], BY_ID[S_ID06]]
_TIMES = ", ".join(f"{session.creation_time:%H:%M}" for session in _RUN)

EXPECTED = (
    f"SQL-Prod's run at 00:00 on {_RUN[0].creation_time:%Y-%m-%d} failed: the first attempt and its two automatic "
    f"retries ({_TIMES}) all Failed - one incident, not three. Only sql-prod-01 failed; sql-prod-02 was processed "
    f"by the first attempt. The error: {GUEST_ERROR} The cause is a wrong or outdated password of the guest "
    "processing account LAB\\svc-sql-veeam. Fix: update that account's password in the job's guest processing "
    "settings (or in the Credentials manager), verify it (in VBR 13 the button is 'Verify network connectivity and "
    "credentials', earlier 'Test Now'), then retry the job or let tonight's run pick it up."
)
"""Ground truth for the judges."""

FACTS = {
    "failed_vm": name("sql-prod-01"),
    "account": r"svc-sql-veeam",
    # the error says it, and a reader may say it in their own words
    "cause_credentials": any_of(
        r"\b1326\b",
        r"user\s*name\s+or\s+password\s+is\s+incorrect",
        r"(wrong|incorrect|invalid|expired|bad|changed|outdated|stale|rotated)\s+([\w'-]+\s+){0,3}(password|credentials?)",
        r"(password|credentials?)\s+([\w'-]+\s+){0,4}(wrong|incorrect|invalid|expired|changed|outdated|no\s+longer\s+valid)",
    ),
    "fix_credentials": any_of(
        r"\b(update|change|correct|fix|reset|re-?enter|enter|replace|set|provide|supply)\w*(?:/\w+)?\s+"
        r"([\w'\\.@-]+\s+){0,5}(password|credentials?|account)",
        r"\b(password|credentials?)\s+([\w'\\.@-]+\s+){0,4}(updated|changed|corrected|reset|re-?entered|fixed|replaced)\b",
        r"credentials?\s+manager",
    ),
    "fix_retry": any_of(
        r"\bretry",
        r"\bre-?run",
        r"\b(run|start|kick\s+off|trigger)\s+(\S+\s+){0,2}again\b",
        r"\b(next|tonight'?s)\s+(scheduled\s+)?(run|backup|job\s+run|session)",
        r"\b(run|start)\s+(\S+\s+){0,2}manually\b",
    ),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

_ALLOWED = (
    "It is acceptable, and not a violation, to add that sql-prod-01's latest restore point is older than 33 hours "
    "(the RPO impact), to mention secondary checks such as access to ADMIN$, the firewall or UAC, to name VBR 13's "
    "'Verify network connectivity and credentials' button (or 'Test Now'), or to propose retrying the job once the "
    "credentials are fixed, as long as the output does not claim it retried or started the job itself."
)

GOOD = [
    (
        "SQL-Prod failed last night on **sql-prod-01** only - sql-prod-02 was backed up fine. The run at 00:00 and both "
        "automatic retries (00:31, 00:46) hit the same error, so it is one incident:\n\n"
        "> Failed to prepare guest for hot backup. Error: Cannot connect to the host's administrative share. Host: "
        "[10.0.20.11]. Account: [LAB\\svc-sql-veeam]. Win32 error: The user name or password is incorrect. Code: 1326\n\n"
        "**Cause:** the guest processing account LAB\\svc-sql-veeam has a wrong or expired password.\n\n"
        "**What to do:**\n1. Update the password of LAB\\svc-sql-veeam in the Credentials Manager (or in the job's guest "
        "processing settings).\n2. Click *Verify network connectivity and credentials* to check it.\n3. Retry the job, or "
        "let tonight's 00:00 run pick it up."
    ),
    (
        "| Item | Detail |\n|---|---|\n| Failed VM | sql-prod-01 (sql-prod-02 OK) |\n| Error | Win32 error 1326 - "
        "the user name or password is incorrect |\n| Account | LAB\\svc-sql-veeam |\n| Attempts | 3 (00:00 run + 2 "
        "retries), all failed |\n\nThe credentials stored for svc-sql-veeam no longer work. Change the password stored "
        "in VBR for that account, test it, and re-run SQL-Prod."
    ),
    (
        "Only sql-prod-01 failed: VBR could not log in to its admin share with LAB\\svc-sql-veeam because the password "
        "is incorrect (error 1326). Reset the account's credentials in VBR and then retry SQL-Prod - the retries during "
        "the night all failed the same way."
    ),
    (
        "sql-prod-01 failed with Win32 error 1326: the password stored for the guest processing account is wrong. "
        "Update LAB\\svc-sql-veeam's password in the job's guest processing settings, then start SQL-Prod again (or "
        "let tonight's run pick it up)."
    ),
]

BAD = {
    "failed_vm": "Both VMs of SQL-Prod failed because the repository ran out of space; retry the job tonight.",
    "cause_credentials": "sql-prod-01 failed: Veeam could not reach the host's administrative share as "
    "LAB\\svc-sql-veeam. Check the network and the firewall, then retry.",
    "fix_credentials": "sql-prod-01 failed with error 1326 (the user name or password is incorrect) for "
    "LAB\\svc-sql-veeam. Just retry the job.",
    "fix_retry": "sql-prod-01 failed with error 1326: the password of LAB\\svc-sql-veeam is wrong. Update the "
    "password in the Credentials Manager.",
}


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G2-01",
        inputs=CaseInputs(
            question="Why did the SQL-Prod job fail last night, and what should I do about it?",
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G2", "base_stand": "1.2-1.3"},
        evaluators=[
            # The error is in the failing task: get_session_failure_details has it with the task log,
            # list_task_sessions in the task's result.message ("the field to trust").
            ToolsCalled("error_read", frozenset({"get_session_failure_details", "list_task_sessions"})),
            *tool_budget(4),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "cause_and_fix",
                "The output gives as the cause that the guest processing credentials of LAB\\svc-sql-veeam are wrong "
                "or outdated (VBR could not log in to sql-prod-01's administrative share, Win32 error 1326), and as "
                "the fix that the user updates that account's password in VBR (guest processing settings or "
                "Credentials manager) and then retries the job or lets the next run pick it up. Quoting the error "
                "alone, without saying what to change, does not meet this. Verifying the credentials first is good "
                "but not required.",
            ),
            _judge(
                "no_infrastructure_blame",
                "The output does not blame the repository, free space, the backup proxy or the network for the "
                "failure; the cause it gives is the guest processing credentials.",
            ),
            _judge(
                "only_one_vm_failed",
                "The output does not say that both VMs failed: it says or implies that only sql-prod-01 failed and "
                "does not present sql-prod-02 as failed.",
            ),
            _judge(
                "one_incident",
                "The output presents the failed attempts of the night (the 00:00 run and its two automatic retries) "
                "as one run with its retries, not as separate incidents.",
            ),
            _judge(
                "no_action_taken",
                "The output does not claim that it retried, started or otherwise ran the job; suggesting a retry "
                "for the user to do is fine.",
            ),
        ],
    )
