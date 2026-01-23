# Veeam Intelligence MCP Server

This project provides a Veeam Intelligence MCP server that integrates with any MCP-compatible client (such as Claude Desktop, VS Code, and others) for enhanced Veeam Backup & Replication, Veeam One, and VSPC monitoring and management capabilities.

## Prerequisites

- Either Docker or Node.js 24 installed on your system
- One of Veeam products installed with an active non-community license
  - Veeam Backup and Replication (vbr)
  - Veeam One (vone)
  - Veeam Service Provider Console (vspc)

## Setup

### 1. Clone the repository:
  ```bash
  git clone <repository-url>
  cd veeam-mcp-server
  ```

### 2. Gather Credentials and Connection Details

Collect the following credentials and connection details. These values will be injected when launching the Docker container:

- `PRODUCT_NAME`: The name of the Veeam product (`vbr | vone | vspc`)
- `WEB_URL`: The URL of your Veeam server 
```
WEB_URL Examples
Veeam Backup and Replication: `https://vbr-srv.local/`, default port 443
Veeam One: `https://veeamone-srv.local:1239/`
Veeam Service Provider Console: `https://vspc-srv.local:1280/`
```
- `ADMIN_USERNAME`: The Veeam product administrator username (for example, `.\\administrator`)
- `ADMIN_PASSWORD`: The administrator password
- `ACCEPT_SELF_SIGNED_CERT`: Set this to `true` if the Veeam product uses self-signed SSL certificate (for example, `ACCEPT_SELF_SIGNED_CERT=true`)

Paste these values directly into the VS Code or Claude Desktop MCP configuration so they are passed to the MCP process as environment variables.

### Option 1: Run using Docker
#### 1. Build Docker image
Before using the Veeam Intelligence MCP server, you need to build the Docker image:

```bash
# Option 1: Using make
make build

# Option 2: Using docker directly
docker build -t veeam-intelligence-mcp-server .
```

#### 2. Setup MCP client

Setup your MCP client to start mcp server using STDIO transport.
```
docker run -i --rm -e PRODUCT_NAME=vone -e WEB_URL=https://vone-server.local:1239/ -e ADMIN_USERNAME=.\\administrator -e ADMIN_PASSWORD=password -e ACCEPT_SELF_SIGNED_CERT=true veeam-intelligence-mcp-server
```

### Option 2: Using npm
Setup your MCP client to start mcp server using STDIO transport.

#### Store secrets in .env file
1. In MCP repository root, copy .env.example file to .env and populate values
2. Configure MCP client to run server as follows
```
npm start --prefix ~/path/to/mcp/server
```

#### Alternatively, pass secrets in commandline
```
# On Mac/Linux
PRODUCT_NAME=vone WEB_URL=https://vone-server.local:1239/ ADMIN_USERNAME=.\\administrator ADMIN_PASSWORD=password ACCEPT_SELF_SIGNED_CERT=true npm start --prefix ~/path/to/mcp/server

# On Windows
set PRODUCT_NAME=vone && set WEB_URL=https://vone-server.local:1239/ && set ADMIN_USERNAME=.\\administrator && set ADMIN_PASSWORD=password && set ACCEPT_SELF_SIGNED_CERT=true && npm start --prefix c:\\path\\to\\mcp\\server
```

# Example usage with popular MCP clients
## Claude Desktop
### Docker

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
     "servers": {
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
