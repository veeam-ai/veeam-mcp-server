/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { BaseRestClient } from '@/product/clients/BaseRestClient';
import { ServiceInfo, AuthResult } from '@/common/types';
import { AuthRequestConfig, AuthResponse } from './types';
import { mergeUrlParts } from '@/utils/url';

export class VbrRestClient extends BaseRestClient {
    async getServiceInfo(): Promise<ServiceInfo> {
        return this.get<ServiceInfo>('/private-api/v1/veeamintelligence/serviceInfo');
    }

    async authenticateChatService(): Promise<AuthResult> {
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

        return this.post<AuthResult>('/private-api/v1/veeamintelligence/authenticate', data, config);
    }

    protected override async authenticateProductRest(): Promise<AuthResponse> {
        const currentUserAuthResponse = await this.authenticateAsCurrentUser();
        const chatBotAuthResponse = await this.authenticateAsChatBotRole(currentUserAuthResponse.access_token);

        return chatBotAuthResponse;
    }

    private async authenticateAsCurrentUser(): Promise<AuthResponse> {
        const authData = new URLSearchParams();
        authData.append('username', this.config.username);
        authData.append('password', this.config.password);
        authData.append('grant_type', 'password');

        const privateRestAuthUrl = this.config.authUrl;

        const response = await this.client.post<AuthResponse>(privateRestAuthUrl, authData.toString(), {
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
        });

        const data = response.data;
        return data;
    }

    private async authenticateAsChatBotRole(userToken: string): Promise<AuthResponse> {
        const authData = new URLSearchParams();
        authData.append('grant_type', 'vbr_common_auth');
        authData.append('type', 'VeeamChatbot');
        authData.append('instance_id', '00000000-0000-0000-0000-000000000000');

        const botAuthUrl = mergeUrlParts(this.config.baseURL, '/private-api/oauth2/vbr_extension');

        const response = await this.client.post<AuthResponse>(botAuthUrl, authData.toString(), {
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                Authorization: `Bearer ${userToken}`,
            },
        });

        const data = response.data;
        return data;
    }
}
