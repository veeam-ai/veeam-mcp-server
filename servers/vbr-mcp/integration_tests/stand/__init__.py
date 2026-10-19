# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""The base stand (test plan section 1) as VBR serves it: one consistent VBR, which every case starts from.

``environment()`` mocks every route vbr-mcp's read tools ask for - collections, each object by id, logs, task
sessions, restore points per object, disks, the files and objects of each backup - so that a natural extra read gets
what a real VBR would answer instead of a 404. A case changes the stand by passing its own data for a collection
(``environment(job_states=...)``): the routes derived from it (``/sessions/{id}``, ``/backupObjects/{id}/restorePoints``,
...) are built from what it passed. Its actions (``POST .../start`` and the like) it adds to the result itself.

Where the plan's stand is not what VBR 13 would hold, the stand follows VBR, with the source:

- **Retries** (1.3): ``retryInfo`` only on a retry, numbered without the original run (swagger ``SessionRetryInfo``):
  S-ID05 and S-ID06 are retries 1 and 2 of S-ID04, S-ID15 retry 1 of S-ID14.
- **Configuration backup** (1.3, 1.12): no session after 2026-09-27. VBR does not start an unencrypted configuration
  backup once the Password Manager holds a password (User Guide v13, config_backup_encrypted), so there is no daily
  Failed session; the runs up to 09-27 end with "Skipping credentials backup because the encryption is disabled"
  (forum t74377). S-ID09 is gone.
- **Malware** (1.8, 1.10): fs-01 was marked clean on 10-05 (EV07, not as a false positive), which is how its 10-05
  point can be Clean after the Suspicious one of 10-04 (User Guide v13, malware_detection_how_it_works and
  malware_detection_managing_status_console); web-02's Informative signature scan has its trigger, a bulk deletion
  (EV08, malware_detection_signature_detection); app-01's false positive has its mark-as-clean (EV09).
- **Scan Backup** (S-ID13): a ``SureBackup`` session named "Scan Backup", as ``POST /malwareDetection/scanBackup``
  starts it (swagger); its task's ``restorePointReference`` is the point's API path.
- **Jobs** (1.2): Reports-VM makes a weekly synthetic full (hardened repository, User Guide v13,
  hardened_repository_limitations); VM jobs retry automatically (VBR's default; Daily-VMs retried on 10-05); job states
  read ``Stopped`` with the last run's progress at 100% once a job has run (swagger ``JobStatesResultExample``);
  Reports-VM's ``nextRunPolicy`` is "After [Daily-VMs]", as in that example.
- **Database** (1.1): ``sqlServerVersion`` carries the PostgreSQL version (swagger ``ServerInfoModelExample``).
- **Timeline**: Reports-VM is chained, so S-ID16 starts after that night's Daily-VMs (22:41:31) and on 10-05 it and
  Copy-to-DR wait for the Daily-VMs retry; Agent-Laptops warns every day laptop-fin-01 is offline, as S-ID10 does;
  laptop-fin-01 last connected when its backup of 10-01 ended (the plan's T0-6d, 09:00, came before that backup).
- **Disks**: named like VMDKs, ``sql-prod-02`` and ``sql-prod-02_1`` (swagger ``ObjectRestorePointDisksResultExample``);
  a laptop's point lists its agent's disk, and VBR refuses to list a file share's or bucket's (400,
  ObjectRestorePointsControllerImpl).

- **NAS sources** (1.15): none is broken on its own. VBR requires backup proxies and a cache repository for each
  (swagger ``SMBShareServerProcessingModel``) and does not save a share that needs credentials without them, so the
  plan's blockers (no cache repository, no proxy, no credentials) cannot exist; a case blocks a source through the
  state of its proxy or cache repository instead (G2-13).

- **Names and versions**: a backup carries its job's name (swagger ``BackupModel.name``), so the orphaned B10 and the
  imported B11 are "FileApp-Weekly" and "ERP-Nightly"; vCenter's inventory ``objectId`` is a GUID (swagger
  ``ServersInventoryBrowserResultExample``); agents run the 13.1 agent of a 13.1 server; license object types read
  "Virtual Machines"/"Workstations" (swagger ``InstalledLicenseModelExample``); the ``Json`` license report is CSV
  rows (swagger ``LicenseCreateReportExample``); the WAN traffic port is VBR's default, 6165.

Kept from the plan although VBR would differ: the duplicate fs-01 row of ``/backupObjects``, and B10's 6 files for 5
points per VM. Jobs writing to the nearly full Repo-Linux-01 other than Agent-Laptops do not warn about its free space.
The backup server's own default proxy is not there (as if removed, common in production); G2-13 adds general-purpose
proxies of its own.
"""

from collections.abc import Callable, Iterable, Mapping
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from cases import Environment
from stand import (
    agents,
    backups,
    config_backup,
    ids,
    instant_recovery,
    inventory,
    jobs,
    license,
    malware,
    nas,
    options,
    protected,
    proxies,
    repositories,
    server,
    sessions,
)
from vbr_models.sessions import SessionLog

__all__ = [
    "agents",
    "backups",
    "by_id",
    "by_name",
    "config_backup",
    "environment",
    "ids",
    "instant_recovery",
    "inventory",
    "jobs",
    "license",
    "malware",
    "nas",
    "options",
    "protected",
    "proxies",
    "replace",
    "repositories",
    "server",
    "sessions",
]

DEFAULTS: dict[str, Any] = {
    "server_info": server.SERVER_INFO,
    "server_time": server.SERVER_TIME,
    "jobs": jobs.JOBS,
    "job_states": jobs.JOB_STATES,
    "sessions": sessions.SESSIONS,
    "tasks": sessions.TASKS,
    "session_logs": {},
    "task_logs": {},
    "repositories": repositories.REPOSITORIES,
    "repository_states": repositories.REPOSITORY_STATES,
    "scale_out_repositories": repositories.SCALE_OUT_REPOSITORIES,
    "proxies": proxies.PROXIES,
    "proxy_states": proxies.PROXY_STATES,
    "wan_accelerators": proxies.WAN_ACCELERATORS,
    "vmware_hosts": inventory.VMWARE_HOSTS,
    "inventory_hosts": inventory.INVENTORY_HOSTS,
    "inventory_objects": inventory.OBJECTS,
    "backup_objects": protected.BACKUP_OBJECTS,
    "restore_points": protected.RESTORE_POINTS,
    "disks": protected.DISKS,
    "networks": protected.NETWORK_INFO,
    "backups": backups.BACKUPS,
    "backup_contents": backups.BACKUP_OBJECTS,
    "backup_files": backups.BACKUP_FILES,
    "malware_events": malware.EVENTS,
    "yara_rules": malware.YARA_RULES,
    "license": license.LICENSE,
    "license_instances": license.INSTANCES,
    "license_sockets": license.SOCKETS,
    "license_capacity": license.CAPACITY,
    "license_report": license.LICENSE_REPORT,
    "config_backup": config_backup.CONFIG_BACKUP,
    "general_options": options.GENERAL_OPTIONS,
    "protection_groups": agents.PROTECTION_GROUPS,
    "discovered_entities": agents.DISCOVERED_ENTITIES,
    "unstructured_data_servers": nas.UNSTRUCTURED_DATA_SERVERS,
    "instant_recovery_mounts": instant_recovery.MOUNTS,
}
"""What ``environment`` serves, by the keyword that overrides it. A mapping (``session_logs``, ``disks``,
``networks``, ``backup_files``, ...) is merged into the stand's, keyed by object id (``inventory_objects`` by root server name);
anything else replaces the stand's. Some routes are answered from the data rather than served as it is:
``POST /api/v1/inventory`` filters ``inventory_hosts`` by the request's body, ``POST /api/v1/inventory/{name}`` browses
the ``inventory_objects`` of each of those roots (VBR's 404 for the names of the hosts inside them), and the license
report is made from ``license`` and ``license_capacity`` unless a case passes its own ``license_report``."""

IR_MOUNTS = "/api/v1/restore/instantRecovery/vSphere/vm"


def environment(**overrides: Any) -> Environment:
    """Every route of the base stand, with ``overrides`` (see ``DEFAULTS``) in place of the stand's data.

    Routes are keyed without a verb, so a case replaces one by its plain path; the exceptions are the reads VBR serves
    over ``POST`` (``POST /api/v1/inventory``, ``POST /api/v1/inventory/{name}``, ``POST /api/v1/license/createReport``,
    ``POST /api/v1/restorePoints/{id}/networkInfo``) and the Instant Recovery list,
    whose path the start action shares (``GET /api/v1/restore/instantRecovery/vSphere/vm``).
    """
    unknown = sorted(set(overrides) - set(DEFAULTS))
    if unknown:
        raise TypeError(f"Unknown stand collections: {', '.join(unknown)}. Known: {', '.join(sorted(DEFAULTS))}")
    data: dict[str, Any] = {
        name: (
            {**value, **overrides[name]}
            if isinstance(value, Mapping) and name in overrides
            else overrides.get(name, value)
        )
        for name, value in DEFAULTS.items()
    }
    env: Environment = {
        "/api/v1/serverInfo": data["server_info"],
        "/api/v1/serverTime": data["server_time"],
        **_jobs(data),
        **_sessions(data),
        "/api/v1/backupInfrastructure/repositories": data["repositories"],
        "/api/v1/backupInfrastructure/repositories/states": data["repository_states"],
        "/api/v1/backupInfrastructure/scaleOutRepositories": data["scale_out_repositories"],
        "/api/v1/backupInfrastructure/proxies": data["proxies"],
        "/api/v1/backupInfrastructure/proxies/states": data["proxy_states"],
        "/api/v1/backupInfrastructure/wanAccelerators": data["wan_accelerators"],
        "/api/v1/inventory/vmware/hosts": data["vmware_hosts"],
        "POST /api/v1/inventory": inventory.hosts_browser(data["inventory_hosts"]),
        **_inventory_objects(data),
        **_protected(data),
        **_backups(data),
        "/api/v1/malwareDetection/events": data["malware_events"],
        "/api/v1/malwareDetection/yaraRules": data["yara_rules"],
        "/api/v1/license": data["license"],
        "/api/v1/license/instances": data["license_instances"],
        "/api/v1/license/sockets": data["license_sockets"],
        "/api/v1/license/capacity": data["license_capacity"],
        "POST /api/v1/license/createReport": (
            data["license_report"]
            if "license_report" in overrides
            else license.report(data["license"], data["license_capacity"])
        ),
        "/api/v1/configBackup": data["config_backup"],
        "/api/v1/generalOptions": data["general_options"],
        "/api/v1/agents/protectionGroups": data["protection_groups"],
        **{
            f"/api/v1/agents/protectionGroups/{group.id}/discoveredEntities": data["discovered_entities"].get(
                group.id, []
            )
            for group in data["protection_groups"]
        },
        "/api/v1/inventory/unstructuredDataServers": data["unstructured_data_servers"],
        **{
            f"/api/v1/inventory/unstructuredDataServers/{source.id}": source
            for source in data["unstructured_data_servers"]
        },
        f"GET {IR_MOUNTS}": data["instant_recovery_mounts"],
        **{f"GET {IR_MOUNTS}/{mount.id}": mount for mount in data["instant_recovery_mounts"]},
    }
    return env


def _inventory_objects(data: dict[str, Any]) -> Environment:
    """``POST /api/v1/inventory/{name}`` for every root of the inventory, and VBR's 404 for the hosts inside them.

    A root the stand holds no objects for is browsed as itself alone; a host (or root) that is no root now - an ESXi
    host a vCenter manages, a vCenter a case removed - answers "Cannot find host with name", as VBR does.
    """
    roots = {host.name: host for host in data["inventory_hosts"]}
    hosts_inside = {
        item.name
        for hierarchies in data["inventory_objects"].values()
        for items in hierarchies.values()
        for item in items
        if item.type in ("vCenterServer", "Host")
    }
    return {
        **{f"POST /api/v1/inventory/{name}": inventory.not_found(name) for name in sorted(hosts_inside - set(roots))},
        **{
            f"POST /api/v1/inventory/{name}": inventory.objects_browser(root, data["inventory_objects"].get(name, {}))
            for name, root in roots.items()
        },
    }


def _jobs(data: dict[str, Any]) -> Environment:
    return {
        "/api/v1/jobs": data["jobs"],
        **{f"/api/v1/jobs/{job.id}": job for job in data["jobs"]},
        "/api/v1/jobs/states": data["job_states"],
    }


def _sessions(data: dict[str, Any]) -> Environment:
    tasks_of: dict[UUID, list] = {}
    for task in data["tasks"]:
        tasks_of.setdefault(task.session_id, []).append(task)
    return {
        "/api/v1/sessions": data["sessions"],
        **{f"/api/v1/sessions/{s.id}": s for s in data["sessions"]},
        **{
            f"/api/v1/sessions/{s.id}/logs": data["session_logs"].get(s.id)
            or _built(_SESSION_LOGS, s, sessions.session_log)
            for s in data["sessions"]
        },
        **{f"/api/v1/sessions/{s.id}/taskSessions": tasks_of.get(s.id, []) for s in data["sessions"]},
        "/api/v1/taskSessions": data["tasks"],
        **{
            f"/api/v1/taskSessions/{t.id}/logs": data["task_logs"].get(t.id) or _built(_TASK_LOGS, t, sessions.task_log)
            for t in data["tasks"]
        },
    }


_SESSION_LOGS: dict[int, tuple[Any, SessionLog]] = {}
_TASK_LOGS: dict[int, tuple[Any, SessionLog]] = {}


def _built[Owner](
    cache: dict[int, tuple[Any, SessionLog]], owner: Owner, build: Callable[[Owner], SessionLog]
) -> SessionLog:
    """``build(owner)``, built once per object: every case's ``environment()`` serves the same sessions and tasks.

    Keyed by identity, not equality - models are not hashable, and comparing them would cost what building does. The
    entry holds the object, so its id is not reused while cached; a case's own sessions are built once too.
    """
    entry = cache.get(id(owner))
    if entry is None or entry[0] is not owner:
        entry = cache[id(owner)] = (owner, build(owner))
    return entry[1]


def _protected(data: dict[str, Any]) -> Environment:
    points_of: dict[UUID, list] = {}
    for point in sorted(data["restore_points"], key=lambda p: p.creation_time, reverse=True):
        points_of.setdefault(point.backup_object_id, []).append(point)
    objects = list({obj.id: obj for obj in data["backup_objects"]}.values())  # the listing may repeat a row
    return {
        "/api/v1/backupObjects": data["backup_objects"],
        **{f"/api/v1/backupObjects/{obj.id}": obj for obj in objects},
        **{f"/api/v1/backupObjects/{obj.id}/restorePoints": points_of.get(obj.id, []) for obj in objects},
        "/api/v1/restorePoints": data["restore_points"],
        **{
            f"/api/v1/restorePoints/{point.id}/disks": (
                protected.NAS_DISKS if point.platform_name == "UnstructuredData" else data["disks"].get(point.id, [])
            )
            for point in data["restore_points"]
        },
        **{
            f"POST /api/v1/restorePoints/{point.id}/networkInfo": data["networks"].get(point.id, [])
            for point in data["restore_points"]
            if point.platform_name == "VMware"
        },
    }


def _backups(data: dict[str, Any]) -> Environment:
    return {
        "/api/v1/backups": data["backups"],
        **{f"/api/v1/backups/{backup.id}": backup for backup in data["backups"]},
        **{
            f"/api/v1/backups/{backup.id}/objects": data["backup_contents"].get(backup.id, [])
            for backup in data["backups"]
        },
        **{
            f"/api/v1/backups/{backup.id}/backupFiles": data["backup_files"].get(backup.id, [])
            for backup in data["backups"]
        },
    }


def _matches(item: BaseModel, key: UUID | str) -> bool:
    return str(getattr(item, "id", "")) == str(key) or getattr(item, "name", None) == key


def by_id[Item: BaseModel](items: Iterable[Item], key: UUID) -> Item:
    """The item of ``items`` whose id is ``key`` (a job's state, a session, a malware event...)."""
    found = next((item for item in items if getattr(item, "id", None) == key), None)
    if found is None:
        raise KeyError(key)
    return found


def by_name[Item: BaseModel](items: Iterable[Item], name: str) -> Item:
    """The item of ``items`` named ``name`` (a job, a repository, a protected object...)."""
    found = next((item for item in items if getattr(item, "name", None) == name), None)
    if found is None:
        raise KeyError(name)
    return found


def replace[Item: BaseModel](items: Iterable[Item], key: UUID | str, **update: Any) -> list[Item]:
    """``items`` with the one whose id or name is ``key`` changed by ``update`` (its fields, by Python name).

    The changed item is validated again, so an update VBR could not answer with fails here, not in the mock.
    """
    result, found = [], False
    for item in items:
        if _matches(item, key):
            item = type(item).model_validate({**item.model_dump(by_alias=False), **update})
            found = True
        result.append(item)
    if not found:
        raise KeyError(key)
    return result
