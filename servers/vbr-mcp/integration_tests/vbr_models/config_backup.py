# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""``/api/v1/configBackup``."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from vbr_models import VbrDateTime, VbrModel


class ConfigBackupNotifications(VbrModel):
    """``ConfigBackupNotificationsModel``."""

    snmp_enabled: bool = Field(alias="SNMPEnabled")  # sic: the API's own casing


class ScheduleDaily(VbrModel):
    """``ScheduleDailyModel``."""

    is_enabled: bool
    local_time: str | None = None
    """``HH:mm``, in the server's time zone."""
    daily_kind: Literal["Everyday", "WeekDays", "SelectedDays"] | None = None


class ConfigBackupSchedule(VbrModel):
    """``ConfigBackupScheduleModel``."""

    is_enabled: bool
    daily: ScheduleDaily | None = None


class ConfigBackupLastSuccessful(VbrModel):
    """``ConfigBackupLastSuccessfulModel``."""

    last_successful_time: VbrDateTime | None = None
    session_id: UUID | None = None


class ConfigBackupEncryption(VbrModel):
    """``ConfigBackupEncryptionModel``."""

    is_enabled: bool
    password_id: UUID | None = None


class ConfigBackup(VbrModel):
    """``ConfigBackupModel``, ``GET /api/v1/configBackup``."""

    is_enabled: bool
    backup_repository_id: UUID
    restore_points_to_keep: int
    notifications: ConfigBackupNotifications
    schedule: ConfigBackupSchedule
    last_successful_backup: ConfigBackupLastSuccessful
    encryption: ConfigBackupEncryption
