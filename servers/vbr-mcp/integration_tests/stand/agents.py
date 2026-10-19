# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""Agent protection groups (1.14): ``/agents/protectionGroups`` and what each discovered.

``discoveredEntities`` is for the Veeam Backup Administrator role only. laptop-fin-01 has been offline since its
last backup on 10-01: its ``lastConnected`` is the end of that run, so the two agree.
"""

from datetime import timedelta
from uuid import UUID

from stand.ids import AGENT_CREDENTIALS, PG01, PG02, T0, at, mnemonic
from vbr_models.protection_groups import (
    ActiveDirectoryObjectContainer,
    ADDomain,
    ADObject,
    ADObjectsProtectionGroup,
    ADObjectsProtectionGroupCredential,
    DiscoveredCluster,
    DiscoveredComputer,
    DiscoveredEntity,
    IndividualComputerContainer,
    IndividualComputersProtectionGroup,
    ProtectionGroup,
)

LAB_DOMAIN = "lab.local"
AGENT_VERSION = "13.1.0.1810"  # the Veeam Agent for Windows that ships with VBR 13.1: no upgrade pending
OLD_AGENT_VERSION = "6.3.2.1205"
FIN01_LAST_CONNECTED = at(1, 12, 31, 20)
"""When laptop-fin-01 was last seen: as its backup of 10-01 ended, about six days before T0."""

LAPTOPS = ("laptop-hr-01", "laptop-hr-02", "laptop-fin-01")
"""The computers of the laptops protection group, which Agent-Laptops backs up."""

PG_LAPTOPS = IndividualComputersProtectionGroup(
    id=PG01,
    name="PG-Laptops",
    description="",
    is_disabled=False,
    computers=[
        IndividualComputerContainer(
            host_name=name, connection_type="PermanentCredentials", credentials_id=AGENT_CREDENTIALS
        )
        for name in LAPTOPS
    ],
)

PG_SERVERS = ADObjectsProtectionGroup(
    id=PG02,
    name="PG-Servers",
    description="",
    is_disabled=False,
    active_directory=ActiveDirectoryObjectContainer(
        domain_controller_settings=ADDomain(
            id=LAB_DOMAIN,
            name=LAB_DOMAIN,
            server_name="dc01.lab.local",
            port=389,
            credentials_id=str(AGENT_CREDENTIALS),
        ),
        objects=[
            ADObject(
                id="OU=Servers,DC=lab,DC=local",
                full_name="lab.local/Servers",
                domain_id=LAB_DOMAIN,
                distinguished_name="OU=Servers,DC=lab,DC=local",
                type="OrganizationUnit",
            )
        ],
    ),
    credentials=ADObjectsProtectionGroupCredential(
        master_connection_type="PermanentCredentials",
        master_credentials_id=str(AGENT_CREDENTIALS),
        use_custom_credentials=False,
    ),
)

PROTECTION_GROUPS: list[ProtectionGroup] = [PG_LAPTOPS, PG_SERVERS]
"""``GET /api/v1/agents/protectionGroups``."""


def computer(number: int, name: str, group: UUID, **state: object) -> DiscoveredComputer:
    """A computer a group discovered, with its agent's install state (``state``: the entity's fields)."""
    return DiscoveredComputer.model_validate({
        "id": mnemonic("81000000", number),
        "name": name,
        "parent_id": group,
        "protection_group_id": group,
        "ip_addresses": [f"10.0.30.{10 + number}"],
        "object_id": mnemonic("82000000", number),
        "plugins": [],
        "is_trusted": True,
        **state,
    })


DISCOVERED_ENTITIES: dict[UUID, list[DiscoveredEntity]] = {
    PG01: [
        computer(1, "laptop-hr-01", PG01, state="Online", agent_status="Installed", agent_version=AGENT_VERSION,
                 driver_status="Installed", last_connected=T0 - timedelta(minutes=40), operating_system="Windows11"),
        computer(2, "laptop-hr-02", PG01, state="Online", agent_status="UpgradeRequired", agent_version=OLD_AGENT_VERSION,
                 driver_status="UpgradeAvailable", last_connected=T0 - timedelta(hours=2), operating_system="Windows10"),
        computer(3, "laptop-fin-01", PG01, state="Offline", agent_status="Installed", agent_version=AGENT_VERSION,
                 driver_status="Installed", last_connected=FIN01_LAST_CONNECTED, operating_system="Windows11"),
    ],
    PG02: [
        computer(4, "srv-app-01", PG02, state="Online", agent_status="NotInstalled", driver_status="NotInstalled",
                 last_connected=None, operating_system="WindowsServer2022"),
        computer(5, "srv-app-02", PG02, state="Online", agent_status="Installed", agent_version=AGENT_VERSION,
                 driver_status="InstalledRebootRequired", reboot_required=True, last_connected=T0 - timedelta(minutes=30),
                 operating_system="WindowsServer2022"),
        DiscoveredCluster(id=mnemonic("81000000", 6), name="SQLCLUSTER01", parent_id=PG02, protection_group_id=PG02),
    ],
}  # fmt: skip
"""``GET /api/v1/agents/protectionGroups/{id}/discoveredEntities``, by group."""
