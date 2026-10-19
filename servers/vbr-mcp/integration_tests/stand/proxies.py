# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""Proxies, WAN accelerators and managed servers (1.6).

Only Proxy-01 can take tasks. Proxy-02 is offline and Proxy-03 disabled, and both have out-of-date components, so
neither would take tasks even if it were back. vbr-mcp's dedicated tools list no managed servers: their ids show as the
``hostId`` of a proxy, a repository or a WAN accelerator, and VBR's own list (``MANAGED_SERVER_LIST``) is read with
``api_get``, which a case mocks when it needs it.
"""

from typing import Literal
from uuid import UUID

from stand.ids import M01, M02, M03, M04, M05, M06, M07, M08, M09, M10, M11, M12, M13, P01, P02, P03, W01, W02
from vbr_models.infrastructure import (
    ManagedServer,
    Proxy,
    ProxyServer,
    ProxyState,
    ViManagedServer,
    WanAccelerator,
    WanAcceleratorCache,
    WanAcceleratorServer,
)

MANAGED_SERVERS: dict[UUID, str] = {
    M01: "vbr-lab01.lab.local",
    M02: "vcenter01.lab.local",
    M03: "prx01.lab.local",
    M04: "prx02.lab.local",
    M05: "prx03.lab.local",
    M06: "repo-win01.lab.local",
    M07: "repo-lnx01.lab.local",
    M08: "repo-sobr01.lab.local",
    M09: "repo-sobr02.lab.local",
    M10: "repo-sobr03.lab.local",
    M11: "wan01.lab.local",
    M12: "wan02.lab.local",
    M13: "dr-lnx01.lab.local",
}
"""Managed servers M01-M13, by id: their host names."""

MANAGED_SERVER_LIST: list[ManagedServer | ViManagedServer] = [
    (
        ViManagedServer(id=server_id, name=name, description="", vi_host_type="VC")
        if server_id == M02
        else ManagedServer(
            id=server_id,
            name=name,
            description="",
            type="LinuxHost" if "-lnx" in name else "WindowsHost",
            status="Unavailable" if server_id == M04 else "Available",  # prx02 is offline
        )
    )
    for server_id, name in MANAGED_SERVERS.items()
]
"""``GET /api/v1/backupInfrastructure/managedServers``: vcenter01 is the vCenter Server (``ViHost``), the rest Windows
and Linux hosts. Not a base stand route: a case whose agent needs a managed server's id from it mocks it."""


def proxy(
    id: UUID,
    name: str,
    host_id: UUID,
    transport_mode: Literal["DirectAccess", "VirtualAppliance", "Network"],
    max_task_count: int,
    *,
    is_disabled: bool,
    is_online: bool,
    is_out_of_date: bool,
) -> tuple[Proxy, ProxyState]:
    """A VMware proxy as ``/proxies`` configures it and as ``/proxies/states`` reports it."""
    host_name = MANAGED_SERVERS[host_id]
    config = Proxy(
        id=id,
        name=name,
        description="",
        type="ViProxy",
        server=ProxyServer(
            host_id=host_id,
            host_name=host_name,
            transport_mode=transport_mode,
            failover_to_network=True,
            host_to_proxy_encryption=False,
            max_task_count=max_task_count,
        ),
    )
    state = ProxyState(
        id=id,
        name=name,
        description="",
        type="ViProxy",
        host_id=host_id,
        host_name=host_name,
        is_disabled=is_disabled,
        is_online=is_online,
        is_out_of_date=is_out_of_date,
    )
    return config, state


_PROXIES = [
    proxy(P01, "Proxy-01", M03, "VirtualAppliance", 8, is_disabled=False, is_online=True, is_out_of_date=False),
    proxy(P02, "Proxy-02", M04, "Network", 4, is_disabled=False, is_online=False, is_out_of_date=True),
    proxy(P03, "Proxy-03", M05, "DirectAccess", 6, is_disabled=True, is_online=True, is_out_of_date=True),
]

PROXIES: list[Proxy] = [config for config, _ in _PROXIES]
"""``GET /api/v1/backupInfrastructure/proxies``."""

PROXY_STATES: list[ProxyState] = [state for _, state in _PROXIES]
"""``GET /api/v1/backupInfrastructure/proxies/states``."""


def _wan(id: UUID, host_id: UUID, description: str, high_bandwidth: bool, folder: str, cache_gb: int) -> WanAccelerator:
    return WanAccelerator(
        id=id,
        name=MANAGED_SERVERS[host_id],
        server=WanAcceleratorServer(
            host_id=host_id,
            description=description,
            traffic_port=6165,  # VBR's default data port between accelerators (6164 is the control port)
            streams_count=5,
            high_bandwidth_mode_enabled=high_bandwidth,
        ),
        cache=WanAcceleratorCache(cache_folder=folder, cache_size=cache_gb, cache_size_unit="GB"),
    )


WAN_ACCELERATORS: list[WanAccelerator] = [
    _wan(W01, M11, "HQ", False, "D:\\VeeamWAN", 100),  # the source of Copy-to-DR
    _wan(W02, M12, "DR site", True, "E:\\VeeamWAN", 200),  # its target
]
"""``GET /api/v1/backupInfrastructure/wanAccelerators``."""
