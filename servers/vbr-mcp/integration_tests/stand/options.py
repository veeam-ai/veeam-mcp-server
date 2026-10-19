# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""General options (1.13): ``/generalOptions``. Email is configured, but its master switch is off, so nothing is sent."""

from stand.ids import SMTP_CREDENTIALS, at
from vbr_models.general_options import (
    AdvancedSmtpOptions,
    EmailSettings,
    GeneralOptions,
    Notifications,
    SiemIntegration,
    SyslogServer,
)

GENERAL_OPTIONS = GeneralOptions(
    notification_enabled=False,  # the master switch: off, so nothing is sent whatever the settings below say
    email_settings=EmailSettings(
        smtp_server_name="smtp.lab.local",
        advanced_smtp_options=AdvancedSmtpOptions(
            port=587, timeout_ms=100_000, ssl_enabled=True, auth_required=True, credentials_id=SMTP_CREDENTIALS
        ),
        from_="vbr-lab01@lab.local",
        to="backup-admins@lab.local",
        subject="[%JobResult%] %JobName% (%ObjectCount% machines) %Issues%",
        send_daily_reports_at=at(7, 22, 0),
        notify_on_success=False,
        notify_on_warning=True,
        notify_on_failure=True,
        notify_on_last_retry=True,
    ),
    notifications=Notifications(
        storage_space_threshold_enabled=True,
        storage_space_threshold=10,
        datastore_space_threshold_enabled=True,
        datastore_space_threshold=10,
        skip_vm_space_threshold_enabled=False,
        notify_on_support_expiration=True,
        notify_on_updates=True,
    ),
    siem_integration=SiemIntegration(
        snmp_events_enabled=False,
        syslog_events_enabled=True,
        syslog_server=SyslogServer(server_name="siem.lab.local", port=514, transport_protocol="Udp"),
    ),
)
"""``GET /api/v1/generalOptions``."""
