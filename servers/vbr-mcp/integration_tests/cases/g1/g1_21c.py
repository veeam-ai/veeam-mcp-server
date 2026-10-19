# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G1-21 (c): the VBR server accepts the connection but does not answer in time."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import TIMEOUT_SEC, CaseInputs, Environment, judge, tool_budget
from cases.patterns import any_of
from evaluators import FactsPresent, ToolsNotCalled

# ---- What VBR serves: nothing in time. vbr-mcp is pointed at a server that accepts the TCP connection and never
# answers - a hung REST service, an overloaded backup server, a firewall that drops instead of refusing - with its
# request timeout set to TIMEOUT_SEC (vbr="timeout"), so every tool call fails with vbr-mcp's "The VBR server at <url>
# did not respond within 3 s (VBR_REQUEST_TIMEOUT_SEC). It may be overloaded, or a firewall may be dropping the
# connection."

ENVIRONMENT: Environment = {}

# ---- What a correct answer says.

EXPECTED = (
    "The job statuses cannot be retrieved: the VBR server accepted the connection but did not respond within the "
    f"{TIMEOUT_SEC}-second request timeout. The backup server or its REST API service may be overloaded or hung, or a "
    "firewall may be dropping the traffic; check the server and the Veeam Backup REST API service, and if the server "
    "is just slow, raise VBR_REQUEST_TIMEOUT_SEC."
)
"""Ground truth for the judges."""

FACTS = {
    "timed_out": any_of(
        r"\b(did\s*n[o']?t|does\s*n[o']?t|is\s*n[o']?t|was\s*n[o']?t|has\s*n[o']?t|have\s*n[o']?t|never|failed\s+to)\s+"
        r"(yet\s+|been\s+)?(respond|answer|repl(y|ied))",
        r"\bnot\s+respond(ing)?\b",
        r"\bunresponsive\b",
        r"\bno\s+(reply|answer)\b",
        r"\bstopped\s+responding\b",
        r"\btime[ds]?[\s-]*out\b",
        r"\btimeout\b",
        r"\bno\s+response\b",
        r"\btook\s+too\s+long\b",
        r"\bin\s+time\b",
    ),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

_ALLOWED = (
    "It is acceptable, and not a violation, to name VBR_REQUEST_TIMEOUT_SEC, to suggest checking the load of the "
    "backup server, the Veeam Backup REST API service or a firewall, to suggest raising the timeout if the server is "
    "merely slow, or to say that the call was retried once."
)

GOOD = [
    (
        "I couldn't get the job statuses: the VBR server accepted the connection but did not respond within 3 seconds "
        "(VBR_REQUEST_TIMEOUT_SEC). It may be overloaded, its REST API service may be hung, or a firewall may be dropping "
        "the traffic - check the server, and raise the timeout if it is just slow."
    ),
    (
        "The request to VBR timed out, so no job data came back. Please check that the backup server and the Veeam "
        "Backup REST API service are healthy."
    ),
    (
        "The backup server accepted the connection but never answered within 3 seconds - it looks unresponsive. "
        "Check the server's load and the Veeam Backup REST API service."
    ),
]
"""Answers a correct agent could give: every fact must match each of them."""

BAD = {
    "timed_out": "Authentication with the VBR server failed: check VBR_USERNAME and VBR_PASSWORD.",
}
"""Per fact, an answer that gets that fact wrong: the fact must not match it."""


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G1-21c",
        inputs=CaseInputs(
            question="What's the status of my backup jobs?",
            environment=ENVIRONMENT,
            vbr="timeout",
        ),
        expected_output=EXPECTED,
        metadata={"group": "G1", "base_stand": "none"},
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
                "timeout_not_misdiagnosed",
                "The output presents the problem as the VBR server not answering in time (busy or hung server or "
                "service, or a firewall dropping the traffic). It does not blame wrong credentials or permissions, "
                "and does not state as a certainty that the address is wrong or that the host is down.",
            ),
        ],
    )
