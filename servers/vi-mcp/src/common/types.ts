/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { z } from 'zod';

import { artifactSchema, httpMethodSchema, responseChunkSchema, toolInvocationSchema, userInteractionKindSchema } from './schemas';

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

export type DataframeArtifact = {
    id: string;
    type: 'dataframe';
    data: {
        columns: string[];
        index: number[];
        data: unknown[][];
    };
};

export type StringArtifact = {
    id: string;
    type: 'string';
    data: string;
};

/**
 * An artifact as it arrives from Veeam Intelligence.
 *
 * `type` is deliberately open. Veeam Intelligence ships `string`, `dataframe`, `chart` and
 * `hero-metric` today (see `ArtifactType` in veeam-intelligence `ai-core/src/types/artifacts.ts`)
 * and adds more over time. The MCP server does not render artifacts — it forwards them verbatim to
 * the client — so narrowing this to the shapes we happen to model would silently drop content.
 * Use `StringArtifact` / `DataframeArtifact` where a specific shape is actually needed.
 */
export type Artifact = z.infer<typeof artifactSchema>;

export type ResponseChunk = z.infer<typeof responseChunkSchema>;

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

export type HttpMethod = z.infer<typeof httpMethodSchema>;

export type UserInteractionKind = z.infer<typeof userInteractionKindSchema>;

/**
 * Everything Veeam Intelligence can ask the client to do, as the validated post-parse shape.
 * Inferred from `toolInvocationSchema`, so the parser and the handlers can never disagree about
 * what a frame contains — notably `method`, which a read omits on the wire and which parsing
 * defaults to `GET` before the gate or the REST client ever sees it.
 */
export type ToolInvocationConfig = z.infer<typeof toolInvocationSchema>;

/**
 * Veeam Intelligence asks the client to call a product REST endpoint. Reads are GET; actions
 * (VBR 13.1+, AdvancedWithActions mode) arrive on the same envelope with a non-GET `method`,
 * an optional pre-serialised JSON `body`, and an optional assistant-written `description`.
 */
export type CommonInvokeConfig = Extract<ToolInvocationConfig, { tool_name: 'fetch_data_from_endpoint' }>;

/** Veeam Intelligence asks the user a question (confirmation / selection) as a client-side tool call. */
export type RequestUserInteractionConfig = Extract<ToolInvocationConfig, { tool_name: 'request_user_interaction' }>;

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
