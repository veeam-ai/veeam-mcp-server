# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G1-14: whether email notifications actually work."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import CaseInputs, Environment, judge, tool_budget
from cases.patterns import any_of
from evaluators import FactsPresent, ToolsNotCalled
from stand import environment, options

# ---- What VBR serves: the base stand. General options (1.13) have SMTP filled in and failure notifications ticked,
# but the master switch, notificationEnabled, is off: VBR sends no email at all until it is on ("Reports are sent only
# after you enable and configure the global email notification settings", User Guide v13, job_email_notifications).

ENVIRONMENT: Environment = environment()

# ---- What a correct answer says, derived from the data above.

_OPTIONS = options.GENERAL_OPTIONS
_EMAIL = _OPTIONS.email_settings
assert _EMAIL is not None
_SMTP = _EMAIL.advanced_smtp_options

EXPECTED = (
    "No: email notifications are not being sent. SMTP is configured - server "
    f"{_EMAIL.smtp_server_name}:{_SMTP.port} with SSL and authentication with stored credentials, from {_EMAIL.from_} "
    f"to {_EMAIL.to}, and notify on failure is on - but the master switch notificationEnabled is off, so VBR sends "
    "no email at all until it is turned on."
)
"""Ground truth for the judges."""

FACTS = {
    # "notificationEnabled is false", "the master switch is off", "Email notifications are currently disabled in VBR",
    # "the global e-mail notification setting is off", "| Email notifications (global) | Disabled |"
    "master_switch_off": any_of(
        r"notificationEnabled",
        r"\b(master|global|main|overall|top-level)\s+(e-?mail\s+)?(notifications?\s+)?(toggle|switch|setting|option|"
        r"checkbox|check\s+box|flag)\b",
        r"\benable\s+e-?mail\s+notifications\b",
        r"\b(e-?mail\s+)?notifications?\s+(are|is)\s+(currently\s+|globally\s+|still\s+|actually\s+)?(disabled|"
        r"turned\s+off|switched\s+off|off|not\s+enabled)\b",
        r"\b(e-?mail\s+)?notifications?\s+(are|is|have|has)(n't|\s+not)\s+(currently\s+|globally\s+|yet\s+)?(been\s+)?"
        r"(enabled|turned\s+on|switched\s+on|on|active)\b",
        r"\b(e-?mail\s+)?notifications?\s+(\w+\s+){0,2}?(disabled|turned\s+off|switched\s+off)\b",
        r"\b(e-?mail\s+)?notifications?\W{1,5}(disabled|off)\b",
        r"\bnotifications?\b[^\n|]{0,30}\|\s*(disabled|off|no)\b",
        r"\bglobally\s+(disabled|turned\s+off|switched\s+off|off)\b",
        r"\b(sending|e-?mail)\s+(is\s+|are\s+)?(disabled|turned\s+off|switched\s+off)\b",
    ),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

_ALLOWED = (
    "It is acceptable, and not a violation, to name the SMTP server, its port, the sender or the recipient, to say "
    "which results trigger a notification, to mention that syslog goes to siem.lab.local over UDP (not encrypted) "
    "or that SNMP is off, to give the storage space threshold of 10%, or to explain how to turn the master switch "
    "on in the console."
)

GOOD = [
    (
        "Not right now. SMTP is configured (smtp.lab.local:587, SSL, authenticated) and job failures are set to notify "
        "backup-admins@lab.local, but the master switch - notificationEnabled - is off, so VBR doesn't send any email. "
        'Turn on "Enable e-mail notifications" in General Options to start receiving alerts.'
    ),
    (
        "No. Email notifications are currently disabled in VBR: the global e-mail notification setting is off. "
        "Everything else is ready - SMTP server smtp.lab.local, sender vbr-lab01@lab.local, failure and warning alerts "
        "selected - so you only need to switch it on."
    ),
    (
        "| Item | Status |\n|---|---|\n| Email notifications (global) | Disabled |\n| SMTP server | smtp.lab.local, port "
        "587, SSL |\n| Notify on failure | Yes |\n\nSo no alerts will arrive until notifications are enabled."
    ),
]
"""Answers a correct agent could give: every fact must match each of them."""

BAD = {
    "master_switch_off": "Yes - email notifications are set up: SMTP smtp.lab.local:587 with SSL and authentication, "
    "and alerts on failure go to backup-admins@lab.local.",
}
"""Per fact, an answer that gets that fact wrong: the fact must not match it."""


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G1-14",
        inputs=CaseInputs(
            question="Are email notifications set up so we get alerted when a job fails?",
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G1", "base_stand": "1.13"},
        evaluators=[
            ToolCorrectness(expected_tools=["get_general_options"], allow_extra=True),
            *tool_budget(1),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "verdict_not_sent",
                "The output's verdict is that failure alerts are not being emailed now, because the master email "
                "notification switch is off. It does not say that notifications work because SMTP and recipients "
                "are filled in.",
            ),
            _judge(
                "smtp_not_blamed",
                "The output does not claim that SMTP is missing or misconfigured (no server, no port, no credentials, "
                "no recipient): those settings are filled in, and only the master switch is off.",
            ),
        ],
    )
