# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

from typing import Any

from vbr_mcp.server import mcp, vbr_client
from vbr_mcp.tool_annotations import READ_ONLY


@mcp.tool(annotations=READ_ONLY)
async def get_general_options() -> dict[str, Any]:
    """Return VBR's global options: email settings, disk-space/support/update notification thresholds, SIEM forwarding.

    Fields live under nested sub-objects (`emailSettings`, `notifications`,
    `siemIntegration`) with raw casing (`SSLEnabled`, `SNMPEventsEnabled`,
    `SyslogEventsEnabled`) - read each null-safely, a never-configured section
    is simply absent. Email is only actually usable when the master toggle
    (`notificationEnabled`) is on, `from`/`to` and (for a plain SMTP server)
    `smtpServerName` are set, and any SMTP auth has stored credentials -
    Gmail/MS365 legitimately leave `smtpServerName` empty.
    """
    return await vbr_client.get("/api/v1/generalOptions")
