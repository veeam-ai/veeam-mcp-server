# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

import fastmcp
import pytest

import vbr_mcp
from vbr_mcp.server import mcp


def test_server_runs_over_stdio_regardless_of_fastmcp_transport_setting(monkeypatch: pytest.MonkeyPatch):
    # FastMCP falls back on its own FASTMCP_TRANSPORT setting for a transport left out of run().
    monkeypatch.setattr(fastmcp.settings, "transport", "http")
    calls = []
    monkeypatch.setattr(mcp, "run", lambda *args, **kwargs: calls.append((args, kwargs)))

    vbr_mcp.main()

    assert calls == [((), {"transport": "stdio"})]
