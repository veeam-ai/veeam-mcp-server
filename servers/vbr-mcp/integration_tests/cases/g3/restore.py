# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""The restores of the G3 cases as VBR performs them: the session a restore starts, and VBR's refusals."""

from typing import Any

import stand
from cases import Environment
from stand.ids import FIRST_G3_SESSION
from vbr_mock.markers import VbrAction, VbrError
from vbr_models.sessions import Session

VM_RESTORE_PATH = "/api/v1/restore/vmRestore/vSphere"
EXISTS = "The original VM still exists. Add overwrite: true if you want to overwrite the original VM"
"""VBR's own message for a restore in place without overwrite (RestEntireViVmRestoreSpecBuilders.cs, test plan 0.3)."""


def unknown_point(body: Any) -> VbrError | None:
    """VBR's refusal of a restore whose body names a restore point it does not have; ``None`` for a known one."""
    point = body.get("restorePointId", "") if isinstance(body, dict) else ""
    if str(point).lower() not in stand.protected.POINT_IDS:
        return VbrError(status_code=404, message="Restore point was not found.")
    return None


def vm_restore_session(vm_name: str) -> Session:
    """The session an entire-VM restore of ``vm_name`` starts: the first one a G3 case's action starts."""
    return stand.sessions.started(FIRST_G3_SESSION, vm_name, session_type="RestoreVm", platform="VMware")


def _reject_vm_restore(body: Any) -> VbrError | None:
    """VBR's checks of an entire-VM restore, as far as the cases need them.

    The VM still exists in vCenter, so a restore to its original place must agree to replace it.
    """
    if (unknown := unknown_point(body)) is not None:
        return unknown
    if body.get("type") == "OriginalLocation" and not body.get("overwrite"):
        return VbrError(status_code=400, message=EXISTS)
    return None


def vm_restore(session: Session) -> Environment:
    """The entire-VM restore, which VBR answers with ``session``: the session reads list it from then on."""
    return {
        VM_RESTORE_PATH: VbrAction(
            response=session,
            reject=_reject_vm_restore,
            effects={
                f"/api/v1/sessions/{session.id}": session,
                "/api/v1/sessions": [session, *stand.sessions.SESSIONS],
            },
        ),
    }
