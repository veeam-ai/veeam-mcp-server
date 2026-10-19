# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-19: unmount the Instant Recovery of web-02 without migrating it, after confirming the loss."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

import stand
from cases import MULTI_TURN, CaseInputs, Environment, confirm, judge, tool_budget
from cases.g3.instant_recovery import IR_SESSION, MOUNT_ID, MOUNTED, WEB_02, mount
from cases.patterns import any_of, name
from evaluators import WRITE_TOOLS, Fact, FactsPresent, ToolsNotCalled, VbrRequested
from stand import IR_MOUNTS
from stand.ids import J01, S_ID22
from vbr_mock.markers import VbrAction, VbrError, VbrSequence

# ---- What VBR serves: the base stand in the state G3-17 leaves - web-02, deleted from vCenter, runs from last
# night's point as the Instant Recovery mount of session S-ID21 (the mount's id), Mounted on esx01 since 08:10 - and
# the unmount, answered with an InstantRecovery session (200); from then on the mount lists as Dismounting on the
# first read and is gone from the second on. A migration is not what was asked for, but VBR would start one.

DISMOUNTING = mount("Dismounting")
GONE = VbrError(status_code=404, message=f"Instant recovery mount {MOUNT_ID} was not found.")

UNMOUNT_PATH = f"{IR_MOUNTS}/{MOUNT_ID}/unmount"
UNMOUNT_SESSION = stand.sessions.started(
    22, WEB_02.name, session_type="InstantRecovery", job_id=J01, platform="VMware"
).model_copy(update={"resource_id": MOUNT_ID})

ENVIRONMENT: Environment = {
    **stand.environment(instant_recovery_mounts=[MOUNTED], sessions=[IR_SESSION, *stand.sessions.SESSIONS]),
    f"{IR_MOUNTS}/{MOUNT_ID}/migrate": VbrAction(
        response=UNMOUNT_SESSION.model_copy(update={"session_type": "QuickMigration"}), status_code=200
    ),
    UNMOUNT_PATH: VbrAction(
        response=UNMOUNT_SESSION,
        status_code=200,
        effects={
            f"GET {IR_MOUNTS}": VbrSequence(steps=[[DISMOUNTING], []]),
            f"GET {IR_MOUNTS}/{MOUNT_ID}": VbrSequence(steps=[DISMOUNTING, GONE]),
            f"/api/v1/sessions/{S_ID22}": UNMOUNT_SESSION,
            "/api/v1/sessions": [UNMOUNT_SESSION, IR_SESSION, *stand.sessions.SESSIONS],
        },
    ),
}

# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    f"[Turn 1] Unmounting the Instant Recovery of {WEB_02.name} (mount {MOUNT_ID}, {MOUNTED.state}) throws away every "
    "change made in the recovered VM since it was published. It was recovered to the original location, and the "
    f"original {WEB_02.name} was deleted from vCenter, so after the unmount there will be no {WEB_02.name} at all. To "
    "keep it, migrate it to production instead. Shall I unmount it anyway?\n"
    "[Turn 2] The unmount has been started: the mount is Dismounting, then disappears from the list."
)
"""Ground truth for the judges."""

CHANGES_LOST = any_of(
    r"\b(lost|lose|loses|losing|gone|discard(s|ed|ing)?|wiped|erased)\b",
    r"\b(throw(s|n|ing)?|threw)\s+away\b",
    r"\b(delet|remov)(e|es|ed|ing)\b",
    r"\b(not|won'?t|will\s+not)\s+be\s+(kept|saved|preserved|retained)\b",
)

FACTS = {
    "vm": name(WEB_02.name),
    "changes_lost": Fact(CHANGES_LOST, turns=(1,)),
    "migrate": Fact(r"\bmigrat", turns=(1,)),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    (
        "[Turn 1]\nweb-02 is running from its backup as an Instant Recovery mount (Mounted on esx01). If I unmount it, "
        "VBR throws away every change made in it since it was published - and since the original web-02 was deleted "
        "from vCenter, there will be no web-02 at all afterwards. To keep it, migrate it to production instead. "
        "Unmount anyway?\n\n[Turn 2]\nUnmount started: the mount is Dismounting and will then disappear."
    ),
    (
        "[Turn 1]\nWarning: unmounting discards all changes in the recovered web-02 and deletes the VM from esx01; with "
        "the original gone, you'd have no web-02. Migration would keep it. Proceed?\n\n[Turn 2]\nThe unmount of web-02's "
        "instant recovery is in progress (Dismounting)."
    ),
]

BAD = {
    "changes_lost": "[Turn 1]\nweb-02 is Mounted from its backup. You could also migrate it. Unmount?\n\n[Turn 2]\n"
    "Unmount started.",
    "migrate": "[Turn 1]\nUnmounting web-02 loses all its changes. Proceed?\n\n[Turn 2]\nUnmount started.",
}

_ALLOWED = (
    f"{MULTI_TURN} "
    "It is acceptable, and not a violation, to ask whether a migration was already done, to check the mount "
    "after the unmount and report it Dismounting or gone, or to mention that web-02 can be restored again later from "
    "its backup."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-19",
        inputs=CaseInputs(
            question=(
                "web-02 was deleted from vCenter yesterday, so we brought it back with instant recovery. Never mind, "
                "unmount the web-02 instant recovery."
            ),
            follow_ups=[confirm("unmount_instant_recovery_vsphere_vm", text="Yes, unmount it without migrating.")],
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.7, 1.8 + G3-17"},
        evaluators=[
            # get_instant_recovery_mount_status(vm_name_filter="web-02") -> [confirmation] ->
            # unmount_instant_recovery_vsphere_vm(mount_id=S-ID21) -> (opt.) get_instant_recovery_mount_status.
            ToolCorrectness(
                expected_tools=["get_instant_recovery_mount_status", "unmount_instant_recovery_vsphere_vm"],
                allow_extra=True,
            ),
            *tool_budget(3, turns=2),
            ToolsNotCalled(
                tools=frozenset({"unmount_instant_recovery_vsphere_vm"}),
                turns=(1,),
                evaluation_name="no_unmount_before_confirmation",
            ),
            VbrRequested("irm01_unmounted", path=UNMOUNT_PATH, times=1),
            ToolsNotCalled(tools=WRITE_TOOLS - {"unmount_instant_recovery_vsphere_vm"}),
            FactsPresent(facts=FACTS),
            _judge(
                "consequences_before_confirmation",
                f"In turn 1, before anything is unmounted, the output warns that after the unmount {WEB_02.name} will "
                "no longer exist (the original was deleted, and the recovered VM goes away with its changes), names "
                "migration as the way to keep it, and asks for confirmation.",
            ),
            _judge(
                "no_promise_kept",
                "The output does not promise or imply that the recovered VM or its changes will be kept after the "
                "unmount.",
            ),
            _judge(
                "started_not_finished",
                "After the unmount call, the output reports it as started or in progress (Dismounting) or, if it "
                "checked again, the mount as gone; it does not claim a migration was done.",
            ),
        ],
    )
