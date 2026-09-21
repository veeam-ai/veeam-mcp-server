/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { Observable, Subject } from 'rxjs';
import { io, Socket as SocketIO } from 'socket.io-client';
import { v4 as uuidv4 } from 'uuid';

import { ServiceInfo, SocketConfig } from '@/common/types';
import { log } from '@/utils/logger';

import { describeParseError, invocationIdSchema, responseChunkSchema, toolInvocationSchema } from '@/common/schemas';
import { ChatTransport, ConnectionError, ConnectionErrorCode, ResponseErrorConfig, SocketEmitConfig, TransportInboundEvent } from './types';

const KNOWN_CONNECTION_ERROR_CODES = new Set<string>(Object.values(ConnectionErrorCode));

export class Socket implements ChatTransport {
    private instance: SocketIO | null;
    private subject = new Subject<TransportInboundEvent>();
    private currentSessionId: string | null;
    private chatId: string;

    public readonly events: Observable<TransportInboundEvent> = this.subject.asObservable();

    constructor() {
        this.currentSessionId = null;
        this.instance = null;
        this.chatId = uuidv4();
    }

    public initialize(serviceInfo: ServiceInfo, config: SocketConfig) {
        if (this.instance === null) {
            if (!process.env.PRODUCT_NAME) {
                throw new Error('PRODUCT_NAME environment variable is required');
            }

            const now = new Date();
            const socketHost = this.resolveSocketHost(serviceInfo.chatbotApiUrl, process.env.PRODUCT_NAME);
            const uri = this.resolveSocketURI(socketHost);
            const path = this.resolveSocketPath(socketHost, config.socketPath);

            const auth: any = {
                token: null,
                mode: config.mode ?? serviceInfo.chatbotMode,
                chat_id: this.chatId,
                timezone_offset: now.getTimezoneOffset() * -1,
            };

            if (serviceInfo.userRole) {
                auth.user_role = serviceInfo.userRole;
            }

            this.instance = io(uri, {
                path,
                autoConnect: false,
                withCredentials: config.withCredentials ?? false,
                auth,
                reconnectionAttempts: 2,
            });

            this.addListeners();
        }
    }

    public connect() {
        this.getInstance().connect();
    }

    public disconnect() {
        this.getInstance().disconnect();
    }

    public emit(config: SocketEmitConfig) {
        this.getInstance().emit(config.name, config.value);
    }

    private addListeners() {
        this.getInstance().on('connect', () => {
            if (this.currentSessionId === null) {
                this.currentSessionId = uuidv4();

                this.subject.next({ type: 'connected', sessionId: this.currentSessionId });
            } else {
                this.getInstance().disconnect();
            }
        });

        this.getInstance().on('connect_error', (error) => {
            if (this.getInstance().active === false) {
                this.subject.next({ type: 'connectError', error: Socket.toConnectionError(error) });
            }
        });

        this.getInstance().on('disconnect', () => {
            this.currentSessionId = null;

            this.subject.next({ type: 'disconnected' });
        });

        this.getInstance().on('response_chunk', (chunk: unknown) => {
            if (this.currentSessionId === null || chunk === undefined) {
                return;
            }

            const parsed = responseChunkSchema.safeParse(chunk);
            if (!parsed.success) {
                // Dropped rather than appended: a malformed chunk would otherwise reach the MCP
                // client as part of the answer or as a broken artifact.
                log.warn(`discarding malformed Veeam Intelligence response chunk (${describeParseError(parsed.error)})`);
                return;
            }

            this.subject.next({ type: 'chunk', payload: parsed.data });
        });

        this.getInstance().on('tool_invocation', (config: unknown) => {
            if (this.currentSessionId === null) {
                return;
            }

            const parsed = toolInvocationSchema.safeParse(config);
            if (parsed.success) {
                this.subject.next({ type: 'toolInvocation', payload: parsed.data });
                return;
            }

            const reason = describeParseError(parsed.error);
            const withId = invocationIdSchema.safeParse(config);
            if (withId.success) {
                this.subject.next({ type: 'toolInvocationInvalid', invocationId: withId.data.invocation_id, reason });
                return;
            }

            // No id to answer with; Veeam Intelligence gets no tool_result and will time out.
            log.warn(`discarding unidentifiable Veeam Intelligence tool invocation (${reason})`);
        });

        this.getInstance().on('response_error', (config: ResponseErrorConfig) => {
            if (this.currentSessionId === null) {
                return;
            }

            this.subject.next({ type: 'responseError', details: config.details });
        });

        this.getInstance().io.on('reconnect_error', () => {
            this.subject.next({ type: 'reconnectError' });
        });

        this.getInstance().io.on('reconnect_failed', () => {
            this.subject.next({ type: 'reconnectFailed' });
        });
    }

    public setAuthToken(token: string | null) {
        const inst = this.getInstance();

        inst.auth = {
            ...inst.auth,
            token,
        };
    }

    private getInstance() {
        if (this.instance === null) {
            throw new Error("Veeam Intelligence Socket connection wasn't initialized");
        }

        return this.instance;
    }

    private resolveSocketPath(host: string, socketPath?: string) {
        const url = new URL(host);
        const path = socketPath ?? '/socket.io';

        // INFO: > 1 because URL's pathname will contains "/" symbol in any case
        if (url.pathname.length > 1) {
            return `${url.pathname}${path}`;
        }

        return path;
    }

    private resolveSocketHost(apiUrl: string, productSuffix: string) {
        const base = apiUrl.replace(/\/$/, '');

        if (productSuffix.length > 0) {
            return `${base}/${productSuffix}`;
        }

        return base;
    }

    private resolveSocketURI(host: string) {
        const url = new URL(host);

        return url.origin;
    }

    /**
     * Veeam Intelligence reports handshake refusals as a JSON envelope in the error message.
     * Anything else (an unreachable host sends "xhr poll error") is reported as `Unknown` rather
     * than thrown, so a transport failure can never escape as an uncaught exception.
     */
    private static toConnectionError(error: Error): ConnectionError {
        try {
            const parsed: unknown = JSON.parse(error.message);

            if (typeof parsed === 'object' && parsed !== null) {
                const { code, details } = parsed as Record<string, unknown>;

                if (typeof code === 'string' && typeof details === 'string') {
                    // A code we don't know is reported as `Unknown` rather than passed through as a
                    // value the `ConnectionErrorCode` type claims to cover.
                    return {
                        code: KNOWN_CONNECTION_ERROR_CODES.has(code) ? (code as ConnectionErrorCode) : ConnectionErrorCode.Unknown,
                        details,
                    };
                }
            }
        } catch {
            // not a Veeam Intelligence error envelope
        }

        return { code: ConnectionErrorCode.Unknown, details: error.message };
    }
}
