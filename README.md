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
cd veeam-mcp-server
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

Before using the Veeam Intelligence MCP server, build the Docker image:

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

1. In the MCP repository root, copy `.env.example` to `.env` and populate the values.
2. Configure your MCP client to run the server as follows:

```bash
npm start --prefix ~/path/to/mcp/server
```

#### Alternatively, pass secrets on the command line

```bash
# On Mac/Linux
PRODUCT_NAME=vone WEB_URL=https://vone-server.local:1239/ ADMIN_USERNAME=.\\administrator ADMIN_PASSWORD=password ACCEPT_SELF_SIGNED_CERT=true npm start --silent --prefix ~/path/to/mcp/server

# On Windows
set PRODUCT_NAME=vone && set WEB_URL=https://vone-server.local:1239/ && set ADMIN_USERNAME=.\\administrator && set ADMIN_PASSWORD=password && set ACCEPT_SELF_SIGNED_CERT=true && npm start --silent --prefix c:\\path\\to\\mcp\\server
```

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
        "/path/to/mcp/server"
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

2. Restart Claude Desktop to apply the changes. If Claude Desktop shows an MCP initialization error, review the MCP logs for troubleshooting.

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
        "~/path/to/mcp/server"
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

No MCP-side configuration is needed: switch the Veeam Intelligence chatbot mode on the Veeam server to `AdvancedWithActions` and restart the MCP client. The server logs the product mode and the effective mode on startup (`mcp-server-veeam-intelligence.log` in Claude Desktop). To run the MCP server read-only, keep the product in `Advanced` mode.

Limitations: the action policy currently covers VBR 13.1/13.2 REST endpoints (VBR 13.2 uses the same policy); actions are not available for Veeam ONE or VSPC. Each question opens a new Veeam Intelligence chat, so a confirmation must be answered within the same action flow rather than by asking a new question.

## Known issues

- Running the Veeam Intelligence MCP server may fail if the connected Veeam Backup & Replication 13.0.1 instance uses multi-factor authentication (MFA). This issue will be addressed in upcoming releases.
