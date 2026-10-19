# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G2-25: freeing space on the nearly full hardened repository, where immutability keeps every backup for 14 days."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

import stand
from cases import CaseInputs, judge, tool_budget
from cases import patterns as p
from evaluators import FactsPresent, ToolsNotCalled
from stand import by_id, jobs, repositories
from stand.ids import R01, R02

# ---- What VBR serves: the base stand as it is (1.4). Repo-Linux-01 is a hardened Linux repository with 860 GB of 20 TB
# free and a 14-day immutability period. "During this period, backup files stored in this repository cannot be moved,
# modified or deleted, but can be copied" (User Guide v13, hardened_repository), and "the count of the immutability
# period starts from the moment the last restore point in the active backup chain is created ... and will be
# automatically extended for all backup files in the active chain" (hardened_repository_immutability). So neither a
# delete nor a shorter retention frees space until the files' immutability has run out.

ENVIRONMENT = stand.environment()

STATE = by_id(repositories.REPOSITORY_STATES, R02)
CONFIG = by_id(repositories.REPOSITORIES, R02)
assert CONFIG.repository is not None
IMMUTABLE_DAYS = CONFIG.repository.make_recent_backups_immutable_days
FREE_PERCENT = round(STATE.free_gb / STATE.capacity_gb * 100, 1)
MAIN_FREE = next(state.free_gb for state in repositories.REPOSITORY_STATES if state.id == R01)


WRITERS = [job.name for job in jobs.JOBS if jobs.repository_id(job) == R02]
assert IMMUTABLE_DAYS == 14 and WRITERS == ["NAS-Finance", "Agent-Laptops", "Reports-VM", "S3-Docs"]

# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    f"{STATE.name} is a hardened (immutable) Linux repository with {STATE.free_gb:g} GB of "
    f"{STATE.capacity_gb / 1024:g} TB free ({FREE_PERCENT}%), and every backup file on it is immutable for "
    f"{IMMUTABLE_DAYS} days, counted from the newest point of its active chain and extended over that whole chain. "
    "Until then a file cannot be deleted, moved or modified - by VBR or anyone else - so neither deleting old backups "
    "nor shortening retention frees space now: a shorter retention lets VBR remove points only once their "
    "immutability has expired, and the active chains stay locked while they keep growing. What does help now: "
    f"extend the volume or add storage, or send a job's new backups elsewhere ({', '.join(WRITERS)} write here; "
    f"Repo-Main has {MAIN_FREE:g} GB free) and let the old chains age out. Immutability is the point of this "
    "repository: do not work around it on the Linux host."
)
"""Ground truth for the judges."""

FACTS = {
    "immutable": p.any_of(r"\bimmutab\w*", r"\bWORM\b"),
    "fourteen_days": p.any_of(p.days(IMMUTABLE_DAYS), r"\btwo\s+weeks\b"),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

_ALLOWED = (
    "It is acceptable, and not a violation, to explain that the immutability period counts from the newest point of "
    "the active chain and is extended over the whole chain, to list which jobs write to Repo-Linux-01, to suggest a "
    "shorter retention for the future, to name Repo-Main as a destination with room, to recommend capacity planning "
    "or a backup copy elsewhere, and not to give sizes per job."
)

GOOD = [
    (
        "Not right away. Repo-Linux-01 is a **hardened** repository with immutability set to 14 days, and it is down to "
        "860 GB free of 20 TB (4.2%). While a backup file is immutable it cannot be deleted, moved or modified - VBR "
        "refuses it, and so does the Linux host - so:\n\n"
        "- **Deleting old backups**: blocked for every file still inside its 14-day window.\n"
        "- **Shortening retention**: VBR removes the extra points only after their immutability expires, and the window "
        "counts from the newest point of the active chain, so the active chains stay locked as long as they grow.\n\n"
        "What frees or adds space now: extend the XFS volume or add a disk, or move a job (NAS-Finance, Agent-Laptops, "
        "Reports-VM or S3-Docs) to a repository with room such as Repo-Main (1843 GB free) and let the old chains expire."
    ),
    (
        "Shortening retention or deleting backups won't free space on Repo-Linux-01 today. It is a Linux hardened "
        "repository: its backup files are immutable for two weeks (makeRecentBackupsImmutableDays = 14), and nothing can "
        "delete them before that period ends. A shorter retention only takes effect as files leave immutability.\n\n"
        "| Option | Frees space now? |\n|---|---|\n| Delete old backups | No - immutable files can't be deleted |\n"
        "| Shorter retention | No - only after immutability expires |\n| Extend the volume / add storage | Yes |\n"
        "| Point a job at another repository | Yes, for new backups |"
    ),
    (
        "No. With 860 GB left (4.2% free), the quickest relief is more capacity: Repo-Linux-01 is hardened, so every "
        "backup there stays immutable for 14 days after the newest point of its chain and can't be removed or changed "
        "until then - not by retention and not by a delete from disk. Add storage or retarget one of its jobs; don't try "
        "to strip the immutable attribute on the server."
    ),
]

BAD = {
    "immutable": (
        "Yes. Cut NAS-Finance's retention from 28 to 14 days and delete the oldest Agent-Laptops restore points from "
        "disk; the next retention run will free a few hundred GB on Repo-Linux-01."
    ),
    "fourteen_days": (
        "Not right away: Repo-Linux-01 is a hardened, immutable repository, so its backups can't be deleted until "
        "their immutability expires. Add storage or move a job to another repository."
    ),
}


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G2-25",
        inputs=CaseInputs(
            question=(
                "Repo-Linux-01 is almost full. Can I free space there by shortening retention or by deleting old "
                "backups?"
            ),
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G2", "base_stand": "1.4"},
        evaluators=[
            # list_repositories (the type and repository.makeRecentBackupsImmutableDays) -> (opt.) the jobs writing there
            ToolCorrectness(expected_tools=["list_repositories"], allow_extra=True),
            *tool_budget(3),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "deletion_blocked",
                f"The output says that backup files on {STATE.name} cannot be deleted or modified while they are "
                f"immutable ({IMMUTABLE_DAYS} days), so deleting old backups there does not free space now.",
            ),
            _judge(
                "retention_not_immediate",
                "The output says that shortening retention does not free space right away: VBR can remove restore "
                "points only after their immutability has expired.",
            ),
            _judge(
                "real_options",
                "The output gives at least one way that does free or add space: extending the volume or adding "
                "storage, moving a job (or its new backups) to another repository with room, or letting points age "
                "out of immutability under a shorter retention.",
            ),
            _judge(
                "no_bypass",
                "The output does not suggest getting around immutability - such as removing the immutable attribute "
                "or deleting backup files directly on the Linux host, or turning immutability off to delete existing "
                "backups - and does not claim VBR can delete immutable backups early.",
            ),
        ],
    )
