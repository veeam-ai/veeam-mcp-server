# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G2-21: a malware scan that failed for a technical reason - it found nothing, and it verified nothing."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import CaseInputs, judge, tool_budget
from cases.patterns import any_of, near
from evaluators import FactsPresent, ToolsCalled, ToolsNotCalled
from stand import environment, protected, sessions
from stand.ids import at, mnemonic
from vbr_models.sessions import AntivirusTaskSession

# ---- What VBR serves: the base stand plus one more Scan Backup: an admin scanned web-02's newest restore point last
# night, and the scan itself failed. A Scan Backup is a SureBackup session named "Scan Backup" (swagger,
# POST /malwareDetection/scanBackup); its antivirus task's outcome is scanResult, and EAntivirusScanResult has Failed
# and Inconclusive besides Clean and Infected (swagger). Unlike S-ID13, whose Failed means malware was found, here the
# antivirus did not finish: the point was not verified either way, and no malware event was created (a scan raises
# one only when it finds something - User Guide v13, scan_backup_antivirus_hiw).

POINT = protected.points_of("web-02")[0]
SCAN = sessions.session(
    17,
    "Scan Backup",
    at(6, 23, 50, 0),
    at(6, 23, 58, 31),
    "Failed",
    message="Failed to scan 1 of 1 restore points. See the session log for details.",
    initiated_by=sessions.ADMIN,
    session_type="SureBackup",
    platform="VMware",
)
TASK = AntivirusTaskSession(
    id=mnemonic("41000000", 13),
    session_id=SCAN.id,
    session_type="SureBackup",
    creation_time=at(6, 23, 50, 20),
    end_time=at(6, 23, 58, 20),
    name="web-02",
    restore_point_id=POINT.id,
    restore_point_reference=f"/api/v1/restorePoints/{POINT.id}",
    scan_type="Antivirus",
    scan_result="Failed",
    scan_state="Finished",
    antivirus_name=sessions.ANTIVIRUS,
)
SCAN_ERROR = (
    f"Antivirus scan failed: {sessions.ANTIVIRUS} did not complete the scan of the mounted disks within the allotted "
    "time (3600 s)."
)
"""Neutral wording of ours: VBR's own text for a scan that times out was not verified."""

_SESSION_LOG = sessions.log(
    SCAN.creation_time,
    [
        ("Succeeded", f"Scan Backup started by {sessions.ADMIN}"),
        ("Succeeded", f"Scanning restore point of web-02 created {POINT.creation_time:%Y-%m-%d %H:%M}"),
        ("Failed", "Failed to scan 1 of 1 restore points"),
    ],
    SCAN.end_time,
)
_TASK_LOG = sessions.log(
    TASK.creation_time,
    [
        ("Succeeded", "Queued for processing"),
        ("Succeeded", "Restore point mounted to repo-win01.lab.local"),
        ("Succeeded", f"Scanning restore point with {sessions.ANTIVIRUS}"),
        ("Failed", SCAN_ERROR),
        ("Failed", "Restore point was not scanned"),
    ],
    TASK.end_time,
)

ENVIRONMENT = environment(
    sessions=sorted([SCAN, *sessions.SESSIONS], key=lambda s: s.creation_time, reverse=True),
    tasks=sorted([TASK, *sessions.TASKS], key=lambda t: t.creation_time, reverse=True),
    session_logs={SCAN.id: _SESSION_LOG},
    task_logs={TASK.id: _TASK_LOG},
)

# ---- What a correct answer says, derived from the data above.

assert SCAN.end_time is not None and POINT.malware_status == "Clean"

EXPECTED = (
    f"Last night's scan of web-02 (Scan Backup started by {sessions.ADMIN} on {SCAN.creation_time:%Y-%m-%d} at "
    f"{SCAN.creation_time:%H:%M}) did not find anything - but only because it did not complete: its antivirus task "
    f"for web-02's newest restore point ({POINT.creation_time:%Y-%m-%d %H:%M}) ended with scan result Failed: "
    f"{sessions.ANTIVIRUS} did not complete the scan of the mounted disks in time. So the point was neither found "
    "infected nor verified clean; the session's Failed status here means the scan itself failed, not that malware "
    "was found, and no malware event was raised. (The point's own status Clean only means no detection is recorded "
    "for it.) Next: find out why the antivirus timed out on the mount server repo-win01 (load, exclusions, the "
    "engine's health) and run the scan again."
)
"""Ground truth for the judges."""

_NOT_DONE = any_of(
    r"\b(did\s*n[o']?t|did\s+not|was\s*n[o']?t|was\s+not|could\s*n[o']?t|could\s+not)\s+(complete|finish|run|scan)",
    r"\b(never|not)\s+(completed|finished)",
    r"\bincomplete\b",
    r"\b(timed?\s*out|time-?out)\b",
    r"\bscan\s+(itself\s+)?failed\b",
    r"\bfailed\s+to\s+(complete|scan|finish)",
)

FACTS = {
    # the scan did not get to a verdict: it failed or timed out, rather than finding something
    "scan_failed": _NOT_DONE,
    # so it verified nothing: not clean, not infected
    "not_verified": any_of(
        r"\b(not|n't|never)\s+(been\s+|yet\s+)?(verified|confirmed|checked|scanned|determined|established)\b",
        r"\b(unverified|unconfirmed|undetermined|inconclusive|indeterminate|unknown)\b",
        r"\bno\s+(verdict|result|conclusion|answer)\b",
        r"\b(neither|nor)\s+([\w-]+\s+){0,2}?(clean|infected)\b",
        near(
            r"\b(can(not|'t)|could\s*n[o']?t|unable\s+to|no\s+way\s+to)\s+(say|tell|confirm|conclude|know|determine)",
            r"clean|infected|malware",
            60,
        ),
    ),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    """The scan didn't find anything - but it also didn't finish. Last night's Scan Backup of web-02 (started 2026-10-06 23:50 by LAB\\admin) shows **Failed**, and its antivirus task for web-02's latest restore point ended with scan result *Failed*: Microsoft Defender Antivirus did not complete the scan of the mounted disks within the time limit (3600 s).

So the point was not verified: it is neither confirmed clean nor infected, and no malware event was created. Check the antivirus on the mount server (repo-win01) - load, exclusions, Defender's health - and run the scan again.""",
    """Short answer: no result. The Scan Backup session for web-02 failed because the antivirus timed out, so nothing was scanned to the end - we cannot say whether web-02's newest restore point is clean or infected. Rerun the scan once Defender on the mount server is working.""",
    """Nothing was found, but the result is inconclusive: the antivirus task for web-02's newest restore point failed - Microsoft Defender did not complete the scan in time - so whether the point is clean is undetermined. Run the scan again after checking Defender on repo-win01.""",
]

BAD = {
    "scan_failed": (
        "The last scan of web-02 found malware: the Scan Backup session ended Failed, which is how VBR reports an "
        "infection. Don't restore web-02's latest point until it is verified."
    ),
    "not_verified": (
        "The scan of web-02 failed to complete because the antivirus timed out, but the restore point is Clean, so "
        "web-02 is fine and nothing needs to be done."
    ),
}

_ALLOWED = (
    "It is acceptable, and not a violation, to give the scan's start and end times or who started it, to quote the "
    "error from the task log, to mention the point's recorded status Clean as 'no detection recorded' (not as a scan "
    "result), to mention the earlier Informative signature scan of 2026-10-04 as a separate event, or to suggest "
    "checking the antivirus on the mount server and rerunning the scan, as advice."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G2-21",
        inputs=CaseInputs(
            question="Did last night's malware scan of web-02 find anything?",
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G2", "base_stand": "1.3, 1.10"},
        evaluators=[
            # the scan session, then its antivirus task (scanResult) or its failure details: the session's Failed
            # alone does not tell a failed scan from a finding
            ToolCorrectness(expected_tools=["list_sessions"], allow_extra=True),
            ToolsCalled("scan_task_read", frozenset({"list_task_sessions", "get_session_failure_details"})),
            *tool_budget(4),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "not_infected",
                "The output does not say or imply that the scan found malware on web-02 or that web-02's restore "
                "point is infected or suspicious.",
            ),
            _judge(
                "not_clean_by_scan",
                "The output does not say the scan showed web-02's restore point to be clean. Mentioning that the "
                "point carries no recorded detection is fine if it is not presented as the scan's result.",
            ),
            _judge(
                "failed_explained",
                "The output explains that this Scan Backup's Failed status comes from the scan itself failing (the "
                "antivirus did not complete), not from a finding.",
            ),
            _judge(
                "no_scan_started",
                "The output does not claim to have started a new scan; suggesting one is fine.",
            ),
        ],
    )
