# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""The Instant Recovery of web-02 as the G3 cases mock it: its mount, and the state G3-17 leaves for G3-18 and G3-19.

web-02, deleted from vCenter by accident, runs from last night's point on esx01, published to its original place and
not powered on; an admin started it at 08:10 (session S-ID21).
"""

import stand
from stand import IR_MOUNTS
from stand.ids import J01, S_ID21, at
from stand.inventory import ESX01
from stand.sessions import ADMIN
from vbr_models.instant_recovery import InstantRecoveryMount, InstantRecoverySpec, MountState, SecureRestore

WEB_02 = stand.protected.BY_NAME["web-02"]
LAST_NIGHT = stand.protected.points_of(WEB_02.name)[0]  # 10-06 22:12
RECOVERED_AT = at(7, 8, 10)
MOUNT_ID = S_ID21
"""The mount's id is its Instant Recovery session's: VBR lists the mounts of the running Instant Recovery sessions and
finds a mount by its session's id (RestViIrManager.GetInstantViVMRecoveryMounts, CRecoveryMountBuilder), so the id the
start returns is the mount id."""


def mount(
    state: MountState,
    *,
    power_up: bool | None = False,
    nics_enabled: bool | None = True,
    antivirus_scan_enabled: bool | None = False,
    yara_scan_enabled: bool | None = False,
    reason: str | None = None,
) -> InstantRecoveryMount:
    """web-02's mount in ``state``: published from last night's point to its original place on esx01."""
    return InstantRecoveryMount(
        id=MOUNT_ID,
        session_id=S_ID21,
        state=state,
        spec=InstantRecoverySpec(
            restore_point_id=LAST_NIGHT.id,
            type="OriginalLocation",
            secure_restore=SecureRestore(
                antivirus_scan_enabled=antivirus_scan_enabled, yara_scan_enabled=yara_scan_enabled
            ),
            nics_enabled=nics_enabled,
            power_up=power_up,
            reason=reason,
        ),
        vm_name=WEB_02.name,
        job_name="Daily-VMs",
        restore_point_date=LAST_NIGHT.creation_time,
        host_name=ESX01.name,
        error_message="",
    )


IR_SESSION = stand.sessions.session(
    21,
    WEB_02.name,
    RECOVERED_AT,
    at(7, 8, 13, 40),
    "Success",
    session_type="InstantRecovery",
    job_id=J01,
    platform="VMware",
    initiated_by=ADMIN,
).model_copy(update={"resource_id": MOUNT_ID, "resource_reference": f"{IR_MOUNTS}/{MOUNT_ID}"})
"""The admin's Instant Recovery of web-02 at 08:10, over by the time the cases ask."""

MOUNTED = mount("Mounted")
