# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G2-07: is the configuration backup really healthy - and if not, why, and what to fix."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

import stand
from cases import CaseInputs, Environment, judge, tool_budget
from cases.patterns import any_of, day
from evaluators import FactsPresent, ToolsNotCalled
from stand.config_backup import CONFIG_BACKUP, LAST_SUCCESS
from stand.ids import R01, T0
from stand.jobs import JOBS, storage_data
from stand.repositories import REPOSITORY_STATES
from stand.sessions import CONFIG_WARNING, SESSIONS
from vbr_models.jobs import Job

# ---- What VBR serves: the base stand. The configuration backup is enabled (daily 10:00, to Repo-Main) but its
# encryption is off, and its last run was 2026-09-27 (a Warning: credentials skipped). That day encryption was turned
# on for the backup jobs, which put a password into the Password Manager, and VBR has not started a configuration
# backup since: it does not start one whose encryption is off then (User Guide v13, config_backup_encrypted; forum
# t24954 "suddenly there are no new configuration backups being performed"). There are no failed sessions to see.

ENVIRONMENT: Environment = stand.environment()

# ---- What a correct answer says, derived from the data above.

_CONFIG_SESSIONS = [s for s in SESSIONS if s.session_type == "ConfigurationBackup"]
_NEWEST = _CONFIG_SESSIONS[0]
_DAYS_SINCE = round((T0 - LAST_SUCCESS).total_seconds() / 86400)  # 10


def _encrypted(job: Job) -> bool:
    """Whether the job encrypts its backups."""
    data = storage_data(job)
    return bool(data and data.encryption.is_enabled)


_ENCRYPTED_JOBS = [job.name for job in JOBS if _encrypted(job)]
_REPO_MAIN_FREE = next(state.free_gb for state in REPOSITORY_STATES if state.id == R01)
assert _NEWEST.creation_time.date() == LAST_SUCCESS.date() and not CONFIG_BACKUP.encryption.is_enabled

EXPECTED = (
    "The configuration backup is not healthy. It is enabled and scheduled daily at 10:00 to Repo-Main, but it has "
    f"not run since {LAST_SUCCESS:%Y-%m-%d %H:%M} (its last successful backup, about {_DAYS_SINCE} days ago): there "
    "is no "
    "configuration backup session after that day - not even a failed one. The cause: the configuration backup's own "
    f"encryption is off, while backup jobs use password encryption ({', '.join(_ENCRYPTED_JOBS)}; turned on on "
    "2026-09-27), so the Password "
    "Manager holds a password - and then VBR does not start a configuration backup that is not encrypted. (Its last "
    f"run ended with the warning '{CONFIG_WARNING}') Space is not the cause: Repo-Main has {_REPO_MAIN_FREE:.0f} GB "
    "(about 1.8 TB) free. Fix: enable encryption of the configuration backup with a password (keep that password "
    "safe, or use password loss protection), then run the configuration backup and check that it succeeds. Do not "
    "remove the job passwords or turn off job encryption to get it running."
)
"""Ground truth for the judges."""

FACTS = {
    "last_success": day(LAST_SUCCESS, weekday=False),
    # no run since then - not "failing every day"
    "not_running": any_of(
        r"(no|not|n't|never|nothing)\s+([\w'-]+\s+){0,5}(run|ran|running|started|executed|created|completed|taken|made)\b",
        r"\bno\s+(new\s+|recent\s+)?([\w'-]+\s+){0,2}(sessions?|runs?|backups?)\b",
        r"\bstopped\s+(running|being\s+(created|run|taken)|appearing|happening)",
        r"\b(stale|overdue)\b",
        r"\bmissed\b[^.\n]{0,40}\b(runs?|backups?|sessions?)\b",
        r"\b(runs?|backups?|sessions?)\s+(\w+\s+){0,3}?(been\s+)?missed\b",
        r"\b(will|would|does|do|did)(n't|\s+not)\s+(even\s+)?(start|run|create|take)\b",
        r"\black\s+of\s+(any\s+)?(new\s+|recent\s+)?([\w'-]+\s+){0,2}(sessions?|runs?|backups?)\b",
    ),
    "cause_passwords": any_of(
        r"password\s+manager",
        r"(stored|saved|job|encryption)\s+passwords?",
        r"passwords?\s+([\w'-]+\s+){0,4}(stored|saved|exist|defined|configured)",
    ),
    "cause_job_encryption": any_of(
        r"(jobs?|backups?)\s+([\w'-]+\s+){0,4}(are\s+|is\s+)?encrypt",
        r"encrypt\w*\s+([\w'-]+\s+){0,4}(backup\s+)?jobs?",
    ),
    "fix_enable_encryption": any_of(
        r"enabl\w*\s+([\w'-]+\s+){0,5}encryption",
        r"encryption\s+([\w'-]+\s+){0,6}(enabl|turn\w*\s+on|on\b)",
        r"turn\w*\s+on\s+([\w'-]+\s+){0,5}encryption",
        r"encrypt\s+(the\s+)?config",
    ),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

_ALLOWED = (
    "It is acceptable, and not a violation, to quote the warning of the 2026-09-27 run, to remind that an "
    "unencrypted configuration backup does not contain credentials, to mention password loss protection, or to "
    "propose running the configuration backup once the fix is in place, as long as the output does not claim it ran "
    "it."
)

GOOD = [
    (
        "**No - the configuration backup is not healthy.**\n\n"
        "- It is enabled (daily at 10:00 to Repo-Main), but the last successful backup is from **2026-09-27 10:03** - "
        "about 10 days ago - and no configuration backup session has run since then.\n"
        "- **Why:** the configuration backup's encryption is **disabled**, while your backup jobs (Daily-VMs, SQL-Prod, "
        "Copy-to-DR, ...) use password encryption, so the Password Manager holds a password. In that state VBR does not "
        "start an unencrypted configuration backup at all - there are no failures to see, it just stops running.\n"
        "- Not a space problem: Repo-Main has ~1.8 TB free.\n\n"
        "**Fix:** enable encryption for the configuration backup (Configuration Backup settings, set a password and keep "
        "it safe), then run it once and check that it succeeds. Don't delete the job passwords or turn off job "
        "encryption."
    ),
    (
        "Not healthy. Last success: Sep 27 (10:03), nothing has run since - the scheduled 10:00 runs are not even "
        "attempted. Configuration backup encryption is off and the jobs are encrypted with a stored password, which "
        "makes VBR refuse to start an unencrypted config backup. Turn on encryption of the configuration backup with a "
        "password, then start a configuration backup to confirm."
    ),
    (
        "| Check | Result |\n|---|---|\n| Enabled / schedule | yes, daily 10:00 |\n| Last success | 27.09.2026 |\n"
        "| Runs since | none |\n| Encryption | off |\n\nThe job encryption enabled on 2026-09-27 put passwords into the "
        "Password Manager; VBR then won't run the configuration backup until its encryption is enabled. Enable "
        "configuration backup encryption and run it again."
    ),
    """## Verdict: **No \u2014 the configuration backup is unhealthy**

- Configuration backup is enabled and scheduled daily at **10:00 server time**.
- The last run was **September 27, 2026 at 10:00**, finishing with **Warning** at 10:03.
- VBR\u2019s current server time is **October 7, 2026 at 09:00**, so **nine scheduled runs have been missed** since then.
- Every recent recorded run warned:
  **\u201cSkipping credentials backup because the encryption is disabled.\u201d**
- Configuration-backup encryption is currently **disabled**.

### Why this is happening

Several jobs use encrypted backups and a stored encryption password. Once VBR\u2019s Password Manager contains passwords, VBR will not start an unencrypted configuration backup. That explains why the daily sessions stopped appearing after September 27.

Even the older warning-state backups are incomplete for disaster recovery: they contain configuration data but omit stored credentials and encryption keys. Restoring VBR from one would require manually re-entering every credential, and encrypted workload backups could become unrecoverable if their encryption password/key is unavailable separately.

## Exactly what to fix

In the VBR console:

1. Open **Configuration Backup Settings**.
2. **Enable encryption**.
3. Select or create a strong encryption password.
4. Store that password outside the VBR server in your password vault/recovery documentation.
5. Consider changing the target from **Repo-Main** to **Repo-DR**:
   - Current target **Repo-Main** is online with **1.84 TB free (18%)**, so capacity is not currently blocking it.
   - **Repo-DR** is online with **7 TB free (45.6%)** and offers better failure-domain separation.
   - Do **not** select the SOBR itself; configuration backup cannot target a scale-out repository.
6. Keep at least the configured **10 restore points**, or increase retention according to your DR policy.
7. Save the settings and run a configuration backup immediately.
8. Verify that the new `ConfigurationBackup` session finishes with **Success**, not Warning, and confirm daily sessions resume.

Starting it now without first enabling encryption would not resolve the underlying problem.""",  # a real answer
]

BAD = {
    "not_running": "Not healthy: every daily configuration backup since 2026-09-28 has failed because the Password "
    "Manager holds passwords and the backup jobs are encrypted. Enable encryption for the configuration backup. Last "
    "success: 2026-09-27.",
    "fix_enable_encryption": "Not healthy: no configuration backup since 2026-09-27 because job encryption put "
    "passwords into the Password Manager. Delete those passwords and turn off job encryption.",
    "cause_passwords": "Not healthy: it has not run since 2026-09-27. Repo-Main may be full; enable encryption and "
    "free some space.",
}


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G2-07",
        inputs=CaseInputs(
            question="Is our configuration backup actually healthy? If not, why, and what exactly should I fix?",
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G2", "base_stand": "1.12, 1.3"},
        evaluators=[
            # get_config_backup_status is the answer; list_sessions (no run since 09-27), list_jobs (which jobs are
            # encrypted) and list_repositories (the target's space) are reads on top of it.
            ToolCorrectness(expected_tools=["get_config_backup_status"], allow_extra=True),
            *tool_budget(4),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "not_called_healthy",
                "The output says the configuration backup is not healthy. It does not call it healthy or working "
                "because it is enabled or because a last successful time exists.",
            ),
            _judge(
                "cause_explained",
                "The output gives as the cause that the configuration backup's own encryption is off while the "
                "Password Manager holds a password (from the job encryption turned on around 2026-09-27), and that "
                "VBR therefore does not run the configuration backup.",
            ),
            _judge(
                "no_invented_failures",
                "The output does not claim that configuration backup sessions failed after 2026-09-27, and does not "
                "quote an error message from such a session: there are none - the backup has not run since then.",
            ),
            _judge(
                "no_harmful_fix",
                "The output does not recommend removing passwords from the Password Manager or turning off the "
                "encryption of backup jobs to get the configuration backup running.",
            ),
            _judge(
                "space_not_blamed",
                "The output does not blame free space in the repository for the problem.",
            ),
            _judge(
                "no_backup_started",
                "The output does not claim that it started or ran a configuration backup; proposing it to the user "
                "is fine.",
            ),
        ],
    )
