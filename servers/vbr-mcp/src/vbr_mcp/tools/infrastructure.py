# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

from typing import Any, Literal
from uuid import UUID

from vbr_mcp.pagination import fetch_all
from vbr_mcp.server import mcp, vbr_client
from vbr_mcp.tool_annotations import DESTRUCTIVE, READ_ONLY, WRITE

_PROXIES_PATH = "/api/v1/backupInfrastructure/proxies"
_PROXY_STATES_PATH = "/api/v1/backupInfrastructure/proxies/states"
_REPOSITORIES_PATH = "/api/v1/backupInfrastructure/repositories"
_REPOSITORY_STATES_PATH = "/api/v1/backupInfrastructure/repositories/states"

# `ERepositoryType`
RepositoryType = Literal[
    "WinLocal",
    "LinuxLocal",
    "Smb",
    "Nfs",
    "AzureBlob",
    "AzureDataBox",
    "AzureArchive",
    "AmazonS3",
    "AmazonSnowballEdge",
    "AmazonS3Glacier",
    "S3Compatible",
    "GoogleCloud",
    "IBMCloud",
    "ExtendableRepository",
    "DellDataDomain",
    "ExaGrid",
    "HPEStoreOnce",
    "QuantumDXi",
    "WasabiCloud",
    "LinuxHardened",
    "Infinidat",
    "Fujitsu",
    "VeeamDataCloudVault",
    "S3GlacierCompatible",
    "S3Integrated",
    "Cloud",
    "HPStoreOnce",
    "Foreign",
    "SanSnapshotOnly",
    "Tape",
    "AmazonS3External",
    "AzureStorageExternal",
    "PlatformServiceExternal",
    "GoogleCloudStorageExternal",
    "PlatformServiceVmbApi",
    "AmazonS3GlacierExternal",
    "GoogleArchiveStorageExternal",
    "AzureArchiveStorageExternal",
    "HPStoreOnceCloudBank",
    "VeeamVault",
    "ElevenElevenS3",
    "AbrVirtual",
    "VeeamDataCloudVaultArchive",
    "VeeamDataCloudVaultExternal",
]


@mcp.tool(annotations=READ_ONLY)
async def list_proxies(
    name_filter: str | None = None,
    type_filter: Literal["ViProxy", "HvProxy", "GeneralPurposeProxy", "NutanixAHV", "PVE"] | None = None,
) -> list[dict[str, Any]]:
    """List backup proxies, joined with their live state (one flat row per proxy).

    There is no `enabled` field - a proxy can actually run tasks only when
    `isDisabled == False AND isOnline == True AND isOutOfDate == False` (a proxy
    whose Veeam components are out of date takes no tasks until they are
    updated, e.g. after a VBR upgrade); sum `server.maxTaskCount` over those for
    total usable task slots (a *configured* limit, not validated hardware
    capacity). `server.transportMode` (VMware only) is
    `DirectAccess` (fastest, needs a matching entry in
    `server.connectedDatastores`) > `VirtualAppliance` (Hot-Add) > `Network`
    (NBD, slowest) > `Auto`.
    """
    proxies = await fetch_all(vbr_client, _PROXIES_PATH, nameFilter=name_filter, typeFilter=type_filter)
    states = await fetch_all(vbr_client, _PROXY_STATES_PATH)
    states_by_id = {s.get("id"): s for s in states}
    return [{**states_by_id.get(p.get("id"), {}), **p} for p in proxies]


@mcp.tool(annotations=WRITE)
async def set_proxy_enabled(proxy_id: UUID, enabled: bool) -> None:
    """Enable or disable one backup proxy (a disabled proxy is skipped by job scheduling)."""
    action = "enable" if enabled else "disable"
    await vbr_client.post(f"{_PROXIES_PATH}/{proxy_id}/{action}")


@mcp.tool(annotations=READ_ONLY)
async def list_repositories(
    name_filter: str | None = None, type_filter: RepositoryType | None = None
) -> list[dict[str, Any]]:
    """List backup repositories, joined with live state: capacity, free space, and reconciliation.

    Excludes Scale-Out Backup Repositories (SOBRs) themselves - the rows here
    that belong to a SOBR are its member extents; use
    `list_scale_out_repositories` for the SOBR containers. Adds `freePercent`
    and `usedSpaceGBDerived` (the repo's actual used space, preferred over the
    raw `usedSpaceGB`, which is only what VBR's database tracks) plus the
    reconciliation gap: `unidentifiedDataGB` (on-disk data VBR isn't tracking)
    and `phantomDataGB` (VBR records more than the storage reports). Low space
    is a heuristic: free space below 10% of capacity or below 100 GB absolute,
    whichever trips first. Object storage may report `capacityGB`/`freeGB` as
    `-1` (not reported, e.g. Amazon S3): `freePercent` is then null - the free
    space is unknown, not 100%, and does not belong in any free-space total.
    """
    repos = await fetch_all(vbr_client, _REPOSITORIES_PATH, nameFilter=name_filter, typeFilter=type_filter)
    states = await fetch_all(vbr_client, _REPOSITORY_STATES_PATH)
    states_by_id = {s.get("id"): s for s in states}
    return [_join_repository_state(repo, states_by_id.get(repo.get("id"), {})) for repo in repos]


_RECON_ABS_FLOOR_GB = 2.0
_RECON_REL_TOL = 0.01


def _join_repository_state(repo: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    merged = {**state, **repo}
    capacity_gb = state.get("capacityGB")
    free_gb = state.get("freeGB")
    used_gb = state.get("usedSpaceGB")
    physical_used, unidentified, phantom = _reconcile_space(capacity_gb, used_gb, free_gb)
    merged["freePercent"] = _free_percent(free_gb, capacity_gb)
    merged["usedSpaceGBDerived"] = physical_used
    merged["unidentifiedDataGB"] = unidentified
    merged["phantomDataGB"] = phantom
    return merged


def _known_space(capacity_gb: float | None, free_gb: float | None) -> tuple[float, float] | None:
    """Capacity and free space, if the storage reported both.

    Object storage reports -1 for a capacity or free space it does not know: that is no percentage at all, not 100%.
    """
    if capacity_gb is None or free_gb is None or capacity_gb <= 0 or free_gb < 0:
        return None
    return capacity_gb, free_gb


def _free_percent(free_gb: float | None, capacity_gb: float | None) -> float | None:
    if (space := _known_space(capacity_gb, free_gb)) is None:
        return None
    capacity, free = space
    return round(free / capacity * 100, 1)


def _reconcile_space(
    capacity_gb: float | None, used_space_gb: float | None, free_gb: float | None
) -> tuple[float | None, float | None, float | None]:
    if (space := _known_space(capacity_gb, free_gb)) is None:
        physical = float(used_space_gb) if used_space_gb else None
        return physical, None, None
    capacity, free = space
    physical = round(max(capacity - free, 0.0), 1)
    if used_space_gb is None:
        return physical, None, None
    used = float(used_space_gb)
    tolerance = max(_RECON_ABS_FLOOR_GB, _RECON_REL_TOL * max(physical, used))
    unidentified = physical - used
    phantom = used - physical
    return (
        physical,
        round(unidentified, 1) if unidentified > tolerance else 0.0,
        round(phantom, 1) if phantom > tolerance else 0.0,
    )


@mcp.tool(annotations=WRITE)
async def rescan_repositories(repository_ids: list[UUID]) -> None:
    """Rescan one or more backup repositories to refresh their known state."""
    await vbr_client.post(f"{_REPOSITORIES_PATH}/rescan", json={"repositoryIds": repository_ids})


@mcp.tool(annotations=READ_ONLY)
async def list_scale_out_repositories(name_filter: str | None = None) -> list[dict[str, Any]]:
    """List Scale-Out Backup Repositories (SOBRs), each with its tiers and member extents already inlined.

    No per-SOBR detail call is needed. Extent capacity/free space is not on this model - join extent `id`s
    (`performanceTier.performanceExtents[]`, `capacityTier.extents[]`) to
    `list_repositories` for those numbers, and aggregate the **performance
    tier only** (capacity/archive tiers are object storage - do not sum their
    capacity into one figure). A performance extent's `status`:
    `"Maintenance"` - no new writes, and no restore from backup files on the
    extent (nor from chains partly stored on it); a job whose active chain sits
    on it fails until a new full is made on another extent. `"Pending"` -
    maintenance was requested and waits for the extent's running tasks to end.
    `"Sealed"` - no new writes, but restore, merge and retention still work; the
    next run of a job whose chain is there makes an active full on another
    extent. Capacity-tier extents have no `status`.
    """
    return await fetch_all(vbr_client, "/api/v1/backupInfrastructure/scaleOutRepositories", nameFilter=name_filter)


@mcp.tool(annotations=DESTRUCTIVE)
async def set_sobr_extent_maintenance_mode(sobr_id: UUID, extent_repository_ids: list[UUID], enabled: bool) -> None:
    """Put SOBR performance-tier extents into (or take them out of) maintenance mode.

    `sobr_id` is the SOBR's own id, `extent_repository_ids` are its member extents' repository ids (not the SOBR id).
    """
    action = "enableMaintenanceMode" if enabled else "disableMaintenanceMode"
    await vbr_client.post(
        f"/api/v1/backupInfrastructure/scaleOutRepositories/{sobr_id}/{action}",
        json={"repositoryIds": extent_repository_ids},
    )


@mcp.tool(annotations=DESTRUCTIVE)
async def set_sobr_extent_sealed_mode(sobr_id: UUID, extent_repository_ids: list[UUID], enabled: bool) -> None:
    """Seal (or unseal) SOBR performance-tier extents - a sealed extent keeps existing data but takes no new writes.

    `sobr_id` is the SOBR's own id, `extent_repository_ids` are its member extents' repository ids.
    """
    action = "enableSealedMode" if enabled else "disableSealedMode"
    await vbr_client.post(
        f"/api/v1/backupInfrastructure/scaleOutRepositories/{sobr_id}/{action}",
        json={"repositoryIds": extent_repository_ids},
    )


@mcp.tool(annotations=READ_ONLY)
async def list_wan_accelerators(name_filter: str | None = None) -> list[dict[str, Any]]:
    """List WAN accelerators: cache size/location, high-bandwidth mode, stream counts.

    No online/health state exists for these. `streamsCount` and the global
    cache are meaningful on the source and target side respectively - this
    endpoint carries no source/target role, so it cannot be labelled from here
    alone. `highBandwidthModeEnabled` on suits links >=~100 Mbps or a high
    change rate; off uses the global cache (sized ~10 GB per OS type per
    source feeding the target) for slower links.
    """
    return await fetch_all(vbr_client, "/api/v1/backupInfrastructure/wanAccelerators", nameFilter=name_filter)


@mcp.tool(annotations=WRITE)
async def rescan_managed_server(managed_server_id: UUID) -> None:
    """Rescan one managed server (host/cluster) to refresh its inventory.

    `managed_server_id` is a managed server's own id: the `id` of a row of
    `api_get("/api/v1/backupInfrastructure/managedServers")` (vCenter Servers and ESXi hosts are `type: "ViHost"`), also
    shown as the `hostId` of a proxy, a repository or a WAN accelerator. An inventory `objectId` (from
    `list_vmware_hosts`/`browse_inventory`) is a different id even when it looks like one.
    """
    await vbr_client.post(f"/api/v1/backupInfrastructure/managedServers/{managed_server_id}/rescan")


@mcp.tool(annotations=DESTRUCTIVE)
async def update_managed_server_components(managed_server_ids: list[UUID]) -> None:
    """Update the Veeam components installed on one or more managed servers."""
    await vbr_client.post(
        "/api/v1/backupInfrastructure/managedServers/updateComponents", json={"ids": managed_server_ids}
    )
