# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""Configuration backup (1.12): ``/configBackup``.

Enabled, daily at 10:00, to Repo-Main, encryption off. It last ran on 2026-09-27 (S-CFG-OK, with the Warning every
unencrypted run gets): that day job encryption put a password into the Password Manager, and VBR has not started a
configuration backup since - it will not while its encryption is off (User Guide v13, config_backup_encrypted). The
only sign is that no run is newer: there are no failed sessions to see, and starting one by hand is refused (a case
that starts one mocks ``POST /api/v1/configBackup/backup``; ``REFUSED`` is VBR's reason).
"""

from stand.ids import R01, S_CFG_OK, at
from vbr_models.config_backup import (
    ConfigBackup,
    ConfigBackupEncryption,
    ConfigBackupLastSuccessful,
    ConfigBackupNotifications,
    ConfigBackupSchedule,
    ScheduleDaily,
)

LAST_SUCCESS = at(27, 10, 3, 41, month=9)

CONFIG_BACKUP = ConfigBackup(
    is_enabled=True,
    backup_repository_id=R01,
    restore_points_to_keep=10,
    notifications=ConfigBackupNotifications(snmp_enabled=False),
    schedule=ConfigBackupSchedule(
        is_enabled=True, daily=ScheduleDaily(is_enabled=True, local_time="10:00", daily_kind="Everyday")
    ),
    last_successful_backup=ConfigBackupLastSuccessful(last_successful_time=LAST_SUCCESS, session_id=S_CFG_OK),
    encryption=ConfigBackupEncryption(is_enabled=False),
)
"""``GET /api/v1/configBackup``."""

REFUSED = "Configuration backup encryption must be enabled because product configuration contains encryption keys."
"""What VBR says to a configuration backup started while its encryption is off and the Password Manager holds a
password (as the console words it, forum t24954)."""
