# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G2-17: which VMs in vCenter no backup protects - vCenter's VMs set against the protected objects."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import CaseInputs, judge, tool_budget
from cases.patterns import name
from evaluators import FactsPresent, ToolsNotCalled
from stand import environment, inventory, jobs, protected
from vbr_models.jobs import BackupJob

# ---- What VBR serves: the base stand. VBR's servers (browse_inventory) are vcenter01 alone; the VMs it holds come
# from its own inventory (POST /api/v1/inventory/vcenter01.lab.local, browse_inventory with server_name; swagger
# GetInventoryObjects). Protected objects (1.8) list only workloads with a backup, also old-fs-01, old-app-01 and
# erp-db-2024, gone from vCenter but kept in orphaned and imported backups. vCenter also holds test-vm-01 and jump-01,
# in no job, and new-app-01, in Test-NewApp, created an hour ago and never run: none of the three has a backup.

ENVIRONMENT = environment()

# ---- What a correct answer says, derived from the data above.

_PROTECTED_VMS = {obj.name for obj in protected.OBJECTS if obj.platform_name == "VMware"}
_IN_VCENTER = {vm.name for vm in inventory.VMS.values() if not vm.gone}
_JOB_OF = {vm.name: job.name for job in jobs.JOBS if isinstance(job, BackupJob) for vm in job.virtual_machines.includes}
UNPROTECTED = sorted(_IN_VCENTER - _PROTECTED_VMS)
_IN_NO_JOB = [vm for vm in UNPROTECTED if vm not in _JOB_OF]
((_NEW_VM, _NEW_VM_JOB),) = ((vm, _JOB_OF[vm]) for vm in UNPROTECTED if vm in _JOB_OF)
_PROTECTED_IN_VCENTER = sorted(_IN_VCENTER & _PROTECTED_VMS)
_KNOWN_VMS = sorted(_IN_VCENTER | _PROTECTED_VMS)
assert _IN_NO_JOB == ["jump-01", "test-vm-01"] and (_NEW_VM, _NEW_VM_JOB) == ("new-app-01", "Test-NewApp")

EXPECTED = (
    f"Three VMs in {inventory.VCENTER_NAME} have no backup: {' and '.join(_IN_NO_JOB)}, which are in no backup job, "
    f"and {_NEW_VM}, which is in the {_NEW_VM_JOB} job but has never been backed up (the job has not run yet). Every "
    "other VM in vCenter has restore points; legacy-erp-01's newest is 25 days old, its job (Legacy-Archive) being "
    "disabled."
)
"""Ground truth for the judges."""

FACTS = {vm.replace("-", "_"): name(vm) for vm in UNPROTECTED}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    """Three VMs in vcenter01.lab.local have no backup:

- **test-vm-01** - not in any backup job
- **jump-01** - not in any backup job
- **new-app-01** - in the Test-NewApp job, which has never run, so it has no restore point yet

Every other VM in vCenter has restore points (legacy-erp-01's newest is 25 days old, because Legacy-Archive is disabled).""",
    "Unprotected VMs: new-app-01 (its job Test-NewApp never ran), test-vm-01 and jump-01 (in no job).",
]

BAD = {
    "new_app_01": (
        "test-vm-01 and jump-01 are in vCenter but in no backup job, so they have no backup. Every VM in a job has "
        "restore points."
    ),
    "test_vm_01": "new-app-01 has never been backed up (Test-NewApp never ran), and jump-01 is in no job.",
    "jump_01": "Two VMs have no backup: new-app-01, whose job never ran, and test-vm-01, which is in no job.",
}

_ALLOWED = (
    "It is acceptable, and not a violation, to list the protected VMs, to note that legacy-erp-01's latest backup is "
    "25 days old because Legacy-Archive is disabled, to note that old-fs-01, old-app-01 and erp-db-2024 are no longer "
    "in vCenter but kept in orphaned or imported backups, or to suggest adding the unprotected VMs to a job."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G2-17",
        inputs=CaseInputs(
            question="Which VMs in our vCenter are not protected by any backup?",
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G2", "base_stand": "1.7, 1.8, 1.2"},
        evaluators=[
            # vCenter's VMs (browse_inventory(server_name=vcenter01), after browse_inventory or list_vmware_hosts for its
            # name)
            # against what is protected (list_protected_objects); list_jobs tells why new-app-01 has no backup
            ToolCorrectness(expected_tools=["browse_inventory", "list_protected_objects"], allow_extra=True),
            *tool_budget(5),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "no_false_unprotected",
                f"The output does not say that any of these VMs has no backup or is unprotected: "
                f"{', '.join(_PROTECTED_IN_VCENTER)} (each has restore points).",
            ),
            _judge(
                "no_invented_vms",
                f"Every VM name the output mentions is one of these: {', '.join(_KNOWN_VMS)}. It names no other VM.",
            ),
        ],
    )
