import { BaseVeeamClient } from './BaseVeeamClient.js';
import { ServiceInfo, AuthResult } from '../../common/types.js';

export class VspcClient extends BaseVeeamClient {
    private pluginId: string;

    constructor(baseURL: string, username: string, password: string, pluginId: string) {
        super(baseURL, username, password, `${baseURL}/api/v3/token`);
        this.pluginId = pluginId;
    }

    async getServiceInfo(): Promise<ServiceInfo> {
        const response = await this.apiClient.get<any>(`plugins/${this.pluginId}/api/v1/serviceInfo`);
        if (response.chatBotApiUrl && !response.chatbotApiUrl) {
            response.chatbotApiUrl = response.chatBotApiUrl;
            delete response.chatBotApiUrl;
        }
        return response as ServiceInfo;
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

        return this.apiClient.post<AuthResult>(`plugins/${this.pluginId}/api/v1/authenticate`, data, config);
    }
}
