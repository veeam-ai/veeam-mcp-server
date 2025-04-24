/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { Artifact, MessageRole, ProcessStepStatus } from '../common/types.js';

export enum ConnectionErrorCode {
    TokenRequired = 'TOKEN_REQUIRED',
    TokenInvalid = 'TOKEN_INVALID',
    ConnectionInfo = 'CONNECTION_INFO',
    UnknownProduct = 'UNKNOWN_PRODUCT',
}

export interface ConnectionError {
    details: string;
    code: ConnectionErrorCode;
}

export enum SocketMessageType {
    chunk = 'chunk',
    connected = 'connected',
    connectionError = 'connectionError',
    connectionInfoError = 'connectionInfoError',
    disconnected = 'disconnected',
    reconnectError = 'reconnectError',
    reconnectFailed = 'reconnectFailed',
    responseError = 'responseError',
    tokenInvalid = 'tokenInvalid',
    tokenRequired = 'tokenRequired',
    toolInvocation = 'toolInvocation',
    unknownProduct = 'unknownProduct',
    processStart = 'processStart',
    processEnd = 'processEnd',
    processUpdate = 'processUpdate',
}

export interface SocketMessageData {
    message: string;
}

export interface SocketMessage {
    type: SocketMessageType;
    data: SocketMessageData;
}

export interface ResponseErrorConfig {
    details: string;
}

export interface SocketEmitMessageItem {
    role: MessageRole;
    content: string;
}

export interface SocketSessionMetadata {
    pii_data_in_history: boolean;
}

export interface SocketEmitValue {
    messages: SocketEmitMessageItem[];
    artifacts: Artifact[];
    metadata: SocketSessionMetadata;
}

export interface SocketMessageEmitConfig {
    name: 'chat';
    value: SocketEmitValue;
}

export interface SocketToolResultEmitConfig {
    name: 'tool_result';
    value: unknown;
}

export type SocketEmitConfig = SocketMessageEmitConfig | SocketToolResultEmitConfig;

interface ResponseChunkToken {
    type: 'token';
    payload: string;
}

interface ResponseChunkArtifact {
    type: 'artifact';
    payload: Artifact;
}

export type ResponseChunk = ResponseChunkToken | ResponseChunkArtifact;

export interface ProcessUpdatePayload {
    id: number;
    label: string;
    status: ProcessStepStatus;
    reason: string;
}

export interface SocketSubscribeHandlers {
    onChunk: (data: SocketMessageData) => Promise<void>;
    onConnected: (data: SocketMessageData) => Promise<void>;
    onConnectionError: (data: SocketMessageData) => Promise<void>;
    onConnectionInfoError: (data: SocketMessageData) => Promise<void>;
    onDisconnected: (data: SocketMessageData) => Promise<void>;
    onReconnectError: (data: SocketMessageData) => Promise<void>;
    onReconnectFailed: (data: SocketMessageData) => Promise<void>;
    onResponseError: (data: SocketMessageData) => Promise<void>;
    onTokenInvalid: (data: SocketMessageData) => Promise<void>;
    onTokenRequired: (data: SocketMessageData) => Promise<void>;
    onToolInvocation: (data: SocketMessageData) => Promise<void>;
    onUnknownProduct: (data: SocketMessageData) => Promise<void>;
    onProcessStart: (data: SocketMessageData) => Promise<void>;
    onProcessUpdate: (data: SocketMessageData) => Promise<void>;
    onProcessEnd: (data: SocketMessageData) => Promise<void>;
}
