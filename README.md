# Veeam Intelligence MCP Server

This project provides a Veeam Intelligence MCP server that integrates with any MCP-compatible client (such as Claude Desktop, VS Code, and others) for enhanced Veeam Backup & Replication, Veeam One, and VSPC monitoring and management capabilities.

## Prerequisites

- Either Docker or Node.js 24 installed on your system
- One of Veeam products installed with an active non-community license
  - Veeam One
  - Veeam Backup and Replication
  - Veeam Service Provider Console

## Setup

### 1. Clone the repository:
  ```bash
  git clone <repository-url>
  cd veeam-mcp-server
  ```

### 2. Gather Credentials and Connection Details

Collect the following credentials and connection details. These values will be injected when launching the Docker container:

- `PRODUCT_NAME`: The name of the Veeam product (`vbr | vone | vspc`)
- `WEB_URL`: The URL of your Veeam ONE server (for example, `https://veeamone-srv:1239/`)
- `ADMIN_USERNAME`: The Veeam product administrator username (for example, `.\\administrator`)
- `ADMIN_PASSWORD`: The administrator password
- `ACCEPT_SELF_SIGNED_CERT`: Set this to `true` if the Veeam product SSL certificate is not trusted (for example, `ACCEPT_SELF_SIGNED_CERT=true`)

Paste these values directly into the VS Code or Claude Desktop MCP configuration so they are passed to the container using `docker run -e VARIABLE_NAME`, along with an `env` block that contains the actual secrets.

## Option 1: using Docker
### 1. Build Docker image
Before using the Veeam Intelligence MCP server, you need to build the Docker image:

```bash
# Option 1: Using make
make build

# Option 2: Using docker directly
docker build -t veeam-intelligence-mcp-server .
```

To remove any previously built Docker images:

```bash
# Option 1: Using make
make clean

# Option 2: Using docker directly
docker rmi veeam-intelligence-mcp-server || true 
```

### 2. Start MCP server

Setup your MCP client to start mcp server using STDIO transport.

Example for Docker
```
docker run -i --rm -e PRODUCT_NAME=vone -e WEB_URL=https://vone-server.local:1239/ -e ADMIN_USERNAME=.\\administrator -e ADMIN_PASSWORD=password -e ACCEPT_SELF_SIGNED_CERT=true veeam-intelligence-mcp-server
```

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
           "-e", "ACCEPT_SELF_SIGNED_CERT",
           "veeam-mcp"
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

   Replace the placeholder values within `env` with your actual credentials.

3. Restart VS Code or reload the window for the changes to take effect.

4. The Veeam Intelligence MCP server will now be available in GitHub Copilot chat within VS Code.
