# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

from typing import Literal

from .settings import vbr_settings  # noqa: F401  (scanned by update_env_example.py)

TRANSPORT: Literal["stdio", "http"] = "stdio"
HTTP_HOST = "127.0.0.1"
HTTP_PORT = 8000


def main() -> None:
    from vbr_mcp.server import mcp
    from vbr_mcp.tools import (  # noqa: F401
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

    if TRANSPORT == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport=TRANSPORT, host=HTTP_HOST, port=HTTP_PORT)
