# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G2-08: a morning health summary - jobs, failures, storage, license, config backup and security alerts."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

import stand
from cases import CaseInputs, Environment, judge, tool_budget
from cases.patterns import DISABLED, any_of, day, days, gb, name, near, percent
from evaluators import FactsPresent, ToolsCalled, ToolsNotCalled
from stand.config_backup import LAST_SUCCESS
from stand.ids import T0
from stand.jobs import JOB_STATES
from stand.license import EXPIRES, LICENSE
from stand.repositories import EXTENT_STATUS, REPOSITORY_STATES, is_low_on_space
from vbr_models.infrastructure import RepositoryState

# ---- What VBR serves: the whole base stand.

ENVIRONMENT: Environment = stand.environment()

# ---- What a correct answer says, derived from the data above.

_RUNNING = next(job for job in JOB_STATES if job.status == "Running")
_FAILED = next(job for job in JOB_STATES if job.last_result == "Failed")
_WARNINGS = [job.name for job in JOB_STATES if job.last_result == "Warning"]
_DISABLED = next(job for job in JOB_STATES if job.status == "Disabled")
_NEVER_RUN = next(job for job in JOB_STATES if job.last_result == "None")


def _pct(state: RepositoryState) -> float:
    return round(100 * state.free_gb / state.capacity_gb, 1)


_STATES = {state.name: state for state in REPOSITORY_STATES}
_LOW = [state for state in REPOSITORY_STATES if is_low_on_space(state)]
_MAIN = _STATES["Repo-Main"]
_MAINTENANCE = next(state.name for state in REPOSITORY_STATES if EXTENT_STATUS.get(state.id) == "Maintenance")
_WRITABLE_SOBR_GB = sum(state.free_gb for state in REPOSITORY_STATES if EXTENT_STATUS.get(state.id) == "Normal")
_DAYS_TO_EXPIRY = (EXPIRES - T0).days  # 44, as vbr-mcp's daysToExpiry counts them
_INSTANCES = LICENSE.instance_license_summary
_CAPACITY = LICENSE.capacity_license_summary
assert _INSTANCES is not None and _CAPACITY is not None
_INSTANCES_PERCENT = 100 * _INSTANCES.used_instances_number / _INSTANCES.licensed_instances_number

EXPECTED = (
    f"Server time: {T0:%Y-%m-%d %H:%M} (Europe/Prague). Not everything is fine. Most urgent: fs-01 is Infected - "
    "Microsoft Defender found Ransom:Win32/LockBit.SB!MTB on its latest restore point (10-06), after a Suspicious "
    "encrypted-data event on 10-04 and a mark-as-clean on 10-05 that proved premature. "
    f"Jobs: {len(JOB_STATES)} jobs; {_RUNNING.name} is running ({_RUNNING.progress_percent}%). {_FAILED.name} failed "
    "last night - one run whose two automatic retries failed too: sql-prod-01 could not be processed (guest "
    f"credentials, error 1326). {' and '.join(_WARNINGS)} ended with warnings; {_DISABLED.name} is disabled; "
    f"{_NEVER_RUN.name}, created an hour ago, has not run yet. Storage: low free space on "
    + ", ".join(f"{state.name} ({state.free_gb:g} GB, {_pct(state)}%)" for state in _LOW)
    + f"; {_MAINTENANCE} is in maintenance mode, so SOBR-Prod has about {_WRITABLE_SOBR_GB:.0f} GB for new backups. "
    "S3-Capacity is object storage that reports no capacity: not low, and not 100% free. "
    f"License: expires {EXPIRES:%Y-%m-%d}, in {_DAYS_TO_EXPIRY} days; {_INSTANCES.used_instances_number:g} of "
    f"{_INSTANCES.licensed_instances_number:g} instances used (~{_INSTANCES_PERCENT:.0f}%); capacity "
    f"{_CAPACITY.used_capacity_tb:g} of {_CAPACITY.licensed_capacity_tb:g} TB. Config backup: it has not run since "
    f"{LAST_SUCCESS:%Y-%m-%d} (its encryption is off while the jobs' passwords are in the Password Manager, so VBR "
    "does not start it). Only one proxy (Proxy-01, 8 task slots) can take tasks. Not infections: web-02's "
    "bulk-deletion event of 10-04 (Suspicious, but its signature scan found nothing - Informative; unconfirmed, "
    "nobody has marked it clean); web-01's and app-01's events marked false "
    f"positives. Other figures: {_MAIN.name} {_MAIN.free_gb:g} GB free ({_pct(_MAIN)}%), Repo-DR 7000 GB free, the "
    "SOBR performance tier 6700 GB free of which SOBR-Ext-03's 3900 GB is in maintenance."
)
"""Ground truth for the judges: the summary and the figures it may quote."""

FACTS = {
    "infected_machine": near(name("fs-01"), r"infect", 200),
    "threat": r"lockbit|ransom",
    "running_job": near(name(_RUNNING.name), r"running|in\s+progress|active", 120),
    "failed_job": near(name(_FAILED.name), r"fail", 150),
    **{f"warning_{job.lower().replace('-', '_')}": name(job) for job in _WARNINGS},
    "disabled_job": near(name(_DISABLED.name), DISABLED, 120),
    **{
        f"low_{state.name.lower().replace('-', '_')}": near(
            name(state.name), any_of(gb(state.free_gb), percent(_pct(state)), percent(100 - _pct(state))), 150
        )
        for state in _LOW
    },
    "maintenance_extent": near(name(_MAINTENANCE), r"maintenance", 150),
    "license_expiry": any_of(days(_DAYS_TO_EXPIRY, slack=1), day(EXPIRES, weekday=False)),
    "license_usage": any_of(
        percent(_INSTANCES_PERCENT),
        r"(?<![\d.])90\s*%",
        near(r"(?<![\d.])10(\.0+)?(?!\d|[.,]\d)", r"(?<![\d.])11(?!\d|[.,]\d)", 40),
    ),
    "config_backup_stale": near(
        r"config(uration)?[\s-]*backup",
        any_of(
            day(LAST_SUCCESS, weekday=False),
            days(round((T0 - LAST_SUCCESS).total_seconds() / 86400), slack=1),
            r"not\s+(been\s+)?(running|run)\b",
            r"(has|have)\s*n[o']?t\s+(run|ran|succeeded|completed)",
            r"no\s+(successful\s+|recent\s+)?([\w'-]+\s+){0,2}(runs?|sessions?|backups?)\s+(for|since|in)",
            r"\b(stale|overdue)\b",
        ),
        300,
    ),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

_ALLOWED = (
    "It is acceptable, and not a violation, to add that only one proxy can take tasks, to give a prioritized list of "
    "actions with the fs-01 incident first, to omit WAN accelerators, to mention or omit Test-NewApp (created an "
    "hour ago, first run tonight), to give the cause of the SQL-Prod or config backup problem in more detail, to "
    "mention web-02's checked event as a non-issue, or to recommend fixes as advice."
)

GOOD = [
    (
        "**Morning summary - 2026-10-07 09:00**\n\n"
        "🔴 **Security:** fs-01 is **Infected** - Defender found Ransom:Win32/LockBit.SB!MTB in its latest restore point "
        "(Oct 6). Treat this first.\n\n"
        "**Jobs:** SQL-Dev is running (45%). SQL-Prod failed last night (one run, both retries failed - sql-prod-01, "
        "error 1326). Copy-to-DR and Agent-Laptops ended with warnings. Legacy-Archive is disabled.\n\n"
        "**Storage:** Repo-Linux-01 860 GB free (4.2%), Repo-Branch 90 GB free, SOBR-Ext-02 300 GB free (3.7%); "
        "SOBR-Ext-03 is in maintenance mode. S3-Capacity reports no capacity figures.\n\n"
        "**License:** expires 2026-11-21 (44 days); 10 of 11 instances used.\n\n"
        "**Config backup:** has not run since 2026-09-27 - it is unencrypted while job passwords exist, so VBR won't "
        "start it."
    ),
    (
        "| Area | Status |\n|---|---|\n| Malware | fs-01 infected (LockBit), most urgent |\n| Running | SQL-Dev - in "
        "progress, 45 % |\n| Failed | SQL-Prod (00:00 run + retries) |\n| Warnings | Copy-to-DR, Agent-Laptops |\n"
        "| Disabled | Legacy-Archive |\n| Low space | Repo-Linux-01 (95.8% full), Repo-Branch (90.0 GB), SOBR-Ext-02 "
        "(96.3% full) |\n| SOBR | SOBR-Ext-03 in Maintenance |\n| License | 90.9% used, 45 days left |\n| Config backup "
        "| last success Sep 27, nothing since - stale |"
    ),
    (
        "Not all good. fs-01's newest point is infected with ransomware (LockBit) - priority one. SQL Prod failed "
        "overnight; SQL Dev is running right now; Copy-to-DR and Agent-Laptops warned; Legacy-Archive is turned off. "
        "Space is tight on Repo-Linux-01 (0.86 TB, 4.2%), Repo-Branch (90 GB) and SOBR-Ext-02 (300 GB); SOBR-Ext-03 is in "
        "maintenance. License good until 21 November (10/11 instances). The configuration backup hasn't run for 10 "
        "days."
    ),
]

BAD = {
    "infected_machine": "Jobs: SQL-Prod failed, SQL-Dev running, Copy-to-DR and Agent-Laptops warned, Legacy-Archive "
    "disabled. No security alerts. Repo-Linux-01 (4.2%), Repo-Branch (90 GB), SOBR-Ext-02 (3.7%) are low, SOBR-Ext-03 "
    "in maintenance. License: 44 days, 10 of 11. Config backup: not run since 2026-09-27. LockBit seen once.",
    "config_backup_stale": "fs-01 is infected with LockBit. SQL-Prod failed, SQL-Dev running, Copy-to-DR and "
    "Agent-Laptops warned, Legacy-Archive disabled. Repo-Linux-01 4.2%, Repo-Branch 90 GB, SOBR-Ext-02 3.7%, SOBR-Ext-03 "
    "in maintenance. License expires in 44 days, 10 of 11 used. The configuration backup is enabled and fine.",
    "low_sobr_ext_02": "fs-01 is infected with LockBit. SQL-Prod failed, SQL-Dev running, Copy-to-DR and "
    "Agent-Laptops warned, Legacy-Archive disabled. Repo-Linux-01 4.2% and Repo-Branch 90 GB are low; SOBR-Ext-03 is "
    "in maintenance. License: 44 days, 10 of 11. Config backup not run since 2026-09-27.",
}


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G2-08",
        inputs=CaseInputs(
            question="Give me a morning health summary of the backup environment: jobs, failures, storage, license, config backup and any security alerts.",
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G2", "base_stand": "1.1-1.12"},
        evaluators=[
            # One read per area; the jobs' state from get_job_states or the sessions. get_server_status,
            # list_proxies, list_scale_out_repositories and a failure drill-down or two are reads on top.
            ToolCorrectness(
                expected_tools=[
                    "list_repositories",
                    "get_license_status",
                    "get_config_backup_status",
                    "list_malware_events",
                ],
                allow_extra=True,
            ),
            ToolsCalled("jobs_read", frozenset({"get_job_states", "list_sessions"})),
            *tool_budget(12),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "not_all_fine",
                "The output does not say or imply that everything is fine or healthy: it reports problems.",
            ),
            _judge(
                "consistent_with_data",
                "The numbers and statuses the output gives (job results, free space, license days and usage, config "
                "backup dates, malware findings) do not contradict the expected output, and the output does not "
                "contradict itself between sections. A figure that the expected output does not list is not a "
                "contradiction by itself; judge only figures the expected output covers.",
            ),
            _judge(
                "no_false_alarms",
                "The output does not present web-02's bulk-deletion event of 10-04 as malware found or an infection "
                "(its signature scan found nothing, severity Informative; listing it as an unconfirmed suspicious "
                "event to review is fine), and raises no alert for the mark-as-clean events or for the events marked "
                "false positive (web-01 renamed files, app-01 extensions). fs-01's events are a real alert.",
            ),
            _judge(
                "fs01_most_urgent",
                "The output treats the fs-01 infection as the most urgent item, or at least flags it as critical or "
                "a top priority.",
            ),
            _judge(
                "sql_prod_one_incident",
                "The output reports SQL-Prod's night as one failed run (with its retries), not as several failures.",
            ),
            _judge(
                "s3_not_free",
                "The output does not present S3-Capacity as 100% free, as having free space, or as low on space.",
            ),
            _judge(
                "no_actions_taken",
                "The output does not claim to have started, retried, enabled, disabled, scanned, restored or "
                "otherwise changed anything; recommendations are fine.",
            ),
        ],
    )
