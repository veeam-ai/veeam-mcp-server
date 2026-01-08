/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

export enum MessageRole {
    user = 'user',
    assistant = 'assistant',
}

export enum ChatbotMode {
    Base = 'Base',
    Advanced = 'Advanced',
}

export const PRODUCT_NAMES = {
    vbr: 'Veeam Backup & Replication',
    vone: 'Veeam ONE',
    vspc: 'Veeam Service Provider Console',
} as const;

export type ProductCode = keyof typeof PRODUCT_NAMES;

export interface DataframeArtifact {
    id: string;
    type: 'dataframe';
    data: {
        columns: string[];
        index: number[];
        data: unknown[][];
    };
}

export interface StringArtifact {
    id: string;
    type: 'string';
    data: string;
}

export type Artifact = StringArtifact | DataframeArtifact;

export interface AuthResponse {
    access_token: string;
    issued_unix_ts: number;
    ttl_sec: number;
    product_suffix: string;
}

export interface AuthResult {
    source: 'Direct' | 'Cache';
    response: AuthResponse;
}

export interface ServiceInfo {
    chatbotApiUrl: string;
    chatbotEnabled: boolean;
    chatbotMode: ChatbotMode;
    productName: string;
    productVersion: string;
    userRole?: string;
}

interface BaseToolInvocationConfig {
    invocation_id: string;
}

interface CommonInvokeConfig extends BaseToolInvocationConfig {
    tool_name: 'fetch_data_from_endpoint';
    parameters: {
        endpoint_path: string;
        query_params: Record<string, unknown>;
    };
}

export type ToolInvocationConfig = CommonInvokeConfig;

export interface SocketConfig {
    withCredentials?: boolean;
    socketPath?: string;
}
