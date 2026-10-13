/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { BaseRestClient } from '@/product/clients/BaseRestClient';
import { ServiceInfo, ChatBotAuthResponse } from '@/common/types';
import { AuthRequestConfig, ProductAuthResponse, ProductAuthResponseUnifiedDate } from './types';
import { mergeUrlParts } from '@/utils/url';

const USER_AUTH_URL_SUFFIX = '/private-api/oauth2/token';
const BOT_AUTH_URL_SUFFIX = '/private-api/oauth2/vbr_extension';

export class VbrRestClient extends BaseRestClient {
    protected readonly userTokenPath = USER_AUTH_URL_SUFFIX;

    async getServiceInfo(): Promise<ServiceInfo> {
        return this.get<ServiceInfo>('/private-api/v1/veeamintelligence/serviceInfo');
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

        return this.post<ChatBotAuthResponse>('/private-api/v1/veeamintelligence/authenticate', data, config);
    }

    protected async authenticateProductRest(renewUserToken: boolean): Promise<ProductAuthResponseUnifiedDate> {
        const { accessToken } = await this.currentUserToken(renewUserToken);
        return this.authenticateAsChatBotRole(accessToken);
    }

    private async authenticateAsChatBotRole(userToken: string): Promise<ProductAuthResponseUnifiedDate> {
        const authData = new URLSearchParams();
        authData.append('grant_type', 'vbr_common_auth');
        authData.append('type', 'VeeamChatbot');
        authData.append('instance_id', '00000000-0000-0000-0000-000000000000');

        const botAuthUrl = mergeUrlParts(this.config.baseURL, BOT_AUTH_URL_SUFFIX);

        const response = await this.client.post<ProductAuthResponse>(botAuthUrl, authData.toString(), {
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                Authorization: `Bearer ${userToken}`,
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
