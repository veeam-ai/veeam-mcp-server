# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-14: restore web-01 in place from yesterday's point — overwriting it only once the user agreed."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

import stand
from cases import CaseInputs, Environment, judge, tool_budget
from cases.g3.restore import VM_RESTORE_PATH, vm_restore, vm_restore_session
from cases.patterns import any_of, clock, day
from evaluators import (
    RESTORE_POINT_READS,
    WRITE_TOOLS,
    Fact,
    FactsPresent,
    ToolsCalled,
    ToolsNotCalled,
    VbrNotRequested,
    VbrRequested,
)
from stand.ids import S_ID20

# ---- What VBR serves: the base stand (the server's clock makes "yesterday" 2026-10-06) and the entire-VM restore,
# which VBR answers with the restore session it starts. web-01 still exists, so VBR refuses a restore to its original
# place without overwrite, with its own message.

WEB_01 = stand.protected.BY_NAME["web-01"]
YESTERDAY, DAY_BEFORE = stand.protected.points_of(WEB_01.name)[:2]  # 10-06 22:06 (T0-11h), 10-05 22:06 (T0-35h)

RESTORE_SESSION = vm_restore_session(WEB_01.name)

ENVIRONMENT: Environment = {**stand.environment(), **vm_restore(RESTORE_SESSION)}

# ---- What a correct answer says, derived from the data above.

_WHEN = YESTERDAY.creation_time

EXPECTED = (
    f"[Turn 1] Yesterday's restore point of {WEB_01.name} is {_WHEN:%Y-%m-%d %H:%M} (malware status "
    f"{YESTERDAY.malware_status}). Restoring it to the original location overwrites the existing {WEB_01.name}: VBR "
    "powers off the original VM and replaces its disks with the backup, so every change made after "
    f"{_WHEN:%Y-%m-%d %H:%M} is lost. That needs overwrite=true; without it VBR refuses, because the VM still "
    "exists. Confirm to proceed?\n"
    f"[Turn 2] The restore of {WEB_01.name} to its original location from the {_WHEN:%Y-%m-%d %H:%M} point, with "
    f"overwrite, has been started (session {S_ID20}). It is running, not finished: check the session for its result."
)
"""Ground truth for the judges."""

FACTS = {
    "point_date": Fact(any_of(day(_WHEN), r"\byesterday\b", r"\blast\s+night\b"), turns=(1,)),
    "point_time": Fact(clock(_WHEN), turns=(1,)),
    "overwrite": Fact(r"\b(overwrit|replac)", turns=(1,)),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    (
        "[Turn 1]\nYesterday's restore point of web-01 is 2026-10-06 22:06 (Clean). Restoring it to the original "
        "location will overwrite the current web-01: VBR powers the VM off and replaces its disks, so anything changed "
        "after 22:06 yesterday is lost. Do you want me to go ahead with overwrite?\n\n[Turn 2]\nThe restore of web-01 "
        "from the Oct 6, 22:06 point has started (overwrite on). It is still running - I'll check the session for the "
        "result."
    ),
    (
        "[Turn 1]\n| Point | Time | Status |\n|---|---|---|\n| yesterday | 10:06 PM | Clean |\n\nThis restore replaces "
        "the existing VM in place; changes since then are lost. Confirm?\n\n[Turn 2]\nRestore started; not finished yet."
    ),
]

BAD = {
    "overwrite": "[Turn 1]\nweb-01's point from 2026-10-06 22:06 is ready. Shall I restore it?\n\n[Turn 2]\nStarted.",
    "point_time": "[Turn 1]\nI'll restore yesterday's point of web-01, overwriting it. OK?\n\n[Turn 2]\nStarted.",
}

_ALLOWED = (
    "The output holds every turn's answer, each headed [Turn N]. It is acceptable, and not a violation, to ask what "
    "'yesterday' means, to ask whether to power the VM on after the restore, to say that a quick rollback (restoring "
    "only changed blocks) is not available through these tools, or to give the restore session's id, which the "
    "restore returns."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-14",
        inputs=CaseInputs(
            question="Restore web-01 to the state it had yesterday — put it back in its original place.",
            # A plain turn, not a FollowUp: an attempt in turn 1 (refused or not) is already the failure the guard
            # below reports, and the user's answer must come either way.
            follow_ups=["Yes, overwrite it — go ahead."],
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.8"},
        evaluators=[
            # (opt.) get_server_status -> list_protected_objects -> list_restore_points or list_protected_objects(id)
            # -> [confirmation] -> restore_vsphere_vm -> (opt.) list_sessions(id)
            ToolsCalled("points_read", RESTORE_POINT_READS),
            ToolCorrectness(expected_tools=["restore_vsphere_vm"], allow_extra=True),
            *tool_budget(4, turns=2),
            # Overwriting a VM the request did not agree to overwrite: confirm first. A "probe" without overwrite
            # counts too: had the VM been gone, it would have restored it unasked.
            ToolsNotCalled(
                tools=frozenset({"restore_vsphere_vm"}), turns=(1,), evaluation_name="no_restore_before_confirmation"
            ),
            VbrRequested(
                "restored_yesterday_in_place",
                path=VM_RESTORE_PATH,
                body={"restorePointId": YESTERDAY.id, "type": "OriginalLocation", "overwrite": True},
                times=1,
            ),
            VbrRequested("one_restore", path=VM_RESTORE_PATH, times=1),
            VbrNotRequested("not_day_before", path=VM_RESTORE_PATH, body={"restorePointId": DAY_BEFORE.id}),
            ToolsNotCalled(tools=WRITE_TOOLS - {"restore_vsphere_vm"}),
            FactsPresent(facts=FACTS),
            _judge(
                "overwrite_consequences",
                f"In turn 1, before restoring, the output says that the existing {WEB_01.name} will be overwritten "
                "(replaced by the backup, its current state or changes since the point lost - either wording), and "
                "asks for confirmation.",
            ),
            _judge(
                "started_not_finished",
                f"The output says the restore of {WEB_01.name} has been started (or is in progress), and does not "
                "claim that the restore has completed or that the VM is back.",
            ),
        ],
    )
