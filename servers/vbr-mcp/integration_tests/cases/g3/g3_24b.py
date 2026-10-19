# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-24 (b): revoke laptop-hr-01's license, which VBR does not allow: say so, call nothing."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

import stand
from cases import CaseInputs, Environment, judge, tool_budget
from cases.g3.actions import REVOKE_REFUSED, not_revocable, revoke_path
from evaluators import FactsPresent, ToolsNotCalled, VbrNotRequested
from stand import license
from vbr_mock.markers import VbrAction

# ---- What VBR serves: the base stand (1.11: laptop-hr-01's instance license has canBeRevoked=false) and the revokes,
# accepted where VBR allows them, so that a revoke of another machine would do what VBR does.

LAPTOP_HR_01 = stand.by_name(license.INSTANCES, "laptop-hr-01")  # I10


ENVIRONMENT: Environment = {
    **stand.environment(),
    **{
        f"POST {revoke_path(row)}": VbrAction(status_code=200) if row.can_be_revoked else not_revocable(row)
        for row in license.INSTANCES
    },
}

# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    f"The license of {LAPTOP_HR_01.name} cannot be revoked: VBR reports canBeRevoked=false for it "
    f"({LAPTOP_HR_01.used_instances_number:g} instance, {LAPTOP_HR_01.type}), so nothing was done. (Revoking an "
    "agent's license would also disconnect that computer from the backup server until it is removed from the license "
    "list.)"
)
"""Ground truth for the judges."""

FACTS = {
    "machine": r"laptop-hr-01",
    "cannot": REVOKE_REFUSED,
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    (
        "I checked the license: laptop-hr-01 holds 0.33 instance (Workstation), but VBR marks it canBeRevoked = false, so "
        "its license cannot be revoked. I didn't change anything."
    ),
    (
        "laptop-hr-01's license isn't revocable - VBR does not permit revoking it. Nothing was done. If you need the "
        "instance back, check the agent's state in the VBR console."
    ),
    (
        "| Machine | Instances | Revocable |\n|---|---|---|\n| laptop-hr-01 | 0.33 | no |\n\nVBR won't let me revoke this "
        "one, so I left it as is."
    ),
]
"""Answers a correct agent could give: every fact must match each."""

BAD = {
    "cannot": "Done: the license of laptop-hr-01 has been revoked and its 0.33 instance is free again.",
    "machine": "That license cannot be revoked, so nothing was done.",
}
"""Answers that miss one fact each: the fact must not match its answer."""

_ALLOWED = (
    "It is acceptable, and not a violation, to show laptop-hr-01's license row (0.33 instance, Workstation), to "
    "explain why VBR might not allow the revoke, to mention that revoking an agent's license disconnects that "
    "computer from the backup server until it is removed from the list, or to suggest the VBR console for license "
    "management."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-24b",
        inputs=CaseInputs(question="Revoke the license from laptop-hr-01.", environment=ENVIRONMENT),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.11"},
        evaluators=[
            ToolCorrectness(expected_tools=["get_license_status"], allow_extra=True),
            *tool_budget(1),
            ToolsNotCalled(),  # canBeRevoked=false: no revoke, and nothing else instead
            VbrNotRequested("no_revoke_requested", path="/api/v1/license/*/revoke"),
            FactsPresent(facts=FACTS),
            _judge(
                "not_revoked",
                f"The output says the license of {LAPTOP_HR_01.name} cannot be revoked (VBR does not allow it) and "
                "does not claim it was revoked.",
            ),
        ],
    )
