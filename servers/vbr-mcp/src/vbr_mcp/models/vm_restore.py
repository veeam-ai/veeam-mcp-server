# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""Request-body parts of `restore_vsphere_vm`."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from vbr_mcp.models.shared import VmwareObjectModel


class RestoreProxySpec(BaseModel):
    """Backup proxies for VM data transport."""

    model_config = ConfigDict(
        extra="forbid",
    )
    autoSelectEnabled: Annotated[
        bool,
        Field(
            description="If `true`, Veeam Backup & Replication detects backup proxies that are connected to the source datastore and automatically assigns optimal proxy resources for processing VM data."
        ),
    ]
    proxyIds: Annotated[list[UUID] | None, Field(description="Array of backup proxy IDs.")] = None


class RestoreTargetDatastoreSpec(BaseModel):
    """Destination datastore."""

    model_config = ConfigDict(
        extra="forbid",
    )
    diskName: Annotated[
        str,
        Field(
            description="Disk as VBR names it in the restore point: the `name` of a row from "
            "`GET /api/v1/restorePoints/{id}/disks`. VBR matches it as an ID - not the .vmdk file name, "
            "device key or controller slot."
        ),
    ]
    datastore: VmwareObjectModel
    diskType: Annotated[
        Literal["Source", "Thick", "Thin", "ThickEagerZeroed"] | None,
        Field(description="Disk provisioning type for the recovered VM."),
    ] = None


class RestoreTargetDatastoresSpec(BaseModel):
    """Destination datastore."""

    model_config = ConfigDict(
        extra="forbid",
    )
    defaultDatastore: VmwareObjectModel | None = None
    configurationFileDatastore: VmwareObjectModel | None = None
    diskMappings: Annotated[
        list[RestoreTargetDatastoreSpec] | None,
        Field(description="Array of disks and their locations in the target datastore."),
    ] = None


class RestoreTargetFolderSpec(BaseModel):
    """Destination VM folder."""

    model_config = ConfigDict(
        extra="forbid",
    )
    vmName: Annotated[
        str | None,
        Field(
            description="Name of the restored VM. Note that if you do not specify a value for this property, Veeam Backup & Replication will use the original VM name."
        ),
    ] = None
    folder: VmwareObjectModel
    restoreVmTags: Annotated[
        bool | None,
        Field(
            description="If `true`, Veeam Backup & Replication restores tags that were assigned to the original VMs, and assigns them to the restored VMs."
        ),
    ] = None


class RestoreTargetNetworkMappingModel(BaseModel):
    """Network mapping rule."""

    model_config = ConfigDict(
        extra="forbid",
    )
    sourceNetwork: VmwareObjectModel
    targetNetwork: VmwareObjectModel


class RestoreTargetNetworkSpec(BaseModel):
    """Network to which the restored VM will be connected. To get a network object, run the [Get Inventory Objects](#/Inventory-Browser/GetInventoryObjects) request."""

    model_config = ConfigDict(
        extra="forbid",
    )
    networks: Annotated[
        list[RestoreTargetNetworkMappingModel],
        Field(
            description="Array of network mapping rules. To get a network object, run the [Get Inventory Objects](#/Inventory-Browser/GetInventoryObjects) request.",
            min_length=1,
        ),
    ]
    disconnected: Annotated[
        bool | None,
        Field(description="If `true`, the restored VMs are not connected to any virtual network."),
    ] = None
