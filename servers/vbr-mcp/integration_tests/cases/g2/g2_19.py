# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G2-19: the configuration backup warns every day: is it working, and can the warning be ignored.

The most common configuration backup "problem" in the field: with no password in the Password Manager, an unencrypted
configuration backup runs fine but finishes with "Skipping credentials backup because the encryption is disabled"
(forum t74377). It is working, but the backup holds no credentials: after a configuration restore every one of them
must be entered again, and encrypted data has no keys (User Guide v13, config_backup_encrypted). The fix is to encrypt
the configuration backup; it is neither a failure nor safe to ignore without that caveat.
"""

from datetime import timedelta
from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

import stand
from cases import CaseInputs, Environment, judge, tool_budget
from cases.patterns import any_of, day, near
from evaluators import FactsPresent, ToolsNotCalled
from stand.config_backup import CONFIG_BACKUP
from stand.ids import at, mnemonic
from stand.jobs import JOBS, NOT_ENCRYPTED
from stand.sessions import CONFIG_WARNING, SESSIONS, session
from vbr_models.config_backup import ConfigBackupLastSuccessful
from vbr_models.jobs import BackupCopyJob, BackupJob, FileBackupJob, Job, ObjectStorageBackupJob
from vbr_models.jobs import WindowsAgentWorkstationPolicy as AgentPolicy

# ---- What VBR serves: the base stand, but no job encrypts its backups - so the Password Manager holds no password,
# and the daily configuration backup has kept running: every day at 10:00 through 10-06, each with the Warning.


def _unencrypted(job: Job) -> Job:
    """``job`` with its backup encryption off; the setting sits in a different subtree per job type."""
    match job:
        case BackupJob() | AgentPolicy():
            settings = job.storage.advanced_settings
            assert settings is not None
            return job.model_copy(
                update={
                    "storage": job.storage.model_copy(
                        update={"advanced_settings": settings.model_copy(update={"storage_data": NOT_ENCRYPTED})}
                    )
                }
            )
        case BackupCopyJob():
            settings = job.target.advanced_settings
            assert settings is not None
            return job.model_copy(
                update={
                    "target": job.target.model_copy(
                        update={"advanced_settings": settings.model_copy(update={"storage_data": NOT_ENCRYPTED})}
                    )
                }
            )
        case FileBackupJob() | ObjectStorageBackupJob():
            settings = job.backup_repository.advanced_settings
            assert settings is not None
            return job.model_copy(
                update={
                    "backup_repository": job.backup_repository.model_copy(
                        update={"advanced_settings": settings.model_copy(update={"storage_data": NOT_ENCRYPTED})}
                    )
                }
            )


_STAND_LAST = at(27, 10, 0, month=9)  # the stand's last configuration backup, S-CFG-OK (session 120)
_RUNS = [
    session(
        120 + n,
        "Backup Configuration Job",
        _STAND_LAST + timedelta(days=n),
        _STAND_LAST + timedelta(days=n, minutes=3, seconds=41),
        "Warning",
        message=CONFIG_WARNING,
        session_type="ConfigurationBackup",
    )
    for n in range(1, 10)  # 09-28 .. 10-06
]
_LAST = _RUNS[-1]
assert _LAST.id == mnemonic("40000000", 129) and _LAST.creation_time == at(6, 10, 0)

ENVIRONMENT: Environment = stand.environment(
    jobs=[_unencrypted(job) for job in JOBS],
    sessions=sorted(SESSIONS + _RUNS, key=lambda s: s.creation_time, reverse=True),
    config_backup=CONFIG_BACKUP.model_copy(
        update={
            "last_successful_backup": ConfigBackupLastSuccessful(
                last_successful_time=_LAST.end_time, session_id=_LAST.id
            )
        }
    ),
)

# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    "Yes, it is working: the configuration backup is enabled, runs daily at 10:00 to Repo-Main (keeping 10 restore "
    f"points) and completed every day - the last time on {_LAST.creation_time:%Y-%m-%d} at 10:03. The warning is "
    f"'{CONFIG_WARNING}': the configuration backup is not encrypted, so VBR leaves the stored credentials (and any "
    "encryption keys) out of it. It is not a failure, but it should not be ignored: after restoring the configuration "
    "from such a backup every credential has to be entered again by hand. Fix: enable encryption for the "
    "configuration backup with a password (and keep that password safe); then credentials are included and the "
    "warning goes away."
)
"""Ground truth for the judges."""

FACTS = {
    "working": any_of(
        r"\b(is|it's|they're|are)\s+([\w'-]+\s+){0,3}(working|running|succeeding|completing|being\s+(created|made|taken))",
        r"\b(runs?|ran|completes?|completed|succeeds?|succeeded|finish(es|ed)?)\s+([\w'-]+\s+){0,4}"
        r"(daily|every\s+day|each\s+day|on\s+schedule|as\s+scheduled|successfully)",
        r"backups?\s+(are|is|were|was)\s+([\w'-]+\s+){0,2}(created|made|taken|produced|written)",
        r"\b(it|this)\s+(does\s+)?works?\b",
        r"\b(is|it's)\s+([\w'-]+\s+){0,2}(fine|ok|okay|healthy|functional)\b",
        r"\bcompleted\s+([\w'-]+\s+){0,2}(yesterday|today|daily)",
    ),
    "last_run": any_of(day(_LAST.creation_time, weekday=False), r"\byesterday\b"),
    "credentials_skipped": any_of(
        r"skipping\s+credentials",
        near(
            r"credentials?",
            any_of(
                r"skip",
                r"not\s+(be\s+)?(included|backed|saved|stored|part)",
                r"exclud",
                r"left\s+out",
                r"missing",
                r"without",
            ),
            120,
        ),
    ),
    "enable_encryption": any_of(
        r"enabl\w*\s+([\w'-]+\s+){0,5}encryption",
        r"encryption\s+([\w'-]+\s+){0,6}(enabl|turn\w*\s+on|on\b)",
        r"turn\w*\s+on\s+([\w'-]+\s+){0,5}encryption",
        r"encrypt\s+(the\s+)?config",
    ),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

_ALLOWED = (
    "It is acceptable, and not a violation, to quote the warning, to mention password loss protection or to keep "
    "the password in a safe place, to note that encrypted backups would need their keys too, or to offer to run a "
    "configuration backup after the change, as long as the output does not claim it changed or ran anything."
)

GOOD = [
    (
        "**Yes, it's working** - the configuration backup runs every day at 10:00 to Repo-Main and completes; the last "
        'one was on 2026-10-06 at 10:03.\n\nThe warning is *"Skipping credentials backup because the encryption is '
        'disabled"*: because the configuration backup is not encrypted, VBR leaves all stored credentials out of it. '
        "It's not a failure, but don't just ignore it - if you ever restore the configuration, you'd have to re-enter "
        "every password by hand.\n\n**Fix:** enable encryption in the configuration backup settings (set a password and "
        "store it safely). The credentials are then included and the warning disappears."
    ),
    (
        "It works: backups are created daily (latest: Oct 6, 10:03). The daily Warning only means the credentials are "
        "not included, since the configuration backup encryption is off. I'd turn on encryption for the configuration "
        "backup - otherwise a configuration restore comes back without any of your saved credentials."
    ),
    (
        "| | |\n|---|---|\n| Runs | daily 10:00, completed yesterday |\n| Result | Warning - credentials skipped "
        "(encryption disabled) |\n\nThe job itself is fine; enable configuration backup encryption so credentials are "
        "backed up too."
    ),
]

BAD = {
    "working": "The configuration backup is failing every day: VBR reports 'Skipping credentials backup because the "
    "encryption is disabled' at each 10:00 run (last on 2026-10-06). Enable encryption for it.",
    "credentials_skipped": "It is working: it ran daily, the last time on 2026-10-06. The warning is cosmetic; still, "
    "enable encryption for the configuration backup.",
    "enable_encryption": "It is working: it ran daily, the last time on 2026-10-06. The warning means credentials are "
    "skipped; you can ignore it.",
}


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G2-19",
        inputs=CaseInputs(
            question=(
                "Our configuration backup ends with a warning every day. Is it actually working, and can we ignore "
                "the warning?"
            ),
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G2", "base_stand": "1.12, 1.3 (no job encryption)"},
        evaluators=[
            # The configuration says it runs and when it last succeeded; the sessions with their warning
            # (list_sessions) and the session log are reads on top.
            ToolCorrectness(expected_tools=["get_config_backup_status"], allow_extra=True),
            *tool_budget(4),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "not_a_failure",
                "The output does not call the configuration backup failed or broken and does not say it stopped "
                "running: it runs every day and completes with a Warning.",
            ),
            _judge(
                "caveat_given",
                "The output does not say the warning can simply be ignored with no caveat: it explains that, the "
                "configuration backup being unencrypted, it holds no credentials (so they would have to be entered "
                "again after a configuration restore), and recommends enabling the configuration backup's "
                "encryption, which includes them.",
            ),
            _judge(
                "no_invented_passwords",
                "The output does not claim that the Password Manager holds passwords, that the backup jobs are "
                "encrypted, or that VBR refuses to run the configuration backup: no job uses encryption here and the "
                "backup runs daily.",
            ),
            _judge(
                "no_action_taken",
                "The output does not claim that it enabled encryption, changed a setting or ran a configuration "
                "backup; recommending it is fine.",
            ),
        ],
    )
