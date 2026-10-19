# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G2-02: the real backup failures of the last 7 days, retries counted once."""

from datetime import timedelta
from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

import stand
from cases import CaseInputs, Environment, judge, tool_budget
from cases.patterns import name
from evaluators import FactsPresent, ToolsNotCalled
from stand.config_backup import LAST_SUCCESS
from stand.ids import S_ID04, S_ID13, S_ID14, S_ID16, T0
from stand.sessions import BY_ID, SESSIONS

# ---- What VBR serves: the base stand. In the window: SQL-Prod's run of 10-07 failed with both retries; Daily-VMs
# failed on 10-05 and its retry succeeded; Reports-VM was canceled by an admin on 10-04; the Scan Backup of fs-01
# (a SureBackup session) is Failed because it found malware; Copy-to-DR and Agent-Laptops warned. No configuration
# backup ran in the window at all: VBR has not started one since 2026-09-27 (see stand.config_backup).

ENVIRONMENT: Environment = stand.environment()

# ---- What a correct answer says, derived from the data above.

WINDOW_START = T0 - timedelta(days=7)
_IN_WINDOW = [session for session in SESSIONS if session.creation_time >= WINDOW_START]
_WARNED = sorted({s.name for s in _IN_WINDOW if s.result and s.result.result == "Warning"})
assert not any(s.session_type == "ConfigurationBackup" for s in _IN_WINDOW)

EXPECTED = (
    f"Sessions since {WINDOW_START:%Y-%m-%d %H:%M} (server time). The one real backup failure is SQL-Prod's run of "
    f"{BY_ID[S_ID04].creation_time:%Y-%m-%d} 00:00: the first attempt and both automatic retries (00:31, 00:46) "
    "failed - one failure, sharing one original session - on sql-prod-01 (guest credentials, error 1326). "
    f"Not failures: Daily-VMs on {BY_ID[S_ID14].creation_time:%Y-%m-%d} failed on its first attempt (snapshot "
    "timeout on web-02) and succeeded on the retry; Reports-VM on "
    f"{BY_ID[S_ID16].creation_time:%Y-%m-%d} was canceled by LAB\\admin (isCanceled); the Scan Backup session of "
    f"{BY_ID[S_ID13].creation_time:%Y-%m-%d} (SureBackup type) is Failed because it found malware on fs-01, not "
    f"because a backup failed. Warnings, not failures: {', '.join(_WARNED)}. No configuration backup session exists "
    f"in the window: the last configuration backup ran on {LAST_SUCCESS:%Y-%m-%d}."
)
"""Ground truth for the judges."""

FACTS = {
    "sql_prod": name("SQL-Prod"),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

_ALLOWED = (
    "It is acceptable, and not a violation, to list the warnings (Copy-to-DR, Agent-Laptops) and the fs-01 scan "
    "finding separately, to give the cause of each failure, to break the failures down by day, to mention "
    "Daily-VMs' recovered failure and the canceled Reports-VM run as non-failures, and to point out that no "
    f"configuration backup has run since {LAST_SUCCESS:%Y-%m-%d} (a problem of its own, found by checking the "
    "configuration backup rather than the sessions)."
)

GOOD = [
    (
        "Real backup failures in the last 7 days (server time 2026-10-07 09:00):\n\n"
        "1. **SQL-Prod - 2026-10-07 00:00.** One failure: the run and its two automatic retries (00:31, 00:46) all "
        "failed on sql-prod-01 (Win32 error 1326, guest credentials). sql-prod-02 was fine.\n\n"
        "Not counted as failures:\n- Daily-VMs, Oct 5: first attempt failed on web-02 (snapshot timeout), the retry "
        "succeeded.\n- Reports-VM, Oct 4: canceled by LAB\\admin.\n- Scan Backup of fs-01, Oct 6: Failed means malware "
        "was found, not a backup failure.\n- Copy-to-DR and Agent-Laptops ended with warnings."
    ),
    (
        "| Job | When | Verdict |\n|---|---|---|\n| SQL-Prod | 07.10 00:00 (+2 retries) | **Failed** - sql-prod-01 |\n"
        "| Daily-VMs | 05.10 22:00 | recovered by retry |\n| Reports-VM | 04.10 | canceled by user |\n\n"
        "So there is exactly one real failure: SQL-Prod last night."
    ),
    (
        "Only one: SQL Prod's nightly run on Oct 7 failed after its retries (all three attempts on sql-prod-01). "
        "Everything else either succeeded, recovered on retry (Daily-VMs, Oct 5), was canceled (Reports-VM) or is a "
        "malware scan result. Note also that the configuration backup has not run since Sep 27."
    ),
]

BAD = {
    "sql_prod": "There were three real failures: Daily-VMs on Oct 5, Reports-VM on Oct 4 and the fs-01 backup scan "
    "on Oct 6.",
}


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G2-02",
        inputs=CaseInputs(
            question="Give me the real backup failures over the last 7 days — don't count retries twice.",
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G2", "base_stand": "1.3"},
        evaluators=[
            # list_sessions is the only history; get_server_status (what "now" is), get_session_failure_details per
            # real failure and get_config_backup_status are reads the case allows on top of it.
            ToolCorrectness(expected_tools=["list_sessions"], allow_extra=True),
            *tool_budget(5),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "sql_prod_counted_once",
                "The output counts SQL-Prod's night of 2026-10-07 as one failure (one run whose attempts all "
                "failed), not as three failures.",
            ),
            _judge(
                "daily_vms_recovered",
                "The output does not count Daily-VMs on 2026-10-05 as a failure: it failed on the first attempt "
                "and the retry succeeded. Mentioning it as recovered on retry is fine.",
            ),
            _judge(
                "canceled_not_failure",
                "The output does not count the canceled Reports-VM run of 2026-10-04 as a failure. Mentioning it "
                "as canceled is fine.",
            ),
            _judge(
                "scan_explained",
                "The output does not present the Failed Scan Backup session of fs-01 as a backup failure without "
                "explaining that the scan found malware. Leaving the scan out, or listing it separately as a "
                "malware finding, is fine.",
            ),
            _judge(
                "warnings_not_failures",
                "The output does not count the Warning results of Copy-to-DR or Agent-Laptops as failures. Listing "
                "them as warnings is fine.",
            ),
            _judge(
                "no_invented_config_failures",
                "The output does not claim that configuration backup sessions failed in the last 7 days or quote "
                "an error of one: there is no configuration backup session in the window. Saying that no "
                "configuration backup ran, or that its last run was on 2026-09-27, is fine.",
            ),
        ],
    )
