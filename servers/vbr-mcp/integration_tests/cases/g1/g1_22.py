# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G1-22: more sessions than one page — how many one job ran in 30 days, and how many failed."""

from datetime import datetime, timedelta
from functools import partial
from typing import Literal

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import CaseInputs, Environment, judge, tool_budget
from cases.patterns import number
from evaluators import FactsPresent, ToolsNotCalled
from stand import backups, environment, jobs, protected, sessions
from stand.ids import GB, R01, T0, ZERO, at, mnemonic
from stand.inventory import VMS
from vbr_models import VbrModel
from vbr_models.jobs import BackupJob, BackupSchedule, JobState, RetentionPolicy, ScheduleDaily, ScheduleRetry
from vbr_models.protected_objects import RestorePoint, ViBackupObject
from vbr_models.sessions import Session, SessionProgress

# ---- What VBR serves: the base stand plus, as the case's delta, a job that backs up test-vm-01 every hour: far more
# sessions than one page (vbr-mcp pages by 200). It ran from 08-20, was disabled from 09-05 to 09-07 for maintenance
# and has run every hour since 2026-09-08 00:05, so where exactly "the last 30 days" starts (a rolling 720 hours, or
# 09-07 on either clock) does not change the count. Its runs are not retried (an hourly job; retry is off), and none
# is canceled: a failed session is a failed run, and nothing needs collapsing. vbr-mcp can count without paging
# (list_sessions count_only=True) or page through every session; both get exact numbers.

J11 = mnemonic("10000000", 11)
JOB_NAME = "Periodic-Small-VM"
VM = "test-vm-01"
B12, O18 = mnemonic("52000000", 12), mnemonic("50000000", 18)


class SchedulePeriodically(VbrModel):
    """``SchedulePeriodicallyModel``: run every ``frequency`` ``periodicallyKind``."""

    is_enabled: bool
    periodically_kind: Literal["Hours", "Minutes"]
    frequency: int
    start_time_within_an_hour: int | None = None


class PeriodicSchedule(BackupSchedule):
    """``BackupScheduleModel`` with its ``periodically`` part, which the base stand's jobs do not use."""

    periodically: SchedulePeriodically


class PeriodicBackupJob(BackupJob):
    """``BackupJobModel`` of a job on a periodic schedule."""

    schedule: PeriodicSchedule


_job = jobs.vm_job(
    J11,
    JOB_NAME,
    [VM],
    R01,
    RetentionPolicy(type="RestorePoints", quantity=14),
    jobs.NOT_ENCRYPTED,
    jobs.daily("00:00"),
)
JOB = PeriodicBackupJob.model_validate({
    **_job.model_dump(by_alias=False),
    "schedule": PeriodicSchedule(
        run_automatically=True,
        daily=ScheduleDaily(is_enabled=False),
        retry=ScheduleRetry(is_enabled=False),
        periodically=SchedulePeriodically(
            is_enabled=True, periodically_kind="Hours", frequency=1, start_time_within_an_hour=5
        ),
    ),
})  # fmt: skip

FAILED_MESSAGE = "Failed to process 1 of 1 VMs. See the session log for details."
_RUN = timedelta(minutes=4, seconds=12)


def _runs(first_number: int, start: datetime, end: datetime, failed: int) -> list[Session]:
    """Hourly runs at :05 from ``start`` up to ``end``, ``failed`` of them (spread evenly) failed."""
    starts = []
    moment = start
    while moment < end:
        starts.append(moment)
        moment += timedelta(hours=1)
    failing = {round((k + 0.5) * len(starts) / failed) for k in range(failed)}
    return [
        sessions.session(
            first_number + n,
            JOB_NAME,
            begun,
            begun + _RUN,
            "Failed" if n in failing else "Success",
            message=FAILED_MESSAGE if n in failing else "",
            job_id=J11,
            platform="VMware",
        )
        for n, begun in enumerate(starts)
    ]


BEFORE_PAUSE = _runs(5_000, at(20, 0, 5, month=8), at(5, 0, 0, month=9), failed=9)
SINCE_RESUMED = _runs(6_000, at(8, 0, 5, month=9), T0, failed=37)
"""Every run since 2026-09-08 00:05, the last one at 08:05 today."""

WINDOW_START = T0 - timedelta(days=30)
IN_WINDOW = [s for s in SINCE_RESUMED if s.creation_time >= WINDOW_START]
assert len(IN_WINDOW) == len(SINCE_RESUMED)  # the pause holds the boundary
IN_WINDOW_FAILED = sum(1 for s in IN_WINDOW if s.result and s.result.result == "Failed")

_LAST = SINCE_RESUMED[-1]
_LAST_GOOD = [s for s in SINCE_RESUMED if s.result and s.result.result == "Success"][-14:][::-1]  # newest first

JOB_STATE = JobState(
    id=J11,
    name=JOB_NAME,
    type="VSphereBackup",
    description="",
    status="Stopped",
    last_run=_LAST.creation_time,
    last_result=_LAST.result.result if _LAST.result else "None",
    next_run=_LAST.creation_time + timedelta(hours=1),
    workload="Vm",
    repository_id=R01,
    repository_name="Repo-Main",
    objects_count=1,
    session_id=_LAST.id,
    high_priority=False,
    progress_percent=100,
    session_progress=SessionProgress(
        duration="00:04:12",
        processing_rate="64 MB/s",
        bottleneck="Source",
        processed_size=40 * GB,
        read_size=2 * GB,
        transferred_size=1 * GB,
        progress_percent=100,
    ),
)

BACKUP_OBJECT = ViBackupObject(
    id=O18,
    name=VM,
    type="VM",
    restore_points_count=len(_LAST_GOOD),
    last_run_failed=bool(_LAST.result and _LAST.result.result == "Failed"),
    backup_id=B12,
    object_id=VMS[VM].ref,
    vi_type="VirtualMachine",
)
POINTS = [
    RestorePoint(
        id=protected.point_id(BACKUP_OBJECT, index),
        name=VM,
        platform_name="VMware",
        platform_id=ZERO,
        creation_time=run.creation_time + timedelta(minutes=2),
        backup_id=B12,
        type="Full" if index == len(_LAST_GOOD) - 1 else "Increment",
        allowed_operations=protected.VMWARE_OPERATIONS,
        malware_status="Clean",
        backup_object_id=O18,
    )
    for index, run in enumerate(_LAST_GOOD)
]

ENVIRONMENT: Environment = environment(
    jobs=[*jobs.JOBS, JOB],
    job_states=[*jobs.JOB_STATES, JOB_STATE],
    sessions=sorted([*sessions.SESSIONS, *BEFORE_PAUSE, *SINCE_RESUMED], key=lambda s: s.creation_time, reverse=True),
    backup_objects=[*protected.BACKUP_OBJECTS, BACKUP_OBJECT],
    restore_points=sorted([*protected.RESTORE_POINTS, *POINTS], key=lambda p: p.creation_time, reverse=True),
    backups=[
        *backups.BACKUPS,
        backups.backup(B12, JOB_NAME, J11, R01, "VSphereBackup", "VMware", at(20, 0, 5, month=8)),
    ],
    backup_contents={B12: [BACKUP_OBJECT]},
)

# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    f"In the last 30 days the {JOB_NAME} job ran {len(IN_WINDOW)} sessions (every hour since 2026-09-08 00:05; it was "
    f"disabled from 09-05 to 09-07), and {IN_WINDOW_FAILED} of them failed. These are exact counts over the complete "
    "list, not estimates; its runs are not retried, so each failed session is one failed run."
)
"""Ground truth for the judges."""

FACTS = {
    "total": number(len(IN_WINDOW), decimals=0),
    "failed": number(IN_WINDOW_FAILED, decimals=0),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

_ALLOWED = (
    "It is acceptable, and not a violation, to count with count_only or by paging through every session, to get the "
    "failed count with a separate call, to give the failure rate as a percentage, to mention the pause from 09-05 "
    "to 09-07 or that the job runs hourly, or to warn that the listing is large."
)

GOOD = [
    (
        f"In the last 30 days {JOB_NAME} ran {len(IN_WINDOW)} sessions, and {IN_WINDOW_FAILED} of them failed "
        f"({IN_WINDOW_FAILED / len(IN_WINDOW):.1%})."
    ),
    (
        f"| Last 30 days | Sessions |\n|---|---|\n| Total | {len(IN_WINDOW)} |\n| Failed | {IN_WINDOW_FAILED} |\n\n"
        "The job runs every hour; it was paused from Sep 5 to Sep 7."
    ),
    f"{IN_WINDOW_FAILED} out of {len(IN_WINDOW):,} runs failed.",
]
"""Answers a correct agent could give: every fact must match each of them."""

BAD = {
    "total": f"The job ran 200 sessions in the last 30 days; {IN_WINDOW_FAILED} failed.",
    "failed": f"{len(IN_WINDOW)} sessions ran, and about 10 of them failed.",
}
"""Per fact, an answer that gets that fact wrong: the fact must not match it."""


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G1-22",
        inputs=CaseInputs(
            question=f"How many sessions did the {JOB_NAME} job run in the last 30 days, and how many of them failed?",
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G1", "base_stand": "1.3 + delta"},
        evaluators=[
            # list_sessions is the answer, maybe twice (the failed ones on their own), by count_only or paging;
            # list_jobs (the job's id) and get_server_status (what "now" is) are reads the case allows on top.
            ToolCorrectness(expected_tools=["list_sessions"], allow_extra=True),
            *tool_budget(4),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "not_first_page",
                "The output does not give 200 (one page of results) as the number of sessions, and does not "
                "present a partial count as the total.",
            ),
            _judge(
                "exact_counts",
                f"The output states {len(IN_WINDOW)} sessions and {IN_WINDOW_FAILED} failures as exact numbers, not "
                'hedged as approximate ("about", "around", "at least").',
            ),
            _judge(
                "only_this_job",
                f"The counts the output gives are of the {JOB_NAME} job's sessions only, not of every session on the "
                "server.",
            ),
        ],
    )
