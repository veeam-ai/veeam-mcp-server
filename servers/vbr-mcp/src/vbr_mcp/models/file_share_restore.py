# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""Request-body parts of `restore_file_share`."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from vbr_mcp.models.shared import UnstructuredDataColdStorageRetrievalSettings


class UnstructuredDataShareRestoreDestinationModel(BaseModel):
    """Target for restoring entire file share."""

    model_config = ConfigDict(
        extra="forbid",
    )
    unstructuredDataServerId: Annotated[
        UUID | None,
        Field(
            description="ID of the target file share. To get the ID, run the [Get All Unstructured Data Servers](#/Inventory-Browser/GetAllUnstructuredDataServers) request."
        ),
    ] = None
    restoreToBackupServer: Annotated[
        bool | None,
        Field(description="If `true`, the contents of the file share will be restored to the backup server."),
    ] = None
    path: Annotated[
        str | None,
        Field(description="Path to the folder on the selected file share to which files will be restored."),
    ] = None
    preserveHierarchy: Annotated[
        bool | None,
        Field(
            description="If `true`, the folder hierarchy of the original file share will be kept in the new location."
        ),
    ] = None


class UnstructuredDataShareRestoreOptionsModel(BaseModel):
    """Restore options for restoring entire file share."""

    model_config = ConfigDict(
        extra="forbid",
    )
    rollback: Annotated[
        bool | None,
        Field(description="If `true`, the file share will be rolled back to the state as of a specific restore point."),
    ] = None
    overwriteMode: Annotated[
        Literal["Skip", "ReplaceOlder", "ReplaceNewer", "Overwrite"] | None,
        Field(description="Overwrite mode."),
    ] = None
    restorePermissions: Annotated[
        bool | None,
        Field(
            description="If `true`, the restored files will keep their original ownership and security permissions. If `false`, Veeam Backup & Replication will change the security settings. The user account under which the Veeam Backup Service runs will be set as the owner of the restored objects."
        ),
    ] = None
    coldStorageRetrievalSettings: UnstructuredDataColdStorageRetrievalSettings | None = None
