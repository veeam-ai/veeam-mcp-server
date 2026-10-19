# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G1-19: which vCenter servers or ESXi hosts are connected to VBR."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case

from cases import CaseInputs, Environment, judge, tool_budget
from cases.patterns import name
from evaluators import FactsPresent, ToolsCalled, ToolsNotCalled
from stand import environment, inventory
from vbr_models.inventory import VmwareObject

# ---- What VBR serves: the base stand's vSphere inventory (1.7) - vcenter01 with Cluster-A and two ESXi hosts - and,
# as the case's delta, a standalone ESXi host added to VBR directly rather than through vCenter (a DMZ host):
# /inventory/vmware/hosts lists "all VMware vSphere servers added to the backup infrastructure" (swagger), and
# POST /inventory the roots of VBR's inventory, so both show the vCenter Server and that host, each its own root (a
# standalone ESXi's object is "ha-host"). The hosts vcenter01 manages are inside it (browse_inventory with
# server_name).

STANDALONE = VmwareObject(host_name="esx-dmz01.lab.local", name="esx-dmz01.lab.local", type="Host", object_id="ha-host")

VMWARE_HOSTS = [*inventory.VMWARE_HOSTS, STANDALONE]
INVENTORY_HOSTS = [*inventory.INVENTORY_HOSTS, STANDALONE]

ENVIRONMENT: Environment = environment(vmware_hosts=VMWARE_HOSTS, inventory_hosts=INVENTORY_HOSTS)

# ---- What a correct answer says, derived from the data above.

VCENTER, CLUSTER, ESX01, ESX02 = inventory.VCENTER, inventory.CLUSTER, inventory.ESX01, inventory.ESX02
DATACENTER = inventory.DATACENTER

EXPECTED = (
    f"Two vSphere servers are connected to VBR: the vCenter Server {VCENTER.name} and the standalone ESXi host "
    f"{STANDALONE.name}, added directly. vcenter01 manages the cluster {CLUSTER.name} with the ESXi hosts "
    f"{ESX01.name} and {ESX02.name}, as its inventory shows."
)
"""Ground truth for the judges."""

FACTS = {
    "vcenter": name(VCENTER.name.removesuffix(".lab.local")),
    "standalone_esxi": name(STANDALONE.name.removesuffix(".lab.local")),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

_ALLOWED = (
    f"It is acceptable, and not a violation, to also list the ESXi hosts {ESX01.name} and {ESX02.name} in "
    f"{CLUSTER.name} (datacenter {DATACENTER.name}), as vcenter01's inventory reports them, or to add what else that "
    "inventory holds (datastores, VMs)."
)

GOOD = [
    (
        "Two vSphere servers are added to VBR:\n- vcenter01.lab.local (vCenter Server) - it manages Cluster-A with "
        "esx01.lab.local and esx02.lab.local\n- esx-dmz01.lab.local - a standalone ESXi host added directly, not through "
        "vCenter."
    ),
    (
        "| Server | Type |\n|---|---|\n| vcenter01.lab.local | vCenter Server |\n| esx-dmz01.lab.local | ESXi host "
        "(standalone) |"
    ),
    "VBR is connected to the vCenter vcenter01 and to one standalone ESXi host, esx-dmz01.",
]
"""Answers a correct agent could give: every fact must match each of them."""

BAD = {
    "vcenter": "Two ESXi hosts are connected, esx01.lab.local and esx02.lab.local, plus esx-dmz01.lab.local.",
    "standalone_esxi": "One vCenter Server is connected: vcenter01.lab.local, with Cluster-A (esx01.lab.local and "
    "esx02.lab.local).",
}
"""Per fact, an answer that gets that fact wrong: the fact must not match it."""


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G1-19",
        inputs=CaseInputs(
            question="Which vCenter servers or ESXi hosts are connected to our VBR server?",
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G1", "base_stand": "1.7 + delta"},
        evaluators=[
            # list_vmware_hosts or browse_inventory (the servers added to VBR): either answers it; a browse of
            # vcenter01 (browse_inventory with server_name) for the hosts it manages is a read the case allows on top.
            ToolsCalled("hosts_read", frozenset({"list_vmware_hosts", "browse_inventory"})),
            *tool_budget(3),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "no_invented_hosts",
                f"The output names no vCenter, ESXi host, datacenter or cluster other than {VCENTER.name}, "
                f"{STANDALONE.name}, {DATACENTER.name}, {CLUSTER.name}, {ESX01.name} and {ESX02.name}.",
            ),
            _judge(
                "standalone_not_in_vcenter",
                f"The output does not place {STANDALONE.name} under {VCENTER.name} or in {CLUSTER.name}: it is a "
                "standalone host added to VBR directly.",
            ),
        ],
    )
