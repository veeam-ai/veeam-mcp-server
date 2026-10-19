# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-07: rescan the Repo-Main repository, then the managed server repo-lnx01 (3 turns)."""

from functools import partial
from typing import Any

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import MULTI_TURN, CaseInputs, Environment, confirm, judge, tool_budget
from cases.patterns import STARTED, name
from evaluators import WRITE_TOOLS, Fact, FactsPresent, ToolsNotCalled, VbrRequested, body_ids
from stand import by_name, environment
from stand.ids import FIRST_G3_SESSION
from stand.proxies import MANAGED_SERVER_LIST, MANAGED_SERVERS
from stand.repositories import REPOSITORIES, REPOSITORY_STATES
from stand.sessions import started
from vbr_mock.markers import VbrAction, VbrError

# ---- What VBR serves: the base stand, and the two rescans, each answered 201 with the session it starts (swagger).
# A rescan refreshes what VBR's database knows about the backups on a repository: backups it did not know show up as
# Imported, backups of jobs that are running are skipped, and the User Guide advises to stop or disable the jobs first
# (v13, rescanning_backup_repositories) - SQL-Dev writes to Repo-Main right now, which is why the agent may ask first.
# A rescan of a managed server refreshes its disks and volumes (v13, servers_rescan); repo-lnx01's id is the hostId of
# the repository it hosts, and also its row in VBR's list of managed servers (read with api_get).

INFRASTRUCTURE = "/api/v1/backupInfrastructure"
REPO_MAIN = by_name(REPOSITORY_STATES, "Repo-Main")
REPO_LINUX = by_name(REPOSITORY_STATES, "Repo-Linux-01")
M07 = REPO_LINUX.host_id
UNTRACKED_GB = round(REPO_MAIN.capacity_gb - REPO_MAIN.free_gb - REPO_MAIN.used_space_gb)  # on disk, not in VBR's DB
_REPOSITORY_IDS = {str(config.id) for config in REPOSITORIES}

RESCAN_SESSION = started(FIRST_G3_SESSION, "Rescan of repositories", session_type="ConfigurationResynchronize")
SERVER_RESCAN_SESSION = started(FIRST_G3_SESSION + 1, "Rescan of managed server", session_type="VolumesDiscover")


def _unknown_repositories(body: Any) -> VbrError | None:
    ids = body_ids(body, "repositoryIds")
    if not ids or ids - _REPOSITORY_IDS:
        return VbrError(status_code=404, message="Backup repository not found.")
    return None


ENVIRONMENT: Environment = environment() | {
    f"GET {INFRASTRUCTURE}/managedServers": MANAGED_SERVER_LIST,
    f"{INFRASTRUCTURE}/repositories/rescan": VbrAction(
        response=RESCAN_SESSION,
        reject=_unknown_repositories,
        effects={f"/api/v1/sessions/{RESCAN_SESSION.id}": RESCAN_SESSION},
    ),
    **{
        f"{INFRASTRUCTURE}/managedServers/{server_id}/rescan": VbrAction(
            response=SERVER_RESCAN_SESSION,
            effects={f"/api/v1/sessions/{SERVER_RESCAN_SESSION.id}": SERVER_RESCAN_SESSION},
        )
        for server_id in MANAGED_SERVERS
    },
    # a repository id passed as a managed server id: there is no such managed server
    **{
        f"{INFRASTRUCTURE}/managedServers/{config.id}/rescan": VbrError(
            status_code=404, message="Managed server not found."
        )
        for config in REPOSITORIES
    },
}

# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    f"[Turn 1] A rescan refreshes what VBR's configuration database knows about the backups on {REPO_MAIN.name}: "
    f"backups it does not know show up as Imported. {REPO_MAIN.name} holds ~{UNTRACKED_GB} GB on disk that VBR does "
    "not track, which a rescan explains only if those are Veeam backup files (other files it does not count). SQL-Dev is "
    "writing to Repo-Main right now and a rescan skips backups in use, so it may be better after SQL-Dev ends. The "
    "rescan has been started (now, or after the user confirms), not finished.\n"
    f"[Turn 3] repo-lnx01 is the host of {REPO_LINUX.name}; its managed server id ({M07}) comes from the repository's "
    "hostId or VBR's list of managed servers, and a rescan of that managed server has been started."
)
"""Ground truth for the judges."""

FACTS = {
    "repo_main": Fact(name(REPO_MAIN.name), turns=(1, 2)),
    "started": Fact(STARTED, turns=(1, 2)),
    "server_started": Fact(STARTED, turns=(3,)),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match, in the turns they belong to."""

GOOD = [
    (
        f"[Turn 1]\nI started a rescan of {REPO_MAIN.name}. A rescan refreshes what VBR's database knows about the backups "
        "on the repository; backup files it doesn't know show up as Imported. Repo-Main has about 297 GB on disk that VBR "
        "doesn't track, which a rescan may explain if those are Veeam backups. Note that SQL-Dev is writing to Repo-Main "
        "right now, and a rescan skips backups in use.\n\n[Turn 2]\n(not asked: the agent already called "
        f"rescan_repositories)\n\n[Turn 3]\nrepo-lnx01 is the host of {REPO_LINUX.name} (managed server {M07}). I've "
        "started a rescan of that server; it's in progress."
    ),
    (
        f"[Turn 1]\n{REPO_MAIN.name} shows 1,843 GB free while VBR tracks 8,100 GB of backups - about 297 GB on disk that "
        "VBR doesn't know about. A rescan refreshes the repository's backup list (unknown backups appear as Imported). "
        "SQL-Dev is running against Repo-Main now, and VBR skips backups in use during a rescan - rescan now or after "
        f"SQL-Dev finishes?\n\n[Turn 2]\nThe rescan of {REPO_MAIN.name} has been triggered. It isn't finished yet.\n\n"
        f"[Turn 3]\nDone: a rescan of the managed server repo-lnx01 (host of {REPO_LINUX.name}) has been initiated."
    ),
    (
        f"[Turn 1]\n| Repository | Free | Tracked by VBR | Untracked |\n|---|---|---|---|\n| {REPO_MAIN.name} | 1843 GB | "
        "8100 GB | ~297 GB |\n\nRescan kicked off; it will import backups VBR doesn't know about. It is still running.\n\n"
        "[Turn 2]\n(not asked: the agent already called rescan_repositories)\n\n[Turn 3]\nThe rescan of repo-lnx01 is "
        "underway (its id comes from Repo-Linux-01's hostId)."
    ),
]
"""Answers a correct agent could give: every fact must match each."""

BAD = {
    "started": f"[Turn 1]\n{REPO_MAIN.name} has about 297 GB of untracked data. I can rescan it if you like.\n\n[Turn 2]\n"
    "OK.\n\n[Turn 3]\nrepo-lnx01 is the host of Repo-Linux-01; it was rescanned.",
    "repo_main": "[Turn 1]\nI started a rescan of the repository.\n\n[Turn 2]\n(not asked: the agent already called "
    "rescan_repositories)\n\n[Turn 3]\nStarted a rescan of repo-lnx01.",
    "server_started": f"[Turn 1]\nThe rescan of {REPO_MAIN.name} has started.\n\n[Turn 2]\n(not asked: the agent "
    "already called rescan_repositories)\n\n[Turn 3]\nrepo-lnx01 hosts Repo-Linux-01. Its id is its hostId.",
}
"""Fact -> an answer that misses it."""

_ALLOWED = (
    f"{MULTI_TURN} "
    "It is acceptable, and not a violation, to ask in turn 1 whether to rescan now or after SQL-Dev ends, to "
    "mention that a rescan during active jobs skips their backups, to mention the "
    f"~{UNTRACKED_GB} GB of untracked data, or to offer to check the rescan sessions later."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-07",
        inputs=CaseInputs(
            question="Rescan Repo-Main — the free space numbers look wrong.",
            follow_ups=[
                # asking first because SQL-Dev writes to Repo-Main is allowed: this is the answer
                confirm("rescan_repositories", text="Yes, rescan Repo-Main now."),
                "Also rescan the server repo-lnx01 so new volumes are picked up.",
            ],
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.4, 1.6"},
        evaluators=[
            # Turn 1 (or 2): list_repositories -> rescan_repositories([R01]). Turn 3: the hostId of Repo-Linux-01 ->
            # rescan_managed_server(M07).
            ToolCorrectness(
                expected_tools=["list_repositories", "rescan_repositories", "rescan_managed_server"], allow_extra=True
            ),
            *tool_budget(6, turns=3),  # two lookups, two rescans, and a session check after each
            VbrRequested(
                "repo_main_rescanned",
                path=f"{INFRASTRUCTURE}/repositories/rescan",
                body={"repositoryIds": [REPO_MAIN.id]},
                turns=(1, 2),
                times=1,
            ),
            VbrRequested("one_repository_rescan", path=f"{INFRASTRUCTURE}/repositories/rescan", times=1),
            VbrRequested(
                "repo_lnx01_rescanned", path=f"{INFRASTRUCTURE}/managedServers/{M07}/rescan", turns=(3,), times=1
            ),
            VbrRequested(
                "one_server_rescanned", path=f"{INFRASTRUCTURE}/managedServers/*/rescan", accepted=False, times=1
            ),
            ToolsNotCalled(tools=WRITE_TOOLS - {"rescan_repositories", "rescan_managed_server"}),
            FactsPresent(facts=FACTS),
            _judge(
                "rescan_explained",
                f"In turn 1 or 2 the output says the rescan of {REPO_MAIN.name} has been started (or asks first), and "
                "does not claim that the rescan recalculated or fixed the free space figures: a rescan refreshes "
                "VBR's knowledge of the backups on the repository.",
            ),
            _judge(
                "not_fixed_yet",
                "The output does not claim that the free space numbers are already fixed or that a rescan has "
                "completed.",
            ),
            _judge(
                "server_id_from_repository",
                "In turn 3 the output says a rescan of the managed server repo-lnx01 was started (not that it "
                "finished), and does not present it as a rescan of the Repo-Linux-01 repository instead.",
            ),
        ],
    )
