/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { ServiceInfo, AuthResult, ToolInvocationConfig } from '@/common/types';
import { ProductApi, VoneClient, VspcClient, VbrClient } from './clients';

export class ProductClient implements ProductApi {
    private client: ProductApi;

    constructor() {
        if (
            !process.env.PRODUCT_NAME ||
            !process.env.WEB_URL ||
            !process.env.ADMIN_USERNAME ||
            !process.env.ADMIN_PASSWORD
        ) {
            throw new Error(
                'Missing required environment variables: PRODUCT_NAME, WEB_URL, ADMIN_USERNAME, ADMIN_PASSWORD',
            );
        }

        const baseURL = process.env.WEB_URL;
        const username = process.env.ADMIN_USERNAME;
        const password = process.env.ADMIN_PASSWORD;

        switch (process.env.PRODUCT_NAME) {
            case 'vone':
                this.client = new VoneClient(baseURL, username, password);
                break;
            case 'vspc':
                this.client = new VspcClient(baseURL, username, password);
                break;
            case 'vbr':
                this.client = new VbrClient(baseURL, username, password);
                break;
            default:
                throw new Error(
                    'Unknown or missing PRODUCT_NAME environment variable. Supported values: vone, vspc, vbr',
                );
        }
    }

    async getServiceInfo(): Promise<ServiceInfo> {
        return this.client.getServiceInfo();
    }

    async authenticate(): Promise<AuthResult> {
        return this.client.authenticate();
    }

    async getToolCallData(
        config: ToolInvocationConfig,
    ): Promise<{ data: unknown; status: string }> {
        return this.client.getToolCallData(config);
    }
}
