# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""Shared MCP tool annotations.

These are the hints an MCP client uses to decide whether to run a tool silently or
ask the user first.

`openWorldHint` is false throughout: every tool talks to the single VBR server named
by `VBR_BASE_URL`, never to an open-ended set of external systems.

Classification rules:

* READ_ONLY   - issues no state-changing call. A few of these are `POST` requests
                (`browse_inventory`, `create_license_report`, `api_post_query`) because
                the VBR API takes a request body for them; they still only read -
                `api_post_query` refuses any endpoint outside its read-only allowlist.
* WRITE       - changes state additively or reversibly: starting a job, triggering a
                rescan, toggling a proxy back on.
* DESTRUCTIVE - may interrupt protection, overwrite production data, or tear down a
                running workload. Every restore tool lives here: restores can overwrite
                an existing VM, file share, or bucket, and instant recovery publishes a
                VM straight into production vSphere.
"""

from typing import Any

READ_ONLY: dict[str, Any] = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}

WRITE: dict[str, Any] = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "openWorldHint": False,
}

DESTRUCTIVE: dict[str, Any] = {
    "readOnlyHint": False,
    "destructiveHint": True,
    "idempotentHint": False,
    "openWorldHint": False,
}
