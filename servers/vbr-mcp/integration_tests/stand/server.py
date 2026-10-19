# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""The backup server (1.1): ``/serverInfo`` and ``/serverTime``."""

from datetime import UTC, datetime

from stand.ids import M01, T0
from vbr_models.server import ServerInfo, ServerTime, VeeamRegistration

SERVER_INFO = ServerInfo(
    vbr_id=M01,
    name="vbr-lab01",
    build_version="13.1.0.344",
    patches=[],
    database_vendor="PostgreSql",
    sql_server_edition="",
    # VBR 13 reports the PostgreSQL version here (swagger ServerInfoModelExample: "PostgreSQL 17.5 on x86_64-pc-linux-
    # gnu, ..."); this is the engine a Windows install of 13.1 bundles.
    sql_server_version="PostgreSQL 15.10, compiled by Visual C++ build 1940, 64-bit",
    database_schema_version="4231",
    database_content_version="1214",
    veeam_registration=VeeamRegistration(
        is_registered=True,
        expiration_date=datetime(2027, 3, 31, tzinfo=UTC),
        thumprint="8F2A6C1D9B3E47A0C5D2E8F1B4A7C3D6E9F0A1B2",
    ),
    platform="Windows",
)

SERVER_TIME = ServerTime(
    server_time=T0,
    time_zone="(UTC+01:00) Belgrade, Bratislava, Budapest, Ljubljana, Prague",  # the Windows zone: its standard offset
    iana_time_zone_id="Europe/Prague",
)
