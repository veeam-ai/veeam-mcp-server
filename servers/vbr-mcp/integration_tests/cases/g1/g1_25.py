# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G1-25: the license shows Expired — are backups still running, and what happens next (the grace period)."""

from datetime import UTC, datetime, timedelta
from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import CaseInputs, Environment, judge, tool_budget
from cases.patterns import any_of, day, days
from evaluators import FactsPresent, ToolsNotCalled
from stand import environment, license
from stand.ids import T0

# ---- What VBR serves: the base stand, with its Subscription license expired on 2026-10-01. A paid license gets a
# grace period: for a Subscription 30 days, during which "you can perform all types of data protection and disaster
# recovery operations"; if it is not updated by then, VBR "stops processing workloads. All existing jobs fail with
# the Error status. However, you will be able to restore machine data from existing backups" (User Guide v13,
# license_grace). Last night's jobs ran as usual: the server is six days into its grace period.

EXPIRED = datetime(2026, 10, 1, tzinfo=UTC)
GRACE_DAYS = 30
GRACE_ENDS = (EXPIRED + timedelta(days=GRACE_DAYS)).date()

LICENSE = license.LICENSE.model_copy(
    update={"status": "Expired", "expiration_date": EXPIRED, "support_expiration_date": EXPIRED}
)

ENVIRONMENT: Environment = environment(license=LICENSE)

# ---- What a correct answer says, derived from the data above.

_DAYS_LEFT = (GRACE_ENDS - T0.date()).days  # 24

EXPECTED = (
    f"The Subscription license expired on {EXPIRED:%Y-%m-%d}, six days ago, and VBR is now in its {GRACE_DAYS}-day "
    f"grace period: every job and restore keeps working - last night's jobs ran as usual. The grace period ends "
    f"around {GRACE_ENDS:%Y-%m-%d} (about {_DAYS_LEFT} days from now). If the license is not renewed and installed "
    "by then, VBR stops processing workloads and every job fails, though restoring from the existing backups stays "
    "possible. Renew the subscription and install the new license file now."
)
"""Ground truth for the judges."""

FACTS = {
    "still_running": any_of(
        r"\bstill\s+(run|work|back|process|operat|function|protect)",
        r"\bcontinu\w*\s+(to\s+)?(run|work|back|process|operat|function)",
        r"\bkeeps?\s+(on\s+)?(running|working|backing|processing)",
        r"\b(not|n't)\s+(yet\s+)?(been\s+)?(stopped|affected|impacted|blocked|interrupted)",
        r"\b(running|working|processed|ran|run|runs|worked|works)\s+(normally|as\s+usual|as\s+normal|fine)",
        r"\bno\s+(impact|effect)\s+(yet|for\s+now|on\s+(your\s+)?(jobs|backups))",
        r"\byes\b[^\n]{0,60}\b(running|run|work)",
    ),
    "grace": r"\bgrace\b",
    "grace_end": any_of(
        day(GRACE_ENDS, weekday=False), day(GRACE_ENDS - timedelta(days=1), weekday=False), days(_DAYS_LEFT, slack=1)
    ),
    "after_grace": any_of(
        r"\bjobs?\s+(will\s+)?(start\s+to\s+|begin\s+to\s+)?(fail|stop)",
        r"\bstops?\s+processing\b",
        r"\bno\s+longer\s+(run|process|back|protect)",
        r"\bbackups?\s+(jobs?\s+)?(will\s+)?(stop|fail|cease)",
        r"\bstop\s+(running|working|backing\s+up|processing)",
        r"\b(processing|backups?|jobs?|protection)\b[^.\n]{0,40}\b(stops?|fails?|restricted|ceases?|halts?)\b",
    ),
    "renew": any_of(
        r"\brenew",
        r"\binstall\w*\s+(a\s+|the\s+)?(new|renewed|updated|valid)\s+licen",
        r"\bupdate\s+the\s+licen",
        r"\bnew\s+licen[sc]e\s+(file|key)",
        r"\breplace\s+the\s+licen",
    ),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

_ALLOWED = (
    "It is acceptable, and not a violation, to say the license expired 6 or 7 days ago (the tool's daysToExpiry is "
    "-7), to give the license's edition, instances or support ID, to check the jobs' last results to confirm they "
    "still run, or to mention the Community Edition as the free alternative."
)

GOOD = [
    (
        "Yes - backups are still running. The Subscription license expired on 2026-10-01 and VBR is in its 30-day grace "
        "period, during which everything keeps working (last night's jobs ran). The grace period ends around "
        "2026-10-31, about 24 days from now. If you haven't installed a renewed license by then, VBR stops processing "
        "workloads and all jobs fail - you could still restore from existing backups. Renew the subscription and install "
        "the new license file."
    ),
    (
        "| Item | Value |\n|---|---|\n| License | Subscription, Expired (since Oct 1, 2026) |\n| Grace period | 30 days, "
        "until Oct 31 |\n| Backups now | continue to run normally |\n| After the grace period | jobs will fail; restore "
        "from existing backups still works |\n\nAction: renew the license."
    ),
    (
        "Yes. Your jobs haven't stopped: the license expired on 2026-10-01 and VBR is in its 30-day grace period, so "
        "last night's backups ran as usual. The grace period ends around 2026-10-31; after that VBR stops processing "
        "workloads. Renew the subscription before then."
    ),
]
"""Answers a correct agent could give: every fact must match each of them."""

BAD = {
    "still_running": "Your license expired on 2026-10-01, so backups have stopped. Renew it before the grace period "
    "ends on 2026-10-31; after that jobs will fail.",
    "grace": "The license expired on 2026-10-01. Backups still run, but jobs will fail once it is enforced - renew "
    "it before 2026-10-31.",
    "grace_end": "Backups still run during the grace period, which ends on 2026-11-30; then jobs will fail. Renew it.",
    "after_grace": "Backups still run: the license is in its grace period until 2026-10-31. Renew it soon.",
    "renew": "Backups still run during the grace period until 2026-10-31; after that jobs will fail.",
}
"""Per fact, an answer that gets that fact wrong: the fact must not match it."""


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G1-25",
        inputs=CaseInputs(
            question="Our VBR license shows Expired. Are our backups still running, and what happens next?",
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G1", "base_stand": "1.11 + delta"},
        evaluators=[
            # get_license_status is the answer; get_job_states or list_sessions (did last night's jobs run) and
            # get_server_status are reads the case allows on top.
            ToolCorrectness(expected_tools=["get_license_status"], allow_extra=True),
            *tool_budget(2),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "not_stopped_yet",
                "The output does not say that backups have already stopped or that jobs are failing now because of "
                "the license: during the grace period they keep running.",
            ),
            _judge(
                "restores_remain",
                "The output does not say that restores will become impossible after the grace period: restoring from "
                "existing backups stays possible. Not mentioning restores is fine.",
            ),
            _judge(
                "grace_length",
                f"The output gives the license's expiration as {EXPIRED:%Y-%m-%d} and a grace period of {GRACE_DAYS} "
                f"days ending around {GRACE_ENDS:%Y-%m-%d}; it does not claim another length or end date.",
            ),
        ],
    )
