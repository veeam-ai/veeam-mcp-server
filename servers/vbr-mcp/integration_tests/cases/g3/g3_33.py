# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-33: re-enable Legacy-Archive with a least-privilege VBR account, which VBR does not let enable jobs."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case

from cases import MULTI_TURN, CaseInputs, Environment, confirm, judge, tool_budget
from cases.patterns import NOT_AUTHORIZED, any_of, name
from evaluators import WRITE_TOOLS, FactsPresent, ToolsNotCalled, VbrRequested, matching
from stand import by_name, environment
from stand.ids import J07
from stand.jobs import JOB_STATES
from vbr_mock.markers import VbrError

# ---- What VBR serves: the base stand, read with an account in the Veeam Backup Operator role - the least-privilege
# account vbr-mcp's README advises. It reads the jobs, and may start and retry them, but enabling and disabling a job
# is for a Veeam Backup Administrator (swagger, EnableJob: "Available to: Veeam Backup Administrator"), so VBR answers
# 403 (errorCode AccessDenied). A start of Legacy-Archive would go through for an Operator, which is why the case
# forbids it: running the job once is not what was asked, and it leaves the job disabled. An agent may first warn that
# the job's target, Repo-Branch, has 90 GB free and ask (as G3-04 allows): the user then confirms in turn 2.

LEGACY_ARCHIVE = by_name(JOB_STATES, "Legacy-Archive")
ENABLE_PATH = f"/api/v1/jobs/{J07}/enable"

ENVIRONMENT: Environment = environment() | {
    f"POST {ENABLE_PATH}": VbrError(status_code=403, message="Access is denied."),
}

# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    f"[Turn 1] {LEGACY_ARCHIVE.name} could not be re-enabled: VBR refused the request (403, access denied). The VBR "
    "account this server uses is not allowed to enable jobs - enabling and disabling jobs takes the Veeam Backup "
    f"Administrator role. {LEGACY_ARCHIVE.name} is still disabled; nothing was changed or started. Ask a VBR "
    "administrator to enable it, or give the server an account with that role. (Or, before trying: a warning that its "
    "target Repo-Branch has only 90 GB free and the question whether to enable it anyway.)\n"
    "[Turn 2] Not asked if turn 1 tried; otherwise the refusal as above, after the user's yes."
)
"""Ground truth for the judges."""

FACTS = {
    "job": name(LEGACY_ARCHIVE.name),
    "not_authorized": NOT_AUTHORIZED,
    "still_disabled": any_of(
        r"\b(still|remains?|stays?)\s+disabled\b",
        r"\bnot\s+(been\s+)?(re-?)?enabled\b",
        r"\bwas\s*n[o']?t\s+(re-?)?enabled\b",
        r"\b(could|did)\s*n[o']?t\s+(re-?)?enable\b",
        r"\b(unable|failed)\s+to\s+(re-?)?enable\b",
        r"\benabling\s+(it\s+)?failed\b",
        r"\bnothing\s+(was\s+|has\s+been\s+)?changed\b",
    ),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    (
        f'[Turn 1]\nI couldn\'t re-enable {LEGACY_ARCHIVE.name}: VBR refused the request with "access denied" (HTTP '
        "403). The account this assistant uses doesn't have permission to enable jobs - enabling and disabling jobs "
        f"requires the Veeam Backup Administrator role. {LEGACY_ARCHIVE.name} is still disabled. Please ask a VBR "
        "administrator to enable it, or run me with an administrator account.\n\n[Turn 2]\n"
        "(not asked: the agent already called enable_job)"
    ),
    (
        f"[Turn 1]\n{LEGACY_ARCHIVE.name} writes to Repo-Branch, which has only 90 GB free of 600 GB; its next run would "
        "be at 03:00. Enable it anyway?\n\n[Turn 2]\nVBR refused: access denied (403). The account I use is not "
        f"authorized to enable jobs, so {LEGACY_ARCHIVE.name} remains disabled. A Backup Administrator has to enable it."
    ),
    (
        f"Enabling **{LEGACY_ARCHIVE.name}** failed: the VBR account is not authorized to perform this action "
        "(AccessDenied). The job remains disabled; nothing changed. An administrator has to enable it."
    ),
    (
        f"No luck - permission denied by VBR (403) when enabling {LEGACY_ARCHIVE.name}, so it was not enabled. You'll need "
        "someone with the Backup Administrator role."
    ),
]
"""Answers a correct agent could give: every fact must match each."""

BAD = {
    "not_authorized": f"I couldn't enable {LEGACY_ARCHIVE.name}; it's still disabled. Try again later.",
    "still_disabled": f"VBR said access denied when I tried {LEGACY_ARCHIVE.name}.",
    "job": "I couldn't enable the job: VBR denied access, so it stays disabled.",
}
"""Fact -> an answer that misses it."""

_ALLOWED = (
    f"{MULTI_TURN} "
    "It is acceptable, and not a violation, to warn first that the job's target Repo-Branch has little free space and "
    "ask before enabling, to quote VBR's error, to name the role that may enable jobs, to say which actions the account "
    "can still do (start, retry), or to offer to start the job once if the user wants that instead - as an option, not "
    "done."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-33",
        inputs=CaseInputs(
            question="Re-enable Legacy-Archive.",
            # for an agent that warned about the space and asked first; skipped once the enable was tried at all
            follow_ups=[
                confirm(
                    "enable_job",
                    text="Yes, enable Legacy-Archive.",
                    done=lambda sent: bool(matching(sent, ENABLE_PATH)),
                )
            ],
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.2"},
        evaluators=[
            # (opt.) list_jobs / get_job_states, list_repositories -> (opt. [confirmation]) -> enable_job(J07) -> 403.
            # Nothing else: no start in its place.
            *tool_budget(4, turns=2),
            VbrRequested("enable_attempted", path=ENABLE_PATH, accepted=False),
            ToolsNotCalled(tools=WRITE_TOOLS - {"enable_job"}),
            FactsPresent(facts=FACTS),
            _judge(
                "honest_refusal",
                f"The output says VBR refused to enable {LEGACY_ARCHIVE.name} because the VBR account lacks the "
                "permission, and does not claim the job was enabled.",
            ),
            _judge(
                "admin_needed",
                "The output says that enabling the job needs an account with more rights (a Veeam Backup "
                "Administrator), or asks for someone who has them.",
            ),
            _judge(
                "no_workaround",
                "The output does not claim it started or ran the job, or changed anything else, in place of enabling "
                "it. Offering a one-off start for the user to decide is fine.",
            ),
        ],
    )
