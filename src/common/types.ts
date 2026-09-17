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
    /** VBR 13.1+: Advanced plus user-confirmed product actions proposed by Veeam Intelligence. */
    AdvancedWithActions = 'AdvancedWithActions',
}

/** Advanced and AdvancedWithActions both grant Veeam Intelligence access to product REST data. */
export function isAdvancedMode(mode: ChatbotMode): boolean {
    return mode === ChatbotMode.Advanced || mode === ChatbotMode.AdvancedWithActions;
}

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

/**
 * An artifact as it arrives from Veeam Intelligence.
 *
 * `type` is deliberately open. Veeam Intelligence ships `string`, `dataframe`, `chart` and
 * `hero-metric` today (see `ArtifactType` in veeam-intelligence `ai-core/src/types/artifacts.ts`)
 * and adds more over time. The MCP server does not render artifacts — it forwards them verbatim to
 * the client — so narrowing this to the shapes we happen to model would silently drop content.
 * Use `StringArtifact` / `DataframeArtifact` where a specific shape is actually needed.
 */
export interface Artifact {
    id: string;
    type: string;
    data: unknown;
}

export interface ChatBotAuthResult {
    access_token: string;
    issued_unix_ts: number;
    ttl_sec: number;
    product_suffix: string;
}

export interface ChatBotAuthResponse {
    source: 'Direct' | 'Cache';
    response: ChatBotAuthResult;
}

export interface ServiceInfo {
    chatbotApiUrl: string;
    chatbotEnabled: boolean;
    chatbotMode: ChatbotMode;
    productName: string;
    productVersion: string;
    productPlatform?: string;
    isAdvancedModeAllowed?: boolean;
    userRole?: string;
}

export type ToolCallHttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

interface BaseToolInvocationConfig {
    invocation_id: string;
}

/**
 * Veeam Intelligence asks the client to call a product REST endpoint. Reads are GET; actions
 * (VBR 13.1+, AdvancedWithActions mode) arrive on the same envelope with a non-GET `method`,
 * an optional pre-serialised JSON `body`, and an optional assistant-written `description`.
 *
 * This is the validated, post-parse shape (see `socket/schemas.ts`). `method` is optional on the
 * wire — a read omits it — and is defaulted to `GET` during parsing, so the gate and the REST
 * client can never disagree about what an absent method meant.
 */
export interface CommonInvokeConfig extends BaseToolInvocationConfig {
    tool_name: 'fetch_data_from_endpoint';
    parameters: {
        endpoint_path: string;
        query_params: Record<string, unknown>;
        method: ToolCallHttpMethod;
        body?: string;
        headers?: Record<string, string>;
        description?: string;
    };
}

export type UserInteractionKind = 'confirmation' | 'singleSelect' | 'multiSelect' | 'treeSelect';

/** Veeam Intelligence asks the user a question (confirmation / selection) as a client-side tool call. */
export interface RequestUserInteractionConfig extends BaseToolInvocationConfig {
    tool_name: 'request_user_interaction';
    parameters: {
        request_id?: string;
        kind: UserInteractionKind;
        label?: string;
        title?: string;
        description?: string;
        options?: unknown[];
        default_value?: unknown;
        accept_custom_input?: boolean;
    };
}

export type ToolInvocationConfig = CommonInvokeConfig | RequestUserInteractionConfig;

/** Result envelope for a product REST call made on behalf of Veeam Intelligence. */
export interface ToolCallResult {
    status: 'success' | 'error';
    data: unknown;
}

export interface SocketConfig {
    withCredentials?: boolean;
    socketPath?: string;
    mode?: ChatbotMode;
}
