# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""Request-body parts of `restore_object_storage`."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from vbr_mcp.models.shared import UnstructuredDataColdStorageRetrievalSettings


class UnstructuredDataOSRestoreDestinationModel(BaseModel):
    """Target for restoring entire object storage bucket or container."""

    model_config = ConfigDict(
        extra="forbid",
    )
    unstructuredDataServerId: Annotated[
        UUID | None,
        Field(
            description="Unstructured data server ID. To get the ID, run the [Get All Unstructured Data Servers](#/Inventory-Browser/GetAllUnstructuredDataServers) request."
        ),
    ] = None
    restoreToBackupServer: Annotated[
        bool | None,
        Field(description="If `true`, the contents of the bucket or container will be restored to the backup server."),
    ] = None
    path: Annotated[
        str | None,
        Field(description="Path to the folder on the selected storage to which files will be restored."),
    ] = None
    newBucketName: Annotated[
        str | None,
        Field(description="Name for the bucket or container following naming rules for the selected object storage."),
    ] = None
    regionId: Annotated[str | None, Field(description="ID of a region where the storage is located.")] = None


class UnstructuredDataOSRestoreOptionsModel(BaseModel):
    """Restore options for restoring entire object storage bucket or container."""

    model_config = ConfigDict(
        extra="forbid",
    )
    rollback: Annotated[
        bool | None,
        Field(
            description="If `true`, the bucket or container will be rolled back to the state as of a specific restore point."
        ),
    ] = None
    overwriteMode: Annotated[
        Literal["Skip", "ReplaceOlder", "ReplaceNewer", "Overwrite"] | None,
        Field(description="Overwrite mode."),
    ] = None
    overwriteBucketAttributes: Annotated[
        bool | None,
        Field(description="If `true`, bucket attributes will be overwritten."),
    ] = None
    coldStorageRetrievalSettings: UnstructuredDataColdStorageRetrievalSettings | None = None
