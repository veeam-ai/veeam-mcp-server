import { ServiceInfo, AuthResult, ToolInvocationConfig } from '../../common/types.js';

export interface VeeamClient {
    getServiceInfo(): Promise<ServiceInfo>;
    authenticate(): Promise<AuthResult>;
    getToolCallData(config: ToolInvocationConfig): Promise<{ data: unknown; status: string }>;
}
