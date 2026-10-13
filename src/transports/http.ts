/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { randomUUID } from 'node:crypto';
import { readFileSync } from 'node:fs';
import http from 'node:http';
import https from 'node:https';
import { AddressInfo } from 'node:net';
import express, { NextFunction, Request, RequestHandler, Response } from 'express';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import { isInitializeRequest } from '@modelcontextprotocol/sdk/types.js';
import { getOAuthProtectedResourceMetadataUrl, mcpAuthRouter } from '@modelcontextprotocol/sdk/server/auth/router.js';
import { requireBearerAuth } from '@modelcontextprotocol/sdk/server/auth/middleware/bearerAuth.js';
import type { McpSession } from '@/mcp/session';
import { getProductName, isLoopbackHost, LOOPBACK_HOSTS, normalizeHost, Settings } from '@/config/settings';
import { createProductRestClient, ProductRestClient } from '@/product';
import { AuthError, BasicAuthenticator } from '@/auth/basicAuth';
import { identityOf } from '@/auth/identity';
import { LOGIN_FAILURE_WINDOW_MS, LoginThrottle } from '@/auth/loginThrottle';
import { LOGIN_PATH, VeeamOAuthProvider, VeeamOAuthProviderOptions } from '@/auth/oauthProvider';
import { TokenSealer } from '@/auth/tokenSealer';
import { log } from '@/utils/logger';

export const MCP_PATH = '/mcp';
export const HEALTH_PATH = '/healthz';

const MAX_BODY_BYTES = 4 * 1024 * 1024;

export type HttpAuthOptions =
    | { mode: 'basic'; product: Pick<ProductRestClient, 'requestUserToken'> }
    | { mode: 'oauth'; publicUrl?: URL; provider: Omit<VeeamOAuthProviderOptions, 'resourceUrl'> };

export interface HttpServerOptions {
    host: string;
    port: number;
    createSession: () => McpSession;
    auth: HttpAuthOptions;
    /** Host names accepted in the Host and Origin headers; omitted means any. */
    allowedHosts?: string[];
    trustProxy: number;
    tls?: { cert: Buffer; key: Buffer };
    maxSessions: number;
    maxSessionsPerUser: number;
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
    owner: string;
    user: string;
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

function httpAuthFromSettings(settings: Settings, publicUrl: URL | undefined): HttpAuthOptions {
    const product = createProductRestClient(undefined);
    if (settings.MCP_HTTP_AUTH === 'basic') {
        return { mode: 'basic', product };
    }

    return {
        mode: 'oauth',
        publicUrl,
        provider: {
            sealer: TokenSealer.fromSecret(settings.MCP_HTTP_TOKEN_SECRET),
            product,
            productName: getProductName(),
            signInMaxAgeSec: settings.MCP_HTTP_SIGN_IN_MAX_AGE_SEC,
            allowedRedirectUris: settings.MCP_HTTP_ALLOWED_REDIRECT_URIS ?? [],
        },
    };
}

export function httpServerOptionsFromSettings(settings: Settings, createSession: () => McpSession): HttpServerOptions {
    const publicUrl =
        settings.MCP_HTTP_AUTH === 'oauth' && settings.MCP_HTTP_PUBLIC_URL !== undefined
            ? new URL(settings.MCP_HTTP_PUBLIC_URL)
            : undefined;
    const defaultAllowedHosts =
        publicUrl !== undefined ? [publicUrl.hostname] : isLoopbackHost(settings.MCP_HTTP_HOST) ? LOOPBACK_HOSTS : undefined;

    return {
        host: settings.MCP_HTTP_HOST,
        port: settings.MCP_HTTP_PORT,
        createSession,
        auth: httpAuthFromSettings(settings, publicUrl),
        allowedHosts: settings.MCP_HTTP_ALLOWED_HOSTS ?? defaultAllowedHosts,
        trustProxy: settings.MCP_HTTP_TRUST_PROXY ?? (settings.MCP_HTTP_BEHIND_TLS_PROXY ? 1 : 0),
        tls:
            settings.MCP_HTTP_TLS_CERT_FILE !== undefined && settings.MCP_HTTP_TLS_KEY_FILE !== undefined
                ? { cert: readFileSync(settings.MCP_HTTP_TLS_CERT_FILE), key: readFileSync(settings.MCP_HTTP_TLS_KEY_FILE) }
                : undefined,
        maxSessions: settings.MCP_HTTP_MAX_SESSIONS,
        maxSessionsPerUser: settings.MCP_HTTP_MAX_SESSIONS_PER_USER,
        sessionIdleTimeoutMs: settings.MCP_HTTP_SESSION_IDLE_TIMEOUT_SEC * 1000,
    };
}

function hostnameOf(value: string, withScheme: boolean): string | undefined {
    try {
        return normalizeHost(new URL(withScheme ? value : `http://${value}`).hostname);
    } catch {
        return undefined;
    }
}

function listenUrl(host: string, port: number, tls: boolean): URL {
    const displayHost = host.includes(':') ? `[${host}]` : host;
    return new URL(`${tls ? 'https' : 'http'}://${displayHost}:${port}`);
}

function defaultPublicUrl(host: string, port: number, tls: boolean): URL {
    if (!isLoopbackHost(host)) {
        throw new Error(`A public URL is required when listening on ${host}`);
    }
    return new URL(`${tls ? 'https' : 'http'}://${host === '127.0.0.1' ? host : 'localhost'}:${port}`);
}

function clientAddress(req: Request): string {
    return req.ip ?? req.socket.remoteAddress ?? 'unknown';
}

function sendRpcError(res: Response, status: number, code: number, message: string, headers: Record<string, string> = {}): void {
    if (res.headersSent) {
        res.end();
        return;
    }
    res.status(status).set(headers).json({ jsonrpc: '2.0', error: { code, message }, id: null });
}

export async function startHttpServer(options: HttpServerOptions): Promise<RunningHttpServer> {
    const sessions = new Map<string, SessionEntry>();
    const opening = new Map<string, number>();
    const allowedHosts = options.allowedHosts?.map(normalizeHost);
    const throttle = new LoginThrottle();
    const basic = options.auth.mode === 'basic' ? new BasicAuthenticator(options.auth.product, throttle) : undefined;

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

    async function dispatch(entry: SessionEntry, req: Request, res: Response): Promise<void> {
        entry.lastActivity = Date.now();
        entry.inFlight += 1;
        res.once('close', () => {
            entry.inFlight -= 1;
            entry.lastActivity = Date.now();
        });

        await entry.transport.handleRequest(req, res, req.body);
    }

    function sessionsOf(user: string): number {
        let count = opening.get(user) ?? 0;
        for (const entry of sessions.values()) {
            if (entry.user === user) {
                count += 1;
            }
        }
        return count;
    }

    async function openSession(req: Request, res: Response, owner: string, username: string): Promise<void> {
        const user = username.toLowerCase();
        const openingTotal = Array.from(opening.values()).reduce((sum, count) => sum + count, 0);
        if (sessions.size + openingTotal >= options.maxSessions) {
            throw new HttpError(503, -32000, `Too many active sessions (limit ${options.maxSessions})`);
        }
        if (sessionsOf(user) >= options.maxSessionsPerUser) {
            throw new HttpError(
                503,
                -32000,
                `Too many active sessions for "${username}" (limit ${options.maxSessionsPerUser}); close another MCP client window and retry`,
            );
        }

        opening.set(user, (opening.get(user) ?? 0) + 1);
        let reserved = true;
        const release = () => {
            if (reserved) {
                reserved = false;
                const left = (opening.get(user) ?? 1) - 1;
                if (left === 0) {
                    opening.delete(user);
                } else {
                    opening.set(user, left);
                }
            }
        };

        const session = options.createSession();

        const transport = new StreamableHTTPServerTransport({
            sessionIdGenerator: () => randomUUID(),
            onsessioninitialized: (id) => {
                sessions.set(id, entry);
                release();
                log.info(`HTTP session ${id} opened for "${username}"; ${sessions.size} active`);
            },
        });
        transport.onclose = () => {
            if (transport.sessionId !== undefined) {
                void closeSession(transport.sessionId, 'closed by client');
            }
        };

        const entry: SessionEntry = { session, transport, owner, user, lastActivity: Date.now(), inFlight: 0 };

        try {
            await session.server.connect(transport);
            await dispatch(entry, req, res);
        } catch (error) {
            if (transport.sessionId !== undefined && sessions.has(transport.sessionId)) {
                await closeSession(transport.sessionId, 'failed to initialize');
            } else {
                await session.close();
            }
            throw error;
        } finally {
            release();
        }

        if (transport.sessionId === undefined) {
            await session.close();
        }
    }

    async function handleMcp(req: Request, res: Response): Promise<void> {
        const identity = identityOf(req.auth);
        if (identity === undefined) {
            throw new HttpError(401, -32001, 'Unauthorized');
        }

        const sessionHeader = req.headers['mcp-session-id'];
        const sessionId = Array.isArray(sessionHeader) ? sessionHeader[0] : sessionHeader;

        if (sessionId !== undefined) {
            const entry = sessions.get(sessionId);
            if (entry === undefined || entry.owner !== identity.owner) {
                throw new HttpError(404, -32001, 'Session not found; initialize a new session');
            }
            await dispatch(entry, req, res);
            return;
        }

        if (req.method !== 'POST' || !isInitializeRequest(req.body)) {
            throw new HttpError(400, -32000, 'Bad Request: no valid session ID provided');
        }

        await openSession(req, res, identity.owner, identity.username);
    }

    function hostGuard(req: Request, res: Response, next: NextFunction): void {
        const host = hostnameOf(req.headers.host ?? '', false);
        if (allowedHosts !== undefined && (host === undefined || !allowedHosts.includes(host))) {
            sendRpcError(res, 403, -32000, 'Forbidden: host not allowed');
            return;
        }
        next();
    }

    function originGuard(req: Request, res: Response, next: NextFunction): void {
        const origin = req.headers.origin;
        if (allowedHosts !== undefined && origin !== undefined) {
            const host = hostnameOf(origin, true);
            if (host === undefined || !allowedHosts.includes(host)) {
                sendRpcError(res, 403, -32000, 'Forbidden: origin not allowed');
                return;
            }
        }
        next();
    }

    function basicAuth(authenticator: BasicAuthenticator): RequestHandler {
        return async (req, res, next) => {
            try {
                req.auth = await authenticator.authenticate(req, clientAddress(req));
            } catch (error) {
                if (error instanceof AuthError) {
                    sendRpcError(res, error.status, error.status >= 500 ? -32000 : -32001, error.message, error.headers);
                    return;
                }
                next(error);
                return;
            }
            next();
        };
    }

    function mountOAuth(app: express.Express, provider: VeeamOAuthProvider, publicUrl: URL, mcpUrl: URL): RequestHandler {
        app.use(mcpAuthRouter({ provider, issuerUrl: publicUrl, resourceServerUrl: mcpUrl, resourceName: 'Veeam Intelligence' }));

        app.post(LOGIN_PATH, originGuard, express.urlencoded({ extended: false, limit: '16kb' }), async (req, res) => {
            const address = clientAddress(req);
            if (throttle.isLocked(address)) {
                res.status(429)
                    .set({ 'Retry-After': String(LOGIN_FAILURE_WINDOW_MS / 1000), 'Cache-Control': 'no-store' })
                    .type('text/plain')
                    .send('Too many failed sign-in attempts. Try again later.');
                return;
            }
            const release = throttle.begin(address);
            try {
                if ((await provider.handleLogin(req, res)) === 'rejected') {
                    throttle.recordFailure(address);
                }
            } finally {
                release();
            }
        });

        return requireBearerAuth({ verifier: provider, resourceMetadataUrl: getOAuthProtectedResourceMetadataUrl(mcpUrl) });
    }

    function buildApp(publicUrl: URL): express.Express {
        const mcpUrl = new URL(MCP_PATH, publicUrl);

        const app = express();
        app.disable('x-powered-by');
        app.set('trust proxy', options.trustProxy);

        app.get(HEALTH_PATH, (_req, res) => {
            res.json({ status: 'ok' });
        });

        app.use(hostGuard);

        const authenticate =
            options.auth.mode === 'oauth'
                ? mountOAuth(app, new VeeamOAuthProvider({ ...options.auth.provider, resourceUrl: mcpUrl }), publicUrl, mcpUrl)
                : basicAuth(basic!);

        app.all(MCP_PATH, originGuard, authenticate, express.json({ limit: MAX_BODY_BYTES }), async (req, res) => {
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
        });

        app.use((_req, res) => {
            res.status(404).json({ error: 'Not found' });
        });

        app.use((error: any, _req: Request, res: Response, _next: NextFunction) => {
            if (error?.type === 'entity.too.large') {
                sendRpcError(res, 413, -32600, `Request body exceeds ${MAX_BODY_BYTES} bytes`);
            } else if (error?.type === 'entity.parse.failed') {
                sendRpcError(res, 400, -32700, 'Parse error: request body is not valid JSON');
            } else {
                log.error(`HTTP request failed: ${error?.message || String(error)}`);
                sendRpcError(res, 500, -32603, 'Internal server error');
            }
        });

        return app;
    }

    const server = options.tls !== undefined ? https.createServer(options.tls) : http.createServer();

    await new Promise<void>((resolve, reject) => {
        server.once('error', reject);
        server.listen(options.port, options.host, () => {
            server.off('error', reject);
            resolve();
        });
    });

    const { port } = server.address() as AddressInfo;
    const tls = options.tls !== undefined;
    let publicUrl: URL;
    try {
        publicUrl =
            options.auth.mode === 'oauth'
                ? (options.auth.publicUrl ?? defaultPublicUrl(options.host, port, tls))
                : listenUrl(options.host, port, tls);
        server.on('request', buildApp(publicUrl));
    } catch (error) {
        await new Promise<void>((resolve) => server.close(() => resolve()));
        throw error;
    }

    const sweep = setInterval(
        () => {
            const cutoff = Date.now() - options.sessionIdleTimeoutMs;
            for (const [id, entry] of sessions) {
                if (entry.inFlight === 0 && entry.lastActivity < cutoff) {
                    void closeSession(id, 'idle timeout');
                }
            }
            basic?.prune();
            throttle.prune();
        },
        Math.min(60_000, Math.max(100, options.sessionIdleTimeoutMs / 4)),
    );
    sweep.unref();

    return {
        url: new URL(MCP_PATH, publicUrl).href,
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
