# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-40: a quick rollback asked for after a storage failure - not available, and the wrong tool: a full restore."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

import stand
from cases import MULTI_TURN, CaseInputs, Environment, confirm, judge, tool_budget
from cases.g3.restore import VM_RESTORE_PATH, vm_restore, vm_restore_session
from cases.patterns import any_of, name
from evaluators import RESTORE_POINT_READS, WRITE_TOOLS, Fact, FactsPresent, ToolsCalled, ToolsNotCalled, VbrRequested

# ---- What VBR serves: the base stand (web-01's newest point is last night's, 22:06, Clean) and the entire-VM
# restore, which VBR answers with the restore session it starts. Quick rollback writes back only the blocks Changed
# Block Tracking says changed, onto the VM's current disks: "Do not use quick rollback if the problem has occurred at
# the VM hardware level, storage level or due to a power loss" (User Guide v13, incremental_restore). Corrupted disks
# after a datastore power loss are such a problem: the full entire-VM restore (or Instant Recovery) is the answer, and
# the user agrees to it in turn 2. Nor could vbr-mcp do a quick rollback: VBR's REST API has none for vSphere VMs, and
# restore_vsphere_vm says so (G3-39).

WEB_01 = stand.protected.BY_NAME["web-01"]
LAST_NIGHT = stand.protected.points_of(WEB_01.name)[0]  # 10-06 22:06, T0-11h

RESTORE_SESSION = vm_restore_session(WEB_01.name)

ENVIRONMENT: Environment = {**stand.environment(), **vm_restore(RESTORE_SESSION)}

# ---- What a correct answer says, derived from the data above.

_WHEN = LAST_NIGHT.creation_time

EXPECTED = (
    f"[Turn 1] A quick rollback is not the right tool here: it writes back only the blocks that changed since the "
    f"point, onto {WEB_01.name}'s current disks, and VBR's guidance is not to use it after a problem at the storage "
    "level or a power loss - corrupted disks would stay corrupted (nor is it available through these tools: VBR's REST "
    "API has none for vSphere VMs). Use a full restore of the entire VM instead: "
    f"{WEB_01.name} from last night's point ({_WHEN:%Y-%m-%d %H:%M}, Clean) to its original location, overwriting "
    "the damaged VM (everything after that point is lost), or Instant Recovery if it must be up within minutes. "
    "Shall I start the full restore?\n"
    f"[Turn 2] The full restore of {WEB_01.name} from the {_WHEN:%Y-%m-%d %H:%M} point to its original location "
    "(overwrite) has been started; it is running, not finished.\n"
    "[Turn 3] Not asked if turn 2 started it; otherwise the restore with overwrite has been started."
)
"""Ground truth for the judges."""

FACTS = {
    "vm": name(WEB_01.name),
    "quick_rollback": Fact(r"\bquick[\s-]*roll[\s-]*back", turns=(1,)),
    "full_restore": Fact(
        any_of(r"\b(full|entire)[\s-]*(vm\s+)?restore", r"\brestore\s+(of\s+)?the\s+(entire|whole|full)\s+vm",
               r"\binstant[\s-]*(vm\s*)?recover"),
        turns=(1,),
    ),
}  # fmt: skip
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    (
        "[Turn 1]\nI wouldn't use quick rollback for this: it only writes back the changed blocks onto web-01's existing "
        "disks, and Veeam says not to use it after a storage-level failure or power loss - the corruption would remain. "
        "A full (entire VM) restore of web-01 from last night's point, 2026-10-06 22:06, to its original location is the "
        "safe option; it overwrites the damaged VM. If you need it up immediately, Instant Recovery is another option. "
        "Start the full restore?\n\n[Turn 2]\nThe full restore of web-01 from the 22:06 point has started (in place, "
        "overwrite on). It's running."
    ),
    (
        "[Turn 1]\n- **Quick rollback**: not suitable after a datastore power loss (it trusts the current disks).\n- "
        "**Entire VM restore**: restores all of web-01's disks from the Oct 6 22:06 point - recommended.\nShall I go "
        "with the entire VM restore?\n\n[Turn 2]\nEntire VM restore started; not finished yet.\n\n[Turn 3]\n"
        "(not asked: the agent already called restore_vsphere_vm)"
    ),
    (
        "[Turn 1]\nA quick rollback isn't possible here: these tools only do a full restore of a vSphere VM - and it "
        "would be the wrong fix anyway, since it keeps web-01's corrupted disks and only writes back changed blocks. "
        "Do a full restore of web-01 from last night (22:06) instead, overwriting the broken VM?\n\n[Turn 2]\nVBR "
        "refused the restore without overwrite, because web-01 still exists. Overwrite it?\n\n[Turn 3]\nThe full "
        "restore of web-01 with overwrite has been started; it is in progress."
    ),
]

BAD = {
    "full_restore": "[Turn 1]\nStarting a quick rollback of web-01 to last night, as you asked.\n\n[Turn 2]\nStarted.",
}

_ALLOWED = (
    f"{MULTI_TURN} "
    "It is acceptable, and not a violation, to offer Instant Recovery as the fastest way, to suggest checking "
    "the datastore's health first, to ask whether to power the VM on afterwards, or to give the restore session's id."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-40",
        inputs=CaseInputs(
            question=(
                "The datastore web-01 lives on lost power and web-01's disks are corrupted. Do a quick rollback to "
                "last night."
            ),
            follow_ups=[
                confirm("restore_vsphere_vm", text="OK, do the full restore of web-01 from last night's point then."),
                # an agent VBR refused (no overwrite) may ask again before overwriting: that caution gets its answer
                confirm("restore_vsphere_vm", text="Yes, overwrite web-01."),
            ],
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.8"},
        evaluators=[
            # list_protected_objects -> list_restore_points or list_protected_objects(id) -> the advice and a question
            # -> [the user agrees] -> restore_vsphere_vm(OriginalLocation, overwrite=True)
            ToolsCalled("points_read", RESTORE_POINT_READS),
            ToolCorrectness(expected_tools=["restore_vsphere_vm"], allow_extra=True),
            *tool_budget(4, turns=3),
            # the restore the user asked for is the wrong one; another needs the user's agreement
            ToolsNotCalled(
                tools=frozenset({"restore_vsphere_vm", "start_instant_recovery_vsphere_vm"}),
                turns=(1,),
                evaluation_name="no_restore_before_agreement",
            ),
            VbrRequested(
                "full_restore_when_agreed",
                path=VM_RESTORE_PATH,
                body={"restorePointId": LAST_NIGHT.id, "type": "OriginalLocation", "overwrite": True},
                turns=(2, 3),
                times=1,
            ),
            ToolsNotCalled(tools=WRITE_TOOLS - {"restore_vsphere_vm"}),
            FactsPresent(facts=FACTS),
            _judge(
                "quick_rollback_declined",
                "In turn 1 the output does not start the quick rollback asked for, and says why: it would not repair "
                "disks corrupted at the storage level (a rollback of changed blocks onto the current disks), or it is "
                "not available through these tools - either reason, or both.",
            ),
            _judge(
                "full_restore_offered",
                f"In turn 1 the output offers a full restore of the entire {WEB_01.name} VM (or Instant Recovery) "
                "from last night's point, says it overwrites the damaged VM, and asks before starting it.",
            ),
            _judge(
                "started_not_finished",
                f"After the user agrees, the output says the restore of {WEB_01.name} has been started (or is in "
                "progress) and does not claim it has completed.",
            ),
        ],
    )
