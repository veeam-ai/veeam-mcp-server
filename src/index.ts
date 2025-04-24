/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { McpServer, ResourceTemplate } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { config } from 'dotenv';
import { answer_question } from './tool_main.js';

// Load environment variables from .env file
config();


// Create an MCP server
const server = new McpServer({
  name: "Veeam Intelligence",
  version: "1.0.0"
});

server.tool(
  "veeam_intelligence",
  "Ask Veeam Intelligence chat bot to answer any Veeam related question.",
  { veeam_question: z.string() },
  async ({ veeam_question }) => ({
    content: [{ type: "text", text: await answer_question(veeam_question) }]
  })
);

// Start receiving messages on stdin and sending messages on stdout
const transport = new StdioServerTransport();
await server.connect(transport);