/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { BaseRestClient } from '@/product/clients/BaseRestClient';
import { ServiceInfo, ChatBotAuthResponse } from '@/common/types';
import { AuthRequestConfig, ProductAuthResponseUnifiedDate } from './types';

const VSPC_VI_PLUGIN_ID = 'acfa09fe128645f09cd5b794d9d183d0';
const AUTH_URL_SUFFIX = '/api/v3/token';

export class VspcRestClient extends BaseRestClient {
    protected readonly userTokenPath = AUTH_URL_SUFFIX;

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

    protected async authenticateProductRest(renewUserToken: boolean): Promise<ProductAuthResponseUnifiedDate> {
        const { accessToken, expiresAt } = await this.currentUserToken(renewUserToken);
        return { access_token: accessToken, valid_until: expiresAt, token_type: 'Bearer' };
    }
}
