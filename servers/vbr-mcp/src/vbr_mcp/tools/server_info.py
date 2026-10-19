# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

from typing import Any

from vbr_mcp.server import mcp, vbr_client
from vbr_mcp.tool_annotations import READ_ONLY


@mcp.tool(annotations=READ_ONLY)
async def get_server_status() -> dict[str, Any]:
    """Return the VBR server's version/build, DB engine/version, registration status/expiry, and server time/timezone.

    Use for "what VBR version/build are we on", "what database", "is the
    server registered / when does registration expire", "what time/timezone
    does the server think it is". `databaseVendor` names the configuration
    database engine; `sqlServerVersion` is that engine's version string (for
    PostgreSQL, e.g. "PostgreSQL 15.10, compiled by ..."), and
    `sqlServerEdition` is only filled for Microsoft SQL Server. Registration
    `expirationDate` may be absent.
    """
    info = await vbr_client.get("/api/v1/serverInfo")
    time = await vbr_client.get("/api/v1/serverTime")
    return {**info, **time}
