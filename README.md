# Veeam Intelligence MCP Server

This project provides a Veeam Intelligence MCP server that integrates with any MCP-compatible client (such as Claude Desktop, VS Code, and others) for enhanced Veeam Backup & Replication, Veeam One, and VSPC monitoring and management capabilities.

## Roadmap & Future Releases
- Veeam Backup and Replication (coming soon)
- VDC (coming soon)

## Prerequisites

- Docker installed on your system
- Veeam One server with a valid license (Community edition is not supported).


## Setup

1. Clone the repository:
  ```bash
  git clone <repository-url>
  cd veeam-mcp
  ```

2. Gather the credentials and connection details that will be injected when launching the Docker container (no `.env` file is used anymore):
  - `PRODUCT_NAME`: The name of the Veeam product `[vbr | vone | vspc]`
  - `WEB_URL`: URL of your Veeam One server, for example https://veeamone-srv:1239/
  - `ADMIN_USERNAME`: Veeam One administrator username, for example domain\\username
  - `ADMIN_PASSWORD`: Administrator password
  - Optional hardening flags such as `NODE_ENV`, `NODE_TLS_REJECT_UNAUTHORIZED`, etc.

  You will paste these values directly into the VS Code or Claude Desktop MCP configuration so they are provided to the container via `docker run -e VARIABLE_NAME` plus an `env` block that holds the actual secrets.

## Build

Before using the Veeam Intelligence MCP server, you need to build the Docker image:

```bash
# Option 1: Using make
make build

# Option 2: Using docker directly
docker build -t veeam-mcp .
```

## Clean

To remove any previously built Docker images:

```bash
# Option 1: Using make
make clean

# Option 2: Using docker directly
docker rmi veeam-mcp || true 
```

## Security Warning

⚠️ **Important Security Notice**: Your Veeam One administrator credentials now live inside your local MCP configuration (VS Code or Claude Desktop). For security reasons:

- Never commit or share your MCP configuration files if they contain secrets
- Never push the built Docker image to a public registry
- Always build the image locally on the machine where it will be used

## Usage with Claude Desktop

1. Add the Veeam Intelligence MCP server to your Claude Desktop configuration:
   Edit `claude_desktop_config.json` and add the following configuration:

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
           "-e", "NODE_TLS_REJECT_UNAUTHORIZED",
           "veeam-mcp"
         ],
         "env": {
           "PRODUCT_NAME": "vone",
           "WEB_URL": "https://veeamone-srv:1239/",
           "ADMIN_USERNAME": "username",
           "ADMIN_PASSWORD": "secret",
           "NODE_TLS_REJECT_UNAUTHORIZED": "0"
         }
       }
     }
   }
   ```

   Replace the placeholder values inside the `env` block with your own secrets.

2. Restart Claude Desktop to apply the changes.

## Usage with VS Code

To use this MCP server with GitHub Copilot in VS Code, you need to create a `.vscode/mcp.json` file in your workspace:

1. Create a `.vscode` directory in your workspace if it doesn't exist:
   ```bash
   mkdir -p .vscode
   ```

2. Create a `.vscode/mcp.json` file with the following configuration:

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
           "-e", "NODE_TLS_REJECT_UNAUTHORIZED",
           "veeam-mcp"
         ],
         "env": {
           "PRODUCT_NAME": "vone",
           "WEB_URL": "https://veeamone-srv:1239/",
           "ADMIN_USERNAME": "username",
           "ADMIN_PASSWORD": "super-secret",
           "NODE_TLS_REJECT_UNAUTHORIZED": "0"
         }
       }
     }
   }
   ```

   Replace the placeholder values within `env` with your actual credentials.

3. Restart VS Code or reload the window for the changes to take effect.

4. The Veeam Intelligence MCP server will now be available in GitHub Copilot chat within VS Code.
