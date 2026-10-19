# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G1-21 (d): vbr-mcp does not trust the VBR server's TLS certificate."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import CaseInputs, Environment, judge, tool_budget
from cases.patterns import any_of
from evaluators import FactsPresent, ToolsNotCalled
from stand import environment

# ---- What VBR serves: the base stand, over HTTPS with a self-signed certificate - what a VBR server installs by
# default (run.py, vbr="untrusted_tls"). vbr-mcp verifies TLS by default (VBR_VERIFY_TLS=true), so the handshake fails
# before any route is read, and every tool call fails with vbr-mcp's "Could not verify the TLS certificate of the VBR
# server at <url>: it is not trusted on this machine (often a self-signed certificate). vbr-mcp checks certificates
# against its own CA bundle, not the operating system's certificate store: point SSL_CERT_FILE at a PEM file with the
# server's certificate or its CA, or set VBR_VERIFY_TLS=false if you trust this server."

ENVIRONMENT: Environment = environment()

# ---- What a correct answer says.

EXPECTED = (
    "The job statuses cannot be retrieved: vbr-mcp does not trust the VBR server's TLS certificate (VBR uses a "
    "self-signed certificate by default). Make vbr-mcp trust it: point SSL_CERT_FILE at a PEM file with the server's "
    "certificate or the CA that issued it (vbr-mcp does not read the operating system's certificate store); or, for a "
    "server you trust such as a lab, set VBR_VERIFY_TLS=false."
)
"""Ground truth for the judges."""

FACTS = {
    "certificate": any_of(r"\bcertificate", r"\btls\b", r"\bssl\b"),
    "fix": any_of(
        r"VBR_VERIFY_TLS",
        r"SSL_CERT_FILE",
        r"\btrust(ed)?\s+(the\s+)?(server'?s?\s+|vbr'?s?\s+|its\s+)?(certificate|ca\b|cert\b)",
        r"\b(install|import|add)\s+(the\s+)?(server'?s?\s+|vbr'?s?\s+|its\s+)?(certificate|ca\b|cert\b)",
        r"\b(certificate|ca|cert)\s+(as\s+)?trusted\b",
        r"\btrusted\s+(root|ca|certificate)",
    ),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

_ALLOWED = (
    "It is acceptable, and not a violation, to explain that a VBR server comes with a self-signed certificate, to "
    "suggest replacing it with one from a trusted CA, or to say that the call was retried once."
)

GOOD = [
    (
        "I can't read the job statuses: the connection fails because vbr-mcp doesn't trust the VBR server's TLS "
        "certificate - most likely the self-signed one VBR installs by default. Install that certificate (or its CA) as "
        "trusted on this machine, or, if this is a lab server you trust, set VBR_VERIFY_TLS=false."
    ),
    (
        "TLS verification of the VBR server failed (untrusted, probably self-signed certificate). Either import the "
        "server's certificate into the trusted store or disable verification with VBR_VERIFY_TLS=false for a trusted "
        "lab server."
    ),
    (
        "No job statuses: vbr-mcp refuses the VBR server's certificate (self-signed by default). Set SSL_CERT_FILE to a "
        "PEM file with that certificate or its CA - vbr-mcp doesn't use the Windows/macOS certificate store."
    ),
]
"""Answers a correct agent could give: every fact must match each of them."""

BAD = {
    "certificate": "The VBR server could not be reached; check VBR_BASE_URL and port 9419.",
    "fix": "The VBR server's certificate could not be verified, so I can't show the job statuses.",
}
"""Per fact, an answer that gets that fact wrong: the fact must not match it."""


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G1-21d",
        inputs=CaseInputs(
            question="What's the status of my backup jobs?",
            environment=ENVIRONMENT,
            vbr="untrusted_tls",
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
                "tls_not_misdiagnosed",
                "The output presents the problem as the VBR server's TLS certificate not being trusted, not as wrong "
                "credentials, missing permissions, an unreachable or stopped server, or a wrong address.",
            ),
            _judge(
                "verification_off_with_care",
                "If the output suggests turning TLS verification off (VBR_VERIFY_TLS=false), it limits that to a "
                "server the user trusts (for example a lab) or presents trusting the certificate (SSL_CERT_FILE, a "
                "trusted certificate) as the better fix. Suggesting only to trust or install the certificate is fine.",
            ),
        ],
    )
