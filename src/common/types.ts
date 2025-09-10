/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

export enum MessageRole {
    user = 'user',
    assistant = 'assistant',
}

export enum MessageType {
    message = 'message',
    error = 'error',
    process = 'process',
}

export enum ChatbotMode {
    Base = 'Base',
    Advanced = 'Advanced',
}

export interface MarkdownChunk {
    type: 'markdown';
    id: string;
}

export interface ArtifactChunk {
    type: 'artifact';
    id: string;
}

export type MessageChunk = MarkdownChunk | ArtifactChunk;

export interface ErrorMessage {
    id: string;
    type: MessageType.error;
    message: string;
}

export interface ConversationMessage {
    id: string;
    type: MessageType.message;
    role: MessageRole;
    chunkList: string[];
    chunks: Record<string, MessageChunk>;
}

export type ProcessStepStatus = 'in_progress' | 'success';

export interface ProcessStep {
    label: string;
    status: ProcessStepStatus;
    reason: string;
}

export interface ProcessMessage {
    id: string;
    type: MessageType.process;
    inProgress: boolean;
    steps: Record<string, ProcessStep>;
    stepsList: string[];
}

export type Message = ErrorMessage | ConversationMessage | ProcessMessage;

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

export interface Api {
    checkServiceInfo: () => Promise<ServiceInfo | string>;
    getAccessToken: (config: AuthRequestConfig) => Promise<AuthResult>;
    getToolCallData: (config: ToolInvocationConfig) => Promise<{ data: unknown; status: string }>;
}

export interface AppConfig {
    onAdvancedModeClick: () => void;
    getSocketConfig: () => SocketConfig;
    // INFO: we use any here because auth in socket is also any
    // eslint-disable-next-line
    getSocketConnectionInfo?: () => { [key: string]: any };
    modeSelectorEnabled: boolean;
    api: Api;
    promptsList: PromptsItem[];
    welcomeText: string;
}

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

export interface AuthRequestConfig {
    cachePolicy: 'NoCache' | 'CacheAndReturn' | 'ReturnFromCacheOrCreate';
    cacheTtlSec: number;
    requestTemplate: {
        product_name: string;
        product_version: string;
        license: string;
        user_hash: string;
    };
}

export interface ServiceInfo {
    chatbotApiUrl: string;
    chatbotEnabled: boolean;
    chatbotMode: ChatbotMode;
    productName: string;
    productVersion: string;
}

interface BaseToolInvocationConfig {
    invocation_id: string;
}

interface ThreatCenterConfig extends BaseToolInvocationConfig {
    tool_name: 'fetch_threat_center';
    parameters: object;
}

interface CommonInvokeConfig extends BaseToolInvocationConfig {
    tool_name: 'fetch_data_from_endpoint';
    parameters: {
        endpoint_path: string;
        query_params: Record<string, unknown>;
    };
}

export type ToolInvocationConfig = ThreatCenterConfig | CommonInvokeConfig;

export interface PromptsItem {
    id: string;
    title: string;
    description: string;
    prompt: string;
    mode: ChatbotMode[];
}

export interface SocketConfig {
    withCredentials?: boolean;
    socketPath?: string;
}
