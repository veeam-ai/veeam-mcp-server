/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { describe, it, expect, beforeAll, beforeEach, afterEach, jest } from '@jest/globals';
import { createHash, randomBytes } from 'node:crypto';
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

const PASSWORD = 'correct horse battery staple';
const REDIRECT_URI = 'http://127.0.0.1:43210/callback';

let startHttpServer: (options: HttpServerOptions) => Promise<RunningHttpServer>;
let TokenSealer: typeof import('@/auth/tokenSealer').TokenSealer;
let productAuthOf: typeof import('@/auth/identity').productAuthOf;

beforeAll(async () => {
    ({ startHttpServer } = await import('../http'));
    ({ TokenSealer } = await import('@/auth/tokenSealer'));
    ({ productAuthOf } = await import('@/auth/identity'));
});

let productReachable: boolean;
let refreshAccepted: boolean;

const rejected = () =>
    new AxiosError('Request failed with status code 400', 'ERR_BAD_REQUEST', undefined, undefined, { status: 400 } as never);

const requestUserToken = jest.fn(async ({ username, password }: ProductCredentials): Promise<ProductUserToken> => {
    if (!productReachable) {
        throw new AxiosError('connect ECONNREFUSED', 'ECONNREFUSED');
    }
    if (password === PASSWORD) {
        return { accessToken: `vbr-${username}`, refreshToken: `refresh-${username}`, expiresAt: Date.now() + 900_000 };
    }
    throw rejected();
});

const refreshUserToken = jest.fn(async (refreshToken: string): Promise<ProductUserToken> => {
    if (refreshAccepted) {
        return { accessToken: `${refreshToken}-renewed`, expiresAt: Date.now() + 900_000 };
    }
    throw rejected();
});

function testSession(): McpSession {
    const server = new McpServer({ name: 'test-server', version: '0.0.0' });

    server.registerTool('echo', { inputSchema: { text: z.string() } }, async ({ text }) => ({
        content: [{ type: 'text', text }],
    }));

    server.registerTool('whoami', { inputSchema: {} }, async (_args, extra) => {
        const auth = productAuthOf(extra.authInfo);
        return { content: [{ type: 'text', text: auth?.kind === 'token' ? auth.token.accessToken : 'nobody' }] };
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

describe('startHttpServer with OAuth sign-in', () => {
    let running: RunningHttpServer | undefined;
    let clients: Client[];
    let stderr: jest.SpiedFunction<typeof process.stderr.write>;

    async function start(overrides: Partial<HttpServerOptions> = {}): Promise<RunningHttpServer> {
        running = await startHttpServer({
            host: '127.0.0.1',
            port: 0,
            createSession: testSession,
            auth: {
                mode: 'oauth',
                provider: {
                    sealer: TokenSealer.fromSecret(undefined),
                    product: { requestUserToken, refreshUserToken },
                    productName: 'Veeam Backup & Replication',
                    signInMaxAgeSec: 3600,
                    allowedRedirectUris: ['https://vscode.dev/redirect'],
                },
            },
            allowedHosts: ['localhost', '127.0.0.1', '::1'],
            trustProxy: 0,
            maxSessions: 10,
            maxSessionsPerUser: 10,
            sessionIdleTimeoutMs: 60_000,
            ...overrides,
        });
        return running;
    }

    function endpoint(path: string): URL {
        return new URL(path, running!.url);
    }

    async function register(redirectUris: string[] = [REDIRECT_URI], headers: Record<string, string> = {}): Promise<Response> {
        return fetch(endpoint('/register'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...headers },
            body: JSON.stringify({ redirect_uris: redirectUris, client_name: 'Test <client>', token_endpoint_auth_method: 'none' }),
        });
    }

    async function registeredClientId(): Promise<string> {
        const response = await register();
        expect(response.status).toBe(201);
        return ((await response.json()) as { client_id: string }).client_id;
    }

    function pkce(): { verifier: string; challenge: string } {
        const verifier = randomBytes(32).toString('base64url');
        return { verifier, challenge: createHash('sha256').update(verifier).digest('base64url') };
    }

    async function loginPage(clientId: string, challenge: string): Promise<{ page: string; request: string }> {
        const url = endpoint('/authorize');
        url.search = new URLSearchParams({
            response_type: 'code',
            client_id: clientId,
            redirect_uri: REDIRECT_URI,
            code_challenge: challenge,
            code_challenge_method: 'S256',
            state: 'state-1',
            resource: running!.url,
        }).toString();

        const response = await fetch(url);
        expect(response.status).toBe(200);
        const page = await response.text();
        return { page, request: /name="request" value="([^"]+)"/.exec(page)![1] };
    }

    async function submitLogin(fields: Record<string, string>, headers: Record<string, string> = {}): Promise<Response> {
        return fetch(endpoint('/login'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded', ...headers },
            body: new URLSearchParams(fields).toString(),
            redirect: 'manual',
        });
    }

    async function token(fields: Record<string, string>): Promise<Response> {
        return fetch(endpoint('/token'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: new URLSearchParams(fields).toString(),
        });
    }

    async function authorizationCode(clientId: string, username: string, challenge: string): Promise<string> {
        const { request } = await loginPage(clientId, challenge);
        const response = await submitLogin({ request, username, password: PASSWORD });
        expect(response.status).toBe(302);
        const location = new URL(response.headers.get('location')!);
        expect(`${location.origin}${location.pathname}`).toBe(REDIRECT_URI);
        expect(location.searchParams.get('state')).toBe('state-1');
        return location.searchParams.get('code')!;
    }

    async function signIn(username = 'alice'): Promise<{ clientId: string; access_token: string; refresh_token?: string }> {
        const clientId = await registeredClientId();
        const { verifier, challenge } = pkce();
        const code = await authorizationCode(clientId, username, challenge);

        const response = await token({
            grant_type: 'authorization_code',
            client_id: clientId,
            code,
            code_verifier: verifier,
            redirect_uri: REDIRECT_URI,
        });
        expect(response.status).toBe(200);
        return { clientId, ...((await response.json()) as { access_token: string; refresh_token?: string }) };
    }

    async function connectClient(accessToken: string, capabilities: Record<string, unknown> = {}): Promise<Client> {
        const transport = new StreamableHTTPClientTransport(new URL(running!.url), {
            requestInit: { headers: { Authorization: `Bearer ${accessToken}` } },
        });
        const client = new Client({ name: 'test-client', version: '0.0.0' }, { capabilities });
        await client.connect(transport);
        clients.push(client);
        return client;
    }

    async function signedInClient(username = 'alice'): Promise<Client> {
        return connectClient((await signIn(username)).access_token);
    }

    function sessionIdOf(client: Client): string | undefined {
        return (client.transport as StreamableHTTPClientTransport).sessionId;
    }

    beforeEach(() => {
        clients = [];
        productReachable = true;
        refreshAccepted = true;
        requestUserToken.mockClear();
        refreshUserToken.mockClear();
        stderr = jest.spyOn(process.stderr, 'write').mockImplementation(() => true);
    });

    afterEach(async () => {
        await Promise.all(clients.map((client) => client.close().catch(() => {})));
        await running?.close();
        running = undefined;
        stderr.mockRestore();
    });

    describe('OAuth sign-in', () => {
        it('lets a user sign in with their own Veeam account and hands that identity to the tools', async () => {
            await start();
            const client = await signedInClient('alice');

            const result = await client.callTool({ name: 'whoami', arguments: {} });

            expect(textOf(result)).toBe('vbr-alice');
            expect(requestUserToken).toHaveBeenCalledWith({ username: 'alice', password: PASSWORD });
        });

        it('keeps two users apart: each tool call carries the identity of whoever made it', async () => {
            await start();
            const alice = await signedInClient('alice');
            const bob = await signedInClient('bob');

            expect(textOf(await alice.callTool({ name: 'whoami', arguments: {} }))).toBe('vbr-alice');
            expect(textOf(await bob.callTool({ name: 'whoami', arguments: {} }))).toBe('vbr-bob');
        });

        it('advertises the authorization server so MCP clients can discover the sign-in flow', async () => {
            await start();

            const resource = await (await fetch(endpoint('/.well-known/oauth-protected-resource/mcp'))).json();
            const server = await (await fetch(endpoint('/.well-known/oauth-authorization-server'))).json();

            expect(resource).toMatchObject({ resource: running!.url, authorization_servers: [endpoint('/').href] });
            expect(server).toMatchObject({
                authorization_endpoint: endpoint('/authorize').href,
                token_endpoint: endpoint('/token').href,
                registration_endpoint: endpoint('/register').href,
                code_challenge_methods_supported: ['S256'],
            });
        });

        it('shows the requesting client and its redirect target on the login page, escaped', async () => {
            await start();
            const clientId = await registeredClientId();

            const { page } = await loginPage(clientId, pkce().challenge);

            expect(page).toContain('Test &#60;client&#62;');
            expect(page).not.toContain('Test <client>');
            expect(page).toContain(REDIRECT_URI);
        });

        it('lets the browser send its origin with the login form, which a no-referrer policy would turn into Origin: null', async () => {
            await start();
            const clientId = await registeredClientId();
            const url = endpoint('/authorize');
            url.search = new URLSearchParams({
                response_type: 'code',
                client_id: clientId,
                redirect_uri: REDIRECT_URI,
                code_challenge: pkce().challenge,
                code_challenge_method: 'S256',
            }).toString();
            const page = await fetch(url);
            const request = /name="request" value="([^"]+)"/.exec(await page.text())![1];

            const response = await submitLogin({ request, username: 'alice', password: PASSWORD }, { Origin: endpoint('/').origin });

            expect(page.headers.get('referrer-policy')).toBe('same-origin');
            expect(response.status).toBe(302);
        });

        it('rate limits sign-in endpoints per client behind a trusted proxy, not per proxy', async () => {
            await start({ trustProxy: 1 });

            for (let attempt = 0; attempt < 20; attempt += 1) {
                expect((await register([REDIRECT_URI], { 'X-Forwarded-For': '10.0.0.1' })).status).toBe(201);
            }

            expect((await register([REDIRECT_URI], { 'X-Forwarded-For': '10.0.0.2' })).status).toBe(201);
            expect((await register([REDIRECT_URI], { 'X-Forwarded-For': '10.0.0.1' })).status).toBe(429);
        });

        it('keeps the user on the login page when the Veeam password is wrong', async () => {
            await start();
            const { request } = await loginPage(await registeredClientId(), pkce().challenge);

            const response = await submitLogin({ request, username: 'alice', password: 'wrong' });

            expect(response.status).toBe(401);
            expect(response.headers.get('location')).toBeNull();
            expect(await response.text()).toContain('The user name or password is incorrect.');
        });

        it('says the product is unreachable instead of blaming the password', async () => {
            await start();
            const { request } = await loginPage(await registeredClientId(), pkce().challenge);
            productReachable = false;

            const response = await submitLogin({ request, username: 'alice', password: PASSWORD });

            expect(response.status).toBe(502);
            expect(await response.text()).toContain('failed (ECONNREFUSED)');
        });

        it('rejects a login whose sign-in request was not issued by this server', async () => {
            await start();

            const response = await submitLogin({ request: 'forged', username: 'alice', password: PASSWORD });

            expect(response.status).toBe(400);
            expect(requestUserToken).not.toHaveBeenCalled();
        });

        it('locks out an address after repeated failed logins', async () => {
            await start();
            const { request } = await loginPage(await registeredClientId(), pkce().challenge);

            for (let attempt = 0; attempt < 10; attempt += 1) {
                expect((await submitLogin({ request, username: 'alice', password: 'wrong' })).status).toBe(401);
            }
            const locked = await submitLogin({ request, username: 'alice', password: PASSWORD });

            expect(locked.status).toBe(429);
            expect(requestUserToken).toHaveBeenCalledTimes(10);
        });

        it('only registers clients that redirect to loopback or to an explicitly allowed URI', async () => {
            await start();

            const evil = await register(['https://evil.example.test/callback']);
            const allowed = await register(['https://vscode.dev/redirect']);

            expect(evil.status).toBe(400);
            expect(await evil.json()).toMatchObject({ error: 'invalid_client_metadata' });
            expect(allowed.status).toBe(201);
        });

        it('refuses to exchange a code without the matching PKCE verifier', async () => {
            await start();
            const clientId = await registeredClientId();
            const code = await authorizationCode(clientId, 'alice', pkce().challenge);

            const response = await token({ grant_type: 'authorization_code', client_id: clientId, code, code_verifier: pkce().verifier });

            expect(response.status).toBe(400);
            expect(await response.json()).toMatchObject({ error: 'invalid_grant' });
        });

        it('refuses to exchange a code issued to another client', async () => {
            await start();
            const { verifier, challenge } = pkce();
            const code = await authorizationCode(await registeredClientId(), 'alice', challenge);

            const response = await token({
                grant_type: 'authorization_code',
                client_id: await registeredClientId(),
                code,
                code_verifier: verifier,
            });

            expect(response.status).toBe(400);
            expect(await response.json()).toMatchObject({ error: 'invalid_grant' });
        });

        it('renews the access token through the Veeam refresh token', async () => {
            await start();
            const { clientId, refresh_token } = await signIn('alice');

            const response = await token({ grant_type: 'refresh_token', client_id: clientId, refresh_token: refresh_token! });
            const renewed = (await response.json()) as { access_token: string; refresh_token: string };
            const client = await connectClient(renewed.access_token);

            expect(response.status).toBe(200);
            expect(renewed.refresh_token).toBeDefined();
            expect(textOf(await client.callTool({ name: 'whoami', arguments: {} }))).toBe('refresh-alice-renewed');
            expect(refreshUserToken).toHaveBeenLastCalledWith('refresh-alice');
        });

        it('sends the user back to the login page once the product refuses the refresh token', async () => {
            await start();
            const { clientId, refresh_token } = await signIn('alice');
            refreshAccepted = false;

            const response = await token({ grant_type: 'refresh_token', client_id: clientId, refresh_token: refresh_token! });

            expect(response.status).toBe(400);
            expect(await response.json()).toMatchObject({ error: 'invalid_grant' });
        });
    });

    describe('MCP endpoint', () => {
        it('serves tool calls to a signed-in MCP client over Streamable HTTP', async () => {
            await start();
            const client = await signedInClient();

            const { tools } = await client.listTools();
            const result = await client.callTool({ name: 'echo', arguments: { text: 'hello' } });

            expect(tools.map((tool) => tool.name).sort()).toEqual(['confirm', 'echo', 'whoami']);
            expect(result.content).toEqual([{ type: 'text', text: 'hello' }]);
            expect(running!.url).toMatch(/^http:\/\/127\.0\.0\.1:\d+\/mcp$/);
        });

        it('relays elicitation to the client inside the tool call, as the action confirmation flow needs', async () => {
            await start();
            const client = await connectClient((await signIn()).access_token, { elicitation: { form: {} } });
            client.setRequestHandler(ElicitRequestSchema, async (request) => {
                expect(request.params.message).toBe('Start the job?');
                return { action: 'accept', content: {} };
            });

            const result = await client.callTool({ name: 'confirm', arguments: {} });

            expect(result.content).toEqual([{ type: 'text', text: 'accept' }]);
        });

        it('points an unauthenticated client at the sign-in metadata before any session is created', async () => {
            await start();

            const response = await fetch(running!.url, { method: 'POST', headers: mcpHeaders, body: JSON.stringify(initializeBody) });

            expect(response.status).toBe(401);
            expect(response.headers.get('www-authenticate')).toContain(
                `resource_metadata="${endpoint('/.well-known/oauth-protected-resource/mcp').href}"`,
            );
            expect(running!.sessionCount).toBe(0);
        });

        it('rejects an access token this server did not issue', async () => {
            await start();

            await expect(connectClient('not-a-real-token')).rejects.toThrow();
            expect(running!.sessionCount).toBe(0);
        });

        it('rejects an access token sealed with another server key', async () => {
            await start();
            const { access_token } = await signIn();
            await running!.close();
            await start();

            await expect(connectClient(access_token)).rejects.toThrow();
        });

        it('does not let another user take over a session by its id', async () => {
            await start();
            const alice = await signedInClient('alice');
            const { access_token: bobToken } = await signIn('bob');

            const response = await fetch(running!.url, {
                method: 'POST',
                headers: { ...mcpHeaders, Authorization: `Bearer ${bobToken}`, 'Mcp-Session-Id': sessionIdOf(alice)! },
                body: JSON.stringify({ jsonrpc: '2.0', id: 2, method: 'tools/list' }),
            });

            expect(response.status).toBe(404);
        });

        it('rejects a Host header outside the allowed list, which blocks DNS rebinding', async () => {
            await start({ allowedHosts: ['mcp.example.test'] });

            const response = await fetch(running!.url, { method: 'POST', headers: mcpHeaders, body: JSON.stringify(initializeBody) });

            expect(response.status).toBe(403);
        });

        it('rejects a browser Origin outside the allowed list', async () => {
            await start();
            const { access_token } = await signIn();

            const response = await fetch(running!.url, {
                method: 'POST',
                headers: { ...mcpHeaders, Authorization: `Bearer ${access_token}`, Origin: 'https://evil.example.test' },
                body: JSON.stringify(initializeBody),
            });

            expect(response.status).toBe(403);
        });

        it('answers 404 outside the known paths', async () => {
            await start();

            const response = await fetch(endpoint('/other'));

            expect(response.status).toBe(404);
        });
    });
});
