# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

from collections.abc import Mapping
from typing import Any, Literal
from urllib.parse import quote
from uuid import UUID

from fastmcp.exceptions import ToolError
from pydantic import BaseModel

from vbr_mcp.models.file_share_restore import (
    UnstructuredDataShareRestoreDestinationModel,
    UnstructuredDataShareRestoreOptionsModel,
)
from vbr_mcp.models.instant_recovery import (
    InstantViVMCustomizedRecoveryDatastoreSpec,
    InstantViVMCustomizedRecoveryDestinationSpec,
    InstantViVMOtherPlatformRecoveryDestinationSpec,
)
from vbr_mcp.models.instant_recovery_migration import ViVMQuickMigrationDatastoresSpec
from vbr_mcp.models.object_storage_restore import (
    UnstructuredDataOSRestoreDestinationModel,
    UnstructuredDataOSRestoreOptionsModel,
)
from vbr_mcp.models.shared import VmwareObjectModel
from vbr_mcp.models.vm_restore import (
    RestoreProxySpec,
    RestoreTargetDatastoresSpec,
    RestoreTargetFolderSpec,
    RestoreTargetNetworkSpec,
)
from vbr_mcp.pagination import fetch_all
from vbr_mcp.server import mcp, vbr_client
from vbr_mcp.tool_annotations import DESTRUCTIVE, READ_ONLY
from vbr_mcp.vsphere_placement import (
    DATASTORES,
    NETWORKS,
    PLACEMENT_ROOTS,
    RESOURCE_POOLS,
    VM_FOLDERS,
    check_placement,
    check_type,
)

_MOUNT_PATH = "/api/v1/restore/instantRecovery/vSphere/vm"
# VBR answers restore/migration starts only after preparing them - a migration start took 73 s against VBR 13.1 - so
# these POSTs get more time than the client default rather than failing while VBR goes on to start the action.
_ACTION_TIMEOUT_SEC = 600.0


def _put(body: dict[str, Any], **fields: object) -> None:
    """Add each non-None field to `body` under its VBR name, serializing models to JSON-ready dicts."""
    for name, value in fields.items():
        if isinstance(value, BaseModel):
            body[name] = value.model_dump(mode="json", exclude_none=True)
        elif value is not None:
            body[name] = value


def _check_mode(mode: str, *, required: Mapping[str, object], not_allowed: Mapping[str, object]) -> None:
    """Reject a call whose mode-specific arguments do not match `mode`, before anything is sent to VBR."""
    if missing := [name for name, value in required.items() if value is None]:
        raise ToolError(f'mode="{mode}" requires: {", ".join(missing)}.')
    if extra := [name for name, value in not_allowed.items() if value is not None]:
        raise ToolError(f'mode="{mode}" does not accept: {", ".join(extra)}.')


@mcp.tool(annotations=DESTRUCTIVE)
async def start_instant_recovery_vsphere_vm(
    restore_point_id: UUID,
    mode: Literal["OriginalLocation", "Customized", "OtherPlatform"] = "OriginalLocation",
    power_up: bool = True,
    nics_enabled: bool = True,
    overwrite: bool = False,
    reason: str | None = None,
    antivirus_scan_enabled: bool = False,
    yara_scan_enabled: bool = False,
    vm_tags_restore_enabled: bool | None = None,
    destination: InstantViVMCustomizedRecoveryDestinationSpec | None = None,
    other_platform_destination: InstantViVMOtherPlatformRecoveryDestinationSpec | None = None,
    datastore: InstantViVMCustomizedRecoveryDatastoreSpec | None = None,
) -> dict[str, Any] | None:
    """Start a vSphere Instant Recovery: publish a restore point as a running VM without a full data copy.

    `mode="OriginalLocation"` restores to the VM's original host/datastore -
    the common case, no placement arguments. `mode="Customized"` requires
    `destination.destinationHost`; `destination` can also set `resourcePool`,
    `folder` (a VM `Folder` row - VBR silently ignores a `Datacenter` row here)
    and `restoredVmName`. `mode="OtherPlatform"` (a backup of a non-vSphere
    workload, e.g. a Hyper-V VM or a Veeam Agent backup) takes the same
    placement in `other_platform_destination` instead, plus `networkMapping`:
    each `sourceNetwork` is a row of the restore point's
    `api_post_query('/api/v1/restorePoints/{id}/networkInfo')` as-is, each
    `targetNetwork` an inventory `Network` row. `datastore` defaults to keeping
    redo logs in vPower NFS (`{"redirectEnabled": false}`); to redirect them pass
    `{"redirectEnabled": true, "cacheDatastore": <Datastore row>}`. Every vSphere
    object is an inventory row passed as-is, all from the same managed server:
    the host is a `Host` row from `browse_inventory(server_name=<vCenter>,
    hierarchy_type="HostsAndClusters")` (a standalone ESXi host: its
    `list_vmware_hosts` row), the rest come from `browse_inventory` on the
    host's `hostName` server.
    `overwrite=True` replaces an existing VM of the same name at the target - a
    destructive, hard-to-reverse choice; only pass it when the caller explicitly
    wants that. A VM published next to a still-running original keeps its
    MAC/IP: pass `nics_enabled=False` or `power_up=False` to avoid a clash.
    Returns the VBR session of the start; its `id` is also the mount id - poll
    `get_instant_recovery_mount_status(mount_id=<that id>)` until `Mounted`.
    """
    target: InstantViVMCustomizedRecoveryDestinationSpec | InstantViVMOtherPlatformRecoveryDestinationSpec | None
    if mode == "OriginalLocation":
        _check_mode(
            mode,
            required={},
            not_allowed={
                "destination": destination,
                "other_platform_destination": other_platform_destination,
                "datastore": datastore,
            },
        )
        target, field = None, ""
    elif mode == "Customized":
        _check_mode(
            mode,
            required={"destination.destinationHost": destination.destinationHost if destination else None},
            not_allowed={"other_platform_destination": other_platform_destination},
        )
        target, field = destination, "destination"
    else:
        _check_mode(
            mode,
            required={"other_platform_destination": other_platform_destination},
            not_allowed={"destination": destination, "vm_tags_restore_enabled": vm_tags_restore_enabled},
        )
        target, field = other_platform_destination, "other_platform_destination"
    if target is not None:
        host = target.destinationHost
        assert host is not None  # narrowed by the mode check above
        if target.folder is not None and target.folder.type == "Datacenter":
            raise ToolError(
                f"`{field}.folder` is a Datacenter row, which VBR silently ignores for Instant Recovery. "
                "Pass a VM Folder row (`browse_inventory(..., hierarchy_type='VmsAndTemplates', "
                "object_type='Folder')`), or leave `folder` out - a standalone ESXi host has no VM folders."
            )
        if datastore is None:
            datastore = InstantViVMCustomizedRecoveryDatastoreSpec(redirectEnabled=False)
        if (datastore.cacheDatastore is not None) != bool(datastore.redirectEnabled):
            raise ToolError(
                "`datastore.redirectEnabled` and `datastore.cacheDatastore` go together: pass "
                '`{"redirectEnabled": true, "cacheDatastore": <Datastore row>}` to redirect redo logs, or '
                '`{"redirectEnabled": false}` to keep them in vPower NFS.'
            )
        appliance = target.helperAppliance
        mappings = (
            target.networkMapping if isinstance(target, InstantViVMOtherPlatformRecoveryDestinationSpec) else None
        )
        check_placement(
            f"{field}.destinationHost",
            host,
            {
                f"{field}.resourcePool": (target.resourcePool, RESOURCE_POOLS),
                f"{field}.folder": (target.folder, VM_FOLDERS),
                f"{field}.helperAppliance.productionNetwork": (
                    appliance.productionNetwork if appliance is not None else None,
                    NETWORKS,
                ),
                **{
                    f"{field}.networkMapping[{i}].targetNetwork": (mapping.targetNetwork, NETWORKS)
                    for i, mapping in enumerate(mappings or [])
                },
                "datastore.cacheDatastore": (datastore.cacheDatastore, DATASTORES),
            },
        )
    body: dict[str, Any] = {
        "restorePointId": restore_point_id,
        "type": mode,
        "secureRestore": {"antivirusScanEnabled": antivirus_scan_enabled, "yaraScanEnabled": yara_scan_enabled},
        "powerUp": power_up,
        "nicsEnabled": nics_enabled,
        "overwrite": overwrite,
    }
    _put(
        body,
        reason=reason,
        vmTagsRestoreEnabled=vm_tags_restore_enabled,
        destination=target,
        datastore=datastore,
    )
    return await vbr_client.post(_MOUNT_PATH, json=body, timeout=_ACTION_TIMEOUT_SEC)


@mcp.tool(annotations=READ_ONLY)
async def get_instant_recovery_mount_status(
    mount_id: UUID | None = None,
    vm_name_filter: str | None = None,
    state_filter: Literal["Mounting", "Mounted", "Dismounting", "Failed"] | None = None,
) -> dict[str, Any] | list[dict[str, Any]]:
    """Check the status of a vSphere Instant Recovery mount, or list active mounts to find one's id.

    Use `vm_name_filter`/`state_filter` to narrow the list (`vmName` is the
    published VM's name, i.e. `restoredVmName` when one was set). There is no
    progress percentage - infer status from `state`: `"Mounting"`
    (in progress), `"Mounted"` (ready, VM published and running),
    `"Dismounting"` (being torn down), `"Failed"` (surface `errorMessage`). The
    mount appears in the list only after VBR creates it, a few seconds into
    the start. The mount id is the id `start_instant_recovery_vsphere_vm`
    returned.
    """
    if mount_id is not None:
        return await vbr_client.get(f"{_MOUNT_PATH}/{mount_id}")
    return await fetch_all(vbr_client, _MOUNT_PATH, vmNameFilter=vm_name_filter, stateFilter=state_filter)


@mcp.tool(annotations=DESTRUCTIVE)
async def migrate_instant_recovery_vsphere_vm(
    mount_id: UUID,
    destination_host: VmwareObjectModel,
    resource_pool: VmwareObjectModel | None = None,
    folder: VmwareObjectModel | None = None,
    datastore: ViVMQuickMigrationDatastoresSpec | None = None,
    source_proxy_ids: list[UUID] | None = None,
    target_proxy_ids: list[UUID] | None = None,
    veeam_quick_migration_enabled: bool | None = None,
    delete_source_vm_files: bool | None = None,
) -> dict[str, Any] | None:
    """Quick-migrate a mounted Instant Recovery VM to permanent storage on `destination_host`.

    `destination_host` is a `Host` inventory row passed as-is (from
    `browse_inventory(..., hierarchy_type="HostsAndClusters")`; a standalone ESXi
    host: its `list_vmware_hosts` row); `resource_pool`, `folder` (a VM `Folder` row) and
    the datastores in `datastore` come from `browse_inventory` on the same
    server. Resource pool, folder, datastore and proxies default to VBR's own
    choice when omitted. For per-disk placement give each `datastore.diskMappings`
    entry the disk's `id` only (the IR VM's device key, e.g. `2000`): the tool
    looks up its current file name, which changes with every snapshot.
    `veeam_quick_migration_enabled=False` asks VBR for VMware vMotion, but that is
    a preference: without a vCenter (a standalone ESXi target) VBR copies the
    data itself (`SmartSwitch`) either way. Migration copies the whole VM and
    can take an hour or more; follow the returned session.
    """
    disk_datastores = {
        f"datastore.diskMappings[{i}].datastore": (mapping.datastore, DATASTORES)
        for i, mapping in enumerate((datastore.diskMappings if datastore else None) or [])
    }
    check_placement(
        "destination_host",
        destination_host,
        {
            "resource_pool": (resource_pool, RESOURCE_POOLS),
            "folder": (folder, VM_FOLDERS),
            "datastore.defaultDatastore": (datastore.defaultDatastore if datastore else None, DATASTORES),
            "datastore.configurationFileDatastore": (
                datastore.configurationFileDatastore if datastore else None,
                DATASTORES,
            ),
            **disk_datastores,
        },
    )
    datastore_body: dict[str, Any] | None = None
    if datastore is not None:
        datastore_body = datastore.model_dump(mode="json", exclude_none=True)
        if datastore.diskMappings:
            await _fill_current_disk_names(mount_id, destination_host, datastore_body["diskMappings"])
    body: dict[str, Any] = {}
    _put(
        body,
        destinationHost=destination_host,
        resourcePool=resource_pool,
        folder=folder,
        datastore=datastore_body,
        sourceProxyIds=source_proxy_ids,
        targetProxyIds=target_proxy_ids,
        VeeamQMEnabled=veeam_quick_migration_enabled,
        DeleteSourceVmsFiles=delete_source_vm_files,
    )
    return await vbr_client.post(f"{_MOUNT_PATH}/{mount_id}/migrate", json=body, timeout=_ACTION_TIMEOUT_SEC)


async def _fill_current_disk_names(
    mount_id: UUID, destination_host: VmwareObjectModel, disk_mappings: list[dict[str, Any]]
) -> None:
    """Set each mapping's `disk.name` to the IR VM's current disk file name, rejecting unknown disk ids.

    VBR identifies a migrated disk by id and file name, and the name changes with every snapshot of the IR VM (a
    failed migration attempt leaves one behind), so it is read fresh rather than trusted from the caller.
    """
    mount = await vbr_client.get(f"{_MOUNT_PATH}/{mount_id}")
    vm_rows = await _find_ir_vm_rows(mount, destination_host)
    if len(vm_rows) != 1:
        if all(mapping["disk"].get("name") for mapping in disk_mappings):
            return  # the caller named every disk; send them as given
        vm_name = mount.get("vmName")
        # Several rows: guessing could read the disks of a same-named VM, such as the original, and migrate wrong files.
        problem = (
            f"Could not find the Instant Recovery VM {vm_name!r} in the inventory"
            if not vm_rows
            else f"{len(vm_rows)} VMs in the inventory are named {vm_name!r} and the Instant Recovery VM is not "
            "told apart from the others"
        )
        raise ToolError(
            f"{problem}, so its disk names cannot be read. Pass each `datastore.diskMappings[].disk.name` yourself, "
            "from `api_post_query('/api/v1/inventory/retrieveMachineDetails', {'object': <the IR VM's inventory row>})`."
        )
    vm_object = VmwareObjectModel.model_validate(vm_rows[0])
    details = await vbr_client.post(
        "/api/v1/inventory/retrieveMachineDetails", json={"object": vm_object}, read_only=True
    )
    current = {disk["id"]: disk["name"] for disk in (details or {}).get("disks", [])}
    for mapping in disk_mappings:
        disk_id = mapping["disk"]["id"]
        if disk_id not in current:
            known = ", ".join(f"{i} ({name})" for i, name in current.items()) or "none"
            raise ToolError(f"The Instant Recovery VM has no disk with id {disk_id}; its disks are: {known}.")
        mapping["disk"]["name"] = current[disk_id]


async def _find_ir_vm_rows(mount: dict[str, Any], destination_host: VmwareObjectModel) -> list[dict[str, Any]]:
    """The inventory rows named as a mount's published VM, searched on every server it can live on."""
    vm_name = mount.get("vmName")
    if not vm_name:
        return []
    mount_host = ((mount.get("spec") or {}).get("destination") or {}).get("destinationHost") or {}
    servers = dict.fromkeys(
        server for server in (mount_host.get("hostName"), mount.get("hostName"), destination_host.hostName) if server
    )
    query: dict[str, object] = {
        "hierarchyType": "HostsAndClusters",
        "filter": {
            "type": "GroupExpression",
            "operation": "And",
            "items": [
                {"type": "PredicateExpression", "property": "name", "operation": "Equals", "value": vm_name},
                {"type": "PredicateExpression", "property": "type", "operation": "Equals", "value": "VirtualMachine"},
            ],
        },
    }
    found: dict[tuple[object, object], dict[str, Any]] = {}
    for server in servers:
        try:
            rows = await vbr_client.post(f"/api/v1/inventory/{quote(server, safe='')}", json=query, read_only=True)
        except ToolError:
            continue
        for row in (rows or {}).get("data", []):
            if row.get("name") == vm_name and row.get("type") == "VirtualMachine":
                found.setdefault((row.get("hostName"), row.get("objectId")), row)
    return list(found.values())


@mcp.tool(annotations=DESTRUCTIVE)
async def unmount_instant_recovery_vsphere_vm(mount_id: UUID) -> None:
    """Unmount (tear down) a vSphere Instant Recovery mount."""
    await vbr_client.post(f"{_MOUNT_PATH}/{mount_id}/unmount", timeout=_ACTION_TIMEOUT_SEC)


@mcp.tool(annotations=DESTRUCTIVE)
async def restore_file_share(
    restore_point_id: UUID,
    destination: UnstructuredDataShareRestoreDestinationModel | None = None,
    restore_options: UnstructuredDataShareRestoreOptionsModel | None = None,
) -> dict[str, Any] | None:
    """Restore an entire unstructured-data file share from `restore_point_id`.

    Defaults to restoring to the original location. Pass `destination` to
    restore elsewhere (target server id from `list_unstructured_data_servers`);
    without a `path` the target share's root is used.
    """
    destination_body: dict[str, Any] | None = None
    if destination is not None:
        destination_body = destination.model_dump(mode="json", exclude_none=True)
        server_id = destination.unstructuredDataServerId
        if server_id is not None and destination.path is None and not destination.restoreToBackupServer:
            # VBR requires the target to sit under the share's root, so default to that root.
            server = await vbr_client.get(f"/api/v1/inventory/unstructuredDataServers/{server_id}")
            root = server.get("path") if isinstance(server, dict) else None
            if not isinstance(root, str) or not root:
                raise ToolError(
                    f"Unstructured data server {server_id} exposes no share root path; pass `destination.path`."
                )
            destination_body["path"] = root
    body: dict[str, Any] = {"restorePointId": restore_point_id}
    _put(body, destination=destination_body, restoreOptions=restore_options)
    return await vbr_client.post("/api/v1/restore/unstructuredData/fileShare", json=body, timeout=_ACTION_TIMEOUT_SEC)


@mcp.tool(annotations=DESTRUCTIVE)
async def restore_object_storage(
    restore_point_id: UUID,
    destination: UnstructuredDataOSRestoreDestinationModel | None = None,
    restore_options: UnstructuredDataOSRestoreOptionsModel | None = None,
) -> dict[str, Any] | None:
    """Restore an entire object-storage bucket/container from `restore_point_id`.

    Defaults to restoring to the original location. Pass `destination` to
    restore elsewhere (target server id from `list_unstructured_data_servers`):
    `newBucketName` has VBR create a bucket, `path` restores into an existing
    one. A new bucket has nothing to overwrite, so `overwriteMode` and
    `overwriteBucketAttributes` are refused with it.
    """
    if (
        destination is not None
        and destination.newBucketName is not None
        and restore_options is not None
        and (restore_options.overwriteMode is not None or restore_options.overwriteBucketAttributes is not None)
    ):
        raise ToolError(
            "`restore_options.overwriteMode`/`overwriteBucketAttributes` do not apply to a new bucket "
            "(`destination.newBucketName`) - VBR rejects them; leave them out."
        )
    body: dict[str, Any] = {"restorePointId": restore_point_id}
    _put(body, destination=destination, restoreOptions=restore_options)
    return await vbr_client.post(
        "/api/v1/restore/unstructuredData/objectStorage", json=body, timeout=_ACTION_TIMEOUT_SEC
    )


@mcp.tool(annotations=DESTRUCTIVE)
async def restore_vsphere_vm(
    restore_point_id: UUID,
    mode: Literal["OriginalLocation", "Customized"] = "OriginalLocation",
    power_up: bool = True,
    overwrite: bool = False,
    reason: str | None = None,
    antivirus_scan_enabled: bool = False,
    yara_scan_enabled: bool = False,
    restore_proxies: RestoreProxySpec | None = None,
    destination_host: VmwareObjectModel | None = None,
    resource_pool: VmwareObjectModel | None = None,
    datastore: RestoreTargetDatastoresSpec | None = None,
    folder: RestoreTargetFolderSpec | None = None,
    network: RestoreTargetNetworkSpec | None = None,
) -> dict[str, Any] | None:
    """Restore an entire vSphere VM (a full-copy restore, not Instant Recovery) from `restore_point_id`.

    `mode="OriginalLocation"` restores to the VM's original host/datastore.
    Every restore copies the whole VM from the backup, also in place: VBR's REST
    API has no quick rollback (restoring only the blocks changed since the
    point) for vSphere VMs.
    `overwrite=True` replaces an existing VM of the same name - a destructive,
    hard-to-reverse choice; only pass it when the caller explicitly wants that.
    `mode="Customized"` requires `destination_host`, `datastore.defaultDatastore`
    and `network` (VBR would otherwise silently keep the source network
    settings; only a VM backed up without networks may leave it out), and can
    take `resource_pool` and `folder`. `folder.vmName`
    renames the VM, so a rename needs a `folder`: a VM `Folder` row under a
    vCenter, or the `Datacenter` row (`HostsAndDatastores` browse) on a
    standalone ESXi host. Every vSphere object is an inventory row passed as-is:
    the host a `Host` row from `browse_inventory(..., hierarchy_type=
    "HostsAndClusters")` (a standalone ESXi host: its `list_vmware_hosts` row),
    the rest from `browse_inventory` on the host's `hostName` server (target
    networks: `hierarchy_type="Network"`;
    source networks: the source server's rows matching the restore point's
    `api_post_query('/api/v1/restorePoints/{id}/networkInfo')` by name - its
    `id` is not the inventory `objectId`, e.g. `id: "192"` for the row with
    `objectId: "VM Network"`, so pass the inventory row). Per-disk
    placement (`datastore.diskMappings`) names disks as
    `GET /api/v1/restorePoints/{id}/disks` does.
    """
    placement = {
        "destination_host": destination_host,
        "resource_pool": resource_pool,
        "datastore": datastore,
        "folder": folder,
        "network": network,
    }
    if mode == "OriginalLocation":
        _check_mode(mode, required={}, not_allowed=placement)
    else:
        _check_mode(
            mode,
            required={
                "destination_host": destination_host,
                "datastore.defaultDatastore": datastore.defaultDatastore if datastore else None,
            },
            not_allowed={},
        )
        assert destination_host is not None  # narrowed by the check above
        assert datastore is not None
        networks = network.networks if network is not None else []
        check_placement(
            "destination_host",
            destination_host,
            {
                "resource_pool": (resource_pool, RESOURCE_POOLS),
                "datastore.defaultDatastore": (datastore.defaultDatastore, DATASTORES),
                "datastore.configurationFileDatastore": (datastore.configurationFileDatastore, DATASTORES),
                **{
                    f"datastore.diskMappings[{i}].datastore": (mapping.datastore, DATASTORES)
                    for i, mapping in enumerate(datastore.diskMappings or [])
                },
                "folder.folder": (folder.folder if folder else None, PLACEMENT_ROOTS),
                **{
                    f"network.networks[{i}].targetNetwork": (mapping.targetNetwork, NETWORKS)
                    for i, mapping in enumerate(networks)
                },
            },
        )
        for i, mapping in enumerate(networks):
            check_type(f"network.networks[{i}].sourceNetwork", mapping.sourceNetwork, NETWORKS)
        if network is None:
            await _check_backed_up_without_networks(restore_point_id)
        if datastore.diskMappings:
            await _check_disk_names(restore_point_id, [mapping.diskName for mapping in datastore.diskMappings])
    _check_restore_proxies(restore_proxies)
    body: dict[str, Any] = {
        "restorePointId": restore_point_id,
        "type": mode,
        "secureRestore": {"antivirusScanEnabled": antivirus_scan_enabled, "yaraScanEnabled": yara_scan_enabled},
        "powerUp": power_up,
        "overwrite": overwrite,
    }
    _put(
        body,
        reason=reason,
        restoreProxies=restore_proxies,
        destinationHost=destination_host,
        resourcePool=resource_pool,
        datastore=datastore,
        folder=folder,
        network=network,
    )
    return await vbr_client.post("/api/v1/restore/vmRestore/vSphere", json=body, timeout=_ACTION_TIMEOUT_SEC)


async def _check_backed_up_without_networks(restore_point_id: UUID) -> None:
    """Reject a customized restore without `network` unless the VM has no networks to map.

    Without a network mapping VBR silently keeps the source network settings, which can put the restored VM on the
    original's network next to the original.
    """
    info = await vbr_client.post(f"/api/v1/restorePoints/{restore_point_id}/networkInfo", json={}, read_only=True)
    names = [row.get("name") for row in (info or {}).get("data", []) if isinstance(row, dict)]
    if names:
        raise ToolError(
            f'mode="Customized" requires: network. The VM was backed up with networks {", ".join(map(repr, names))}, '
            "whose settings VBR would otherwise silently keep: map each to a target `Network` row "
            "(`browse_inventory(server_name=<destination_host.hostName>, hierarchy_type='Network')`)."
        )


async def _check_disk_names(restore_point_id: UUID, disk_names: list[str]) -> None:
    """Reject disk names VBR would not find: it matches `diskName` against the restore point's disk names."""
    disks = await fetch_all(vbr_client, f"/api/v1/restorePoints/{restore_point_id}/disks")
    known = [disk["name"] for disk in disks if isinstance(disk, dict) and disk.get("name")]
    if unknown := [name for name in disk_names if name not in known]:
        raise ToolError(
            f"Unknown `datastore.diskMappings[].diskName` {', '.join(map(repr, unknown))}: VBR names this "
            f"restore point's disks {', '.join(map(repr, known)) or '(none)'} - use those exact values, not "
            ".vmdk file names, device keys or controller slots."
        )
    if len(set(disk_names)) != len(disk_names):
        raise ToolError("`datastore.diskMappings` maps the same disk more than once.")


def _check_restore_proxies(restore_proxies: RestoreProxySpec | None) -> None:
    if restore_proxies is None:
        return
    if restore_proxies.autoSelectEnabled and restore_proxies.proxyIds:
        raise ToolError("`restore_proxies.proxyIds` is only used with `autoSelectEnabled: false`.")
    if not restore_proxies.autoSelectEnabled and not restore_proxies.proxyIds:
        raise ToolError("`restore_proxies` with `autoSelectEnabled: false` needs `proxyIds` (see `list_proxies`).")
