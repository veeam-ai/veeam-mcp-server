# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G2-06: fs-01's malware events and the safest restore point: the infection boundary, then the clean point before."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

import stand
from cases import CaseInputs, Environment, judge, tool_budget
from cases.patterns import any_of, day
from evaluators import RESTORE_POINT_READS, FactsPresent, ToolsCalled, ToolsNotCalled
from stand import by_id
from stand.ids import EV07, T0
from stand.malware import EVENTS
from stand.protected import points_of

# ---- What VBR serves: the base stand. fs-01's inline scan flagged the 10-04 point Suspicious (encrypted data); an
# admin marked fs-01 clean on 10-05 without calling it a false positive, so the 10-04 point stays Suspicious and the
# 10-05 point was made Clean; the Scan Backup of 10-06 found LockBit in the newest point (Infected). Other VMs' events
# (web-01, web-02, app-01) are not about fs-01.

ENVIRONMENT: Environment = stand.environment()

# ---- What a correct answer says, derived from the data above.

_FS_POINTS = sorted(points_of("fs-01"), key=lambda p: p.creation_time)
_BOUNDARY = next(p for p in _FS_POINTS if p.malware_status in ("Suspicious", "Infected"))
_SAFEST = max((p for p in _FS_POINTS if p.creation_time < _BOUNDARY.creation_time), key=lambda p: p.creation_time)
_NEWEST_CLEAN = max((p for p in _FS_POINTS if p.malware_status == "Clean"), key=lambda p: p.creation_time)
_LATEST = _FS_POINTS[-1]
_MARKED_CLEAN = by_id(EVENTS, EV07)
_HOURS_BACK = round((T0 - _SAFEST.creation_time).total_seconds() / 3600)
assert _NEWEST_CLEAN.creation_time > _MARKED_CLEAN.detection_time_utc > _BOUNDARY.creation_time

EXPECTED = (
    f"Malware events for fs-01: on {_BOUNDARY.creation_time:%Y-%m-%d} a Suspicious event from inline scan "
    f"(encrypted, high-entropy data in 3412 files) on that night's restore point; on "
    f"{_MARKED_CLEAN.detection_time_utc:%Y-%m-%d} a mark-as-clean by LAB\\admin (not as a false positive) - a "
    "remediation marker, not a detection; on "
    f"{_LATEST.creation_time:%Y-%m-%d} an Infected event from Microsoft Defender Antivirus, "
    r"Ransom:Win32/LockBit.SB!MTB in E:\Shares\finance\Q3\invoice_0912.xlsx.lockbit, on the latest point "
    f"({_LATEST.creation_time:%Y-%m-%d %H:%M}). The infection boundary is {_BOUNDARY.creation_time:%Y-%m-%d}, the "
    f"earliest Suspicious point. The safest point to restore from is {_SAFEST.creation_time:%Y-%m-%d %H:%M} (about "
    f"{_HOURS_BACK} hours ago), the nearest Clean point before the boundary. Not "
    f"{_NEWEST_CLEAN.creation_time:%Y-%m-%d}: it is Clean only because fs-01 was marked clean that morning, after the "
    "infection had begun, and the LockBit find of the next night shows it was still there. The "
    f"{_SAFEST.creation_time:%Y-%m-%d} point has no detection, but no antivirus scan verified it either: a Scan "
    "Backup or a secure restore of it is a sensible first step. Changes after it would be lost."
)
"""Ground truth for the judges."""

FACTS = {
    "suspicious": r"suspicious",
    "infected": r"infected",
    "encrypted_data": any_of(r"3[,.\s]?412", r"encrypt", r"high[\s-]entropy"),
    "lockbit": r"lockbit",
    "marked_clean": any_of(r"mark(ed|s|ing)?\s+([\w-]+\s+){0,3}(as\s+)?clean", r"markascleanevent", r"mark-as-clean"),
    "boundary_date": day(_BOUNDARY.creation_time, weekday=False),
    "safest_point": day(_SAFEST.creation_time, weekday=False),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

_ALLOWED = (
    "It is acceptable, and not a violation, to offer (without doing it) a secure restore with an antivirus or YARA "
    "check, or a Scan Backup of the chosen point before restoring, to estimate the data-loss window as the changes "
    f"after {_SAFEST.creation_time:%Y-%m-%d}, to show the list of fs-01's points with their statuses, or to suggest "
    "reviewing who marked fs-01 clean and why."
)

GOOD = [
    (
        "**Malware events for fs-01** (newest first):\n\n"
        "| When (UTC) | Event | Severity |\n|---|---|---|\n"
        "| 2026-10-06 21:35 | Defender: Ransom:Win32/LockBit.SB!MTB in E:\\Shares\\finance\\Q3\\invoice_0912.xlsx.lockbit "
        "| Infected |\n| 2026-10-05 07:30 | Marked as clean by LAB\\admin (not a false positive) | Clean |\n"
        "| 2026-10-04 20:20 | Inline scan: 3412 files with encrypted data | Suspicious |\n\n"
        "**Infection boundary:** the 2026-10-04 point, the first one flagged.\n\n"
        "**Safest point:** **2026-10-03 22:00**, the last Clean point before the boundary. Don't use the 10-05 point: it "
        "only shows Clean because fs-01 was marked clean that morning, after the infection began - LockBit was found "
        "again the next night. Nothing has scanned the 10-03 point, so run a Scan Backup or a secure restore on it first."
    ),
    (
        "fs-01 has three events: a Suspicious inline-scan detection of encrypted (high-entropy) data on Oct 4th, a "
        "manual mark-as-clean on Oct 5th, and an Infected LockBit finding from the Scan Backup on Oct 6th. The safest "
        "restore point is the one from 3 Oct 2026 at 22:00, before the first detection. The Clean point of Oct 5 came "
        "after the infection started and is Clean only because someone marked the VM clean."
    ),
    (
        "Events: 04.10.2026 Suspicious (encryption activity, 3,412 files), 05.10.2026 marked clean by LAB\\admin, "
        "06.10.2026 Infected (LockBit). Restore from October 3 (22:00) - the 5th looks clean but it is after the "
        "infection began."
    ),
]

BAD = {
    "safest_point": "fs-01 was flagged Suspicious on Oct 4 (encrypted data), marked as clean on Oct 5 and found "
    "Infected with LockBit on Oct 6. The safest point is the Clean one of Oct 5.",
    "marked_clean": "fs-01 was flagged Suspicious on Oct 4 (encrypted data) and Infected with LockBit on Oct 6. "
    "Restore from the Oct 3 point.",
    "lockbit": "fs-01 was flagged Suspicious on Oct 4 (encrypted data), marked clean on Oct 5 and found infected on "
    "Oct 6. Restore from Oct 3.",
}


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G2-06",
        inputs=CaseInputs(
            question=(
                "fs-01 looks infected. What malware events do we have for it, and which restore point is the "
                "safest to restore from?"
            ),
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G2", "base_stand": "1.8, 1.10"},
        evaluators=[
            # The events come from list_malware_events only; fs-01's points with their malware status from
            # list_restore_points or list_protected_objects(id=...). get_server_status is a read on top.
            ToolCorrectness(expected_tools=["list_malware_events"], allow_extra=True),
            ToolsCalled("restore_points_read", RESTORE_POINT_READS),
            *tool_budget(4),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "safest_point",
                f"The output recommends the {_SAFEST.creation_time:%Y-%m-%d} point (around "
                f"{_SAFEST.creation_time:%H:%M}) as the safest to restore from, and explains why the "
                f"{_NEWEST_CLEAN.creation_time:%Y-%m-%d} point is not chosen although it is Clean: it was created "
                "after the infection began (it is Clean only because fs-01 was marked clean, which the later "
                "LockBit detection proves premature). Either reason is enough.",
            ),
            _judge(
                "not_newest_clean",
                f"The output does not recommend restoring from the {_NEWEST_CLEAN.creation_time:%Y-%m-%d} point as it "
                f"is, nor from the latest point ({_LATEST.creation_time:%Y-%m-%d}). Offering the "
                f"{_NEWEST_CLEAN.creation_time:%Y-%m-%d} point only on condition that it is scanned first (or restored "
                "with a secure restore), as a lower-data-loss alternative to the safest point, is fine.",
            ),
            _judge(
                "mark_clean_not_evidence",
                f"The output does not present the mark-as-clean of {_MARKED_CLEAN.detection_time_utc:%Y-%m-%d} as a "
                "detection, nor as proof that fs-01 or its later points are clean.",
            ),
            _judge(
                "safest_not_verified",
                f"The output does not claim that the {_SAFEST.creation_time:%Y-%m-%d} point was scanned or verified "
                "clean: it has no detection, but no antivirus scan checked it. Recommending a scan or a secure "
                "restore of it is fine.",
            ),
            _judge(
                "only_fs01_events",
                "The output does not present malware events of web-01, web-02 or app-01 as events of fs-01.",
            ),
            _judge(
                "nothing_started",
                "The output does not claim that a restore or a malware scan was started; offering one is fine.",
            ),
        ],
    )
