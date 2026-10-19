/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { Observable } from 'rxjs';

import { Artifact, MessageRole, ResponseChunk, ServiceInfo, SocketConfig, ToolInvocationConfig } from '@/common/types';

export enum ConnectionErrorCode {
    TokenRequired = 'TOKEN_REQUIRED',
    TokenInvalid = 'TOKEN_INVALID',
    ConnectionInfo = 'CONNECTION_INFO',
    UnknownProduct = 'UNKNOWN_PRODUCT',
    /** Transport-level failure that is not a Veeam Intelligence error envelope (e.g. host unreachable). */
    Unknown = 'UNKNOWN',
}

export interface ConnectionError {
    details: string;
    code: ConnectionErrorCode;
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

/**
 * Everything the Veeam Intelligence connection can report, as one discriminated union.
 *
 * Payloads stay in their parsed form across this boundary: the transport hands over the objects it
 * received from the wire, so consumers never re-parse a string and never assert a type with `as`.
 * Adding a wire event means adding one member here, and every `switch` over it stops compiling
 * until it is handled.
 */
export type TransportInboundEvent =
    | { type: 'connected'; sessionId: string }
    | { type: 'chunk'; payload: ResponseChunk }
    | { type: 'toolInvocation'; payload: ToolInvocationConfig }
    /** A tool invocation that failed validation but carried an id we can answer with an error. */
    | { type: 'toolInvocationInvalid'; invocationId: string; reason: string }
    | { type: 'responseError'; details: string }
    | { type: 'connectError'; error: ConnectionError }
    | { type: 'disconnected' }
    | { type: 'reconnectError' }
    | { type: 'reconnectFailed' };

/**
 * The chat connection as its consumers need it. `Socket` is the socket.io implementation; tests
 * drive a `Subject`-backed double instead of a real server.
 */
export interface ChatTransport {
    /** Inbound wire events. Subscribe once per connection. */
    readonly events: Observable<TransportInboundEvent>;

    /** Prepare the connection. Safe to call repeatedly; only the first call takes effect. */
    initialize(serviceInfo: ServiceInfo, config: SocketConfig): void;

    setAuthToken(token: string | null): void;

    connect(): void;

    /** Throws when the transport was never initialised. */
    disconnect(): void;

    emit(config: SocketEmitConfig): void;
}
