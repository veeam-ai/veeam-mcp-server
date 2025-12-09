/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { ServiceInfo, AuthResult, ToolInvocationConfig } from '../common/types.js';
import { VeeamClient } from './clients/VeeamClient.js';
import { VoneClient } from './clients/VoneClient.js';
import { VspcClient } from './clients/VspcClient.js';
import { VbrClient } from './clients/VbrClient.js';

export class VeeamApiClient implements VeeamClient {
  private client: VeeamClient;

  constructor() {
    if (!process.env.PRODUCT_NAME || !process.env.WEB_URL || !process.env.ADMIN_USERNAME || !process.env.ADMIN_PASSWORD) {
      throw new Error('Missing required environment variables: PRODUCT_NAME, WEB_URL, ADMIN_USERNAME, ADMIN_PASSWORD');
    }

    const baseURL = process.env.WEB_URL;
    const username = process.env.ADMIN_USERNAME;
    const password = process.env.ADMIN_PASSWORD;

    switch (process.env.PRODUCT_NAME) {
      case 'vone':
        this.client = new VoneClient(baseURL, username, password);
        break;
      case 'vspc':
        if (!process.env.VSPC_VI_PLUGIN_ID) {
            throw new Error('Missing required environment variable: VSPC_VI_PLUGIN_ID');
        }
        this.client = new VspcClient(baseURL, username, password, process.env.VSPC_VI_PLUGIN_ID);
        break;
      case 'vbr':
        this.client = new VbrClient(baseURL, username, password);
        break;
      default:
        throw new Error('Unknown or missing PRODUCT_NAME environment variable. Supported values: vone, vspc, vbr');
    }
  }

  async getServiceInfo(): Promise<ServiceInfo> {
    return this.client.getServiceInfo();
  }

  async authenticate(): Promise<AuthResult> {
    return this.client.authenticate();
  }

  async getToolCallData(config: ToolInvocationConfig): Promise<{ data: unknown; status: string }> {
    return this.client.getToolCallData(config);
  }
}
