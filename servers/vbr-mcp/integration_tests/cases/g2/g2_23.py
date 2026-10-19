# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G2-23: the instance license is exceeded, and whether backups will start failing."""

from datetime import date, datetime, time, timedelta
from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import CaseInputs, judge, tool_budget
from cases.patterns import any_of, near, number
from evaluators import FactsPresent, ToolsNotCalled
from stand import by_name, environment, jobs, license, protected, replace, sessions
from stand.ids import B01, GB, J01, M02, R01, S_ID14, SERVER_TZ, ZERO, mnemonic
from stand.inventory import ESX01, VCENTER_NAME
from vbr_models.jobs import BackupJob, BackupJobVirtualMachines, VmwareObject
from vbr_models.license import InstanceLicenseObject, InstanceLicenseWorkload
from vbr_models.protected_objects import RestorePoint, RestorePointDisk, ViBackupObject
from vbr_models.sessions import BackupTaskSession, SessionResult

# ---- What VBR serves: the base stand, three VMs later. web-03, web-04 and app-02 were added to Daily-VMs on 10-03 and
# have been backed up every night since, so the instance license (1.11) counts 12 VMs and 3 workstations (1/3 each):
# 13 instances used of 11. License autoupdate is enabled, so VBR tolerates the excess: "Less than 10 instances (or 10%
# of the total instance count, whichever is greater): All protected workloads are processed normally, Veeam Backup &
# Replication does not display a warning message"; 10-20 over: processed, a weekly warning; more than 20 over: the
# excess is not processed (User Guide v13, license_exceeding).

NEW_VMS = [("web-03", "vm-1054", 18, 13), ("web-04", "vm-1055", 19, 14), ("app-02", "vm-1056", 20, 15)]
"""(name, managed object reference, protected object number, license instance number)."""
NIGHTS = [date(2026, 10, day) for day in (6, 5, 4, 3)]  # newest first: four nights since 10-03


def _point(obj: ViBackupObject, index: int, night: date, minute: int) -> RestorePoint:
    return RestorePoint(
        id=protected.point_id(obj, index),
        name=obj.name,
        platform_name="VMware",
        platform_id=ZERO,
        creation_time=datetime.combine(night, time(22, minute, 10), tzinfo=SERVER_TZ),
        backup_id=B01,
        type="Full" if index == len(NIGHTS) - 1 else "Increment",
        allowed_operations=protected.VMWARE_OPERATIONS,
        malware_status="Clean",
        backup_object_id=obj.id,
    )


_OBJECTS = [
    ViBackupObject(
        id=mnemonic("50000000", number),
        name=name,
        type="VM",
        restore_points_count=len(NIGHTS),
        last_run_failed=False,
        backup_id=B01,
        object_id=ref,
        vi_type="VirtualMachine",
    )
    for name, ref, number, _ in NEW_VMS
]
_POINTS = [
    _point(obj, index, night, minute=24 + 3 * n) for n, obj in enumerate(_OBJECTS) for index, night in enumerate(NIGHTS)
]
_DISKS = {
    point.id: [RestorePointDisk(uid=f"{M02}:{point.name}:2000:{point.id}", name=point.name, capacity=60 * GB)]
    for point in _POINTS
}

# Every Daily-VMs run since 10-03 processed them as well: a task each, and the 10-05 run failed for 1 of 7 VMs. Its
# retry reprocessed only web-02.
_RUNS = [
    run
    for run in sessions.SESSIONS
    if run.job_id == J01 and run.retry_info is None and run.creation_time.date() in NIGHTS
]
_TASKS = [
    BackupTaskSession(
        id=mnemonic("41000000", 5000 + k),
        session_id=run.id,
        session_type=run.session_type,
        creation_time=point.creation_time - timedelta(seconds=25),
        end_time=None if run.end_time is None else run.end_time - timedelta(seconds=20),
        name=point.name,
        restore_point_id=point.id,
        algorithm="Full" if point.type == "Full" else "Increment",
        repository_id=R01,
        state="Stopped",
        result=SessionResult(result="Success", message="", is_canceled=False),
        platform_type="VMware",
    )
    for k, (run, point) in enumerate(
        (run, point) for run in _RUNS for point in _POINTS if point.creation_time.date() == run.creation_time.date()
    )
]
assert len(_RUNS) == len(NIGHTS) and len(_TASKS) == len(NIGHTS) * len(NEW_VMS)
SESSIONS = replace(
    sessions.SESSIONS,
    S_ID14,
    result=SessionResult(result="Failed", message="Failed to process 1 of 7 VMs. See the session log for details."),
)

_DAILY = by_name(jobs.JOBS, "Daily-VMs")
assert isinstance(_DAILY, BackupJob)
_INCLUDES = [
    *_DAILY.virtual_machines.includes,
    *(
        VmwareObject(host_name=VCENTER_NAME, name=name, type="VirtualMachine", object_id=ref)
        for name, ref, _, _ in NEW_VMS
    ),
]

_SUMMARY = license.LICENSE.instance_license_summary
assert _SUMMARY is not None and _SUMMARY.objects is not None
_VM_COUNT = _SUMMARY.objects[0].count + len(NEW_VMS)
SUMMARY = _SUMMARY.model_copy(
    update={
        "used_instances_number": _SUMMARY.used_instances_number + len(NEW_VMS),
        "objects": [
            InstanceLicenseObject(
                type="Virtual Machines", count=_VM_COUNT, multiplier=1, used_instances_number=_VM_COUNT
            ),
            _SUMMARY.objects[1],
        ],
    }
)
LICENSE = license.LICENSE.model_copy(update={"instance_license_summary": SUMMARY})
INSTANCES = [
    *license.INSTANCES,
    *(
        InstanceLicenseWorkload(
            name=name,
            host_name=ESX01.name,
            used_instances_number=1,
            type="VM",
            instance_id=mnemonic("70000000", instance),
            platform_type="VMware",
            can_be_revoked=True,
        )
        for name, _, _, instance in NEW_VMS
    ),
]

ENVIRONMENT = environment(
    sessions=SESSIONS,
    tasks=sorted([*sessions.TASKS, *_TASKS], key=lambda t: t.creation_time, reverse=True),
    jobs=replace(jobs.JOBS, J01, virtual_machines=BackupJobVirtualMachines(includes=_INCLUDES)),
    job_states=replace(jobs.JOB_STATES, J01, objects_count=len(_INCLUDES)),
    backup_objects=[*protected.BACKUP_OBJECTS, *_OBJECTS],
    restore_points=sorted([*protected.RESTORE_POINTS, *_POINTS], key=lambda p: p.creation_time, reverse=True),
    disks=_DISKS,
    license=LICENSE,
    license_instances=INSTANCES,
)

# ---- What a correct answer says, derived from the data above.

_USED, _LICENSED = SUMMARY.used_instances_number, SUMMARY.licensed_instances_number
assert (_USED, _LICENSED, LICENSE.auto_update_enabled) == (13, 11, True)

EXPECTED = (
    f"No, backups will not start failing now. {_USED:g} of {_LICENSED:g} licensed instances are used - {_VM_COUNT} "
    "VMs at 1 instance each (web-03, web-04 and app-02 were added to Daily-VMs on 10-03) and 3 workstations at 1/3 "
    "each - so the license is exceeded by 2 instances. License autoupdate is enabled, and with it VBR keeps "
    "processing every workload while the excess is less than 10 instances (or 10% of the license, whichever is "
    "greater), without even a warning; between 10 and 20 over it still processes everything but shows a weekly "
    "out-of-compliance warning; only beyond 20 over are the excess workloads not processed. Being over is still out "
    "of compliance with the licensing policy: add instances to the license (through the reseller or Veeam) or free "
    "some - legacy-erp-01, whose job has been disabled for 25 days, is released automatically 31 days after its last "
    "backup (in about 6 days) or can be revoked now. The capacity license for the unstructured data is separate and "
    "not exceeded."
)
"""Ground truth for the judges."""

_TWO = r"(?<![\d.,])(?:2|two)(?!\d|[.,]\d)"

FACTS = {
    "usage": near(number(_USED), number(_LICENSED), 60),
    # "2 instances over", "two more than licensed", "exceeds the license by 2", "an overage of 2"
    "over_by_two": any_of(
        rf"{_TWO}\s+(extra\s+|additional\s+)?(licen[sc]e\s+)?(instances?\s+)?(over|above|beyond|too\s+many|more\s+than|"
        r"in\s+excess)\b",
        rf"{_TWO}\s+more\s+(instances?\s+)?than\b",
        rf"\b(exceed\w*|over|above)\s+(it\s+|the\s+license\s+|the\s+limit\s+|your\s+license\s+)?by\s+{_TWO}",
        rf"\b(overage|excess|over-?use|surplus)\s+(is\s+|of\s+)?(only\s+|just\s+)?{_TWO}",
        rf"\b(overage|over\s+the\s+limit|excess|over-?use)\W{{1,5}}(by\s+)?{_TWO}",
        r"\+\s*2\s+instances?\b",
        r"\b13\s*-\s*11\s*=\s*2\b",
    ),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    """**No - backups won't start failing at this level.**

You're using 13 of 11 instances: 12 VMs (one instance each, including web-03, web-04 and app-02, which joined Daily-VMs on Oct 3) and 3 laptops at 1/3 instance each. That puts you 2 instances over the license.

Because license autoupdate is enabled, VBR tolerates an overage of less than 10 instances (or 10%, whichever is greater) and keeps processing every workload without any warning. Between 10 and 20 over it still processes everything but warns weekly; only beyond 20 over are the extra workloads left unprocessed.

You are, however, out of compliance with the licensing policy, so:
- add instances to the license (contact your reseller), or
- free some: legacy-erp-01 hasn't been backed up for 25 days (its job is disabled); its instance is released automatically after 31 days, or you can revoke it now.""",
    """13 used vs 11 licensed means you exceed the license by two instances. With autoupdate on, that is within VBR's tolerance (fewer than 10 extra instances), so jobs keep running and nothing is skipped. It still needs fixing for compliance - buy more instances or revoke ones you no longer need, like legacy-erp-01.""",
    """No. 13 instances are in use against 11 licensed, an excess of 2 instances, and with license autoupdate VBR keeps backing everything up while the overage is under 10 instances. You are out of compliance, though: add 2 more instances than you have now, or revoke legacy-erp-01.""",
]

BAD = {
    "over_by_two": (
        "13 of 11 instances are used. With autoupdate enabled VBR keeps processing every workload, so nothing breaks "
        "tonight; still, add instances to the license."
    ),
}

_ALLOWED = (
    "It is acceptable, and not a violation, to list the licensed workloads, to note that legacy-erp-01 still counts "
    "under the 31-day rule and will be released automatically about 6 days from now, to suggest revoking it or "
    "removing VMs from jobs as advice, to mention the capacity license, or to quote the exceeding thresholds as a "
    "percentage of the license."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G2-23",
        inputs=CaseInputs(
            question="We're now using 13 instances on an 11-instance license. Will backups start failing?",
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G2", "base_stand": "1.11"},
        evaluators=[
            # the license and its autoupdate setting; list_jobs, list_protected_objects and create_license_report are
            # reads the case allows on top
            ToolCorrectness(expected_tools=["get_license_status"], allow_extra=True),
            *tool_budget(3),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "verdict",
                "The output answers that backups will not start failing at this level: with license autoupdate "
                "enabled, 2 instances over the 11 licensed is an overage VBR still processes normally.",
            ),
            _judge(
                "no_hard_limit",
                "The output does not claim that workloads beyond the 11 licensed instances are not processed, that "
                "backups stop or fail now, or that they will stop at the next instance added.",
            ),
            _judge(
                "policy_correct",
                "If the output describes VBR's policy for exceeding an instance license, what it says agrees with "
                "this: with license autoupdate enabled, less than 10 instances (or 10% of the license, whichever is "
                "greater) over - all workloads processed, no warning; 10 to 20 over - all processed, a weekly "
                "warning; more than 20 over - the excess workloads are not processed. An output that does not "
                "describe the policy meets this criterion.",
            ),
            _judge(
                "compliance",
                "The output makes clear that using more instances than licensed still needs fixing (it is out of "
                "compliance with the licensing policy) and suggests adding instances to the license or freeing "
                "some.",
            ),
            _judge(
                "no_license_change_claimed",
                "The output does not claim to have revoked a license or changed a job; suggesting it is fine.",
            ),
        ],
    )
