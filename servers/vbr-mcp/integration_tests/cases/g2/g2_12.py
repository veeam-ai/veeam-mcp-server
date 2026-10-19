# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G2-12: the disks captured in the latest restore point of sql-prod-02."""

from datetime import UTC
from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import CaseInputs, judge, tool_budget
from cases.patterns import any_of
from evaluators import RESTORE_POINT_READS, FactsPresent, ToolsCalled, ToolsNotCalled, VbrRequested
from stand import environment, protected
from stand.ids import GB

# ---- What VBR serves: the base stand. Its restore points (1.8) carry their disks, named as the VMDKs are (swagger
# ObjectRestorePointDisksResultExample) and sized in bytes; sql-prod-02's latest point is tonight's, sql-prod-01's is
# from the night before (tonight's run failed for it), with a different data disk.

ENVIRONMENT = environment()

# ---- What a correct answer says, derived from the data above.

LATEST = protected.points_of("sql-prod-02")[0]
_OTHER_VM_LATEST = protected.points_of("sql-prod-01")[0]
_DISKS = protected.DISKS[LATEST.id]
_OTHER_DISKS = protected.DISKS[_OTHER_VM_LATEST.id]
_SMALL, _LARGE = (disk.capacity // GB for disk in _DISKS)  # GiB, which VBR and most answers call GB
assert (_SMALL, _LARGE) == (80, 500) and [d.capacity // GB for d in _OTHER_DISKS] == [80, 300]
_WHEN, _WHEN_UTC = LATEST.creation_time, LATEST.creation_time.astimezone(UTC)

EXPECTED = (
    f"The latest restore point of sql-prod-02 was created on {_WHEN:%Y-%m-%d} at {_WHEN:%H:%M} on the server's clock "
    f"({_WHEN_UTC:%Y-%m-%d %H:%M} UTC). It captures {len(_DISKS)} disks: "
    + " and ".join(f"{disk.name} ({disk.capacity // GB} GB)" for disk in _DISKS)
    + f", {_SMALL + _LARGE} GB in total. VBR reports the sizes in bytes ({_DISKS[0].capacity:,} and "
    f"{_DISKS[1].capacity:,}), binary gigabytes: in decimal units {_DISKS[0].capacity / 1e9:.1f} GB and "
    f"{_DISKS[1].capacity / 1e9:.1f} GB. The point supports Instant Recovery, entire-VM restore and file-level restore."
)
"""Ground truth for the judges."""


def _size(gib: int) -> str:
    """A disk of ``gib`` GiB as an answer writes it: in GB or GiB, in decimal GB, in bytes, or a bare table cell."""
    decimal = f"{gib * GB / 1e9:.1f}".replace(".", r"\.")
    return any_of(
        rf"(?<![\d.,]){gib}(\.0+)?\s*(GiB|GB|gigabytes?)\b",
        rf"(?<![\d.,]){decimal}\d*\s*GB\b",
        rf"(?<![\d.,]){gib * GB}(?!\d)|(?<![\d.,]){gib * GB:,}(?![\d,])",
        rf"\|\s*{gib}(\.0+)?\s*\|",
    )


FACTS = {
    "disk_small": _size(_SMALL),
    "disk_large": _size(_LARGE),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    """The latest restore point of sql-prod-02 (created 2026-10-07 00:10) captured 2 disks:
- sql-prod-02 - 80 GB
- sql-prod-02_1 - 500 GB

That is 580 GB of disk capacity in total.""",
    """sql-prod-02's newest point is from Oct 6, 22:10 UTC (tonight's run). It contains:

| Disk | Size (GB) | State |
|---|---|---|
| sql-prod-02 | 80 | Processed |
| sql-prod-02_1 | 500 | Processed |""",
    """Two disks are in the latest restore point of sql-prod-02: one of 85.9 GB (85,899,345,920 bytes) and one of 536.9 GB (536,870,912,000 bytes); both were processed.""",
]

BAD = {
    "disk_large": (
        "The latest point of sql-prod-02 (2026-10-06 00:14) has two disks: sql-prod-01 80 GB and sql-prod-01_1 300 GB."
    ),
    "disk_small": "The latest restore point of sql-prod-02 captured a single disk, sql-prod-02_1, of 500 GB.",
}

_ALLOWED = (
    f"It is acceptable, and not a violation, to give the point's time ({_WHEN:%Y-%m-%d %H:%M} on the server's clock "
    f"or {_WHEN_UTC:%H:%M} UTC), the {_SMALL + _LARGE} GB total, the sizes in bytes or decimal GB, the disks' "
    "Processed state, to suppose that the larger disk holds the SQL data, or to mention that the point supports "
    "Instant Recovery and full VM restore."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G2-12",
        inputs=CaseInputs(
            question="What disks are captured in the latest restore point of sql-prod-02?",
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G2", "base_stand": "1.8"},
        evaluators=[
            # the points come from either tool: list_restore_points (filtered by object or name) or
            # list_protected_objects with the object's id; the disks only from get_restore_point_disks, and from
            # the latest point's
            ToolsCalled("restore_points_read", RESTORE_POINT_READS),
            ToolCorrectness(expected_tools=["get_restore_point_disks"], allow_extra=True),
            VbrRequested("disks_of_latest_point", method="GET", path=f"/api/v1/restorePoints/{LATEST.id}/disks"),
            *tool_budget(3),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "not_sql_prod_01_point",
                "The output does not describe a restore point of sql-prod-01 or its disks (an 80 GB and a 300 GB "
                "disk, latest point 2026-10-06 00:14) as the latest point of sql-prod-02.",
            ),
            _judge(
                "no_invented_disks",
                "The output names no disks other than the two in the expected output, and gives them no sizes other "
                "than theirs (in GB, GiB, decimal GB or bytes).",
            ),
        ],
    )
