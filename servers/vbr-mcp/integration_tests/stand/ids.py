# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""The base stand's ids and clock (test plan 0.4): mnemonic UUIDs, T0 and the server's time zone."""

from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

SERVER_TZ = timezone(timedelta(hours=2))
"""Europe/Prague in summer (CEST). Every date of the stand from April to October is in it."""

WINTER_TZ = timezone(timedelta(hours=1))
"""Europe/Prague in winter (CET), for the few dates of the stand outside summer time."""

ZERO = UUID(int=0)
"""What VBR writes where there is no id: the ``jobId`` of a session no job runs, of an orphaned backup."""

GB = 2**30
"""VBR counts sizes in bytes and GB in binary."""


def mnemonic(prefix: str, number: int) -> UUID:
    """The plan's mnemonic ids: the prefix names the object type, the last digits its number (``J02`` = 10000000-...-02)."""
    return UUID(f"{prefix}-0000-0000-0000-{number:012d}")


def at(day: int, hour: int, minute: int, second: int = 0, *, month: int = 10, year: int = 2026) -> datetime:
    """A moment on the backup server's clock."""
    return datetime(year, month, day, hour, minute, second, tzinfo=SERVER_TZ)


def utc(month: int, day: int, hour: int, minute: int, second: int = 0, *, year: int = 2026) -> datetime:
    """A moment in UTC, as the malware events carry it."""
    return datetime(year, month, day, hour, minute, second, tzinfo=UTC)


T0 = at(7, 9, 0)
"""The moment the cases run at, as the server's clock tells it: Wednesday 2026-10-07 09:00 (07:00 UTC)."""

# ---- Jobs (1.2)
J01, J02, J03, J04, J05, J06, J07, J08, J09, J10 = (mnemonic("10000000", n) for n in range(1, 11))

# ---- Repositories (1.4) and the scale-out repository (1.5)
R01, R02, R03, R04, R05, R06, R07, R08 = (mnemonic("20000000", n) for n in range(1, 9))
S01 = mnemonic("21000000", 1)

# ---- Proxies, managed servers, WAN accelerators (1.6)
P01, P02, P03 = (mnemonic("30000000", n) for n in range(1, 4))
M01, M02, M03, M04, M05, M06, M07, M08, M09, M10, M11, M12, M13 = (mnemonic("31000000", n) for n in range(1, 14))
W01, W02 = mnemonic("32000000", 1), mnemonic("32000000", 2)

# ---- Sessions (1.3), those the cases name. S-ID09 is not used: it was a failed configuration backup of 10-06, which VBR
# never starts.
S_ID03, S_ID04, S_ID05, S_ID06, S_ID07, S_ID08 = (mnemonic("40000000", n) for n in range(3, 9))
S_ID10, S_ID13, S_ID14, S_ID15, S_ID16 = (mnemonic("40000000", n) for n in (10, 13, 14, 15, 16))
S_CFG_OK = mnemonic("40000000", 120)
"""The last configuration backup VBR ran, 2026-09-27 10:00: the ``lastSuccessfulBackup`` of ``/configBackup``."""
FIRST_G3_SESSION = 20
"""Sessions a G3 case's action creates are numbered from S-ID20 (test plan 0.4)."""
S_ID20, S_ID21, S_ID22 = (mnemonic("40000000", n) for n in range(FIRST_G3_SESSION, FIRST_G3_SESSION + 3))
"""The sessions of a G3 case's actions, in the order the actions start them."""

# ---- Task sessions of the key sessions (1.3); every other session's tasks are numbered from 1000
T01, T02, T03, T04, T05, T06, T07, T08, T09, T10, T11, T12 = (mnemonic("41000000", n) for n in range(1, 13))

# ---- Backups (1.9). The protected objects (1.8), O01-O17, are numbered from 50000000-... by ``stand.protected``.
B01, B02, B03, B04, B05, B06, B07, B08, B09, B10, B11 = (mnemonic("52000000", n) for n in range(1, 12))

# ---- Malware events (1.10)
EV01, EV02, EV03, EV04, EV05, EV06, EV07, EV08, EV09 = (mnemonic("60000000", n) for n in range(1, 10))

# ---- License (1.11): instance workloads I01-I12, capacity workloads C01-C02
I01, I02, I03, I04, I05, I06, I07, I08, I09, I10, I11, I12 = (mnemonic("70000000", n) for n in range(1, 13))
C01, C02 = mnemonic("71000000", 1), mnemonic("71000000", 2)

# ---- Protection groups (1.14) and NAS sources (1.15)
PG01, PG02 = mnemonic("80000000", 1), mnemonic("80000000", 2)
N01, N02, N03, N04 = (mnemonic("90000000", n) for n in range(1, 5))

# ---- Secrets VBR keeps: the job encryption password, and the credentials records
ENCRYPTION_PASSWORD = mnemonic("c0000000", 1)
"""The Password Manager entry the encrypted jobs use; created 2026-09-27, when job encryption was turned on."""
AGENT_CREDENTIALS = mnemonic("c1000000", 1)
"""LAB\\svc-agent, which the protection groups deploy Veeam Agents with."""
SHARE_CREDENTIALS, AWS_CREDENTIALS = mnemonic("c2000000", 1), mnemonic("c2000000", 2)
"""LAB\\svc-nas, which fs01's shares are read with; the Lab AWS access key."""
SMTP_CREDENTIALS = UUID("a1000000-0000-0000-0000-000000000001")
