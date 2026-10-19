# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G2-05: how much space SOBR-Prod really has for new backups."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

import stand
from cases import CaseInputs, Environment, judge, tool_budget
from cases.patterns import any_of, gb, name, near
from evaluators import FactsPresent, ToolsNotCalled
from stand import by_name
from stand.repositories import EXTENT_STATUS, REPOSITORY_STATES

# ---- What VBR serves: the base stand. SOBR-Prod's performance tier is SOBR-Ext-01 (2500 GB free), SOBR-Ext-02
# (300 GB free, nearly full) and SOBR-Ext-03 (3900 GB free, in maintenance mode); its capacity tier is the S3-Capacity
# object storage, which reports no capacity (-1).

ENVIRONMENT: Environment = stand.environment()

# ---- What a correct answer says, derived from the data above.

_STATES = {state.id: state for state in REPOSITORY_STATES}
_EXTENTS = [_STATES[extent] for extent in EXTENT_STATUS]
_WRITABLE = [_STATES[extent] for extent, status in EXTENT_STATUS.items() if status == "Normal"]
_MAINTENANCE = next(_STATES[extent] for extent, status in EXTENT_STATUS.items() if status == "Maintenance")
_EXT_01, _EXT_02 = _WRITABLE
_CAPACITY = by_name(REPOSITORY_STATES, "S3-Capacity")

TOTAL_GB = sum(state.capacity_gb for state in _EXTENTS)  # 20480
FREE_GB = sum(state.free_gb for state in _EXTENTS)  # 6700
WRITABLE_FREE_GB = sum(state.free_gb for state in _WRITABLE)  # 2800

EXPECTED = (
    f"SOBR-Prod's performance tier has {TOTAL_GB:.0f} GB (about 20 TB) in total with {FREE_GB:.0f} GB "
    f"(about 6.7 TB, {FREE_GB / TOTAL_GB * 100:.1f}%) free. But {_MAINTENANCE.name} ({_MAINTENANCE.free_gb:.0f} GB "
    "free) is in maintenance mode: it takes no new writes (and nothing can be restored from backup files on it), so "
    f"for new backups only about {WRITABLE_FREE_GB:.0f} GB (about 2.8 TB) is really available: "
    + " and ".join(f"{state.name} with {state.free_gb:.0f} GB" for state in _WRITABLE)
    + f". {_EXT_02.name} is nearly full at {_EXT_02.free_gb / _EXT_02.capacity_gb * 100:.1f}% free; with the Data "
    "locality placement a chain on it has only those 300 GB to grow into. The capacity tier "
    f"({_CAPACITY.name}, S3 object storage, {_CAPACITY.used_space_gb:.0f} GB offloaded) is not part of these figures."
)
"""Ground truth for the judges."""


def _both(first: str, second: str) -> str:
    """``first`` and ``second`` anywhere in the answer, in either order."""
    return rf"^(?=[\s\S]*(?:{first}))(?=[\s\S]*(?:{second}))"


FACTS = {
    # the sum, or the two extents that make it up
    "writable_free": any_of(gb(WRITABLE_FREE_GB), _both(gb(_EXT_01.free_gb), gb(_EXT_02.free_gb))),
    "maintenance_extent": near(name(_MAINTENANCE.name), r"maintenance", 150),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

_ALLOWED = (
    "It is acceptable, and not a violation, to give the total capacity and free space of the performance tier, to "
    "give a table per extent, to explain that with the Data locality placement policy running out of space on one "
    "extent matters even when the total is enough, to mention that nothing can be restored from SOBR-Ext-03 while it "
    "is in maintenance, or to advise taking SOBR-Ext-03 out of maintenance mode once the maintenance is over, as "
    "advice only."
)

GOOD = [
    (
        "For new backups SOBR-Prod really has about **2.8 TB** (2800 GB):\n\n"
        "| Extent | Free | Status |\n|---|---|---|\n| SOBR-Ext-01 | 2500 GB | Normal |\n| SOBR-Ext-02 | 300 GB (3.7%) | "
        "Normal, nearly full |\n| SOBR-Ext-03 | 3900 GB | **Maintenance** - takes no new backups |\n\n"
        "The performance tier shows 6.7 TB free in total, but 3.9 TB of that is on SOBR-Ext-03, which is in maintenance "
        "mode. The capacity tier (S3-Capacity) is object storage and is not counted."
    ),
    (
        "Only ~2.8 TB. SOBR-Ext-03 is in maintenance mode, so its 3.9 TB can't take new backups; what's left is 2.5 TB "
        "on SOBR-Ext-01 and 0.3 TB on SOBR-Ext-02, which is almost full."
    ),
    (
        "Realistically 2.5 TB on SOBR-Ext-01 plus 300 GB on the nearly full SOBR-Ext-02. SOBR Ext-03 has 3.9 TB free but "
        "it is in Maintenance and accepts no writes."
    ),
]

BAD = {
    "writable_free": "SOBR-Prod has 6.7 TB free across its three extents; SOBR-Ext-03 is in maintenance.",
    "maintenance_extent": "SOBR-Prod has 2.8 TB free for new backups (2.5 TB on SOBR-Ext-01, 300 GB on SOBR-Ext-02).",
}


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G2-05",
        inputs=CaseInputs(
            question="How much free space do we really have in SOBR-Prod for new backups?",
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G2", "base_stand": "1.4, 1.5"},
        evaluators=[
            # list_scale_out_repositories names the extents and their status; list_repositories has their space.
            ToolCorrectness(expected_tools=["list_scale_out_repositories", "list_repositories"], allow_extra=True),
            *tool_budget(2),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "no_capacity_tier_in_sum",
                f"The output does not add the capacity tier ({_CAPACITY.name}) to any free-space or capacity figure "
                "for SOBR-Prod, including as -1, as unlimited or as 100% free.",
            ),
            _judge(
                "maintenance_caveat",
                f"The output does not present the {FREE_GB:.0f} GB (about 6.7 TB) free across the performance "
                f"tier as available for new backups without saying that {_MAINTENANCE.name} is in maintenance and "
                f"its space cannot take new backups; the space really available for new backups is about "
                f"{WRITABLE_FREE_GB:.0f} GB.",
            ),
            _judge(
                "sobr_not_a_plain_repository",
                "The output does not describe SOBR-Prod as an ordinary repository with one capacity and free space "
                "of its own: it is a scale-out repository whose space is that of its extents.",
            ),
            _judge(
                "no_restore_from_maintenance",
                f"The output does not claim that backups on {_MAINTENANCE.name} can still be restored, or that jobs "
                "with a chain on it keep working normally, while it is in maintenance mode. Not mentioning restores "
                "at all is fine.",
            ),
        ],
    )
