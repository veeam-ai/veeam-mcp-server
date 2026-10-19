# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G2-03: the protected workloads with no new restore point in the last 24 hours (server time)."""

from datetime import timedelta
from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case

import stand
from cases import CaseInputs, Environment, judge, tool_budget
from cases.patterns import any_of, clock, day, days, name, near
from evaluators import RESTORE_POINT_READS, FactsPresent, ToolsCalled, ToolsNotCalled
from stand.ids import B10, B11, T0
from stand.protected import OBJECTS, POINTS
from vbr_models.protected_objects import BackupObject

# ---- What VBR serves: the base stand. Three workloads of active jobs are stale: sql-prod-01 (last night's SQL-Prod
# run failed for it), legacy-erp-01 (its job Legacy-Archive is disabled) and laptop-fin-01 (offline). Three more are
# stale but belong to no job: old-fs-01 and old-app-01 (the orphaned FileApp-Weekly backup) and erp-db-2024
# (the imported backup).

ENVIRONMENT: Environment = stand.environment()

# ---- What a correct answer says, derived from the data above.

WINDOW_START = T0 - timedelta(hours=24)
LATEST = {obj.name: POINTS[obj.name][0].creation_time for obj in OBJECTS}
_STALE = [obj for obj in OBJECTS if LATEST[obj.name] < WINDOW_START]
_ORPHANED_OR_IMPORTED = [obj for obj in _STALE if obj.backup_id in (B10, B11)]
_WITH_JOB = [obj for obj in _STALE if obj not in _ORPHANED_OR_IMPORTED]
_FRESH = [obj for obj in OBJECTS if obj not in _STALE]
assert [obj.name for obj in _WITH_JOB] == ["sql-prod-01", "legacy-erp-01", "laptop-fin-01"]


def _age(obj: BackupObject) -> timedelta:
    return T0 - LATEST[obj.name]


def _describe(obj: BackupObject) -> str:
    age = _age(obj)
    hours = age.total_seconds() / 3600
    when = f"{hours:.0f} hours" if age < timedelta(days=2) else f"{age.days} days"
    return f"{obj.name} (latest point {LATEST[obj.name]:%Y-%m-%d %H:%M}, about {when} ago)"


EXPECTED = (
    f"Server time is {T0:%Y-%m-%d %H:%M}, so the window starts {WINDOW_START:%Y-%m-%d %H:%M}. Workloads with an "
    f"active job and no restore point in the last 24 hours: {', '.join(_describe(obj) for obj in _WITH_JOB)}. "
    "sql-prod-01 was not processed by last night's SQL-Prod run (it failed for this VM); the Legacy-Archive job "
    "of legacy-erp-01 is disabled; laptop-fin-01 is offline. Also older than 24 hours, but with no job at all: "
    f"{', '.join(_describe(obj) for obj in _ORPHANED_OR_IMPORTED)} - old-fs-01 and old-app-01 are only in the "
    "orphaned backup FileApp-Weekly, erp-db-2024 only in the imported backup ERP-Nightly; they can be "
    "listed with that note or excluded for that reason. Every other protected object has a point in the window, "
    "including sql-dev-01 (about 7 hours ago, and a new run is in progress). new-app-01 is in the Test-NewApp job "
    "but has never been backed up, so it is not a protected object."
)
"""Ground truth for the judges."""


def _when(obj: BackupObject) -> str:
    """When the object's newest point is from, as an answer gives it: its date, or its age.

    The date alone is enough only where no fresh point carries the same date; otherwise the time must come with it.
    """
    latest, age = LATEST[obj.name], _age(obj)
    hours = age.total_seconds() / 3600
    whole_days = age.days
    ages = [
        rf"(?<![\d.])({int(hours)}|{round(hours)}|{hours:.1f})\s*(h\b|hrs?\b|hours?)",
        rf"(?<![\d.]){whole_days}\s*(d\b|days?),?\s*(and\s+)?\d{{1,2}}\s*(h\b|hrs?\b|hours?)",
    ]
    if age < timedelta(days=2):  # 32.8 hours: "1.4 days", "over a day", "a day and a half"
        ages += [rf"(?<![\d.]){hours / 24:.1f}\s*days?", r"(over|more\s+than|about)\s+(a|one|1)\s+day",
                 r"a\s+day\s+and\s+a\s+half"]  # fmt: skip
    else:
        ages.append(days(round(age.total_seconds() / 86400), slack=1))
    if age >= timedelta(days=14):
        ages.append(r"(?<![\d.])(3|three|3\.5)\+?\s*weeks?")
    stamp = rf"(?:{day(latest, weekday=False)})[^\n]{{0,25}}?{clock(latest)}"
    # a date alone names the point if no fresh point carries it
    unique_day = all(LATEST[other.name].date() != latest.date() for other in _FRESH)
    return any_of(stamp, *ages, *([day(latest, weekday=False)] if unique_day else []))


FACTS = {f"stale_{obj.name}": near(name(obj.name), _when(obj), 220) for obj in _WITH_JOB}
"""Case-insensitive regexes, one per fact, that a correct answer must match: each stale workload with its age or
the time of its latest point, on the same line or under the same bullet."""

_ALLOWED = (
    "It is acceptable, and not a violation, to ask for or state the RPO threshold it assumed (24 hours), to mention "
    "new-app-01 (in the Test-NewApp job but never backed up, so not a protected object), to mention that sql-prod-01 "
    "failed in last night's run, that the Legacy-Archive job is disabled or that laptop-fin-01 is offline, and either "
    "to list old-fs-01, old-app-01 and erp-db-2024 with the note that they exist only in an orphaned or imported "
    "backup with no job, or to exclude them for that reason."
)

GOOD = [
    (
        "Server time: 2026-10-07 09:00 (CEST), so the window is since 2026-10-06 09:00.\n\n"
        "**No restore point in the last 24 hours (active jobs):**\n"
        "- **sql-prod-01**\n  - Latest restore point: 2026-10-06 00:14\n  - About 33 hours old - last night's SQL-Prod "
        "run failed for it\n"
        "- **legacy-erp-01**\n  - Latest: 2026-09-12 03:04 (25 days)\n  - Its job Legacy-Archive is disabled\n"
        "- **laptop-fin-01**\n  - Latest: 2026-10-01 12:04 (~6 days)\n  - The laptop is offline\n\n"
        "Also stale but without a job: old-fs-01 and old-app-01 (orphaned FileApp-Weekly backup) and erp-db-2024 "
        "(imported backup)."
    ),
    (
        "| Workload | Latest point | Age |\n|---|---|---|\n| sql-prod-01 | Oct 6, 00:14 | 32.8 h |\n"
        "| legacy-erp-01 | Sep 12 | 25 days |\n| laptop-fin-01 | 1 Oct 2026 12:04 | 5 days 21 hours |\n\n"
        "old-fs-01, old-app-01 and erp-db-2024 are older too, but they only exist in orphaned/imported backups with no "
        "job, so I left them out. Everything else, including sql-dev-01 (7 h), has a point from the last 24 hours."
    ),
    (
        "Three workloads missed their RPO: sql-prod-01 (last point 06.10.2026 00:14, ~33 hours ago), legacy-erp-01 "
        "(12 September, over 3 weeks ago - job disabled) and laptop-fin-01 (last backed up 6 days ago, offline)."
    ),
]

BAD = {
    "stale_sql-prod-01": "Stale: legacy-erp-01 (25 days) and laptop-fin-01 (6 days). sql-prod-01 was backed up "
    "on Oct 6 like the other VMs.",
    "stale_legacy-erp-01": "Stale: sql-prod-01 (33 hours) and laptop-fin-01 (6 days). legacy-erp-01 is in a "
    "disabled job.",
    "stale_laptop-fin-01": "Stale: sql-prod-01 (33 hours), legacy-erp-01 (25 days). laptop-fin-01 is offline.",
}


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    fresh = ", ".join(obj.name for obj in _FRESH)
    return Case(
        name="G2-03",
        inputs=CaseInputs(
            question="Which workloads haven't had a new restore point in the last 24 hours?",
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G2", "base_stand": "1.8, 1.9"},
        evaluators=[
            # Restore points come from list_restore_points (every point carries its object's name) or from
            # list_protected_objects(id=...); either road is fine, and the plan's walk of one call per object fits
            # the budget, as do list_backups / list_jobs to mark the orphaned objects.
            ToolsCalled("restore_points_read", RESTORE_POINT_READS),
            *tool_budget(len(OBJECTS) + 4),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "orphans_explained",
                "The output either lists old-fs-01, old-app-01 and erp-db-2024 with a note that they exist only in an "
                "orphaned or imported backup and have no job, or explicitly excludes them for that reason; it does not "
                "list them as ordinary workloads with an active job.",
            ),
            _judge(
                "no_sql_dev",
                "The output does not list sql-dev-01 among the workloads without a restore point in the last 24 "
                "hours: its latest point is about 7 hours old.",
            ),
            _judge(
                "no_fresh_objects",
                f"The output does not list any of these, which all have a point in the last 24 hours, as lacking "
                f"one: {fresh}.",
            ),
            _judge(
                "server_clock",
                "The ages or the window the output gives are measured from the backup server's time in the expected "
                "output (2026-10-07 09:00), not from some other clock. Do not use your own notion of the current date "
                "or time; compare only with the expected output.",
            ),
            _judge(
                "not_all_protected",
                "The output does not claim that everything is protected or that all workloads have a recent point.",
            ),
        ],
    )
