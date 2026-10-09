/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { describe, it, expect, beforeEach, jest } from '@jest/globals';
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { InMemoryTransport } from '@modelcontextprotocol/sdk/inMemory.js';
import { ElicitRequestSchema } from '@modelcontextprotocol/sdk/types.js';

// `@/config/settings` validates process.env at import time, so env is set before the first dynamic
// import below. The URL is never contacted: both network-touching modules are mocked.
process.env.PRODUCT_NAME = 'vbr';
process.env.WEB_URL = 'https://vbr.example.test:9419';
process.env.ADMIN_USERNAME = 'x';
process.env.ADMIN_PASSWORD = 'x';

let currentMode = 'Advanced';
let initializeError: Error | undefined;
let nextOutcome: unknown;

const getServiceInfo = jest.fn();
const chatServiceCtor = jest.fn();
const chatDisconnect = jest.fn();

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
            return nextOutcome;
        }
        getEffectiveMode() {
            return currentMode;
        }
        whenSettled() {
            return new Promise(() => {});
        }
        resolveConfirmation() {
            return true;
        }
        async resume() {
            return { kind: 'complete', message: 'done', artifacts: [], actions: [] };
        }
        disconnect() {
            chatDisconnect();
        }
    },
}));

const { registerTools, TOOL_NAMES, BASE_MODE_WARNING } = await import('@/mcp/registerTools');
const { createMcpSession } = await import('@/mcp/session');
const { PendingActionRegistry } = await import('@/tools');

async function connect(server: McpServer, capabilities: Record<string, unknown> = {}): Promise<Client> {
    const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
    await server.connect(serverTransport);

    const client = new Client({ name: 'test-client', version: '0.0.0' }, { capabilities });
    await client.connect(clientTransport);
    return client;
}

async function connectedClient(): Promise<Client> {
    const server = new McpServer({ name: 'test-server', version: '0.0.0' });
    registerTools(server, new PendingActionRegistry());
    return connect(server);
}

function awaitingConfirmation(id: string) {
    return {
        kind: 'awaiting_confirmation',
        request: {
            id,
            invocationId: `inv-${id}`,
            kind: 'action',
            title: 'Start this backup job?',
            description: 'Starts a backup job on the Veeam server.',
            createdAt: Date.now(),
            expiresAt: Date.now() + 60_000,
        },
        message: '',
        artifacts: [],
        actions: [],
    };
}

function errorText(result: Awaited<ReturnType<Client['callTool']>>): string {
    return (result.content as Array<{ type: string; text: string }>).map((c) => c.text).join('\n');
}

describe('registerTools', () => {
    beforeEach(() => {
        currentMode = 'Advanced';
        initializeError = undefined;
        nextOutcome = { kind: 'complete', message: 'answer', artifacts: [], actions: [] };
        getServiceInfo.mockClear();
        chatServiceCtor.mockClear();
        chatDisconnect.mockClear();
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
        expect(errorText(result)).toContain('Error occurred: connect ECONNREFUSED');
    });

    it('sends the confirmation prompt on the tool call it belongs to, so HTTP clients without a standalone stream receive it', async () => {
        currentMode = 'AdvancedWithActions';
        nextOutcome = awaitingConfirmation('a1');
        const server = new McpServer({ name: 'test-server', version: '0.0.0' });
        registerTools(server, new PendingActionRegistry());
        const elicitInput = jest.spyOn(server.server, 'elicitInput');
        const client = await connect(server, { elicitation: { form: {} } });
        client.setRequestHandler(ElicitRequestSchema, async () => ({ action: 'accept', content: {} }));

        const result = await client.callTool({ name: TOOL_NAMES.answer, arguments: { question: 'start the job' } });

        expect(result.structuredContent).toMatchObject({ message: 'done' });
        expect(elicitInput).toHaveBeenCalledTimes(1);
        expect(elicitInput.mock.calls[0][1]?.relatedRequestId).toEqual(expect.anything());
    });

    it('answers list-pending-actions with an empty list when nothing is parked', async () => {
        const client = await connectedClient();

        const result = await client.callTool({ name: TOOL_NAMES.listPending, arguments: {} });

        expect(result.structuredContent).toEqual({ pending_actions: [] });
    });
});

describe('createMcpSession', () => {
    beforeEach(() => {
        currentMode = 'AdvancedWithActions';
        initializeError = undefined;
        chatDisconnect.mockClear();
    });

    it('keeps actions parked in one session invisible and unconfirmable from another', async () => {
        const first = createMcpSession();
        const second = createMcpSession();
        const firstClient = await connect(first.server);
        const secondClient = await connect(second.server);

        nextOutcome = awaitingConfirmation('a1');
        const asked = await firstClient.callTool({ name: TOOL_NAMES.answer, arguments: { question: 'start the job' } });
        expect((asked.structuredContent as { pending_action?: { action_id: string } }).pending_action?.action_id).toBe('a1');

        const foreignList = await secondClient.callTool({ name: TOOL_NAMES.listPending, arguments: {} });
        expect(foreignList.structuredContent).toEqual({ pending_actions: [] });

        const foreignConfirm = await secondClient.callTool({ name: TOOL_NAMES.confirm, arguments: { action_id: 'a1', approve: true } });
        expect(foreignConfirm.isError).toBe(true);
        expect(errorText(foreignConfirm)).toContain('Unknown or expired action id "a1"');

        const ownList = await firstClient.callTool({ name: TOOL_NAMES.listPending, arguments: {} });
        expect((ownList.structuredContent as { pending_actions: Array<{ action_id: string }> }).pending_actions).toEqual([
            expect.objectContaining({ action_id: 'a1' }),
        ]);

        await first.close();
        await second.close();
    });

    it('disconnects every parked Veeam Intelligence turn when the session closes', async () => {
        const session = createMcpSession();
        const client = await connect(session.server);

        nextOutcome = awaitingConfirmation('a1');
        await client.callTool({ name: TOOL_NAMES.answer, arguments: { question: 'start the job' } });
        expect(chatDisconnect).not.toHaveBeenCalled();

        await session.close();

        expect(chatDisconnect).toHaveBeenCalledTimes(1);
    });
});
