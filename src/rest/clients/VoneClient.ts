import { BaseVeeamClient } from './BaseVeeamClient.js';
import { ServiceInfo, AuthResult } from '../../common/types.js';

export class VoneClient extends BaseVeeamClient {
    constructor(baseURL: string, username: string, password: string) {
        super(baseURL, username, password, `${baseURL}/api/token`);
    }

    async getServiceInfo(): Promise<ServiceInfo> {
        return this.apiClient.get<ServiceInfo>('/api/v2.2/veeamintelligence/serviceInfo');
    }

    async authenticate(): Promise<AuthResult> {
        const data = {
            "cachePolicy": "ReturnFromCacheOrCreate",
            "cacheTtlSec": 43200,
            "requestTemplate": { "product_name": "@getProductName", "product_version": "@getProductVersion", "license": "@getLicense", "user_hash": "@getUserHash" }
        };

        const config = {
            headers: {
                'Content-Type': 'application/json;charset=UTF-8'
            }
        };

        return this.apiClient.post<AuthResult>('/api/v2.2/veeamintelligence/authenticate', data, config);
    }
}
