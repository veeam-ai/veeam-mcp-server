/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { BaseRestClient } from '@/product/clients/BaseRestClient';
import { ServiceInfo, ChatBotAuthResponse } from '@/common/types';
import { AuthRequestConfig, ProductAuthResponse, ProductAuthResponseUnifiedDate } from './types';
import { mergeUrlParts } from '@/utils/url';

const VSPC_VI_PLUGIN_ID = 'acfa09fe128645f09cd5b794d9d183d0';
const AUTH_URL_SUFFIX = '/api/v3/token';

export class VspcRestClient extends BaseRestClient {
    async getServiceInfo(): Promise<ServiceInfo> {
        const response = await this.get<any>(`plugins/${VSPC_VI_PLUGIN_ID}/api/v1/serviceInfo`);
        if (response.chatBotApiUrl && !response.chatbotApiUrl) {
            response.chatbotApiUrl = response.chatBotApiUrl;
            delete response.chatBotApiUrl;
        }
        return response as ServiceInfo;
    }

    async authenticateChatService(): Promise<ChatBotAuthResponse> {
        const data: AuthRequestConfig = {
            cachePolicy: 'ReturnFromCacheOrCreate',
            cacheTtlSec: 43200,
            requestTemplate: {
                product_name: '@getProductName',
                product_version: '@getProductVersion',
                license: '@getLicense',
                user_hash: '@getUserHash',
            },
        };

        const config = {
            headers: {
                'Content-Type': 'application/json;charset=UTF-8',
            },
        };

        return this.post<ChatBotAuthResponse>(`plugins/${VSPC_VI_PLUGIN_ID}/api/v1/authenticate`, data, config);
    }

    protected async authenticateProductRest(): Promise<ProductAuthResponseUnifiedDate> {
        const authData = new URLSearchParams();
        authData.append('username', this.config.username);
        authData.append('password', this.config.password);
        authData.append('grant_type', 'password');

        const authUrl = mergeUrlParts(this.config.baseURL, AUTH_URL_SUFFIX);
        const response = await this.client.post<ProductAuthResponse>(authUrl, authData.toString(), {
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
        });

        const data = response.data;
        const result = {
            access_token: data.access_token,
            valid_until: Date.now() + data.expires_in * 1000,
            token_type: data.token_type,
        };
        return result;
    }
}
