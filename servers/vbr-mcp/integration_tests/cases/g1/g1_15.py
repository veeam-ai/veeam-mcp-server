# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G1-15: malware detections of the last 30 days, then the YARA rules available (two turns)."""

from datetime import date, datetime, timedelta
from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import MULTI_TURN, CaseInputs, Environment, judge, tool_budget
from cases.patterns import any_of, day, name
from evaluators import Fact, FactsPresent, ToolsCalled, ToolsNotCalled
from stand import environment, malware
from stand.ids import EV01, EV02, EV07, EV08, SERVER_TZ, T0

# ---- What VBR serves: the base stand. Its malware events (1.10) within the last 30 days:
# - fs-01: Suspicious on 10-04 (inline scan, encrypted data, EV01), marked clean by an admin on 10-05 - not as a false
#   positive (EV07) - and then Infected on 10-06, when a Scan Backup found LockBit in its newest point (EV02);
# - web-02: Suspicious on 10-04 (a bulk file deletion, EV08), whose proactive signature scan found nothing (EV03,
#   Informative): flagged, not confirmed;
# - web-01: a mass rename of 09-30 marked clean as a false positive (EV06, EV04).
# app-01's false positive (EV05, EV09) is older than 30 days.

ENVIRONMENT: Environment = environment()

# ---- What a correct answer says, derived from the data above.

WINDOW_START = T0 - timedelta(days=30)
_EVENTS = {event.id: event for event in malware.EVENTS}
_FS_SUSPICIOUS, _FS_INFECTED, _FS_MARKED_CLEAN, _WEB_02_SUSPICIOUS = (_EVENTS[i] for i in (EV01, EV02, EV07, EV08))
_YARA = [rule.file_name for rule in malware.YARA_RULES]


def _local_day(moment: datetime) -> date:
    return moment.astimezone(SERVER_TZ).date()


EXPECTED = (
    f"[Turn 1] In the last 30 days (since {WINDOW_START:%Y-%m-%d}) VBR recorded detections on two machines. fs-01: "
    f"Suspicious on {_local_day(_FS_SUSPICIOUS.detection_time_utc)} (inline scan: 3412 files with encrypted, "
    f"high-entropy data), then Infected on {_local_day(_FS_INFECTED.detection_time_utc)} - a Scan Backup with "
    "Microsoft Defender Antivirus found Ransom:Win32/LockBit.SB!MTB in its newest restore point. An admin had marked "
    f"fs-01 clean on {_local_day(_FS_MARKED_CLEAN.detection_time_utc)}, before that finding, so the infection is not "
    f"resolved. web-02: Suspicious on {_local_day(_WEB_02_SUSPICIOUS.detection_time_utc)} (a mass deletion of 2400 "
    "files); the proactive signature scan it triggered found no threats (an Informative event), so it is flagged but "
    "not confirmed malware. The web-01 rename event of 2026-09-30 was marked clean as a false positive (the "
    "MarkAsCleanEvent is that remediation, not a detection), and the app-01 events are older than 30 days.\n"
    f"[Turn 2] Two YARA rules are available: {_YARA[0]} and {_YARA[1]}."
)
"""Ground truth for the judges."""

FACTS = {
    "fs_01": Fact(name("fs-01"), turns=(1,)),
    "infected": Fact(r"\binfected\b", turns=(1,)),
    "lockbit": Fact(r"lockbit(?!_indicators)", turns=(1,)),  # the threat, not the YARA rule named after it
    "infected_date": Fact(day(_local_day(_FS_INFECTED.detection_time_utc)), turns=(1,)),
    "suspicious": Fact(r"\bsuspicious\b", turns=(1,)),
    "suspicious_date": Fact(day(_local_day(_FS_SUSPICIOUS.detection_time_utc)), turns=(1,)),
    "web_02": Fact(name("web-02"), turns=(1,)),
    **{
        f"yara_rule_{n}": Fact(any_of(name(rule), name(rule.removesuffix(".yar"))), turns=(2,))
        for n, rule in enumerate(_YARA, 1)
    },
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

_ALLOWED = (
    f"{MULTI_TURN} "
    "It is acceptable, and not a violation, to offer (without doing it) to scan fs-01 with Lockbit_Indicators.yar "
    "or to look for its nearest clean restore point, to mention the excluded events while explaining why they are "
    "not detections, or to list the events as a table."
)

GOOD = [
    (
        "[Turn 1]\nYes. In the last 30 days (since 2026-09-07) VBR recorded detections on two machines:\n\n"
        "- **fs-01** - Suspicious on 2026-10-04 (inline scan: 3412 files with encrypted, high-entropy data), then "
        "Infected on 2026-10-06: Microsoft Defender found Ransom:Win32/LockBit.SB!MTB in its newest restore point during "
        "a Scan Backup. fs-01 had been marked clean on 10-05, but the LockBit finding came after that, so treat it as "
        "infected.\n- **web-02** - Suspicious on 2026-10-04 (2400 files deleted at once); the signature scan it triggered "
        "found no threats (Informative), so it is not confirmed malware.\n\nThe web-01 rename event of 2026-09-30 was "
        "marked a false positive, and the app-01 event is older than 30 days.\n\n"
        "[Turn 2]\nTwo YARA rules are available: Ransomware_Generic.yar and Lockbit_Indicators.yar."
    ),
    (
        "[Turn 1]\n| Machine | Detected | Severity | What |\n|---|---|---|---|\n"
        "| fs-01 | Oct 6th | Infected | LockBit ransomware (Ransom:Win32/LockBit.SB!MTB), Defender during a backup scan |\n"
        "| fs-01 | 4 Oct 2026 | Suspicious | inline scan: encrypted (high-entropy) files |\n"
        "| web-02 | 4 Oct 2026 | Suspicious | mass file deletion; the follow-up signature scan found nothing |\n\n"
        "fs-01 is the real problem: it was marked clean on Oct 5, yet LockBit was found the day after. web-01's event "
        "was a false positive.\n\n[Turn 2]\nYou can scan with Ransomware_Generic and Lockbit_Indicators."
    ),
]
"""Answers a correct agent could give: every fact must match each of them."""

BAD = {
    "fs_01": "[Turn 1]\nNo malware was detected in the last 30 days.\n\n[Turn 2]\nRansomware_Generic.yar and "
    "Lockbit_Indicators.yar.",
    "lockbit": "[Turn 1]\nfs-01 was flagged Suspicious on 2026-10-04 and web-02 on 2026-10-04; fs-01 was marked "
    "clean on 10-05.\n\n[Turn 2]\nRansomware_Generic.yar and Lockbit_Indicators.yar.",
    "web_02": "[Turn 1]\nOnly fs-01: Suspicious on 2026-10-04, Infected (LockBit) on 2026-10-06.\n\n[Turn 2]\n"
    "Ransomware_Generic.yar and Lockbit_Indicators.yar.",
    "yara_rule_2": "[Turn 1]\nfs-01: Suspicious on 2026-10-04, Infected with LockBit on 2026-10-06 - you could scan "
    "it with Lockbit_Indicators.yar. web-02: Suspicious on 2026-10-04.\n\n[Turn 2]\nYou have Ransomware_Generic.yar.",
}
"""Per fact, an answer that gets that fact wrong: the fact must not match it."""


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G1-15",
        inputs=CaseInputs(
            question="Have we had any malware detections in the last 30 days?",
            follow_ups=["Which YARA rules do we have available for scanning?"],
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G1", "base_stand": "1.10"},
        evaluators=[
            # get_server_status (what "the last 30 days" ends at) is a read the case allows on top of these.
            ToolsCalled("events_read", frozenset({"list_malware_events"}), turns=(1,)),
            ToolCorrectness(expected_tools=["list_malware_events", "get_yara_rules"], allow_extra=True),
            *tool_budget(3, turns=2),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "fs01_infected_web02_unconfirmed",
                "The first answer reports fs-01 as infected (LockBit found on 2026-10-06), and web-02's event as "
                "suspicious, not as an infection (that its signature scan found nothing is welcome, not required). "
                "It presents no other machine "
                "as having an open detection in the last 30 days; listing web-01's event is fine as long as it is "
                "shown as a false positive that was cleared.",
            ),
            _judge(
                "mark_clean_not_resolution",
                "The output does not say that fs-01's infection is resolved or cleared because it was marked clean on "
                "2026-10-05: the Infected finding of 2026-10-06 came after that.",
            ),
            _judge(
                "informative_is_not_a_detection",
                "The output does not present web-02's Informative event as a malware finding: it is a signature scan "
                "that found no threats.",
            ),
            _judge(
                "false_positive_is_not_a_detection",
                "The output does not present web-01 as having an open detection: its RenamedFiles event was marked a "
                "false positive, and the MarkAsCleanEvent is a remediation marker, not a detection. Listing the event "
                "is fine if it is clearly labelled as a false positive (e.g. counted apart from the real detections).",
            ),
            _judge(
                "window_respected",
                "The output does not count the app-01 events of 2026-08-28/29 as detections of the last 30 days: they "
                "are older than the window (and a false positive).",
            ),
            _judge(
                "only_listed_rules",
                f"The second answer names only the YARA rules {_YARA[0]} and {_YARA[1]}, and no other rule as "
                "available.",
            ),
            _judge(
                "no_scan_started",
                "The output does not say that it started, ran or queued a malware or YARA scan. Offering one is fine.",
            ),
        ],
    )
