/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { registerTools } from './mcp/registerTools';
import { log } from './utils/logger';

// Create an MCP server
const server = new McpServer({
    name: 'Veeam Intelligence',
    version: '1.0.0',
});

// Tool registration is static: the Veeam product is contacted only when a tool is called.
registerTools(server);

// Start receiving messages on stdin and sending messages on stdout
const transport = new StdioServerTransport();
await server.connect(transport);
log.info('MCP server started; the chatbot mode is read from the Veeam product on every request');
