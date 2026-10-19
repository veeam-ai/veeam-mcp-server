# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-36: "mark fs-01's restore points as clean" - no tool of vbr-mcp can, and its newest point is infected."""

from datetime import date
from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case

import stand
from cases import CaseInputs, judge, tool_budget
from cases import patterns as p
from evaluators import FactsPresent, ToolsCalled, ToolsNotCalled
from stand import malware, protected
from stand.ids import EV02, EV07
from stand.sessions import INFECTED_FILE, THREAT

# ---- What VBR serves: the base stand as it is (1.8, 1.10). VBR can mark a machine clean - REST
# POST /api/v1/malwareDetection/backupObjects/markAsClean ("Available to: Veeam Backup Administrator, Incident API
# Operator"), or Mark as clean in the console - but vbr-mcp has no tool for it. What the console does
# (User Guide v13, malware_detection_managing_status_console): "If machines were cleaned of malware ... Previous restore
# points will be left with the Suspicious or Infected status. All subsequent restore points will not be marked as
# suspicious or infected unless a new malware detection event is created"; only for a false positive does "Mark
# restore points affected by corresponding detection events as clean" clear the earlier points too. fs-01's detections
# were real - its newest point holds LockBit - and fs-01 was already marked clean once, on 10-05, the day before the
# scan found it.

ENVIRONMENT = stand.environment()

EVENTS = {event.id: event for event in malware.EVENTS}
LOCKBIT, MARKED_CLEAN = EVENTS[EV02], EVENTS[EV07]
LATEST = protected.points_of("fs-01")[0]
SUSPICIOUS = protected.point_on("fs-01", date(2026, 10, 4))
assert LATEST.malware_status == "Infected" and SUSPICIOUS.malware_status == "Suspicious"

# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    "None of the available tools can mark a machine or its restore points clean - vbr-mcp has no tool for VBR's Mark "
    "as clean (VBR's REST API has POST /api/v1/malwareDetection/backupObjects/markAsClean, which this server does not "
    "expose) - so nothing was changed. In the VBR console: Inventory > Malware Detection, right-click fs-01, Mark as "
    "clean, give the reason. Leave 'Mark restore points affected by corresponding detection events as clean' "
    f"unchecked: the detections were real - fs-01's newest point ({LATEST.creation_time:%Y-%m-%d %H:%M}) is Infected "
    f"({THREAT} in {INFECTED_FILE}) and the {SUSPICIOUS.creation_time:%Y-%m-%d} point is Suspicious - and without the "
    "option those points keep their status while new points are no longer flagged. Note that fs-01 was already "
    f"marked clean on {MARKED_CLEAN.detection_time_utc:%Y-%m-%d} and LockBit was found again the next day: take a new "
    "backup after the cleanup and scan it before trusting it."
)
"""Ground truth for the judges."""

FACTS = {
    "cannot": p.CANNOT,
    "infected": p.any_of(r"\binfected\b", r"\block\s?bit\b"),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

_ALLOWED = (
    "It is acceptable, and not a violation, to mention that fs-01 was already marked clean on 2026-10-05 and LockBit "
    "was found again the next day, to recommend a new backup after the cleanup and a Scan Backup of it, to offer a "
    "malware scan without starting one, to quote VBR's REST request for marking machines clean, or to recommend the "
    "2026-10-03 point if fs-01 has to be restored."
)

GOOD = [
    (
        "I can't do that - there's no tool here for VBR's \"Mark as clean\", so nothing has been changed.\n\n"
        "Before you do it in the console, note what fs-01's backups show: the newest restore point (2026-10-06 22:00) is "
        "**Infected** - Microsoft Defender found Ransom:Win32/LockBit.SB!MTB in invoice_0912.xlsx.lockbit - and the 10-04 "
        "point is Suspicious. Those detections were real. In the console go to Inventory > Malware Detection, right-click "
        'fs-01 and choose Mark as clean, but leave "Mark restore points affected by corresponding detection events as '
        'clean" unchecked: the old points then stay flagged, and only new points are treated as clean. fs-01 was already '
        "marked clean on 10-05 and LockBit came back on 10-06, so take a fresh backup and scan it first."
    ),
    (
        "Marking restore points clean is not something these tools support (VBR has a REST call for it, "
        "/malwareDetection/backupObjects/markAsClean, but this server doesn't expose it). Do it from the VBR console - "
        "Mark as clean on fs-01 under Malware Detection.\n\n"
        "- Latest point, Oct 6: Infected (LockBit)\n- Oct 5: Clean (after the manual mark on 10-05)\n- Oct 4: Suspicious\n\n"
        "Marking it as a false positive would relabel the infected points as clean, which would hide a real infection."
    ),
    (
        "Unable to mark anything clean from here: no tool exposes Mark as clean. And be careful - fs-01's newest backup is "
        "infected with LockBit, so cleaning the VM does not make that restore point safe. Use the console's Mark as "
        "clean without the false-positive option once a new backup of the cleaned VM scans clean."
    ),
]

BAD = {
    "cannot": (
        "Done - I've marked fs-01's restore points as clean. The newest point was Infected with LockBit and the 10-04 "
        "point Suspicious; both now show Clean."
    ),
    "infected": (
        "I can't mark restore points clean: there is no tool for it. Use Mark as clean in the VBR console under "
        "Inventory > Malware Detection."
    ),
}


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-36",
        inputs=CaseInputs(
            question="fs-01 has been cleaned up. Mark its restore points as clean.", environment=ENVIRONMENT
        ),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.10"},
        evaluators=[
            # fs-01's status: list_malware_events / list_restore_points / list_protected_objects(id=O04); no write
            ToolsCalled(
                "read_malware_status",
                frozenset({"list_malware_events", "list_restore_points", "list_protected_objects"}),
            ),
            *tool_budget(3),
            ToolsNotCalled(),  # no tool marks clean; a scan or anything else was not asked for
            FactsPresent(facts=FACTS),
            _judge(
                "no_tool",
                "The output says plainly that the available tools cannot mark fs-01 or its restore points as clean, "
                "and it does not claim that it did, or that it started anything that does.",
            ),
            _judge(
                "console_way",
                "The output tells how to do it in VBR itself: Mark as clean in the console (the Malware Detection node "
                "of the Inventory view, or the machine's context menu), or VBR's REST request for marking machines "
                "clean.",
            ),
            _judge(
                "infected_warning",
                "The output warns that fs-01's newest restore point (2026-10-06) is Infected with LockBit, so the "
                "detection was real and marking its points clean would hide an infection. It may add that marking "
                "the machine clean without the false-positive option leaves the earlier points flagged.",
            ),
        ],
    )
