# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G1-07: the repositories running low on free space."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import CaseInputs, judge, tool_budget
from cases.patterns import any_of, gb, name, percent
from evaluators import FactsPresent, ToolsNotCalled
from stand import by_name, environment
from stand.repositories import REPOSITORY_STATES, SOBR_NAME, is_low_on_space
from vbr_models.infrastructure import RepositoryState

# ---- What VBR serves: the base stand. By vbr-mcp's rule (under 10% or under 100 GB free) Repo-Linux-01 (4.2%),
# SOBR-Ext-02 (3.7%) and Repo-Branch (90 GB, 15%) are low. S3-Capacity is Amazon S3, which reports no capacity (-1):
# vbr-mcp leaves its free percentage null.

ENVIRONMENT = environment()

# ---- What a correct answer says, derived from the stand.


LOW = [state for state in REPOSITORY_STATES if is_low_on_space(state)]  # Repo-Linux-01, Repo-Branch, SOBR-Ext-02
_LINUX_01, _BRANCH, _EXT_02 = (by_name(REPOSITORY_STATES, n) for n in ("Repo-Linux-01", "Repo-Branch", "SOBR-Ext-02"))
assert {s.name for s in LOW} == {_LINUX_01.name, _BRANCH.name, _EXT_02.name}


def _percent_free(state: RepositoryState) -> float:
    return state.free_gb / state.capacity_gb * 100


def _free(state: RepositoryState) -> str:
    """Its free space, in GB (or TB), or as the share free: 860 GB, 0.84 TB, 4.2%, 4.20%, 3.66%."""
    return any_of(gb(state.free_gb), percent(_percent_free(state), decimals=2))


EXPECTED = (
    f"{len(LOW)} repositories are low on free space: "
    + "; ".join(
        f"{state.name} with {state.free_gb:.0f} GB free of {state.capacity_gb:.0f} GB ({_percent_free(state):.1f}%)"
        for state in LOW
    )
    + f". {_BRANCH.name} is listed because it is under the 100 GB floor, though 15% is free. {_EXT_02.name} is a "
    f"performance extent of {SOBR_NAME}, not a repository of its own. S3-Capacity is Amazon S3 object storage that "
    "reports no capacity (capacityGB and freeGB are -1, so its free percentage is unknown): the rule does not apply "
    "to it, and it is neither low nor '100% free'."
)
"""Ground truth for the judges."""

FACTS = {
    "repo_linux_01": name(_LINUX_01.name),
    "repo_linux_01_free": _free(_LINUX_01),
    "repo_branch": name(_BRANCH.name),
    "repo_branch_free": _free(_BRANCH),
    "sobr_ext_02": name(_EXT_02.name),
    "sobr_ext_02_free": _free(_EXT_02),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match: each low repository, with its free
space in GB or as a share."""

_ALLOWED = (
    "It is acceptable, and not a violation, to say that the 10% and 100 GB thresholds are a heuristic rather than a "
    "VBR setting (VBR's own warning threshold is 10%), to treat Repo-Branch as borderline because 15% is free as "
    "long as it is named with its 90 GB free, to mention the 297 GB of unidentified data on Repo-Main, or to mention "
    "that SOBR-Ext-03 is in maintenance mode."
)

GOOD = [
    (
        "Three repositories are low on free space:\n- Repo-Linux-01: 860 GB free of 20 TB (4.2%)\n- SOBR-Ext-02 (extent "
        "of SOBR-Prod): 300 GB free (3.7%)\n- Repo-Branch: 90 GB free of 600 GB - 15%, but under 100 GB\n\nS3-Capacity is "
        "Amazon S3 object storage; it reports no capacity, so it isn't counted."
    ),
    (
        "| Repository | Free | Free % |\n|---|---|---|\n| Repo-Linux-01 | 0.84 TB | 4.2 % |\n| SOBR-Ext-02 | 300.0 GB | "
        "3.66 % |\n| Repo-Branch | 90.0 GB | 15 % |"
    ),
    "Low: Repo-Linux-01 (~4% free), SOBR-Ext-02 (about 3.7% free) and Repo-Branch (90 GB left).",
]

BAD = {
    "repo_branch": "Two repositories are low on space: Repo-Linux-01 (860 GB, 4.2%) and SOBR-Ext-02 (300 GB, 3.7%).",
    "repo_linux_01_free": "Low on space: Repo-Linux-01, SOBR-Ext-02 (300 GB) and Repo-Branch (90 GB).",
    "sobr_ext_02_free": "Low on space: Repo-Linux-01 (860 GB), SOBR-Ext-02 and Repo-Branch (90 GB).",
}
"""Answers that each miss one repository or its free space."""


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G1-07",
        inputs=CaseInputs(
            question="Which backup repositories are running low on free space?",
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G1", "base_stand": "1.4"},
        evaluators=[
            ToolCorrectness(expected_tools=["list_repositories"], allow_extra=True),
            *tool_budget(1),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "exactly_three_low",
                "The repositories the output names as low on free space are exactly Repo-Linux-01, Repo-Branch and "
                "SOBR-Ext-02 (Repo-Branch may be called borderline). Mentioning other repositories for context "
                "without calling them low on space is fine.",
            ),
            _judge(
                "s3_capacity_not_low",
                "The output does not list S3-Capacity as low on free space. Explaining that it is object storage "
                "with unlimited or unreported capacity is fine.",
            ),
            _judge(
                "s3_capacity_not_100_free",
                "The output does not say that S3-Capacity is 100% free or has 100% free space.",
            ),
            _judge(
                "sobr_not_a_repository",
                f"The output does not present {SOBR_NAME} as a repository with free space of its own. Saying that "
                f"SOBR-Ext-02 is an extent of {SOBR_NAME} is fine.",
            ),
        ],
    )
