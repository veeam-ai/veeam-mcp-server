# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G1-01: VBR version, database and server time."""

import re
from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import CaseInputs, judge, tool_budget
from cases.patterns import clock, day
from evaluators import FactsPresent, ToolsNotCalled
from stand import environment
from stand.server import SERVER_INFO, SERVER_TIME

# ---- What VBR serves: the base stand. Its database is PostgreSQL, whose version VBR 13 reports in
# sqlServerVersion (swagger ServerInfoModelExample); its Windows time zone name carries the standard offset, +01:00,
# while the clock is on summer time, +02:00.

ENVIRONMENT = environment()

# ---- What a correct answer says, derived from the stand.

_NOW = SERVER_TIME.server_time
_OFFSET = _NOW.utcoffset()
assert _OFFSET is not None
_OFFSET_HOURS = int(_OFFSET.total_seconds() // 3600)  # 2: CEST
_REGISTERED_UNTIL = SERVER_INFO.veeam_registration.expiration_date
_POSTGRES_VERSION = re.search(r"PostgreSQL (\d+\.\d+)", SERVER_INFO.sql_server_version)
assert _POSTGRES_VERSION is not None
POSTGRES_VERSION = _POSTGRES_VERSION.group(1)  # 15.10

EXPECTED = (
    f"Backup server {SERVER_INFO.name} ({SERVER_INFO.platform}) runs Veeam Backup & Replication build "
    f"{SERVER_INFO.build_version} with no patches. The configuration database is PostgreSQL, version "
    f"{POSTGRES_VERSION} ({SERVER_INFO.sql_server_version}, as VBR reports it). The server time is "
    f"{_NOW:%Y-%m-%d %H:%M}, UTC+{_OFFSET_HOURS:02d}:00 (summer time, CEST), time zone {SERVER_TIME.iana_time_zone_id}; "
    f"VBR's Windows time zone name, {SERVER_TIME.time_zone}, carries the standard offset, not the current one."
)
"""Ground truth for the judges."""

FACTS = {
    "build": re.escape(SERVER_INFO.build_version),
    "database": r"postgre",  # PostgreSQL, PostgreSql, Postgres
    "date": day(_NOW),
    "time": clock(_NOW),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

_ALLOWED = (
    f"It is acceptable, and not a violation, to give the server name {SERVER_INFO.name} and platform "
    f"{SERVER_INFO.platform}, to quote the PostgreSQL version string as VBR reports it, to mention that the server is "
    f"registered until {_REGISTERED_UNTIL:%Y-%m-%d} or that no patches are installed, to quote VBR's Windows time "
    "zone name, or to advise checking the build against the release notes."
)

GOOD = [
    (
        "You're running Veeam Backup & Replication 13.1, build 13.1.0.344 (no patches), on vbr-lab01. The configuration "
        "database is PostgreSQL 15.10. The backup server's clock says 2026-10-07 09:00 (UTC+02:00, Europe/Prague)."
    ),
    (
        "| Item | Value |\n|---|---|\n| Build | 13.1.0.344 |\n| Database | PostgreSql - PostgreSQL 15.10, compiled by Visual "
        "C++ build 1940, 64-bit |\n| Server time | Wednesday, 7 Oct 2026, 9:00 AM CEST |"
    ),
    (
        "Build 13.1.0.344. The DB is Postgres. It's 09:00 on October 7th on the server (Prague time, +02:00 right now; "
        "the Windows zone name says UTC+01:00 because that is the standard offset)."
    ),
]

BAD = {
    "build": "You are on Veeam Backup & Replication 13.1 build 13.1.0.300; the database is PostgreSQL and it is "
    "09:00 CEST on 2026-10-07.",
    "database": "Build 13.1.0.344 with a Microsoft SQL Server Express database; it is 09:00 CEST on 2026-10-07.",
    "date": "Build 13.1.0.344 on PostgreSQL; on the server it is 09:00 CEST on Oct 6.",
    "time": "Build 13.1.0.344 on PostgreSQL; on the server it is 07:00 on 2026-10-07 (Europe/Prague).",
}
"""Answers that each miss one fact."""


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G1-01",
        inputs=CaseInputs(
            question="What VBR version and build are we running, what database does it use, and what time is it on the backup server right now?",
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G1", "base_stand": "1.1"},
        evaluators=[
            ToolCorrectness(expected_tools=["get_server_status"], allow_extra=True),
            *tool_budget(1),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "no_sql_server",
                "The output does not say the configuration database is Microsoft SQL Server, and does not give it "
                "a SQL Server edition. Quoting VBR's sqlServerVersion field, which holds the PostgreSQL version, "
                "is fine.",
            ),
            _judge(
                "postgres_version_from_api",
                f"If the output gives a version of the database, it is PostgreSQL {POSTGRES_VERSION} as VBR reports "
                "it. The output does not state any other PostgreSQL version, and does not claim that VBR does not "
                "report the database version. Leaving the version out is fine.",
            ),
            _judge(
                "server_clock",
                "The current time the output reports is the backup server time from the expected output, "
                "not the time of some other clock such as the assistant's or the user's. Do not use your own "
                "notion of the current date or time; compare only with the expected output.",
            ),
            _judge(
                "current_offset",
                f"If the output gives the server's current UTC offset, it is +{_OFFSET_HOURS:02d}:00 (summer "
                "time). It does not present +01:00, the standard offset in VBR's Windows time zone name, as the "
                "current offset. Quoting that time zone name as VBR reports it is fine.",
            ),
        ],
    )
