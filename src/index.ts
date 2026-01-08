/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { z } from 'zod';
import { answerQuestion } from './tools';
import { createTool } from './mcp/toolFactory';

// Create an MCP server
const server = new McpServer({
    name: 'Veeam Intelligence',
    version: '1.0.0',
});

const toolConfig = await createTool();

server.registerTool(
    'veeam-question-answering',
    {
        title: toolConfig.title,
        description: toolConfig.description,
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
