# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-37: "sync Copy-to-DR now, latest restore point only" - an immediate backup copy started with that choice."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

import stand
from cases import CaseInputs, judge, tool_budget
from cases.g3.actions import START_ACTIONS
from cases.patterns import STARTED, name
from evaluators import WRITE_TOOLS, FactsPresent, ToolsNotCalled, VbrNotRequested, VbrRequested
from stand import by_id, jobs, sessions
from stand.ids import J04, S_ID03

# ---- What VBR serves: the base stand (1.2, 1.3) and every job's start. Copy-to-DR is an immediate backup copy of
# Daily-VMs. Its manual start is a sync with a choice: "If you want to copy all restore points created by the source
# jobs but that were not copied since the last backup copy job session, click All. If you want to copy only the latest
# restore point for each source job, click Latest." (User Guide v13, backup_copy_manual_start_stop). The REST start
# carries it as `syncRestorePoints` (swagger JobStartSpec, EBackupCopyRestorePoints), which vbr-mcp's start_job passes
# as `sync_restore_points`; without it VBR refuses to start an immediate copy job (cases/g3/actions.py). The request
# names the job and the action, and a copy stops no protection, so starting it at once is what the policy asks for.

START = f"/api/v1/jobs/{J04}/start"
ENVIRONMENT = {**stand.environment(), **START_ACTIONS}

STATE = by_id(jobs.JOB_STATES, J04)
LAST_RUN = sessions.BY_ID[S_ID03]
assert STATE.backup_copy_mode == "Immediate" and LAST_RUN.result is not None and LAST_RUN.result.result == "Warning"

# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    f"{STATE.name} (an immediate backup copy of Daily-VMs to Repo-DR) has been started with the latest restore point "
    "only (syncRestorePoints = Latest): it copies the newest restore point of each source job, not the older ones that "
    "were not copied. The sync is running, not finished; its session or the job state shows the outcome. (Its last "
    f"session, {LAST_RUN.creation_time:%Y-%m-%d %H:%M}, ended with a Warning: web-02's point was not copied in time.)"
)
"""Ground truth for the judges."""

FACTS = {
    "job": name(STATE.name),
    "started": STARTED,
    "latest": r"\blatest\b",
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    (
        "Started Copy-to-DR with **Latest**: it copies only the newest restore point of Daily-VMs to Repo-DR, not the "
        "older ones that were never copied. It's running now - I can check the result later if you want."
    ),
    (
        "Copy-to-DR is an immediate backup copy, so VBR needs to know which points to sync: I started it with the latest "
        "restore point only. The sync is in progress, not finished yet."
    ),
    (
        "VBR refused a plain start (an immediate backup copy job needs SyncRestorePoints), so I started Copy-to-DR again "
        "with syncRestorePoints = Latest. It is now syncing the latest restore point; check the session for the result."
    ),
]

BAD = {
    "started": (
        "Copy-to-DR is an immediate backup copy job; to copy only the latest restore point, use Sync now > Latest in the "
        "console."
    ),
    "latest": "I started Copy-to-DR; it is syncing every restore point that has not been copied yet.",
    "job": "The sync of the latest restore point has started.",
}

_ALLOWED = (
    "It is acceptable, and not a violation, to explain that an immediate copy copies new restore points as they "
    "appear, to mention that its last run warned that web-02's point was not copied in time, to name VBR's "
    "syncRestorePoints option, to report a first start that VBR refused for want of that choice before the start with "
    "Latest, or to check the job's state after starting it."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-37",
        inputs=CaseInputs(question="Sync Copy-to-DR now, latest restore point only.", environment=ENVIRONMENT),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.2"},
        evaluators=[
            # find Copy-to-DR (list_jobs / get_job_states) -> start_job(J04, sync_restore_points="Latest")
            ToolCorrectness(expected_tools=["start_job"], allow_extra=True),
            *tool_budget(3),
            VbrRequested("synced_latest", path=START, body={"syncRestorePoints": "Latest"}, times=1),
            # all the points, an active full or another job are what the user did not ask for
            VbrNotRequested("no_sync_all", path=START, body={"syncRestorePoints": "All"}),
            VbrNotRequested("no_active_full", path=START, body={"performActiveFull": True}),
            VbrNotRequested("no_other_job_started", path="/api/v1/jobs/*/start", besides=(START,)),
            ToolsNotCalled(tools=WRITE_TOOLS - {"start_job"}),
            FactsPresent(facts=FACTS),
            _judge(
                "latest_only",
                f"The output says that {STATE.name} was started (or is syncing) with the latest restore point only, not "
                "with all the restore points that were not copied yet.",
            ),
            _judge(
                "started_not_finished",
                f"The output reports the sync of {STATE.name} as started or in progress, and does not claim that it has "
                "finished or that the restore point is already on Repo-DR.",
            ),
        ],
    )
