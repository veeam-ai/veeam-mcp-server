# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

from importlib.metadata import version

from fastmcp import FastMCP

from vbr_mcp.auth import StaticBearerVerifier
from vbr_mcp.settings import mcp_auth_settings, vbr_settings
from vbr_mcp.vbr_client import VbrClient

vbr_client = VbrClient(
    base_url=vbr_settings.base_url,
    username=vbr_settings.username,
    password=vbr_settings.password,
    verify_tls=vbr_settings.verify_tls,
    api_version=vbr_settings.api_version,
    timeout=vbr_settings.request_timeout_sec,
)

INSTRUCTIONS = """\
Tools for one Veeam Backup & Replication (VBR) server, over its REST API.

Read tools change nothing: call them freely, also to check the state after an action.

Write tools (start, retry or enable a job, enable or disable a proxy, rescans, malware scans, configuration backup)
change VBR. Run one when the user explicitly asks for it. If it has a serious side effect, such as disabling the last
proxy that can take tasks or writing a full backup into an almost full repository, say so first; when it would stop
protection, ask before acting.

Destructive tools (stop or disable a job, every restore, Instant Recovery start, migrate and unmount, SOBR extent
maintenance and sealed mode, component updates, license revoke) can interrupt protection or overwrite data. Before
calling one, find the target with read tools, tell the user the target (name and key attributes) and what the action
will do to it, and ask for an explicit yes; call the tool only after that yes. A request that names the action and the
target ("stop SQL-Dev", "restore web-01", "put Ext-02 into maintenance") is not that yes: asking is the point. Skip
the question only when the user's own message already states the consequence and still asks for the action ("stop
it now, I know the running VM gets no restore point"). Before an operation on several objects, always list them and
get the user's confirmation for that list.

A question about an action ("what happens if...", "how do I...") is not a request to run it. If the object is already
in the requested state, say so instead of calling the tool. Actions are asynchronous: report them as started, not
done, and confirm with read tools. Take ids from tool results or from the user, never guess or construct one, and
use each only for what it identifies. When VBR refuses a call, pass on its reason and do not repeat the same call
unchanged. Read "now", "today" and "last night" off the backup server's clock (get_server_status).
"""
"""Sent to MCP clients at initialization: how to use these tools safely, whatever client runs them."""

mcp = FastMCP(
    "VBR",
    version=version("vbr-mcp"),
    instructions=INSTRUCTIONS,
    auth=StaticBearerVerifier(tokens=mcp_auth_settings.tokens) if mcp_auth_settings.enabled else None,
)
