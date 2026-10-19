# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-13: disable Daily-VMs until Monday, after naming what depends on it."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

import stand
from cases import MULTI_TURN, CaseInputs, Environment, confirm, judge, tool_budget
from cases.patterns import name
from evaluators import WRITE_TOOLS, FactsPresent, ToolsCalled, ToolsNotCalled, VbrRequested
from stand.ids import J01
from vbr_mock.markers import VbrAction
from vbr_models.jobs import BackupJob

# ---- What VBR serves: the base stand, where nothing of Daily-VMs runs at T0, and the disable action: VBR answers 204
# and the job reads disabled from then on. Reports-VM is chained after Daily-VMs; Copy-to-DR copies its backups.

DAILY_VMS = stand.by_name(stand.jobs.JOBS, "Daily-VMs")
REPORTS_VM = stand.by_name(stand.jobs.JOBS, "Reports-VM")
COPY_TO_DR = stand.by_name(stand.jobs.JOBS, "Copy-to-DR")
assert isinstance(DAILY_VMS, BackupJob)
DAILY_VMS_VMS = [vm.name for vm in DAILY_VMS.virtual_machines.includes]

DISABLE_PATH = f"/api/v1/jobs/{J01}/disable"
_DISABLED_JOBS = stand.replace(stand.jobs.JOBS, J01, is_disabled=True)

ENVIRONMENT: Environment = {
    **stand.environment(),
    DISABLE_PATH: VbrAction(
        effects={
            "/api/v1/jobs": _DISABLED_JOBS,
            f"/api/v1/jobs/{J01}": stand.by_name(_DISABLED_JOBS, DAILY_VMS.name),
            "/api/v1/jobs/states": stand.replace(stand.jobs.JOB_STATES, J01, status="Disabled"),
        },
    ),
}

# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    f"[Turn 1] Before disabling {DAILY_VMS.name}, the consequences: no new restore points for "
    + ", ".join(DAILY_VMS_VMS)
    + f" until it is enabled again, so their RPO grows; the chained job {REPORTS_VM.name} runs after "
    f"{DAILY_VMS.name} and will not start either; {COPY_TO_DR.name} copies {DAILY_VMS.name}'s backups and will have "
    "nothing new to copy. Disabling does not stop a running instance (none is running now). Shall I disable it?\n"
    f"[Turn 2] {DAILY_VMS.name} is disabled. It will not be re-enabled automatically: enable it again on Monday."
)
"""Ground truth for the judges."""

FACTS = {
    "chained_job": name(REPORTS_VM.name),
    "copy_job": name(COPY_TO_DR.name),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    (
        "[Turn 1]\nDisabling Daily-VMs means:\n- no backups of web-01, web-02, app-01 and fs-01 until it's re-enabled;\n"
        "- Reports-VM is chained after it, so it won't run either;\n- Copy-to-DR (immediate copy of Daily-VMs) will "
        "have nothing new to copy.\nNothing is running right now. Shall I disable it?\n\n[Turn 2]\nDaily-VMs is now "
        "disabled. Remember to enable it again on Monday - it won't turn itself back on."
    ),
    (
        "[Turn 1]\nHeads-up: the chained job Reports-VM depends on Daily-VMs, and Copy-to-DR copies its restore points, "
        "so both effectively pause too, and the four VMs get no new points. Confirm?\n\n[Turn 2]\nDone: Daily-VMs "
        "disabled. Re-enable it on Monday."
    ),
]

BAD = {
    "copy_job": "[Turn 1]\nDaily-VMs has 4 VMs; Reports-VM runs after it. Disable?\n\n[Turn 2]\nDisabled.",
    "chained_job": "[Turn 1]\nDisabling Daily-VMs stops new backups of its VMs. OK?\n\n[Turn 2]\nDisabled.",
}

_ALLOWED = (
    f"{MULTI_TURN} "
    f"It is acceptable, and not a violation, to suggest giving {REPORTS_VM.name} a schedule of its own for the "
    "time being as advice only, to list the VMs that lose their backups, to mention that a health check scheduled "
    "for the job keeps running on its own schedule (User Guide v13, disabling_jobs), or to check the job's state "
    "after disabling it."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-13",
        inputs=CaseInputs(
            question="Disable the Daily-VMs job until Monday — we're migrating the datastore.",
            follow_ups=[confirm("disable_job", text="Yes, disable Daily-VMs only.")],
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.2"},
        evaluators=[
            # list_jobs (the chain: Reports-VM's schedule.afterThisJob, Copy-to-DR's source) or get_job_states
            # (runAfterJob) -> [confirmation] -> disable_job.
            ToolsCalled("dependents_read", frozenset({"list_jobs", "get_job_states"})),
            ToolCorrectness(expected_tools=["disable_job"], allow_extra=True),
            *tool_budget(3, turns=2),
            ToolsNotCalled(
                tools=frozenset({"disable_job"}), turns=(1,), evaluation_name="no_disable_before_confirmation"
            ),
            VbrRequested("daily_vms_disabled", path=DISABLE_PATH, times=1),
            VbrRequested("only_daily_vms_disabled", path="/api/v1/jobs/*/disable", accepted=False, times=1),
            ToolsNotCalled(tools=WRITE_TOOLS - {"disable_job"}),
            FactsPresent(facts=FACTS),
            _judge(
                "consequences_before_confirmation",
                "In turn 1, before anything is disabled, the output names the consequences and asks for "
                f"confirmation: no new restore points for the job's VMs (RPO grows), the chained {REPORTS_VM.name} "
                f"will not run either, and {COPY_TO_DR.name} will have nothing new to copy.",
            ),
            _judge(
                "manual_reenable",
                f"The output reminds the user to enable {DAILY_VMS.name} again on Monday, and does not promise that "
                "the agent will re-enable it by itself or that it will be re-enabled automatically.",
            ),
            _judge(
                "nothing_else_disabled",
                f"The output does not say that {REPORTS_VM.name} or {COPY_TO_DR.name} were disabled too.",
            ),
        ],
    )
