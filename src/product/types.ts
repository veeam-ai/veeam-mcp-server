/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { ServiceInfo, AuthResult, ToolInvocationConfig } from '../common/types';

export interface ProductApi {
    getServiceInfo(): Promise<ServiceInfo>;
    authenticate(): Promise<AuthResult>;
    getToolCallData(config: ToolInvocationConfig): Promise<{ data: unknown; status: string }>;
}
