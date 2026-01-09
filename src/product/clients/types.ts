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

export interface AuthResponse {
    access_token: string;
    expires_in: number;
    token_type: 'Bearer';
}

export interface ProductRestClientConfig {
    baseURL: string;
    username: string;
    password: string;
    authUrl: string;
    acceptSelfSignedCert: boolean;
}

export interface RequestConfig {
    headers?: Record<string, string>;
    params?: Record<string, string>;
}
