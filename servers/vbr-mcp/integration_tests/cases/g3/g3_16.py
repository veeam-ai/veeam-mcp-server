# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-16: restore a copy of app-01 to another host, asking which of the host's datastores and folders to use."""

from dataclasses import dataclass
from functools import partial
from typing import Any

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext, ToolCorrectness

import stand
from cases import CaseInputs, Environment, judge, tool_budget
from cases.g3.restore import VM_RESTORE_PATH, vm_restore, vm_restore_session
from evaluators import (
    RESTORE_POINT_READS,
    WRITE_TOOLS,
    FactsPresent,
    ToolsCalled,
    ToolsNotCalled,
    VbrNotRequested,
    VbrRequested,
    requests,
)
from stand.inventory import DATASTORES_OF, ESX02, NETWORKS, OBJECTS, TEST, VCENTER_NAME

# ---- What VBR serves: the base stand - VBR's servers (browse_inventory) are vcenter01 alone, and vcenter01's own
# inventory (POST /inventory/vcenter01.lab.local, browse_inventory with server_name) holds esx02, the datastores it
# can use (esx02-ds1, esx02-ds2), the VM folders Production and Test and the networks; app-01 was backed up on
# Prod-VLAN10 (POST /restorePoints/{id}/networkInfo) - and the entire-VM restore, which VBR answers with the restore
# session it starts. app-01 still exists, so VBR refuses a restore to its original place without overwrite. A
# customized restore's placement is not required by VBR's spec (swagger EntireViVMCustomizedRestoreSpec), so the mock
# accepts one without it as VBR would; vbr-mcp itself asks for a host, a default datastore and, for a VM with networks,
# a network mapping (without one VBR silently keeps the source network settings). Whether the agent asked which
# datastore and folder to use is what the case checks, not a refusal that tells it.

APP_01 = stand.protected.BY_NAME["app-01"]
LATEST = stand.protected.points_of(APP_01.name)[0]  # 10-06 22:19, T0-11h
COPY_NAME = "app-01-test"
CHOICES = DATASTORES_OF[ESX02.name]  # esx02-ds1, esx02-ds2: the user picks one in turn 2
DATASTORE = CHOICES[0]
FOLDER = TEST
ISOLATED = next(network for network in NETWORKS if network.name == "Isolated-Test")  # the user's choice in turn 2
_PLACEMENT_KINDS = frozenset({
    "Datacenter",
    "Cluster",
    "Host",
    "ResourcePool",
    "Datastore",
    "Folder",
    "Network",
    "DVSNetwork",
})
PLACEMENT_IDS = sorted({
    str(item.object_id) for items in OBJECTS[VCENTER_NAME].values() for item in items if item.type in _PLACEMENT_KINDS
})
"""Every placement object's id vcenter01's inventory holds: the ids a correct answer can give."""

_SOURCE_NETWORK = stand.protected.NETWORK_INFO[LATEST.id][0]
"""The network app-01 was backed up on, as the restore point names it (``networkInfo``)."""

RESTORE_SESSION = vm_restore_session(COPY_NAME)

ENVIRONMENT: Environment = {**stand.environment(), **vm_restore(RESTORE_SESSION)}


def _on_given_datastore(body: Any) -> bool:
    """The restore puts the VM on the datastore the user gave: as its default datastore, or for every disk."""
    datastore = (body or {}).get("datastore") or {}
    default = (datastore.get("defaultDatastore") or {}).get("objectId")
    mappings = datastore.get("diskMappings") or []
    on_mappings = bool(mappings) and all(
        (m.get("datastore") or {}).get("objectId") == DATASTORE.object_id for m in mappings
    )
    return default == DATASTORE.object_id or on_mappings


def _on_given_network(body: Any) -> bool:
    """The restore connects the copy to the network the user gave, away from the original's."""
    mappings = ((body or {}).get("network") or {}).get("networks") or []
    return bool(mappings) and all(
        (m.get("targetNetwork") or {}).get("objectId") == ISOLATED.object_id for m in mappings
    )


@dataclass
class CopyRestored(Evaluator[Any, str, Any]):
    """Every restore VBR was asked for is the named copy, and the accepted one lands on the given datastore and network.

    A customized restore without a new name keeps the original's; to the original's folder that deletes the original
    (User Guide v13, full_restore_mode_vm), so no request may leave the name out.
    """

    def evaluate(self, ctx: EvaluatorContext[Any, str, Any]) -> dict[str, EvaluationReason]:
        sent = requests(ctx, VM_RESTORE_PATH)
        unnamed = [
            r
            for r in sent
            if not isinstance(r["body"], dict)
            or r["body"].get("type") != "Customized"
            or (r["body"].get("folder") or {}).get("vmName") != COPY_NAME
        ]
        placed = [r for r in sent if r["status_code"] < 400 and _on_given_datastore(r["body"])]
        connected = [r for r in sent if r["status_code"] < 400 and _on_given_network(r["body"])]
        bodies = "; ".join(f"{r['status_code']} {r['body']}" for r in sent) or "no restore sent"
        return {
            "every_restore_is_the_named_copy": EvaluationReason(value=not unnamed, reason=bodies),
            "copy_on_given_datastore": EvaluationReason(value=bool(placed), reason=bodies),
            "copy_on_given_network": EvaluationReason(value=bool(connected), reason=bodies),
        }


# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    f"[Turn 1] A copy next to the original needs a Customized restore (not OriginalLocation, which would overwrite "
    f"{APP_01.name}), from the latest point ({LATEST.creation_time:%Y-%m-%d %H:%M}), with the new name {COPY_NAME}: "
    "without a new name the copy keeps the original's, and in the original's folder that would replace the original. "
    f"{VCENTER_NAME}'s inventory has {ESX02.name} (objectId {ESX02.object_id}), which can use the datastores "
    f"{' and '.join(choice.name for choice in CHOICES)}; the VM folders are Production and {FOLDER.name}. The copy "
    "would come up with the same network identity (IP, hostname) as the original, which was backed up on "
    f"{stand.protected.VM_NETWORK.name}: keep it powered off, or connect it to an isolated network such as "
    f"{ISOLATED.name}. Which datastore and folder should it go to, and which network?\n"
    f"[Turn 2] The restore of {APP_01.name} as {COPY_NAME} to {ESX02.name}, datastore {DATASTORE.name}, folder "
    f"{FOLDER.name}, network {ISOLATED.name}, powered off, has been started; the original is untouched. It is running, "
    "not finished."
)
"""Ground truth for the judges."""

FACTS = {
    "esx02": r"esx02",
    "datastore": r"datastore",
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    (
        "[Turn 1]\nI can restore app-01's latest point (2026-10-06 22:19) as a new VM named app-01-test on "
        "esx02.lab.local (host-102). esx02 can use two datastores, esx02-ds1 and esx02-ds2, and vCenter has the VM "
        "folders Production and Test - which datastore and folder should the copy go to? Note: the copy will have the "
        "same IP and hostname as app-01 - keep it powered off or off the network until you re-IP it.\n\n[Turn 2]\n"
        "Restore started: app-01 -> app-01-test on esx02, datastore esx02-ds1, folder Test, network Isolated-Test, "
        "powered off. The original app-01 isn't touched; the restore is still running."
    ),
    (
        "[Turn 1]\n- Mode: Customized restore (a copy, not in place)\n- Host: esx02 (host-102)\n- Datastore: "
        "esx02-ds1 or esx02-ds2 - which one?\n- Folder: Production or Test?\n- Network: the copy clones app-01's "
        "identity, so I'd keep it powered off.\n\n[Turn 2]\nStarted the restore of app-01-test to esx02-ds1 on esx02, "
        "folder Test. Not finished yet."
    ),
]

BAD = {
    "datastore": "[Turn 1]\nRestoring app-01 as app-01-test on esx02 now.\n\n[Turn 2]\nThe restore was started.",
}

_ALLOWED = (
    "The output holds every turn's answer, each headed [Turn N]. It is acceptable, and not a violation, to propose a "
    "datastore and a folder from the inventory and ask the user to confirm them, to ask for a network mapping too, to "
    "suggest restoring with the network disconnected or mapped to an isolated network, to offer console steps as an "
    "alternative, or to give the restore session's id, which the restore returns."
)

REPLY = (
    f"Use datastore {DATASTORE.name}, the VM folder {FOLDER.name} and the {ISOLATED.name} network. Don't power it on "
    "yet. Go ahead."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-16",
        inputs=CaseInputs(
            question="Restore app-01 as a copy named app-01-test on host esx02 — don't touch the original.",
            # A plain turn, not a FollowUp: whatever the agent did in turn 1, the user answers.
            follow_ups=[REPLY],
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.7, 1.8"},
        evaluators=[
            # list_protected_objects -> list_restore_points or list_protected_objects(id) -> (browse_inventory or
            # list_vmware_hosts for the vCenter's name) -> browse_inventory(server_name=vcenter01): esx02, its
            # datastores, the VM folders, the networks (one call per hierarchy) -> [the user's choice] ->
            # restore_vsphere_vm(mode="Customized")
            ToolsCalled("points_read", RESTORE_POINT_READS),
            ToolCorrectness(expected_tools=["browse_inventory", "restore_vsphere_vm"], allow_extra=True),
            *tool_budget(7, turns=2),
            ToolsNotCalled(
                tools=frozenset({"restore_vsphere_vm"}), turns=(1,), evaluation_name="no_restore_before_placement"
            ),
            VbrNotRequested(
                "original_not_touched",
                path=VM_RESTORE_PATH,
                body={"type": "OriginalLocation"},
            ),
            VbrRequested(
                "copy_restored_to_esx02",
                path=VM_RESTORE_PATH,
                body={
                    "restorePointId": LATEST.id,
                    "type": "Customized",
                    "powerUp": False,
                    "destinationHost": {"objectId": ESX02.object_id},
                    "folder": {"vmName": COPY_NAME, "folder": {"objectId": FOLDER.object_id}},
                },
                times=1,
            ),
            CopyRestored(),
            ToolsNotCalled(tools=WRITE_TOOLS - {"restore_vsphere_vm"}),
            FactsPresent(facts=FACTS),
            _judge(
                "asks_for_placement",
                f"In turn 1, instead of restoring, the output asks the user which datastore and folder the copy goes "
                f"to, naming datastores {ESX02.name} can use ({', '.join(choice.name for choice in CHOICES)}) to "
                "choose from, or proposes a datastore and folder from the inventory and asks to confirm them.",
            ),
            _judge(
                "no_invented_placement",
                f"Every host, datastore, folder or network id the output gives is one of the inventory's: "
                f"{', '.join(PLACEMENT_IDS)}, or the id the restore point gives its network "
                f"({_SOURCE_NETWORK.id} for {_SOURCE_NETWORK.name}). It presents no other such id as read from VBR.",
            ),
            _judge(
                "identity_conflict",
                "The output warns that the copy has the same network identity (IP address, hostname) as the "
                "original, so it must not be brought onto the network as it is.",
            ),
            _judge(
                "started_not_finished",
                f"The output does not claim that {COPY_NAME} has been restored or is ready: the restore has only "
                "been started.",
            ),
        ],
    )
