# Veeam Backup & Replication MCP Server

The Veeam Backup & Replication MCP Server (`vbr-mcp`) exposes a curated subset of the Veeam Backup & Replication (VBR)
REST API as tools for MCP-compatible clients, such as Claude Code, Claude Desktop, Visual Studio Code, and others.

Tools are grouped by resource (jobs, sessions, backups, restore, backup infrastructure, licensing, and more) rather
than mapped one per raw endpoint, so a model can pick the right one reliably. Several of them do real work on top of
the API:

- `list_repositories` joins repository configuration with live capacity state and derives free, used and unidentified
  space.
- `get_session_failure_details` collapses "why did this job fail" into a single call across session logs and failing
  task sessions.
- Every list tool pages through the whole result set concurrently instead of returning only the first page.

See [Tools](#tools) for the full list.

## Safety and permissions

**Read this before pointing the server at anything you care about.**

Of the 49 tools, 29 only read. The other 20 change state, and 12 of those can interrupt protection or destroy data:

- `restore_vsphere_vm`, `restore_file_share`, `restore_object_storage`: can overwrite an existing VM, file share or
  bucket
- `start_instant_recovery_vsphere_vm`, `migrate_instant_recovery_vsphere_vm`, `unmount_instant_recovery_vsphere_vm`:
  publish a VM into production vSphere, finalize the migration, or tear a running mount down
- `stop_job`, `disable_job`: interrupt a running job or stop it running on its schedule, leaving workloads unprotected
- `set_sobr_extent_maintenance_mode`, `set_sobr_extent_sealed_mode`, `update_managed_server_components`: change backup
  infrastructure state
- `revoke_license`: releases a consumed license unit

Every tool is annotated with the MCP `readOnlyHint` and `destructiveHint` hints, so a client that supports them can ask
you to confirm before a destructive call. The server also sends its usage policy as MCP server instructions: the agent
names the target and the consequences and waits for your confirmation before a destructive call, lists the targets
first for an action on several objects, and treats "what happens if…" as a question, not a request. **Honoring the
hints and the instructions is the client's choice, not something this server enforces.**

The server applies no authorization model of its own: a tool call runs with the full rights of the VBR account in
`VBR_USERNAME`. Constrain it there.

- Create a **dedicated, least-privilege VBR account** for the server instead of reusing a full administrator.
- Try it against a **lab or test VBR server first**.

See [SECURITY.md](SECURITY.md) for the full security model and how to report a vulnerability.

## Prerequisites

- **Veeam Backup & Replication 13**. The server sends `x-api-version: 1.3-rev2` by default; set `VBR_API_VERSION` for
  other builds.
- A VBR account that can use the REST API, and network access to the REST API port (9419 by default).
- One of the following:
  - [**uv**](https://docs.astral.sh/uv/getting-started/installation/) to run the server locally. It installs
    Python 3.13 if your system does not have it.
  - **Docker** to run the server in a container.

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/veeam-ai/veeam-mcp-server
cd veeam-mcp-server/servers/vbr-mcp
```

### 2. Configure the connection

In the `servers/vbr-mcp` directory, copy `.env.example` to `.env` and fill in the VBR connection details. At minimum,
set `VBR_BASE_URL`, `VBR_USERNAME` and `VBR_PASSWORD`.

```bash
cp .env.example .env
```

| Variable | Default | Description |
| --- | --- | --- |
| `VBR_BASE_URL` | `https://localhost:9419` | Base URL of the VBR REST API server, for example, `https://vbr-srv.local:9419` |
| `VBR_USERNAME` | — | VBR REST API username used for the password grant |
| `VBR_PASSWORD` | — | VBR REST API password used for the password grant |
| `VBR_VERIFY_TLS` | `True` | Verify the VBR server's TLS certificate. Set to `False` for self-signed lab certificates only |
| `VBR_API_VERSION` | `1.3-rev2` | Sent as the `x-api-version` header |
| `VBR_REQUEST_TIMEOUT_SEC` | `30.0` | Per-request timeout for calls to VBR, in seconds |

- The server finds `.env` next to its own code, whatever working directory it is launched from. This matters because
  MCP clients do not necessarily start the server in `servers/vbr-mcp`.
- Variables already set in the environment, for example, in the `env` block of an MCP client configuration, take
  precedence over `.env`.
- A self-signed or private-CA certificate can stay verified: instead of `VBR_VERIFY_TLS=False`, point `SSL_CERT_FILE`
  (also read from `.env`) at a PEM file with the server's certificate or its CA. The server checks certificates
  against its own CA bundle (certifi), not the operating system's store, so installing the CA there does not help.

### Option 1: Run with uv

Install the dependencies:

```bash
uv sync
```

The server talks MCP over `stdio` transport: the MCP client starts it as its own child process with `uv run vbr-mcp`.
See [Example usage with MCP clients](#example-usage-with-mcp-clients) for client configurations.

To try the tools without an AI client, open them in [MCP Inspector](https://github.com/modelcontextprotocol/inspector)
(requires Node.js):

```bash
npx @modelcontextprotocol/inspector uv run vbr-mcp
```

### Option 2: Run in Docker

The same `stdio` server, packaged: no uv or Python is needed on the machine that runs it.

#### 1. Build the Docker image

Run one of these commands from the `servers/vbr-mcp` directory:

```bash
# Option 1: Using make
make docker-build

# Option 2: Using Docker directly
docker build -f docker/Dockerfile -t vbr-mcp .
```

#### 2. Set up your MCP client

The MCP client starts a container for each session, in place of `uv run vbr-mcp`:

```bash
docker run -i --rm --env-file /absolute/path/to/veeam-mcp-server/servers/vbr-mcp/.env vbr-mcp
```

- `-i` attaches stdin, which carries the MCP protocol. Do not add `-t`: a terminal would corrupt it.
- The VBR credentials are read from `.env` when the container starts and are never baked into an image layer.
  `--env-file` takes values literally, so write them in `.env` without quotes.
- Inside the container, `localhost` is the container itself. If VBR, or a tunnel to it, listens on your machine, use
  `host.docker.internal` instead of `localhost` in `VBR_BASE_URL`. On Linux, also add
  `--add-host=host.docker.internal:host-gateway` to `docker run`.

## Example usage with MCP clients

In the examples below, replace `/absolute/path/to/veeam-mcp-server` with the location of your clone. Unless a
configuration sets them itself, the connection details come from `servers/vbr-mcp/.env`.

### Claude Code

#### Using uv

```bash
claude mcp add vbr -- uv run --project /absolute/path/to/veeam-mcp-server/servers/vbr-mcp vbr-mcp
```

`--project` points uv at the project explicitly, whatever working directory Claude Code starts the server in. No
`--scope` is needed: the default `local` scope keeps this personal configuration out of a checked-in `.mcp.json`.

#### Using Docker

Once the image is built:

```bash
claude mcp add vbr -- docker run -i --rm --env-file /absolute/path/to/veeam-mcp-server/servers/vbr-mcp/.env vbr-mcp
```

### Claude Desktop

1. Add the server to your Claude Desktop configuration: edit `claude_desktop_config.json` and add one of the following
   configurations. For help locating the file, see the Model Context Protocol documentation.

#### Using uv

```json
{
  "mcpServers": {
    "vbr": {
      "command": "uv",
      "args": ["run", "--project", "/absolute/path/to/veeam-mcp-server/servers/vbr-mcp", "vbr-mcp"]
    }
  }
}
```

If Claude Desktop cannot find `uv` (the log shows `spawn uv ENOENT`), set `command` to the absolute path that
`which uv` prints.

#### Using Docker

```json
{
  "mcpServers": {
    "vbr": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "--env-file", "/absolute/path/to/veeam-mcp-server/servers/vbr-mcp/.env",
        "vbr-mcp"
      ]
    }
  }
}
```

2. Restart Claude Desktop to apply the changes. The server signs in to VBR only on the first tool call, so a wrong URL
   or password surfaces in the tool response when you ask a question. If Claude Desktop shows an MCP initialization
   error, review the MCP logs:

```bash
# Follow VBR MCP server logs in real time (macOS)
tail -n 20 -F ~/Library/Logs/Claude/mcp-server-vbr.log
```

### Visual Studio Code

To use the server with GitHub Copilot in VS Code, create a `.vscode/mcp.json` file in your workspace. This
configuration prompts for the VBR password instead of writing it to disk, and sets the other connection details in
`env`. Add `VBR_VERIFY_TLS` or any other variable from [Configure the connection](#2-configure-the-connection) to `env`
when you need it.

#### Using uv

```json
{
  "inputs": [
    {
      "type": "promptString",
      "id": "vbr-password",
      "description": "VBR REST API password",
      "password": true
    }
  ],
  "servers": {
    "vbr": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--project", "/absolute/path/to/veeam-mcp-server/servers/vbr-mcp", "vbr-mcp"],
      "env": {
        "VBR_BASE_URL": "https://vbr-srv.local:9419",
        "VBR_USERNAME": "svc-mcp",
        "VBR_PASSWORD": "${input:vbr-password}"
      }
    }
  }
}
```

#### Using Docker

Use the same file with `command` and `args` replaced as follows. The container receives only the variables passed with
`-e`, so add `-e` for every variable you set in `env`:

```jsonc
"command": "docker",
"args": ["run", "-i", "--rm", "-e", "VBR_BASE_URL", "-e", "VBR_USERNAME", "-e", "VBR_PASSWORD", "vbr-mcp"],
```

To start the server, click **Start** above its entry in `mcp.json` or run the **MCP: List Servers** command, and enter
the password when prompted. The `vbr` tools are then available in Copilot Chat agent mode.

## Tools

49 tools across 14 resource groups. The **Access** column shows what a tool does to the VBR server: `read` touches
nothing, `write` changes state additively or reversibly, and **destructive** may interrupt protection or overwrite
data.

### Jobs

| Tool | Access | What it does |
| --- | --- | --- |
| `list_jobs` | read | List backup job configuration, or, with `id`, one job's configuration |
| `get_job_states` | read | List jobs' live operational state: running/idle status, last-run result, progress/throughput, bottleneck |
| `start_job` | write | Start a job now |
| `stop_job` | **destructive** | Stop a running job |
| `retry_job` | write | Retry a job's last run, reprocessing only the objects that previously failed |
| `enable_job` | write | Enable a disabled job so its schedule resumes |
| `disable_job` | **destructive** | Disable a job so it no longer runs on its schedule |

### Sessions

| Tool | Access | What it does |
| --- | --- | --- |
| `list_sessions` | read | List sessions (the run history of any VBR operation), or, with `id`, one session |
| `list_task_sessions` | read | List task sessions, the per-object fan-out of a session. Use `session_id_filter` to scope to one session |
| `get_session_failure_details` | read | One-shot "why did this session fail" drill-down |

### Backups

| Tool | Access | What it does |
| --- | --- | --- |
| `list_backups` | read | List backups (the on-disk backup chains, not individual restore points) |
| `get_backup_details` | read | Return one backup's protected objects and/or backup-file storage footprint |

### Protected objects

| Tool | Access | What it does |
| --- | --- | --- |
| `list_protected_objects` | read | List protected objects, or, with `id`, that object's restore-point history |
| `list_restore_points` | read | List restore points across the whole estate (or scoped to one object/backup) |
| `get_restore_point_disks` | read | List the disks captured by one restore point |

### Restore

| Tool | Access | What it does |
| --- | --- | --- |
| `start_instant_recovery_vsphere_vm` | **destructive** | Start a vSphere Instant Recovery: publish a restore point as a running VM without a full data copy (to its original location, or a chosen host/resource pool/folder; also from a backup of a non-vSphere workload) |
| `get_instant_recovery_mount_status` | read | Check the status of a vSphere Instant Recovery mount, or list active mounts to find one's id |
| `migrate_instant_recovery_vsphere_vm` | **destructive** | Quick-migrate a mounted Instant Recovery VM to permanent storage on `destination_host` |
| `unmount_instant_recovery_vsphere_vm` | **destructive** | Unmount (tear down) a vSphere Instant Recovery mount |
| `restore_file_share` | **destructive** | Restore an entire unstructured-data file share from `restore_point_id` |
| `restore_object_storage` | **destructive** | Restore an entire object-storage bucket/container from `restore_point_id` |
| `restore_vsphere_vm` | **destructive** | Restore an entire vSphere VM (a full-copy restore, not Instant Recovery) from `restore_point_id` |

### Backup infrastructure

| Tool | Access | What it does |
| --- | --- | --- |
| `list_proxies` | read | List backup proxies, joined with their live state (one flat row per proxy) |
| `set_proxy_enabled` | write | Enable or disable one backup proxy (a disabled proxy is skipped by job scheduling) |
| `list_repositories` | read | List backup repositories, joined with live state: capacity, free space, and reconciliation |
| `rescan_repositories` | write | Rescan one or more backup repositories to refresh their known state |
| `list_scale_out_repositories` | read | List Scale-Out Backup Repositories (SOBRs), each with its tiers and member extents already inlined |
| `set_sobr_extent_maintenance_mode` | **destructive** | Put SOBR performance-tier extents into (or take them out of) maintenance mode |
| `set_sobr_extent_sealed_mode` | **destructive** | Seal (or unseal) SOBR performance-tier extents. A sealed extent keeps existing data but takes no new writes |
| `list_wan_accelerators` | read | List WAN accelerators: cache size/location, high-bandwidth mode, stream counts |
| `rescan_managed_server` | write | Rescan one managed server (host/cluster) to refresh its inventory |
| `update_managed_server_components` | **destructive** | Update the Veeam components installed on one or more managed servers |

### Inventory

| Tool | Access | What it does |
| --- | --- | --- |
| `list_unstructured_data_servers` | read | List registered NAS/unstructured-data sources, or, with `id`, one server's full record |
| `list_vmware_hosts` | read | List the vSphere servers VBR manages: vCenter Servers and standalone ESXi hosts |
| `browse_inventory` | read | Browse the virtualization inventory: managed servers, or one server's hosts, resource pools, datastores, folders and networks. This is the source of every restore placement |

### Protection groups

| Tool | Access | What it does |
| --- | --- | --- |
| `list_protection_groups` | read | List agent protection groups: the policies that discover and manage Veeam Agent installs across computers |
| `get_protection_group_entities` | read | List the computers/containers one protection group discovered, with their agent/driver install state |

### Malware detection

| Tool | Access | What it does |
| --- | --- | --- |
| `list_malware_events` | read | List malware-detection events, newest detection first by default |
| `get_yara_rules` | read | List the YARA rules configured for malware-detection scanning |
| `start_malware_scan` | write | Start a malware scan of a workload's backup |

### Licensing

| Tool | Access | What it does |
| --- | --- | --- |
| `get_license_status` | read | Return the installed license's status plus its per-workload breakdown for every active model |
| `create_license_report` | read | Generate VBR's own point-in-time license usage report. Read-only despite the `POST` |
| `revoke_license` | **destructive** | Revoke one consumed license unit, freeing it back to the pool |

### Configuration backup

| Tool | Access | What it does |
| --- | --- | --- |
| `get_config_backup_status` | read | Return the VBR configuration-backup posture: enabled, schedule, retention, encryption, target repository |
| `start_config_backup` | write | Start a VBR configuration backup now, using its configured settings |

### General options

| Tool | Access | What it does |
| --- | --- | --- |
| `get_general_options` | read | Return VBR's global options: email settings, disk-space/support/update notification thresholds, SIEM forwarding |

### Server info

| Tool | Access | What it does |
| --- | --- | --- |
| `get_server_status` | read | Return the VBR server's version/build, DB engine/version, registration status/expiry, and server time/timezone |

### Generic REST API reads

| Tool | Access | What it does |
| --- | --- | --- |
| `api_get` | read | Send any GET request to the VBR REST API, for data no dedicated tool returns |
| `api_post_query` | read | Send a read-only POST query (inventory browser, ACLs, restore point network info). Any other POST is refused |

## Limitations

- **One VBR server per process.** The connection is configured from the environment at startup, so a process cannot
  switch to another VBR server at runtime or serve several. To work with several VBR servers, add one MCP client entry
  per server, each with its own `env`.
- **Configuration is environment-only.** There are no CLI flags and no configuration file other than `.env`.
- **The destructive/read-only split is advisory.** It is published as MCP tool annotations and server instructions for
  clients to act on; the server does not gate or confirm calls itself. See
  [Safety and permissions](#safety-and-permissions).
- **No logging of its own.** The only log is FastMCP's, on stderr: its startup banner and a line for every failed tool
  call (`Error calling tool '<name>'`, with a traceback for an unexpected error and a warning for invalid arguments).
  The error text itself goes to the client. `FASTMCP_LOG_LEVEL=CRITICAL` silences the tool-call lines.

## Development

```bash
make install            # uv sync --all-groups
make quality            # ruff format, ruff check --fix, then typecheck
make quality-check      # ruff format and ruff check without rewriting files (CI runs this and typecheck)
make typecheck          # ty
make test               # pytest with coverage
make env-example        # regenerate .env.example from the settings classes
make check-env-example  # fail if .env.example drifted from the settings classes
```

`.env.example` is generated from the settings classes, so it cannot drift from the code. Regenerate it with
`make env-example` after changing `src/vbr_mcp/settings.py`.

Tools that send structured request bodies take Pydantic models from `src/vbr_mcp/models/`, so each tool publishes
VBR's real body schema to MCP clients instead of a free-form object. The models mirror the VBR REST API 1.3-rev2
schemas of the same name and are maintained by hand, one module per tool plus `shared.py` for parts several tools use.
Add or adjust one when a tool needs another body part.

The models check a request's shape; `src/vbr_mcp/vsphere_placement.py` and the restore tools check its meaning before
anything is sent. They reject what VBR was seen to refuse or silently ignore when tested against VBR 13.1: a placement
object of the wrong type, objects from different managed servers, a standalone ESXi host's `ha-host` row, an Instant
Recovery folder that is a `Datacenter`, restore disk names that are not the restore point's own, and a customized VM
restore without a network mapping for a VM that has networks.

The test suite mocks the VBR REST API at the transport layer with `pytest-httpx` and drives the tools through the real
MCP protocol with an in-process `fastmcp.Client`, so no VBR server is needed to run it. The evals in
[integration_tests](integration_tests/README.md), where an LLM agent drives the server against a mocked VBR, are a
separate uv project.

Every source file carries the Veeam copyright header, enforced by ruff's `CPY001` rule.

## Security

See [SECURITY.md](SECURITY.md) for the security model and for how to report a vulnerability. Please do not report
security issues through public GitHub issues.

## License

[MIT](LICENSE) © Veeam Software
