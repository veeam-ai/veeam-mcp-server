/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { createHash, randomUUID, timingSafeEqual } from 'node:crypto';
import { readFileSync } from 'node:fs';
import http, { IncomingMessage, ServerResponse } from 'node:http';
import https from 'node:https';
import { AddressInfo } from 'node:net';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import { isInitializeRequest } from '@modelcontextprotocol/sdk/types.js';
import type { McpSession } from '@/mcp/session';
import { LOOPBACK_HOSTS, Settings } from '@/config/settings';
import { log } from '@/utils/logger';

export const MCP_PATH = '/mcp';
export const HEALTH_PATH = '/healthz';

const MAX_BODY_BYTES = 4 * 1024 * 1024;

export interface HttpServerOptions {
    host: string;
    port: number;
    createSession: () => McpSession;
    authToken?: string;
    /** Host names accepted in the Host and Origin headers; omitted means any. */
    allowedHosts?: string[];
    tls?: { cert: Buffer; key: Buffer };
    maxSessions: number;
    sessionIdleTimeoutMs: number;
}

export interface RunningHttpServer {
    url: string;
    readonly sessionCount: number;
    close(): Promise<void>;
}

interface SessionEntry {
    session: McpSession;
    transport: StreamableHTTPServerTransport;
    lastActivity: number;
    inFlight: number;
}

class HttpError extends Error {
    constructor(
        public readonly status: number,
        public readonly rpcCode: number,
        message: string,
    ) {
        super(message);
    }
}

export function httpServerOptionsFromSettings(settings: Settings, createSession: () => McpSession): HttpServerOptions {
    const isLoopback = LOOPBACK_HOSTS.includes(settings.MCP_HTTP_HOST.toLowerCase());

    return {
        host: settings.MCP_HTTP_HOST,
        port: settings.MCP_HTTP_PORT,
        createSession,
        authToken: settings.MCP_HTTP_AUTH_TOKEN,
        allowedHosts: settings.MCP_HTTP_ALLOWED_HOSTS ?? (isLoopback ? LOOPBACK_HOSTS : undefined),
        tls:
            settings.MCP_HTTP_TLS_CERT_FILE !== undefined && settings.MCP_HTTP_TLS_KEY_FILE !== undefined
                ? { cert: readFileSync(settings.MCP_HTTP_TLS_CERT_FILE), key: readFileSync(settings.MCP_HTTP_TLS_KEY_FILE) }
                : undefined,
        maxSessions: settings.MCP_HTTP_MAX_SESSIONS,
        sessionIdleTimeoutMs: settings.MCP_HTTP_SESSION_IDLE_TIMEOUT_SEC * 1000,
    };
}

function digest(value: string): Buffer {
    return createHash('sha256').update(value).digest();
}

function normalizeHost(host: string): string {
    return host.toLowerCase().replace(/^\[(.*)\]$/, '$1');
}

function hostnameOf(value: string, withScheme: boolean): string | undefined {
    try {
        return normalizeHost(new URL(withScheme ? value : `http://${value}`).hostname);
    } catch {
        return undefined;
    }
}

function sendJson(res: ServerResponse, status: number, body: unknown, headers: Record<string, string> = {}): void {
    if (res.headersSent) {
        res.end();
        return;
    }
    res.writeHead(status, { 'Content-Type': 'application/json', ...headers });
    res.end(JSON.stringify(body));
}

function sendRpcError(res: ServerResponse, status: number, code: number, message: string, headers?: Record<string, string>): void {
    sendJson(res, status, { jsonrpc: '2.0', error: { code, message }, id: null }, headers);
}

async function readJsonBody(req: IncomingMessage): Promise<unknown> {
    const chunks: Buffer[] = [];
    let size = 0;

    for await (const chunk of req) {
        size += (chunk as Buffer).length;
        if (size > MAX_BODY_BYTES) {
            throw new HttpError(413, -32600, `Request body exceeds ${MAX_BODY_BYTES} bytes`);
        }
        chunks.push(chunk as Buffer);
    }

    try {
        return JSON.parse(Buffer.concat(chunks).toString('utf8'));
    } catch {
        throw new HttpError(400, -32700, 'Parse error: request body is not valid JSON');
    }
}

export async function startHttpServer(options: HttpServerOptions): Promise<RunningHttpServer> {
    const sessions = new Map<string, SessionEntry>();
    const expectedToken = options.authToken !== undefined ? digest(options.authToken) : undefined;
    const allowedHosts = options.allowedHosts?.map(normalizeHost);

    async function closeSession(id: string, reason: string): Promise<void> {
        const entry = sessions.get(id);
        if (entry === undefined) {
            return;
        }

        sessions.delete(id);
        log.info(`HTTP session ${id} closed (${reason}); ${sessions.size} active`);

        try {
            await entry.session.close();
        } catch (error: any) {
            log.warn(`failed to close HTTP session ${id}: ${error?.message || String(error)}`);
        }
    }

    function isAuthorized(req: IncomingMessage): boolean {
        if (expectedToken === undefined) {
            return true;
        }

        const match = /^Bearer\s+(.+)$/i.exec(req.headers.authorization ?? '');
        return match !== null && timingSafeEqual(digest(match[1].trim()), expectedToken);
    }

    function isAllowedOrigin(req: IncomingMessage): boolean {
        if (allowedHosts === undefined) {
            return true;
        }

        const host = hostnameOf(req.headers.host ?? '', false);
        if (host === undefined || !allowedHosts.includes(host)) {
            return false;
        }

        const origin = req.headers.origin;
        if (origin === undefined) {
            return true;
        }

        const originHost = hostnameOf(origin, true);
        return originHost !== undefined && allowedHosts.includes(originHost);
    }

    async function dispatch(entry: SessionEntry, req: IncomingMessage, res: ServerResponse, body: unknown): Promise<void> {
        entry.lastActivity = Date.now();
        if (req.method === 'POST') {
            entry.inFlight += 1;
            res.once('close', () => {
                entry.inFlight -= 1;
                entry.lastActivity = Date.now();
            });
        }

        await entry.transport.handleRequest(req, res, body);
    }

    async function openSession(req: IncomingMessage, res: ServerResponse, body: unknown): Promise<void> {
        if (sessions.size >= options.maxSessions) {
            throw new HttpError(503, -32000, `Too many active sessions (limit ${options.maxSessions})`);
        }

        const session = options.createSession();

        const transport = new StreamableHTTPServerTransport({
            sessionIdGenerator: () => randomUUID(),
            onsessioninitialized: (id) => {
                sessions.set(id, entry);
                log.info(`HTTP session ${id} opened; ${sessions.size} active`);
            },
        });
        transport.onclose = () => {
            if (transport.sessionId !== undefined) {
                void closeSession(transport.sessionId, 'closed by client');
            }
        };

        const entry: SessionEntry = { session, transport, lastActivity: Date.now(), inFlight: 0 };

        await session.server.connect(transport);
        await dispatch(entry, req, res, body);

        if (transport.sessionId === undefined) {
            await session.close();
        }
    }

    async function handleMcp(req: IncomingMessage, res: ServerResponse): Promise<void> {
        const body = req.method === 'POST' ? await readJsonBody(req) : undefined;
        const sessionHeader = req.headers['mcp-session-id'];
        const sessionId = Array.isArray(sessionHeader) ? sessionHeader[0] : sessionHeader;

        if (sessionId !== undefined) {
            const entry = sessions.get(sessionId);
            if (entry === undefined) {
                throw new HttpError(404, -32001, 'Session not found; initialize a new session');
            }
            await dispatch(entry, req, res, body);
            return;
        }

        if (req.method !== 'POST' || !isInitializeRequest(body)) {
            throw new HttpError(400, -32000, 'Bad Request: no valid session ID provided');
        }

        await openSession(req, res, body);
    }

    async function handle(req: IncomingMessage, res: ServerResponse): Promise<void> {
        const { pathname } = new URL(req.url ?? '/', 'http://localhost');

        if (pathname === HEALTH_PATH && req.method === 'GET') {
            sendJson(res, 200, { status: 'ok' });
            return;
        }

        if (pathname !== MCP_PATH) {
            sendJson(res, 404, { error: 'Not found' });
            return;
        }

        if (!isAllowedOrigin(req)) {
            sendRpcError(res, 403, -32000, 'Forbidden: host or origin not allowed');
            return;
        }

        if (!isAuthorized(req)) {
            sendRpcError(res, 401, -32001, 'Unauthorized', { 'WWW-Authenticate': 'Bearer' });
            return;
        }

        try {
            await handleMcp(req, res);
        } catch (error: any) {
            if (error instanceof HttpError) {
                sendRpcError(res, error.status, error.rpcCode, error.message);
                return;
            }
            log.error(`HTTP request failed: ${error?.message || String(error)}`);
            sendRpcError(res, 500, -32603, 'Internal server error');
        }
    }

    const listener = (req: IncomingMessage, res: ServerResponse) => void handle(req, res);
    const server = options.tls !== undefined ? https.createServer(options.tls, listener) : http.createServer(listener);

    const sweep = setInterval(
        () => {
            const cutoff = Date.now() - options.sessionIdleTimeoutMs;
            for (const [id, entry] of sessions) {
                if (entry.inFlight === 0 && entry.lastActivity < cutoff) {
                    void closeSession(id, 'idle timeout');
                }
            }
        },
        Math.min(60_000, Math.max(100, options.sessionIdleTimeoutMs / 4)),
    );
    sweep.unref();

    await new Promise<void>((resolve, reject) => {
        server.once('error', reject);
        server.listen(options.port, options.host, () => {
            server.off('error', reject);
            resolve();
        });
    });

    const { port } = server.address() as AddressInfo;
    const displayHost = options.host.includes(':') ? `[${options.host}]` : options.host;
    const url = `${options.tls !== undefined ? 'https' : 'http'}://${displayHost}:${port}${MCP_PATH}`;

    return {
        url,
        get sessionCount() {
            return sessions.size;
        },
        async close() {
            clearInterval(sweep);
            await Promise.all(Array.from(sessions.keys(), (id) => closeSession(id, 'server shutdown')));
            await new Promise<void>((resolve) => {
                server.close(() => resolve());
                server.closeAllConnections();
            });
        },
    };
}
