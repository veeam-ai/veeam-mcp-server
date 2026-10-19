# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""Request-body parts and VBR enum values shared by several tools."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

# `ESessionResult`: a session/task/job-run outcome. `None` means not finished (or never run).
SessionResult = Literal["None", "Success", "Warning", "Failed"]

# `ESuspiciousActivitySeverity`: malware status of a restore point / severity of a malware event. `Informative` is not a positive detection.
MalwareStatus = Literal["Clean", "Suspicious", "Infected", "Informative"]


class UnstructuredDataColdStorageRetrievalSettings(BaseModel):
    """Settings for retrieving data from cold storages."""

    model_config = ConfigDict(
        extra="forbid",
    )
    coldStorageRetrievalMode: Annotated[
        Literal[
            "AmazonBulk",
            "AmazonStandard",
            "AmazonExpedited",
            "AzureStandardPriority",
            "AzureHighPriority",
        ]
        | None,
        Field(description="Cold Storage retrieval mode"),
    ] = None
    availabilityPeriodDays: Annotated[
        int | None,
        Field(
            description="Number of days, the retrieved files should be kept available. If no value is specified, the files will only be retrieved as long as necessary.",
            ge=1,
            le=100,
        ),
    ] = None
    sendNotificationMail: Annotated[
        bool,
        Field(description="Indicates whether to send notification email when the retrieval is about to expire."),
    ] = False
    notificationHours: Annotated[
        int | None,
        Field(
            description="Number of hours before the retrieval expires to send a notification.",
            ge=1,
        ),
    ] = None


class VmwareObjectModel(BaseModel):
    """VMware vSphere object.

    Only the fields that identify the object are modeled. Extra fields are ignored rather than forbidden, so an
    inventory row (which also carries response-only data like `size` or `metadata`) can be passed as-is.
    """

    model_config = ConfigDict(
        extra="ignore",
    )
    platform: Annotated[Literal["VSphere"], Field(description="Platform type of inventory object.")] = "VSphere"
    hostName: Annotated[
        str,
        Field(description="Name of the VMware vSphere server that hosts the object."),
    ]
    name: Annotated[str, Field(description="Name of the VMware vSphere object.")]
    type: Annotated[
        Literal[
            "Unknown",
            "VirtualMachine",
            "vCenterServer",
            "Datacenter",
            "Cluster",
            "Host",
            "ResourcePool",
            "Folder",
            "Datastore",
            "DatastoreCluster",
            "StoragePolicy",
            "Template",
            "ComputeResource",
            "VirtualApp",
            "Tag",
            "Category",
            "Multitag",
            "Network",
            "DVSNetwork",
            "Disk",
            "SharedDisk",
        ],
        Field(
            description="Type of the VMware vSphere object.<p> Note that inventory objects with multiple tags (*Multitag* type) can only be added in the Veeam Backup & Replication UI or PowerShell."
        ),
    ]
    objectId: Annotated[
        str | None,
        Field(
            description="ID of the VMware vSphere object. The parameter is required for all VMware vSphere objects except vCenter Servers and standalone ESXi hosts."
        ),
    ] = None
    urn: Annotated[str | None, Field(description="Uniform Resource Name (URN) of the object.")] = None
