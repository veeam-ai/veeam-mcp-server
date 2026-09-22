/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { describe, it, expect, beforeEach, jest } from '@jest/globals';
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { InMemoryTransport } from '@modelcontextprotocol/sdk/inMemory.js';

// `@/config/settings` validates process.env at import time, so env is set before the first dynamic
// import below. The URL is never contacted: both network-touching modules are mocked.
process.env.PRODUCT_NAME = 'vbr';
process.env.WEB_URL = 'https://vbr.example.test:9419';
process.env.ADMIN_USERNAME = 'x';
process.env.ADMIN_PASSWORD = 'x';

let currentMode = 'Advanced';
let initializeError: Error | undefined;

const getServiceInfo = jest.fn();
const chatServiceCtor = jest.fn();

jest.unstable_mockModule('@/product/ProductClientFactory', () => ({
    createProductRestClient: () => ({
        getServiceInfo,
        authenticateChatService: jest.fn(),
        getToolCallData: jest.fn(),
    }),
}));

jest.unstable_mockModule('@/services/chatService', () => ({
    ChatService: class {
        constructor(client: unknown) {
            chatServiceCtor(client);
        }
        async initialize() {
            if (initializeError) {
                throw initializeError;
            }
        }
        async sendMessage() {
            return { kind: 'complete', message: 'answer', artifacts: [], actions: [] };
        }
        getEffectiveMode() {
            return currentMode;
        }
        disconnect() {}
    },
}));

const { registerTools, TOOL_NAMES, BASE_MODE_WARNING } = await import('@/mcp/registerTools');

async function connectedClient(): Promise<Client> {
    const server = new McpServer({ name: 'test-server', version: '0.0.0' });
    registerTools(server);

    const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
    await server.connect(serverTransport);

    const client = new Client({ name: 'test-client', version: '0.0.0' });
    await client.connect(clientTransport);
    return client;
}

describe('registerTools', () => {
    beforeEach(() => {
        currentMode = 'Advanced';
        initializeError = undefined;
        getServiceInfo.mockClear();
        chatServiceCtor.mockClear();
    });

    it('registers every tool without contacting the Veeam product', async () => {
        const client = await connectedClient();

        const { tools } = await client.listTools();

        expect(tools.map((t) => t.name).sort()).toEqual(Object.values(TOOL_NAMES).sort());
        expect(getServiceInfo).not.toHaveBeenCalled();
        expect(chatServiceCtor).not.toHaveBeenCalled();
    });

    it('adds the Base-mode warning when the product reports Base mode on this call', async () => {
        currentMode = 'Base';
        const client = await connectedClient();

        const result = await client.callTool({ name: TOOL_NAMES.answer, arguments: { question: 'q' } });

        expect(result.isError).toBeFalsy();
        expect(result.structuredContent).toEqual({ message: 'answer', artifacts: [], actions: [], warning: BASE_MODE_WARNING });
    });

    it('omits the warning and never leaks the mode when the product reports Advanced mode', async () => {
        currentMode = 'Advanced';
        const client = await connectedClient();

        const result = await client.callTool({ name: TOOL_NAMES.answer, arguments: { question: 'q' } });

        expect(result.isError).toBeFalsy();
        expect(result.structuredContent).toEqual({ message: 'answer', artifacts: [], actions: [] });
    });

    it('reports an unreachable product as a normal tool error at call time', async () => {
        initializeError = new Error('connect ECONNREFUSED');
        const client = await connectedClient();

        const result = await client.callTool({ name: TOOL_NAMES.answer, arguments: { question: 'q' } });

        expect(result.isError).toBe(true);
        const text = (result.content as Array<{ type: string; text: string }>).map((c) => c.text).join('\n');
        expect(text).toContain('Error occurred: connect ECONNREFUSED');
    });

    it('answers list-pending-actions with an empty list when nothing is parked', async () => {
        const client = await connectedClient();

        const result = await client.callTool({ name: TOOL_NAMES.listPending, arguments: {} });

        expect(result.structuredContent).toEqual({ pending_actions: [] });
    });
});
