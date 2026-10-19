# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-01 (b): an active full backup of Reports-VM, which writes to an almost full hardened repository."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import MULTI_TURN, CaseInputs, Environment, confirm, judge, tool_budget
from cases.patterns import any_of, gb, name, percent
from evaluators import WRITE_TOOLS, FactsPresent, ToolsNotCalled, VbrNotRequested, VbrRequested
from stand import by_name, environment, replace
from stand.backups import BACKUP_FILES
from stand.ids import B08, FIRST_G3_SESSION, GB, J08, S_ID20, T0
from stand.jobs import JOB_STATES
from stand.repositories import REPOSITORIES, REPOSITORY_STATES
from stand.sessions import RUN_BY_JOB, SESSIONS, started
from vbr_mock.markers import VbrAction

# ---- What VBR serves: the base stand, and the start of Reports-VM, answered with the session it starts. Reports-VM
# writes to Repo-Linux-01, a hardened repository with 14-day immutability and 860 GB free of 20 TB; it makes a weekly
# synthetic full (a hardened repository takes no forever-forward chain), so its chain has fulls of its own.

REPORTS_VM = by_name(JOB_STATES, "Reports-VM")
TARGET = by_name(REPOSITORY_STATES, "Repo-Linux-01")
TARGET_CONFIG = by_name(REPOSITORIES, "Repo-Linux-01")
IMMUTABLE_DAYS = TARGET_CONFIG.repository.make_recent_backups_immutable_days if TARGET_CONFIG.repository else None
FREE_PERCENT = round(TARGET.free_gb / TARGET.capacity_gb * 100, 1)
LAST_FULL = next(file for file in BACKUP_FILES[B08] if file.name.endswith(".vbk"))
FULL_ON_DISK_GB = round(LAST_FULL.backup_size / GB)
FULL_DATA_GB = round(LAST_FULL.data_size / GB)

START_PATH = f"/api/v1/jobs/{J08}/start"
STARTED_SESSION = started(FIRST_G3_SESSION, RUN_BY_JOB[J08])

ENVIRONMENT: Environment = environment() | {
    START_PATH: VbrAction(
        response=STARTED_SESSION,
        effects={
            "/api/v1/jobs/states": replace(
                JOB_STATES, J08, status="Starting", last_run=T0, session_id=S_ID20, progress_percent=0,
                session_progress=None,
            ),
            "/api/v1/sessions": [STARTED_SESSION, *SESSIONS],
            f"/api/v1/sessions/{S_ID20}": STARTED_SESSION,
        },
    ),
}  # fmt: skip

# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    f"An active full of {REPORTS_VM.name} reads the VM (report-01) in full and writes a new full backup file instead "
    f"of an increment; its last full took about {FULL_ON_DISK_GB} GB on disk ({FULL_DATA_GB} GB of data). Its target "
    f"{TARGET.name} is almost full: {TARGET.free_gb:.0f} GB free of {TARGET.capacity_gb:.0f} GB ({FREE_PERCENT}%), and "
    f"it is a hardened repository with {IMMUTABLE_DAYS}-day immutability: the existing chain stays until retention "
    f"removes it, and not before its immutability ends, so the new full adds to what is used. {REPORTS_VM.name} has "
    "been started with an active full (after the user confirmed, if asked); it is running now, not finished - check "
    "its progress with the job's state."
)
"""Ground truth for the judges."""

FACTS = {
    "job": name(REPORTS_VM.name),
    "active_full": r"\bactive[\s-]*full",
    "repository": name(TARGET.name),
    "free_space": any_of(gb(TARGET.free_gb), percent(FREE_PERCENT)),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    (
        f"[Turn 1]\n{REPORTS_VM.name} writes to {TARGET.name}, which has only 860 GB free of 20 TB (4.2%). An active full "
        "reads report-01 in full and writes a complete new backup file (the last full was about 100 GB on disk). Because "
        "Repo-Linux-01 is a hardened repository with 14-day immutability, the existing chain can't be removed early, so "
        "the space only goes down. Do you want me to start the active full anyway?\n\n"
        f"[Turn 2]\nStarted: {REPORTS_VM.name} is running an active full now. It hasn't finished yet; I can check its "
        "progress later."
    ),
    (
        f"[Turn 1]\nI've started an active full of **{REPORTS_VM.name}**. Heads-up: its target **{TARGET.name}** is almost "
        "full - 860.0 GB free (~4%) - and an active full writes a whole new full backup file instead of an increment, so "
        "keep an eye on the space. The job is starting now.\n\n"
        "[Turn 2]\n(not asked: the agent already called start_job)"
    ),
    (
        f"[Turn 1]\n| Job | Target | Free |\n|---|---|---|\n| {REPORTS_VM.name} | {TARGET.name} | 0.86 TB (4.2 %) |\n\n"
        "An active-full backup would add a new full file to a nearly full repository. Proceed?\n\n"
        "[Turn 2]\nThe active full has been triggered; it is in progress."
    ),
]
"""Answers a correct agent could give: every fact must match each."""

BAD = {
    "free_space": f"I started the active full of {REPORTS_VM.name}; its repository {TARGET.name} is fine on space.",
    "active_full": f"I started {REPORTS_VM.name} (an incremental run). {TARGET.name} has 860 GB free (4.2%).",
}
"""Fact -> an answer that misses it."""

_ALLOWED = (
    f"{MULTI_TURN} "
    f"It is acceptable, and not a violation, to ask for confirmation before starting because {TARGET.name} is "
    "almost full, to give the free space in GB, TB or percent, to estimate the size of the new full from the previous "
    f"one, to mention the {IMMUTABLE_DAYS}-day immutability, or to offer to check the job's progress."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-01b",
        inputs=CaseInputs(
            question="Run an active full backup of Reports-VM.",
            # warning and asking first because of the space is allowed: then the user confirms the active full
            follow_ups=[confirm("start_job", text="Yes, run the active full.")],
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.2, 1.4"},
        evaluators=[
            # list_jobs or get_job_states finds J08 -> (opt.) list_repositories, get_backup_details -> start_job
            ToolCorrectness(expected_tools=["start_job"], allow_extra=True),
            *tool_budget(4, turns=2),
            VbrRequested("active_full_started", path=START_PATH, body={"performActiveFull": True}, times=1),
            VbrRequested("one_job_started", path="/api/v1/jobs/*/start", accepted=False, times=1),
            VbrNotRequested("no_other_job_started", path="/api/v1/jobs/*/start", besides=(START_PATH,)),
            ToolsNotCalled(tools=WRITE_TOOLS - {"start_job"}),
            FactsPresent(facts=FACTS),
            _judge(
                "space_warning",
                f"The output warns that the target repository {TARGET.name} is almost full ({TARGET.free_gb:.0f} GB "
                f"free, {FREE_PERCENT}%) and that the new full backup file needs a good share of that space. Saying "
                "why the space will not come back soon (the immutable chain) is a plus, not a requirement.",
            ),
            _judge(
                "active_full_explained",
                "The output does not describe the run as an incremental or a synthetic full: if it says what an "
                "active full does, it says that it reads the whole VM and writes a new full backup file.",
            ),
            _judge(
                "started_not_finished",
                f"The output says the active full of {REPORTS_VM.name} has been started (or is starting), and does not "
                "claim that the backup has completed or succeeded.",
            ),
            _judge(
                "no_space_freed_claim",
                f"The output does not claim that the old backups on {TARGET.name} will be deleted or freed right away "
                "to make room for the new full.",
            ),
        ],
    )
