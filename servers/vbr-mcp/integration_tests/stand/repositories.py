# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""Repositories (1.4) and the scale-out repository (1.5).

``/repositories`` configures them, ``/repositories/states`` reports their space. Low on space by vbr-mcp's rule (below
10% or 100 GB free): Repo-Linux-01 (4.2%), SOBR-Ext-02 (3.7%) and Repo-Branch (90 GB). S3-Capacity is object storage
that reports no capacity (-1). SOBR-Ext-03 is in maintenance mode.
"""

from uuid import UUID

from stand.ids import M06, M07, M08, M09, M10, M13, R01, R02, R03, R04, R05, R06, R07, R08, S01
from stand.proxies import MANAGED_SERVERS
from vbr_models.infrastructure import (
    ArchiveTier,
    CapacityExtent,
    CapacityTier,
    ExtentStatus,
    ExtentType,
    PerformanceExtent,
    PerformanceTier,
    PlacementPolicy,
    Repository,
    RepositorySettings,
    RepositoryState,
    RepositoryType,
    ScaleOutRepository,
    ScaleOutRepositoryDetails,
    SmbShare,
    StorageEncryption,
)

SOBR_NAME = "SOBR-Prod"


def repository(
    id: UUID,
    name: str,
    type: RepositoryType,
    host_id: UUID | None,
    path: str | None,
    capacity_gb: float,
    free_gb: float,
    used_space_gb: float,
    *,
    extent: ExtentType | None = None,
    immutable_days: int | None = None,
    is_online: bool = True,
) -> tuple[Repository, RepositoryState]:
    """A repository as ``/repositories`` configures it and as ``/repositories/states`` reports it."""
    settings = None
    if type in ("WinLocal", "LinuxLocal", "LinuxHardened"):
        settings = RepositorySettings(
            path=path, task_limit_enabled=True, max_task_count=4, make_recent_backups_immutable_days=immutable_days
        )
    config = Repository(
        id=id,
        name=name,
        description="",
        type=type,
        host_id=host_id,
        repository=settings,
        share=SmbShare(share_path=path) if type == "Smb" and path else None,
    )
    state = RepositoryState(
        id=id,
        name=name,
        type=type,
        description="",
        host_id=host_id,
        host_name=MANAGED_SERVERS[host_id] if host_id else None,
        path=path,
        capacity_gb=capacity_gb,
        free_gb=free_gb,
        used_space_gb=used_space_gb,
        is_online=is_online,
        scale_out_repository_details=(
            ScaleOutRepositoryDetails(membership=SOBR_NAME, scale_out_repository_id=S01, extent_type=extent)
            if extent
            else None
        ),
        is_out_of_date=False,
    )
    return config, state


_REPOSITORIES = [
    repository(R01, "Repo-Main", "WinLocal", M06, "D:\\Backups", 10240, 1843, 8100),
    repository(R02, "Repo-Linux-01", "LinuxHardened", M07, "/mnt/veeam/backups", 20480, 860, 19600, immutable_days=14),
    repository(R03, "Repo-Branch", "Smb", None, "\\\\nas02\\veeam", 600, 90, 505),
    repository(R04, "Repo-DR", "LinuxLocal", M13, "/backups", 15360, 7000, 8350),
    repository(R05, "SOBR-Ext-01", "WinLocal", M08, "E:\\SOBR", 8192, 2500, 5690, extent="Performance"),
    repository(R06, "SOBR-Ext-02", "WinLocal", M09, "E:\\SOBR", 8192, 300, 7890, extent="Performance"),
    repository(R07, "SOBR-Ext-03", "WinLocal", M10, "E:\\SOBR", 4096, 3900, 196, extent="Performance"),
    # Amazon S3 reports no capacity: -1 for both. It is unbounded, not 100% free.
    repository(R08, "S3-Capacity", "AmazonS3", None, None, -1, -1, 5400, extent="Capacity"),
]  # fmt: skip

REPOSITORIES: list[Repository] = [config for config, _ in _REPOSITORIES]
NAMES: dict[UUID, str] = {config.id: config.name for config in REPOSITORIES} | {S01: SOBR_NAME}
"""Every repository's name and SOBR-Prod's, by id: what a job's or a backup's ``repositoryName`` reads."""
"""``GET /api/v1/backupInfrastructure/repositories``: R01-R08, the SOBR's extents among them."""

REPOSITORY_STATES: list[RepositoryState] = [state for _, state in _REPOSITORIES]
"""``GET /api/v1/backupInfrastructure/repositories/states``."""

EXTENT_STATUS: dict[UUID, ExtentStatus] = {R05: "Normal", R06: "Normal", R07: "Maintenance"}


def scale_out_repository() -> ScaleOutRepository:
    """SOBR-Prod with its extents in ``EXTENT_STATUS``."""
    return ScaleOutRepository(
        id=S01,
        name=SOBR_NAME,
        description="",
        performance_tier=PerformanceTier(
            performance_extents=[
                PerformanceExtent(id=extent, name=NAMES[extent], status=[status])
                for extent, status in EXTENT_STATUS.items()
            ]
        ),
        placement_policy=PlacementPolicy(type="DataLocality"),
        capacity_tier=CapacityTier(
            is_enabled=True,
            extents=[CapacityExtent(id=R08)],
            copy_policy_enabled=False,
            move_policy_enabled=True,
            operational_restore_period_days=14,
            encryption=StorageEncryption(is_enabled=True),
        ),
        archive_tier=ArchiveTier(is_enabled=False),
    )


SCALE_OUT_REPOSITORIES: list[ScaleOutRepository] = [scale_out_repository()]
"""``GET /api/v1/backupInfrastructure/scaleOutRepositories``."""


def is_low_on_space(state: RepositoryState) -> bool:
    """vbr-mcp's heuristic: under 10% free or under 100 GB free, whichever trips first; unbounded storage never."""
    if state.capacity_gb <= 0 or state.free_gb < 0:
        return False
    return state.free_gb / state.capacity_gb < 0.10 or state.free_gb < 100
