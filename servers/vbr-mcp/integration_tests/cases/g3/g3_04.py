# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-04: re-enable the disabled Legacy-Archive job, whose target has little free space."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import MULTI_TURN, CaseInputs, Environment, confirm, judge, tool_budget
from cases.patterns import any_of, clock, gb, name, percent
from evaluators import WRITE_TOOLS, FactsPresent, ToolsNotCalled, VbrNotRequested, VbrRequested
from stand import by_name, environment, replace
from stand.ids import J07, T0, at
from stand.jobs import JOB_STATES, JOBS
from stand.protected import points_of
from stand.repositories import REPOSITORY_STATES
from vbr_mock.markers import VbrAction

# ---- What VBR serves: the base stand, where Legacy-Archive (legacy-erp-01 to Repo-Branch, daily at 03:00) has been
# disabled since its last run 25 days ago, and Repo-Branch has 90 GB free of 600 GB. VBR enables a job with 204; it then
# runs on its schedule again (User Guide v13, disabling_jobs), and its state reads idle with the next run.

LEGACY_ARCHIVE = by_name(JOB_STATES, "Legacy-Archive")
TARGET = by_name(REPOSITORY_STATES, "Repo-Branch")
FREE_PERCENT = round(TARGET.free_gb / TARGET.capacity_gb * 100)
LAST_POINT = points_of("legacy-erp-01")[0]
DAYS_SINCE = (T0 - LAST_POINT.creation_time).days
ENABLE_PATH = f"/api/v1/jobs/{J07}/enable"
NEXT_RUN = at(8, 3, 0)

ENVIRONMENT: Environment = environment() | {
    ENABLE_PATH: VbrAction(
        effects={
            "/api/v1/jobs": (enabled := replace(JOBS, J07, is_disabled=False)),
            f"/api/v1/jobs/{J07}": by_name(enabled, LEGACY_ARCHIVE.name),
            "/api/v1/jobs/states": replace(JOB_STATES, J07, status="Stopped", next_run=NEXT_RUN),
        }
    ),
}

# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    f"{LEGACY_ARCHIVE.name} has been enabled. It was not started now: it runs on its schedule, next at 03:00 tonight "
    f"({NEXT_RUN:%Y-%m-%d %H:%M}). Its target {TARGET.name} has only {TARGET.free_gb:.0f} GB free of "
    f"{TARGET.capacity_gb:.0f} GB ({FREE_PERCENT}%), which may not be enough for the next run, the first in "
    f"{DAYS_SINCE} days. legacy-erp-01 still consumes a license instance: it was backed up less than 31 days ago, and "
    "it keeps consuming one once the job runs again (without the job it would be released 31 days after its last "
    "backup)."
)
"""Ground truth for the judges."""

FACTS = {
    "job": name(LEGACY_ARCHIVE.name),
    "enabled": r"\b(re-?)?enabled\b",
    "schedule": clock(NEXT_RUN),
    "free_space": any_of(
        gb(TARGET.free_gb), r"(?<![\d.])90(\.0+)?\s*(GB\s*)?(free\s*)?(of|/|out\s+of)\s*600", percent(FREE_PERCENT)
    ),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    (
        f"[Turn 1]\n{LEGACY_ARCHIVE.name} has been re-enabled. It isn't started now: it will run on its schedule, next at "
        "03:00 tomorrow (2026-10-08). Heads-up: its target Repo-Branch has only 90 GB free (15%), which may be tight, and "
        "its last backup of legacy-erp-01 is 25 days old.\n\n[Turn 2]\n(not asked: the agent already called enable_job)"
    ),
    (
        f"[Turn 1]\n{LEGACY_ARCHIVE.name} has been disabled since its last run on Sep 12. Before I enable it: its "
        "repository Repo-Branch has just 90.0 GB free of 600 GB. The job runs daily at 3:00 AM. Enable it anyway?\n\n"
        f"[Turn 2]\nDone - {LEGACY_ARCHIVE.name} is enabled again; the next run is tonight at 3 AM."
    ),
    (
        f"[Turn 1]\n| Job | State | Next run | Target free |\n|---|---|---|---|\n| {LEGACY_ARCHIVE.name} | enabled | "
        "2026-10-08 03:00 | 90 GB of 600 GB |\n\nIt will run on schedule; I did not start it.\n\n[Turn 2]\n"
        "(not asked: the agent already called enable_job)"
    ),
]
"""Answers a correct agent could give: every fact must match each."""

BAD = {
    "free_space": f"{LEGACY_ARCHIVE.name} has been enabled; the next run is at 03:00 tomorrow.",
    "schedule": f"{LEGACY_ARCHIVE.name} has been enabled. Repo-Branch has only 90 GB free.",
    "enabled": f"{LEGACY_ARCHIVE.name} is disabled. Its next run would be at 03:00 and Repo-Branch has 90 GB free. Do "
    "you want me to turn it back on?",
}
"""Fact -> an answer that misses it."""

_ALLOWED = (
    f"{MULTI_TURN} "
    "It is acceptable, and not a violation, to ask before enabling because of the low space, to mention that "
    f"the last restore point of legacy-erp-01 is {DAYS_SINCE} days old, that the first run after the pause may be "
    "larger than usual, or that legacy-erp-01 keeps consuming a license instance."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-04",
        inputs=CaseInputs(
            question="Re-enable the Legacy-Archive job.",
            # a write: done at once, but asking because of the space is allowed
            follow_ups=[confirm("enable_job", text="Yes, enable Legacy-Archive.")],
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.2, 1.4"},
        evaluators=[
            # list_jobs or get_job_states -> (opt.) list_repositories -> enable_job(J07)
            ToolCorrectness(expected_tools=["enable_job"], allow_extra=True),
            *tool_budget(4, turns=2),
            VbrRequested("legacy_archive_enabled", path=ENABLE_PATH, times=1),
            VbrRequested("one_job_enabled", path="/api/v1/jobs/*/enable", accepted=False, times=1),
            VbrNotRequested("not_started", path="/api/v1/jobs/*/start"),
            ToolsNotCalled(tools=WRITE_TOOLS - {"enable_job"}),
            FactsPresent(facts=FACTS),
            _judge(
                "runs_on_schedule",
                f"The output says {LEGACY_ARCHIVE.name} will run on its schedule (daily at 03:00), and does not say it "
                "was started now.",
            ),
            _judge(
                "space_warning",
                f"The output warns that the target repository {TARGET.name} has only {TARGET.free_gb:.0f} GB free.",
            ),
            _judge(
                "no_wrong_license_claim",
                "The output does not claim that enabling the job starts consuming a license that legacy-erp-01 does not "
                "consume now: if it mentions licensing, it is that legacy-erp-01 keeps (or will keep) its instance.",
            ),
        ],
    )
