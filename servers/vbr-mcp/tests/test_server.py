# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

from fastmcp import Client


async def test_server_tells_clients_to_confirm_destructive_actions(mcp_client: Client):
    instructions = mcp_client.instructions or ""

    assert "Destructive tools" in instructions
    assert "ask for an explicit yes" in instructions
    assert "is not that yes" in instructions  # a plain "stop X" does not count as the confirmation
