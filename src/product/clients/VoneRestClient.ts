/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { BaseRestClient } from '@/product/clients/BaseRestClient';
import { ServiceInfo, AuthResult } from '@/common/types';
import { AuthRequestConfig, AuthResponse } from './types';

export class VoneRestClient extends BaseRestClient {
    async getServiceInfo(): Promise<ServiceInfo> {
        return this.get<ServiceInfo>('/api/v2.2/veeamintelligence/serviceInfo');
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

        return this.post<AuthResult>('/api/v2.2/veeamintelligence/authenticate', data, config);
    }

    protected override async authenticateProductRest(): Promise<AuthResponse> {
        throw new Error('Method not implemented.');
    }
}
