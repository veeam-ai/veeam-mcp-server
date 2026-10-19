# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """LLM and eval settings read from the environment or from ``.env`` next to this module (see ``.env.example``)."""

    model_config = SettingsConfigDict(env_file=Path(__file__).parent / ".env", env_ignore_empty=True)

    AZURE_ENDPOINT: str
    AZURE_DEPLOYMENT: str
    AZURE_API_VERSION: str
    AZURE_TENANT_ID: str
    AZURE_CLIENT_ID: str
    AZURE_CLIENT_SECRET: str

    # Runs per case: LLM answers vary, so one green run proves little.
    EVAL_REPEAT: int = 3
    # Parallel runs. A whole group at once exceeds the deployment's token rate limit.
    EVAL_MAX_CONCURRENCY: int | None = 4
    # Retries of a rate-limited (429) or failed LLM request, with the OpenAI client's exponential backoff.
    LLM_MAX_RETRIES: int = 8
    # The deployment the LLM judges run on. Unset, the agent's own: a judge from another model family is a sterner one.
    JUDGE_DEPLOYMENT: str | None = None
    # The share of soft assertions (facts, judges, trajectory) the run must pass; any hard one failing fails it anyway.
    MIN_SOFT_PASS_RATE: float = 0.9
