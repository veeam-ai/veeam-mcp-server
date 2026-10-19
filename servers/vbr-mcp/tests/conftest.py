# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

import pytest
from fastmcp import Client, FastMCP

from vbr_mcp.server import mcp
from vbr_mcp.tools import (  # noqa: F401  (import side effect: registers every tool on `mcp`)
    api,
    backups,
    config_backup,
    general_options,
    infrastructure,
    inventory,
    jobs,
    license,
    malware_detection,
    protected_objects,
    protection_groups,
    restore,
    server_info,
    sessions,
)
from vbr_mcp.vbr_client import VbrClient


@pytest.fixture(name="vbr_client")
def vbr_client_fixture() -> VbrClient:
    return VbrClient(base_url="https://vbr.example.com:9419", username="admin", password="secret")


@pytest.fixture(autouse=True)
def _reset_shared_vbr_client_auth():
    """Clear the shared client's cached token before each test.

    `vbr_mcp.server.vbr_client` is a process-wide singleton (shared by every tool module), so without this each
    test's own `/api/oauth2/token` mock would go unused once an earlier test has already authenticated.
    """
    from vbr_mcp.server import vbr_client as shared_client

    shared_client._access_token = None
    shared_client._refresh_token = None


@pytest.fixture(name="mcp_app")
def mcp_app_fixture() -> FastMCP:
    return mcp


@pytest.fixture(name="mcp_client")
async def mcp_client_fixture(mcp_app: FastMCP):
    async with Client(mcp_app) as client:
        yield client


def tool_data(result):
    """A tool call's actual return value.

    Works around a FastMCP client quirk where `CallToolResult.data` fails to
    reconstruct a bare `list[dict]` result (it wraps non-object returns as
    `{"result": [...]}` server-side; the client-side rebuild of that wrapper
    can come back as opaque `Root()` placeholders instead of plain dicts) - so
    read the already-correct `structured_content` and unwrap it ourselves.
    """
    content = result.structured_content
    if isinstance(content, dict) and content.keys() == {"result"}:
        return content["result"]
    return content
