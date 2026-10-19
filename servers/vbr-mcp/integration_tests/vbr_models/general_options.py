# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""``/api/v1/generalOptions``.

Several keys keep VBR's raw casing (``SSLEnabled``, ``SNMPEventsEnabled``, ``SyslogServer``), which camelCase
would not produce, so those fields name their alias.
"""

from typing import Literal
from uuid import UUID

from pydantic import Field

from vbr_models import VbrDateTime, VbrModel


class AdvancedSmtpOptions(VbrModel):
    """``AdvancedSmtpOptionsModel``."""

    port: int
    timeout_ms: int
    ssl_enabled: bool = Field(alias="SSLEnabled")
    auth_required: bool
    credentials_id: UUID | None = None


class EmailSettings(VbrModel):
    """``GeneralOptionsEmailNotificationsModel``."""

    smtp_server_name: str
    advanced_smtp_options: AdvancedSmtpOptions
    from_: str = Field(alias="from")
    to: str
    subject: str
    send_daily_reports_at: VbrDateTime
    notify_on_success: bool
    notify_on_warning: bool
    notify_on_failure: bool
    notify_on_last_retry: bool


class Notifications(VbrModel):
    """``GeneralOptionsNotificationsModel``."""

    storage_space_threshold_enabled: bool
    storage_space_threshold: int | None = None
    datastore_space_threshold_enabled: bool
    datastore_space_threshold: int | None = None
    skip_vm_space_threshold_enabled: bool = Field(alias="skipVMSpaceThresholdEnabled")
    notify_on_support_expiration: bool
    notify_on_updates: bool


class SyslogServer(VbrModel):
    """``GeneralOptionsSyslogServerModel``."""

    server_name: str
    port: int | None = None
    transport_protocol: Literal["Udp", "Tcp", "Tls"] | None = None


class SiemIntegration(VbrModel):
    """``GeneralOptionsSiemIntegrationModel``."""

    snmp_events_enabled: bool = Field(alias="SNMPEventsEnabled")
    syslog_events_enabled: bool = Field(alias="SyslogEventsEnabled")
    syslog_server: SyslogServer | None = Field(default=None, alias="SyslogServer")


class GeneralOptions(VbrModel):
    """``GeneralOptionsModel``, ``GET /api/v1/generalOptions``."""

    notification_enabled: bool
    email_settings: EmailSettings | None = None
    notifications: Notifications
    siem_integration: SiemIntegration
