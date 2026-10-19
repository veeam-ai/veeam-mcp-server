# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G1-13: configuration backup — enabled, encrypted, last success."""

from datetime import timedelta
from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import CaseInputs, Environment, judge, tool_budget
from cases.patterns import any_of, day
from evaluators import FactsPresent, ToolsNotCalled
from stand import config_backup, environment
from stand.ids import T0

# ---- What VBR serves: the base stand. Configuration backup (1.12) is enabled, daily at 10:00, unencrypted, and last
# ran on 2026-09-27: job encryption put a password into the Password Manager that day, and VBR has not started an
# unencrypted configuration backup since (User Guide v13, config_backup_encrypted) - no session after 09-27, failed
# or otherwise. Why it stopped is G2-07's question; this one asks only what the settings and the last success say.

ENVIRONMENT: Environment = environment()

# ---- What a correct answer says, derived from the data above.

CONFIG = config_backup.CONFIG_BACKUP
LAST_SUCCESS = config_backup.LAST_SUCCESS
_DAYS_SINCE_SUCCESS = (T0 - LAST_SUCCESS) / timedelta(days=1)  # ≈ 9.9

EXPECTED = (
    f"Configuration backup is enabled: daily at 10:00, keeping {CONFIG.restore_points_to_keep} restore points, to "
    "Repo-Main. It is not encrypted, so it stores no credentials or encryption keys: after restoring the "
    "configuration from it, every credential has to be re-entered and encrypted backups cannot be opened without "
    f"their passwords. It last succeeded on {LAST_SUCCESS:%Y-%m-%d} at {LAST_SUCCESS:%H:%M} (with the usual warning "
    f"that credentials were skipped), about {_DAYS_SINCE_SUCCESS:.0f} days ago - stale for a daily schedule: no "
    "configuration backup has run since."
)
"""Ground truth for the judges."""

FACTS = {
    # "is enabled", "Enabled: Yes", "| Enabled | Yes |", "yes, it is enabled", "enabled, daily at 10:00"
    "enabled": any_of(
        r"\b(backup|job|it|which|this)(\s+is|'s|\s+has\s+been)\s+(currently\s+|still\s+)?(enabled|on|turned\s+on|active|"
        r"scheduled)\b",
        r"\bit\s+is\s+(currently\s+)?enabled\b",
        r"\benabled\W{1,5}(yes|true|on)\b",
        r"\b(configuration\s+backup|config\s+backup|status|state)(\s+job)?\W{1,5}(is\s+)?(enabled|on|active)\b",
        r"\byes\b[^\n]{0,60}\benabled\b",
        r"\benabled\b[^\n]{0,40}\b(daily|every\s+day|at\s+10)",
    ),
    "unencrypted": any_of(
        r"\bnot\s+encrypted\b",
        r"\bunencrypted\b",
        r"\bisn't\s+encrypted\b",
        r"\bencrypt(ed|ion)\W+(\w+\W+){0,3}(disabled|off|not\s+enabled|false|no)\b",
        r"\bencryption\s+(is\s*n[o']?t|isn't|wasn't)\s+(enabled|on|turned\s+on|configured|set)\b",
        r"\b(no|without)\s+encryption\b",
    ),
    "last_success": day(LAST_SUCCESS, weekday=False),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

_ALLOWED = (
    "It is acceptable, and not a violation, to give the schedule, the number of restore points kept or the target "
    "repository, to say how many days ago the last success was, to check the configuration backup sessions and say "
    "that none has run since 2026-09-27, to mention that its last run ended with a Warning because credentials were "
    "skipped, to say that VBR does not start an unencrypted configuration backup once the Password Manager holds a "
    "password, or to recommend enabling encryption (as advice, not as something done)."
)

GOOD = [
    (
        f"Configuration backup is enabled: it runs daily at 10:00, keeps {CONFIG.restore_points_to_keep} restore points "
        "and writes to Repo-Main. It is not encrypted (encryption is disabled), so it does not contain stored credentials "
        "or encryption keys - after restoring the configuration you would have to re-enter every credential. Its last "
        "successful run was on 2026-09-27 at 10:03, about 10 days ago, which is stale for a daily schedule."
    ),
    (
        "| Setting | Value |\n|---|---|\n| Enabled | Yes (daily at 10:00, 10 restore points, Repo-Main) |\n"
        "| Encrypted | No |\n| Last successful backup | Sep 27, 2026 10:03 (about 10 days ago) |\n\n"
        "Because encryption is off, credentials and keys are skipped in the backup. Consider enabling encryption with a "
        "password."
    ),
    (
        "- Enabled: yes\n- Encryption: off - the configuration backup doesn't include credentials or keys; enable it "
        "with a password\n- Last success: 27 September 2026, 10:03. Nothing has run since, although it is scheduled "
        "every day at 10:00."
    ),
]
"""Answers a correct agent could give: every fact must match each of them."""

BAD = {
    "enabled": "Configuration backup is disabled, and encryption is not enabled either. The last successful run was "
    "2026-09-27 at 10:03.",
    "unencrypted": "Configuration backup is enabled and encrypted with a password. It last succeeded on 2026-09-27.",
    "last_success": "Configuration backup is enabled but not encrypted. It last succeeded yesterday at 10:00.",
}
"""Per fact, an answer that gets that fact wrong: the fact must not match it."""


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G1-13",
        inputs=CaseInputs(
            question="Is configuration backup enabled, is it encrypted, and when did it last succeed?",
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G1", "base_stand": "1.12"},
        evaluators=[
            # get_config_backup_status is the answer; list_sessions (the latest runs) and get_server_status (what
            # "now" is) are reads the case allows on top of it.
            ToolCorrectness(expected_tools=["get_config_backup_status"], allow_extra=True),
            *tool_budget(2),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "unencrypted_risk",
                "The output says that configuration backup encryption is off and does not present that as harmless "
                "(e.g. by claiming the backup still holds the credentials and keys). Naming the consequence or "
                "recommending encryption is welcome, not required: the question only asks whether it is encrypted.",
            ),
            _judge(
                "no_false_health",
                "The output does not call the configuration backup healthy or working, and does not claim that it "
                "ran or succeeded recently (today, yesterday, or on any day after 2026-09-27).",
            ),
            _judge(
                "no_invented_failures",
                "The output does not claim that configuration backup runs after 2026-09-27 failed or that there are "
                "failed configuration backup sessions: none has run since then. Saying that it has not run since, "
                "and why, is fine.",
            ),
        ],
    )
