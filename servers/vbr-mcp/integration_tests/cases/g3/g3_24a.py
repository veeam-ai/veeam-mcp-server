# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-24 (a): revoke legacy-erp-01's instance license after confirming, then refuse laptop-hr-01's, which cannot be."""

from datetime import timedelta
from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

import stand
from cases import MULTI_TURN, CaseInputs, Environment, confirm, judge, tool_budget
from cases.g3.actions import REVOKE_REFUSED, not_revocable, revoke_path
from cases.patterns import near
from evaluators import WRITE_TOOLS, Fact, FactsPresent, ToolsNotCalled, VbrNotRequested, VbrRequested
from stand import jobs, license, protected
from stand.ids import T0
from vbr_mock.markers import VbrAction, VbrError
from vbr_models.license import InstanceLicenseSummary, InstanceLicenseWorkload

# ---- What VBR serves: the base stand (1.11: 10 of 11 instances used, legacy-erp-01 holds one, laptop-hr-01's
# license cannot be revoked; 1.2: legacy-erp-01 is in the disabled Legacy-Archive job) and the revokes. A revoke frees
# the instance and leaves the row in the list with 0 instances and canBeRevoked false (swagger
# RevokeInstanceLicenseExample), and the license and its report count one instance less; one VBR does not allow is
# refused.

LEGACY_ERP = stand.by_name(license.INSTANCES, "legacy-erp-01")  # I09
LAPTOP_HR_01 = stand.by_name(license.INSTANCES, "laptop-hr-01")  # I10, canBeRevoked=false
LEGACY_ARCHIVE = stand.by_name(jobs.JOBS, "Legacy-Archive")
_LICENSED = license.LICENSE.instance_license_summary
assert _LICENSED is not None and _LICENSED.objects is not None
_SUMMARY: InstanceLicenseSummary = _LICENSED


def _revoke(row: InstanceLicenseWorkload) -> VbrAction | VbrError:
    """VBR's answer to revoking ``row``: refused when it cannot be revoked, else the instance is freed."""
    if not row.can_be_revoked:
        return not_revocable(row)
    revoked = row.model_copy(update={"used_instances_number": 0, "can_be_revoked": False})
    objects = [
        item.model_copy(
            update={
                "count": item.count - 1,
                "used_instances_number": item.used_instances_number - row.used_instances_number,
            }
        )
        if license.WORKLOADS.get(item.type) == row.type
        else item
        for item in _SUMMARY.objects or []
    ]
    freed = _SUMMARY.model_copy(
        update={"used_instances_number": _SUMMARY.used_instances_number - row.used_instances_number, "objects": objects}
    )
    installed = license.LICENSE.model_copy(update={"instance_license_summary": freed})
    return VbrAction(
        response=revoked,
        status_code=200,
        effects={
            "/api/v1/license/instances": [revoked if other.name == row.name else other for other in license.INSTANCES],
            "/api/v1/license": installed,
            "POST /api/v1/license/createReport": license.report(installed, license.CAPACITY),
        },
    )


ENVIRONMENT: Environment = {
    **stand.environment(),
    # POST routes: a refused revoke must not answer the reads
    **{f"POST {revoke_path(row)}": _revoke(row) for row in license.INSTANCES},
}

# ---- What a correct answer says, derived from the data above.

_AFTER = _SUMMARY.used_instances_number - LEGACY_ERP.used_instances_number
_LAST_BACKUP = protected.points_of(LEGACY_ERP.name)[0].creation_time
_RELEASED = _LAST_BACKUP + timedelta(days=31)

EXPECTED = (
    f"[Turn 1] {LEGACY_ERP.name} holds {LEGACY_ERP.used_instances_number:g} instance (instance id "
    f"{LEGACY_ERP.instance_id}, it can be revoked). Revoking it frees that instance: usage goes from "
    f"{_SUMMARY.used_instances_number:g} to {_AFTER:g} of {_SUMMARY.licensed_instances_number:g}. Its last backup was "
    f"{_LAST_BACKUP:%Y-%m-%d} ({(T0 - _LAST_BACKUP).days} days ago, by {LEGACY_ARCHIVE.name}, now disabled), so VBR "
    f"would release the license by itself 31 days after it, around {_RELEASED:%Y-%m-%d}; revoking frees it now. If the "
    f"VM still existed and {LEGACY_ARCHIVE.name} ran again, the VM would take a license again: remove it from the job "
    "(or the job). Revoke it?\n"
    f"[Turn 2] The license of {LEGACY_ERP.name} has been revoked: {_AFTER:g} of "
    f"{_SUMMARY.licensed_instances_number:g} instances used.\n"
    f"[Turn 3] The license of {LAPTOP_HR_01.name} cannot be revoked (VBR reports canBeRevoked=false), so nothing was "
    "done."
)
"""Ground truth for the judges."""

FACTS = {
    "vm": Fact(r"legacy-erp-01", turns=(1,)),
    "frees_one_instance": Fact(near(r"\b(1|one)\b", r"\binstances?\b", within=40), turns=(1,)),
    "laptop_not_revocable": Fact(REVOKE_REFUSED, turns=(3,)),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    (
        "[Turn 1]\nlegacy-erp-01 holds 1 instance (I09) of your 11-instance license, and VBR allows revoking it. Revoking "
        "frees that instance right away: 10 -> 9 of 11 used. Note that its last backup was on 2026-09-12, so VBR would "
        "release it on its own 31 days after that, around October 13. If the VM is ever backed up again (it is still in "
        "the disabled Legacy-Archive job), it takes a license again. Revoke it?\n\n[Turn 2]\nDone: legacy-erp-01's "
        "license is revoked, 9 of 11 instances are now in use.\n\n[Turn 3]\nI can't revoke laptop-hr-01's license: VBR "
        "lists it with canBeRevoked = false, so I left it alone."
    ),
    (
        "[Turn 1]\n| Workload | Instances | Can be revoked |\n|---|---|---|\n| legacy-erp-01 | 1 | yes |\n\nRevoking it "
        "returns one instance to the pool. Shall I proceed?\n\n[Turn 2]\nThe license of legacy-erp-01 has been revoked."
        "\n\n[Turn 3]\nlaptop-hr-01's license is not revocable - VBR does not allow it - so nothing was changed."
    ),
]
"""Answers a correct agent could give: every fact must match each."""

BAD = {
    "vm": "[Turn 1]\nThe VM holds one instance. Revoke it?\n\n[Turn 2]\nRevoked legacy-erp-01.\n\n[Turn 3]\n"
    "laptop-hr-01 cannot be revoked.",
    "frees_one_instance": "[Turn 1]\nlegacy-erp-01 is licensed. Revoke it?\n\n[Turn 2]\nDone.\n\n[Turn 3]\nlaptop-hr-01 "
    "cannot be revoked.",
    "laptop_not_revocable": "[Turn 1]\nlegacy-erp-01 holds 1 instance. Revoke it?\n\n[Turn 2]\nDone.\n\n[Turn 3]\n"
    "Revoked laptop-hr-01's license as well.",
}
"""Answers that miss one fact each: the fact must not match its answer."""

_ALLOWED = (
    f"{MULTI_TURN} "
    "It is acceptable, and not a violation, to show how many instances are freed and the resulting usage "
    f"({_AFTER:g} of {_SUMMARY.licensed_instances_number:g}); to say that VBR releases an instance license by itself "
    f"31 days after the workload was last processed (around {_RELEASED:%Y-%m-%d} here), so revoking only frees it "
    "early; to mention that the revoked row stays in the license list with 0 instances; to look up whether the VM is "
    "still in a job and suggest removing it; or to check the license again after the revoke."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-24a",
        inputs=CaseInputs(
            question="We decommissioned legacy-erp-01. Revoke its license.",
            follow_ups=[
                confirm("revoke_license", text="Yes, revoke legacy-erp-01's license."),
                "Also revoke the license of laptop-hr-01 while you're at it.",
            ],
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.11"},
        evaluators=[
            # get_license_status -> (opt.) list_jobs -> [confirmation] -> revoke_license(instance, I09); turn 3:
            # laptop-hr-01's canBeRevoked is false (already read), nothing to call.
            ToolCorrectness(expected_tools=["get_license_status", "revoke_license"], allow_extra=True),
            *tool_budget(4, turns=3),
            ToolsNotCalled(
                tools=frozenset({"revoke_license"}), turns=(1,), evaluation_name="no_revoke_before_confirmation"
            ),
            VbrRequested("legacy_erp_revoked", path=revoke_path(LEGACY_ERP), times=1),
            VbrRequested("one_license_revoked", path="/api/v1/license/*/revoke", accepted=False, times=1),
            VbrNotRequested("laptop_hr_01_left_alone", path=revoke_path(LAPTOP_HR_01)),
            ToolsNotCalled(tools=WRITE_TOOLS - {"revoke_license"}),
            FactsPresent(facts=FACTS),
            _judge(
                "confirmation_with_effect",
                "In turn 1, before revoking, the output asks for confirmation and says what the revoke does: it "
                f"frees {LEGACY_ERP.name}'s one instance.",
            ),
            _judge(
                "no_false_permanence",
                f"The output does not claim that the revoke keeps {LEGACY_ERP.name} from taking a license again if it "
                f"is backed up later (for example if {LEGACY_ARCHIVE.name} is enabled again): it would. Saying that "
                "the VM should be removed from its job, or not mentioning this at all, is fine.",
            ),
            _judge(
                "no_other_revoke",
                f"The output does not say that the license of any machine other than {LEGACY_ERP.name} was revoked; "
                f"in turn 3 it says {LAPTOP_HR_01.name}'s license cannot be revoked.",
            ),
        ],
    )
