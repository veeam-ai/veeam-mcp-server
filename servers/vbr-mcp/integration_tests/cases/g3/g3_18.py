# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-18: migrate the Instant Recovery of web-02 to production on esx02, after confirming."""

from functools import partial
from typing import Any

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

import stand
from cases import MULTI_TURN, CaseInputs, Environment, confirm, judge, tool_budget
from cases.g3.instant_recovery import IR_SESSION, MOUNT_ID, MOUNTED, WEB_02
from cases.patterns import name
from evaluators import WRITE_TOOLS, FactsPresent, ToolsNotCalled, VbrRequested
from stand import IR_MOUNTS
from stand.ids import J01, S_ID22
from stand.inventory import ESX02, OBJECTS, VCENTER_NAME
from stand.sessions import started
from vbr_mock.markers import VbrAction, VbrError

# ---- What VBR serves: the base stand in the state G3-17 leaves - web-02, deleted from vCenter, runs from last
# night's point as the Instant Recovery mount of session S-ID21 (the mount's id), Mounted on esx01 since 08:10 - and
# the migration, answered with the QuickMigration session S-ID22 (200, as VBR answers it). esx02 is a host vcenter01
# manages, so only the vCenter's own inventory (POST /inventory/vcenter01.lab.local, browse_inventory with
# server_name) has its object: VBR's list of servers (browse_inventory without one) holds vcenter01 alone. VBR refuses a destination host that is not a full inventory object it
# can resolve; its wording is not known, so the mock's is neutral.

MIGRATE_PATH = f"{IR_MOUNTS}/{MOUNT_ID}/migrate"
MIGRATION_SESSION = started(22, WEB_02.name, session_type="QuickMigration", job_id=J01, platform="VMware").model_copy(
    update={"resource_id": MOUNT_ID}
)

_HOST_FIELDS = ("type", "objectId", "name", "hostName")
_HOSTS = {item.object_id for item in OBJECTS[VCENTER_NAME]["HostsAndClusters"] if item.type == "Host"}


def _reject_migration(body: Any) -> VbrError | None:
    """VBR's answer to a destination host that is not an inventory object it can resolve."""
    host = (body or {}).get("destinationHost")
    if not isinstance(host, dict) or any(not host.get(field) for field in _HOST_FIELDS):
        return VbrError(status_code=400, message="Invalid destinationHost.")
    if host["objectId"] not in _HOSTS:
        return VbrError(status_code=404, message="The destination host was not found.")
    return None


ENVIRONMENT: Environment = {
    **stand.environment(instant_recovery_mounts=[MOUNTED], sessions=[IR_SESSION, *stand.sessions.SESSIONS]),
    MIGRATE_PATH: VbrAction(
        response=MIGRATION_SESSION,
        status_code=200,
        reject=_reject_migration,
        effects={
            f"/api/v1/sessions/{S_ID22}": MIGRATION_SESSION,
            "/api/v1/sessions": [MIGRATION_SESSION, IR_SESSION, *stand.sessions.SESSIONS],
        },
    ),
}

# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    f"[Turn 1] {WEB_02.name} runs from the backup as Instant Recovery mount {MOUNT_ID} ({MOUNTED.state}, on "
    f"{MOUNTED.host_name}). Migrating it to {ESX02.name} ({ESX02.object_id}) makes the recovery permanent: VBR moves "
    "the VM and the changes made since the recovery to production storage. Downtime depends on the method: Veeam "
    "Quick Migration switches the VM over with a short stop, vMotion keeps it running. Shall I start it?\n"
    f"[Turn 2] The migration of {WEB_02.name} to {ESX02.name} has been started (session {S_ID22}); it is not "
    "finished yet, and its progress can be followed in the session."
)
"""Ground truth for the judges."""

FACTS = {
    "vm": name(WEB_02.name),
    "host": r"esx02",
    "migrat": r"\bmigrat",
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    (
        "[Turn 1]\nweb-02 is running from its backup as Instant Recovery mount (Mounted on esx01.lab.local). Migrating "
        "it to esx02.lab.local (host-102) makes it permanent: VBR moves the VM, with the changes made since the recovery, "
        "to production storage. With Veeam Quick Migration there is a short switchover; vMotion keeps it running. "
        "Go ahead?\n\n[Turn 2]\nThe migration of web-02 to esx02 has started - it's in progress, not done yet."
    ),
    (
        "[Turn 1]\nReady to migrate web-02 (IR mount, Mounted) to production on host esx02. This finalizes the "
        "recovery; expect a brief downtime. Confirm?\n\n[Turn 2]\nMigration started; I'll report when it completes."
    ),
]

BAD = {
    "host": "[Turn 1]\nweb-02 is Mounted. Migrate it to production?\n\n[Turn 2]\nThe migration has started.",
}

_ALLOWED = (
    f"{MULTI_TURN} "
    "It is acceptable, and not a violation, to ask which datastore or resource pool to use, to ask whether to "
    "use Quick Migration or vMotion, to report a refusal from VBR honestly and retry once with corrected arguments, "
    "or to give the session id, which the migration returns."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-18",
        inputs=CaseInputs(
            question="web-02 looks fine. Migrate it to production on esx02.",
            follow_ups=[confirm("migrate_instant_recovery_vsphere_vm", text="Yes, migrate web-02 to esx02.")],
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.7, 1.8 + G3-17"},
        evaluators=[
            # get_instant_recovery_mount_status(vm_name_filter="web-02") -> (browse_inventory or list_vmware_hosts
            # for the vCenter's name) -> browse_inventory(server_name=vcenter01) (only it lists the ESXi hosts a
            # vCenter manages) -> [confirmation] -> migrate_instant_recovery_vsphere_vm(mount_id=S-ID21, host-102).
            ToolCorrectness(
                expected_tools=[
                    "get_instant_recovery_mount_status",
                    "browse_inventory",
                    "migrate_instant_recovery_vsphere_vm",
                ],
                allow_extra=True,
            ),
            *tool_budget(5, turns=2),
            ToolsNotCalled(
                tools=frozenset({"migrate_instant_recovery_vsphere_vm"}),
                turns=(1,),
                evaluation_name="no_migration_before_confirmation",
            ),
            VbrRequested(
                "migrated_to_esx02",
                path=MIGRATE_PATH,
                body={"destinationHost": {"type": "Host", "objectId": ESX02.object_id, "name": ESX02.name}},
                times=1,
            ),
            ToolsNotCalled(tools=WRITE_TOOLS - {"migrate_instant_recovery_vsphere_vm"}),
            FactsPresent(facts=FACTS),
            _judge(
                "consequences_before_confirmation",
                "In turn 1, before anything is migrated, the output explains that the migration makes the recovery "
                "permanent by moving or copying the VM to production storage, and asks for confirmation; mentioning "
                "downtime or the migration method is welcome.",
            ),
            _judge(
                "started_not_finished",
                "The output says the migration has been started or is in progress, and does not claim that it has "
                "completed.",
            ),
            _judge(
                "no_invented_host",
                f"The output does not present an id or object for esx02 other than the inventory's "
                f"{ESX02.object_id} / {ESX02.name}.",
            ),
        ],
    )
