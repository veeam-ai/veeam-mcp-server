# Veeam Intelligence MCP Server

Unlocking Veeam Intelligence at the Operational Edge

The Veeam Intelligence MCP Server extends the power of Veeam Intelligence beyond native Veeam consoles, enabling trusted operational signals to be securely delivered where enterprise operations happen, at the edge and in real-time workflows.

By exposing Veeam Intelligence through the Model Context Protocol (MCP), organizations can merge Veeam's protection, recovery, malware, and compliance signals with data from ITSM, storage, cloud, security, and monitoring platforms in a unified operational workflow.

This project provides a Veeam Intelligence MCP server that integrates with any MCP-compatible client, such as Claude Desktop, Visual Studio Code, and others, to enhance monitoring and management for Veeam Backup & Replication, Veeam ONE, and Veeam Service Provider Console (VSPC).

## Features

Veeam Intelligence MCP Server delivers cross-product, operational intelligence with these core capabilities:

| Category | Capabilities |
|---|---|
| **Platform & Version Intelligence** | - Retrieve Veeam ONE, Veeam Backup & Replication, and VSPC versions<br>- Detect patch/build drift<br>- Identify outdated components |
| **Environment Health** | - Triggered alarms with filtering and ranking<br>- Permanent notifications and active alarms<br>- Severity, object, and repeat analysis |
| **Threat & Malware Visibility** | - Threat Center overview and widgets<br>- Malware event listing and severity rollups<br>- Detection source and false positive tracking |
| **Backup Server Governance** | - Backup server inventory and versions<br>- Configuration backup enabled and encrypted status<br>- Best practices and security posture per server |
| **License & Consumption Intelligence** | - License status, edition, and expiration<br>- Instance, socket, and NAS capacity consumption<br>- Top consumers and headroom analysis |
| **Protected Workload Coverage** | - VM, agent, application, NAS, and object protection status<br>- Last protected time and job mapping<br>- Unprotected workload detection |
| **Job & Policy Operations** | - Job and policy status across all job types<br>- Failure trends, durations, and data movement<br>- Performance outliers and bottlenecks |
| **Live Job State & Triage** | - Running, waiting, and chained jobs<br>- Bottleneck and progress analysis<br>- Stalled job detection heuristics |
| **Session & History Analysis** | - Session timelines and outcomes<br>- Top failure reasons and noisy jobs<br>- Success rate and SLA validation |
| **Restore Point & RPO Coverage** | - Restore point counts per object<br>- RPO age and drift detection<br>- Restore capability mapping |
| **Repository Health & Capacity** | - Repository inventory and online state<br>- Capacity, utilization, and throttling<br>- Fast clone and vPower NFS readiness |
| **Proxy & Data Mover Capacity** | - Proxy inventory and live state<br>- Transport mode and concurrency<br>- Encryption and fallback risks |
| **WAN Acceleration** | - WAN accelerator inventory<br>- Stream capacity and cache sizing<br>- High bandwidth mode coverage |
| **Unstructured Data Protection** | - NAS and file server inventory<br>- Processing mode and proxy usage<br>- Cache and IO control posture |
| **Agent & Protection Group Health** | - Protection group policies and schedules<br>- Agent, driver, and plugin coverage<br>- Offline and stale endpoint detection |
| **Cloud & SaaS Workloads** | - Public cloud policy and workload status<br>- Platform-specific signals and failures<br>- VB365 protected object inventory |
| **Service Provider Operations (VSPC)** | - Companies and resellers inventory<br>- Managed server and agent visibility<br>- Support case tracking |
| **Operational Readiness & Notifications** | - Global email and SIEM settings<br>- Storage and capacity thresholds<br>- Misconfiguration detection |

## Why MCP for Veeam Intelligence?

- Real-time, cross-system insight for operators and AI agents.
- Single conversational interface for daily operations, planned changes, and incident response.
- Secure, governed access. Product actions are available only when the Veeam Backup & Replication administrator enables the `AdvancedWithActions` chatbot mode (VBR 13.1+), and every state-changing call requires explicit user confirmation, see [Actions](#actions-vbr-131-and-later).
- Full customer control over deployment, data exposure, and integration with AI clients, including local and self-hosted LLMs.

## Prerequisites

- Docker or Node.js 24 installed on your system
- One supported Veeam product installed with an active, non-Community license:
  - Veeam Backup & Replication (`vbr`)
  - Veeam ONE (`vone`)
  - Veeam Service Provider Console (`vspc`)

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/veeam-ai/veeam-mcp-server
cd veeam-mcp-server/servers/vi-mcp
```

### 2. Gather credentials and connection details

Collect the following credentials and connection details. These values are passed to the MCP server as environment variables.

- `PRODUCT_NAME`: The name of the Veeam product (`vbr | vone | vspc`)
- `WEB_URL`: The base URL of your Veeam server web UI.
  - Veeam Backup & Replication: `https://vbr-srv.local/` (default port 443)
  - Veeam ONE: `https://veeamone-srv.local:1239/`
  - Veeam Service Provider Console: `https://vspc-srv.local:1280/`
- `ADMIN_USERNAME`: The Veeam product administrator username, for example, `.\administrator`
- `ADMIN_PASSWORD`: The administrator password
- `ACCEPT_SELF_SIGNED_CERT`: Set to `true` if the Veeam product uses a self-signed SSL certificate, for example, `ACCEPT_SELF_SIGNED_CERT=true`
- `ACTION_CONFIRMATION_TIMEOUT_SEC` (optional, default `1500`): How long a proposed action waits for the user's decision before it is declined automatically.
- `CHAT_TURN_TIMEOUT_SEC` (optional, default `3600`): Upper bound for a single Veeam Intelligence answer, including confirmation waits.

Paste these values directly into the MCP client, such as Visual Studio Code or Claude Desktop, so they are passed to the MCP process as environment variables.

### Option 1: Run using Docker

#### 1. Build the Docker image

Before using the Veeam Intelligence MCP server, build the Docker image. Run these commands from the `servers/vi-mcp` directory:

```bash
# Option 1: Using make
make build

# Option 2: Using Docker directly
docker build -t veeam-intelligence-mcp-server .
```

#### 2. Set up your MCP client

Set up your MCP client to start the MCP server using `stdio` transport.

```bash
docker run -i --rm \
  -e PRODUCT_NAME=vone \
  -e WEB_URL=https://vone-server.local:1239/ \
  -e ADMIN_USERNAME=.\\administrator \
  -e ADMIN_PASSWORD=password \
  -e ACCEPT_SELF_SIGNED_CERT=true \
  veeam-intelligence-mcp-server
```

### Option 2: Using npm

Set up your MCP client to start the MCP server using `stdio` transport.

#### Store secrets in a `.env` file

1. In the `servers/vi-mcp` directory, copy `.env.example` to `.env` and populate the values.
2. Configure your MCP client to run the server as follows:

```bash
npm start --prefix ~/path/to/veeam-mcp-server/servers/vi-mcp
```

#### Alternatively, pass secrets on the command line

```bash
# On Mac/Linux
PRODUCT_NAME=vone WEB_URL=https://vone-server.local:1239/ ADMIN_USERNAME=.\\administrator ADMIN_PASSWORD=password ACCEPT_SELF_SIGNED_CERT=true npm start --silent --prefix ~/path/to/veeam-mcp-server/servers/vi-mcp

# On Windows
set PRODUCT_NAME=vone && set WEB_URL=https://vone-server.local:1239/ && set ADMIN_USERNAME=.\\administrator && set ADMIN_PASSWORD=password && set ACCEPT_SELF_SIGNED_CERT=true && npm start --silent --prefix c:\\path\\to\\veeam-mcp-server\\servers\\vi-mcp
```

### Option 3: Run as a shared HTTP server

Instead of each user starting a local process over `stdio`, the MCP server can run once as a network service and expose the MCP [Streamable HTTP](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports#streamable-http) transport. MCP clients then connect by URL. `stdio` remains the default; HTTP is enabled with `MCP_TRANSPORT=http`.

In HTTP mode there are **no shared Veeam credentials**: `ADMIN_USERNAME` and `ADMIN_PASSWORD` must not be set. Every user signs in with their own Veeam account, and the server works with that user's account and permissions. Choose how users sign in with `MCP_HTTP_AUTH`:

| `MCP_HTTP_AUTH` | How users sign in | Trade-off |
|---|---|---|
| `basic` (default) | The user puts their Veeam user name and password in the MCP client, which sends them with every request (HTTP Basic). | Simplest to run; the password sits in the client configuration and travels with every request. |
| `oauth` | The MCP client opens a sign-in page served by this server, the user enters the Veeam password once, and the client receives a short-lived token. | No password in any client configuration; needs a public URL and clients that support MCP OAuth (Claude Code, VS Code). |

Either way the server stores no passwords.

| Variable | Default | Description |
|---|---|---|
| `MCP_TRANSPORT` | `stdio` | `stdio` or `http` |
| `MCP_HTTP_AUTH` | `basic` | `basic` or `oauth`, see above. |
| `MCP_HTTP_HOST` | `127.0.0.1` | Interface to bind. Use `0.0.0.0` to accept connections from other machines. |
| `MCP_HTTP_PORT` | `8080` | Port to listen on. The endpoint is `/mcp`; `/healthz` is an unauthenticated health probe. |
| `MCP_HTTP_TLS_CERT_FILE`, `MCP_HTTP_TLS_KEY_FILE` | – | PEM certificate and key to serve HTTPS directly. |
| `MCP_HTTP_BEHIND_TLS_PROXY` | `false` | Set to `true` when a reverse proxy in front of the server terminates TLS. On a non-loopback address the server refuses to start without either this or a certificate, because passwords reach it over the network. |
| `MCP_HTTP_TRUST_PROXY` | `1` with `MCP_HTTP_BEHIND_TLS_PROXY=true`, otherwise `0` | Number of reverse proxies in front of the server, so the login rate limits see the real client address from `X-Forwarded-For`. |
| `MCP_HTTP_ALLOWED_HOSTS` | the `MCP_HTTP_PUBLIC_URL` host; otherwise loopback names on a loopback bind, otherwise any | Comma-separated host names accepted in the `Host` and `Origin` headers (DNS rebinding protection), for example `mcp.company.local`. |
| `MCP_HTTP_MAX_SESSIONS` | `1000` | Maximum concurrent sessions in total. A session is one connected MCP client window, not one user, and it lasts while the client stays connected. This is a safety net for server memory, not a capacity plan. |
| `MCP_HTTP_MAX_SESSIONS_PER_USER` | `10` | Maximum concurrent sessions of one Veeam user, so one user cannot take every session. Normal use is one session per open editor or Claude Code window. |
| `MCP_HTTP_SESSION_IDLE_TIMEOUT_SEC` | `3600` | A session with no requests for this long is closed; the client re-initializes automatically. Must not be shorter than `ACTION_CONFIRMATION_TIMEOUT_SEC`. |

#### Basic sign-in

```bash
docker run -d --rm -p 8080:8080 \
  -e MCP_TRANSPORT=http \
  -e MCP_HTTP_HOST=0.0.0.0 \
  -e MCP_HTTP_TLS_CERT_FILE=/certs/server.crt \
  -e MCP_HTTP_TLS_KEY_FILE=/certs/server.key \
  -v /path/to/certs:/certs:ro \
  -e MCP_HTTP_ALLOWED_HOSTS=mcp.company.local \
  -e PRODUCT_NAME=vbr \
  -e WEB_URL=https://vbr-srv.local/ \
  veeam-intelligence-mcp-server
```

The server checks each user name and password against the Veeam product. A successful check is remembered in memory for up to five minutes so the product is not asked on every request.

The `Authorization` header value is `Basic ` followed by the Base64 encoding of `user:password`, for example `printf '%s' '.\jdoe:password' | base64`.

Connect Claude Code:

```bash
claude mcp add --transport http veeam-intelligence https://mcp.company.local:8080/mcp --header "Authorization: Basic <base64 of user:password>"
```

Claude Code stores this header in plain text in its configuration. In Visual Studio Code, let the editor prompt for it instead, so it is kept in the OS secret store (`.vscode/mcp.json`):

```json
{
  "servers": {
    "veeam-intelligence": {
      "type": "http",
      "url": "https://mcp.company.local:8080/mcp",
      "headers": { "Authorization": "Basic ${input:veeam-credentials}" }
    }
  },
  "inputs": [{ "id": "veeam-credentials", "type": "promptString", "description": "Base64 of your Veeam user:password", "password": true }]
}
```

#### OAuth sign-in

| Variable | Default | Description |
|---|---|---|
| `MCP_HTTP_PUBLIC_URL` | `http://localhost:<port>` on a loopback bind | Origin MCP clients use to reach the server, for example `https://mcp.company.local:8080`. **Required** off loopback; must be `https` unless it is `localhost`, and must not contain a path. |
| `MCP_HTTP_TOKEN_SECRET` | random per start | At least 32 characters, used to encrypt the tokens handed to clients. Without it, sign-ins end when the server restarts and do not work across replicas. Generate one with `openssl rand -hex 32`. |
| `MCP_HTTP_SIGN_IN_MAX_AGE_SEC` | `43200` | How long a sign-in can be renewed before the user must enter the Veeam password again. |
| `MCP_HTTP_ALLOWED_REDIRECT_URIS` | – | Comma-separated OAuth redirect URIs accepted besides loopback ones, for example `https://vscode.dev/redirect` for VS Code for the Web. |

```bash
docker run -d --rm -p 8080:8080 \
  -e MCP_TRANSPORT=http \
  -e MCP_HTTP_AUTH=oauth \
  -e MCP_HTTP_HOST=0.0.0.0 \
  -e MCP_HTTP_PUBLIC_URL=https://mcp.company.local:8080 \
  -e MCP_HTTP_TOKEN_SECRET=<output of openssl rand -hex 32> \
  -e MCP_HTTP_TLS_CERT_FILE=/certs/server.crt \
  -e MCP_HTTP_TLS_KEY_FILE=/certs/server.key \
  -v /path/to/certs:/certs:ro \
  -e PRODUCT_NAME=vbr \
  -e WEB_URL=https://vbr-srv.local/ \
  veeam-intelligence-mcp-server
```

How it works:

1. The client connects without a token, gets `401` and discovers the sign-in endpoints from `/.well-known/oauth-protected-resource/mcp` and `/.well-known/oauth-authorization-server`.
2. The client registers itself and opens the sign-in page in the browser. The page names the client and where it will be sent after sign-in.
3. The user enters their Veeam user name and password. The server signs in to the Veeam product with them and never keeps the password.
4. The client receives an access token that contains the user's Veeam token, encrypted with the server key. Client registrations, sign-in requests and codes are encrypted the same way, so the server keeps no sign-in state.
5. When the Veeam token expires, the client renews its token and the server renews the Veeam token with the product's refresh token. If the product issues no refresh token, the user signs in again.

Connect Claude Code; it runs the sign-in itself on first use (or from `/mcp`):

```bash
claude mcp add --transport http veeam-intelligence https://mcp.company.local:8080/mcp
```

Visual Studio Code (`.vscode/mcp.json`):

```json
{
  "servers": {
    "veeam-intelligence": { "type": "http", "url": "https://mcp.company.local:8080/mcp" }
  }
}
```

#### Things to know before exposing the HTTP endpoint

- **Each user acts as themselves.** Tool calls reach the Veeam product with the caller's own account, and a session can only be used by the user (and, for Basic, the password) that opened it. Actions proposed to one session cannot be listed or approved from another.
- **TLS is mandatory off loopback**, because passwords reach the server over the network. Never log the `Authorization` header in a reverse proxy.
- **Failed sign-ins are rate limited** to 10 per client address per 15 minutes. Behind more than one proxy, set `MCP_HTTP_TRUST_PROXY` to their number, or users share an address. A user whose password is already verified is not locked out by failures from the same address. The limit is per address, so if users reach the server through a TCP load balancer or NAT that hides their addresses, they share one limit; prefer a proxy that sets `X-Forwarded-For`.
- **Changing or disabling a Veeam account** takes effect within five minutes with Basic, and with OAuth once the current Veeam token expires and its renewal is refused.
- **Sessions live in memory.** If you run several replicas behind a load balancer, enable sticky sessions on the `Mcp-Session-Id` header. With OAuth, also give all replicas the same `MCP_HTTP_TOKEN_SECRET`.
- Clients that only launch local `stdio` servers (for example, Claude Desktop's `claude_desktop_config.json`) cannot connect to the HTTP endpoint directly; keep using `stdio` for them.

## Example usage with popular MCP clients

### Claude Desktop

1. Add the Veeam Intelligence MCP server to your Claude Desktop configuration. Edit `claude_desktop_config.json` and add the following configuration.

For help locating the Claude Desktop MCP configuration file, see the Model Context Protocol documentation.

#### Using Docker

```json
{
  "mcpServers": {
    "veeam-intelligence": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-e", "PRODUCT_NAME",
        "-e", "WEB_URL",
        "-e", "ADMIN_USERNAME",
        "-e", "ADMIN_PASSWORD",
        "-e", "ACCEPT_SELF_SIGNED_CERT",
        "veeam-intelligence-mcp-server"
      ],
      "env": {
        "PRODUCT_NAME": "vone",
        "WEB_URL": "https://veeamone-srv:1239/",
        "ADMIN_USERNAME": "username",
        "ADMIN_PASSWORD": "secret",
        "ACCEPT_SELF_SIGNED_CERT": "true"
      }
    }
  }
}
```

#### Using npm

```json
{
  "mcpServers": {
    "veeam-intelligence": {
      "command": "npm",
      "args": [
        "start",
        "--silent",
        "--prefix",
        "/path/to/veeam-mcp-server/servers/vi-mcp"
      ],
      "env": {
        "PRODUCT_NAME": "vone",
        "WEB_URL": "https://veeamone-srv:1239/",
        "ADMIN_USERNAME": "username",
        "ADMIN_PASSWORD": "secret",
        "ACCEPT_SELF_SIGNED_CERT": "true"
      }
    }
  }
}
```

Replace the placeholder values inside the `env` block with your own secrets.

2. Restart Claude Desktop to apply the changes. The server starts without contacting the Veeam product, so connection or credential problems surface in the tool response when you ask a question. If Claude Desktop shows an MCP initialization error, review the MCP logs for troubleshooting.

```bash
# Follow Veeam Intelligence MCP server logs in real time (macOS)
tail -n 20 -F ~/Library/Logs/Claude/mcp-server-veeam-intelligence.log
```

## Visual Studio Code

Refer to the Visual Studio Code documentation for how to set up MCP servers in VS Code.

### Configure Veeam Intelligence MCP server in the current workspace

To use this MCP server with GitHub Copilot in VS Code, create a `.vscode/mcp.json` file in your workspace.

1. Create a `.vscode` directory in your workspace if it does not exist:

```bash
mkdir -p .vscode
```

2. Create a `.vscode/mcp.json` file with the following configuration.

#### Using Docker

```json
{
  "inputs": [
    {
      "id": "product-name",
      "type": "pickString",
      "options": [
        "vbr",
        "vone",
        "vspc"
      ],
      "description": "Select a product name to connect VI MCP to"
    },
    {
      "id": "product-web-url",
      "type": "promptString",
      "description": "Product web UI URL for selected product"
    },
    {
      "id": "admin-login",
      "type": "promptString",
      "description": "Administrator login for selected product"
    },
    {
      "id": "admin-password",
      "type": "promptString",
      "description": "Administrator password for selected product"
    },
    {
      "id": "accept-self-signed-cert",
      "type": "promptString",
      "description": "Trust self-signed certificates of Veeam Server? (true/false)"
    }
  ],
  "servers": {
    "veeam-intelligence": {
      "type": "stdio",
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-e", "PRODUCT_NAME",
        "-e", "WEB_URL",
        "-e", "ADMIN_USERNAME",
        "-e", "ADMIN_PASSWORD",
        "-e", "ACCEPT_SELF_SIGNED_CERT",
        "veeam-intelligence-mcp-server"
      ],
      "env": {
        "PRODUCT_NAME": "${input:product-name}",
        "WEB_URL": "${input:product-web-url}",
        "ADMIN_USERNAME": "${input:admin-login}",
        "ADMIN_PASSWORD": "${input:admin-password}",
        "ACCEPT_SELF_SIGNED_CERT": "${input:accept-self-signed-cert}"
      }
    }
  }
}
```

#### Using npm

```json
{
  "inputs": [
    {
      "id": "product-name",
      "type": "pickString",
      "options": [
        "vbr",
        "vone",
        "vspc"
      ],
      "description": "Select a product name to connect VI MCP to"
    },
    {
      "id": "product-web-url",
      "type": "promptString",
      "description": "Product web UI URL for selected product"
    },
    {
      "id": "admin-login",
      "type": "promptString",
      "description": "Administrator login for selected product"
    },
    {
      "id": "admin-password",
      "type": "promptString",
      "description": "Administrator password for selected product"
    },
    {
      "id": "accept-self-signed-cert",
      "type": "promptString",
      "description": "Trust self-signed certificates of Veeam Server? (true/false)"
    }
  ],
  "servers": {
    "veeam-intelligence": {
      "type": "stdio",
      "command": "npm",
      "args": [
        "start",
        "--silent",
        "--prefix",
        "~/path/to/veeam-mcp-server/servers/vi-mcp"
      ],
      "env": {
        "PRODUCT_NAME": "${input:product-name}",
        "WEB_URL": "${input:product-web-url}",
        "ADMIN_USERNAME": "${input:admin-login}",
        "ADMIN_PASSWORD": "${input:admin-password}",
        "ACCEPT_SELF_SIGNED_CERT": "${input:accept-self-signed-cert}"
      }
    }
  }
}
```

### Start MCP server in VS Code

1. Open Copilot.
2. At the bottom, click the tools icon and select the `veeam-intelligence` tool. The first time, click **Update Tools** under the `veeam-intelligence` section.
3. Fill in the prompted variables.
4. Once the MCP server is configured and selected in Copilot, it will answer requests that involve Veeam products.

## Actions (VBR 13.1 and later)

Veeam Backup & Replication 13.1 introduces the `AdvancedWithActions` chatbot mode: besides answering questions, Veeam Intelligence can propose product actions such as starting or disabling a job, rescanning a repository, or running a restore. The MCP server supports this mode with a **human-in-the-loop** design:

- The MCP server **follows the chatbot mode configured on the Veeam server**; there is no separate switch. Actions are offered only when the product reports `AdvancedWithActions` (enabled by the VBR administrator in Veeam Intelligence settings). If the server has no action policy for the product version, the handshake is downgraded to `Advanced` (read-only) so Veeam Intelligence never proposes actions the server cannot gate.
- Every state-changing REST call proposed by Veeam Intelligence is checked against a **deny-by-default policy** that mirrors the VBR web UI: `GET` requests always run; a small whitelist of POST-shaped reads and routine maintenance calls runs silently; the checklist of real actions (start/stop/disable job, restores, failover, ...) requires the user's confirmation; anything else is rejected without being executed.
- Confirmations are delivered to the user by the MCP client:
  - **Clients with MCP elicitation** (Claude Code, Visual Studio Code): the server asks for approval inside the tool call with a native Yes/No dialog that shows the action title, its risk description, the exact request (method, path, body) and Veeam Intelligence's own explanation.
  - **Clients without elicitation** (Claude Desktop): the `veeam-question-answering` tool returns early with a `pending_action` object and instructions. The assistant must present the action to the user and ask for approval; the user's decision is then passed to the `veeam-confirm-action` tool (`action_id`, `approve: true|false`), which executes (or declines) the action and returns the rest of the answer. Claude Desktop additionally shows its own permission prompt before `veeam-confirm-action` runs. `veeam-list-pending-actions` lists actions still waiting for a decision.
- A declined or unanswered action (after `ACTION_CONFIRMATION_TIMEOUT_SEC`) is reported to Veeam Intelligence as cancelled by the user, and the answer says the action did not run. The `actions` field of every response lists what was executed, declined, rejected by policy or expired.

No MCP-side configuration is needed: switch the Veeam Intelligence chatbot mode on the Veeam server to `AdvancedWithActions`. The MCP server reads the chatbot mode from the product on every question, so no restart is required. To run the MCP server read-only, keep the product in `Advanced` mode.

Limitations: the action policy currently covers VBR 13.1/13.2 REST endpoints (VBR 13.2 uses the same policy); actions are not available for Veeam ONE or VSPC. Each question opens a new Veeam Intelligence chat, so a confirmation must be answered within the same action flow rather than by asking a new question.

## Known issues

- Running the Veeam Intelligence MCP server may fail if the connected Veeam Backup & Replication 13.0.1 instance uses multi-factor authentication (MFA). This issue will be addressed in upcoming releases.
