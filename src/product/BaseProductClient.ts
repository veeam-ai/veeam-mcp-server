/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { ProductApiTransport } from '@/product/ProductApiTransport';
import { ProductClient as ProductClient } from './types';
import { ServiceInfo, AuthResult, ToolInvocationConfig } from '@/common/types';
import { ToolCallingError } from '@/common/errors';
import { createSortFindParams } from '@/utils';

export abstract class BaseProductClient implements ProductClient {
    protected productApiTransport: ProductApiTransport;

    constructor(baseURL: string, username: string, password: string, authUrl: string) {
        this.productApiTransport = new ProductApiTransport({
            baseURL,
            username,
            password,
            authUrl,
        });
    }

    abstract getServiceInfo(): Promise<ServiceInfo>;
    abstract authenticate(): Promise<AuthResult>;

    async getToolCallData(config: ToolInvocationConfig): Promise<{ data: unknown; status: string }> {
        const cfg = config;
        switch (config.tool_name) {
            case 'fetch_data_from_endpoint': {
                const query = createSortFindParams(config.parameters.query_params);
                let url = config.parameters.endpoint_path;

                if (query.size > 0) {
                    url = `${url}?${query.toString()}`;
                }

                try {
                    const response = await this.productApiTransport.get(url);
                    return { data: response, status: 'success' };
                } catch (err: any) {
                    if (err.response?.status === 404) {
                        throw new ToolCallingError({
                            message: `Failed to provide Veeam Intelligence response. URL ${config.parameters.endpoint_path} does not exist`,
                        });
                    }

                    throw new ToolCallingError(
                        err.response?.data || {
                            message: `Failed to fetch data from endpoint: ${err.message || 'Unknown error'}`,
                        },
                    );
                }
            }
            default: {
                throw new ToolCallingError({
                    message: `Failed to provide Veeam Intelligence response. Unable to load ${cfg.tool_name}`,
                });
            }
        }
    }
}
