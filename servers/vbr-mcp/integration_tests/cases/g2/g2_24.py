# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G2-24: why the license counts 10 instances when 8 VMs and 3 laptops are backed up - VBR's 31-day rule."""

from datetime import timedelta
from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

import stand
from cases import CaseInputs, judge, tool_budget
from cases import patterns as p
from evaluators import FactsPresent, ToolsCalled, ToolsNotCalled
from stand import by_id, jobs, license, protected
from stand.ids import J07, J09, T0
from vbr_models.jobs import BackupJob

# ---- What VBR serves: the base stand as it is - the license (1.11), the jobs (1.2) and the restore points (1.8).
# The instance list holds nine VMs at one instance and three laptops at 0.33. Eight of the VMs are in jobs that run;
# the ninth, legacy-erp-01, is in Legacy-Archive, disabled since its run of 2026-09-12, 25 days before T0. VBR counts it
# anyway: "Workloads that have been processed in the past 31 days are considered protected. Every protected workload
# consumes instances from the license scope." (User Guide v13, licensing). A machine no longer processed "will remain
# assigned to that machine for 31 days and then automatically release" (KB1470). The NAS share and the S3 bucket are
# on the capacity license, which counts data sources the same way, not instances.

ENVIRONMENT = stand.environment()

SUMMARY = license.LICENSE.instance_license_summary
assert SUMMARY is not None and SUMMARY.objects is not None
USED, LICENSED = int(SUMMARY.used_instances_number), int(SUMMARY.licensed_instances_number)
WORKSTATIONS = next(row for row in SUMMARY.objects if row.type == "Workstations")

LEGACY_JOB = by_id(jobs.JOB_STATES, J07)
LEGACY_POINT = protected.points_of("legacy-erp-01")[0]  # made by that last Legacy-Archive run
RELEASED = LEGACY_POINT.creation_time + timedelta(days=31)
DAYS_TO_RELEASE = (RELEASED - T0).days
ACTIVE_VMS = [
    vm.name
    for job in jobs.JOBS
    if isinstance(job, BackupJob) and not job.is_disabled and job.id != J09  # Test-NewApp has never run
    for vm in job.virtual_machines.includes
]
assert len(ACTIVE_VMS) == 8 and USED == 10

# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    f"The license shows {USED} of {LICENSED} instances used: the {len(ACTIVE_VMS)} VMs of the jobs that run "
    f"({', '.join(ACTIVE_VMS)}) at one instance each, legacy-erp-01 at one more, and the {WORKSTATIONS.count} laptops "
    f"at a third of an instance each ({WORKSTATIONS.used_instances_number:g} together). legacy-erp-01 still counts "
    f"although its job, Legacy-Archive, has been disabled since its last run on {LEGACY_POINT.creation_time:%Y-%m-%d}: "
    "VBR treats every workload processed in the past 31 days as protected, and a protected workload consumes "
    f"instances. Its instance is released automatically 31 days after that backup, around {RELEASED:%Y-%m-%d} "
    f"({DAYS_TO_RELEASE} days from now), unless Legacy-Archive backs it up again; it can also be revoked now, and "
    "would come back if the job ran again. new-app-01 (Test-NewApp) has never been backed up and consumes nothing; "
    "the NAS share and the S3 bucket are covered by the capacity license, not by instances."
)
"""Ground truth for the judges."""

FACTS = {
    "legacy_erp_01": p.name("legacy-erp-01"),
    "31_days": p.any_of(
        r"(?<![\d.])31[-\s]*(?:calendar\s+)?days?\b",
        r"\b(?:past|last|previous)\s+(?:calendar\s+)?month\b",
        r"\bwithin\s+(?:a|one|the\s+last)\s+month\b",
    ),
    "workstation_weight": p.any_of(
        r"(?<![\d.])1\s*/\s*3\b",
        r"(?<![\d.])0?\.33\b",
        r"\bone[\s-]third\b",
        r"\ba\s+third\b",
        r"\b(?:three|3)\s+(?:laptops|workstations)\b[^.\n]{0,60}?\b(?:one|1)\s+instance\b",
    ),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

_ALLOWED = (
    "It is acceptable, and not a violation, to offer to revoke legacy-erp-01's license without doing it, to say that "
    "its restore points stay usable after the license is released, to mention that the capacity license covers the "
    f"NAS share and the S3 bucket (1.5 of 5 TB), to give the release date as about {DAYS_TO_RELEASE} days from now, "
    "or to note that 0.33 is VBR's rounding of a third."
)

GOOD = [
    (
        f"The license shows {USED} of {LICENSED} instances in use, and the breakdown explains the gap:\n\n"
        "- 8 VMs in the jobs that run: web-01, web-02, app-01, fs-01, sql-prod-01, sql-prod-02, sql-dev-01, report-01 "
        "(1 instance each).\n"
        "- legacy-erp-01: 1 instance. Its job, Legacy-Archive, is disabled, but its last run was on 2026-09-12, and VBR "
        "counts every workload processed in the past 31 days as protected, so it still consumes an instance.\n"
        "- 3 laptops: a workstation is 1/3 of an instance (0.33 in VBR), so the three together are 1 instance.\n\n"
        "8 + 1 + 1 = 10. legacy-erp-01 stops counting on its own around Oct 13, 31 days after that last backup, unless "
        "the job runs again; or you can revoke its license now."
    ),
    (
        "Your tenth instance is **legacy-erp-01**. Legacy-Archive was disabled after its run of September 12th, yet a "
        "machine backed up within the last 31 days is still protected in VBR's eyes and keeps its instance; the license "
        "is released automatically 31 days after the last backup (in about 6 days), or you can revoke it.\n\n"
        "| Workload | Count | Instances |\n|---|---|---|\n| VMs in running jobs | 8 | 8 |\n"
        "| legacy-erp-01 (job disabled) | 1 | 1 |\n| Laptops (one-third instance each) | 3 | 1 |\n"
        "| **Total** | | **10 of 11** |\n\nnew-app-01 has never been backed up, and the file share and the S3 bucket "
        "use the capacity license, so none of them takes an instance."
    ),
    (
        "Ten instances = 9 VMs + 1 for the laptops. The ninth VM is legacy-erp-01: Legacy-Archive is off, but it backed "
        "the VM up 25 days ago, and VBR counts anything it processed in the past month as protected. The 3 laptops count "
        "as one instance together (0.33 each). If you don't re-enable the job, the instance frees itself around "
        "2026-10-13."
    ),
]

BAD = {
    "legacy_erp_01": (
        "You're using 10 instances because new-app-01 in Test-NewApp was already counted, and the three laptops "
        "count as a third each. VBR keeps counting workloads for 31 days."
    ),
    "31_days": (
        "The extra instance is legacy-erp-01: Legacy-Archive still exists, so VBR keeps its license reserved for as "
        "long as the job is there. The three laptops are a third of an instance each."
    ),
    "workstation_weight": (
        "legacy-erp-01 still counts because it was backed up in the past 31 days, and each laptop is one more instance."
    ),
}


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G2-24",
        inputs=CaseInputs(
            question="We back up only 8 VMs and 3 laptops, so why does our license show 10 instances in use?",
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G2", "base_stand": "1.11"},
        evaluators=[
            # get_license_status -> what legacy-erp-01's job did lately: get_job_states / list_jobs / its points
            ToolCorrectness(expected_tools=["get_license_status"], allow_extra=True),
            ToolsCalled(
                "found_legacy_backup",
                frozenset({
                    "get_job_states",
                    "list_jobs",
                    "list_restore_points",
                    "list_protected_objects",
                    "list_backups",
                    "get_backup_details",
                    "list_sessions",
                }),
            ),
            *tool_budget(3),
            ToolsNotCalled(),  # revoke_license among them: the question asks why, not to free anything
            FactsPresent(facts=FACTS),
            _judge(
                "why_legacy_counts",
                "The output explains that legacy-erp-01 still consumes an instance because VBR counts a workload as "
                "protected for 31 days after it was last backed up, and Legacy-Archive, although disabled, last "
                f"backed it up on {LEGACY_POINT.creation_time:%Y-%m-%d}, less than 31 days ago.",
            ),
            _judge(
                "instances_add_up",
                "The output accounts for the 10 instances consistently with the expected output: the eight VMs of "
                "the running jobs plus legacy-erp-01 at one instance each, and the three laptops at a third of an "
                "instance each, one together. It gives no breakdown that sums to another total.",
            ),
            _judge(
                "how_it_stops",
                "The output says how legacy-erp-01 stops counting: its instance is released automatically once 31 "
                f"days pass without a backup (around {RELEASED:%Y-%m-%d}, unless Legacy-Archive runs again), or its "
                "license can be revoked. Either one is enough.",
            ),
            _judge(
                "no_wrong_cause",
                "The output does not attribute any of the 10 instances to new-app-01 or Test-NewApp (it has never "
                "been backed up), to the NAS share or the S3 bucket (they are on the capacity license), or to fs-01 "
                "appearing twice in the protected objects.",
            ),
        ],
    )
