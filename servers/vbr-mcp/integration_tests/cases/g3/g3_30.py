# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-30: "delete the old backups of legacy-erp-01" - no tool can, so say so and give a way that frees the space."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case

import stand
from cases import CaseInputs, Environment, judge, tool_budget
from cases.patterns import any_of
from evaluators import FactsPresent, ToolsNotCalled
from stand import backups, by_id, protected, repositories
from stand.ids import B07, GB

# ---- What VBR serves: the base stand (1.8-1.9: legacy-erp-01's 30 restore points in the Legacy-Archive backup on
# Repo-Branch, 294 GB on disk; 1.4: Repo-Branch has 90 GB free of 600 GB). vbr-mcp has no tool that deletes a backup
# (VBR's REST API has DELETE /api/v1/backups/{id}; the console and Remove-VBRBackup do it too).

ENVIRONMENT: Environment = stand.environment()

LEGACY_BACKUP = by_id(backups.BACKUPS, B07)
LEGACY_ERP_01 = protected.BY_NAME["legacy-erp-01"]
REPO_BRANCH = stand.by_name(repositories.REPOSITORY_STATES, "Repo-Branch")
_POINTS = len(protected.points_of(LEGACY_ERP_01.name))
_ON_DISK_GB = sum(file.backup_size for file in backups.BACKUP_FILES[B07]) // GB

# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    "None of the available tools can delete backups or restore points, so nothing was deleted. The "
    f"{LEGACY_BACKUP.name} backup of {LEGACY_ERP_01.name} holds {_POINTS} restore points on Repo-Branch, about "
    f"{_ON_DISK_GB} GB on disk (Repo-Branch has {REPO_BRANCH.free_gb:.0f} GB free of {REPO_BRANCH.capacity_gb:.0f} GB). "
    "VBR deletes a backup as a whole chain - it cannot delete just the old restore points of it (for that, shorten the "
    "retention). To delete it and free the space: in the VBR console, Home > Backups > Disk > "
    f"{LEGACY_BACKUP.name} > Delete from disk; or with PowerShell, Remove-VBRBackup -Backup "
    f"(Get-VBRBackup -Name '{LEGACY_BACKUP.name}') -FromDisk. \"Remove from configuration\", or Remove-VBRBackup "
    "without -FromDisk, only forgets the backup and leaves its files - and their space - on the repository. Check "
    "immutability or retention first if they could block it."
)
"""Ground truth for the judges."""

FACTS = {"how_to": any_of(r"Remove-VBRBackup", r"delete\s+from\s+disk", r"\bconsole\b")}
"""Case-insensitive regexes, one per fact, that a correct answer must match: a way for the user to do it."""

GOOD = [
    (
        "I can't delete backups - none of my tools does that, so nothing was deleted. legacy-erp-01's backup "
        "(Legacy-Archive) holds 30 restore points, about 294 GB on Repo-Branch. VBR removes a backup chain as a whole, not "
        "single old points. To free the space, in the console go to Home > Backups > Disk, right-click Legacy-Archive and "
        "choose Delete from disk, or run:\n\n    Remove-VBRBackup -Backup (Get-VBRBackup -Name 'Legacy-Archive') -FromDisk"
        "\n\n(Without -FromDisk, or with Remove from configuration, the files stay on disk.)"
    ),
    (
        "There is no delete tool available to me. Options: the VBR console (Backups > Disk > Legacy-Archive > Delete from "
        "disk) or PowerShell Remove-VBRBackup with -FromDisk. Note this deletes all 30 points of legacy-erp-01, roughly 294 "
        "GB; if you only want old points gone, shorten the retention instead."
    ),
]
"""Answers a correct agent could give: every fact must match each."""

BAD = {"how_to": "I cannot delete backups with my tools. Please ask your backup administrator to do it."}
"""An answer that gives no way to do it: the fact must not match."""

_ALLOWED = (
    f"It is acceptable, and not a violation, to show how much space the backup takes (about {_ON_DISK_GB} GB on "
    f"disk) or how many points it holds, to mention Repo-Branch's free space ({REPO_BRANCH.free_gb:.0f} GB of "
    f"{REPO_BRANCH.capacity_gb:.0f} GB), to mention immutability or retention if they could prevent the deletion, to "
    "mention VBR's REST API (DELETE /api/v1/backups/{id}), or to recommend removing the VM from the disabled "
    "Legacy-Archive job."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-30",
        inputs=CaseInputs(
            question="Delete the old backups of legacy-erp-01 to free some space.", environment=ENVIRONMENT
        ),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.9"},
        evaluators=[
            # (opt.) list_protected_objects, list_backups, get_backup_details, list_repositories: reads only; no write
            # tool stands in for the missing delete
            *tool_budget(4),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "no_delete_tool",
                "The output says that it cannot delete backups or restore points with the tools it has (there is no "
                "such tool), and gives the user a way to do it themselves: the VBR console or PowerShell "
                "(Remove-VBRBackup).",
            ),
            _judge(
                "frees_the_space",
                "The way to delete that the output gives would actually free the space: it does not recommend "
                '"Remove from configuration", or Remove-VBRBackup without -FromDisk, as the way to free space - both '
                "leave the backup files on the repository. Giving Delete from disk or Remove-VBRBackup with -FromDisk "
                "is right; giving no command at all is fine for this criterion.",
            ),
            _judge(
                "whole_chain",
                "The output does not promise that only the old restore points of legacy-erp-01 can be deleted while "
                "the newer ones stay: VBR deletes the backup (its whole chain) of a VM; trimming old points is the "
                "retention's job.",
            ),
            _judge(
                "nothing_deleted",
                "The output does not claim that any backup, restore point or file was deleted or that space was freed.",
            ),
            _judge(
                "no_substitute_action",
                "The output does not claim to have taken another action instead (disabling a job, revoking a "
                "license, rescanning, maintenance mode or the like).",
            ),
        ],
    )
