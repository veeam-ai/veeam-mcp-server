# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""``/api/v1/restore/instantRecovery/vSphere/vm``: vSphere Instant Recovery mounts."""

from typing import Literal
from uuid import UUID

from vbr_models import VbrDateTime, VbrModel

MountState = Literal["Failed", "Mounting", "Mounted", "Dismounting"]
"""``EInstantRecoveryMountState``."""


class SecureRestore(VbrModel):
    """``SecureRestoreSpec``."""

    antivirus_scan_enabled: bool | None = None
    yara_scan_enabled: bool | None = None


class InstantRecoverySpec(VbrModel):
    """``InstantViVMRecoverySpec``: how the mount was started, as far as the cases use it."""

    restore_point_id: UUID
    type: Literal["OriginalLocation", "Customized", "OtherPlatform"]
    secure_restore: SecureRestore
    nics_enabled: bool | None = None
    power_up: bool | None = None
    reason: str | None = None


class InstantRecoveryMount(VbrModel):
    """``InstantViVMRecoveryMount``, an item of ``GET /api/v1/restore/instantRecovery/vSphere/vm``.

    ``id`` is the mount's own id, which the migrate and unmount actions take; ``sessionId`` is the restore session
    that created it, and is what the start action answers with.
    """

    id: UUID
    session_id: UUID
    state: MountState
    spec: InstantRecoverySpec
    vm_name: str
    job_name: str
    restore_point_date: VbrDateTime
    host_name: str | None = None
    error_message: str | None = None
