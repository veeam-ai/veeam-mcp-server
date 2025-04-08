# Veeam Intelligence MCP Server

This project provides a Veeam Intelligence MCP server that integrates with Claude Desktop for enhanced Veeam One monitoring and management capabilities.

## Prerequisites

- Docker installed on your system
- Veeam One server with a valid license (Community edition is not supported).

## Setup

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd veeam-mcp
   ```

2. Configure environment variables:
   ```bash
   cp .env.example .env
   ```
   Edit the `.env` file and fill in your Veeam One server details:
   - `VONE_WEB_URL`: URL of your Veeam One server, for example https://veeamone-srv:1239/
   - `VONE_ADMIN_USERNAME`: Veeam One administrator username, example: domain\\username
   - `VONE_ADMIN_PASSWORD`: Administrator password

## Build

Before using the Veeam Intelligence MCP server, you need to build the Docker image:

```bash
# Option 1: Using make
make build

# Option 2: Using docker directly
docker build -t veeam-mcp .
```

## Security Warning

⚠️ **Important Security Notice**: The Docker image built from this repository will contain the `.env` file with your Veeam One administrator credentials. For security reasons:

- Never push the built Docker image to a public registry
- Never share the Docker image with untrusted parties
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
           "veeam-mcp"
         ]
       }
     }
   }
   ```

2. Restart Claude Desktop to apply the changes.