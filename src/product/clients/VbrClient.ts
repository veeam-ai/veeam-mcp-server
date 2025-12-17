/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { BaseProductClient } from '@/product/BaseProductClient';
import { ServiceInfo, AuthResult } from '@/common/types';
import { AuthRequestConfig } from './types';

export class VbrClient extends BaseProductClient {
    constructor(baseURL: string, username: string, password: string) {
        super(baseURL, username, password, `${baseURL}/private-api/oauth2/token`);
    }

    async getServiceInfo(): Promise<ServiceInfo> {
        return this.apiClient.get<ServiceInfo>('/private-api/v1/veeamintelligence/serviceInfo');
    }

    async authenticate(): Promise<AuthResult> {
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

        return this.apiClient.post<AuthResult>(
            '/private-api/v1/veeamintelligence/authenticate',
            data,
            config,
        );
    }
}
