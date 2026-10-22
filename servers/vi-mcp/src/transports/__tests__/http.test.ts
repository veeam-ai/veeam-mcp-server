/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { describe, it, expect, beforeAll, beforeEach, afterEach, jest } from '@jest/globals';
import { AxiosError } from 'axios';
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { ElicitRequestSchema } from '@modelcontextprotocol/sdk/types.js';
import { z } from 'zod';
import type { McpSession } from '@/mcp/session';
import type { ProductCredentials, ProductUserToken } from '@/product/clients/types';
import type { HttpServerOptions, RunningHttpServer } from '../http';

// `@/config/settings` validates process.env at import time, so env is set before the dynamic import.
process.env.PRODUCT_NAME = 'vbr';
process.env.WEB_URL = 'https://vbr.example.test:9419';
process.env.ADMIN_USERNAME = 'x';
process.env.ADMIN_PASSWORD = 'x';

const PASSWORD = 'correct horse: battery staple';

let startHttpServer: typeof import('../http').startHttpServer;
let httpServerOptionsFromSettings: typeof import('../http').httpServerOptionsFromSettings;
let parseSettings: typeof import('@/config/settings').parseSettings;
let parseBasicCredentials: typeof import('@/auth/basicAuth').parseBasicCredentials;
let identityOf: typeof import('@/auth/identity').identityOf;
let productAuthOf: typeof import('@/auth/identity').productAuthOf;

beforeAll(async () => {
    ({ startHttpServer, httpServerOptionsFromSettings } = await import('../http'));
    ({ parseSettings } = await import('@/config/settings'));
    ({ parseBasicCredentials } = await import('@/auth/basicAuth'));
    ({ identityOf, productAuthOf } = await import('@/auth/identity'));
});

let productReachable: boolean;
let productDelayMs: number;
let productStatus: number | undefined;

const requestUserToken = jest.fn(async ({ username, password }: ProductCredentials): Promise<ProductUserToken> => {
    await new Promise((resolve) => setTimeout(resolve, productDelayMs));
    if (!productReachable) {
        throw new AxiosError('connect ECONNREFUSED', 'ECONNREFUSED');
    }
    if (productStatus !== undefined) {
        throw new AxiosError(`Request failed with status code ${productStatus}`, 'ERR_BAD_REQUEST', undefined, undefined, {
            status: productStatus,
        } as never);
    }
    if (password === PASSWORD) {
        return { accessToken: `vbr-${username}`, expiresAt: Date.now() + 900_000 };
    }
    throw new AxiosError('Request failed with status code 400', 'ERR_BAD_REQUEST', undefined, undefined, { status: 400 } as never);
});

function basic(username: string, password: string = PASSWORD): string {
    return `Basic ${Buffer.from(`${username}:${password}`).toString('base64')}`;
}

function testSession(onClose: () => void): McpSession {
    const server = new McpServer({ name: 'test-server', version: '0.0.0' });

    server.registerTool('echo', { inputSchema: { text: z.string() } }, async ({ text }) => ({
        content: [{ type: 'text', text }],
    }));

    server.registerTool('whoami', { inputSchema: {} }, async (_args, extra) => ({
        content: [{ type: 'text', text: identityOf(extra.authInfo)?.username ?? 'nobody' }],
    }));

    server.registerTool('veeam-token', { inputSchema: {} }, async (_args, extra) => {
        const auth = productAuthOf(extra.authInfo);
        return { content: [{ type: 'text', text: auth?.kind === 'token' ? auth.token.accessToken : 'none' }] };
    });

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

function textOf(result: Awaited<ReturnType<Client['callTool']>>): string {
    return (result.content as Array<{ text: string }>)[0].text;
}

describe('parseBasicCredentials', () => {
    it('splits at the first colon, so passwords may contain colons', () => {
        expect(parseBasicCredentials(basic('.\\admin', 'a:b:c'))).toEqual({ username: '.\\admin', password: 'a:b:c' });
    });

    it('rejects other schemes, missing parts and garbage', () => {
        expect(parseBasicCredentials(undefined)).toBeUndefined();
        expect(parseBasicCredentials('Bearer abc')).toBeUndefined();
        expect(parseBasicCredentials(`Basic ${Buffer.from('no-colon').toString('base64')}`)).toBeUndefined();
        expect(parseBasicCredentials(`Basic ${Buffer.from(':pw').toString('base64')}`)).toBeUndefined();
        expect(parseBasicCredentials(`Basic ${Buffer.from('user:').toString('base64')}`)).toBeUndefined();
        expect(parseBasicCredentials('Basic !!!')).toBeUndefined();
    });
});

describe('httpServerOptionsFromSettings', () => {
    const http = { PRODUCT_NAME: 'vbr', WEB_URL: 'https://vbr.example.test', MCP_TRANSPORT: 'http' };

    it('trusts the TLS proxy it is told about, so the login limit is not shared by every user behind it', () => {
        const behindProxy = parseSettings({ ...http, MCP_HTTP_HOST: '0.0.0.0', MCP_HTTP_BEHIND_TLS_PROXY: 'true' });

        expect(httpServerOptionsFromSettings(behindProxy, () => undefined as never).trustProxy).toBe(1);
        expect(httpServerOptionsFromSettings({ ...behindProxy, MCP_HTTP_TRUST_PROXY: 2 }, () => undefined as never).trustProxy).toBe(2);
        expect(httpServerOptionsFromSettings(parseSettings(http), () => undefined as never).trustProxy).toBe(0);
    });
});

describe('startHttpServer with Basic sign-in', () => {
    let running: RunningHttpServer | undefined;
    let closedSessions: number;
    let clients: Client[];
    let stderr: jest.SpiedFunction<typeof process.stderr.write>;

    async function start(overrides: Partial<HttpServerOptions> = {}): Promise<RunningHttpServer> {
        running = await startHttpServer({
            host: '127.0.0.1',
            port: 0,
            createSession: () => testSession(() => (closedSessions += 1)),
            auth: { mode: 'basic', product: { requestUserToken } },
            allowedHosts: ['localhost', '127.0.0.1', '::1'],
            trustProxy: 0,
            maxSessions: 10,
            maxSessionsPerUser: 10,
            sessionIdleTimeoutMs: 60_000,
            ...overrides,
        });
        return running;
    }

    async function connectClient(authorization: string = basic('alice'), capabilities: Record<string, unknown> = {}): Promise<Client> {
        const transport = new StreamableHTTPClientTransport(new URL(running!.url), {
            requestInit: { headers: { Authorization: authorization } },
        });
        const client = new Client({ name: 'test-client', version: '0.0.0' }, { capabilities });
        await client.connect(transport);
        clients.push(client);
        return client;
    }

    async function initialize(headers: Record<string, string>): Promise<Response> {
        return fetch(running!.url, { method: 'POST', headers: { ...mcpHeaders, ...headers }, body: JSON.stringify(initializeBody) });
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
        productReachable = true;
        productDelayMs = 0;
        productStatus = undefined;
        requestUserToken.mockClear();
        stderr = jest.spyOn(process.stderr, 'write').mockImplementation(() => true);
    });

    afterEach(async () => {
        await Promise.all(clients.map((client) => client.close().catch(() => {})));
        await running?.close();
        running = undefined;
        stderr.mockRestore();
    });

    describe('Veeam sign-in', () => {
        it("hands the caller's own Veeam account to the tools", async () => {
            await start();
            const client = await connectClient(basic('alice'));

            const result = await client.callTool({ name: 'whoami', arguments: {} });

            expect(textOf(result)).toBe('alice');
            expect(requestUserToken).toHaveBeenCalledWith({ username: 'alice', password: PASSWORD });
        });

        it('keeps two users apart: each tool call carries the account of whoever made it', async () => {
            await start();
            const alice = await connectClient(basic('alice'));
            const bob = await connectClient(basic('bob'));

            expect(textOf(await alice.callTool({ name: 'whoami', arguments: {} }))).toBe('alice');
            expect(textOf(await bob.callTool({ name: 'whoami', arguments: {} }))).toBe('bob');
        });

        it('asks for Basic credentials before any session is created', async () => {
            await start();

            const response = await initialize({});

            expect(response.status).toBe(401);
            expect(response.headers.get('www-authenticate')).toBe('Basic realm="Veeam Intelligence", charset="UTF-8"');
            expect(running!.sessionCount).toBe(0);
            expect(requestUserToken).not.toHaveBeenCalled();
        });

        it('rejects a wrong Veeam password', async () => {
            await start();

            const response = await initialize({ Authorization: basic('alice', 'wrong') });

            expect(response.status).toBe(401);
            expect(await response.json()).toMatchObject({ error: { message: expect.stringContaining('incorrect') } });
            expect(running!.sessionCount).toBe(0);
        });

        it('says the product is unreachable instead of blaming the password', async () => {
            await start();
            productReachable = false;

            const response = await initialize({ Authorization: basic('alice') });

            expect(response.status).toBe(502);
        });

        it('checks a password with the product once and not on every request', async () => {
            await start();
            const client = await connectClient(basic('alice'));

            await client.callTool({ name: 'echo', arguments: { text: 'one' } });
            await client.callTool({ name: 'echo', arguments: { text: 'two' } });

            expect(requestUserToken).toHaveBeenCalledTimes(1);
        });

        it('hands the tools the Veeam token from the password check, so they do not sign in again', async () => {
            await start();
            const client = await connectClient(basic('alice'));

            const result = await client.callTool({ name: 'veeam-token', arguments: {} });

            expect(textOf(result)).toBe('vbr-alice');
            expect(requestUserToken).toHaveBeenCalledTimes(1);
        });

        it('locks out an address after repeated wrong passwords without asking the product again', async () => {
            await start();

            for (let attempt = 0; attempt < 10; attempt += 1) {
                expect((await initialize({ Authorization: basic('alice', `wrong-${attempt}`) })).status).toBe(401);
            }
            const locked = await initialize({ Authorization: basic('alice') });

            expect(locked.status).toBe(429);
            expect(locked.headers.get('retry-after')).toBe('900');
            expect(requestUserToken).toHaveBeenCalledTimes(10);
        });

        it('does not let parallel guesses past the lockout before the product answers', async () => {
            await start();
            productDelayMs = 100;

            const responses = await Promise.all(
                Array.from({ length: 25 }, (_, attempt) => initialize({ Authorization: basic('alice', `wrong-${attempt}`) })),
            );

            expect(requestUserToken).toHaveBeenCalledTimes(10);
            expect(responses.filter((response) => response.status === 429)).toHaveLength(15);
        });

        it('does not blame the password or count a lockout failure when the product answers with another error', async () => {
            await start();
            productStatus = 404;

            for (let attempt = 0; attempt < 10; attempt += 1) {
                const response = await initialize({ Authorization: basic('alice') });
                expect(response.status).toBe(502);
                expect(await response.json()).toMatchObject({ error: { message: expect.stringContaining('HTTP 404') } });
            }
            productStatus = undefined;

            expect((await initialize({ Authorization: basic('alice') })).status).toBe(200);
        });

        it('still serves a user whose password was already verified when their address gets locked', async () => {
            await start();
            const client = await connectClient(basic('alice'));

            for (let attempt = 0; attempt < 10; attempt += 1) {
                await initialize({ Authorization: basic('mallory', 'wrong') });
            }

            expect((await initialize({ Authorization: basic('mallory') })).status).toBe(429);
            expect(textOf(await client.callTool({ name: 'whoami', arguments: {} }))).toBe('alice');
        });

        it('ignores X-Forwarded-For unless a proxy is trusted, so the lockout cannot be dodged', async () => {
            await start();

            for (let attempt = 0; attempt < 10; attempt += 1) {
                await initialize({ Authorization: basic('alice', 'wrong'), 'X-Forwarded-For': `10.0.0.${attempt}` });
            }

            expect((await initialize({ Authorization: basic('alice'), 'X-Forwarded-For': '10.0.0.99' })).status).toBe(429);
        });

        it('counts failures per client behind a trusted proxy', async () => {
            await start({ trustProxy: 1 });

            for (let attempt = 0; attempt < 10; attempt += 1) {
                await initialize({ Authorization: basic('alice', 'wrong'), 'X-Forwarded-For': '10.0.0.1' });
            }

            expect((await initialize({ Authorization: basic('bob'), 'X-Forwarded-For': '10.0.0.2' })).status).toBe(200);
            expect((await initialize({ Authorization: basic('alice'), 'X-Forwarded-For': '10.0.0.1' })).status).toBe(429);
        });

        it('does not let another user take over a session by its id', async () => {
            await start();
            const alice = await connectClient(basic('alice'));

            const response = await fetch(running!.url, {
                method: 'POST',
                headers: { ...mcpHeaders, Authorization: basic('bob'), 'Mcp-Session-Id': sessionIdOf(alice)! },
                body: JSON.stringify({ jsonrpc: '2.0', id: 2, method: 'tools/list' }),
            });

            expect(response.status).toBe(404);
        });
    });

    describe('MCP endpoint', () => {
        it('serves tool calls to an authenticated MCP client over Streamable HTTP', async () => {
            await start();
            const client = await connectClient();

            const { tools } = await client.listTools();
            const result = await client.callTool({ name: 'echo', arguments: { text: 'hello' } });

            expect(tools.map((tool) => tool.name).sort()).toEqual(['confirm', 'echo', 'veeam-token', 'whoami']);
            expect(result.content).toEqual([{ type: 'text', text: 'hello' }]);
            expect(running!.url).toMatch(/^http:\/\/127\.0\.0\.1:\d+\/mcp$/);
        });

        it('relays elicitation to the client inside the tool call, as the action confirmation flow needs', async () => {
            await start();
            const client = await connectClient(basic('alice'), { elicitation: { form: {} } });
            client.setRequestHandler(ElicitRequestSchema, async (request) => {
                expect(request.params.message).toBe('Start the job?');
                return { action: 'accept', content: {} };
            });

            const result = await client.callTool({ name: 'confirm', arguments: {} });

            expect(result.content).toEqual([{ type: 'text', text: 'accept' }]);
        });

        it('rejects a Host header outside the allowed list, which blocks DNS rebinding', async () => {
            await start({ allowedHosts: ['mcp.example.test'] });

            const response = await initialize({ Authorization: basic('alice') });

            expect(response.status).toBe(403);
        });

        it('rejects a browser Origin outside the allowed list', async () => {
            await start();

            const response = await initialize({ Authorization: basic('alice'), Origin: 'https://evil.example.test' });

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
                headers: { ...mcpHeaders, Authorization: basic('alice'), 'Mcp-Session-Id': 'missing' },
                body: JSON.stringify({ jsonrpc: '2.0', id: 2, method: 'tools/list' }),
            });

            expect(response.status).toBe(404);
        });

        it('refuses a non-initialize request that carries no session id', async () => {
            await start();

            const response = await fetch(running!.url, {
                method: 'POST',
                headers: { ...mcpHeaders, Authorization: basic('alice') },
                body: JSON.stringify({ jsonrpc: '2.0', id: 2, method: 'tools/list' }),
            });

            expect(response.status).toBe(400);
            expect(running!.sessionCount).toBe(0);
        });

        it('reports malformed JSON as a JSON-RPC parse error', async () => {
            await start();

            const response = await fetch(running!.url, {
                method: 'POST',
                headers: { ...mcpHeaders, Authorization: basic('alice') },
                body: '{not json',
            });

            expect(response.status).toBe(400);
            expect(await response.json()).toMatchObject({ error: { code: -32700 } });
        });

        it('refuses an oversized request body', async () => {
            await start();

            const response = await fetch(running!.url, {
                method: 'POST',
                headers: { ...mcpHeaders, Authorization: basic('alice') },
                body: JSON.stringify({ padding: 'x'.repeat(5 * 1024 * 1024) }),
            });

            expect(response.status).toBe(413);
        });

        it('keeps to the session limit when clients initialize at the same time', async () => {
            await start({
                maxSessions: 1,
                createSession: () => {
                    const session = testSession(() => (closedSessions += 1));
                    const connect = session.server.connect.bind(session.server);
                    session.server.connect = async (transport) => {
                        await new Promise((resolve) => setTimeout(resolve, 50));
                        await connect(transport);
                    };
                    return session;
                },
            });

            const responses = await Promise.all(Array.from({ length: 5 }, () => initialize({ Authorization: basic('alice') })));

            expect(responses.map((response) => response.status).sort()).toEqual([200, 503, 503, 503, 503]);
            expect(running!.sessionCount).toBe(1);
        });

        it('closes a session that fails while it is being opened', async () => {
            await start({
                createSession: () => {
                    const session = testSession(() => (closedSessions += 1));
                    session.server.connect = async () => {
                        throw new Error('connect failed');
                    };
                    return session;
                },
            });

            const response = await initialize({ Authorization: basic('alice') });

            expect(response.status).toBe(500);
            expect(closedSessions).toBe(1);
            expect(running!.sessionCount).toBe(0);
        });

        it('limits the sessions of one user without blocking other users', async () => {
            await start({ maxSessionsPerUser: 2 });
            await connectClient(basic('alice'));
            await connectClient(basic('alice'));

            const third = await initialize({ Authorization: basic('alice') });

            expect(third.status).toBe(503);
            expect(await third.json()).toMatchObject({ error: { message: expect.stringContaining('"alice"') } });
            expect((await initialize({ Authorization: basic('bob') })).status).toBe(200);
        });

        it('refuses new sessions beyond the configured limit', async () => {
            await start({ maxSessions: 1 });
            await connectClient();

            await expect(connectClient()).rejects.toThrow();
            expect(running!.sessionCount).toBe(1);
        });

        it('closes a session that stays idle past the timeout', async () => {
            await start({ sessionIdleTimeoutMs: 200 });
            expect((await initialize({ Authorization: basic('alice') })).status).toBe(200);
            expect(running!.sessionCount).toBe(1);

            await waitFor(() => running!.sessionCount === 0);
            expect(closedSessions).toBe(1);
        });

        it('keeps a session open while the client listens on its event stream', async () => {
            await start({ sessionIdleTimeoutMs: 200 });
            const client = await connectClient();
            expect(running!.sessionCount).toBe(1);

            await new Promise((resolve) => setTimeout(resolve, 600));
            expect(running!.sessionCount).toBe(1);

            await client.close();
            await waitFor(() => running!.sessionCount === 0);
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

            const response = await fetch(new URL('/other', running!.url), { headers: { Authorization: basic('alice') } });

            expect(response.status).toBe(404);
        });
    });
});
