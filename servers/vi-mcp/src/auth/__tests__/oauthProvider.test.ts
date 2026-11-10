/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { describe, it, expect, beforeAll, beforeEach, afterEach, jest } from '@jest/globals';
import type { OAuthClientInformationFull } from '@modelcontextprotocol/sdk/shared/auth.js';
import type { ProductUserToken } from '@/product/clients/types';

process.env.PRODUCT_NAME = 'vbr';
process.env.WEB_URL = 'https://vbr.example.test:9419';
process.env.ADMIN_USERNAME = 'x';
process.env.ADMIN_PASSWORD = 'x';

type ProviderModule = typeof import('../oauthProvider');
type SealerModule = typeof import('../tokenSealer');

let VeeamOAuthProvider: ProviderModule['VeeamOAuthProvider'];
let productAuthOf: typeof import('../identity').productAuthOf;
let TokenSealer: SealerModule['TokenSealer'];

beforeAll(async () => {
    ({ VeeamOAuthProvider } = await import('../oauthProvider'));
    ({ productAuthOf } = await import('../identity'));
    ({ TokenSealer } = await import('../tokenSealer'));
});

const RESOURCE = new URL('https://mcp.example.test/mcp');
const SECRET = 's'.repeat(32);

describe('TokenSealer', () => {
    it('round-trips a payload', () => {
        const sealer = TokenSealer.fromSecret(SECRET);

        expect(sealer.unseal('access', sealer.seal('access', { exp: Date.now() / 1000 + 60, value: 1 } as never))).toMatchObject({
            value: 1,
        });
    });

    it('derives the same key from the same secret, so replicas accept each other’s tokens', () => {
        const token = TokenSealer.fromSecret(SECRET).seal('access', {});

        expect(TokenSealer.fromSecret(SECRET).unseal('access', token)).toEqual({});
        expect(TokenSealer.fromSecret('t'.repeat(32)).unseal('access', token)).toBeUndefined();
    });

    it('never accepts a token sealed for another purpose, so a code or refresh token is no access token', () => {
        const sealer = TokenSealer.fromSecret(SECRET);

        expect(sealer.unseal('access', sealer.seal('refresh', {}))).toBeUndefined();
        expect(sealer.unseal('access', sealer.seal('code', {}))).toBeUndefined();
    });

    it('rejects an expired, truncated or altered token', () => {
        const sealer = TokenSealer.fromSecret(SECRET);
        const valid = sealer.seal('access', { exp: Math.floor(Date.now() / 1000) + 60 });
        const flipped = Buffer.from(valid, 'base64url');
        flipped[20] ^= 1;

        expect(sealer.unseal('access', sealer.seal('access', { exp: Math.floor(Date.now() / 1000) - 1 }))).toBeUndefined();
        expect(sealer.unseal('access', valid.slice(0, 20))).toBeUndefined();
        expect(sealer.unseal('access', flipped.toString('base64url'))).toBeUndefined();
    });
});

describe('VeeamOAuthProvider', () => {
    let productTokens: ProductUserToken;
    let stderr: jest.SpiedFunction<typeof process.stderr.write>;
    const requestUserToken = jest.fn(async () => productTokens);
    const refreshUserToken = jest.fn(async (_refreshToken: string) => productTokens);

    function provider(signInMaxAgeSec = 3600, allowedRedirectUris: string[] = []) {
        return new VeeamOAuthProvider({
            sealer: TokenSealer.fromSecret(SECRET),
            product: { requestUserToken, refreshUserToken },
            productName: 'Veeam Backup & Replication',
            resourceUrl: RESOURCE,
            signInMaxAgeSec,
            allowedRedirectUris,
        });
    }

    async function registered(subject: InstanceType<typeof VeeamOAuthProvider>): Promise<OAuthClientInformationFull> {
        return subject.clientsStore.registerClient!({ redirect_uris: ['http://localhost/callback'], client_name: 'Test' });
    }

    /** Runs the login form and returns the authorization code it redirects with. */
    async function codeFor(subject: InstanceType<typeof VeeamOAuthProvider>, client: OAuthClientInformationFull): Promise<string> {
        let page = '';
        await subject.authorize(client, { codeChallenge: 'challenge', redirectUri: 'http://localhost/callback' }, {
            status: () => ({ set: () => ({ send: (html: string) => (page = html) }) }),
        } as never);
        const request = /name="request" value="([^"]+)"/.exec(page)![1];

        let location = '';
        await subject.handleLogin(
            { body: { request, username: 'Alice', password: 'pw' } } as never,
            {
                set: () => ({ redirect: (_status: number, url: string) => (location = url) }),
            } as never,
        );
        return new URL(location).searchParams.get('code')!;
    }

    beforeEach(() => {
        productTokens = { accessToken: 'vbr-access', refreshToken: 'vbr-refresh', expiresAt: Date.now() + 900_000 };
        requestUserToken.mockClear();
        refreshUserToken.mockClear();
        stderr = jest.spyOn(process.stderr, 'write').mockImplementation(() => true);
    });

    afterEach(() => {
        stderr.mockRestore();
    });

    it('issues an access token that expires a minute before the Veeam token and carries the Veeam identity', async () => {
        const subject = provider();
        const client = await registered(subject);

        const tokens = await subject.exchangeAuthorizationCode(client, await codeFor(subject, client));
        const info = await subject.verifyAccessToken(tokens.access_token);

        expect(tokens.expires_in).toBeGreaterThan(830);
        expect(tokens.expires_in).toBeLessThanOrEqual(840);
        expect(info).toMatchObject({ clientId: client.client_id, resource: RESOURCE, extra: { identity: { username: 'alice' } } });
        expect(productAuthOf(info)).toMatchObject({ kind: 'token', token: productTokens });
    });

    it('never lets a sign-in outlive the configured maximum age', async () => {
        const subject = provider(120);
        const client = await registered(subject);

        const tokens = await subject.exchangeAuthorizationCode(client, await codeFor(subject, client));

        expect(tokens.expires_in).toBeLessThanOrEqual(120);
    });

    it('issues no refresh token when the product returned none', async () => {
        productTokens = { accessToken: 'vbr-access', expiresAt: Date.now() + 900_000 };
        const subject = provider();
        const client = await registered(subject);

        const tokens = await subject.exchangeAuthorizationCode(client, await codeFor(subject, client));

        expect(tokens.refresh_token).toBeUndefined();
    });

    it('keeps the previous Veeam refresh token when a refresh does not rotate it', async () => {
        const subject = provider();
        const client = await registered(subject);
        const first = await subject.exchangeAuthorizationCode(client, await codeFor(subject, client));
        productTokens = { accessToken: 'vbr-access-2', expiresAt: Date.now() + 900_000 };

        const renewed = await subject.exchangeRefreshToken(client, first.refresh_token!);
        await subject.exchangeRefreshToken(client, renewed.refresh_token!);

        expect(refreshUserToken).toHaveBeenLastCalledWith('vbr-refresh');
    });

    it('lets the client renew with its old refresh token after a tool call already renewed and rotated the Veeam token', async () => {
        const subject = provider();
        const client = await registered(subject);
        const first = await subject.exchangeAuthorizationCode(client, await codeFor(subject, client));
        const auth = productAuthOf(await subject.verifyAccessToken(first.access_token));
        productTokens = { accessToken: 'vbr-access-2', refreshToken: 'vbr-refresh-2', expiresAt: Date.now() + 900_000 };

        const renewedInCall = auth?.kind === 'token' ? await auth.renew!(auth.token) : undefined;
        const renewedByClient = await subject.exchangeRefreshToken(client, first.refresh_token!);

        expect(renewedInCall).toMatchObject({ accessToken: 'vbr-access-2' });
        expect(productAuthOf(await subject.verifyAccessToken(renewedByClient.access_token))).toMatchObject({
            token: { accessToken: 'vbr-access-2', refreshToken: 'vbr-refresh-2' },
        });
        expect(refreshUserToken).toHaveBeenCalledTimes(1);
    });

    it('renews the Veeam token once when several calls need it at the same time', async () => {
        const subject = provider();
        const client = await registered(subject);
        const first = await subject.exchangeAuthorizationCode(client, await codeFor(subject, client));
        const auth = productAuthOf(await subject.verifyAccessToken(first.access_token));
        if (auth?.kind !== 'token') {
            throw new Error('expected a token identity');
        }
        productTokens = { accessToken: 'vbr-access-2', refreshToken: 'vbr-refresh-2', expiresAt: Date.now() + 900_000 };

        await Promise.all([auth.renew!(auth.token), auth.renew!(auth.token), subject.exchangeRefreshToken(client, first.refresh_token!)]);

        expect(refreshUserToken).toHaveBeenCalledTimes(1);
    });

    it('asks the product again when it rejected the token a previous renewal returned', async () => {
        const subject = provider();
        const client = await registered(subject);
        const first = await subject.exchangeAuthorizationCode(client, await codeFor(subject, client));
        const auth = productAuthOf(await subject.verifyAccessToken(first.access_token));
        if (auth?.kind !== 'token') {
            throw new Error('expected a token identity');
        }
        productTokens = { accessToken: 'vbr-access-2', expiresAt: Date.now() + 900_000 };
        const renewed = await auth.renew!(auth.token);
        productTokens = { accessToken: 'vbr-access-3', expiresAt: Date.now() + 900_000 };

        const afterRejection = await auth.renew!(renewed);

        expect(renewed.refreshToken).toBe('vbr-refresh');
        expect(afterRejection.accessToken).toBe('vbr-access-3');
        expect(refreshUserToken).toHaveBeenCalledTimes(2);
    });

    it('refuses a token request for another resource', async () => {
        const subject = provider();
        const client = await registered(subject);
        const code = await codeFor(subject, client);

        await expect(
            subject.exchangeAuthorizationCode(client, code, undefined, undefined, new URL('https://other.example.test/mcp')),
        ).rejects.toThrow(/only issues tokens for/);
    });

    it('does not accept a refresh token as an access token', async () => {
        const subject = provider();
        const client = await registered(subject);
        const tokens = await subject.exchangeAuthorizationCode(client, await codeFor(subject, client));

        await expect(subject.verifyAccessToken(tokens.refresh_token!)).rejects.toThrow(/Invalid or expired access token/);
    });

    it('forgets a registered client once its redirect URI is no longer allowed', async () => {
        const client = await provider(3600, ['https://vscode.dev/redirect']).clientsStore.registerClient!({
            redirect_uris: ['https://vscode.dev/redirect'],
        });

        expect(await provider(3600, ['https://vscode.dev/redirect']).clientsStore.getClient(client.client_id)).toBeDefined();
        expect(await provider(3600, []).clientsStore.getClient(client.client_id)).toBeUndefined();
    });
});
