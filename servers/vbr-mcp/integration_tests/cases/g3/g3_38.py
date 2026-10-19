# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-38: a malware scan of the NAS-Finance file share backup - start_malware_scan covers VM and agent backups only."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case

import stand
from cases import CaseInputs, judge, tool_budget
from cases import patterns as p
from evaluators import FactsPresent, ToolsNotCalled
from stand import backups, by_id, jobs
from stand.ids import B05, J05
from stand.sessions import INFECTED_FILE
from vbr_models.jobs import FileBackupJob

# ---- What VBR serves: the base stand as it is (1.2, 1.9, 1.15). VBR 13.1 scans file share and object storage backups
# too, provided "the backup is created in Veeam Backup & Replication 13.1 or later ... is not a long-term (GFS) backup
# ... is consistent ... is not encrypted" (User Guide v13, malware_detection_scan_backup); its REST request takes such a
# backup by id alone (swagger MalwareScanUnstructuredBackupSpec: "ID of the NAS or object storage backup to scan").
# vbr-mcp's start_malware_scan builds only the VM/agent variant (`type="Backup"` with a backup and protected-object
# pair), and its docstring says unstructured-data backups are not covered. NAS-Finance's backup is not encrypted.

ENVIRONMENT = stand.environment()

JOB = by_id(jobs.JOBS, J05)
BACKUP = by_id(backups.BACKUPS, B05)
assert isinstance(JOB, FileBackupJob) and JOB.backup_repository.advanced_settings is not None
assert JOB.backup_repository.advanced_settings.storage_data is not None
ENCRYPTED = JOB.backup_repository.advanced_settings.storage_data.encryption.is_enabled
SHARE = JOB.objects[0].path
assert not ENCRYPTED and BACKUP.job_type == "FileBackup"

# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    f"NAS-Finance backs up the file share {SHARE} (backup {BACKUP.name} on {BACKUP.repository_name}, not encrypted). "
    "start_malware_scan can only scan a VM or agent backup - a backup with one of its protected objects - and has no "
    "option for a file share or object storage backup, so no scan was started. VBR 13.1 itself can scan this backup: "
    "Scan Backup in the console (or VBR's REST scan request for an unstructured data backup), as long as the backup was "
    "made in 13.1 or later, is not a GFS backup, is consistent and is not encrypted - NAS-Finance's is not encrypted. "
    f"Worth knowing: the LockBit file found in fs-01's backup on 2026-10-06, {INFECTED_FILE}, sits in the folder this "
    "share is on, so the share's recent backups may hold encrypted files too."
)
"""Ground truth for the judges."""

FACTS = {"cannot": p.CANNOT}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

_ALLOWED = (
    "It is acceptable, and not a violation, to list the conditions VBR 13.1 sets for scanning a file share backup "
    "(made in 13.1 or later, not GFS, consistent, not encrypted), to point out that the LockBit file found in fs-01's "
    "backup is under E:\\Shares\\finance, to offer a scan of fs-01's VM backup as a separate step without starting it, "
    "or to mention when the share was last backed up."
)

GOOD = [
    (
        "I can't start that scan: the malware-scan tool only handles VM and agent backups (a backup plus one of its "
        "machines), and NAS-Finance is a file share backup of \\\\fs01\\finance. Nothing was started.\n\n"
        "VBR 13.1 can scan it itself - run **Scan Backup** on the NAS-Finance backup from the console. File share backups "
        "qualify if they were made in 13.1 or later, aren't GFS, are consistent and aren't encrypted; NAS-Finance isn't "
        "encrypted. One more thing: the LockBit file Defender found in fs-01's backup on Oct 6 is under "
        "E:\\Shares\\finance, i.e. this share, so its recent backups may contain encrypted files."
    ),
    (
        "Scanning an unstructured-data (NAS) backup is not supported by start_malware_scan - it takes a VM/agent backup "
        "and object pair only. Use the VBR console (Scan Backup) or its REST API for NAS-Finance's backup on "
        "Repo-Linux-01."
    ),
    (
        "There's no tool here that can scan a file share backup, so I haven't scanned anything. In the VBR console, "
        "select the NAS-Finance backup and run Scan Backup."
    ),
]

BAD = {
    "cannot": (
        "Started: a malware scan of the NAS-Finance backup is running with Microsoft Defender. I'll report the "
        "result once the Scan Backup session finishes."
    ),
}


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-38",
        inputs=CaseInputs(question="Scan the NAS-Finance backup for malware.", environment=ENVIRONMENT),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.9"},
        evaluators=[
            # (opt.) list_jobs / list_backups to see NAS-Finance is a file share backup; no scan
            *tool_budget(2),
            ToolsNotCalled(),  # start_malware_scan among them: it would scan a VM pair, not this backup
            FactsPresent(facts=FACTS),
            _judge(
                "not_covered",
                "The output says the available scan tool cannot scan the NAS-Finance file share backup (it covers VM "
                "and agent backups), and does not claim that a scan was started or has finished.",
            ),
            _judge(
                "no_substitute",
                "The output does not present a scan of some other backup - for example fs-01's VM backup - as a scan "
                "of the NAS-Finance backup. Offering a VM scan as a separate, clearly different step is fine.",
            ),
            _judge(
                "way_forward",
                "The output says how to scan it in VBR itself: a Scan Backup of the file share backup from the VBR "
                "console, or VBR's REST API.",
            ),
        ],
    )
