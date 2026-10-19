# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G1-11: when the license expires, and whether that is a worry."""

from datetime import timedelta
from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import CaseInputs, judge, tool_budget
from cases.patterns import any_of, day, days
from evaluators import FactsPresent, ToolsNotCalled
from stand import environment
from stand.ids import T0
from stand.license import EXPIRES, LICENSE

# ---- What VBR serves: the base stand. The Subscription license expires on 2026-11-21: 44 days from T0 by vbr-mcp's
# count (daysToExpiry), 45 calendar days. What happens then (User Guide v13, license_grace): a Subscription license
# gets a 30-day grace period in which "you can perform all types of data protection and disaster recovery
# operations"; after it, "Veeam Backup & Replication stops processing workloads. All existing jobs fail ... However,
# you will be able to restore machine data from existing backups." License consumption is G2-11's question.

ENVIRONMENT = environment()

# ---- What a correct answer says, derived from the stand.

DAYS_LEFT = (EXPIRES - T0).days  # 44, how vbr-mcp computes daysToExpiry
_CALENDAR_DAYS = (EXPIRES.date() - T0.date()).days  # 45
GRACE_ENDS = EXPIRES + timedelta(days=30)

EXPECTED = (
    f"The {LICENSE.type} license ({LICENSE.edition}, licensed to {LICENSE.licensed_to}) is {LICENSE.status} and "
    f"expires on {EXPIRES:%Y-%m-%d}, in {DAYS_LEFT} days ({_CALENDAR_DAYS} calendar days); support expires on the "
    "same date. It is not urgent yet, but the renewal should be started now. Nothing stops on the expiry date: a "
    f"subscription license has a 30-day grace period (to about {GRACE_ENDS:%Y-%m-%d}) in which everything keeps "
    "working; if it is not renewed by then, jobs stop processing workloads and fail, while restores from existing "
    "backups remain possible."
)
"""Ground truth for the judges."""

FACTS = {
    "expires": day(EXPIRES, weekday=False),
    "days_left": any_of(days(DAYS_LEFT), days(_CALENDAR_DAYS), r"\bsix\s+weeks\b", r"(?<![\d.])6\s+weeks\b"),
    "renewal": any_of(
        r"\brenew",
        r"\bextend",
        r"\bnew\s+licen[cs]e",
        r"\b(?:contact|reach\s+out\s+to|talk\s+to)\s+(?:your\s+)?(?:veeam|reseller|partner|sales|account)",
    ),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match: the date, how far off it is, and that it
needs a renewal."""

_ALLOWED = (
    f"It is acceptable, and not a violation, to give the license type, edition, status and owner, to mention the "
    f"support ID {LICENSE.support_id} or that support expires the same day, to describe the grace period and what "
    "happens after it, or to present thresholds as a rule of thumb, such as fewer than 60 days left being a warning. "
    "Giving the license consumption is fine but not asked."
)

GOOD = [
    (
        f"Your Subscription license (Enterprise Plus, licensed to Lab Corp) is valid until **{EXPIRES:%Y-%m-%d}** - "
        f"{DAYS_LEFT} days from now by the backup server's clock. Not an emergency, but start the renewal now: after "
        "expiry there is a 30-day grace period, and if the license isn't renewed by then, jobs stop processing (restores "
        "keep working). Support expires the same day."
    ),
    (
        f"It expires on November 21st (in {_CALENDAR_DAYS} days). Should you worry? Plan it soon - contact your Veeam "
        "partner to extend the subscription; nothing stops on the day itself thanks to the grace period."
    ),
    (
        f"Expiration: 21 Nov 2026 ({DAYS_LEFT} day(s) left). Status: Valid. Recommendation: renew within the next few "
        "weeks."
    ),
]

BAD = {
    "expires": f"The license expires on 2026-12-21, in {DAYS_LEFT + 30} days; renew it in time.",
    "days_left": "The license expires on 2026-11-21; renew it in time.",
    "renewal": f"The license expires on 2026-11-21, in {DAYS_LEFT} days. There is nothing to do yet.",
}
"""Answers that each miss one fact."""


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G1-11",
        inputs=CaseInputs(
            question="When does our license expire, and should I be worried?",
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G1", "base_stand": "1.11"},
        evaluators=[
            ToolCorrectness(expected_tools=["get_license_status"], allow_extra=True),
            *tool_budget(1),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "days_from_server_clock",
                f"The number of days to expiry the output gives, if any, is {DAYS_LEFT} or {_CALENDAR_DAYS} (counting "
                "calendar days), as in the expected output. Do not use your own notion of the current date; "
                "compare only with the expected output.",
            ),
            _judge(
                "expiry_consequences",
                f"The output does not claim that backup jobs stop on {EXPIRES:%Y-%m-%d} itself (a 30-day grace "
                "period follows, in which everything keeps working), nor that restoring from existing backups "
                "becomes impossible after the license expires. Not describing the consequences at all is fine.",
            ),
            _judge(
                "support_is_not_job_stop",
                "The output does not claim that support expiry stops backup jobs from running, and keeps support "
                "expiry apart from license expiry.",
            ),
            _judge(
                "no_socket_model",
                "The output does not present the socket license model as being in use, nor as a problem: it is "
                "not used at all on this server. Saying that it is not used is fine.",
            ),
        ],
    )
