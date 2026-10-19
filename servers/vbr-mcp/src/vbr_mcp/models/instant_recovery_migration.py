# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""Request-body parts of `migrate_instant_recovery_vsphere_vm`."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from vbr_mcp.models.shared import VmwareObjectModel


class ViVMDiskModel(BaseModel):
    """VMware vSphere virtual machine disk."""

    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[int, Field(description="ID (device key) of the disk on the Instant Recovery VM, e.g. `2000`.")]
    name: Annotated[
        str | None,
        Field(
            description="Name of the disk file. Leave it out: the tool fills in the IR VM's current name, which "
            "changes with every snapshot (e.g. `vm-000001.vmdk` -> `vm-000002.vmdk` after a failed attempt)."
        ),
    ] = None
    capacity: Annotated[float | None, Field(description="Capacity of the disk, in bytes.")] = None


class ViVMQuickMigrationDatastoreSpec(BaseModel):
    """Destination datastore."""

    model_config = ConfigDict(
        extra="forbid",
    )
    disk: ViVMDiskModel
    datastore: VmwareObjectModel
    diskType: Annotated[
        Literal["Source", "Thick", "Thin", "ThickEagerZeroed"] | None,
        Field(description="Disk provisioning type for the recovered VM."),
    ] = None


class ViVMQuickMigrationDatastoresSpec(BaseModel):
    """Destination datastore."""

    model_config = ConfigDict(
        extra="forbid",
    )
    defaultDatastore: VmwareObjectModel | None = None
    configurationFileDatastore: VmwareObjectModel | None = None
    diskMappings: Annotated[
        list[ViVMQuickMigrationDatastoreSpec] | None,
        Field(description="Array of disks and their locations in the target datastore."),
    ] = None
