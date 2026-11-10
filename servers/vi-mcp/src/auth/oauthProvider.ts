/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import type { Request, Response } from 'express';
import type { AuthorizationParams, OAuthServerProvider } from '@modelcontextprotocol/sdk/server/auth/provider.js';
import type { OAuthRegisteredClientsStore } from '@modelcontextprotocol/sdk/server/auth/clients.js';
import type { AuthInfo } from '@modelcontextprotocol/sdk/server/auth/types.js';
import {
    InvalidClientMetadataError,
    InvalidGrantError,
    InvalidTargetError,
    InvalidTokenError,
    ServerError,
} from '@modelcontextprotocol/sdk/server/auth/errors.js';
import { redirectUriMatches } from '@modelcontextprotocol/sdk/server/auth/handlers/authorize.js';
import type { OAuthClientInformationFull, OAuthTokens } from '@modelcontextprotocol/sdk/shared/auth.js';
import { ProductRestClient, ProductUserToken, USER_TOKEN_EXPIRY_SKEW_MS } from '@/product';
import { isLoopbackHost } from '@/config/settings';
import { log } from '@/utils/logger';
import { CallerIdentity, describeFailure, rejectedByProduct } from './identity';
import { ProductTokenRefresher } from './tokenRefresher';
import { nowSec, TokenSealer } from './tokenSealer';
import { LoginPageModel, sendLoginPage } from './loginPage';

export const LOGIN_PATH = '/login';

const AUTHORIZE_REQUEST_TTL_SEC = 600;
const AUTHORIZATION_CODE_TTL_SEC = 60;

export interface VeeamOAuthProviderOptions {
    sealer: TokenSealer;
    product: Pick<ProductRestClient, 'requestUserToken' | 'refreshUserToken'>;
    productName: string;
    resourceUrl: URL;
    signInMaxAgeSec: number;
    allowedRedirectUris: string[];
}

export type LoginOutcome = 'signed-in' | 'rejected' | 'failed';

interface ClientPayload {
    exp?: number;
    redirectUris: string[];
    clientName?: string;
}

interface AuthorizePayload {
    exp: number;
    clientId: string;
    redirectUri: string;
    codeChallenge: string;
    state?: string;
}

interface SignInGrant {
    clientId: string;
    subject: string;
    productTokens: ProductUserToken;
    authTime: number;
}

interface CodePayload extends SignInGrant {
    exp: number;
    redirectUri: string;
    codeChallenge: string;
}

interface AccessPayload {
    exp: number;
    clientId: string;
    subject: string;
    productTokens: ProductUserToken;
    resource: string;
}

interface RefreshPayload {
    exp: number;
    clientId: string;
    subject: string;
    refreshToken: string;
    authTime: number;
}

function sameResource(a: URL | string, b: URL): boolean {
    const strip = (href: string) => href.replace(/\/+$/, '');
    return strip(new URL(a).href) === strip(b.href);
}

export class VeeamOAuthProvider implements OAuthServerProvider {
    readonly clientsStore: OAuthRegisteredClientsStore;
    private readonly refresher: ProductTokenRefresher;

    constructor(private readonly options: VeeamOAuthProviderOptions) {
        this.refresher = new ProductTokenRefresher(options.product, options.signInMaxAgeSec * 1000);
        this.clientsStore = {
            getClient: (clientId) => this.getClient(clientId),
            registerClient: (client) => this.registerClient(client),
        };
    }

    private isAllowedRedirect(uri: string): boolean {
        if (this.options.allowedRedirectUris.includes(uri)) {
            return true;
        }
        try {
            const url = new URL(uri);
            return (url.protocol === 'http:' || url.protocol === 'https:') && isLoopbackHost(url.hostname);
        } catch {
            return false;
        }
    }

    private registerClient(client: Omit<OAuthClientInformationFull, 'client_id' | 'client_id_issued_at'>): OAuthClientInformationFull {
        const rejected = client.redirect_uris.filter((uri) => !this.isAllowedRedirect(uri));
        if (rejected.length > 0) {
            throw new InvalidClientMetadataError(
                `redirect_uri not allowed: ${rejected.join(', ')}. Loopback redirect URIs are always accepted; ` +
                    'others must be listed in MCP_HTTP_ALLOWED_REDIRECT_URIS.',
            );
        }

        const { client_secret: _secret, client_secret_expires_at: _secretExpiresAt, ...metadata } = client;
        const payload: ClientPayload = { redirectUris: client.redirect_uris, clientName: client.client_name };

        return {
            ...metadata,
            client_id: this.options.sealer.seal('client', payload),
            client_id_issued_at: nowSec(),
            token_endpoint_auth_method: 'none',
            grant_types: ['authorization_code', 'refresh_token'],
            response_types: ['code'],
        };
    }

    private getClient(clientId: string): OAuthClientInformationFull | undefined {
        const payload = this.options.sealer.unseal<ClientPayload>('client', clientId);
        const redirectUris = payload?.redirectUris.filter((uri) => this.isAllowedRedirect(uri)) ?? [];
        if (payload === undefined || redirectUris.length === 0) {
            return undefined;
        }

        return {
            client_id: clientId,
            client_name: payload.clientName,
            redirect_uris: redirectUris,
            token_endpoint_auth_method: 'none',
            grant_types: ['authorization_code', 'refresh_token'],
            response_types: ['code'],
        };
    }

    private pageModel(client: OAuthClientInformationFull | undefined, redirectUri: string): LoginPageModel {
        return { productName: this.options.productName, clientName: client?.client_name ?? 'An MCP client', redirectUri };
    }

    async authorize(client: OAuthClientInformationFull, params: AuthorizationParams, res: Response): Promise<void> {
        if (params.resource !== undefined && !sameResource(params.resource, this.options.resourceUrl)) {
            throw new InvalidTargetError(`This server only issues tokens for ${this.options.resourceUrl.href}`);
        }

        const request: AuthorizePayload = {
            exp: nowSec() + AUTHORIZE_REQUEST_TTL_SEC,
            clientId: client.client_id,
            redirectUri: params.redirectUri,
            codeChallenge: params.codeChallenge,
            state: params.state,
        };

        sendLoginPage(res, 200, { ...this.pageModel(client, params.redirectUri), request: this.options.sealer.seal('authorize', request) });
    }

    async handleLogin(req: Request, res: Response): Promise<LoginOutcome> {
        const body = (req.body ?? {}) as Record<string, unknown>;
        const field = (name: string) => (typeof body[name] === 'string' ? body[name] : '');

        const sealedRequest = field('request');
        const pending = this.options.sealer.unseal<AuthorizePayload>('authorize', sealedRequest);
        const client = pending !== undefined ? this.getClient(pending.clientId) : undefined;

        if (
            pending === undefined ||
            client === undefined ||
            !client.redirect_uris.some((registered) => redirectUriMatches(pending.redirectUri, registered))
        ) {
            sendLoginPage(res, 400, {
                productName: this.options.productName,
                error: 'The sign-in request is invalid or has expired. Start the sign-in again from your MCP client.',
            });
            return 'failed';
        }

        const model = { ...this.pageModel(client, pending.redirectUri), request: sealedRequest };
        const username = field('username').trim();
        const password = field('password');

        if (username === '' || password === '') {
            sendLoginPage(res, 400, { ...model, username, error: 'Enter the user name and password.' });
            return 'failed';
        }

        let productTokens: ProductUserToken;
        try {
            productTokens = await this.options.product.requestUserToken({ username, password });
        } catch (error) {
            const rejected = rejectedByProduct(error);
            log.warn(`sign-in of "${username}" failed: ${describeFailure(error)}`);
            sendLoginPage(res, rejected ? 401 : 502, {
                ...model,
                username,
                error: rejected
                    ? 'The user name or password is incorrect.'
                    : `Signing in to ${this.options.productName} failed (${describeFailure(error)}). Try again later.`,
            });
            return rejected ? 'rejected' : 'failed';
        }

        const code: CodePayload = {
            exp: nowSec() + AUTHORIZATION_CODE_TTL_SEC,
            clientId: client.client_id,
            redirectUri: pending.redirectUri,
            codeChallenge: pending.codeChallenge,
            subject: username.toLowerCase(),
            productTokens,
            authTime: nowSec(),
        };

        const target = new URL(pending.redirectUri);
        target.searchParams.set('code', this.options.sealer.seal('code', code));
        if (pending.state !== undefined) {
            target.searchParams.set('state', pending.state);
        }

        log.info(`"${username}" signed in through ${client.client_name ?? 'an unnamed MCP client'}`);
        res.set('Cache-Control', 'no-store').redirect(302, target.href);
        return 'signed-in';
    }

    private codeFor(client: OAuthClientInformationFull, authorizationCode: string): CodePayload {
        const code = this.options.sealer.unseal<CodePayload>('code', authorizationCode);
        if (code === undefined || code.clientId !== client.client_id) {
            throw new InvalidGrantError('Invalid or expired authorization code');
        }
        return code;
    }

    private checkResource(resource: URL | undefined): void {
        if (resource !== undefined && !sameResource(resource, this.options.resourceUrl)) {
            throw new InvalidTargetError(`This server only issues tokens for ${this.options.resourceUrl.href}`);
        }
    }

    async challengeForAuthorizationCode(client: OAuthClientInformationFull, authorizationCode: string): Promise<string> {
        return this.codeFor(client, authorizationCode).codeChallenge;
    }

    async exchangeAuthorizationCode(
        client: OAuthClientInformationFull,
        authorizationCode: string,
        _codeVerifier?: string,
        redirectUri?: string,
        resource?: URL,
    ): Promise<OAuthTokens> {
        const code = this.codeFor(client, authorizationCode);
        if (redirectUri !== undefined && redirectUri !== code.redirectUri) {
            throw new InvalidGrantError('redirect_uri does not match the authorization request');
        }
        this.checkResource(resource);

        return this.issueTokens(code);
    }

    async exchangeRefreshToken(
        client: OAuthClientInformationFull,
        refreshToken: string,
        _scopes?: string[],
        resource?: URL,
    ): Promise<OAuthTokens> {
        const grant = this.options.sealer.unseal<RefreshPayload>('refresh', refreshToken);
        if (grant === undefined || grant.clientId !== client.client_id) {
            throw new InvalidGrantError('Invalid or expired refresh token');
        }
        this.checkResource(resource);

        let fresh: ProductUserToken;
        try {
            fresh = await this.refresher.refresh(grant.refreshToken);
        } catch (error) {
            log.warn(`refreshing the sign-in of "${grant.subject}" failed: ${describeFailure(error)}`);
            if (rejectedByProduct(error)) {
                throw new InvalidGrantError('The Veeam sign-in has expired. Sign in again.');
            }
            throw new ServerError(`Renewing the ${this.options.productName} sign-in failed (${describeFailure(error)})`);
        }

        return this.issueTokens({
            clientId: grant.clientId,
            subject: grant.subject,
            productTokens: { ...fresh, refreshToken: fresh.refreshToken ?? grant.refreshToken },
            authTime: grant.authTime,
        });
    }

    private issueTokens({ clientId, subject, productTokens, authTime }: SignInGrant): OAuthTokens {
        const now = nowSec();
        const signInEnd = authTime + this.options.signInMaxAgeSec;
        const productExp = Math.floor(productTokens.expiresAt / 1000);
        const renewAt = productExp - USER_TOKEN_EXPIRY_SKEW_MS / 1000;
        const exp = Math.min(renewAt > now ? renewAt : productExp, signInEnd);
        if (exp <= now) {
            throw new InvalidGrantError('The Veeam sign-in has expired. Sign in again.');
        }

        const access: AccessPayload = { exp, clientId, subject, productTokens, resource: this.options.resourceUrl.href };
        const tokens: OAuthTokens = {
            access_token: this.options.sealer.seal('access', access),
            token_type: 'Bearer',
            expires_in: exp - now,
        };

        if (productTokens.refreshToken !== undefined) {
            const refresh: RefreshPayload = { exp: signInEnd, clientId, subject, refreshToken: productTokens.refreshToken, authTime };
            tokens.refresh_token = this.options.sealer.seal('refresh', refresh);
        }

        return tokens;
    }

    async verifyAccessToken(token: string): Promise<AuthInfo> {
        const access = this.options.sealer.unseal<AccessPayload>('access', token);
        if (access === undefined || !sameResource(access.resource, this.options.resourceUrl)) {
            throw new InvalidTokenError('Invalid or expired access token');
        }

        const identity: CallerIdentity = {
            username: access.subject,
            owner: `oauth:${JSON.stringify([access.clientId, access.subject])}`,
            productAuth: {
                kind: 'token',
                token: access.productTokens,
                renew: async (current) => {
                    if (current.refreshToken === undefined) {
                        throw new Error('The Veeam sign-in has expired. Sign in again from the MCP client.');
                    }
                    return this.refresher.refresh(current.refreshToken, current);
                },
            },
        };
        return {
            token,
            clientId: access.clientId,
            scopes: [],
            expiresAt: access.exp,
            resource: new URL(access.resource),
            extra: { identity },
        };
    }
}
