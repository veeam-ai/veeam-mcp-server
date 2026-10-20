# vbr-mcp

MCP server that exposes a curated subset of the Veeam Backup & Replication (VBR) REST API
as tools for MCP-compatible clients such as Claude Code, Claude Desktop, VS Code and
MCP Inspector.

Tools are grouped by resource — jobs, sessions, repositories, restore points, licensing —
rather than mapped one per raw endpoint, so a model can pick the right one reliably. Several
of them do real work on top of the API: `list_repositories` joins repository configuration
with live capacity state and derives free, used and unidentified space; `get_session_failure_details`
collapses "why did this job fail" into a single call across session logs and failing task
sessions; and every list tool pages through the whole result set concurrently instead of
returning only the first page.

## Safety and permissions

**Read this before pointing the server at anything you care about.**

Of the 49 tools, 29 only read. The other 20 change state, and 12 of those can interrupt
protection or destroy data:

- `restore_vsphere_vm`, `restore_file_share`, `restore_object_storage` — can overwrite an
  existing VM, file share or bucket
- `start_instant_recovery_vsphere_vm`, `migrate_instant_recovery_vsphere_vm`,
  `unmount_instant_recovery_vsphere_vm` — publish a VM into production vSphere, finalize the
  migration, or tear a running mount down
- `stop_job`, `disable_job` — interrupt a running job or stop it running on its schedule,
  leaving workloads unprotected
- `set_sobr_extent_maintenance_mode`, `set_sobr_extent_sealed_mode`,
  `update_managed_server_components` — change backup infrastructure state
- `revoke_license` — releases a consumed license unit

Every tool is annotated with the MCP `readOnlyHint` and `destructiveHint` hints, so a client
that supports them can ask you to confirm before a destructive call. The server also sends its
usage policy as MCP server instructions: the agent names the target and the consequences and
waits for your confirmation before a destructive call, lists the targets first for an action on
several objects, and treats "what happens if…" as a question, not a request. **Honoring the
hints and the instructions is the client's choice, not something this server enforces.**

The server applies no authorization model of its own: a tool call runs with the full rights
of the VBR account in `VBR_USERNAME`. Constrain it there.

- Create a **dedicated, least-privilege VBR account** for the server instead of reusing a
  full administrator.
- Try it against a **lab or test VBR server first**.

See [SECURITY.md](SECURITY.md) for the full security model and how to report a vulnerability.

## Prerequisites

- **Veeam Backup & Replication 13** — the server sends `x-api-version: 1.3-rev2` by default.
  Point `VBR_API_VERSION` at a different revision for other builds.
- A VBR account that can use the REST API, and network access to its port (9419 by default).
- **Python 3.13** and [**uv**](https://docs.astral.sh/uv/getting-started/installation/).
  Docker instead of both if you only want to run the container.

## Setup

```
git clone https://github.com/veeam-ai/veeam-mcp-server
cd veeam-mcp-server/servers/vbr-mcp
uv sync --all-groups
```

### Configuration

In the `servers/vbr-mcp` directory, copy `.env.example` to `.env` and fill in the VBR connection
details (`VBR_BASE_URL`, `VBR_USERNAME`, `VBR_PASSWORD`, and `VBR_VERIFY_TLS=False` for
self-signed lab certificates).

`.env` is resolved relative to this project's own location, so the server finds it regardless
of the working directory it is launched from — which matters because MCP clients spawn the
server without necessarily setting a matching cwd.

Every setting and its default is listed under [Configuration reference](#configuration-reference).

### Run locally

The server talks MCP over stdio: the MCP client spawns it as its own child process.

```
uv run vbr-mcp
```

To poke at the tools directly instead of through an agent:

```
npx @modelcontextprotocol/inspector uv run vbr-mcp
```

### Run in Docker

The same stdio server, packaged — no Python or uv needed on the machine, and the image is
reproducible enough to hand to someone else. Build it once, from the `servers/vbr-mcp` directory:

```
make docker-build   # docker build -f docker/Dockerfile -t vbr-mcp . (the context is servers/vbr-mcp)
```

The MCP client then starts a container for each session, in place of `uv run vbr-mcp`:

```
docker run -i --rm --env-file /absolute/path/to/veeam-mcp-server/servers/vbr-mcp/.env vbr-mcp
```

`-i` attaches stdin, which carries the MCP protocol; leave out `-t`, as a terminal would corrupt
it. The VBR credentials come from `.env` when the container starts and are never baked into an
image layer. `--env-file` takes values literally, so write them in `.env` without quotes.

If `VBR_BASE_URL` points at a VBR server reachable only from your machine, address it as
`host.docker.internal` rather than `localhost`; on Linux, also pass
`--add-host=host.docker.internal:host-gateway` to `docker run`.

## Example usage with MCP clients

### Claude Code

```
claude mcp add vbr -- uv run --project /absolute/path/to/veeam-mcp-server/servers/vbr-mcp vbr-mcp
```

`--project` pins the uv project explicitly, independent of the working directory Claude
chooses. No `--scope` is needed — `local` is the default and keeps this personal config out of
a checked-in `.mcp.json`.

In Docker, once the image is built:

```
claude mcp add vbr -- docker run -i --rm --env-file /absolute/path/to/veeam-mcp-server/servers/vbr-mcp/.env vbr-mcp
```

### Claude Desktop

Add the server to `claude_desktop_config.json`, then restart Claude Desktop.

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

To follow the server's logs while it runs (macOS):

```bash
tail -n 20 -F ~/Library/Logs/Claude/mcp-server-vbr.log
```

### Visual Studio Code

Create `.vscode/mcp.json` in a workspace opened at the repository root. This form prompts for
the VBR password instead of writing it to disk:

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
      "args": ["run", "--project", "${workspaceFolder}/servers/vbr-mcp", "vbr-mcp"],
      "env": {
        "VBR_BASE_URL": "https://vbr.example.com:9419",
        "VBR_USERNAME": "svc-mcp",
        "VBR_PASSWORD": "${input:vbr-password}"
      }
    }
  }
}
```

## Tools

49 tools across 14 resource groups. The middle column marks what a tool does to the VBR server:
`read` touches nothing, `write` changes state additively or reversibly, and **destructive** may
interrupt protection or overwrite data.

### Jobs

| Tool | | What it does |
| --- | --- | --- |
| `list_jobs` | read | List backup job configuration, or - with `id` - one job's configuration |
| `get_job_states` | read | List jobs' live operational state: running/idle status, last-run result, progress/throughput, bottleneck |
| `start_job` | write | Start a job now |
| `stop_job` | **destructive** | Stop a running job |
| `retry_job` | write | Retry a job's last run, reprocessing only the objects that previously failed |
| `enable_job` | write | Enable a disabled job so its schedule resumes |
| `disable_job` | **destructive** | Disable a job so it no longer runs on its schedule |

### Sessions

| Tool | | What it does |
| --- | --- | --- |
| `list_sessions` | read | List sessions (the run history of any VBR operation), or - with `id` - one session |
| `list_task_sessions` | read | List task sessions - the per-object fan-out of a session. Use `session_id_filter` to scope to one session |
| `get_session_failure_details` | read | One-shot "why did this session fail" drill-down |

### Backups

| Tool | | What it does |
| --- | --- | --- |
| `list_backups` | read | List backups (the on-disk backup chains, not individual restore points) |
| `get_backup_details` | read | Return one backup's protected objects and/or backup-file storage footprint |

### Protected objects

| Tool | | What it does |
| --- | --- | --- |
| `list_protected_objects` | read | List protected objects, or - with `id` - that one object's restore-point history |
| `list_restore_points` | read | List restore points across the whole estate (or scoped to one object/backup) |
| `get_restore_point_disks` | read | List the disks captured by one restore point |

### Restore

| Tool | | What it does |
| --- | --- | --- |
| `start_instant_recovery_vsphere_vm` | **destructive** | Start a vSphere Instant Recovery: publish a restore point as a running VM without a full data copy (to its original location, or a chosen host/resource pool/folder; also from a backup of a non-vSphere workload) |
| `get_instant_recovery_mount_status` | read | Check the status of a vSphere Instant Recovery mount, or list active mounts to find one's id |
| `migrate_instant_recovery_vsphere_vm` | **destructive** | Quick-migrate a mounted Instant Recovery VM to permanent storage on `destination_host` |
| `unmount_instant_recovery_vsphere_vm` | **destructive** | Unmount (tear down) a vSphere Instant Recovery mount |
| `restore_file_share` | **destructive** | Restore an entire unstructured-data file share from `restore_point_id` |
| `restore_object_storage` | **destructive** | Restore an entire object-storage bucket/container from `restore_point_id` |
| `restore_vsphere_vm` | **destructive** | Restore an entire vSphere VM (a full-copy restore, not Instant Recovery) from `restore_point_id` |

### Backup infrastructure

| Tool | | What it does |
| --- | --- | --- |
| `list_proxies` | read | List backup proxies, joined with their live state (one flat row per proxy) |
| `set_proxy_enabled` | write | Enable or disable one backup proxy (a disabled proxy is skipped by job scheduling) |
| `list_repositories` | read | List backup repositories, joined with live state: capacity, free space, and reconciliation |
| `rescan_repositories` | write | Rescan one or more backup repositories to refresh their known state |
| `list_scale_out_repositories` | read | List Scale-Out Backup Repositories (SOBRs), each with its tiers and member extents already inlined |
| `set_sobr_extent_maintenance_mode` | **destructive** | Put SOBR performance-tier extents into (or take them out of) maintenance mode |
| `set_sobr_extent_sealed_mode` | **destructive** | Seal (or unseal) SOBR performance-tier extents - a sealed extent keeps existing data but takes no new writes |
| `list_wan_accelerators` | read | List WAN accelerators: cache size/location, high-bandwidth mode, stream counts |
| `rescan_managed_server` | write | Rescan one managed server (host/cluster) to refresh its inventory |
| `update_managed_server_components` | **destructive** | Update the Veeam components installed on one or more managed servers |

### Inventory

| Tool | | What it does |
| --- | --- | --- |
| `list_unstructured_data_servers` | read | List registered NAS/unstructured-data sources, or - with `id` - one server's full record |
| `list_vmware_hosts` | read | List the vSphere servers VBR manages: vCenter Servers and standalone ESXi hosts |
| `browse_inventory` | read | Browse the virtualization inventory - managed servers, or one server's hosts, resource pools, datastores, folders and networks - the source of every restore placement |

### Protection groups

| Tool | | What it does |
| --- | --- | --- |
| `list_protection_groups` | read | List agent protection groups: the policies that discover and manage Veeam Agent installs across computers |
| `get_protection_group_entities` | read | List the computers/containers one protection group discovered, with their agent/driver install state |

### Malware detection

| Tool | | What it does |
| --- | --- | --- |
| `list_malware_events` | read | List malware-detection events, newest detection first by default |
| `get_yara_rules` | read | List the YARA rules configured for malware-detection scanning |
| `start_malware_scan` | write | Start a malware scan of a workload's backup |

### Licensing

| Tool | | What it does |
| --- | --- | --- |
| `get_license_status` | read | Return the installed license's status plus its per-workload breakdown for every active model |
| `create_license_report` | read | Generate VBR's own point-in-time license usage report. Read-only despite the `POST` |
| `revoke_license` | **destructive** | Revoke one consumed license unit, freeing it back to the pool |

### Configuration backup

| Tool | | What it does |
| --- | --- | --- |
| `get_config_backup_status` | read | Return the VBR configuration-backup posture: enabled, schedule, retention, encryption, target repository |
| `start_config_backup` | write | Start a VBR configuration backup now, using its configured settings |

### General options

| Tool | | What it does |
| --- | --- | --- |
| `get_general_options` | read | Return VBR's global options: email settings, disk-space/support/update notification thresholds, SIEM forwarding |

### Server info

| Tool | | What it does |
| --- | --- | --- |
| `get_server_status` | read | Return the VBR server's version/build, DB engine/version, registration status/expiry, and server time/timezone |

### Generic REST API reads

| Tool | | What it does |
| --- | --- | --- |
| `api_get` | read | Send any GET request to the VBR REST API, for data no dedicated tool returns |
| `api_post_query` | read | Send a read-only POST query (inventory browser, ACLs, restore point network info). Any other POST is refused |
## Configuration reference

Every setting is read from the environment (or `.env`). All of them have defaults except the
VBR credentials.

| Variable | Default | Description |
| --- | --- | --- |
| `VBR_BASE_URL` | `https://localhost:9419` | Base URL of the VBR REST API server |
| `VBR_USERNAME` | — | VBR REST API username used for the password grant |
| `VBR_PASSWORD` | — | VBR REST API password used for the password grant |
| `VBR_VERIFY_TLS` | `True` | Verify the VBR server's TLS certificate. `False` for self-signed lab certificates only |
| `VBR_API_VERSION` | `1.3-rev2` | Sent as the `x-api-version` header |
| `VBR_REQUEST_TIMEOUT_SEC` | `30.0` | Per-request timeout for calls to VBR |

A self-signed or private-CA certificate can stay verified: point `SSL_CERT_FILE` (also read
from `.env`) at a PEM file with the server's certificate or its CA. vbr-mcp checks certificates
against its own CA bundle (certifi), not the operating system's store, so installing the CA
there does not help.

`.env.example` is generated from the settings classes, so it cannot drift from the code.
Regenerate it with `make env-example` after changing `src/vbr_mcp/settings.py`.

## Development

```
make install            # uv sync --all-groups
make quality            # ruff format, ruff check --fix, then typecheck
make quality-check      # the same checks without rewriting files (what CI runs)
make typecheck          # ty
make test               # pytest with coverage
make check-env-example  # fail if .env.example drifted from the settings classes
```

Tools that send structured request bodies take Pydantic models from `src/vbr_mcp/models/`, so
each tool publishes VBR's real body schema to MCP clients instead of a free-form object. The
models mirror the VBR REST API 1.3-rev2 schemas of the same name and are maintained by hand,
one module per tool plus `shared.py` for parts several tools use - add or adjust one when a
tool needs another body part.

The models check a request's shape; `src/vbr_mcp/vsphere_placement.py` and the restore tools
check its meaning before anything is sent. They reject what VBR was seen to refuse or silently
ignore when tested against VBR 13.1: a placement object of the wrong type, objects from different
managed servers, a standalone ESXi host's `ha-host` row, an Instant Recovery folder that is a
`Datacenter`, restore disk names that are not the restore point's own, and a customized VM restore
without a network mapping for a VM that has networks.

The test suite mocks the VBR REST API at the transport layer with `pytest-httpx` and drives
the tools through the real MCP protocol with an in-process `fastmcp.Client`, so no VBR server
is needed to run it.

Every source file carries the Veeam copyright header, enforced by ruff's `CPY001` rule.

## Limitations

- **One VBR server per process.** The client is built at import time from the environment, so
  the server cannot be re-pointed at a different VBR host at runtime, and one process cannot
  serve several hosts.
- **Configuration is environment-only.** There are no CLI flags and no configuration file.
- **The destructive/read-only split is advisory.** It is published as MCP tool annotations and
  server instructions for clients to act on; the server does not gate or confirm calls itself.
- **No logging of its own.** All you get is FastMCP's, on stderr: its startup banner, a line
  for every failed tool call (`Error calling tool '<name>'`, without the error's text, which
  goes to the client; a traceback for an unexpected error, a warning for invalid arguments).
  `FASTMCP_LOG_LEVEL=CRITICAL` silences the tool-call lines.

## Security

See [SECURITY.md](SECURITY.md) for the security model and for how to report a vulnerability.
Please do not report security issues through public GitHub issues.

## License

[MIT](LICENSE) © Veeam Software
