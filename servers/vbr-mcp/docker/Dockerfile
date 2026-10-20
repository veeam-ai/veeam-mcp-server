# BUILD CONTEXT MUST BE THE PROJECT ROOT (servers/vbr-mcp)

ARG PYTHON_VERSION=3.13

# Slim rather than the full -bookworm image: every dependency here is pure Python or ships a
# manylinux wheel, so the 800MB of build toolchain and git/mercurial in the full image is dead
# weight. Revisit if a dependency ever needs to compile from source.
ARG BASE_IMAGE="python:${PYTHON_VERSION}-slim-bookworm"

# Step 1. Build
FROM ${BASE_IMAGE} AS builder

# Pinned rather than :latest so the same commit always builds the same image.
COPY --from=ghcr.io/astral-sh/uv:0.12.18 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Dependencies first, so the layer survives every source-only change.
# README.md comes along because pyproject.toml references it as the project readme.
COPY pyproject.toml uv.lock README.md LICENSE ./

RUN --mount=type=cache,target=/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY src ./src/
RUN uv sync --frozen --no-dev --no-editable

# Step 2. Deploy
FROM ${BASE_IMAGE} AS runtime

LABEL org.opencontainers.image.title="vbr-mcp" \
      org.opencontainers.image.description="MCP server exposing the Veeam Backup & Replication REST API to MCP clients" \
      org.opencontainers.image.source="https://github.com/veeam-ai/veeam-mcp-server" \
      org.opencontainers.image.licenses="MIT"

RUN adduser --disabled-password --gecos '' -u 10001 vbrmcp

WORKDIR /app

# The server talks MCP over stdio, the same as a local run: the MCP client starts the container
# itself with `docker run -i`. VBR_* credentials are injected at runtime, never baked into a layer.
ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

# --no-editable installed the package into the venv, so the venv is the whole payload.
COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}

USER 10001

CMD ["vbr-mcp"]
