/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { ProductRestClient } from '../ProductRestClient';
import { ProductAuthResponseUnifiedDate, ProductRestClientConfig, RequestConfig } from './types';
import { ServiceInfo, ChatBotAuthResponse, ToolInvocationConfig } from '@/common/types';
import { ToolCallingError } from '@/common/errors';
import { createSortFindParams } from '@/utils';

import axios, { AxiosInstance } from 'axios';
import https from 'node:https';
import { mergeUrlParts } from '@/utils/url';

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

    async getToolCallData(config: ToolInvocationConfig): Promise<{ data: unknown; status: string }> {
        const cfg = config;
        switch (config.tool_name) {
            case 'fetch_data_from_endpoint': {
                const query = createSortFindParams(config.parameters.query_params);
                let url = config.parameters.endpoint_path;

                if (query.size > 0) {
                    url = `${url}?${query.toString()}`;
                }

                try {
                    const response = await this.get(url);
                    return { data: response, status: 'success' };
                } catch (err: any) {
                    if (err.response?.status === 404) {
                        throw new ToolCallingError({
                            message: `Failed to provide Veeam Intelligence response. URL ${config.parameters.endpoint_path} does not exist`,
                        });
                    }

                    throw new ToolCallingError(
                        err.response?.data || {
                            message: `Failed to fetch data from endpoint: ${err.message || 'Unknown error'}`,
                        },
                    );
                }
            }
            default: {
                throw new ToolCallingError({
                    message: `Failed to provide Veeam Intelligence response. Unable to load ${cfg.tool_name}`,
                });
            }
        }
    }

    // Convenience methods for common HTTP verbs
    protected async get<T>(url: string, config?: RequestConfig): Promise<T> {
        return this.request<T>({ ...config, method: 'GET', url });
    }

    protected async post<T>(url: string, data?: any, config?: RequestConfig): Promise<T> {
        return this.request<T>({ ...config, method: 'POST', url, data });
    }

    // Generic request method with automatic token handling
    private async request<T>(config: {
        method: string;
        url: string;
        data?: any;
        headers?: Record<string, string>;
        params?: Record<string, string>;
    }): Promise<T> {
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

        // Add auth token
        if (this.accessToken) {
            headers['Authorization'] = `Bearer ${this.accessToken}`;
        }

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
                // Update headers with new token
                if (this.accessToken) {
                    headers['Authorization'] = `Bearer ${this.accessToken}`;
                }
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

            throw new Error(errorMessage, { cause: error.cause });
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

            throw new Error(errorMessage, { cause: error.cause });
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
