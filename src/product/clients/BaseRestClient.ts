/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { ProductRestClient } from '../ProductRestClient';
import {
    ProductAuthResponse,
    ProductAuthResponseUnifiedDate,
    ProductCredentials,
    ProductRestClientConfig,
    ProductUserAuth,
    ProductUserToken,
    RequestConfig,
    USER_TOKEN_EXPIRY_SKEW_MS,
} from './types';
import { ServiceInfo, ChatBotAuthResponse, CommonInvokeConfig, ToolCallResult } from '@/common/types';
import { createSortFindParams } from '@/utils';

import axios, { AxiosInstance, AxiosResponse } from 'axios';
import https from 'node:https';
import { mergeUrlParts } from '@/utils/url';
import safeStringify from '@/utils/safeStringify';

export abstract class BaseRestClient implements ProductRestClient {
    protected readonly config: ProductRestClientConfig;
    protected readonly client: AxiosInstance;
    protected abstract readonly userTokenPath: string;

    private accessToken: string | null = null;
    private tokenExpirationTime: number | null = null;
    private auth: ProductUserAuth | undefined;

    constructor(config: ProductRestClientConfig) {
        this.config = config;
        this.auth = config.auth;

        const httpsAgent = new https.Agent({
            rejectUnauthorized: !this.config.acceptSelfSignedCert,
        });

        this.client = axios.create({
            httpsAgent,
            // Bound every REST call so an unreachable or black-holed host fails within a
            // predictable time instead of hanging until the OS TCP timeout.
            timeout: 30_000,
        });
    }

    abstract getServiceInfo(): Promise<ServiceInfo>;
    abstract authenticateChatService(): Promise<ChatBotAuthResponse>;
    protected abstract authenticateProductRest(renewUserToken: boolean): Promise<ProductAuthResponseUnifiedDate>;

    async requestUserToken({ username, password }: ProductCredentials): Promise<ProductUserToken> {
        return this.postTokenGrant({ grant_type: 'password', username, password });
    }

    async refreshUserToken(refreshToken: string): Promise<ProductUserToken> {
        return this.postTokenGrant({ grant_type: 'refresh_token', refresh_token: refreshToken });
    }

    private async postTokenGrant(grant: Record<string, string>): Promise<ProductUserToken> {
        const response = await this.client.post<ProductAuthResponse>(
            mergeUrlParts(this.config.baseURL, this.userTokenPath),
            new URLSearchParams(grant).toString(),
            { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } },
        );

        const { access_token, refresh_token, expires_in } = response.data;
        return { accessToken: access_token, refreshToken: refresh_token, expiresAt: Date.now() + expires_in * 1000 };
    }

    updateUserAuth(auth: ProductUserAuth): void {
        const current = this.auth;
        if (current?.kind === 'token' && auth.kind === 'token' && current.token.expiresAt > auth.token.expiresAt) {
            this.auth = { ...auth, token: current.token };
            return;
        }
        this.auth = auth;
    }

    protected async currentUserToken(forceRenewal = false): Promise<ProductUserToken> {
        const auth = this.auth;
        if (auth === undefined) {
            throw new Error('No Veeam credentials are available for this request');
        }
        if (auth.kind === 'password') {
            return this.requestUserToken(auth.credentials);
        }

        const current = auth.token;
        if (!forceRenewal && current.expiresAt - USER_TOKEN_EXPIRY_SKEW_MS > Date.now()) {
            return current;
        }

        let renewed: ProductUserToken;
        if (auth.renew !== undefined) {
            renewed = await auth.renew(current);
        } else if (current.refreshToken !== undefined) {
            renewed = await this.refreshUserToken(current.refreshToken);
        } else {
            throw new Error('The Veeam sign-in has expired. Sign in again from the MCP client.');
        }

        const token = { ...renewed, refreshToken: renewed.refreshToken ?? current.refreshToken };
        if (this.auth === auth) {
            this.auth = { ...auth, token };
        }
        return token;
    }

    async getToolCallData(config: CommonInvokeConfig): Promise<ToolCallResult> {
        if (config.tool_name !== 'fetch_data_from_endpoint') {
            return {
                status: 'error',
                data: { message: `Failed to provide Veeam Intelligence response. Unsupported client tool ${String(config.tool_name)}` },
            };
        }

        const { endpoint_path, query_params, method, body, headers } = config.parameters;
        const query = createSortFindParams(query_params ?? {});
        let url = endpoint_path;

        if (query.size > 0) {
            url = `${url}?${query.toString()}`;
        }

        try {
            const response = await this.requestRaw({ method, url, data: body, headers });
            const ok = response.status >= 200 && response.status < 300;

            return {
                status: ok ? 'success' : 'error',
                data: { status: response.status, body: response.data },
            };
        } catch (err: any) {
            return {
                status: 'error',
                data: { message: `Failed to call ${method} ${endpoint_path}: ${err.message || 'Unknown error'}` },
            };
        }
    }

    protected async get<T>(url: string, config?: RequestConfig): Promise<T> {
        return this.request<T>({ ...config, method: 'GET', url });
    }

    protected async post<T>(url: string, data?: any, config?: RequestConfig): Promise<T> {
        return this.request<T>({ ...config, method: 'POST', url, data });
    }

    private async prepareRequest(config: { url: string; headers?: Record<string, string> }) {
        if (this.shouldRefreshToken()) {
            await this.authenticate();
        }

        // Build full URL
        const normalizedUrl = (config.url || '').trim();
        const isAbsoluteUrl = /^https?:\/\//i.test(normalizedUrl);
        const url = isAbsoluteUrl ? normalizedUrl : mergeUrlParts(this.config.baseURL, normalizedUrl);

        // Build headers
        const headers: Record<string, string> = {
            'Content-Type': 'application/json',
            ...config.headers,
        };

        this.applyAuthHeader(headers);

        return { url, headers };
    }

    private applyAuthHeader(headers: Record<string, string>): void {
        if (this.accessToken) {
            headers['Authorization'] = `Bearer ${this.accessToken}`;
        }
    }

    private async requestRaw(config: {
        method: string;
        url: string;
        data?: any;
        headers?: Record<string, string>;
        params?: Record<string, string>;
    }): Promise<AxiosResponse<unknown>> {
        const { url, headers } = await this.prepareRequest(config);
        const send = () =>
            this.client.request<unknown>({
                method: config.method,
                url,
                data: config.data,
                headers,
                params: config.params,
                validateStatus: () => true,
            });

        const response = await send();
        if (response.status !== 401) {
            return response;
        }

        await this.authenticate(true);
        this.applyAuthHeader(headers);
        return send();
    }

    // Generic request method with automatic token handling
    private async request<T>(config: {
        method: string;
        url: string;
        data?: any;
        headers?: Record<string, string>;
        params?: Record<string, string>;
    }): Promise<T> {
        const { url, headers } = await this.prepareRequest(config);

        try {
            const response = await this.client.request<T>({
                method: config.method,
                url,
                data: config.data,
                headers,
                params: config.params,
            });

            return response.data;
        } catch (error: any) {
            // Handle 401 - retry with new token
            if (error.response?.status === 401) {
                await this.authenticate(true);
                this.applyAuthHeader(headers);
                const retryResponse = await this.client.request<T>({
                    method: config.method,
                    url,
                    data: config.data,
                    headers,
                    params: config.params,
                });

                return retryResponse.data;
            }

            // Extract detailed error information
            let errorMessage = `Request failed: ${error.message}`;

            // Include cause details if available
            if (error.cause) {
                errorMessage += this.formatErrorCause(error.cause);
            } else if (error.response) {
                errorMessage = `Request failed: ${error.response.status} ${error.response.statusText}`;
            }

            throw new Error(errorMessage, { cause: error });
        }
    }

    // Authentication
    private shouldRefreshToken(): boolean {
        if (!this.accessToken || !this.tokenExpirationTime) {
            return true;
        }

        const bufferTimeMS = 14 * 60 * 1000; // 14 minutes
        return Date.now() + bufferTimeMS >= this.tokenExpirationTime;
    }

    private async authenticate(renewUserToken = false): Promise<void> {
        try {
            const data = await this.authenticateProductRest(renewUserToken);
            this.accessToken = data.access_token;
            this.tokenExpirationTime = data.valid_until;
        } catch (error: any) {
            console.error('Authentication failed:', error.message || error);

            if (axios.isAxiosError(error)) {
                const errorMessage =
                    'Axios error during authentication.\n' +
                    `Request endpoint: ${error.config?.method} ${error.config?.url}\n` +
                    `Response status: ${error.response?.status} ${error.response?.statusText}\n` +
                    `Response data: ${safeStringify(error.response?.data)}\n` +
                    `Error message: ${error.message}`;

                console.error(errorMessage);
                throw new Error(errorMessage, { cause: error });
            }

            // Extract detailed error information
            let errorMessage = `Authentication failed: ${error.message}`;

            // Include cause details if available
            if (error.cause) {
                errorMessage += ' ' + this.formatErrorCause(error.cause);
            } else if (error.response) {
                errorMessage += ` ${error.response.status} ${error.response.statusText}`;
            } else if (error.message && error.message.toLowerCase().includes('authentication failed')) {
                errorMessage +=
                    this.auth?.kind === 'password'
                        ? ' Please verify that ADMIN_USERNAME and ADMIN_PASSWORD are correct.'
                        : ' Sign in again from the MCP client.';
            }

            throw new Error(errorMessage, { cause: error });
        }
    }

    private formatErrorCause(cause: any): string {
        if (['ENOTFOUND', 'ECONNREFUSED', 'ETIMEDOUT', 'UND_ERR_CONNECT_TIMEOUT'].includes(cause.code)) {
            return `Network error: ${cause.code} ${cause.message || ''}. Validate that WEB_URL contains correct hostname and port for Rest API.`;
        } else if (['DEPTH_ZERO_SELF_SIGNED_CERT', 'CERT_HAS_EXPIRED', 'UNABLE_TO_VERIFY_LEAF_SIGNATURE'].includes(cause.code)) {
            return `SSL error: ${cause.code}. If Veeam product uses self signed certificate, try setting ACCEPT_SELF_SIGNED_CERT=true.`;
        } else if (cause.code) {
            return `Unexpected network error: ${cause.code}: ${cause.message || ''}`;
        } else {
            return `Unexpected network error: ${cause.message || cause}`;
        }
    }
}
