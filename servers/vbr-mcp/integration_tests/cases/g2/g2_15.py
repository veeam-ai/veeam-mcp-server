# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G2-15: what the last malware scan of fs-01 found."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case

from cases import CaseInputs, judge, tool_budget
from cases.patterns import any_of, clock, day, near
from evaluators import FactsPresent, ToolsCalled, ToolsNotCalled
from stand import environment, protected, sessions
from stand.ids import S_ID13

# ---- What VBR serves: the base stand. The last scan of fs-01 (1.3) is the Scan Backup an admin ran on its newest
# restore point: a SureBackup session named "Scan Backup" (swagger, POST /malwareDetection/scanBackup), Failed because
# the antivirus found LockBit; its one task is an antivirus task whose outcome is scanResult=Infected, and the
# finding is also malware event EV02 (1.10). The Suspicious inline detection of 10-04 (EV01) is an older, different
# event.

ENVIRONMENT = environment()

# ---- What a correct answer says, derived from the data above.

SCAN = sessions.BY_ID[S_ID13]
TASK = sessions.T07_SCAN
_POINT = next(p for p in protected.points_of("fs-01") if p.id == TASK.restore_point_id)
assert SCAN.end_time is not None and TASK.scan_result == "Infected"

EXPECTED = (
    f"The last scan of fs-01 is the Scan Backup session (a SureBackup-type session) started by {SCAN.initiated_by} "
    f"on {SCAN.creation_time:%Y-%m-%d} at {SCAN.creation_time:%H:%M}, finished at {SCAN.end_time:%H:%M}. It checked "
    f"fs-01's latest restore point, {_POINT.creation_time:%Y-%m-%d %H:%M}. Result: Infected - {sessions.ANTIVIRUS} "
    f"found {sessions.THREAT} in {sessions.INFECTED_FILE}. The session's Failed status means the scan found an "
    "infection, not that the scan broke. (The Suspicious inline detection of 2026-10-04 is a different, earlier event.)"
)
"""Ground truth for the judges."""

FACTS = {
    "infected": any_of(r"infect", r"ransom"),
    "threat": r"lockbit",
    "file": r"invoice_0912",
    # the point it scanned: the newest one, by its date and time or in words
    "restore_point": any_of(
        r"\b(latest|newest|most\s+recent|last)\s+(backup\s+)?(restore\s+)?point",
        near(day(_POINT.creation_time, weekday=False), clock(_POINT.creation_time), 40),
        str(_POINT.id),
    ),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    """The last malware scan of fs-01 found an infection. A Scan Backup run on 2026-10-06 at 23:20 scanned fs-01's latest restore point (2026-10-06 22:00) with Microsoft Defender Antivirus, which detected **Ransom:Win32/LockBit.SB!MTB** in `E:\\Shares\\finance\\Q3\\invoice_0912.xlsx.lockbit`. The point is marked Infected. The session shows Failed - for a Scan Backup that is how VBR reports that malware was found, not a broken scan.""",
    """Result: Infected - LockBit ransomware.

- Scan: "Scan Backup", started by LAB\\admin on Oct 6 at 11:20 PM, finished 11:36 PM
- Scanned: the newest restore point of fs-01
- Finding: Ransom:Win32/LockBit.SB!MTB in invoice_0912.xlsx.lockbit (E:\\Shares\\finance\\Q3)

The Suspicious inline-scan event of Oct 4 (encrypted data) is a separate, earlier detection.""",
    """The last malware scan of **fs-01** found:

- **Threat:** `Ransom:Win32/LockBit.SB!MTB`
- **File:** `E:\\Shares\\finance\\Q3\\invoice_0912.xlsx.lockbit`
- **Verdict:** **Infected**
- **Scanner:** Microsoft Defender Antivirus
- **Scan completed:** October 6, 2026 at 23:36 (server time, UTC+2)
- **Restore point:** `51000000-0000-0000-1045-000000000000`

The scan completed successfully as a scan operation; its session result is **Failed** because malware was detected.""",  # a real answer
]

BAD = {
    "infected": (
        "The last scan of fs-01 (Scan Backup, 2026-10-06 23:20) checked its latest restore point and found no "
        "threats: the point is Clean."
    ),
    "threat": (
        "The last scan of fs-01 is the inline scan of 2026-10-04: it flagged the latest restore point as Suspicious "
        "because 3412 files hold encrypted (high-entropy) data - possibly an infection."
    ),
}

_ALLOWED = (
    "It is acceptable, and not a violation, to say who started the scan and when, to name the antivirus, to mention "
    "the earlier Suspicious inline detection separately, or to propose a next step such as finding a clean restore "
    "point before the infection, as long as the output does not claim it did so."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G2-15",
        inputs=CaseInputs(question="What did the last malware scan of fs-01 find?", environment=ENVIRONMENT),
        expected_output=EXPECTED,
        metadata={"group": "G2", "base_stand": "1.3, 1.10"},
        evaluators=[
            # the finding is in the scan session (its task and logs) and in the malware event it raised: either road
            # answers; list_task_sessions and get_session_failure_details are reads the case allows on top
            ToolsCalled("scan_found", frozenset({"list_sessions", "list_malware_events"})),
            *tool_budget(4),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "failed_means_found",
                "If the output mentions that the scan session's status is Failed, it explains that this Failed "
                "means the scan found malware, not that the scan or a backup broke. An output that does not mention "
                "the Failed status meets this criterion.",
            ),
            _judge(
                "not_clean_or_broken",
                "The output does not call the scan or the restore point clean, and does not say the scan failed for "
                "a technical reason.",
            ),
            _judge(
                "not_the_inline_event",
                "The output does not present the Suspicious inline detection of 2026-10-04 (encrypted data in 3412 "
                "files) as what the last scan found. Mentioning it separately as an earlier event is fine.",
            ),
        ],
    )
