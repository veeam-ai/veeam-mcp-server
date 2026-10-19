# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

r"""NAS and object storage sources (1.15): ``/inventory/unstructuredDataServers`` and each one by id.

VBR requires backup proxies and a cache repository for every source (swagger ``SMBShareServerProcessingModel`` and
its NFS and S3 siblings: ``backupProxies`` and ``cacheRepositoryId`` are required), and the console does not save a
share that needs credentials without them. So no source here is broken on its own: a source can only be blocked by
the state of what it uses - a hand-picked proxy that cannot take tasks, a cache repository that is offline or full -
which ``list_unstructured_data_servers`` does not show and a case changes (G2-13). ``\\fs01\finance`` (NAS-Finance)
and the Lab AWS account (S3-Docs) are the sources jobs use; ``\\fs01\hr`` and the NFS export are in no job. No source
has an online state.
"""

from stand.ids import AWS_CREDENTIALS, N01, N02, N03, N04, R01, R03, SHARE_CREDENTIALS
from vbr_models.unstructured_data import (
    AmazonS3Server,
    AmazonS3ServerAccount,
    BackupProxiesSettings,
    NfsShareServer,
    SmbShareServer,
    SourceProcessing,
    UnstructuredDataServer,
)

AUTO_PROXIES = BackupProxiesSettings(auto_select_enabled=True)

UNSTRUCTURED_DATA_SERVERS: list[UnstructuredDataServer] = [
    SmbShareServer(
        id=N01,
        name="\\\\fs01\\finance",
        path="\\\\fs01\\finance",
        access_credentials_required=True,
        access_credentials_id=SHARE_CREDENTIALS,
        processing=SourceProcessing(
            backup_proxies=AUTO_PROXIES, cache_repository_id=R01, backup_io_control_level="Medium"
        ),
    ),
    SmbShareServer(
        id=N02,
        name="\\\\fs01\\hr",
        path="\\\\fs01\\hr",
        access_credentials_required=True,
        access_credentials_id=SHARE_CREDENTIALS,
        # its cache on the branch office's SMB repository, next to the HR team's share
        processing=SourceProcessing(
            backup_proxies=AUTO_PROXIES, cache_repository_id=R03, backup_io_control_level="Medium"
        ),
    ),
    NfsShareServer(
        id=N03,
        name="nfs01.lab.local:/exports/eng",
        path="nfs01.lab.local:/exports/eng",
        processing=SourceProcessing(
            backup_proxies=AUTO_PROXIES, cache_repository_id=R01, backup_io_control_level="Medium"
        ),
    ),
    AmazonS3Server(
        id=N04,
        account=AmazonS3ServerAccount(
            friendly_name="Lab AWS", credentials_id=AWS_CREDENTIALS, region_type="Global", region_id="eu-central-1"
        ),
        processing=SourceProcessing(
            backup_proxies=AUTO_PROXIES, cache_repository_id=R01, backup_io_control_level="Medium"
        ),
    ),
]
"""N01 is NAS-Finance's share, N04 the account S3-Docs reads the ``lab-docs-prod`` bucket from; N02 and N03 are
registered but in no job."""
