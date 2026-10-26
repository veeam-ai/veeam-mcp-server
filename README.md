# Veeam MCP Servers

This repository hosts Model Context Protocol (MCP) servers for Veeam products. Each server is an independent project with its own toolchain, dependencies, and documentation, and integrates with any MCP-compatible client, such as Claude Desktop, Visual Studio Code, and others.

## Servers

| Server | Directory | Stack | Description |
|---|---|---|---|
| [Veeam Intelligence MCP Server](servers/vi-mcp/README.md) | `servers/vi-mcp` | TypeScript, Node.js 24.22.1+ | Brings Veeam Intelligence to MCP clients for monitoring and management of Veeam Backup & Replication, Veeam ONE, and Veeam Service Provider Console (VSPC). |
| [Veeam Backup & Replication MCP Server](servers/vbr-mcp/README.md) | `servers/vbr-mcp` | Python 3.13, uv | Exposes the Veeam Backup & Replication REST API as MCP tools grouped by resource: jobs, sessions, backups, restore, backup infrastructure, licensing, and more. Some tools change state or can overwrite data, so read its [safety section](servers/vbr-mcp/README.md#safety-and-permissions) first. |

See the README of each server for prerequisites, setup, and client configuration.

## Repository layout

```
servers/
├── vi-mcp/        # Veeam Intelligence MCP Server
└── vbr-mcp/       # Veeam Backup & Replication MCP Server
.github/           # CI workflows
LICENSE
```

## Upgrading from the previous layout

The Veeam Intelligence MCP Server moved from the repository root to `servers/vi-mcp`. If you set it up before this change:

- **npm:** point `--prefix` in your MCP client configuration to `<repository>/servers/vi-mcp` instead of the repository root.
- **`.env` file:** move it from the repository root to `servers/vi-mcp/.env`. The old location is silently ignored.
- **Docker:** rebuild the image from `servers/vi-mcp` (`make build` or `docker build -t veeam-intelligence-mcp-server .` in that directory). The image name is unchanged, so existing MCP client configurations keep working.
- Remove the leftover `node_modules/` and `build/` directories from the repository root.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
