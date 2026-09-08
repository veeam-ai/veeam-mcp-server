/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { ServiceInfo, ChatBotAuthResponse, CommonInvokeConfig, ToolCallResult } from '@/common/types';

export interface ProductRestClient {
    getServiceInfo(): Promise<ServiceInfo>;
    authenticateChatService(): Promise<ChatBotAuthResponse>;
    /**
     * Execute a product REST call requested by Veeam Intelligence (any HTTP method).
     * Never throws for HTTP-level failures: the upstream status and body are returned in the
     * envelope so the agent can relay them.
     */
    getToolCallData(config: CommonInvokeConfig): Promise<ToolCallResult>;
}
