# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G1-04: the configuration of the Daily-VMs job."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import CaseInputs, judge, tool_budget
from cases.patterns import any_of, clock, name
from evaluators import FactsPresent, ToolsNotCalled
from stand import by_name, environment
from stand.ids import T0
from stand.jobs import JOBS
from stand.repositories import REPOSITORIES
from vbr_models.jobs import BackupJob

# ---- What VBR serves: the base stand. Daily-VMs keeps 14 days with weekly GFS for 4 weeks, makes a synthetic full
# on Saturdays, is encrypted, writes to Repo-Main and retries a failed run 3 times, 10 minutes apart (VBR's default;
# it did retry on 10-05).

ENVIRONMENT = environment()

# ---- What a correct answer says, derived from the stand.

DAILY_VMS = by_name(JOBS, "Daily-VMs")
assert isinstance(DAILY_VMS, BackupJob)
_STORAGE = DAILY_VMS.storage
_DAILY = DAILY_VMS.schedule.daily
_RETRY = DAILY_VMS.schedule.retry
assert _DAILY is not None and _DAILY.local_time and _RETRY is not None and _STORAGE.gfs_policy is not None
_WEEKLY = _STORAGE.gfs_policy.weekly
assert _WEEKLY is not None
_RUNS_AT = T0.replace(hour=int(_DAILY.local_time[:2]), minute=int(_DAILY.local_time[3:]))  # 22:00
_RETENTION = _STORAGE.retention_policy.quantity  # 14 days
_WEEKS = _WEEKLY.keep_for_number_of_weeks  # 4
_RETRY_COUNT, _RETRY_MINUTES = _RETRY.retry_count, _RETRY.await_minutes  # 3 retries, 10 minutes apart
_REPOSITORY = by_name(REPOSITORIES, "Repo-Main")
assert _REPOSITORY.id == _STORAGE.backup_repository_id
_VMS = [vm.name for vm in DAILY_VMS.virtual_machines.includes]

EXPECTED = (
    f"{DAILY_VMS.name} runs daily at {_DAILY.local_time}, every day, and retries a failed run {_RETRY.retry_count} "
    f"times, {_RETRY.await_minutes} minutes apart. Retention: {_RETENTION} days, with GFS weekly fulls kept for "
    f"{_WEEKS} weeks (taken on {_WEEKLY.desired_time}); a synthetic full is made every Saturday. Backup encryption is "
    f"enabled (password-based). It writes to the repository {_REPOSITORY.name}. It also has application-aware "
    f"processing on and protects {len(_VMS)} VMs: {', '.join(_VMS)}; Reports-VM is chained to run after it."
)
"""Ground truth for the judges."""

FACTS = {
    "schedule": clock(_RUNS_AT),
    "retention": any_of(
        rf"(?<![\d.]){_RETENTION}[\s-]*(?:calendar\s+)?days?\b",
        rf"\bdays\W{{1,3}}{_RETENTION}\b",
        r"\btwo\s+weeks\b",
    ),
    "gfs_weekly": any_of(
        rf"(?<![\d.]){_WEEKS}[\s-]*weeks?\b",
        r"\bfour\s+weeks?\b",
        rf"\bweekly\W+(?:\w+\W+){{0,6}}{_WEEKS}\b",
        rf"(?<![\d.]){_WEEKS}\W+(?:\w+\W+){{0,3}}weekly",
    ),
    "encryption": r"\bencrypt",
    "repository": name(_REPOSITORY.name),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match: the four settings the question names."""

_ALLOWED = (
    "It is acceptable, and not a violation, to look up the repository to give its name or describe it with what VBR "
    "reports about it (type, host, path, capacity, free space, online status), and to mention further settings the "
    f"job really has: the VMs it protects ({', '.join(_VMS)}), application-aware processing on, the synthetic full on "
    f"Saturdays, GFS weekly fulls taken on {_WEEKLY.desired_time}, no monthly or yearly GFS, no active fulls, "
    f"incremental backup mode, automatic retry {_RETRY.retry_count} times {_RETRY.await_minutes} minutes apart, "
    "automatic proxy selection, optimal compression, password-based encryption, guest file system indexing off, the "
    "VMs coming from vcenter01.lab.local, and Reports-VM running after it as a chained job."
)

GOOD = [
    (
        "**Daily-VMs** configuration:\n- Schedule: daily at 22:00, every day (automatic retry: 3 times, 10 minutes apart)"
        "\n- Retention: 14 days, plus GFS weekly fulls kept for 4 weeks; synthetic full every Saturday\n- Encryption: "
        "enabled (password-based)\n- Target repository: Repo-Main"
    ),
    (
        "Daily-VMs runs every day at 10:00 PM and keeps restore points for two weeks (Retention policy: Days, 14), with "
        "weekly GFS backups retained 4 weeks. Backup encryption is on. It writes to Repo-Main (D:\\Backups on "
        "repo-win01)."
    ),
    (
        "| Setting | Value |\n|---|---|\n| Schedule | Everyday 22:00 |\n| Retention | 14 days; GFS weekly: 4 weeks |\n| "
        "Encryption | Enabled |\n| Repository | Repo-Main |"
    ),
]

BAD = {
    "schedule": "Daily-VMs runs daily at 02:00, keeps 14 days with GFS weekly for 4 weeks, is encrypted and writes to "
    "Repo-Main.",
    "retention": "Daily-VMs runs daily at 22:00, keeps 7 restore points with GFS weekly for 4 weeks, is encrypted and "
    "writes to Repo-Main.",
    "gfs_weekly": "Daily-VMs runs daily at 22:00, keeps 14 days, no GFS, is encrypted and writes to Repo-Main.",
    "encryption": "Daily-VMs runs daily at 22:00, keeps 14 days with GFS weekly for 4 weeks, writes to Repo-Main.",
    "repository": "Daily-VMs runs daily at 22:00, keeps 14 days with GFS weekly for 4 weeks, is encrypted and writes "
    "to Repo-DR.",
}
"""Answers that each miss one fact."""


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G1-04",
        inputs=CaseInputs(
            question="How is the Daily-VMs job configured — schedule, retention, encryption and target repository?",
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G1", "base_stand": "1.2"},
        evaluators=[
            # list_jobs is the answer, by name or by id; list_repositories (the repository's name) is a read the
            # case allows on top of it.
            ToolCorrectness(expected_tools=["list_jobs"], allow_extra=True),
            *tool_budget(3),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "encryption_enabled",
                "The output says that backup encryption is enabled for the job.",
            ),
            _judge(
                "configuration_not_state",
                "The output describes the job's configuration and does not present the job's live state, such as "
                "when the job last ran, its last result or its progress, as part of its configuration. The "
                "question does not ask about the job's live state.",
            ),
            _judge(
                "no_invented_settings",
                "The output does not attribute to the job any setting that the expected output does not support, "
                "for example a monthly or yearly GFS retention, an active full schedule, a backup window, a "
                f"specific proxy, or a retry policy other than {_RETRY_COUNT} retries {_RETRY_MINUTES} minutes "
                "apart.",
            ),
        ],
    )
