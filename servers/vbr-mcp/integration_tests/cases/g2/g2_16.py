# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G2-16: the numbers about repositories stay consistent across two turns of a dialogue."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import CaseInputs, judge, tool_budget
from cases.patterns import any_of, gb
from evaluators import Fact, FactsPresent, ToolsNotCalled
from stand import environment, repositories
from stand.repositories import is_low_on_space

# ---- What VBR serves: the base stand. Its repositories (1.4): four standalone ones and SOBR-Prod (1.5) with three
# performance extents and the capacity extent S3-Capacity, which as Amazon S3 reports no capacity (-1).

ENVIRONMENT = environment()

# ---- What a correct answer says, derived from the data above.

_STATES = repositories.REPOSITORY_STATES
_BLOCK = [state for state in _STATES if state.capacity_gb > 0]  # S3-Capacity reports -1: unbounded object storage
_STANDALONE = [state for state in _STATES if state.scale_out_repository_details is None]
_EXTENTS = [state for state in _BLOCK if state.scale_out_repository_details is not None]
FREE_GB = sum(state.free_gb for state in _BLOCK)


LOW = [state for state in _STATES if is_low_on_space(state)]
assert [state.name for state in LOW] == ["Repo-Linux-01", "Repo-Branch", "SOBR-Ext-02"] and FREE_GB == 16493

EXPECTED = (
    f"[Turn 1] There are {len(_STANDALONE)} standalone repositories ("
    + ", ".join(state.name for state in _STANDALONE)
    + f") and the scale-out repository {repositories.SOBR_NAME} with {len(_EXTENTS)} performance extents ("
    + ", ".join(state.name for state in _EXTENTS)
    + f") plus a capacity tier on S3-Capacity - {len(_STATES)} repository rows counting the extents. Free space on "
    f"the block storage is {FREE_GB:,.0f} GB (about 16.5 TB); S3-Capacity is left out, Amazon S3 reports no capacity "
    f"(capacityGB and freeGB are -1). SOBR-Ext-03's 3,900 GB free are in the total but take no new backups while it "
    f"is in maintenance.\n[Turn 2] {len(LOW)} of them are low on space: "
    + ", ".join(state.name for state in LOW)
    + f" - 2 standalone repositories and 1 extent of {repositories.SOBR_NAME}, counted within the same scope as turn "
    "1. Repo-Linux-01 and SOBR-Ext-02 are under 10% free; Repo-Branch has 15% free but only 90 GB."
)
"""Ground truth for the judges."""

FACTS = {
    "total_free": Fact(any_of(gb(FREE_GB), r"(?<![\d.])16\s*(TB|TiB)\b"), turns=(1,)),
    # named in turn 2's answer, not merely listed among all repositories in turn 1
    **{f"low_{state.name.lower().replace('-', '_')}": Fact(state.name, turns=(2,)) for state in LOW},
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    """[Turn 1]
You have 5 backup repositories: 4 standalone ones (Repo-Main, Repo-Linux-01, Repo-Branch, Repo-DR) and the scale-out repository SOBR-Prod, which is made of 3 performance extents (SOBR-Ext-01, -02, -03) plus the S3-Capacity capacity tier.

Free space in total: **16,493 GB (about 16.5 TB)** across the block repositories and extents. S3-Capacity is not included - Amazon S3 does not report a capacity, so it has no free-space figure.

[Turn 2]
Of those, 3 are low on space: Repo-Linux-01 (860 GB, 4.2% free), SOBR-Ext-02 (300 GB, 3.7% free - an extent of SOBR-Prod) and Repo-Branch (90 GB, under 100 GB though 15% free).""",
    """[Turn 1]
| Repository | Free |
|---|---|
| Repo-Main | 1,843 GB |
| Repo-Linux-01 | 860 GB |
| Repo-Branch | 90 GB |
| Repo-DR | 7,000 GB |
| SOBR-Prod (Ext-01/02/03) | 6,700 GB |

That is 8 repository rows if you count the extents and S3-Capacity separately; 16.1 TiB free in total, not counting the S3 capacity tier (its capacity is unknown).

[Turn 2]
Two are below VBR's 10% threshold - Repo-Linux-01 and SOBR-Ext-02 - and Repo-Branch is borderline with only 90 GB free.""",
]

BAD = {
    "total_free": (
        "[Turn 1]\nYou have 5 repositories with 12,593 GB free (SOBR-Ext-03 is in maintenance, so I left it out).\n\n"
        "[Turn 2]\nRepo-Linux-01, Repo-Branch and SOBR-Ext-02 are low on space."
    ),
    "low_sobr_ext_02": (
        "[Turn 1]\nYou have 5 repositories (SOBR-Ext-02 is one of SOBR-Prod's extents), 16,493 GB free in total.\n\n"
        "[Turn 2]\nTwo are low on space: Repo-Linux-01 and Repo-Branch."
    ),
}

_ALLOWED = (
    "The output holds both turns' answers, each headed [Turn N]. It is acceptable, and not a violation, to count "
    "the repositories either way - standalone repositories plus SOBR-Prod as one, or every repository row including "
    "the extents - as long as the output says which; to answer turn 2 from the data of turn 1 without new calls; or "
    "to note that SOBR-Ext-03's free space takes no new backups while it is in maintenance."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G2-16",
        inputs=CaseInputs(
            question="How many backup repositories do we have, and how much free space is there in total?",
            follow_ups=["And how many of those are low on space?"],
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G2", "base_stand": "1.4, 1.5"},
        evaluators=[
            # list_repositories answers turn 1 (list_scale_out_repositories is allowed); turn 2 needs no new call.
            ToolCorrectness(expected_tools=["list_repositories"], allow_extra=True),
            *tool_budget(2, turns=2),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "scope_stated",
                "In turn 1 the output says what it counts as a repository: for example standalone repositories "
                "and SOBR-Prod with its extents, or every repository row including the extents.",
            ),
            _judge(
                "repository_count",
                "The number of repositories the output gives in turn 1 matches the data in one of its scopes: 4 "
                "standalone repositories plus SOBR-Prod (5), or 8 repository rows counting SOBR-Prod's 3 "
                "performance extents and its capacity extent S3-Capacity (7 without S3-Capacity). It gives no other "
                "count.",
            ),
            _judge(
                "low_space",
                "In turn 2 the output identifies Repo-Linux-01 (4.2% free) and SOBR-Ext-02 (3.7% free) as low on "
                "space, and treats Repo-Branch (90 GB free, 15%) either as low or as borderline (naming the "
                "criterion is welcome, not required). It presents no other repository as low on space, and makes "
                "clear (or at least does not contradict) that SOBR-Ext-02 is an extent of SOBR-Prod.",
            ),
            _judge(
                "same_scope_both_turns",
                "The output does not change how repositories are counted between turn 1 and turn 2: if turn 1 "
                "counted SOBR-Prod as one repository, turn 2 does not present its extent as a separate repository "
                "without saying so, and the other way round.",
            ),
            _judge(
                "no_object_storage_in_sum",
                "The free-space total in turn 1 does not include S3-Capacity in any form: not as -1, not as "
                "unlimited and not as 100% free.",
            ),
            _judge(
                "numbers_agree",
                "The numbers in turn 2 agree with those in turn 1: the low-space repositories are among the "
                "repositories counted in turn 1, and no free-space figure changes between the turns.",
            ),
        ],
    )
