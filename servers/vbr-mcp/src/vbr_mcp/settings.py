# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(os.getenv("ENV_FILE_OVERRIDE") or _PROJECT_ROOT / ".env")


class VbrSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VBR_")

    base_url: str = Field(
        default="https://localhost:9419",
        description="Base URL of the VBR REST API server, e.g. https://vbr.example.com:9419",
    )
    username: str = Field(default="", description="VBR REST API username used for the password grant.")
    password: str = Field(default="", description="VBR REST API password used for the password grant.")
    verify_tls: bool = Field(default=True, description="Verify the VBR server's TLS certificate.")
    api_version: str = Field(default="1.3-rev2", description="VBR REST API version sent via the x-api-version header.")
    request_timeout_sec: float = Field(default=30.0, description="Per-request timeout for calls to the VBR server.")


class McpAuthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MCP_")

    enabled: bool = Field(default=True, description="Require a bearer token from MCP clients when true.")
    tokens: dict[str, str] = Field(
        default={},
        description='Accepted bearer tokens, mapped to a client name, e.g. {"<token>": "my-client"}.',
    )


vbr_settings = VbrSettings()
mcp_auth_settings = McpAuthSettings()
