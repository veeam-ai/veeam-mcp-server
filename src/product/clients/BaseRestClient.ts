/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { ProductRestClient } from '../ProductRestClient';
import { ProductAuthResponseUnifiedDate, ProductRestClientConfig, RequestConfig } from './types';
import { ServiceInfo, ChatBotAuthResponse, CommonInvokeConfig, ToolCallResult } from '@/common/types';
import { createSortFindParams } from '@/utils';

import axios, { AxiosInstance, AxiosResponse } from 'axios';
import https from 'node:https';
import { mergeUrlParts } from '@/utils/url';
import safeStringify from '@/utils/safeStringify';

export abstract class BaseRestClient implements ProductRestClient {
    protected readonly config: ProductRestClientConfig;
    protected readonly client: AxiosInstance;

    private accessToken: string | null = null;
    private tokenExpirationTime: number | null = null;

    constructor(config: ProductRestClientConfig) {
        this.config = config;

        const httpsAgent = new https.Agent({
            rejectUnauthorized: !this.config.acceptSelfSignedCert,
        });

        this.client = axios.create({
            httpsAgent,
        });
    }

    abstract getServiceInfo(): Promise<ServiceInfo>;
    abstract authenticateChatService(): Promise<ChatBotAuthResponse>;
    protected abstract authenticateProductRest(): Promise<ProductAuthResponseUnifiedDate>;

    async getToolCallData(config: CommonInvokeConfig): Promise<ToolCallResult> {
        if (config.tool_name !== 'fetch_data_from_endpoint') {
            return {
                status: 'error',
                data: { message: `Failed to provide Veeam Intelligence response. Unsupported client tool ${String(config.tool_name)}` },
            };
        }

        const { endpoint_path, query_params, method = 'GET', body, headers } = config.parameters;
        const query = createSortFindParams(query_params ?? {});
        let url = endpoint_path;

        if (query.size > 0) {
            url = `${url}?${query.toString()}`;
        }

        try {
            // `body` arrives pre-serialised from Veeam Intelligence; send it verbatim.
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

    // Convenience methods for common HTTP verbs
    protected async get<T>(url: string, config?: RequestConfig): Promise<T> {
        return this.request<T>({ ...config, method: 'GET', url });
    }

    protected async post<T>(url: string, data?: any, config?: RequestConfig): Promise<T> {
        return this.request<T>({ ...config, method: 'POST', url, data });
    }

    private async prepareRequest(config: { url: string; headers?: Record<string, string> }) {
        // Ensure we have a valid token
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

    /**
     * Request that resolves for every HTTP status (only network/transport errors throw),
     * with the same automatic token refresh and single 401 retry as `request`.
     */
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

        await this.authenticate();
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
                await this.authenticate();
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

    private async authenticate(): Promise<void> {
        try {
            const data = await this.authenticateProductRest();
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
                errorMessage += ' Please verify that ADMIN_USERNAME and ADMIN_PASSWORD are correct.';
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
