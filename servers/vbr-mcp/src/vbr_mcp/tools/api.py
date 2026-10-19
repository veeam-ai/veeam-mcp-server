# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""Generic read-only access to the VBR REST API."""

from __future__ import annotations

import re
from typing import Any

from fastmcp.exceptions import ToolError

from vbr_mcp.server import mcp, vbr_client
from vbr_mcp.tool_annotations import READ_ONLY

# `{name}` matches exactly one path segment.
_READ_ONLY_POST_PATHS = (
    "/api/v1/acl",
    "/api/v1/inventory",
    "/api/v1/inventory/{hostname}",
    "/api/v1/inventory/physical",
    "/api/v1/inventory/physical/all",
    "/api/v1/inventory/physical/{protectionGroupId}",
    "/api/v1/inventory/retrieveMachineDetails",
    "/api/v1/restorePoints/{id}/networkInfo",
)

# Literal segments that `/api/v1/inventory/{hostname}` must not swallow:
# `POST /api/v1/inventory/unstructuredDataServers` *adds* a server.
_RESERVED_INVENTORY_SEGMENTS = frozenset({"unstructuredDataServers", "entraId"})

_SEGMENT = re.compile(r"^[^/?#\\]+$")


def _validate_path(path: str) -> list[str]:
    if not path.startswith("/api/v1/"):
        raise ToolError(f"Path must start with /api/v1/, got {path!r}.")
    segments = path.removeprefix("/").split("/")
    if any(not _SEGMENT.match(s) or s in {".", ".."} for s in segments):
        raise ToolError(
            f"Invalid path {path!r}: pass a plain endpoint path (no '..', empty segments, '?' or '#'); "
            "put query parameters in `params`."
        )
    return segments


def _matches(segments: list[str], pattern: str) -> bool:
    pattern_segments = pattern.removeprefix("/").split("/")
    if len(segments) != len(pattern_segments):
        return False
    return all(p.startswith("{") or p == s for p, s in zip(pattern_segments, segments, strict=True))


def _is_read_only_post(path: str) -> bool:
    segments = _validate_path(path)
    if len(segments) == 4 and segments[2] == "inventory" and segments[3] in _RESERVED_INVENTORY_SEGMENTS:
        return False
    return any(_matches(segments, pattern) for pattern in _READ_ONLY_POST_PATHS)


@mcp.tool(annotations=READ_ONLY)
async def api_get(path: str, params: dict[str, Any] | None = None) -> Any:
    """Send any GET request to the VBR REST API, as described in the API reference.

    Use it for data no dedicated tool returns. `path` is the endpoint path with path
    variables filled in (e.g. `/api/v1/backupInfrastructure/managedServers/{id}`);
    `params` holds query parameters (filters, `skip`/`limit`, `orderColumn`/`orderAsc`).
    List endpoints are paged: the response carries `pagination.total`, so page
    with `skip`/`limit` when it exceeds what you received. Read-only.
    """
    _validate_path(path)
    return await vbr_client.get(path, params=params)


# Built from the allowlist, so the endpoints a caller is offered are the ones `_is_read_only_post` lets through.
_API_POST_QUERY_DESCRIPTION = (
    "Send a read-only POST query to the VBR REST API - an endpoint that takes its query in the request body.\n\n"
    "Only these endpoints are allowed (fill in each `{...}` path segment; `{hostname}` is a managed server's name):\n"
    + "\n".join(f"- `{path}`" for path in _READ_ONLY_POST_PATHS)
    + "\n\n`body` is the endpoint's request body as the API reference describes it. Any other POST is refused: "
    "writes are only available through the dedicated action tools; use `api_get` for GET endpoints."
)


@mcp.tool(annotations=READ_ONLY, description=_API_POST_QUERY_DESCRIPTION)
async def api_post_query(path: str, body: dict[str, Any] | None = None) -> Any:
    if not _is_read_only_post(path):
        raise ToolError(
            f"POST {path} is not an allowed read-only query endpoint. Writes are only available through "
            "the dedicated action tools; use `api_get` for GET endpoints."
        )
    return await vbr_client.post(path, json=body if body is not None else {}, read_only=True)
