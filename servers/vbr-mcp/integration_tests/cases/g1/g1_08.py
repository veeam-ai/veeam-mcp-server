# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G1-08: the scale-out repository and the status of its extents."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import CaseInputs, judge, tool_budget
from cases.patterns import any_of, name
from evaluators import FactsPresent, ToolsNotCalled
from stand import by_name, environment
from stand.repositories import REPOSITORIES, SCALE_OUT_REPOSITORIES

# ---- What VBR serves: the base stand. SOBR-Prod has three performance extents, SOBR-Ext-03 in maintenance mode, and
# a capacity tier on S3-Capacity. Maintenance does more than stop new writes: "You cannot restore VM data from backup
# files residing on the extent. You also cannot restore ... from other extents if a part of the backup chain resides
# on the extent in the Maintenance mode" (User Guide v13, sobr_maintenance).

ENVIRONMENT = environment()

# ---- What a correct answer says, derived from the stand.

(SOBR,) = SCALE_OUT_REPOSITORIES
_PERFORMANCE = SOBR.performance_tier.performance_extents
assert SOBR.capacity_tier is not None and SOBR.capacity_tier.extents
_CAPACITY_EXTENT = next(r.name for r in REPOSITORIES if r.id == SOBR.capacity_tier.extents[0].id)
_IN_MAINTENANCE = by_name(_PERFORMANCE, "SOBR-Ext-03")
assert _IN_MAINTENANCE.status == ["Maintenance"]


def _extent(extent_name: str) -> str:
    """An extent's name, also without the ``SOBR-`` prefix: "SOBR-Ext-01", "Ext-01", "Ext 01"."""
    number = extent_name.rsplit("-", 1)[-1]
    return rf"\b(?:SOBR[-\s]?)?Ext(?:ent)?[-\s]?{number}\b"


EXPECTED = (
    f"One scale-out repository, {SOBR.name}, with the Data locality placement policy. Performance extents: "
    + ", ".join(f"{extent.name} - {', '.join(extent.status)}" for extent in _PERFORMANCE)
    + f". {_IN_MAINTENANCE.name} is in maintenance mode: it takes no new backups, its backup files cannot be "
    "restored from (nor chains partly stored on it), and a job whose active chain sits on it fails until it is out "
    f"of maintenance or a new full is made elsewhere. The capacity tier is enabled on {_CAPACITY_EXTENT} (backups move "
    f"there after {SOBR.capacity_tier.operational_restore_period_days} days, copy policy off, encryption on); "
    "capacity-tier extents have no status. The archive tier is disabled."
)
"""Ground truth for the judges."""

FACTS = {
    "sobr": name(SOBR.name),
    **{extent.name.lower().replace("-", "_"): _extent(extent.name) for extent in _PERFORMANCE},
    "normal": any_of(r"\bnormal\b", r"\bOK\b", r"\bhealthy\b", r"\bactive\b"),
    "maintenance": r"\bmaintenance\b",
}
"""Case-insensitive regexes, one per fact, that a correct answer must match: the SOBR, each performance extent, and
the two statuses."""

_ALLOWED = (
    "It is acceptable, and not a violation, to describe the placement policy, the capacity tier (S3-Capacity, move "
    "after 14 days, copy off, encryption on) and the disabled archive tier, to show each extent's free space from the "
    "repository list, to warn that SOBR-Ext-02 is low on free space, or to explain what maintenance mode blocks."
)

GOOD = [
    (
        "One scale-out repository: **SOBR-Prod** (Data locality placement).\n\n| Extent | Tier | Status |\n|---|---|---|"
        "\n| SOBR-Ext-01 | Performance | Normal |\n| SOBR-Ext-02 | Performance | Normal |\n| SOBR-Ext-03 | Performance | "
        "Maintenance |\n| S3-Capacity | Capacity | (capacity extents have no status) |\n\nSOBR-Ext-03 in maintenance takes "
        "no new backups, and backups on it can't be restored until it leaves maintenance."
    ),
    (
        "SOBR-Prod: SOBR-Ext-01 - Normal; SOBR-Ext-02 - Normal (only 300 GB free); SOBR-Ext-03 - Maintenance mode. "
        "Capacity tier: S3-Capacity, backups move after 14 days, encrypted; the archive tier is disabled."
    ),
    "SOBR-Prod has three performance extents. Ext-01 and Ext-02 are in normal state, Ext-03 is in maintenance.",
]

BAD = {
    "maintenance": "SOBR-Prod has three performance extents, SOBR-Ext-01, SOBR-Ext-02 and SOBR-Ext-03, all Normal.",
    "normal": "SOBR-Prod: SOBR-Ext-03 is in maintenance; SOBR-Ext-01 and SOBR-Ext-02 take new backups.",
    "sobr_ext_02": "SOBR-Prod: SOBR-Ext-01 is Normal and SOBR-Ext-03 is in maintenance.",
}
"""Answers that each miss one status or extent."""


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G1-08",
        inputs=CaseInputs(
            question="Show me our scale-out repositories and the status of each extent.",
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G1", "base_stand": "1.5"},
        evaluators=[
            # list_scale_out_repositories is the answer; list_repositories (space per extent) is allowed on top.
            ToolCorrectness(expected_tools=["list_scale_out_repositories"], allow_extra=True),
            *tool_budget(2),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "extent_statuses",
                "The output gives SOBR-Ext-01 and SOBR-Ext-02 the status Normal and SOBR-Ext-03 the status "
                "Maintenance.",
            ),
            _judge(
                "maintenance_blocks_restores",
                f"If the output says what maintenance mode means for {_IN_MAINTENANCE.name}, it does not say that "
                "restores from it still work or that maintenance only stops new writes: VBR also blocks restores "
                "from an extent in maintenance (and from chains partly stored on it). Not explaining maintenance "
                "at all is fine.",
            ),
            _judge(
                "no_capacity_extent_status",
                f"The output does not give the capacity-tier extent {_CAPACITY_EXTENT} a status such as Normal or "
                "Maintenance: capacity-tier extents have no status.",
            ),
            _judge(
                "no_capacity_in_totals",
                f"The output does not add the capacity or free space of {_CAPACITY_EXTENT} (the capacity tier) to "
                "the performance tier's capacity or free space in any total it gives.",
            ),
        ],
    )
