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

const TOKEN = 'a'.repeat(32);

describe('transport settings', () => {
    it('defaults to stdio so existing client configurations keep working', () => {
        expect(parseSettings(product).MCP_TRANSPORT).toBe('stdio');
    });

    it('defaults the HTTP endpoint to loopback on port 8080 without a token', () => {
        const settings = parseSettings({ ...product, MCP_TRANSPORT: 'HTTP' });

        expect(settings).toMatchObject({ MCP_TRANSPORT: 'http', MCP_HTTP_HOST: '127.0.0.1', MCP_HTTP_PORT: 8080 });
        expect(settings.MCP_HTTP_AUTH_TOKEN).toBeUndefined();
    });

    it('requires a token when the HTTP endpoint listens beyond loopback', () => {
        expect(() => parseSettings({ ...product, MCP_TRANSPORT: 'http', MCP_HTTP_HOST: '0.0.0.0' })).toThrow(
            /MCP_HTTP_AUTH_TOKEN is required/,
        );
        expect(
            parseSettings({ ...product, MCP_TRANSPORT: 'http', MCP_HTTP_HOST: '0.0.0.0', MCP_HTTP_AUTH_TOKEN: TOKEN }).MCP_HTTP_HOST,
        ).toBe('0.0.0.0');
    });

    it('does not require a token in stdio mode whatever the HTTP host says', () => {
        expect(parseSettings({ ...product, MCP_HTTP_HOST: '0.0.0.0' }).MCP_TRANSPORT).toBe('stdio');
    });

    it('rejects a short token', () => {
        expect(() => parseSettings({ ...product, MCP_TRANSPORT: 'http', MCP_HTTP_AUTH_TOKEN: 'short' })).toThrow(/at least 32 characters/);
    });

    it('rejects an unknown transport', () => {
        expect(() => parseSettings({ ...product, MCP_TRANSPORT: 'sse' })).toThrow();
    });

    it('rejects a TLS certificate without its key', () => {
        expect(() => parseSettings({ ...product, MCP_TRANSPORT: 'http', MCP_HTTP_TLS_CERT_FILE: '/certs/server.crt' })).toThrow(
            /must be set together/,
        );
    });

    it('rejects an idle timeout that would close sessions with actions still waiting for approval', () => {
        expect(() =>
            parseSettings({
                ...product,
                MCP_TRANSPORT: 'http',
                ACTION_CONFIRMATION_TIMEOUT_SEC: '600',
                MCP_HTTP_SESSION_IDLE_TIMEOUT_SEC: '300',
            }),
        ).toThrow(/must not be shorter than ACTION_CONFIRMATION_TIMEOUT_SEC/);
    });

    it('parses the allowed hosts list case-insensitively and ignores blanks', () => {
        const settings = parseSettings({ ...product, MCP_TRANSPORT: 'http', MCP_HTTP_ALLOWED_HOSTS: ' MCP.Example.test, ,localhost ' });

        expect(settings.MCP_HTTP_ALLOWED_HOSTS).toEqual(['mcp.example.test', 'localhost']);
    });

    it('rejects an out-of-range port', () => {
        expect(() => parseSettings({ ...product, MCP_TRANSPORT: 'http', MCP_HTTP_PORT: '70000' })).toThrow();
    });
});
