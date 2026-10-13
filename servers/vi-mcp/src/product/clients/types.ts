/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

export interface AuthRequestConfig {
    cachePolicy: 'NoCache' | 'CacheAndReturn' | 'ReturnFromCacheOrCreate';
    cacheTtlSec: number;
    requestTemplate: {
        product_name: string;
        product_version: string;
        license: string;
        user_hash: string;
    };
}

export interface ProductAuthResponse {
    access_token: string;
    refresh_token?: string;
    expires_in: number;
    token_type: 'Bearer';
}

export interface ProductAuthResponseUnifiedDate {
    access_token: string;
    valid_until: number;
    token_type: 'Bearer';
}

export interface ProductCredentials {
    username: string;
    password: string;
}

export interface ProductUserToken {
    accessToken: string;
    refreshToken?: string;
    expiresAt: number;
}

export const USER_TOKEN_EXPIRY_SKEW_MS = 60_000;

export type ProductUserAuth =
    | { kind: 'password'; credentials: ProductCredentials }
    | { kind: 'token'; token: ProductUserToken; renew?: (current: ProductUserToken) => Promise<ProductUserToken> };

export interface ProductRestClientConfig {
    baseURL: string;
    auth?: ProductUserAuth;
    acceptSelfSignedCert: boolean;
}

export interface RequestConfig {
    headers?: Record<string, string>;
    params?: Record<string, string>;
}
