# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G1-21 (b): VBR rejects the login."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import CaseInputs, Environment, judge, tool_budget
from cases.patterns import any_of
from evaluators import FactsPresent, ToolsNotCalled
from stand import environment

# ---- What VBR serves: the base stand - but vbr-mcp logs in with a password the mock rejects, as VBR rejects bad
# credentials (400 invalid_grant), so every tool call fails with vbr-mcp's "Could not authenticate with the VBR
# server: check credentials (VBR_USERNAME, VBR_PASSWORD)." before any route is read.

ENVIRONMENT: Environment = environment()

# ---- What a correct answer says.

EXPECTED = (
    "The job statuses cannot be retrieved: VBR rejected the login. Check the VBR_USERNAME and VBR_PASSWORD vbr-mcp is "
    "configured with (and that the account is not locked and its password has not expired)."
)
"""Ground truth for the judges."""

FACTS = {
    "authentication": any_of(r"authenticat", r"credential", r"log\s*-?\s*in", r"sign\s*-?\s*in", r"\bpassword\b"),
    "username": r"VBR_USERNAME",
    "password": r"VBR_PASSWORD",
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

_ALLOWED = (
    "It is acceptable, and not a violation, to give short diagnostic steps (for example checking that the account is "
    "not locked or that its password has not expired), or to say that the call was retried once."
)

GOOD = [
    (
        "I can't read the job statuses: VBR rejected the login (authentication failed). Check the VBR_USERNAME and "
        "VBR_PASSWORD that vbr-mcp is configured with, and that the account isn't locked or its password expired."
    ),
    (
        "Authentication to the VBR server failed, so no job data is available. Please fix the credentials in "
        "VBR_USERNAME / VBR_PASSWORD and try again."
    ),
]
"""Answers a correct agent could give: every fact must match each of them."""

BAD = {
    "authentication": "The VBR server could not be reached. Check VBR_USERNAME and VBR_PASSWORD... and VBR_BASE_URL.",
    "username": "Authentication failed: check the password in VBR_PASSWORD.",
}
"""Per fact, an answer that gets that fact wrong: the fact must not match it."""


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G1-21b",
        inputs=CaseInputs(
            question="What's the status of my backup jobs?",
            environment=ENVIRONMENT,
            vbr="wrong_password",
        ),
        expected_output=EXPECTED,
        metadata={"group": "G1", "base_stand": "1 (unreadable)"},
        evaluators=[
            # The call fails, so only a count that includes failed calls sees it; a diagnostic read on top is fine.
            ToolCorrectness(expected_tools=["get_job_states"], allow_extra=True, include_failed=True),
            *tool_budget(1),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "no_invented_statuses",
                "The output does not report the status, last result or schedule of any backup job: none could be "
                "retrieved.",
            ),
            _judge(
                "credentials_not_permissions",
                "The output presents the problem as failed authentication (wrong username or password), not as the "
                "account lacking permissions or the server being unreachable.",
            ),
        ],
    )
