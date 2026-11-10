/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { describe, it, expect, beforeAll, afterAll, beforeEach, afterEach, jest } from '@jest/globals';
import http from 'node:http';
import { AddressInfo } from 'node:net';
import { VspcRestClient } from '../VspcRestClient';
import type { ProductUserAuth } from '../types';

const SERVICE_INFO_PATH = '/plugins/acfa09fe128645f09cd5b794d9d183d0/api/v1/serviceInfo';

let server: http.Server;
let baseURL: string;
let tokenRequests: Array<Record<string, string>>;
let serviceInfoAuthorization: string[];
let consoleError: jest.SpiedFunction<typeof console.error>;

beforeAll(async () => {
    server = http.createServer((req, res) => {
        let body = '';
        req.on('data', (chunk) => (body += chunk));
        req.on('end', () => {
            if (req.method === 'POST' && req.url === '/api/v3/token') {
                const form = Object.fromEntries(new URLSearchParams(body));
                tokenRequests.push(form);
                const accessToken = form.grant_type === 'password' ? `token-${form.username}` : `renewed-${form.refresh_token}`;
                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(
                    JSON.stringify({ access_token: accessToken, refresh_token: 'next-refresh', expires_in: 900, token_type: 'Bearer' }),
                );
                return;
            }
            if (req.method === 'GET' && req.url === SERVICE_INFO_PATH) {
                serviceInfoAuthorization.push(req.headers.authorization ?? '');
                if (req.headers.authorization === 'Bearer revoked') {
                    res.writeHead(401).end();
                    return;
                }
                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ chatbotApiUrl: 'https://vi.example.test' }));
                return;
            }
            res.writeHead(404).end();
        });
    });
    await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
    baseURL = `http://127.0.0.1:${(server.address() as AddressInfo).port}/`;
});

afterAll(async () => {
    await new Promise<void>((resolve) => server.close(() => resolve()));
});

beforeEach(() => {
    tokenRequests = [];
    serviceInfoAuthorization = [];
    consoleError = jest.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
    consoleError.mockRestore();
});

function client(auth: ProductUserAuth | undefined): VspcRestClient {
    return new VspcRestClient({ baseURL, auth, acceptSelfSignedCert: false });
}

describe('BaseRestClient user authentication', () => {
    it('signs in as the user it was created for', async () => {
        await client({ kind: 'password', credentials: { username: 'alice', password: 'pw' } }).getServiceInfo();

        expect(tokenRequests).toEqual([{ username: 'alice', password: 'pw', grant_type: 'password' }]);
        expect(serviceInfoAuthorization).toEqual(['Bearer token-alice']);
    });

    it("uses the signed-in user's token as is while it is valid, without asking for a password", async () => {
        await client({ kind: 'token', token: { accessToken: 'alice-token', expiresAt: Date.now() + 600_000 } }).getServiceInfo();

        expect(tokenRequests).toEqual([]);
        expect(serviceInfoAuthorization).toEqual(['Bearer alice-token']);
    });

    it("renews an expiring user token with the user's refresh token", async () => {
        await client({
            kind: 'token',
            token: { accessToken: 'old', refreshToken: 'alice-refresh', expiresAt: Date.now() + 10_000 },
        }).getServiceInfo();

        expect(tokenRequests).toEqual([{ grant_type: 'refresh_token', refresh_token: 'alice-refresh' }]);
        expect(serviceInfoAuthorization).toEqual(['Bearer renewed-alice-refresh']);
    });

    it('asks the user to sign in again once the token expired and cannot be renewed', async () => {
        const expired = client({ kind: 'token', token: { accessToken: 'old', expiresAt: Date.now() - 1 } });

        await expect(expired.getServiceInfo()).rejects.toThrow(/sign-in has expired/);
        expect(serviceInfoAuthorization).toEqual([]);
    });

    it('renews a user token the product rejects instead of retrying with the same token', async () => {
        await client({
            kind: 'token',
            token: { accessToken: 'revoked', refreshToken: 'alice-refresh', expiresAt: Date.now() + 600_000 },
        }).getServiceInfo();

        expect(tokenRequests).toEqual([{ grant_type: 'refresh_token', refresh_token: 'alice-refresh' }]);
        expect(serviceInfoAuthorization).toEqual(['Bearer revoked', 'Bearer renewed-alice-refresh']);
    });

    it('renews through the renewal the caller provided, so the caller sees the new token', async () => {
        const renew = jest.fn(async () => ({ accessToken: 'from-caller', expiresAt: Date.now() + 600_000 }));

        await client({
            kind: 'token',
            token: { accessToken: 'old', refreshToken: 'r', expiresAt: Date.now() - 1 },
            renew,
        }).getServiceInfo();

        expect(renew).toHaveBeenCalledTimes(1);
        expect(tokenRequests).toEqual([]);
        expect(serviceInfoAuthorization).toEqual(['Bearer from-caller']);
    });

    it('keeps a newer token it renewed itself when handed an older one', async () => {
        const subject = client({ kind: 'token', token: { accessToken: 'newer', expiresAt: Date.now() + 600_000 } });

        subject.updateUserAuth({ kind: 'token', token: { accessToken: 'older', expiresAt: Date.now() + 300_000 } });
        await subject.getServiceInfo();

        expect(serviceInfoAuthorization).toEqual(['Bearer newer']);
    });

    it('takes a newer token handed in later', async () => {
        const subject = client({ kind: 'token', token: { accessToken: 'older', expiresAt: Date.now() + 300_000 } });

        subject.updateUserAuth({ kind: 'token', token: { accessToken: 'newer', expiresAt: Date.now() + 600_000 } });
        await subject.getServiceInfo();

        expect(serviceInfoAuthorization).toEqual(['Bearer newer']);
    });

    it('refuses to call the product without any Veeam account', async () => {
        await expect(client(undefined).getServiceInfo()).rejects.toThrow(/No Veeam credentials/);
        expect(tokenRequests).toEqual([]);
    });

    it('checks arbitrary credentials and reports when the sign-in expires', async () => {
        const before = Date.now();

        const token = await client(undefined).requestUserToken({ username: 'bob', password: 'pw' });

        expect(token).toMatchObject({ accessToken: 'token-bob', refreshToken: 'next-refresh' });
        expect(token.expiresAt).toBeGreaterThanOrEqual(before + 900_000);
    });
});
