/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { BaseProductClient } from '@/product/BaseProductClient';
import { ServiceInfo, AuthResult } from '@/common/types';
import { AuthRequestConfig } from './types';

const VSPC_VI_PLUGIN_ID = 'acfa09fe128645f09cd5b794d9d183d0';

export class VspcClient extends BaseProductClient {
    async getServiceInfo(): Promise<ServiceInfo> {
        const response = await this.productApiTransport.get<any>(`plugins/${VSPC_VI_PLUGIN_ID}/api/v1/serviceInfo`);
        if (response.chatBotApiUrl && !response.chatbotApiUrl) {
            response.chatbotApiUrl = response.chatBotApiUrl;
            delete response.chatBotApiUrl;
        }
        return response as ServiceInfo;
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

        return this.productApiTransport.post<AuthResult>(`plugins/${VSPC_VI_PLUGIN_ID}/api/v1/authenticate`, data, config);
    }
}
