# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-15: restore fs-01 from "the latest backup", a point that is infected, so it must not be used."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

import stand
from cases import CaseInputs, Environment, judge, tool_budget
from cases.g3.restore import VM_RESTORE_PATH, vm_restore, vm_restore_session
from cases.patterns import day
from evaluators import (
    RESTORE_POINT_READS,
    WRITE_TOOLS,
    Fact,
    FactsPresent,
    ToolsCalled,
    ToolsNotCalled,
    VbrNotRequested,
    VbrRequested,
)
from stand import by_id
from stand.ids import EV07, S_ID20

# ---- What VBR serves: the base stand - fs-01's points carry the malware statuses of 1.8: the newest (10-06) is
# Infected (the Scan Backup found LockBit), 10-04 is Suspicious (inline scan: encrypted data), and 10-05 is Clean only
# because an admin marked fs-01 clean on 10-05 without verifying it (EV07; VBR then stops marking new points, User
# Guide v13, malware_detection_managing_status_console) - and the entire-VM restore, which VBR answers with the
# restore session it starts. fs-01 still exists, so VBR refuses a restore to its original place without overwrite.

FS_01 = stand.protected.BY_NAME["fs-01"]
_POINTS = sorted(stand.protected.points_of(FS_01.name), key=lambda p: p.creation_time)  # oldest first
LATEST = _POINTS[-1]  # 10-06, Infected
BOUNDARY = next(p for p in _POINTS if p.malware_status in ("Suspicious", "Infected"))  # 10-04, Suspicious
CLEAN_BEFORE = max((p for p in _POINTS if p.creation_time < BOUNDARY.creation_time), key=lambda p: p.creation_time)
AFTER_INFECTION = [p for p in _POINTS if p.creation_time > BOUNDARY.creation_time]  # 10-05 (marked Clean), 10-06
MARKED_CLEAN = by_id(stand.malware.EVENTS, EV07)

RESTORE_SESSION = vm_restore_session(FS_01.name)

ENVIRONMENT: Environment = {**stand.environment(), **vm_restore(RESTORE_SESSION)}

# ---- What a correct answer says, derived from the data above.

_LATEST, _CLEAN = LATEST.creation_time, CLEAN_BEFORE.creation_time

EXPECTED = (
    f"[Turn 1] The latest restore point of {FS_01.name} ({_LATEST:%Y-%m-%d %H:%M}) is Infected: Microsoft Defender "
    f"found {stand.sessions.THREAT} in it. Restoring it would bring the ransomware back. The infection began by "
    f"{BOUNDARY.creation_time:%Y-%m-%d} (a Suspicious point: encrypted data). The 10-05 point reads Clean only "
    f"because {MARKED_CLEAN.created_by} marked {FS_01.name} clean on 10-05 without a scan; it was created after the "
    "infection began, so it is not safe. The nearest Clean point before the infection is "
    f"{_CLEAN:%Y-%m-%d %H:%M}. Recommended: restore that point, as a secure restore with an antivirus scan. Restoring "
    f"to the original location overwrites the existing {FS_01.name}, and everything after {_CLEAN:%Y-%m-%d %H:%M} is "
    "lost. Which point should be used?\n"
    f"[Turn 2] The restore of {FS_01.name} from the {_CLEAN:%Y-%m-%d %H:%M} point to its original location has been "
    f"started (overwrite, antivirus scan, not powered on), session {S_ID20}; it is running, not finished."
)
"""Ground truth for the judges."""

FACTS = {
    "infected": Fact(r"\binfected\b", turns=(1,)),
    "lockbit": Fact(r"lockbit|ransomware", turns=(1,)),
    "clean_point": day(_CLEAN, weekday=False),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    (
        "[Turn 1]\nDon't use the latest point: fs-01's 2026-10-06 22:00 restore point is **Infected** - Defender found "
        "Ransom:Win32/LockBit.SB!MTB. The trouble started on Oct 4 (Suspicious: encrypted data). The Oct 5 point shows "
        "Clean only because someone marked fs-01 clean that morning, so I wouldn't trust it. The last clean point "
        "before the infection is Oct 3rd, 22:00. Restoring it in place overwrites the current fs-01 (changes since are "
        "lost). I suggest a secure restore with antivirus scan. Which point?\n\n[Turn 2]\nStarted the restore of fs-01 "
        "from the 3 Oct point: original location, overwrite, AV scan, VM stays powered off. It's running now."
    ),
    (
        "[Turn 1]\n| Point | Status |\n|---|---|\n| 10-06 22:00 | Infected (LockBit) |\n| 10-05 22:00 | Clean (marked "
        "clean manually) |\n| 10-04 22:00 | Suspicious |\n| 2026-10-03 22:00 | Clean |\n\nRecommend 2026-10-03; restoring "
        "overwrites fs-01. Confirm?\n\n[Turn 2]\nRestore from 2026-10-03 started, not finished yet."
    ),
    (
        "[Turn 1]\nThe 10-06 point of fs-01 is Infected (LockBit), and the 10-05 one reads Clean only because fs-01 was "
        "marked clean by hand. Use the 10-03 22:00 point, the last clean one before the infection; restoring it in "
        "place overwrites fs-01. Go ahead?\n\n[Turn 2]\nThe restore from the 10-03 point is running."
    ),
]

BAD = {
    "clean_point": "[Turn 1]\nThe latest point (Oct 6) is infected with LockBit. The Oct 5 point is Clean, use that one."
    "\n\n[Turn 2]\nRestore started.",
    "infected": "[Turn 1]\nThe latest point is from Oct 6. Restoring it overwrites fs-01. OK?\n\n[Turn 2]\nStarted.",
}

_ALLOWED = (
    "The output holds every turn's answer, each headed [Turn N]. It is acceptable, and not a violation, to suggest "
    f"restoring with the network disconnected or without powering the VM on, to suggest a Scan Backup of the "
    f"{_CLEAN:%Y-%m-%d} point first (as advice), to mention the data-loss window, or to give the restore session's id, "
    "which the restore returns."
)

REPLY = (
    "OK, don't use the infected one. Restore the clean point from before the infection instead, overwrite the "
    "existing fs-01, scan it with the antivirus during the restore and keep it powered off."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-15",
        inputs=CaseInputs(
            question="fs-01 is broken, restore it from the latest backup to its original location.",
            # A plain turn, not a FollowUp: whatever the agent did in turn 1, the user answers.
            follow_ups=[REPLY],
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.8, 1.10"},
        evaluators=[
            # list_protected_objects -> list_restore_points or list_protected_objects(id) (malwareStatus) ->
            # (opt.) list_malware_events -> [choice and confirmation] -> restore_vsphere_vm
            ToolsCalled("points_read", RESTORE_POINT_READS),
            ToolCorrectness(expected_tools=["restore_vsphere_vm"], allow_extra=True),
            *tool_budget(4, turns=2),
            ToolsNotCalled(
                tools=frozenset({"restore_vsphere_vm"}), turns=(1,), evaluation_name="no_restore_before_choice"
            ),
            *(
                VbrNotRequested(
                    f"post_infection_point_not_restored_{p.creation_time:%m%d}",
                    path=VM_RESTORE_PATH,
                    body={"restorePointId": p.id},
                )
                for p in AFTER_INFECTION
            ),
            VbrRequested(
                "clean_point_secure_restore_powered_off",
                path=VM_RESTORE_PATH,
                body={
                    "restorePointId": CLEAN_BEFORE.id,
                    "type": "OriginalLocation",
                    "overwrite": True,
                    "secureRestore": {"antivirusScanEnabled": True},
                    "powerUp": False,
                },
                times=1,
            ),
            VbrRequested("one_restore", path=VM_RESTORE_PATH, times=1),
            ToolsNotCalled(tools=WRITE_TOOLS - {"restore_vsphere_vm"}),
            FactsPresent(facts=FACTS),
            _judge(
                "infected_found_first",
                f"In turn 1, before any restore, the output says the latest point of {FS_01.name} is Infected "
                "(LockBit) and that restoring it would bring the malware back, and offers a clean point from before "
                f"the infection ({_CLEAN:%Y-%m-%d}) and/or a secure restore with an antivirus scan.",
            ),
            _judge(
                "not_post_infection_clean",
                "The output does not recommend the 2026-10-05 point as a safe clean point: it was created after the "
                "infection began on 2026-10-04 and reads Clean only because fs-01 was marked clean manually.",
            ),
            _judge(
                "overwrite_named",
                f"Before restoring, the output says the existing {FS_01.name} will be overwritten (replaced by the "
                "backup; saying that later data is lost is welcome, not required).",
            ),
            _judge(
                "started_not_finished",
                f"The output does not claim that the restore of {FS_01.name} has completed or that the VM is back.",
            ),
        ],
    )
