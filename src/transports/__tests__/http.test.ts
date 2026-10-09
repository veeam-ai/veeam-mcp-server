/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { describe, it, expect, beforeAll, beforeEach, afterEach, jest } from '@jest/globals';
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { ElicitRequestSchema } from '@modelcontextprotocol/sdk/types.js';
import { z } from 'zod';
import type { McpSession } from '@/mcp/session';
import type { HttpServerOptions, RunningHttpServer } from '../http';

// `@/config/settings` validates process.env at import time, so env is set before the dynamic import.
process.env.PRODUCT_NAME = 'vbr';
process.env.WEB_URL = 'https://vbr.example.test:9419';
process.env.ADMIN_USERNAME = 'x';
process.env.ADMIN_PASSWORD = 'x';

const TOKEN = 'test-token-0123456789abcdefghijklmnopqrstuvwxyz';

let startHttpServer: (options: HttpServerOptions) => Promise<RunningHttpServer>;

beforeAll(async () => {
    ({ startHttpServer } = await import('../http'));
});

function testSession(onClose: () => void): McpSession {
    const server = new McpServer({ name: 'test-server', version: '0.0.0' });

    server.registerTool('echo', { inputSchema: { text: z.string() } }, async ({ text }) => ({
        content: [{ type: 'text', text }],
    }));

    server.registerTool('confirm', { inputSchema: {} }, async (_args, extra) => {
        const answer = await server.server.elicitInput(
            { mode: 'form', message: 'Start the job?', requestedSchema: { type: 'object', properties: {} } },
            { relatedRequestId: extra.requestId },
        );
        return { content: [{ type: 'text', text: answer.action }] };
    });

    return {
        server,
        async close() {
            onClose();
            await server.close();
        },
    };
}

const initializeBody = {
    jsonrpc: '2.0',
    id: 1,
    method: 'initialize',
    params: { protocolVersion: '2025-06-18', capabilities: {}, clientInfo: { name: 'raw', version: '0' } },
};

const mcpHeaders = { 'Content-Type': 'application/json', Accept: 'application/json, text/event-stream' };

describe('startHttpServer', () => {
    let running: RunningHttpServer | undefined;
    let closedSessions: number;
    let clients: Client[];
    let stderr: jest.SpiedFunction<typeof process.stderr.write>;

    async function start(overrides: Partial<HttpServerOptions> = {}): Promise<RunningHttpServer> {
        running = await startHttpServer({
            host: '127.0.0.1',
            port: 0,
            createSession: () => testSession(() => (closedSessions += 1)),
            authToken: TOKEN,
            allowedHosts: ['localhost', '127.0.0.1', '::1'],
            maxSessions: 10,
            sessionIdleTimeoutMs: 60_000,
            ...overrides,
        });
        return running;
    }

    async function connectClient(token: string = TOKEN, capabilities: Record<string, unknown> = {}): Promise<Client> {
        const transport = new StreamableHTTPClientTransport(new URL(running!.url), {
            requestInit: { headers: { Authorization: `Bearer ${token}` } },
        });
        const client = new Client({ name: 'test-client', version: '0.0.0' }, { capabilities });
        await client.connect(transport);
        clients.push(client);
        return client;
    }

    function sessionIdOf(client: Client): string | undefined {
        return (client.transport as StreamableHTTPClientTransport).sessionId;
    }

    async function waitFor(condition: () => boolean, timeoutMs = 2_000): Promise<void> {
        const deadline = Date.now() + timeoutMs;
        while (!condition()) {
            if (Date.now() > deadline) {
                throw new Error('condition not met in time');
            }
            await new Promise((resolve) => setTimeout(resolve, 20));
        }
    }

    beforeEach(() => {
        closedSessions = 0;
        clients = [];
        stderr = jest.spyOn(process.stderr, 'write').mockImplementation(() => true);
    });

    afterEach(async () => {
        await Promise.all(clients.map((client) => client.close().catch(() => {})));
        await running?.close();
        running = undefined;
        stderr.mockRestore();
    });

    it('serves tool calls to an authenticated MCP client over Streamable HTTP', async () => {
        await start();
        const client = await connectClient();

        const { tools } = await client.listTools();
        const result = await client.callTool({ name: 'echo', arguments: { text: 'hello' } });

        expect(tools.map((tool) => tool.name).sort()).toEqual(['confirm', 'echo']);
        expect(result.content).toEqual([{ type: 'text', text: 'hello' }]);
        expect(running!.url).toMatch(/^http:\/\/127\.0\.0\.1:\d+\/mcp$/);
    });

    it('relays elicitation to the client inside the tool call, as the action confirmation flow needs', async () => {
        await start();
        const client = await connectClient(TOKEN, { elicitation: { form: {} } });
        client.setRequestHandler(ElicitRequestSchema, async (request) => {
            expect(request.params.message).toBe('Start the job?');
            return { action: 'accept', content: {} };
        });

        const result = await client.callTool({ name: 'confirm', arguments: {} });

        expect(result.content).toEqual([{ type: 'text', text: 'accept' }]);
    });

    it('rejects a request without the bearer token before any session is created', async () => {
        await start();

        const response = await fetch(running!.url, { method: 'POST', headers: mcpHeaders, body: JSON.stringify(initializeBody) });

        expect(response.status).toBe(401);
        expect(response.headers.get('www-authenticate')).toBe('Bearer');
        expect(running!.sessionCount).toBe(0);
    });

    it('rejects a wrong bearer token', async () => {
        await start();

        await expect(connectClient('wrong-token')).rejects.toThrow();
        expect(running!.sessionCount).toBe(0);
    });

    it('accepts any caller when no token is configured', async () => {
        await start({ authToken: undefined });

        const client = await connectClient('ignored');

        expect(sessionIdOf(client)).toBeDefined();
    });

    it('rejects a Host header outside the allowed list, which blocks DNS rebinding', async () => {
        await start({ authToken: undefined, allowedHosts: ['mcp.example.test'] });

        const response = await fetch(running!.url, { method: 'POST', headers: mcpHeaders, body: JSON.stringify(initializeBody) });

        expect(response.status).toBe(403);
    });

    it('rejects a browser Origin outside the allowed list', async () => {
        await start();

        const response = await fetch(running!.url, {
            method: 'POST',
            headers: { ...mcpHeaders, Authorization: `Bearer ${TOKEN}`, Origin: 'https://evil.example.test' },
            body: JSON.stringify(initializeBody),
        });

        expect(response.status).toBe(403);
    });

    it('accepts any Host when no allowed list is configured', async () => {
        await start({ allowedHosts: undefined });

        const client = await connectClient();

        expect(sessionIdOf(client)).toBeDefined();
    });

    it('gives each client its own session', async () => {
        await start();

        const first = await connectClient();
        const second = await connectClient();

        expect(sessionIdOf(first)).toBeDefined();
        expect(sessionIdOf(first)).not.toBe(sessionIdOf(second));
        expect(running!.sessionCount).toBe(2);
    });

    it('closes the session when the client terminates it', async () => {
        await start();
        const client = await connectClient();

        await (client.transport as StreamableHTTPClientTransport).terminateSession();

        await waitFor(() => running!.sessionCount === 0);
        expect(closedSessions).toBe(1);
    });

    it('answers 404 for an unknown session id so the client re-initializes', async () => {
        await start();

        const response = await fetch(running!.url, {
            method: 'POST',
            headers: { ...mcpHeaders, Authorization: `Bearer ${TOKEN}`, 'Mcp-Session-Id': 'missing' },
            body: JSON.stringify({ jsonrpc: '2.0', id: 2, method: 'tools/list' }),
        });

        expect(response.status).toBe(404);
    });

    it('refuses a non-initialize request that carries no session id', async () => {
        await start();

        const response = await fetch(running!.url, {
            method: 'POST',
            headers: { ...mcpHeaders, Authorization: `Bearer ${TOKEN}` },
            body: JSON.stringify({ jsonrpc: '2.0', id: 2, method: 'tools/list' }),
        });

        expect(response.status).toBe(400);
        expect(running!.sessionCount).toBe(0);
    });

    it('reports malformed JSON as a JSON-RPC parse error', async () => {
        await start();

        const response = await fetch(running!.url, {
            method: 'POST',
            headers: { ...mcpHeaders, Authorization: `Bearer ${TOKEN}` },
            body: '{not json',
        });

        expect(response.status).toBe(400);
        expect(await response.json()).toMatchObject({ error: { code: -32700 } });
    });

    it('refuses an oversized request body', async () => {
        await start();

        const response = await fetch(running!.url, {
            method: 'POST',
            headers: { ...mcpHeaders, Authorization: `Bearer ${TOKEN}` },
            body: JSON.stringify({ padding: 'x'.repeat(5 * 1024 * 1024) }),
        });

        expect(response.status).toBe(413);
    });

    it('refuses new sessions beyond the configured limit', async () => {
        await start({ maxSessions: 1 });
        await connectClient();

        await expect(connectClient()).rejects.toThrow();
        expect(running!.sessionCount).toBe(1);
    });

    it('closes a session that stays idle past the timeout', async () => {
        await start({ sessionIdleTimeoutMs: 200 });
        await connectClient();
        expect(running!.sessionCount).toBe(1);

        await waitFor(() => running!.sessionCount === 0);
        expect(closedSessions).toBe(1);
    });

    it('closes every session on shutdown', async () => {
        await start();
        await connectClient();
        await connectClient();

        await running!.close();
        running = undefined;

        expect(closedSessions).toBe(2);
    });

    it('answers the health probe without authentication', async () => {
        await start();

        const response = await fetch(new URL('/healthz', running!.url));

        expect(response.status).toBe(200);
        expect(await response.json()).toEqual({ status: 'ok' });
    });

    it('answers 404 outside the MCP and health paths', async () => {
        await start();

        const response = await fetch(new URL('/other', running!.url), { headers: { Authorization: `Bearer ${TOKEN}` } });

        expect(response.status).toBe(404);
    });
});
