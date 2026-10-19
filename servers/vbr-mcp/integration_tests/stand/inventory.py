# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""The vSphere inventory (1.7): the servers VBR knows, what vCenter holds, and its VMs' managed object references.

``/inventory/vmware/hosts`` (``list_vmware_hosts``) lists the vSphere servers added to the backup infrastructure, and
``POST /api/v1/inventory`` (``browse_inventory``) the roots of VBR's inventory - the same vCenter Server here:
VBR lists the servers registered with it, not the hosts a vCenter manages (InventoryHostHandler.GetAllHosts ->
ViRootFoldersBrowser.GetRootServersAndFolders, ``CFolder.GetHosts(folderId, recursive: false)``). What is inside a root
comes from ``POST /api/v1/inventory/{hostname}`` (``browse_inventory`` with ``server_name``): one hierarchy of it, the whole tree
flattened depth-first with the root itself first (InventoryBrowserControllerImpl.GetVmwareObjects ->
CVSphereInventoryBrowser.GetAllChildItems, HostsAndClusters when the request names none; CHierarchyTree.TransformToList).
The stand's vCenter holds the datacenter DC-Lab with Cluster-A of esx01 and esx02, a datastore of esx01's and two of
esx02's, the VM folders Production and Test, three networks, and the VMs of ``VMS`` that are still in vCenter.
"""

from collections.abc import Mapping
from typing import Any, NamedTuple

from vbr_mock.markers import VbrAction, VbrError
from vbr_mock.presenters.expressions import ExpressionError, select
from vbr_models.inventory import InventoryBrowserResult, PaginationResult, VmwareObject

VCENTER_NAME = "vcenter01.lab.local"

VCENTER = VmwareObject(
    host_name=VCENTER_NAME, name=VCENTER_NAME, type="vCenterServer", object_id="5c2e8a41-9d7b-4f36-a0e2-7b19c4d6e835"
)  # a vCenter's objectId is a GUID (swagger ServersInventoryBrowserResultExample), not a managed server id
DATACENTER = VmwareObject(host_name=VCENTER_NAME, name="DC-Lab", type="Datacenter", object_id="datacenter-2")
CLUSTER = VmwareObject(host_name=VCENTER_NAME, name="Cluster-A", type="Cluster", object_id="domain-c8")
ESX01 = VmwareObject(host_name=VCENTER_NAME, name="esx01.lab.local", type="Host", object_id="host-101")
ESX02 = VmwareObject(host_name=VCENTER_NAME, name="esx02.lab.local", type="Host", object_id="host-102")

VMWARE_HOSTS: list[VmwareObject] = [VCENTER]
"""``GET /api/v1/inventory/vmware/hosts``: the vSphere server added to the backup infrastructure."""

INVENTORY_HOSTS: list[VmwareObject] = [VCENTER]
"""``POST /api/v1/inventory``: the roots of the inventory, every match on one page."""


def _object(name: str, kind: Any, object_id: str) -> VmwareObject:
    return VmwareObject(host_name=VCENTER_NAME, name=name, type=kind, object_id=object_id)


ESX01_DS1 = _object("esx01-ds1", "Datastore", "datastore-201")
ESX02_DS1 = _object("esx02-ds1", "Datastore", "datastore-202")
ESX02_DS2 = _object("esx02-ds2", "Datastore", "datastore-203")
DATASTORES_OF: dict[str, list[VmwareObject]] = {ESX01.name: [ESX01_DS1], ESX02.name: [ESX02_DS1, ESX02_DS2]}
"""The datastores each ESXi host can use; a VM lives on its host's first."""

PRODUCTION = _object("Production", "Folder", "group-v301")
TEST = _object("Test", "Folder", "group-v310")

NETWORKS: list[VmwareObject] = [
    _object("VM Network", "Network", "network-11"),
    _object("Prod-VLAN10", "DVSNetwork", "dvportgroup-31"),
    _object("Isolated-Test", "DVSNetwork", "dvportgroup-32"),
]


class Vm(NamedTuple):
    """A VM the stand names: its name, managed object reference, the ESXi host it runs on, and whether it is gone."""

    name: str
    ref: str
    host: str
    gone: bool = False


VMS: dict[str, Vm] = {
    vm.name: vm
    for vm in (
        Vm("web-01", "vm-1042", ESX01.name),
        Vm("web-02", "vm-1043", ESX01.name),
        Vm("app-01", "vm-1044", ESX01.name),
        Vm("fs-01", "vm-1045", ESX01.name),
        Vm("sql-prod-01", "vm-1046", ESX02.name),
        Vm("sql-prod-02", "vm-1047", ESX02.name),
        Vm("sql-dev-01", "vm-1048", ESX02.name),
        Vm("legacy-erp-01", "vm-1049", ESX02.name),
        Vm("report-01", "vm-1050", ESX02.name),
        Vm("new-app-01", "vm-1051", ESX02.name),
        Vm("test-vm-01", "vm-1052", ESX01.name),  # in no job
        Vm("jump-01", "vm-1053", ESX01.name),  # in no job
        # gone from vCenter; their backups remain (B10 orphaned, B11 imported)
        Vm("old-fs-01", "vm-1012", ESX01.name, gone=True),
        Vm("old-app-01", "vm-1013", ESX01.name, gone=True),
        Vm("erp-db-2024", "vm-1020", ESX02.name, gone=True),
    )
}
"""Every VM the stand names, by name. ``vm-1043`` is the reference VBR's snapshot error for web-02 quotes."""

_IN_TEST_FOLDER = frozenset({"test-vm-01", "jump-01"})


def _vms(where: Any) -> list[VmwareObject]:
    """The VMs vCenter holds for which ``where(vm)`` holds, as inventory objects."""
    return [_object(vm.name, "VirtualMachine", vm.ref) for vm in VMS.values() if not vm.gone and where(vm)]


def _on_host(host: VmwareObject) -> list[VmwareObject]:
    return _vms(lambda vm: vm.host == host.name)


OBJECTS: dict[str, dict[str, list[VmwareObject]]] = {
    VCENTER_NAME: {
        "HostsAndClusters": [VCENTER, DATACENTER, CLUSTER, ESX01, *_on_host(ESX01), ESX02, *_on_host(ESX02)],
        "HostsAndDatastores": [
            VCENTER, DATACENTER, CLUSTER,
            *(item for host in (ESX01, ESX02) for item in (host, *DATASTORES_OF[host.name])),
        ],
        "DatastoresAndVms": [
            VCENTER, DATACENTER, ESX01_DS1, *_on_host(ESX01), ESX02_DS1, *_on_host(ESX02), ESX02_DS2,
        ],
        "VmsAndTemplates": [
            VCENTER, DATACENTER,
            PRODUCTION, *_vms(lambda vm: vm.name not in _IN_TEST_FOLDER),
            TEST, *_vms(lambda vm: vm.name in _IN_TEST_FOLDER),
        ],
        "Network": [VCENTER, DATACENTER, *NETWORKS],
        "VmsAndTags": [VCENTER],  # no tags in the stand
    },
}  # fmt: skip
"""``POST /api/v1/inventory/{hostname}``: per root server, per vSphere hierarchy (``EHierarchyType``), its objects."""

_VSPHERE_HIERARCHIES = (
    "HostsAndClusters",
    "DatastoresAndVms",
    "HostsAndDatastores",
    "VmsAndTemplates",
    "VmsAndTags",
    "Network",
)
"""``EHierarchyType``: the hierarchies VBR browses a vSphere server by (swagger ``InventoryBrowserFilters``)."""

DEFAULT_HIERARCHY = "HostsAndClusters"


def objects_browser(root: VmwareObject, hierarchies: Mapping[str, list[VmwareObject]]) -> VbrAction:
    """``POST /api/v1/inventory/{name}`` (GetInventoryObjects) for the root server ``root``, as VBR answers it.

    VBR browses the hierarchy the body names (``HostsAndClusters`` when none; any other name answers 400, parsed
    without regard to case), narrows and orders it by ``filter`` and ``sorting`` (its flexible filtration over
    ``VmwareObjectModel``; a property the model does not have fails the request's validation), counts the matches as
    ``total`` and serves the page ``pagination`` asks for, 0 and 200 when it asks for none
    (InventoryBrowserControllerImpl.GetVmwareObjects, CHierarchyTypeValidator, CFilterExpressionsInventoryBrowserValidator).
    ``hierarchyType`` echoes the one asked for. A hierarchy ``hierarchies`` does not hold is the server alone.
    """

    def answer(body: Any) -> InventoryBrowserResult | VbrError:
        body = body if isinstance(body, dict) else {}
        asked = body.get("hierarchyType")
        hierarchy = None
        if isinstance(asked, str) and asked.strip():
            hierarchy = next((name for name in _VSPHERE_HIERARCHIES if name.lower() == asked.strip().lower()), None)
            if hierarchy is None:
                return VbrError(status_code=400, message="Hierarchy type is incorrect.")
        tree = hierarchies.get(hierarchy or DEFAULT_HIERARCHY) or [root]
        try:
            found = select(
                tree,
                lambda item: item.model_dump(mode="json"),
                body.get("filter"),
                body.get("sorting"),
                model="VmwareObjectModel",
                enums=frozenset({"type", "platform"}),
            )
        except ExpressionError as exc:
            return VbrError(status_code=400, message=str(exc))
        pagination = body.get("pagination")
        if not isinstance(pagination, dict):
            pagination = {"skip": 0, "limit": 200}  # VBR's PaginationFilter(0, 200) for a body without one
        skip, limit = pagination.get("skip"), pagination.get("limit")
        start = skip if isinstance(skip, int) else 0
        page = found[start : start + limit] if isinstance(limit, int) else found[start:]
        return InventoryBrowserResult(
            data=page,
            pagination=PaginationResult(total=len(found), count=len(page), skip=skip, limit=limit),
            hierarchy_type=hierarchy,
        )

    return VbrAction(response_of=answer)


def not_found(host_name: str) -> VbrError:
    """VBR's answer to browsing a name that is no root of its inventory (RestValidationResources.CantFindHostByName)."""
    return VbrError(status_code=404, message=f"Cannot find host with name: {host_name}.")


def hosts_browser(hosts: list[VmwareObject]) -> VbrAction:
    """``POST /api/v1/inventory`` (GetAllInventoryHosts) over ``hosts``, as VBR answers it.

    VBR narrows and orders the hosts by the body's ``filter`` and ``sorting`` (its flexible filtration over
    ``InventoryRootObjectModel``, whose ``type`` and ``platform`` are enums), and does not page what is left: it serves
    every match, and builds ``pagination`` from the hosts before the filter - ``total`` counts those within
    ``skip``/``limit``, ``count`` the matches it serves (InventoryHostHandler.GetAllHosts and BuildPagination). A
    property the model does not have fails the request, wrapped as the controller wraps any error of the browser.
    """

    def answer(body: Any) -> InventoryBrowserResult | VbrError:
        body = body if isinstance(body, dict) else {}
        try:
            found = select(
                hosts,
                lambda host: host.model_dump(mode="json"),
                body.get("filter"),
                body.get("sorting"),
                model="InventoryRootObjectModel",
                enums=frozenset({"type", "platform"}),
            )
        except ExpressionError as exc:
            return VbrError(status_code=500, message=f"Cannot obtain hierarchy roots. Reason: [{exc}].")
        pagination = body.get("pagination")
        if not isinstance(pagination, dict):
            pagination = {"skip": 0, "limit": 200}  # VBR's PaginationFilter(0, 200) for a body without one
        skip, limit = pagination.get("skip"), pagination.get("limit")
        start = skip if isinstance(skip, int) else 0
        within = hosts[start : start + limit] if isinstance(limit, int) else hosts[start:]
        return InventoryBrowserResult(
            data=found, pagination=PaginationResult(total=len(within), count=len(found), skip=skip, limit=limit)
        )

    return VbrAction(response_of=answer)
