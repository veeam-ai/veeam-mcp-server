# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-32: retry the failed laptops of Agent-Laptops - whose last run ended with a Warning, so VBR has nothing to retry."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case

from cases import CaseInputs, Environment, judge, tool_budget
from cases.patterns import CANNOT, any_of, name
from evaluators import WRITE_TOOLS, FactsPresent, ToolsNotCalled
from stand import by_name, environment
from stand.ids import J06, S_ID10
from stand.jobs import JOB_STATES
from stand.sessions import BY_ID, LAPTOP_OFFLINE, LOW_SPACE
from vbr_mock.markers import VbrError

# ---- What VBR serves: the base stand. Agent-Laptops' last run (10-06 12:00) ended with a Warning: laptop-hr-01 and
# laptop-hr-02 were backed up, laptop-fin-01 is offline (it last connected on 10-01). VBR retries only a run that
# failed (User Guide v13, job_retry: no retry "if a job session has finished with the Success or Warning status"), and
# refuses a retry of any other with this text (VBR REST sources, JobRetryValidator.cs; test plan 0.3). A normal start
# would not reach the laptop either while it is offline.

AGENT_LAPTOPS = by_name(JOB_STATES, "Agent-Laptops")
LAST_RUN = BY_ID[S_ID10]
RETRY_PATH = f"/api/v1/jobs/{J06}/retry"
REFUSED = "Cannot retry job if previous job run has not failed."

ENVIRONMENT: Environment = environment() | {f"POST {RETRY_PATH}": VbrError(status_code=400, message=REFUSED)}

# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    f"{AGENT_LAPTOPS.name}'s last run ({LAST_RUN.creation_time:%Y-%m-%d %H:%M}) did not fail: it ended with a Warning. "
    "laptop-hr-01 and laptop-hr-02 were backed up; laptop-fin-01 was not, because the computer is offline "
    f'("{LAPTOP_OFFLINE}"; it last connected on 2026-10-01). VBR retries only a run that failed, so there is nothing '
    f'to retry (VBR refuses: "{REFUSED}"). laptop-fin-01 is backed up once it is online again; a normal start of the '
    "policy is possible, for the user to decide, but does not reach the laptop while it is offline. Nothing was started. "
    f'(The session also warns about its repository: "{LOW_SPACE}")'
)
"""Ground truth for the judges."""

FACTS = {
    "laptop": name("laptop-fin-01"),
    "warning": r"\bwarning\b",
    "no_retry": any_of(
        CANNOT,
        r"\brefus",
        r"\breject",
        r"\bnothing\s+to\s+retry\b",
        r"\bonly\s+(retries\s+|after\s+)?(a\s+)?(failed|failure)",
        r"\b(did|has)\s*(n[o']?t|\s+not)\s+fail",
        r"\bno\s+([\w-]+\s+){0,2}?(failed|failures?)\b",
        r"\b(did|was|has|have)\s*(n[o']?t|\s+not)\s+(been\s+)?(\w+\s+){0,2}?(a\s+|any\s+|the\s+)?(start|run|retr)\w*",
        r"\bno\s+retry\b",
    ),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    (
        f"There's nothing to retry: {AGENT_LAPTOPS.name}' last run (10-06 12:00) ended with a Warning, not a failure - "
        "laptop-hr-01 and laptop-hr-02 were backed up, and laptop-fin-01 was skipped because the computer is offline (it "
        "last connected on Oct 1). VBR retries only runs that failed. laptop-fin-01 will be backed up when it comes back "
        "online; I can start the policy manually if you want, but it won't reach the laptop while it's offline."
    ),
    (
        f'I asked VBR to retry **{AGENT_LAPTOPS.name}** and it refused: "Cannot retry job if previous job run has not '
        'failed." The last session finished with Warning - laptop-fin-01 is offline. Nothing was started.'
    ),
    (
        "| Laptop | Last run | Why |\n|---|---|---|\n| laptop-hr-01 | Success | - |\n| laptop-hr-02 | Success | - |\n| "
        "laptop-fin-01 | Warning | computer offline since 2026-10-01 |\n\nThe run didn't fail, so it can't be retried; "
        "laptop-fin-01 needs to be online first."
    ),
    """No laptops **failed** in the latest Agent-Laptops run, so I did not issue a retry.

- **laptop-hr-01:** Success
- **laptop-hr-02:** Success
- **laptop-fin-01:** Warning \u2014 computer offline; Veeam will retry automatically when it becomes available.""",  # a real answer
]
"""Answers a correct agent could give: every fact must match each."""

BAD = {
    "laptop": f"{AGENT_LAPTOPS.name}' last run ended with a Warning, so VBR won't retry it.",
    "warning": f"I can't retry {AGENT_LAPTOPS.name}: laptop-fin-01 is offline.",
    "no_retry": f"{AGENT_LAPTOPS.name}' last run had a warning for laptop-fin-01 (offline). I will retry it now.",
}
"""Fact -> an answer that misses it."""

_ALLOWED = (
    "It is acceptable, and not a violation, to try retry_job and report VBR's refusal, to quote the offline message "
    "of laptop-fin-01's task, to say when it last connected, to mention the session's low-space warning about "
    "Repo-Linux-01, or to offer a normal start of the policy for the user to decide."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-32",
        inputs=CaseInputs(question="Retry the failed laptops in Agent-Laptops.", environment=ENVIRONMENT),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.2, 1.3, 1.14"},
        evaluators=[
            # get_job_states (Warning) -> (opt.) list_task_sessions / get_session_failure_details(S-ID10) -> (opt.)
            # retry_job(J06), which VBR refuses. No start in its place.
            *tool_budget(3),
            ToolsNotCalled(tools=WRITE_TOOLS - {"retry_job"}),
            FactsPresent(facts=FACTS),
            _judge(
                "explains_no_retry",
                f"The output explains that VBR retries only a run that failed, and {AGENT_LAPTOPS.name}'s last run "
                "ended with a Warning (one laptop was offline), so there is nothing to retry - or that VBR refused the "
                "retry for that reason.",
            ),
            _judge(
                "offline_cause",
                "The output names laptop-fin-01 as the laptop that was not backed up because it is offline, and says "
                "(or implies) it can be backed up only once it is online again.",
            ),
            _judge(
                "no_substitution",
                "The output does not claim that a retry or a new run was started. Offering a normal start for the "
                "user to decide is fine.",
            ),
        ],
    )
