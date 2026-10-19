# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""``/api/v1/inventory/unstructuredDataServers``: NAS and object storage sources."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from vbr_models import VbrModel
from vbr_models.jobs import BackupProxiesSettings

BackupIOControlLevel = Literal["Lowest", "Low", "Medium", "High", "Highest"]


class SourceProcessing(VbrModel):
    """``SMBShareServerProcessingModel``, ``NFSShareServerProcessingModel``, ``AmazonS3ServerProcessingModel``.

    The three share this shape, and VBR requires both ``backupProxies`` and ``cacheRepositoryId`` in each: a source
    without a cache repository exists only in a mock, so the stand gives every source one.
    """

    backup_proxies: BackupProxiesSettings
    cache_repository_id: UUID | None = None
    backup_io_control_level: BackupIOControlLevel | None = Field(default=None, alias="backupIOControlLevel")


class SmbShareServer(VbrModel):
    """``SMBShareServerModel``: an SMB file share."""

    id: UUID
    type: Literal["SMBShare"] = "SMBShare"
    name: str | None = None
    path: str
    access_credentials_required: bool | None = None
    access_credentials_id: UUID | None = None
    processing: SourceProcessing


class NfsShareServer(VbrModel):
    """``NFSShareServerModel``: an NFS file share."""

    id: UUID
    type: Literal["NFSShare"] = "NFSShare"
    name: str | None = None
    path: str
    processing: SourceProcessing


class AmazonS3ServerAccount(VbrModel):
    """``AmazonS3ServerAccountModel``."""

    friendly_name: str
    credentials_id: UUID
    region_type: Literal["China", "Global", "Government"] | None = None
    region_id: str | None = None


class AmazonS3Server(VbrModel):
    """``AmazonS3ServerModel``: an Amazon S3 account as an object storage source. It has no ``name`` of its own."""

    id: UUID
    type: Literal["AmazonS3"] = "AmazonS3"
    account: AmazonS3ServerAccount
    processing: SourceProcessing


UnstructuredDataServer = SmbShareServer | NfsShareServer | AmazonS3Server
"""``UnstructuredDataServerModel``, as far as the cases use it."""
