# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G2-09: orphaned and imported backups, the disk space they take, and the space savings on Daily-VMs."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

import stand
from cases import CaseInputs, Environment, judge, tool_budget
from cases.patterns import any_of, gb, name, percent
from evaluators import FactsPresent, ToolsNotCalled
from stand.backups import BACKUP_FILES, BACKUPS
from stand.ids import B01, B10, B11, GB
from vbr_models.backups import BackupFile

# ---- What VBR serves: the base stand. VBR names a backup after the job that created it (swagger BackupModel.name), so
# neither name gives the answer away: B11, imported from another server, is "ERP-Nightly", the job it came from, and
# the agent must tell it by its jobId (all zeros) and its policyUniqueId (no job here has it), as list_backups'
# docstring says. B10, "FileApp-Weekly", is orphaned: its job was deleted.

_BACKUPS = BACKUPS
IMPORTED_NAME = stand.by_name(_BACKUPS, "ERP-Nightly").name
ENVIRONMENT: Environment = stand.environment()

# ---- What a correct answer says, derived from the data above.

DECOMMISSIONED = stand.by_name(_BACKUPS, "FileApp-Weekly")


def _sum_gb(files: list[BackupFile], field: str) -> int:
    return sum(getattr(file, field) for file in files) // GB


_B01_ALL = BACKUP_FILES[B01]
_B01_NEWEST = sorted(_B01_ALL, key=lambda f: f.creation_time, reverse=True)[:50]  # get_backup_details' default
_B10_DATA, _B10_DISK = _sum_gb(BACKUP_FILES[B10], "data_size"), _sum_gb(BACKUP_FILES[B10], "backup_size")
_B11_DATA, _B11_DISK = _sum_gb(BACKUP_FILES[B11], "data_size"), _sum_gb(BACKUP_FILES[B11], "backup_size")
_B01_DATA, _B01_DISK = _sum_gb(_B01_NEWEST, "data_size"), _sum_gb(_B01_NEWEST, "backup_size")
_B01_ALL_DATA, _B01_ALL_DISK = _sum_gb(_B01_ALL, "data_size"), _sum_gb(_B01_ALL, "backup_size")
_B01_SAVING = 100 * (1 - _B01_DISK / _B01_DATA)
_B01_ALL_SAVING = 100 * (1 - _B01_ALL_DISK / _B01_ALL_DATA)
assert (_B10_DISK, _B11_DISK, _B01_DATA, _B01_DISK, len(_B01_ALL)) == (640, 180, 3000, 1200, 58)

EXPECTED = (
    f"Two backups have no owning job (jobId all zeros). {DECOMMISSIONED.name} is orphaned: its policyUniqueId is "
    f"empty too. It is on Repo-Main and takes {_B10_DISK} GB on disk ({_B10_DATA} GB of logical data); it holds "
    f"old-fs-01 and old-app-01. {IMPORTED_NAME} has a policyUniqueId that matches no job, so it is an imported or "
    f"exported backup, or the backup of an agent policy; it is on Repo-Branch and takes {_B11_DISK} GB on disk "
    f"({_B11_DATA} GB logical), holding erp-db-2024. Together they take {_B10_DISK + _B11_DISK} GB on disk. "
    f"Daily-VMs has {len(_B01_ALL)} backup files. Over the newest 50 of them: {_B01_DATA} GB of logical data in "
    f"{_B01_DISK} GB on disk, a saving of about {_B01_SAVING:.0f}% - figures for 50 of the {len(_B01_ALL)} files "
    f"(all {len(_B01_ALL)}: {_B01_ALL_DATA} GB logical, {_B01_ALL_DISK} GB on disk, {_B01_ALL_SAVING:.1f}%). Every "
    "other backup belongs to a job on this server."
)
"""Ground truth for the judges."""


def _size(value_gb: float) -> str:
    """A size the tools give in bytes, as an answer writes it: binary GB (as VBR counts), decimal GB, or TB."""
    return any_of(gb(value_gb), gb(round(value_gb * GB / 10**9, 1)))


FACTS = {
    "orphaned": name(DECOMMISSIONED.name),
    "orphaned_on_disk": _size(_B10_DISK),
    "imported": name(IMPORTED_NAME),
    "imported_on_disk": _size(_B11_DISK),
    # the newest 50 files (the tool's default page) or all 58
    "daily_vms_logical": any_of(_size(_B01_DATA), _size(_B01_ALL_DATA)),
    "daily_vms_on_disk": any_of(_size(_B01_DISK), _size(_B01_ALL_DISK)),
    "daily_vms_saving": any_of(
        percent(_B01_SAVING), percent(_B01_ALL_SAVING), r"(?<![\d.])2\.5\s*(:\s*1|x\b|times)", r"2\.48"
    ),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

_ALLOWED = (
    f"It is acceptable, and not a violation, to advise deciding what to do with {DECOMMISSIONED.name} (the tools "
    "here cannot delete it, so only advice or console steps), to relate the space these backups take to repositories "
    "that are short of space, to give their logical sizes too, or to give the full figures over all Daily-VMs files "
    "when it fetched all of them."
)

GOOD = [
    (
        "Yes - two backups belong to no job on this server (their jobId is all zeros):\n\n"
        "| Backup | Kind | Repository | On disk |\n|---|---|---|---|\n"
        "| FileApp-Weekly (old-fs-01, old-app-01) | orphaned - no policy id either | Repo-Main | 640 GB |\n"
        "| ERP-Nightly (erp-db-2024) | imported/exported: its policyUniqueId matches no job | Repo-Branch | 180 GB |\n\n"
        "Together 820 GB.\n\n**Daily-VMs savings** (newest 50 of its 58 files): 3,000 GB of data stored in 1,200 GB on "
        "disk - about 60% saved."
    ),
    (
        "Orphaned: FileApp-Weekly, 640.0 GB on disk (1953 GB logical). Imported: ERP-Nightly - jobId is zeros and "
        "its policyUniqueId belongs to no job here, so it was imported (or exported); 180 GB on disk. Daily-VMs: across "
        "all 58 files 3576 GB logical vs 1440 GB on disk, a 59.7% reduction (2.5:1)."
    ),
    (
        "Two: FileApp-Weekly (orphaned, 0.63 TB on disk) and ERP-Nightly (no matching job - looks imported, "
        "180 GiB). Daily-VMs keeps 3 TB of source data in 1.2 TB, i.e. a 60 % saving - measured on 50 of 58 files."
    ),
]

BAD = {
    "imported": "One orphaned backup: FileApp-Weekly, 640 GB on disk. Daily-VMs: 3000 GB logical in 1200 GB, a "
    "60% saving. Everything else belongs to a job.",
    "orphaned_on_disk": "FileApp-Weekly (orphaned) holds 1953 GB; ERP-Nightly (imported) 180 GB. Daily-VMs: 3000 "
    "GB in 1200 GB, 60% saved.",
    "daily_vms_saving": "FileApp-Weekly (orphaned) 640 GB and ERP-Nightly (imported) 180 GB. Daily-VMs: 3000 GB "
    "logical, 1200 GB on disk.",
}


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G2-09",
        inputs=CaseInputs(
            question=(
                "Do we have orphaned or imported backups, how much disk space do they take, and what space savings "
                "do we get on the Daily-VMs backup?"
            ),
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G2", "base_stand": "1.9"},
        evaluators=[
            # list_backups -> list_jobs (policyUniqueId against job ids) -> get_backup_details for B10, B11, B01.
            ToolCorrectness(expected_tools=["list_backups", "list_jobs", "get_backup_details"], allow_extra=True),
            *tool_budget(5),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "not_all_owned",
                "The output does not say that all backups belong to jobs.",
            ),
            _judge(
                "logical_vs_on_disk",
                "The output does not mix up logical data size (dataSize) and size on disk (backupSize): the on-disk "
                "figures it gives are the expected output's on-disk figures, not the logical ones, and vice versa.",
            ),
            _judge(
                "imported_two_readings",
                f"The output does not confidently mislabel {IMPORTED_NAME}: the REST data (jobId all zeros, a "
                "policyUniqueId that matches no job) cannot prove whether it is orphaned or imported, so any hedged "
                "label naming imported/exported as a possibility (e.g. 'orphaned or imported') is fine; claiming it "
                "belongs to a current job is not.",
            ),
            _judge(
                "partial_files_caveat",
                f"If the Daily-VMs figures the output gives cover only 50 of the {len(_B01_ALL)} backup files, it says "
                f"so; figures over all {len(_B01_ALL)} files need no caveat. It does not present 50-file figures as "
                "the exact total for the whole backup.",
            ),
        ],
    )
