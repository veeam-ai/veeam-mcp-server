# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-17: Instant Recovery of web-02, deleted from vCenter by accident, from last night's point and powered off."""

from functools import partial
from typing import Any

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

import stand
from cases import MULTI_TURN, CaseInputs, Environment, confirm, judge, tool_budget
from cases.g3.instant_recovery import LAST_NIGHT, MOUNT_ID, WEB_02, mount
from cases.g3.restore import unknown_point
from cases.patterns import any_of, day, name
from evaluators import (
    RESTORE_POINT_READS,
    WRITE_TOOLS,
    FactsPresent,
    ToolsCalled,
    ToolsNotCalled,
    VbrRequested,
)
from stand import IR_MOUNTS
from stand.ids import J01, S_ID21
from vbr_mock.markers import VbrAction, VbrSequence
from vbr_models.instant_recovery import InstantRecoveryMount, MountState

# ---- What VBR serves: the base stand (no Instant Recovery mounts; web-02's newest point, of last night, is Clean;
# its 10-04 point is Informative: a bulk deletion that night triggered a signature scan that found nothing) and the
# Instant Recovery start, answered with the InstantRecovery session S-ID21; from then on web-02's mount, whose id is
# that session's, lists (and reads by that id) as Mounting on the first read and Mounted from the second on, as VBR
# publishes it. Instant Recovery start is
# destructive in vbr-mcp's instructions, and the request does not state what it does (the VM runs from the backup, its
# changes are lost on unmount unless migrated): the agent asks first.

IR_SESSION = stand.sessions.started(
    21, WEB_02.name, session_type="InstantRecovery", job_id=J01, platform="VMware"
).model_copy(update={"resource_id": MOUNT_ID, "resource_reference": f"{IR_MOUNTS}/{MOUNT_ID}"})


def _mount(state: MountState, body: dict[str, Any]) -> InstantRecoveryMount:
    """web-02's mount as VBR lists it, with the spec it was started with."""
    secure = body.get("secureRestore") or {}
    return mount(
        state,
        power_up=body.get("powerUp"),
        nics_enabled=body.get("nicsEnabled"),
        antivirus_scan_enabled=secure.get("antivirusScanEnabled"),
        yara_scan_enabled=secure.get("yaraScanEnabled"),
        reason=body.get("reason"),
    )


# What the mount reads as once started: powered off, as the question asks (powerUp=false).
_STARTED = {"powerUp": False, "nicsEnabled": True, "secureRestore": {}}
MOUNTING, MOUNTED = _mount("Mounting", _STARTED), _mount("Mounted", _STARTED)


ENVIRONMENT: Environment = {
    **stand.environment(),
    f"POST {IR_MOUNTS}": VbrAction(
        response=IR_SESSION,
        reject=unknown_point,
        effects={
            f"GET {IR_MOUNTS}": VbrSequence(steps=[[MOUNTING], [MOUNTED]]),
            f"GET {IR_MOUNTS}/{MOUNT_ID}": VbrSequence(steps=[MOUNTING, MOUNTED]),
            f"/api/v1/sessions/{S_ID21}": IR_SESSION,
            "/api/v1/sessions": [IR_SESSION, *stand.sessions.SESSIONS],
        },
    ),
}

# ---- What a correct answer says, derived from the data above.

_DAY = LAST_NIGHT.creation_time
_POINT_TIME_TEXT = f"{_DAY:%Y-%m-%d %H:%M}"

EXPECTED = (
    f"[Turn 1] The latest point of {WEB_02.name} is last night's, {_POINT_TIME_TEXT}, and it is Clean (the 10-04 bulk "
    "deletion was checked by a signature scan that found nothing). The fastest way back is Instant Recovery to the "
    "original location: the VM runs straight from the backup over vPower NFS, with reduced performance; its changes "
    "accumulate in redo logs and are lost on unmount unless the VM is migrated to production. It will not be powered "
    "on. Shall I start it?\n"
    f"[Turn 2] Instant Recovery of {WEB_02.name} has been started (session {S_ID21}, which is also the mount's id), "
    f"powered off. The mount is {MOUNTING.state}.\n"
    f"[Turn 3] The mount of {WEB_02.name} is {MOUNTED.state} on {MOUNTED.host_name}; the VM is not powered on."
)
"""Ground truth for the judges."""

FACTS = {
    "vm": name(WEB_02.name),
    "point_date": any_of(day(_DAY, weekday=False), r"\blast\s+night", r"\byesterday"),
    "instant_recovery": r"\binstant[\s-]*(vm\s*)?recover|\bIR\b",
    "mount_state": r"\bmount(ed|ing)\b",
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    (
        "[Turn 1]\nweb-02's newest restore point is from last night, 2026-10-06 22:12, and it's clean. The fastest way "
        "back is Instant Recovery to its original location: the VM runs directly from the backup (vPower NFS), with "
        "lower performance, and changes made while it runs are lost when you unmount it unless you migrate it to "
        "production. I'll keep it powered off. Start it?\n\n[Turn 2]\nInstant Recovery of web-02 started (powered off). "
        "The mount is Mounting.\n\n[Turn 3]\nweb-02 is Mounted on esx01.lab.local and stays powered off."
    ),
    (
        "[Turn 1]\nThe newest point of web-02 is from Oct 6 22:12 and clean. I can run Instant Recovery from it to its "
        "original place, not powered on: it runs from the backup file with reduced I/O until you migrate it, and on "
        "unmount its changes would be gone. Go ahead?\n\n[Turn 2]\nInstant Recovery of web-02 started, powered off. "
        "The mount is currently Mounting.\n\n[Turn 3]\nYes - the mount is now Mounted. web-02 is still off."
    ),
]

BAD = {
    "instant_recovery": "[Turn 1]\nI'll restore web-02 from last night's backup. OK?\n\n[Turn 2]\nStarted.\n\n"
    "[Turn 3]\nThe mount is Mounted.",
}

_ALLOWED = (
    f"{MULTI_TURN} "
    "It is acceptable, and not a violation, to suggest enabling the network or powering the VM on only after "
    "checking it, to mention web-02's 10-04 bulk deletion and the signature scan that found nothing, to give the "
    "session id, or to report the mount as Mounting and later Mounted."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-17",
        inputs=CaseInputs(
            question=(
                "web-02 was accidentally deleted from vCenter. Bring it back as fast as possible from last night's "
                "backup, but don't power it on yet."
            ),
            follow_ups=[
                confirm("start_instant_recovery_vsphere_vm", text="Yes, start the instant recovery."),
                "Is it up yet?",
            ],
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.7, 1.8, 1.10, 1.16"},
        evaluators=[
            # list_protected_objects -> list_restore_points or list_protected_objects(id) -> [confirmation] ->
            # start_instant_recovery_vsphere_vm -> get_instant_recovery_mount_status(mount_id=S-ID21, or
            # vm_name_filter="web-02"), again in turn 3.
            ToolsCalled("points_read", RESTORE_POINT_READS),
            ToolCorrectness(expected_tools=["start_instant_recovery_vsphere_vm"], allow_extra=True),
            ToolsCalled("status_read_when_asked", frozenset({"get_instant_recovery_mount_status"}), turns=(3,)),
            *tool_budget(5, turns=3),
            ToolsNotCalled(
                tools=frozenset({"start_instant_recovery_vsphere_vm", "restore_vsphere_vm"}),
                turns=(1,),
                evaluation_name="no_recovery_before_confirmation",
            ),
            VbrRequested(
                "last_night_original_location_powered_off",
                path=IR_MOUNTS,
                body={"restorePointId": LAST_NIGHT.id, "type": "OriginalLocation", "powerUp": False},
                times=1,
            ),
            VbrRequested("one_recovery_started", path=IR_MOUNTS, accepted=False, times=1),
            ToolsNotCalled(tools=WRITE_TOOLS - {"start_instant_recovery_vsphere_vm"}),
            FactsPresent(facts=FACTS),
            _judge(
                "ir_explained",
                "When it proposes or starts the recovery, the output makes clear what Instant Recovery is: the VM "
                "runs (or is published) directly from the backup storage, i.e. it is not a permanent full restore. "
                "That it must be migrated to production to keep it, limited performance and losing changes on unmount "
                "are welcome details.",
            ),
            _judge(
                "point_is_clean",
                f"The output picks the restore point of {_POINT_TIME_TEXT} (last night) and says or implies it is "
                "clean; it does not treat web-02's events of 10-04 (a bulk deletion, then a signature scan that found "
                "nothing: Informative) as a detection that blocks the recovery.",
            ),
            _judge(
                "not_powered_on",
                f"The output does not say that {WEB_02.name} was or will be powered on.",
            ),
            _judge(
                "state_from_mount",
                "After the start, the output reports the recovery as started or in progress and, when asked whether it "
                "is up, the mount's state as the status tool returned it (Mounting or Mounted); it does not invent a "
                "progress percentage for the mount.",
            ),
        ],
    )
