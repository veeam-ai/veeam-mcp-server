# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

from typing import Any, Literal
from urllib.parse import quote
from uuid import UUID

from vbr_mcp.pagination import fetch_all
from vbr_mcp.server import mcp, vbr_client
from vbr_mcp.tool_annotations import READ_ONLY


@mcp.tool(annotations=READ_ONLY)
async def list_unstructured_data_servers(
    id: UUID | None = None,
    name_filter: str | None = None,
    max_items: int | None = None,
) -> list[dict[str, Any]] | dict[str, Any]:
    """List registered NAS/unstructured-data sources, or - with `id` - one server's full record.

    Sources include file shares, NAS filers, and object storage. Fields other than `id`/`type`/`name` are type-conditional - read them
    null-safely, branching on `type`. There is no health/online state for these
    (config-derived only): VBR requires a cache repository and backup proxies for
    every source, so a blocker shows only when joined with their state - proxies
    picked by hand (`processing.backupProxies.autoSelectEnabled` is `False`)
    none of which can take tasks (disabled, offline or out of date in
    `list_proxies`), or a cache repository (`processing.cacheRepositoryId`) that
    is offline or out of space in `list_repositories`.
    """
    if id is not None:
        return await vbr_client.get(f"/api/v1/inventory/unstructuredDataServers/{id}")
    return await fetch_all(
        vbr_client, "/api/v1/inventory/unstructuredDataServers", nameFilter=name_filter, max_items=max_items
    )


@mcp.tool(annotations=READ_ONLY)
async def list_vmware_hosts(name_filter: str | None = None, max_items: int | None = None) -> list[dict[str, Any]]:
    """List the vSphere servers VBR manages: vCenter Servers and standalone ESXi hosts.

    A standalone ESXi host's row is also the destination-host row restore tools take as-is; hosts under a vCenter
    are not listed here - browse them with `browse_inventory(server_name=<vCenter>, hierarchy_type="HostsAndClusters",
    object_type="Host")`.
    """
    return await fetch_all(vbr_client, "/api/v1/inventory/vmware/hosts", nameFilter=name_filter, max_items=max_items)


@mcp.tool(annotations=READ_ONLY)
async def browse_inventory(
    server_name: str | None = None,
    hierarchy_type: Literal[
        "HostsAndClusters",
        "DatastoresAndVms",
        "HostsAndDatastores",
        "VmsAndTemplates",
        "VmsAndTags",
        "Network",
        "VmwareDatastores",
        "HostsAndDisks",
        "VAppsAndVms",
        "StoragePolicies",
        "Datastores",
        "HostsAndVms",
        "HostsAndVolumes",
        "Groups",
        "Tags",
    ]
    | None = None,
    name_filter: str | None = None,
    object_type: str | None = None,
    filter: dict[str, Any] | None = None,
    sorting: dict[str, Any] | None = None,
    permission_scope: Literal["Backup", "Restore", "Any"] | None = None,
    skip: int = 0,
    limit: int = 200,
) -> dict[str, Any]:
    """Browse the virtualization inventory VBR sees - the source of every restore placement (host, resource pool, datastore, folder, network).

    Without `server_name`: lists the managed servers (vCenters, standalone ESXi
    hosts, Hyper-V, ...). With `server_name` (a managed server's `name`, or a
    placement object's `hostName`; any other name, such as an ESXi host a
    vCenter manages, is not found - browse its vCenter instead): lists the
    objects under that server - one hierarchy, the whole tree flattened, each
    object before the objects under it, starting with the server itself - in the
    `hierarchy_type` view, which depends on the platform - VMware vSphere:
    `HostsAndClusters` (hosts, clusters, resource pools, VMs),
    `HostsAndDatastores` (datastores, plus the `Datacenter` row a standalone
    ESXi host places VMs into), `VmsAndTemplates` (VM folders), `Network`
    (port groups; dvSwitch ones are `DVSNetwork`), `DatastoresAndVms`,
    `VmsAndTags`, `VmwareDatastores`, `HostsAndDisks`; Cloud Director:
    `VAppsAndVms`, `Network`, `StoragePolicies`, `Datastores`; Hyper-V:
    `HostsAndVms`, `HostsAndVolumes`, `Groups`, `Tags`, `Network`.

    `name_filter` (substring) and `object_type` (e.g. `Host`, `ResourcePool`,
    `Datastore`, `Folder`, `Network`) are shortcuts; `filter` takes a raw VBR
    filter expression (`PredicateExpression` on `platform`/`size`/`hostName`/
    `name`/`type`/`objectId`/`urn`, or a `GroupExpression` of them with
    `And`/`Or`/`Not`) and is ANDed with them. `sorting` is `{"property": ...,
    "direction": "Ascending"|"Descending"}`. Each row carries `objectId`,
    `name`, `type` and `hostName` (the managed server that owns it); restore
    tools take a row as-is. A standalone ESXi host is listed twice: use the row
    whose `objectId` is its name (as in `HostsAndClusters`), not `ha-host`.
    The response is one page - page with `skip`/`limit` up to
    `pagination.total`. Without `server_name`, though, `pagination.total`
    counts every managed server, not the filter's matches: count the rows.
    This is a discovery read, not the protected-object
    inventory: use `list_protected_objects` for what is actually backed up.
    """
    predicates: list[dict[str, Any]] = []
    if name_filter is not None:
        predicates.append(_predicate("name", "Contains", name_filter))
    if object_type is not None:
        predicates.append(_predicate("type", "Equals", object_type))
    if filter is not None:
        predicates.append(filter)

    body: dict[str, Any] = {"pagination": {"skip": skip, "limit": limit}}
    if hierarchy_type is not None:
        body["hierarchyType"] = hierarchy_type
    if len(predicates) == 1:
        body["filter"] = predicates[0]
    elif predicates:
        body["filter"] = {"type": "GroupExpression", "operation": "And", "items": predicates}
    if sorting is not None:
        body["sorting"] = sorting
    if permission_scope is not None:
        body["permissionScope"] = permission_scope

    path = "/api/v1/inventory" if server_name is None else f"/api/v1/inventory/{quote(server_name, safe='')}"
    return await vbr_client.post(path, json=body, read_only=True)


def _predicate(property_name: str, operation: str, value: str) -> dict[str, Any]:
    return {"type": "PredicateExpression", "property": property_name, "operation": operation, "value": value}
