# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""``/api/v1/backupInfrastructure``: repositories, scale-out repositories, proxies, WAN accelerators, managed servers."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from vbr_models import VbrModel

RepositoryType = Literal["WinLocal", "LinuxLocal", "LinuxHardened", "Smb", "AmazonS3"]
"""The ``ERepositoryType`` values the cases use."""
ExtentType = Literal["Performance", "Capacity", "Archive"]
ExtentStatus = Literal["Normal", "Evacuate", "Pending", "Sealed", "Maintenance", "ResyncRequired"]


# ---- Repositories: ``/repositories`` (the configuration) and ``/repositories/states`` (live capacity)


class RepositorySettings(VbrModel):
    """The ``repository`` settings of a block repository (``WindowsLocalRepositorySettingsModel`` and kin)."""

    path: str | None = None
    task_limit_enabled: bool | None = None
    max_task_count: int | None = None
    make_recent_backups_immutable_days: int | None = None  # hardened Linux only


class SmbShare(VbrModel):
    """``SmbRepositoryShareSettingsModel``."""

    share_path: str


class Repository(VbrModel):
    """``RepositoryModel`` and its subtypes, an item of ``GET /api/v1/backupInfrastructure/repositories``."""

    id: UUID
    name: str
    description: str
    type: RepositoryType
    host_id: UUID | None = None
    repository: RepositorySettings | None = None
    share: SmbShare | None = None  # Smb only


class ScaleOutRepositoryDetails(VbrModel):
    """``ScaleOutRepositoryDetailsModel``: the SOBR a repository is an extent of."""

    membership: str
    scale_out_repository_id: UUID
    extent_type: ExtentType


class RepositoryState(VbrModel):
    """``RepositoryStateModel``, an item of ``GET /api/v1/backupInfrastructure/repositories/states``."""

    id: UUID
    name: str
    type: RepositoryType
    description: str
    host_id: UUID | None = None
    host_name: str | None = None
    path: str | None = None
    capacity_gb: float = Field(alias="capacityGB")
    free_gb: float = Field(alias="freeGB")
    used_space_gb: float = Field(alias="usedSpaceGB")
    is_online: bool
    scale_out_repository_details: ScaleOutRepositoryDetails | None = None
    is_out_of_date: bool


# ---- Scale-out repositories: ``/scaleOutRepositories``


class PerformanceExtent(VbrModel):
    """``PerformanceExtentModel``."""

    id: UUID
    name: str
    status: list[ExtentStatus]


class PerformanceTier(VbrModel):
    """``PerformanceTierModel``."""

    performance_extents: list[PerformanceExtent]


class PlacementPolicy(VbrModel):
    """``PlacementPolicyModel``."""

    type: Literal["DataLocality", "Performance"]


class CapacityExtent(VbrModel):
    """``CapacityExtentModel``."""

    id: UUID


class StorageEncryption(VbrModel):
    """``BackupStorageSettingsEncryptionModel``."""

    is_enabled: bool


class CapacityTier(VbrModel):
    """``CapacityTierModel``."""

    is_enabled: bool
    extents: list[CapacityExtent] | None = None
    copy_policy_enabled: bool | None = None
    move_policy_enabled: bool | None = None
    operational_restore_period_days: int | None = None
    encryption: StorageEncryption | None = None


class ArchiveTier(VbrModel):
    """``ArchiveTierModel``."""

    is_enabled: bool


class ScaleOutRepository(VbrModel):
    """``ScaleOutRepositoryModel``, an item of ``GET /api/v1/backupInfrastructure/scaleOutRepositories``."""

    id: UUID
    name: str
    description: str
    performance_tier: PerformanceTier
    placement_policy: PlacementPolicy | None = None
    capacity_tier: CapacityTier | None = None
    archive_tier: ArchiveTier | None = None


# ---- Proxies: ``/proxies`` (the configuration) and ``/proxies/states`` (live state)


class ProxyServer(VbrModel):
    """``ProxyServerSettingsModel``."""

    host_id: UUID
    host_name: str | None = None
    transport_mode: Literal["Auto", "DirectAccess", "VirtualAppliance", "Network"] | None = None
    failover_to_network: bool | None = None
    host_to_proxy_encryption: bool | None = None
    max_task_count: int | None = None


class Proxy(VbrModel):
    """``ViProxyModel``, an item of ``GET /api/v1/backupInfrastructure/proxies``."""

    id: UUID
    name: str
    description: str
    type: Literal["ViProxy"]
    server: ProxyServer


class ProxyState(VbrModel):
    """``ProxyStateModel``, an item of ``GET /api/v1/backupInfrastructure/proxies/states``."""

    id: UUID
    name: str
    description: str
    type: Literal["ViProxy"]
    host_id: UUID
    host_name: str
    is_disabled: bool
    is_online: bool
    is_out_of_date: bool


# ---- WAN accelerators: ``/wanAccelerators``


class WanAcceleratorServer(VbrModel):
    """``WANAcceleratorServerModel``."""

    host_id: UUID
    description: str | None = None
    traffic_port: int | None = None
    streams_count: int | None = None
    high_bandwidth_mode_enabled: bool | None = None


class WanAcceleratorCache(VbrModel):
    """``WANAcceleratorCacheModel``."""

    cache_folder: str | None = None
    cache_size: int | None = None
    cache_size_unit: Literal["B", "KB", "MB", "GB", "TB", "PB"] | None = None


class WanAccelerator(VbrModel):
    """``WANAcceleratorModel``, an item of ``GET /api/v1/backupInfrastructure/wanAccelerators``."""

    id: UUID
    name: str
    server: WanAcceleratorServer
    cache: WanAcceleratorCache


# ---- Managed servers: ``GET /managedServers``

ManagedServerStatus = Literal["Available", "Unavailable"]
"""``EManagedServersStatus``."""


class ManagedServer(VbrModel):
    """A Windows or Linux host, as ``GET /api/v1/backupInfrastructure/managedServers`` lists it.

    ``WindowsHostModel`` or ``LinuxHostModel``, with the fields every managed server has.
    """

    id: UUID
    name: str
    description: str
    type: Literal["WindowsHost", "LinuxHost"]
    status: ManagedServerStatus = "Available"


class ViManagedServer(VbrModel):
    """``ViHostModel``: a vCenter Server or ESXi host added to the backup infrastructure, as a managed server."""

    id: UUID
    name: str
    description: str
    type: Literal["ViHost"] = "ViHost"
    status: ManagedServerStatus = "Available"
    vi_host_type: Literal["ESX", "ESXi", "VC"]
    port: int = 443
