# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G1-16: how many VMs are protected, and how many restore points each has."""

import re
from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case

from cases import CaseInputs, Environment, judge, tool_budget
from cases.patterns import any_of, number
from evaluators import RESTORE_POINT_READS, FactsPresent, ToolsCalled, ToolsNotCalled
from stand import environment, protected

# ---- What VBR serves: the base stand. Its protected objects (1.8) are 12 VMware VMs - nine of the current jobs, and
# old-fs-01, old-app-01 (an orphaned backup) and erp-db-2024 (an imported one) - plus laptops, a file share and a
# bucket, which are protected but are not VMs. /backupObjects repeats fs-01's row, as the stand has it: vbr-mcp
# deduplicates it. new-app-01 is in a job (Test-NewApp) but has no backup yet, so it is not protected.

ENVIRONMENT: Environment = environment()

# ---- What a correct answer says, derived from the data above.

VMS = [obj for obj in protected.OBJECTS if obj.platform_name == "VMware"]
_POINTS = sum(vm.restore_points_count or 0 for vm in VMS)
_FS_01 = protected.BY_NAME["fs-01"]

EXPECTED = (
    f"{len(VMS)} VMware VMs are protected, with {_POINTS} restore points in all: "
    + ", ".join(f"{vm.name} {vm.restore_points_count}" for vm in VMS)
    + ". old-fs-01 and old-app-01 are only in an orphaned backup and erp-db-2024 only in an imported one. "
    "The laptops, the file share and the object storage bucket are protected too, but they are not VMs."
)
"""Ground truth for the judges."""

_BARE_SMALL_NUMBER = r"(?<![\w-])\d{1,3}(?![\w-])"
"""A count of its own, not part of a name (web-02), an id (B03) or a date (2026-10-07)."""


def _points_of(vm_name: str, count: int) -> str:
    """The VM's own restore point count, as an answer writes it next to the VM's name.

    The first count after its name on its line ("sql-dev-01: 7", "| sql-dev-01 | 7 |", "web-01, web-02 and app-01: 14
    each"), or a count followed by a list naming it ("14 points each: web-01, ...").
    """
    vm, points = re.escape(vm_name), rf"(?<![\w-]){count}(?![\w-]|[.,]\d)"
    return any_of(
        rf"(?<![\w-]){vm}(?![\w-])(?:(?!{_BARE_SMALL_NUMBER})[^\n]){{0,80}}?{points}",
        rf"{points}\s*(?:restore\s+)?points?\s*(?:each|apiece)?\s*[:-][^\n]{{0,160}}?(?<![\w-]){vm}(?![\w-])",
    )


FACTS = {
    "vm_count": any_of(number(len(VMS), decimals=0), r"\btwelve\b"),
    **{f"points_{vm.name}": _points_of(vm.name, vm.restore_points_count or 0) for vm in VMS},
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

_ALLOWED = (
    f"It is acceptable, and not a violation, to give the total of {_POINTS} restore points, to note that old-fs-01, "
    "old-app-01 and erp-db-2024 exist only in an orphaned or imported backup, to split the count into the VMs of "
    "current jobs and those, to explain that 'protected' means 'has at least one backup', or to mention the non-VM "
    "protected objects (laptops, file share, bucket) separately."
)

_TABLE = "\n".join(f"| {vm.name} | {vm.restore_points_count} |" for vm in VMS)

GOOD = [
    (
        f"{len(VMS)} VMs are protected:\n\n| VM | Restore points |\n|---|---|\n{_TABLE}\n\n"
        "old-fs-01 and old-app-01 are only in an orphaned backup and erp-db-2024 only in an imported one; the laptops, "
        "the file share and the bucket are protected too but are not VMs."
    ),
    (
        "There are 12 protected VMware VMs (180 restore points in total):\n"
        "- 14 points each: web-01, web-02, app-01, fs-01, report-01\n"
        "- 30 points each: sql-prod-01, sql-prod-02, legacy-erp-01\n"
        "- sql-dev-01: 7\n"
        "- old-fs-01 and old-app-01 (orphaned backup): 5 each\n"
        "- erp-db-2024 (imported backup): 3."
    ),
    (
        "Twelve VMs have backups. web-01 has 14 restore points, web-02 14, app-01 14, fs-01 14, sql-prod-01 30, "
        "sql-prod-02 30, sql-dev-01 7, report-01 14, legacy-erp-01 30, old-fs-01 5, old-app-01 5 and erp-db-2024 3."
    ),
]
"""Answers a correct agent could give: every fact must match each of them."""

BAD = {
    "vm_count": "13 VMs are protected: fs-01 is listed twice. web-01 14, web-02 14, app-01 14, fs-01 14, "
    "sql-prod-01 30, sql-prod-02 30, sql-dev-01 7, report-01 14, legacy-erp-01 30, old-fs-01 5, old-app-01 5, "
    "erp-db-2024 3.",
    "points_sql-dev-01": "12 VMs: sql-dev-01 has 14 restore points, web-01 has 7.",
    "points_erp-db-2024": "12 VMs are protected; erp-db-2024 has 30 points, sql-dev-01 7, the others 14.",
}
"""Per fact, an answer that gets that fact wrong: the fact must not match it."""


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G1-16",
        inputs=CaseInputs(
            question="How many VMs are protected, and how many restore points does each one have?",
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G1", "base_stand": "1.8"},
        evaluators=[
            # restorePointsCount of list_protected_objects is the answer; counting points with list_restore_points
            # is a longer road to the same numbers.
            ToolsCalled("objects_read", RESTORE_POINT_READS),
            *tool_budget(2),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "no_duplicate_count",
                f"The output does not count {len(VMS) + 1} VMs or "
                f"{_POINTS + (_FS_01.restore_points_count or 0)} restore points, and does not list fs-01 twice.",
            ),
            _judge(
                "no_unprotected_vms",
                "The output does not present new-app-01, test-vm-01 or jump-01 as protected VMs: they have no backup "
                "(new-app-01 is in the Test-NewApp job, which has never run).",
            ),
            _judge(
                "vms_only",
                "The VM count the output gives does not include the laptops, the file share or the object storage "
                "bucket, which are protected objects but not VMs.",
            ),
        ],
    )
