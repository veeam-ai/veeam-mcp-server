# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""Checks on the vSphere inventory objects a restore request places a VM with.

The request models only check shape: any of the 21 vSphere object types fits any
`VmwareObjectModel` slot. These checks reject what VBR would refuse - or worse,
silently ignore - before the request is sent, with a message saying which inventory
row to pass instead. They were derived by running the requests against VBR 13.1
(REST API 1.3-rev2).
"""

from __future__ import annotations

from collections.abc import Mapping

from fastmcp.exceptions import ToolError

from vbr_mcp.models.shared import VmwareObjectModel

HOSTS = frozenset({"Host", "Cluster"})
RESOURCE_POOLS = frozenset({"ResourcePool"})
DATASTORES = frozenset({"Datastore"})
NETWORKS = frozenset({"Network", "DVSNetwork"})
VM_FOLDERS = frozenset({"Folder"})
# A full VM restore can also place the VM at a datacenter's root - the only placement
# root a standalone ESXi host has (its `HostsAndDatastores` browse lists it).
PLACEMENT_ROOTS = frozenset({"Folder", "Datacenter"})

_BROWSE_HINT = "Pass a row from `browse_inventory(server_name=<the destination host's hostName>, ...)` as-is."


def check_placement(
    host_field: str,
    host: VmwareObjectModel,
    placements: Mapping[str, tuple[VmwareObjectModel | None, frozenset[str]]],
) -> None:
    """Validate a destination host and the placement objects that must live on the same managed server.

    `placements` maps each argument path (as the caller wrote it) to its object and the types allowed there.
    """
    _check_type(host_field, host, HOSTS)
    _check_standalone_host_row(host_field, host)
    for field, (obj, allowed) in placements.items():
        if obj is None:
            continue
        _check_type(field, obj, allowed)
        if obj.hostName != host.hostName:
            raise ToolError(
                f"`{field}` ({obj.name!r}) belongs to managed server {obj.hostName!r}, but `{host_field}` to "
                f"{host.hostName!r}: every placement object must come from the destination server's inventory. "
                + _BROWSE_HINT
            )


def check_type(field: str, obj: VmwareObjectModel | None, allowed: frozenset[str]) -> None:
    """Validate an inventory object that is not tied to the destination server (e.g. a source network)."""
    if obj is not None:
        _check_type(field, obj, allowed)


def _check_type(field: str, obj: VmwareObjectModel, allowed: frozenset[str]) -> None:
    if obj.type not in allowed:
        expected = " or ".join(sorted(allowed))
        raise ToolError(f"`{field}` must be a {expected} inventory object, got {obj.type} {obj.name!r}. {_BROWSE_HINT}")


def _check_standalone_host_row(field: str, host: VmwareObjectModel) -> None:
    """Reject the second row a standalone ESXi host appears as.

    A standalone ESXi host is its own managed server (`hostName == name`) and shows up twice in the inventory: as
    the server itself (`objectId` = its name, the `list_vmware_hosts` / `HostsAndClusters` row) and again under
    `ha-datacenter` (`objectId: "ha-host"`, in the `HostsAndDatastores` browse). VBR resolves only the first; the
    second fails with "Host ... cannot be found in the configuration database". vCenter-managed hosts are unaffected:
    their `hostName` is the vCenter.
    """
    if host.type == "Host" and host.hostName == host.name and host.objectId not in (None, host.name):
        raise ToolError(
            f"`{field}` is the {host.name!r} row with objectId {host.objectId!r}, which VBR cannot resolve. For a "
            f"standalone ESXi host pass the row whose objectId is {host.name!r}: from `list_vmware_hosts`, or "
            "`browse_inventory(hierarchy_type='HostsAndClusters')`."
        )
