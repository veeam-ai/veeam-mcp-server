/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { z } from 'zod';
import { answerQuestion } from './tools';

// Create an MCP server
const server = new McpServer({
    name: 'Veeam Intelligence',
    version: '1.0.0',
});

const productName = process.env.PRODUCT_NAME?.trim() || 'Veeam product';
const toolDescription =
    `Use this tool whenever a request involves Veeam operational knowledge—health checks, alert triage, remediation steps, configuration advice, integrations, or runbooks—for ${productName}. ` +
    'It returns authoritative Veeam product guidance backed by internal telemetry and documented procedures. ' +
    'Preserve the user wording; forward questions verbatim so intent is not altered. ' +
    'Responses arrive as JSON with top-level "message" and "artifacts" fields; when an artifact has type "dataframe" treat it as tabular output and render it as a table.';

server.registerTool(
    'veeam-question-answering',
    {
        title: 'Veeam Intelligence Question Answering',
        description: toolDescription,
        inputSchema: {
            question: z.string().describe('Question to ask Veeam Intelligence'),
        },
        outputSchema: {
            message: z.string().describe('Answer from Veeam Intelligence'),
            artifacts: z.array(z.any()).describe('Artifacts from Veeam Intelligence'),
        },
    },
    async ({ question }) => {
        const answer = await answerQuestion(question);

        return {
            content: [{ type: 'text', text: JSON.stringify(answer) }],
            structuredContent: answer,
        };
    },
);

// Start receiving messages on stdin and sending messages on stdout
const transport = new StdioServerTransport();
await server.connect(transport);
