/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { createHmac, randomBytes } from 'node:crypto';
import type { IncomingMessage } from 'node:http';
import type { AuthInfo } from '@modelcontextprotocol/sdk/server/auth/types.js';
import type { ProductCredentials, ProductRestClient, ProductUserToken } from '@/product';
import { log } from '@/utils/logger';
import { CallerIdentity, describeFailure, rejectedByProduct } from './identity';
import { LOGIN_FAILURE_WINDOW_MS, LoginThrottle } from './loginThrottle';

export const BASIC_CHALLENGE = 'Basic realm="Veeam Intelligence", charset="UTF-8"';

const CREDENTIAL_CACHE_TTL_MS = 5 * 60 * 1000;
const CREDENTIAL_EXPIRY_SKEW_MS = 60 * 1000;

export class AuthError extends Error {
    constructor(
        public readonly status: number,
        message: string,
        public readonly headers: Record<string, string> = {},
    ) {
        super(message);
    }
}

interface VerifiedCredentials {
    validUntil: number;
    token: Promise<ProductUserToken>;
}

export function parseBasicCredentials(header: string | undefined): ProductCredentials | undefined {
    const match = /^Basic\s+([A-Za-z0-9+/=]+)\s*$/i.exec(header ?? '');
    if (match === null) {
        return undefined;
    }

    const decoded = Buffer.from(match[1], 'base64').toString('utf8');
    const separator = decoded.indexOf(':');
    if (separator <= 0 || separator === decoded.length - 1) {
        return undefined;
    }
    return { username: decoded.slice(0, separator), password: decoded.slice(separator + 1) };
}

export class BasicAuthenticator {
    private readonly verified = new Map<string, VerifiedCredentials>();
    private readonly keySecret = randomBytes(32);

    constructor(
        private readonly product: Pick<ProductRestClient, 'requestUserToken'>,
        private readonly throttle: LoginThrottle,
    ) {}

    async authenticate(req: IncomingMessage, address: string): Promise<AuthInfo> {
        const credentials = parseBasicCredentials(req.headers.authorization);
        if (credentials === undefined) {
            throw new AuthError(401, 'Unauthorized: send your Veeam user name and password with Basic authentication', {
                'WWW-Authenticate': BASIC_CHALLENGE,
            });
        }

        const key = this.keyOf(credentials);
        const verified = this.isVerified(key);
        if (!verified && this.throttle.isLocked(address)) {
            throw new AuthError(429, 'Too many failed sign-in attempts. Try again later.', {
                'Retry-After': String(LOGIN_FAILURE_WINDOW_MS / 1000),
            });
        }

        const release = verified ? () => {} : this.throttle.begin(address);
        let token: ProductUserToken;
        try {
            token = await this.verify(key, credentials);
        } catch (error) {
            log.warn(`sign-in of "${credentials.username}" from ${address} failed: ${describeFailure(error)}`);
            if (rejectedByProduct(error)) {
                this.throttle.recordFailure(address);
                throw new AuthError(401, 'Unauthorized: the Veeam user name or password is incorrect', {
                    'WWW-Authenticate': BASIC_CHALLENGE,
                });
            }
            throw new AuthError(502, `Signing in to the Veeam product failed (${describeFailure(error)})`);
        } finally {
            release();
        }

        const identity: CallerIdentity = {
            username: credentials.username,
            owner: `basic:${key}`,
            productAuth: { kind: 'token', token, renew: (current) => this.renew(key, credentials, current) },
        };
        return { token: '', clientId: credentials.username, scopes: [], extra: { identity } };
    }

    prune(): void {
        const now = Date.now();
        for (const [key, entry] of this.verified) {
            if (entry.validUntil <= now) {
                this.verified.delete(key);
            }
        }
    }

    private keyOf({ username, password }: ProductCredentials): string {
        return createHmac('sha256', this.keySecret).update(`${username}\0${password}`).digest('base64url');
    }

    private isVerified(key: string): boolean {
        const cached = this.verified.get(key);
        return cached !== undefined && cached.validUntil > Date.now();
    }

    private async renew(key: string, credentials: ProductCredentials, current: ProductUserToken): Promise<ProductUserToken> {
        const cached = this.verified.get(key);
        if (cached !== undefined) {
            const token = await cached.token.catch(() => undefined);
            if (
                token !== undefined &&
                token.accessToken !== current.accessToken &&
                token.expiresAt - CREDENTIAL_EXPIRY_SKEW_MS > Date.now()
            ) {
                return token;
            }
            if (this.verified.get(key) === cached) {
                this.verified.delete(key);
            }
        }
        return this.verify(key, credentials);
    }

    private verify(key: string, credentials: ProductCredentials): Promise<ProductUserToken> {
        const cached = this.verified.get(key);
        if (cached !== undefined && cached.validUntil > Date.now()) {
            return cached.token;
        }

        const entry: VerifiedCredentials = { validUntil: Number.POSITIVE_INFINITY, token: this.product.requestUserToken(credentials) };
        entry.token.then(
            ({ expiresAt }) => {
                entry.validUntil = Math.min(expiresAt - CREDENTIAL_EXPIRY_SKEW_MS, Date.now() + CREDENTIAL_CACHE_TTL_MS);
            },
            () => {
                if (this.verified.get(key) === entry) {
                    this.verified.delete(key);
                }
            },
        );
        this.verified.set(key, entry);
        return entry.token;
    }
}
