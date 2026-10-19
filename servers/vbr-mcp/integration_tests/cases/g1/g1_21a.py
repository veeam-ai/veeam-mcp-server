# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G1-21 (a): the VBR server cannot be reached."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import CaseInputs, Environment, judge, tool_budget
from cases.patterns import any_of
from evaluators import FactsPresent, ToolsNotCalled

# ---- What VBR serves: nothing. vbr-mcp is pointed at a port nothing listens on, so every tool call fails before any
# route is read, with vbr-mcp's "Could not reach the VBR server at <url>. Check VBR_BASE_URL, that the host name
# resolves, and that the VBR REST API port (9419 by default) is open from this machine."

ENVIRONMENT: Environment = {}

VBR_REST_PORT = 9419

# ---- What a correct answer says.

EXPECTED = (
    "The job statuses cannot be retrieved: the VBR server could not be reached. Check that VBR_BASE_URL points at the "
    f"backup server, that its host name resolves and the network path to it is open, and that port {VBR_REST_PORT} "
    "(the VBR REST API) is reachable and the Veeam Backup REST API service is running."
)
"""Ground truth for the judges."""

FACTS = {
    "unreachable": any_of(
        r"(could\s*not|couldn'?t|cannot|can'?t|unable\s+to|failed\s+to|not\s+able\s+to)\s+(be\s+)?(reach|connect|contact|"
        r"establish\s+(a\s+)?connection|get\s+through)",
        r"\bunreachable\b",
        r"\bnot\s+reachable\b",
        r"\bconnection\s+(\w+\s+){0,5}?(error|failure|failed|was\s+refused|refused|timed\s+out|could\s*n[o']?t)",
        r"\b(connecting|connection\s+attempts?)\s+(\w+\s+){0,4}?failed\b",
        r"\b(isn't|is\s+not|wasn't|was\s+not|aren't|are\s+not)\s+(responding|reachable|available|answering)\b",
        r"\b(did|does)(n't|\s+not)\s+(respond|answer|reply)\b",
        r"\bnot\s+responding\b",
        r"\bno\s+(response|answer|connection)\b",
    ),
    "base_url": r"VBR_BASE_URL",
    "port": rf"(?<!\d){VBR_REST_PORT}(?!\d)",
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

_ALLOWED = (
    "It is acceptable, and not a violation, to give short diagnostic steps (for example checking that the Veeam Backup "
    "REST API service is running, DNS, a firewall, or testing the URL in a browser), or to say that the call was "
    "retried once."
)

GOOD = [
    (
        "I couldn't get the job statuses: the VBR server could not be reached. Check that VBR_BASE_URL points at your "
        "backup server, that the name resolves, and that port 9419 (the VBR REST API) is open from this machine."
    ),
    (
        "The VBR server isn't responding at the configured address, so I can't read any job status. Please verify "
        "VBR_BASE_URL and that the REST API port 9419 and the Veeam Backup REST API service are up."
    ),
    (
        "I wasn't able to connect to the VBR server: the connection to it failed, so there is no job status to show. "
        "Make sure VBR_BASE_URL is right and that port 9419 is open."
    ),
    "No response from VBR - the server did not respond at all. Check VBR_BASE_URL, DNS and port 9419.",
]
"""Answers a correct agent could give: every fact must match each of them."""

BAD = {
    "unreachable": "All your backup jobs are fine: VBR_BASE_URL is set and port 9419 answered.",
    "base_url": "The VBR server could not be reached. Check the network and port 9419.",
    "port": "The VBR server could not be reached; check VBR_BASE_URL.",
}
"""Per fact, an answer that gets that fact wrong: the fact must not match it."""


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G1-21a",
        inputs=CaseInputs(
            question="What's the status of my backup jobs?",
            environment=ENVIRONMENT,
            vbr="unreachable",
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
                "connection_not_credentials",
                "The output presents the problem as the VBR server being unreachable, not as wrong credentials, "
                "failed authentication, missing permissions or a certificate problem.",
            ),
        ],
    )
