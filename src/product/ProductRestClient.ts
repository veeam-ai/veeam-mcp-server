/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { ServiceInfo, ChatBotAuthResponse, ToolInvocationConfig } from '@/common/types';

export interface ProductRestClient {
    getServiceInfo(): Promise<ServiceInfo>;
    authenticateChatService(): Promise<ChatBotAuthResponse>;
    getToolCallData(config: ToolInvocationConfig): Promise<{ data: unknown; status: string }>;
}
