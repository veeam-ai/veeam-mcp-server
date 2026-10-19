# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G1-20: a freshly installed VBR — which jobs failed last night."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case

from cases import CaseInputs, Environment, judge, tool_budget
from cases.patterns import any_of
from evaluators import FactsPresent, ToolsCalled, ToolsNotCalled
from stand import config_backup, environment, license, options, repositories, sessions
from stand.ids import M01, at, mnemonic
from stand.proxies import MANAGED_SERVERS
from vbr_models.config_backup import ConfigBackupLastSuccessful
from vbr_models.general_options import SiemIntegration
from vbr_models.infrastructure import Proxy, ProxyServer, ProxyState
from vbr_models.license import CapacityLicenseWorkloads, InstanceLicenseSummary

# ---- What VBR serves: not the base stand's data but a VBR installed on 2026-09-30, with nothing configured yet. Every
# route the base stand has is there - a real VBR always answers them - but what a fresh install holds is little: the
# default backup repository and the default VMware backup proxy on the backup server itself, no jobs, no backups, no
# vSphere server added. And its configuration backup, which VBR creates and runs daily at 10:00 by default (User
# Guide v13, export_vbr_config): unencrypted, with nothing in the Password Manager, each run ends with the Warning
# "Skipping credentials backup because the encryption is disabled" (forum t74377). Those sessions are the trap: the
# "Backup Configuration Job" is not a backup job, and its warning is not a failure of last night.

DEFAULT_REPOSITORY = mnemonic("20000000", 99)
DEFAULT_PROXY = mnemonic("30000000", 99)

_REPOSITORY, _REPOSITORY_STATE = repositories.repository(
    DEFAULT_REPOSITORY, "Default Backup Repository", "WinLocal", M01, "C:\\Backup", 500, 482.4, 17.6
)

_PROXY_HOST = MANAGED_SERVERS[M01]
_PROXY = Proxy(
    id=DEFAULT_PROXY,
    name="VMware Backup Proxy",
    description="Created by Veeam Backup & Replication",
    type="ViProxy",
    server=ProxyServer(host_id=M01, host_name=_PROXY_HOST, transport_mode="Auto", failover_to_network=True,
                       host_to_proxy_encryption=False, max_task_count=4),
)  # fmt: skip
_PROXY_STATE = ProxyState(
    id=DEFAULT_PROXY,
    name="VMware Backup Proxy",
    description="Created by Veeam Backup & Replication",
    type="ViProxy",
    host_id=M01,
    host_name=_PROXY_HOST,
    is_disabled=False,
    is_online=True,
    is_out_of_date=False,
)

CONFIG_SESSIONS = [
    sessions.session(
        200 + n,
        "Backup Configuration Job",
        at(1 + n, 10, 0, 2),
        at(1 + n, 10, 0, 41),
        "Warning",
        message=sessions.CONFIG_WARNING,
        session_type="ConfigurationBackup",
    )
    for n in range(6)  # 10-01 .. 10-06; the first one after the install
][::-1]
"""The daily configuration backups since the install, newest first."""

_LAST_CONFIG_BACKUP = CONFIG_SESSIONS[0]

CONFIG_BACKUP = config_backup.CONFIG_BACKUP.model_copy(
    update={
        "backup_repository_id": DEFAULT_REPOSITORY,
        "last_successful_backup": ConfigBackupLastSuccessful(
            last_successful_time=_LAST_CONFIG_BACKUP.end_time, session_id=_LAST_CONFIG_BACKUP.id
        ),
    }
)

_UNUSED = license.LICENSE.instance_license_summary
assert _UNUSED is not None
LICENSE = license.LICENSE.model_copy(
    update={
        "instance_license_summary": InstanceLicenseSummary(
            licensed_instances_number=_UNUSED.licensed_instances_number,
            used_instances_number=0,
            new_instances_number=0,
            rental_instances_number=0,
            objects=[],
        ),
        "capacity_license_summary": license.LICENSE.capacity_license_summary.model_copy(update={"used_capacity_tb": 0})
        if license.LICENSE.capacity_license_summary
        else None,
    }
)

GENERAL_OPTIONS = options.GENERAL_OPTIONS.model_copy(
    update={
        "email_settings": None,
        "siem_integration": SiemIntegration(snmp_events_enabled=False, syslog_events_enabled=False),
    }
)

ENVIRONMENT: Environment = environment(
    jobs=[],
    job_states=[],
    sessions=CONFIG_SESSIONS,
    tasks=[],
    repositories=[_REPOSITORY],
    repository_states=[_REPOSITORY_STATE],
    scale_out_repositories=[],
    proxies=[_PROXY],
    proxy_states=[_PROXY_STATE],
    wan_accelerators=[],
    vmware_hosts=[],
    inventory_hosts=[],
    backup_objects=[],
    restore_points=[],
    backups=[],
    malware_events=[],
    license=LICENSE,
    license_instances=[],
    license_capacity=CapacityLicenseWorkloads(workloads=[]),
    config_backup=CONFIG_BACKUP,
    general_options=GENERAL_OPTIONS,
    protection_groups=[],
    unstructured_data_servers=[],
)

# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    "There are no backup jobs configured on this VBR server at all, so no backup job failed last night. The only "
    "sessions are VBR's own daily configuration backups (Backup Configuration Job, 10:00); the latest, on "
    f"{_LAST_CONFIG_BACKUP.creation_time:%Y-%m-%d}, ended with a Warning because credentials are skipped while its "
    "encryption is off - that is not a failed backup job, and it did not run last night."
)
"""Ground truth for the judges."""

FACTS = {
    # "no jobs", "there are no backup jobs", "no jobs are configured", "zero jobs", "0 configured jobs",
    # "doesn't have any jobs", "no jobs exist"
    "no_jobs": any_of(
        r"\bno\b(\W+\w+){0,3}\W+jobs?\b",
        r"\b(zero|0)\s+(configured\s+)?(backup\s+)?jobs\b",
        r"n[o']t\s+(have\s+|contain\s+|find\s+|show\s+|list\s+)?(any|a\s+single)\s+(configured\s+)?(backup\s+)?jobs?\b",
        r"\bjobs?\b[^.\n]{0,30}\b(empty|none)\b",
    ),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

_ALLOWED = (
    "It is acceptable, and not a violation, to check the night's sessions as well, to mention the daily "
    "configuration backup and its warning, to recommend enabling configuration backup encryption, to suggest "
    "creating backup jobs, or to suggest checking the connection to VBR or the account's permissions in case jobs "
    "were expected."
)

GOOD = [
    (
        "No backup job failed last night - there are no backup jobs configured on this VBR server at all. The only "
        "sessions are the daily configuration backups (Backup Configuration Job at 10:00); the last one, on 2026-10-06, "
        "finished with a warning that credentials were skipped because encryption is disabled. That is not a job "
        "failure."
    ),
    (
        "This VBR server has 0 configured jobs, so nothing could fail last night. (Its own configuration backup runs "
        "daily and warns about missing encryption - consider enabling it.)"
    ),
    "None: the server doesn't have any backup jobs yet.",
]
"""Answers a correct agent could give: every fact must match each of them."""

BAD = {
    "no_jobs": "The Backup Configuration Job failed last night with a warning about credentials; everything else "
    "succeeded.",
}
"""Per fact, an answer that gets that fact wrong: the fact must not match it."""


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G1-20",
        inputs=CaseInputs(question="Which backup jobs failed last night?", environment=ENVIRONMENT),
        expected_output=EXPECTED,
        metadata={"group": "G1", "base_stand": "fresh install"},
        evaluators=[
            # get_job_states, list_jobs or list_sessions shows there are none; get_server_status (what "last night"
            # is) is a read the case allows on top.
            ToolsCalled("jobs_read", frozenset({"get_job_states", "list_jobs", "list_sessions"})),
            *tool_budget(3),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "no_invented_jobs",
                "The output does not name or describe any backup job, any session of one, or any job failure: the "
                "server has none. Mentioning VBR's configuration backup is fine.",
            ),
            _judge(
                "config_backup_not_a_job_failure",
                "The output does not present the Backup Configuration Job, or its warning, as a backup job that "
                "failed last night: it is VBR's own daily configuration backup (at 10:00), and its runs end with a "
                "warning, not a failure.",
            ),
            _judge(
                "no_jobs_not_all_succeeded",
                "The output does not answer that all jobs succeeded or that nothing failed without making clear "
                "that there are no backup jobs at all.",
            ),
        ],
    )
