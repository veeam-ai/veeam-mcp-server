/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { describe, it, expect, beforeAll } from '@jest/globals';

const product = {
    PRODUCT_NAME: 'vbr',
    WEB_URL: 'https://vbr.example.test:9419',
    ADMIN_USERNAME: 'x',
    ADMIN_PASSWORD: 'x',
};

// `@/config/settings` validates process.env at import time, so env is set before the dynamic import.
Object.assign(process.env, product);

let parseSettings: typeof import('../settings').parseSettings;

beforeAll(async () => {
    ({ parseSettings } = await import('../settings'));
});

const { ADMIN_USERNAME: _user, ADMIN_PASSWORD: _password, ...productWithoutCredentials } = product;
const http = { ...productWithoutCredentials, MCP_TRANSPORT: 'http' };
const remote = { ...http, MCP_HTTP_HOST: '0.0.0.0', MCP_HTTP_BEHIND_TLS_PROXY: 'true' };

describe('transport settings', () => {
    it('defaults to stdio so existing client configurations keep working', () => {
        expect(parseSettings(product).MCP_TRANSPORT).toBe('stdio');
    });

    it('requires the Veeam credentials in stdio mode', () => {
        expect(() => parseSettings(productWithoutCredentials)).toThrow(/ADMIN_USERNAME environment variable is required/);
        expect(() => parseSettings({ ...product, ADMIN_PASSWORD: ' ' })).toThrow(/ADMIN_PASSWORD environment variable is required/);
    });

    it('defaults the HTTP endpoint to loopback on port 8080', () => {
        expect(parseSettings({ ...http, MCP_TRANSPORT: 'HTTP' })).toMatchObject({
            MCP_TRANSPORT: 'http',
            MCP_HTTP_HOST: '127.0.0.1',
            MCP_HTTP_PORT: 8080,
            MCP_HTTP_BEHIND_TLS_PROXY: false,
        });
        expect(parseSettings(http).MCP_HTTP_TRUST_PROXY).toBeUndefined();
    });

    it('refuses shared Veeam credentials over HTTP, where every user signs in as themselves', () => {
        expect(() => parseSettings({ ...product, MCP_TRANSPORT: 'http' })).toThrow(/must not be set when MCP_TRANSPORT=http/);
        expect(() => parseSettings({ ...http, ADMIN_USERNAME: 'admin' })).toThrow(/must not be set when MCP_TRANSPORT=http/);
    });

    it('requires TLS when the HTTP endpoint listens beyond loopback, so passwords never travel in clear text', () => {
        expect(() => parseSettings({ ...http, MCP_HTTP_HOST: '0.0.0.0' })).toThrow(/TLS is required/);
        expect(parseSettings(remote).MCP_HTTP_BEHIND_TLS_PROXY).toBe(true);
        expect(
            parseSettings({
                ...http,
                MCP_HTTP_HOST: '0.0.0.0',
                MCP_HTTP_TLS_CERT_FILE: '/certs/server.crt',
                MCP_HTTP_TLS_KEY_FILE: '/certs/server.key',
            }).MCP_HTTP_HOST,
        ).toBe('0.0.0.0');
    });

    it('allows plain HTTP on loopback, where nothing leaves the machine', () => {
        expect(parseSettings({ ...http, MCP_HTTP_HOST: 'localhost' }).MCP_HTTP_HOST).toBe('localhost');
    });

    it('does not require HTTP settings in stdio mode whatever the HTTP host says', () => {
        expect(parseSettings({ ...product, MCP_HTTP_HOST: '0.0.0.0' }).MCP_TRANSPORT).toBe('stdio');
    });

    it('rejects an unknown transport', () => {
        expect(() => parseSettings({ ...product, MCP_TRANSPORT: 'sse' })).toThrow();
    });

    it('rejects a TLS certificate without its key', () => {
        expect(() => parseSettings({ ...http, MCP_HTTP_TLS_CERT_FILE: '/certs/server.crt' })).toThrow(/must be set together/);
    });

    it('rejects an idle timeout that would close sessions with actions still waiting for approval', () => {
        expect(() =>
            parseSettings({
                ...http,
                ACTION_CONFIRMATION_TIMEOUT_SEC: '600',
                MCP_HTTP_SESSION_IDLE_TIMEOUT_SEC: '300',
            }),
        ).toThrow(/must not be shorter than ACTION_CONFIRMATION_TIMEOUT_SEC/);
    });

    it('parses the allowed hosts list case-insensitively and ignores blanks', () => {
        const settings = parseSettings({ ...http, MCP_HTTP_ALLOWED_HOSTS: ' MCP.Example.test, ,localhost ' });

        expect(settings.MCP_HTTP_ALLOWED_HOSTS).toEqual(['mcp.example.test', 'localhost']);
    });

    it('defaults HTTP sign-in to Basic so existing HTTP setups keep working', () => {
        expect(parseSettings(http).MCP_HTTP_AUTH).toBe('basic');
        expect(parseSettings({ ...http, MCP_HTTP_AUTH: 'OAuth' }).MCP_HTTP_AUTH).toBe('oauth');
        expect(() => parseSettings({ ...http, MCP_HTTP_AUTH: 'saml' })).toThrow();
    });

    it('requires a public URL for OAuth beyond loopback, because clients are redirected to it', () => {
        expect(() => parseSettings({ ...remote, MCP_HTTP_AUTH: 'oauth' })).toThrow(/MCP_HTTP_PUBLIC_URL is required/);
        expect(
            parseSettings({ ...remote, MCP_HTTP_AUTH: 'oauth', MCP_HTTP_PUBLIC_URL: 'https://mcp.example.test' }).MCP_HTTP_PUBLIC_URL,
        ).toBe('https://mcp.example.test');
        expect(parseSettings({ ...http, MCP_HTTP_AUTH: 'oauth' }).MCP_HTTP_PUBLIC_URL).toBeUndefined();
        expect(parseSettings(remote).MCP_HTTP_AUTH).toBe('basic');
    });

    it('requires the OAuth public URL to be an https origin unless it is localhost', () => {
        const oauth = { ...remote, MCP_HTTP_AUTH: 'oauth' };

        expect(() => parseSettings({ ...oauth, MCP_HTTP_PUBLIC_URL: 'http://mcp.example.test' })).toThrow(/must use https/);
        expect(() => parseSettings({ ...oauth, MCP_HTTP_PUBLIC_URL: 'https://mcp.example.test/mcp' })).toThrow(/origin without a path/);
        expect(parseSettings({ ...http, MCP_HTTP_AUTH: 'oauth', MCP_HTTP_PUBLIC_URL: 'http://localhost:8080' }).MCP_HTTP_PUBLIC_URL).toBe(
            'http://localhost:8080',
        );
    });

    it('refuses OAuth on ::1 without a public URL, since the sign-in address cannot be http://[::1]', () => {
        expect(() => parseSettings({ ...http, MCP_TRANSPORT: 'http', MCP_HTTP_AUTH: 'oauth', MCP_HTTP_HOST: '::1' })).toThrow(
            /cannot advertise ::1/,
        );
        expect(parseSettings({ ...http, MCP_HTTP_HOST: '::1' }).MCP_HTTP_HOST).toBe('::1');
    });

    it('defaults to 1000 sessions in total and 10 per user', () => {
        expect(parseSettings(http)).toMatchObject({ MCP_HTTP_MAX_SESSIONS: 1000, MCP_HTTP_MAX_SESSIONS_PER_USER: 10 });
    });

    it('rejects a short OAuth token secret and parses the extra redirect URIs', () => {
        const oauth = { ...http, MCP_HTTP_AUTH: 'oauth' };

        expect(() => parseSettings({ ...oauth, MCP_HTTP_TOKEN_SECRET: 'short' })).toThrow(/at least 32 characters/);
        expect(parseSettings({ ...oauth, MCP_HTTP_ALLOWED_REDIRECT_URIS: 'https://vscode.dev/redirect, ' })).toMatchObject({
            MCP_HTTP_ALLOWED_REDIRECT_URIS: ['https://vscode.dev/redirect'],
            MCP_HTTP_SIGN_IN_MAX_AGE_SEC: 43200,
        });
    });

    it('rejects an out-of-range port', () => {
        expect(() => parseSettings({ ...http, MCP_HTTP_PORT: '70000' })).toThrow();
    });
});
