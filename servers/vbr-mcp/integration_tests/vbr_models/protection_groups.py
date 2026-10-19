# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""``/api/v1/agents/protectionGroups``, ``/agents/protectionGroups/{id}/discoveredEntities``."""

from typing import Literal
from uuid import UUID

from vbr_models import VbrDateTime, VbrModel

ConnectionType = Literal["PermanentCredentials", "SingleUseCredentials", "Certificate"]
AgentStatus = Literal[
    "Installed", "NotInstalled", "UpgradeRequired", "Failed", "UnsupportedOperatingSystem", "Unknown", "NotInitialized"
]
DriverStatus = Literal[
    "Unknown",
    "Installed",
    "NotInstalled",
    "Stopped",
    "Failed",
    "UpgradeAvailable",
    "InstalledRebootRequired",
    "NotInstalledRebootRequired",
]
OperatingSystem = Literal["Windows10", "Windows11", "WindowsServer2019", "WindowsServer2022", "Linux"]
"""The ``EOperatingSystem`` values the cases use."""


class IndividualComputerContainer(VbrModel):
    """``IndividualComputerContainerModel``: one computer added to a protection group by name."""

    host_name: str
    connection_type: ConnectionType
    credentials_id: UUID | None = None


class IndividualComputersProtectionGroup(VbrModel):
    """``IndividualComputersProtectionGroupModel``: a group of computers listed one by one."""

    id: UUID
    name: str
    description: str
    type: Literal["IndividualComputers"] = "IndividualComputers"
    is_disabled: bool
    computers: list[IndividualComputerContainer]


class ADDomain(VbrModel):
    """``ADDomainModel``: the domain an Active Directory protection group browses."""

    id: str
    name: str
    server_name: str
    port: int | None = None
    credentials_id: str


class ADObject(VbrModel):
    """``ADObjectModel``: one Active Directory object a protection group includes."""

    id: str
    full_name: str
    domain_id: str
    distinguished_name: str
    type: Literal["Computer", "Cluster", "OrganizationUnit", "Container", "Group", "Domain"]


class ActiveDirectoryObjectContainer(VbrModel):
    """``ActiveDirectoryObjectContainerModel``."""

    domain_controller_settings: ADDomain
    objects: list[ADObject]


class ADObjectsProtectionGroupCredential(VbrModel):
    """``ADObjectsProtectionGroupCredentialModel``."""

    master_connection_type: ConnectionType
    master_credentials_id: str | None = None
    use_custom_credentials: bool


class ADObjectsProtectionGroup(VbrModel):
    """``ADObjectsProtectionGroupModel``: a group of computers found through Active Directory."""

    id: UUID
    name: str
    description: str
    type: Literal["ADObjects"] = "ADObjects"
    is_disabled: bool
    active_directory: ActiveDirectoryObjectContainer
    credentials: ADObjectsProtectionGroupCredential


ProtectionGroup = IndividualComputersProtectionGroup | ADObjectsProtectionGroup
"""``ProtectionGroupModel``, an item of ``GET /api/v1/agents/protectionGroups``, as far as the cases use it."""


class DiscoveredComputer(VbrModel):
    """``DiscoveredComputerEntityModel``: a computer a protection group discovered, with its agent install state."""

    id: UUID
    name: str
    parent_id: UUID
    protection_group_id: UUID
    type: Literal["Computer"] = "Computer"
    state: Literal["Unknown", "Online", "Offline"]
    agent_status: AgentStatus
    agent_version: str | None = None
    driver_status: DriverStatus
    driver_version: str | None = None
    reboot_required: bool | None = None
    ip_addresses: list[str]
    last_connected: VbrDateTime | None = None
    operating_system: OperatingSystem | None = None
    object_id: UUID
    plugins: list[dict[str, str]]
    """``DiscoveredComputerPluginModel`` items; the cases' computers run no application plug-ins."""
    is_trusted: bool


class DiscoveredCluster(VbrModel):
    """``DiscoveredClusterEntityModel``: a cluster, a container of computers rather than a computer of its own."""

    id: UUID
    name: str
    parent_id: UUID
    protection_group_id: UUID
    type: Literal["Cluster"] = "Cluster"


DiscoveredEntity = DiscoveredComputer | DiscoveredCluster
"""``DiscoveredEntityModel``, an item of ``GET /api/v1/agents/protectionGroups/{id}/discoveredEntities``."""
