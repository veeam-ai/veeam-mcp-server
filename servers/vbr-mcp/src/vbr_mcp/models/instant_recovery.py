# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""Request-body parts of `start_instant_recovery_vsphere_vm`."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from vbr_mcp.models.shared import VmwareObjectModel


class IPv4SettingsModel(BaseModel):
    """IPv4 settings."""

    model_config = ConfigDict(
        extra="forbid",
    )
    ipAddress: Annotated[str | None, Field(description="Helper appliance IP address.")] = None
    subnetMask: Annotated[
        str | None,
        Field(description="Mask of a subnet where the helper appliance must reside."),
    ] = None
    defaultGateway: Annotated[str | None, Field(description="Default gateway address.")] = None
    preferredDNSServer: Annotated[str | None, Field(description="Preferred DNS server address.")] = None
    alternateDNSServer: Annotated[str | None, Field(description="Alternate DNS server address.")] = None


class IPv6SettingsModel(BaseModel):
    """IPv6 settings."""

    model_config = ConfigDict(
        extra="forbid",
    )
    ipAddress: Annotated[str | None, Field(description="Helper appliance IP address.")] = None
    prefixLength: Annotated[int | None, Field(description="Subnet prefix length.")] = None
    defaultGateway: Annotated[str | None, Field(description="Default gateway address.")] = None
    preferredDNSServer: Annotated[str | None, Field(description="Preferred DNS server address.")] = None
    alternateDNSServer: Annotated[str | None, Field(description="Alternate DNS server address.")] = None


class ObjectRestorePointNetworkInfoModel(BaseModel):
    """Details on backup object network interfaces.

    A row of `POST /api/v1/restorePoints/{id}/networkInfo`, passed as-is: VBR matches its `id`, not an inventory
    `objectId`.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[str, Field(description="ID of the network interface.")]
    name: Annotated[str, Field(description="Name of the network interface.")]


class IPv4ApplianceSettingsModel(BaseModel):
    """IPv4 address settings."""

    model_config = ConfigDict(
        extra="forbid",
    )
    obtainIPAutomatically: Annotated[
        bool | None,
        Field(description="If `true`, the IPv4 address is obtained automatically."),
    ] = None
    obtainDNSAutomatically: Annotated[
        bool | None,
        Field(description="If `true`, the DNS server address is obtained automatically."),
    ] = None
    ipAddress: IPv4SettingsModel | None = None


class IPv6ApplianceSettingsModel(BaseModel):
    """IPv6 address settings."""

    model_config = ConfigDict(
        extra="forbid",
    )
    obtainIPAutomatically: Annotated[
        bool | None,
        Field(description="If `true`, the IPv6 address is obtained automatically."),
    ] = None
    obtainDNSAutomatically: Annotated[
        bool | None,
        Field(description="If `true`, the DNS server address is obtained automatically."),
    ] = None
    ipAddress: IPv6SettingsModel | None = None


class InstantViVMCustomizedRecoveryDatastoreSpec(BaseModel):
    """Datastore that keeps redo logs with changes that take place while a VM is running from a backup. To get a datastore object, run the [Get Inventory Objects](#/Inventory-Browser/GetInventoryObjects) request."""

    model_config = ConfigDict(
        extra="forbid",
    )
    redirectEnabled: Annotated[
        bool | None,
        Field(description="If `true`, redo logs are redirected to `cacheDatastore`."),
    ] = None
    cacheDatastore: VmwareObjectModel | None = None


class InstantViVMRecoveryHelperApplianceSpec(BaseModel):
    """Helper appliance."""

    model_config = ConfigDict(
        extra="forbid",
    )
    productionNetwork: VmwareObjectModel
    ipv4Address: IPv4ApplianceSettingsModel | None = None
    ipv6Address: IPv6ApplianceSettingsModel | None = None


class InstantViVMRecoveryNetworkMappingSpec(BaseModel):
    """Network mapping."""

    model_config = ConfigDict(
        extra="forbid",
    )
    sourceNetwork: ObjectRestorePointNetworkInfoModel
    targetNetwork: VmwareObjectModel


class InstantViVMCustomizedRecoveryDestinationSpec(BaseModel):
    """Destination where the recovered VM resides. To get objects of the destination host, folder and resource pool, run the [Get Inventory Objects](#/Inventory-Browser/GetInventoryObjects) request."""

    model_config = ConfigDict(
        extra="forbid",
    )
    restoredVmName: Annotated[str | None, Field(description="Restored VM name.")] = None
    destinationHost: VmwareObjectModel | None = None
    folder: VmwareObjectModel | None = None
    resourcePool: VmwareObjectModel | None = None
    helperAppliance: InstantViVMRecoveryHelperApplianceSpec | None = None
    biosUuidPolicy: Annotated[
        Literal["Preserve", "GenerateNew"] | None,
        Field(description="BIOS UUID policy for the restored VM."),
    ] = None
    enableClusterWideMount: Annotated[
        bool | None,
        Field(
            description="If `true`, Veeam Backup & Replication mounts the vPowerNFS datastore to all ESXi hosts in the cluster specified in `destinationHost`."
        ),
    ] = None


class InstantViVMOtherPlatformRecoveryDestinationSpec(BaseModel):
    """Destination where the recovered VM resides. To get objects of the destination host, folder and resource pool, use the [Get Inventory Objects](#/Inventory-Browser/GetInventoryObjects) request."""

    model_config = ConfigDict(
        extra="forbid",
    )
    restoredVmName: Annotated[str | None, Field(description="Restored VM name.")] = None
    destinationHost: VmwareObjectModel
    folder: VmwareObjectModel | None = None
    resourcePool: VmwareObjectModel | None = None
    networkMapping: Annotated[
        list[InstantViVMRecoveryNetworkMappingSpec] | None,
        Field(description="Array of network mapping rules between the source and target networks."),
    ] = None
    helperAppliance: InstantViVMRecoveryHelperApplianceSpec | None = None
    biosUuidPolicy: Annotated[
        Literal["Preserve", "GenerateNew"] | None,
        Field(description="BIOS UUID policy for the restored VM."),
    ] = None
    enableClusterWideMount: Annotated[
        bool | None,
        Field(
            description="If `true`, Veeam Backup & Replication mounts the vPowerNFS datastore to all ESXi hosts in the cluster specified in `destinationHost`."
        ),
    ] = None
