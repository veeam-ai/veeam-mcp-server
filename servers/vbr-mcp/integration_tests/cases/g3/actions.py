# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""VBR's actions as several G3 cases mock them, from the base stand.

Job starts, proxy enable/disable, Scan Backup, license revokes, and the in-place state changes they share.
"""

from collections.abc import Iterable
from typing import Any
from uuid import UUID

from pydantic import BaseModel

import stand
from cases import Environment
from cases.patterns import CANNOT, any_of, near
from stand import jobs, sessions
from stand.backups import BACKUP_OBJECTS
from stand.ids import FIRST_G3_SESSION, T0
from stand.malware import YARA_RULES
from stand.protected import POINT_IDS
from stand.proxies import PROXIES, PROXY_STATES
from vbr_mock.markers import VbrAction, VbrError, VbrUpdate
from vbr_models.jobs import JobState
from vbr_models.license import InstanceLicenseWorkload
from vbr_models.sessions import PlatformName, SessionType

# ---- State an action changes: in place, so that a second action keeps what the first one did


def updated(model: type[BaseModel], key: UUID | str, **update: Any) -> VbrUpdate:
    """An effect that changes the record whose id or name is ``key`` by ``update`` (fields by Python name).

    It changes what the list route serves at that moment, so every other record stays as the earlier actions left it:
    ``stand.replace`` builds the list from the stand, and of two actions on one list the second would undo the first.
    """

    def change(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in stand.replace(map(model.model_validate, rows), key, **update)]

    return VbrUpdate(change=change)


def prepended(item: BaseModel) -> VbrUpdate:
    """An effect that puts ``item`` first in what its list route serves at that moment: a session an action started."""
    return VbrUpdate(change=lambda rows: [item.model_dump(mode="json"), *rows])


# ---- Job starts

_SESSION_KIND: dict[str, tuple[SessionType, PlatformName]] = {
    "VSphereBackup": ("BackupJob", "VMware"),
    "BackupCopy": ("BackupCopyJob", "VMware"),
    "FileBackup": ("BackupJob", "UnstructuredData"),
    "ObjectStorageBackup": ("BackupJob", "UnstructuredData"),
    "WindowsAgentBackupWorkstationPolicy": ("AgentBackup", "WindowsPhysical"),
}


NO_SYNC_CHOICE = VbrError(status_code=400, message="Please provide 'SyncRestorePoints' for Immediate Backup Copy Job.")
"""VBR's refusal to start an immediate backup copy job without the restore points to copy, ``All`` or ``Latest``
(JobsControllerImpl.cs, StartJob: checked before anything else, an active full included)."""


def _sync_choice(body: Any) -> VbrError | None:
    return None if isinstance(body, dict) and body.get("syncRestorePoints") else NO_SYNC_CHOICE


def _start(state: JobState, number: int) -> VbrAction:
    """What ``POST /jobs/{id}/start`` does to ``state``'s job.

    A running job answers with the session it runs, as VBR starts nothing new (test plan 0.3); any other job starts a
    session of its own (``number``) and reads ``Starting``, in the job states and the sessions list as the other
    actions of the run left them. An immediate backup copy job needs the choice of restore points first.
    """
    reject = _sync_choice if state.backup_copy_mode == "Immediate" else None
    if state.status == "Running" and state.session_id is not None:
        return VbrAction(response=sessions.BY_ID[state.session_id], reject=reject)
    session_type, platform = _SESSION_KIND[state.type]
    started = sessions.started(number, state.name, session_type=session_type, job_id=state.id, platform=platform)
    return VbrAction(
        response=started,
        reject=reject,
        effects={
            "/api/v1/jobs/states": updated(
                JobState,
                state.id,
                status="Starting",
                session_id=started.id,
                last_run=T0,
                progress_percent=0,
                session_progress=None,
            ),
            "/api/v1/sessions": prepended(started),
            f"/api/v1/sessions/{started.id}": started,
        },
    )


START_ACTIONS: Environment = {
    f"/api/v1/jobs/{state.id}/start": _start(state, FIRST_G3_SESSION + n) for n, state in enumerate(jobs.JOB_STATES)
}
"""Every job's start, accepted as VBR would accept it: a request that picked the wrong job would start it. Each job's
run is a session of its own, from S-ID20 on in the order of the job states."""

NOT_RUNNING = VbrError(status_code=400, message="Unable to stop the specified job: job is not currently running.")
"""VBR's refusal to stop a job that is not running."""


def refused_stops(states: Iterable[JobState]) -> Environment:
    """The stop of every job of ``states`` that is not running: VBR refuses it with ``NOT_RUNNING``."""
    return {
        f"/api/v1/jobs/{state.id}/stop": VbrAction(reject=lambda _: NOT_RUNNING)
        for state in states
        if state.status != "Running"
    }


# ---- Proxies

PROXIES_PATH = "/api/v1/backupInfrastructure/proxies"
PROXY_ACTIONS: Environment = {
    f"{PROXIES_PATH}/{proxy.id}/{action}": VbrAction(
        effects={f"{PROXIES_PATH}/states": stand.replace(PROXY_STATES, proxy.id, is_disabled=action == "disable")}
    )
    for proxy in PROXIES
    for action in ("enable", "disable")
}
"""Enable and disable of every proxy, as VBR performs them, with the state they leave behind."""

# ---- Scan Backup: POST /malwareDetection/scanBackup answers 201 with the session it starts, a SureBackup session named
# "Scan Backup" (swagger SureBackupSessionExample).

SCAN_PATH = "/api/v1/malwareDetection/scanBackup"
SCAN_SESSION = sessions.started(FIRST_G3_SESSION, "Scan Backup", session_type="SureBackup", platform="VMware")
_PAIRS = {(str(backup_id), str(obj.id)) for backup_id, objects in BACKUP_OBJECTS.items() for obj in objects}
_BACKUPS = {backup for backup, _ in _PAIRS}
_OBJECTS = {obj for _, obj in _PAIRS}
_RULES = {rule.file_name.lower() for rule in YARA_RULES}


def _refused(message: str) -> VbrError:
    return VbrError(status_code=400, message=message)


def _pair_refusal(pairs: list[Any]) -> VbrError | None:
    if not pairs:
        return _refused("Missing BackupObjectPair")
    for pair in pairs:
        backup, obj = str(pair.get("backupId")).lower(), str(pair.get("backupObjectId")).lower()
        if obj not in _OBJECTS:
            return _refused(f"Cannot find backup object with the specified Id: {obj}.")
        if backup not in _BACKUPS:
            return _refused(f"Cannot find backup with the specified Id: {backup}.")
        if (backup, obj) not in _PAIRS:
            return _refused(
                f"Backup with the specified Id: {backup} does not contain backup object with the specified Id: {obj}."
            )
    return None


def _engine_refusal(engine: dict[str, Any]) -> VbrError | None:
    yara, rule = engine.get("useYaraRule"), engine.get("yaraRule")
    if yara and rule is None:
        return _refused("Missing YaraRule specification")
    if not yara and not engine.get("useAntivirusEngine"):
        return _refused("Select at least one content scan mode.")
    if yara:
        file_name = (rule or {}).get("fileName") or ""
        if not file_name:
            return _refused("Select a YARA rule file.")
        if file_name.lower() not in _RULES:
            return _refused(f"Invalid YARA rule file: {file_name}")
    return None


def _point_refusal(body: dict[str, Any]) -> VbrError | None:
    if body.get("scanMode") != "Specific":
        return None
    point = body.get("restorePointId")
    if point is None:
        return _refused("Specify restorePointId when scanMode is Specific.")
    if str(point).lower() not in POINT_IDS:
        return VbrError(status_code=404, message="Restore point was not found.")
    return None


def reject_scan(body: Any) -> VbrError | None:
    """What VBR refuses to scan, in the order it checks, with its own texts.

    RestBackupScanValidator.cs and CYaraScanSettingsValidator.cs, answered as 400 by MalwareDetectionControllerImpl: a
    pair it cannot resolve, YARA without a rule, no engine, a rule file it does not have, a Specific scan without its
    point. A Specific point that is no restore point of the stand gets a neutral text: VBR's is not known.
    """
    body = body if isinstance(body, dict) else {}
    return (
        _pair_refusal(body.get("backupObjectPair") or [])
        or _engine_refusal(body.get("scanEngine") or {})
        or _point_refusal(body)
    )


# ---- License revokes


def revoke_path(row: InstanceLicenseWorkload) -> str:
    """The revoke of ``row``'s instance license."""
    return f"/api/v1/license/instances/{row.instance_id}/revoke"


def not_revocable(row: InstanceLicenseWorkload) -> VbrError:
    """VBR's refusal to revoke ``row``, whose canBeRevoked is false (AgentInstanceRevokeValidator.cs)."""
    return VbrError(status_code=400, message=f"Cannot revoke license for agent with id: {row.instance_id}.")


REVOKE_REFUSED = any_of(
    r"canBeRevoked\W+(is\s+)?(set\s+to\s+)?false",
    r"\bnon-?revocable\b",
    r"\bnot\s+revocable\b",
    near(CANNOT, r"\brevo[ck]", within=60),
)
"""VBR does not allow the revoke, said in any of the ways people say it."""
