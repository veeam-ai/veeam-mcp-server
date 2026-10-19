# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G2-04: which jobs write to repositories that are running out of space."""

from functools import partial
from uuid import UUID

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

import stand
from cases import CaseInputs, Environment, judge, tool_budget
from cases.patterns import about, any_of, gb, name, percent
from evaluators import FactsPresent, ToolsCalled, ToolsNotCalled
from stand import by_name
from stand.ids import R02, R03, S01
from stand.jobs import JOBS, repository_id
from stand.repositories import EXTENT_STATUS, REPOSITORY_STATES, SOBR_NAME

# ---- What VBR serves: the base stand. Low on space by vbr-mcp's rule (under 10% or under 100 GB free): Repo-Linux-01
# (4.2%, a hardened repository with 14-day immutability), Repo-Branch (90 GB) and SOBR-Prod's extent SOBR-Ext-02
# (3.7%); SOBR-Ext-03 is in maintenance. Jobs name their target in their configuration (list_jobs) and in their state
# (get_job_states: repositoryId/repositoryName).

ENVIRONMENT: Environment = stand.environment()

# ---- What a correct answer says, derived from the data above.


_STATES = {state.id: state for state in REPOSITORY_STATES}
_LINUX_01, _BRANCH = _STATES[R02], _STATES[R03]
_EXT_02 = by_name(REPOSITORY_STATES, "SOBR-Ext-02")
_MAINTENANCE = [state.name for state in REPOSITORY_STATES if EXTENT_STATUS.get(state.id) == "Maintenance"]
_WRITABLE_FREE_GB = sum(_STATES[extent].free_gb for extent, status in EXTENT_STATUS.items() if status == "Normal")
_WRITERS = {target: [job for job in JOBS if repository_id(job) == target] for target in (R02, R03, S01)}
_HEALTHY_WRITERS = [job.name for job in JOBS if repository_id(job) not in _WRITERS]  # Daily-VMs, SQL-Dev, Copy-to-DR


def _names(target: UUID) -> str:
    return ", ".join(job.name for job in _WRITERS[target])


EXPECTED = (
    f"{_LINUX_01.name} ({_LINUX_01.free_gb:.0f} GB, {_LINUX_01.free_gb / _LINUX_01.capacity_gb * 100:.1f}% free; a "
    f"hardened repository whose backups are immutable for 14 days) is written to by {_names(R02)}. {_BRANCH.name} "
    f"({_BRANCH.free_gb:.0f} GB free) is written to by {_names(R03)}, which is disabled now, so the risk comes when "
    f"it is enabled again. {SOBR_NAME} is written to by {_names(S01)}: its extent {_EXT_02.name} is nearly full "
    f"({_EXT_02.free_gb:.0f} GB, {_EXT_02.free_gb / _EXT_02.capacity_gb * 100:.1f}% free) and "
    f"{', '.join(_MAINTENANCE)} is in maintenance, so about {_WRITABLE_FREE_GB:.0f} GB (2.8 TB) is left for new "
    "backups. The jobs reference the SOBR's own id, not an extent, and the API does not say on which extent a job's "
    f"backup chain lies. {', '.join(_HEALTHY_WRITERS)} write to repositories with enough space."
)
"""Ground truth for the judges."""

FACTS = {
    "repo_linux_01": name(_LINUX_01.name),
    "repo_branch": name(_BRANCH.name),
    "sobr": name(SOBR_NAME),
    **{
        f"job_{job.name.lower().replace('-', '_')}": name(job.name)
        for target in (R02, R03, S01)
        for job in _WRITERS[target]
    },
    # why SOBR-Prod is on the list: its extent's free space, as GB or as a share - said of the extent, as "4%" is
    # also Repo-Linux-01's free space rounded
    "ext_02_low": about(
        name(_EXT_02.name),
        any_of(gb(_EXT_02.free_gb), percent(3.7), r"3\.66\s*%", r"(under|below|less\s+than)\s+4\s*%", percent(96.3)),
        others=any_of(*(name(state.name) for state in REPOSITORY_STATES if state.name != _EXT_02.name)),
        within=150,
    ),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

_ALLOWED = (
    "It is acceptable, and not a violation, to suggest measures such as shorter retention, moving a job to another "
    "repository or adding storage, as advice only, to note that Repo-Branch at 15% free is low only by the absolute "
    "100 GB rule, or to mention the 297 GB of unidentified data on Repo-Main."
)

GOOD = [
    (
        "Repositories that are running out of space, and who writes to them:\n\n"
        "- **Repo-Linux-01** - 860 GB free (4.2%): NAS-Finance, Agent-Laptops, Reports-VM and S3-Docs.\n"
        "- **Repo-Branch** - 90 GB free: Legacy-Archive (disabled for now).\n"
        "- **SOBR-Prod** - SOBR-Ext-02 has only 300 GB (3.7%) free and SOBR-Ext-03 is in maintenance, leaving about "
        "2.8 TB for new backups: SQL-Prod and Test-NewApp.\n\n"
        "Daily-VMs, SQL-Dev and Copy-to-DR write to repositories with plenty of space."
    ),
    (
        "| Repository | Free | Jobs |\n|---|---|---|\n| Repo-Linux-01 | 4.2 % | NAS-Finance, Agent-Laptops, Reports-VM, "
        "S3-Docs |\n| Repo-Branch | 90.0 GB | Legacy-Archive (disabled) |\n| SOBR-Prod (extent SOBR-Ext-02: 96.3% full) "
        "| | SQL-Prod, Test-NewApp |\n\nNote that Repo-Linux-01 is a hardened repository with 14-day immutability, so "
        "shortening retention there frees space only after the immutability period."
    ),
    (
        "SQL-Prod and Test-NewApp write to SOBR Prod, where SOBR Ext-02 is under 4% free; NAS-Finance, Agent-Laptops, "
        "Reports-VM and S3-Docs write to Repo-Linux-01 (0.86 TB free); Legacy-Archive writes to Repo-Branch (90 GB "
        "free) but is disabled."
    ),
]

BAD = {
    "job_reports_vm": "Repo-Linux-01 (4.2% free): NAS-Finance, Agent-Laptops, S3-Docs. Repo-Branch (90 GB): "
    "Legacy-Archive. SOBR-Prod (SOBR-Ext-02 at 3.7%): SQL-Prod, Test-NewApp.",
    "sobr": "Repo-Linux-01 (4.2% free): NAS-Finance, Agent-Laptops, Reports-VM, S3-Docs. Repo-Branch (90 GB): "
    "Legacy-Archive.",
    "ext_02_low": "SOBR-Prod has 2.8 TB free for SQL-Prod and Test-NewApp; SOBR-Ext-02 is fine. Repo-Linux-01 has 4% "
    "free (NAS-Finance, Agent-Laptops, Reports-VM, S3-Docs) and Repo-Branch is low (Legacy-Archive).",
}


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G2-04",
        inputs=CaseInputs(
            question="Which jobs write to repositories that are running out of space?",
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G2", "base_stand": "1.2, 1.4, 1.5"},
        evaluators=[
            # list_repositories finds the full ones; the job -> repository map comes from list_jobs (configuration)
            # or get_job_states (repositoryId/repositoryName); list_scale_out_repositories resolves the extents.
            ToolCorrectness(expected_tools=["list_repositories"], allow_extra=True),
            ToolsCalled("job_targets_read", frozenset({"list_jobs", "get_job_states"})),
            *tool_budget(4),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "writers_per_repository",
                f"The output attributes {_names(R02)} to {_LINUX_01.name}, {_names(R03)} to {_BRANCH.name} and "
                f"{_names(S01)} to {SOBR_NAME}, and says or makes clear that {_names(R03)} is disabled.",
            ),
            _judge(
                "jobs_not_mapped_to_extents",
                f"The output does not claim that a job writes to a particular extent such as {_EXT_02.name}: the "
                f"jobs reference {SOBR_NAME} itself.",
            ),
            _judge(
                "no_extent_placement_claim",
                f"The output does not state on which extent of {SOBR_NAME} the backup chain of SQL-Prod or "
                "Test-NewApp lies: the API does not tell that.",
            ),
            _judge(
                "healthy_targets_not_flagged",
                f"The output does not present {', '.join(_HEALTHY_WRITERS)} as writing to a repository that is "
                "running out of space.",
            ),
            _judge(
                "immutability_respected",
                f"If the output suggests freeing space on {_LINUX_01.name} by shorter retention or by deleting or "
                "moving backups, it does not promise that the space comes back right away: it is a hardened "
                "repository whose backups stay immutable for 14 days. Not suggesting such measures is fine.",
            ),
        ],
    )
