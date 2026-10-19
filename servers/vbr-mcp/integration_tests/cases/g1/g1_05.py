# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G1-05: the jobs without backup encryption."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import CaseInputs, judge, tool_budget
from cases.patterns import name
from evaluators import FactsPresent, ToolsNotCalled
from stand import by_name, environment, replace
from stand.jobs import JOBS, NOT_ENCRYPTED, storage_data
from vbr_models.jobs import (
    BackupCopyJob,
    BackupCopyJobAdvancedSettings,
    BackupJob,
    Job,
)

# ---- What VBR serves: the base stand, with Copy-to-DR's own encryption off although its source, Daily-VMs, is
# encrypted. A backup copy job's setting is what counts: "Even if encryption is disabled in the backup copy job,
# Veeam Backup & Replication will decrypt data blocks of the encrypted source backup files" (User Guide v13,
# encrypting_backup_copy_jobs), so the copies are not encrypted. A copy that "inherits" its source's encryption is the
# mistake this case sets up. Each job type keeps the setting in its own subtree.

_COPY = by_name(JOBS, "Copy-to-DR")
assert isinstance(_COPY, BackupCopyJob)
JOBS_HERE: list[Job] = replace(
    JOBS,
    _COPY.id,
    target=_COPY.target.model_copy(
        update={"advanced_settings": BackupCopyJobAdvancedSettings(storage_data=NOT_ENCRYPTED)}
    ),
)

ENVIRONMENT = environment(jobs=JOBS_HERE)

# ---- What a correct answer says, derived from the data above.


def _encrypted(job: Job) -> bool:
    data = storage_data(job)
    return data is not None and data.encryption.is_enabled


UNENCRYPTED = [job.name for job in JOBS_HERE if not _encrypted(job)]  # SQL-Dev, Copy-to-DR, NAS-Finance, ...
_ENCRYPTED_OUTSIDE_STORAGE = [job.name for job in JOBS_HERE if _encrypted(job) and not isinstance(job, BackupJob)]
_DISABLED = [job.name for job in JOBS_HERE if job.is_disabled]

EXPECTED = (
    f"{len(UNENCRYPTED)} of {len(JOBS_HERE)} jobs do not have backup encryption enabled: {', '.join(UNENCRYPTED)}. "
    f"{_COPY.name} is among them although its source, Daily-VMs, is encrypted: a backup copy job's own encryption "
    f"setting decides, and it is off. The other {len(JOBS_HERE) - len(UNENCRYPTED)} jobs are encrypted, including "
    f"{', '.join(_ENCRYPTED_OUTSIDE_STORAGE)}, whose encryption setting is not under storage. "
    f"{', '.join(_DISABLED)} is disabled."
)
"""Ground truth for the judges."""

FACTS = {f"job_{job.lower().replace('-', '_')}": name(job) for job in UNENCRYPTED}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

_ALLOWED = (
    f"It is acceptable, and not a violation, to give the share of encrypted jobs ({len(JOBS_HERE) - len(UNENCRYPTED)} "
    f"of {len(JOBS_HERE)}), to note that {', '.join(_DISABLED)} is disabled, to explain where each job type keeps its "
    "encryption setting, or to recommend enabling encryption as advice, without changing anything."
)

GOOD = [
    (
        "These jobs do not have backup encryption enabled:\n- SQL-Dev\n- Copy-to-DR (its own encryption is off - it does "
        "not inherit Daily-VMs' encryption)\n- NAS-Finance\n- Legacy-Archive (disabled)\n- Reports-VM\n\nAll other jobs - "
        "Daily-VMs, SQL-Prod, Agent-Laptops, Test-NewApp and S3-Docs - are encrypted."
    ),
    "5 of 10 jobs are unencrypted: SQL-Dev, Copy-to-DR, NAS-Finance, Legacy-Archive and Reports-VM.",
    (
        "| Job | Type | Encryption |\n|---|---|---|\n| SQL-Dev | VSphereBackup | off |\n| Copy-to-DR | BackupCopy | off |"
        "\n| NAS-Finance | FileBackup | off |\n| Legacy-Archive | VSphereBackup | off |\n| Reports-VM | VSphereBackup | "
        "off |"
    ),
]

BAD = {
    "job_copy_to_dr": "Not encrypted: SQL-Dev, NAS-Finance, Legacy-Archive and Reports-VM. Every other job, the "
    "backup copy included, is encrypted.",
    "job_nas_finance": "Not encrypted: SQL-Dev, Copy-to-DR, Legacy-Archive and Reports-VM.",
}
"""Answers that each miss one of the unencrypted jobs; the first falls for the inherited-encryption trap."""


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G1-05",
        inputs=CaseInputs(question="Which of my jobs do NOT have backup encryption enabled?", environment=ENVIRONMENT),
        expected_output=EXPECTED,
        metadata={"group": "G1", "base_stand": "1.2"},
        evaluators=[
            ToolCorrectness(expected_tools=["list_jobs"], allow_extra=True),
            *tool_budget(1),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "exactly_the_unencrypted_jobs",
                f"The output lists exactly these {len(UNENCRYPTED)} jobs as not encrypted: {', '.join(UNENCRYPTED)}, "
                "and does not list any other job as not encrypted.",
            ),
            _judge(
                "copy_does_not_inherit",
                f"The output does not present {_COPY.name} as encrypted because its source job Daily-VMs is "
                "encrypted: a backup copy job's own encryption setting decides, and it is off.",
            ),
            _judge(
                "other_subtrees_are_encrypted",
                f"The output does not call {', '.join(_ENCRYPTED_OUTSIDE_STORAGE)} unencrypted, or say their "
                "encryption is unknown or missing: they are encrypted, with the setting kept outside the storage "
                "settings that VM backup jobs use.",
            ),
        ],
    )
