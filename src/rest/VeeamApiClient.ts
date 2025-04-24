/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { ApiClient } from './ApiClient.js';
import { AuthResult, ServiceInfo, ToolInvocationConfig } from '../common/types.js';
import { ToolCallingError } from '../common/errors.js';
import { debug } from '../common/debug.js';

export class VeeamApiClient {
  private apiClient: ApiClient;

  constructor() {
    if (!process.env.VONE_WEB_URL || !process.env.VONE_ADMIN_USERNAME || !process.env.VONE_ADMIN_PASSWORD) {
      throw new Error('Missing required environment variables: VONE_WEB_URL, VONE_ADMIN_USERNAME, VONE_ADMIN_PASSWORD');
    }

    this.apiClient = new ApiClient({
      baseURL: process.env.VONE_WEB_URL,
      username: process.env.VONE_ADMIN_USERNAME,
      password: process.env.VONE_ADMIN_PASSWORD,
    });
  }

  async getServiceInfo(): Promise<ServiceInfo> {
    return this.apiClient.get<ServiceInfo>('/api/v2.2/veeamintelligence/serviceInfo');
  }

  async authenticate(): Promise<AuthResult> {
    const data = {
      "cachePolicy":"ReturnFromCacheOrCreate",
      "cacheTtlSec":43200,
      "requestTemplate":{"product_name":"@getProductName","product_version":"@getProductVersion","license":"@getLicense","user_hash":"@getUserHash"}
    }

    const config = {
      headers: {
        'Content-Type': 'application/json;charset=UTF-8'
      }
    };

    return this.apiClient.post<AuthResult>('/api/v2.2/veeamintelligence/authenticate', data, config);
  }

  private isNotObject(value: unknown) {
    const invalidTypes = ['string', 'number', 'undefined', 'boolean', 'function'];
    
    return value === null || Number.isNaN(value) || invalidTypes.includes(typeof value);
  }

  private createQueryString(params: Record<string, unknown>): URLSearchParams {
    const queryParams = new URLSearchParams();
    const keys = Object.keys(params);

    keys.forEach((key) => {
        if (this.isNotObject(params[key])) {
            queryParams.append(key, String(params[key]));
        } else {
            queryParams.append(key, JSON.stringify(params[key]));
        }
    });

    return queryParams;
  }

  async getToolCallData(config: ToolInvocationConfig): Promise<{ data: unknown; status: string }> {
    // TODO: Implement threat center handling
    const cfg = config; // Hack to avoid error in default case
    switch (config.tool_name) {
      case 'fetch_threat_center': {
        //const result = await fetchThreatCenter(httpTransport);
        //return result;
        throw new ToolCallingError({
          message: 'Fetching threat center is not implemented'
        });
      }
      case 'fetch_data_from_endpoint': {
        const query = this.createQueryString(config.parameters.query_params);
        let url = config.parameters.endpoint_path;

        if (query.size > 0) {
            url = `${url}?${query.toString()}`;
        }

        try {
          const response = await this.apiClient.get(url);
          //debug();
          return { data: response, status: 'success' };
        } catch (err: any) {
          //debug();
          if (err.response?.status === 404) {
            throw new ToolCallingError({
              message: `Failed to provide Veeam Intelligence response. URL ${config.parameters.endpoint_path} does not exist`
            });
          }

          throw new ToolCallingError(err.response?.data || {
            message: `Failed to fetch data from endpoint: ${err.message || 'Unknown error'}`
          });
        }
      }
      default: {
        throw new ToolCallingError({
          message: `Failed to provide Veeam Intelligence response. Unable to load ${cfg.tool_name}`
        });
      }
    }
  }
}