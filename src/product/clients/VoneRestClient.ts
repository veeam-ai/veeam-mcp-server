/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { BaseRestClient } from '@/product/clients/BaseRestClient';
import { ServiceInfo, ChatBotAuthResponse } from '@/common/types';
import { AuthRequestConfig, ProductAuthResponse, ProductAuthResponseUnifiedDate } from './types';
import { mergeUrlParts } from '@/utils/url';

const USER_AUTH_URL_SUFFIX = '/api/token';
const BOT_AUTH_URL_SUFFIX = '/api/v2.2/veeamintelligence/webApiAccessToken';

interface VoneBotAuthResponse {
    accessToken: string;
    expirationDate: string;
}

export class VoneRestClient extends BaseRestClient {
    async getServiceInfo(): Promise<ServiceInfo> {
        return this.get<ServiceInfo>('/api/v2.2/veeamintelligence/serviceInfo');
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

        return this.post<ChatBotAuthResponse>('/api/v2.2/veeamintelligence/authenticate', data, config);
    }

    protected async authenticateProductRest(): Promise<ProductAuthResponseUnifiedDate> {
        const currentUserAuthResponse = await this.authenticateAsCurrentUser();
        const chatBotAuthResponse = await this.authenticateAsChatBotRole(currentUserAuthResponse.access_token);

        return chatBotAuthResponse;
    }

    private async authenticateAsCurrentUser(): Promise<ProductAuthResponse> {
        const authData = new URLSearchParams();
        authData.append('username', this.config.username);
        authData.append('password', this.config.password);
        authData.append('grant_type', 'password');

        const authUrl = mergeUrlParts(this.config.baseURL, USER_AUTH_URL_SUFFIX);
        const response = await this.client.post<ProductAuthResponse>(authUrl, authData.toString(), {
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
        });

        const data = response.data;
        return data;
    }

    private async authenticateAsChatBotRole(userToken: string): Promise<ProductAuthResponseUnifiedDate> {
        const botAuthUrl = mergeUrlParts(this.config.baseURL, BOT_AUTH_URL_SUFFIX);

        const response = await this.client.get<VoneBotAuthResponse>(botAuthUrl, {
            headers: {
                'Content-Type': 'application/json;charset=UTF-8',
                Authorization: `Bearer ${userToken}`,
            },
        });

        const data = response.data;
        return {
            access_token: data.accessToken,
            valid_until: new Date(data.expirationDate).getTime(),
            token_type: 'Bearer',
        };
    }
}
