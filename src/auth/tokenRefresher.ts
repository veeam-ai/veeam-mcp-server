/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { createHash } from 'node:crypto';
import { ProductRestClient, ProductUserToken, USER_TOKEN_EXPIRY_SKEW_MS } from '@/product';

interface RefreshResult {
    token: Promise<ProductUserToken>;
    keepUntil: number;
}

export class ProductTokenRefresher {
    private readonly results = new Map<string, RefreshResult>();

    constructor(
        private readonly product: Pick<ProductRestClient, 'refreshUserToken'>,
        private readonly keepMs: number,
    ) {}

    async refresh(refreshToken: string, replacing?: ProductUserToken): Promise<ProductUserToken> {
        this.prune();
        const key = createHash('sha256').update(refreshToken).digest('base64url');

        const cached = this.results.get(key);
        if (cached !== undefined) {
            const token = await cached.token;
            if (token.accessToken !== replacing?.accessToken && token.expiresAt - USER_TOKEN_EXPIRY_SKEW_MS > Date.now()) {
                return token;
            }
            if (this.results.get(key) === cached) {
                this.results.delete(key);
            }
            return this.refresh(token.refreshToken ?? refreshToken);
        }

        const result: RefreshResult = {
            token: this.product
                .refreshUserToken(refreshToken)
                .then((fresh) => ({ ...fresh, refreshToken: fresh.refreshToken ?? refreshToken })),
            keepUntil: Date.now() + this.keepMs,
        };
        this.results.set(key, result);
        result.token.catch(() => {
            if (this.results.get(key) === result) {
                this.results.delete(key);
            }
        });
        return result.token;
    }

    private prune(): void {
        const now = Date.now();
        for (const [key, result] of this.results) {
            if (result.keepUntil <= now) {
                this.results.delete(key);
            }
        }
    }
}
