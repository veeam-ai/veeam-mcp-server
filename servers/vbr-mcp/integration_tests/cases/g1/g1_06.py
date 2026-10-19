# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G1-06: the sessions of the last 24 hours."""

from datetime import timedelta
from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import CaseInputs, judge, tool_budget
from cases.patterns import any_of, name
from evaluators import FactsPresent, ToolsNotCalled
from stand import environment
from stand.ids import S_ID04, T0
from stand.sessions import SESSIONS
from vbr_models.sessions import Session

# ---- What VBR serves: the base stand, whose session history goes back eight days. Twelve sessions fall in the last
# 24 hours by the server's clock. Among them: SQL-Prod's run of 00:00 with its two automatic retries (only the
# retries carry retryInfo), the Scan Backup an admin ran - a SureBackup session whose Failed means it found malware -
# and SQL-Dev running since 08:40. No configuration backup ran: VBR has not started one since 09-27.

ENVIRONMENT = environment()

# ---- What a correct answer says, derived from the stand.

WINDOW_START = T0 - timedelta(hours=24)
IN_WINDOW = sorted((s for s in SESSIONS if s.creation_time >= WINDOW_START), key=lambda s: s.creation_time)
_JOBS = list(dict.fromkeys(s.name for s in IN_WINDOW if s.session_type != "SureBackup"))
_SQL_PROD = [s for s in IN_WINDOW if s.original_session_id == S_ID04]
_RETRIES = [s for s in _SQL_PROD if s.retry_info is not None]
_SCAN = next(s for s in IN_WINDOW if s.session_type == "SureBackup")
_RUNNING = next(s for s in IN_WINDOW if s.end_time is None)
assert len(_SQL_PROD) == 3 and len(_RETRIES) == 2
assert not any(s.session_type == "ConfigurationBackup" for s in IN_WINDOW)


def _outcome(session: Session) -> str:
    if session.end_time is None:
        return "running"
    return session.result.result if session.result else "None"


EXPECTED = (
    f"{len(IN_WINDOW)} sessions were created since {WINDOW_START:%Y-%m-%d %H:%M} (UTC+02:00): "
    + "; ".join(f"{s.creation_time:%m-%d %H:%M} {s.name} ({s.session_type}) {_outcome(s)}" for s in IN_WINDOW)
    + f". SQL-Prod ran once at {_SQL_PROD[0].creation_time:%H:%M} and failed: the run is one session plus its "
    f"{len(_RETRIES)} automatic retries ({', '.join(f'{s.creation_time:%H:%M}' for s in _RETRIES)}), all Failed. The "
    f"{_SCAN.name} session at {_SCAN.creation_time:%H:%M} has result Failed, which means the scan found malware (in "
    f"fs-01's newest restore point), not that a backup failed. {_RUNNING.name} (started "
    f"{_RUNNING.creation_time:%H:%M}, manually) is still running at 45%, so it has no duration yet. Copy-to-DR and "
    "Agent-Laptops ended with Warning. No configuration backup ran in the window, and no session was canceled."
)
"""Ground truth for the judges."""

FACTS = {
    **{f"job_{job.lower().replace('-', '_')}": name(job) for job in _JOBS},
    "scan": any_of(r"\bscan\b", r"\bsurebackup\b"),
    "retries": any_of(r"\bretr(?:y|ies|ied|ying)\b", r"\bre-?attempt", r"\battempts\b", r"\bre-?tried\b"),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

_ALLOWED = (
    "It is acceptable, and not a violation, to present the sessions as a table, to group them by type or by job, to "
    "sum the SQL-Prod sessions up as one run that failed after its retries, to name fs-01 as the VM the scan "
    "checked, or to quote the sessions' messages."
)

GOOD = [
    (
        "Sessions created since 2026-10-06 09:00 (server time):\n\n| Started | Session | Type | Result |\n|---|---|---|---|"
        "\n| 10-06 12:00 | Agent-Laptops | AgentBackup | Warning |\n| 10-06 21:00 | NAS-Finance | BackupJob | Success |"
        "\n| 10-06 21:30 | S3-Docs | BackupJob | Success |\n| 10-06 22:00 | Daily-VMs | BackupJob | Success |\n| 10-06 "
        "22:41 | Reports-VM | BackupJob | Success |\n| 10-06 22:41 | Copy-to-DR | BackupCopyJob | Warning |\n| 10-06 "
        "23:20 | Scan Backup | SureBackup | Failed - malware was found in the scanned restore point, not a backup failure "
        "|\n| 10-07 00:00 | SQL-Prod | BackupJob | Failed (2 automatic retries at 00:31 and 00:46, both Failed) |\n| "
        "10-07 02:00 | SQL-Dev | BackupJob | Success |\n| 10-07 08:40 | SQL-Dev | BackupJob | Running, 45% (started "
        "manually) |"
    ),
    (
        "In the last 24 hours: successes - NAS-Finance, S3-Docs, Daily-VMs, Reports-VM and the 02:00 SQL-Dev run; "
        "warnings - Agent-Laptops and Copy-to-DR; one real failure - SQL-Prod (the 00:00 run plus two retries, all "
        "failed). The Scan Backup at 23:20 shows Failed because it detected malware. SQL-Dev has been running again since "
        "08:40 (45%)."
    ),
    (
        "12 sessions:\n- Daily-VMs 22:00 - Success\n- Reports-VM 22:41 - Success\n- Copy-to-DR 22:41 - Warning\n- "
        "NAS-Finance 21:00 - Success\n- S3-Docs 21:30 - Success\n- Agent-Laptops 12:00 - Warning\n- SQL-Prod 00:00 - "
        "Failed, then re-attempted twice (00:31, 00:46), still Failed\n- SQL-Dev 02:00 - Success; SQL-Dev 08:40 - "
        "running\n- Malware scan (Scan Backup) 23:20 - Failed = infection found"
    ),
]

BAD = {
    "retries": "Sessions: Daily-VMs, Reports-VM, NAS-Finance, S3-Docs and SQL-Dev succeeded; Copy-to-DR and "
    "Agent-Laptops warned; SQL-Prod failed at 00:00; the Scan Backup failed; SQL-Dev is running.",
    "job_copy_to_dr": "Sessions: Daily-VMs, Reports-VM, NAS-Finance, S3-Docs and SQL-Dev succeeded; Agent-Laptops "
    "warned; SQL-Prod failed with two retries; the Scan Backup failed.",
    "scan": "Sessions: Daily-VMs, Reports-VM, NAS-Finance, S3-Docs and SQL-Dev succeeded; Copy-to-DR and "
    "Agent-Laptops warned; SQL-Prod failed after two retries.",
}
"""Answers that each leave out one thing the listing must show."""


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G1-06",
        inputs=CaseInputs(
            question="Show me all sessions from the last 24 hours with their outcomes.",
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G1", "base_stand": "1.3"},
        evaluators=[
            # list_sessions is the answer; get_server_status (what "now" is) and a drill-down are reads the case
            # allows on top of it.
            ToolCorrectness(expected_tools=["list_sessions"], allow_extra=True),
            *tool_budget(3),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "running_session",
                f"The output shows the {_RUNNING.name} session started at {_RUNNING.creation_time:%H:%M} as still "
                "running. It does not give it a negative, zero or otherwise computed final duration; leaving the "
                "duration out or saying it has been running for about 20 minutes is fine.",
            ),
            _judge(
                "retries_as_one_run",
                "The output presents the three failed SQL-Prod sessions (00:00, 00:31, 00:46) as one run with its "
                "retries, not as three independent failures. If it counts the retries, it counts two: the 00:00 "
                "session is the original run, not a retry.",
            ),
            _judge(
                "scan_result_explained",
                f"The output presents the {_SCAN.name} session's Failed result as the scan finding malware (saying so, "
                "or reporting it as 'malware detected'/'infected'), not as a backup job that failed.",
            ),
            _judge(
                "no_config_backup_session",
                "The output does not list a configuration backup session in the last 24 hours: there was none.",
            ),
            _judge(
                "no_canceled_sessions",
                "The output does not claim that any session of the last 24 hours was canceled.",
            ),
            _judge(
                "window_respected",
                "The output does not list sessions created before 2026-10-06 09:00 (for example the Daily-VMs runs "
                "of 2026-10-05 or the canceled Reports-VM run of 2026-10-04) as sessions of the last 24 hours.",
            ),
        ],
    )
