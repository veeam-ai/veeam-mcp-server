import { Subject } from 'rxjs';
import { io, Socket as SocketIO } from 'socket.io-client';
import { v4 as uuidv4 } from 'uuid';

import { ChatbotMode, ServiceInfo, SocketConfig, ToolInvocationConfig } from '../common/types.js';

import {
    ConnectionError,
    ConnectionErrorCode,
    SocketMessage,
    SocketMessageType,
    SocketEmitConfig,
    ResponseErrorConfig,
    ResponseChunk,
    SocketSubscribeHandlers,
    ProcessUpdatePayload,
} from './types.js';

export class Socket {
    private instance: SocketIO | null;
    private subject = new Subject<SocketMessage>();
    private currentSessionId: string | null;
    private chatId: string;

    constructor() {
        this.currentSessionId = null;
        this.instance = null;
        this.chatId = uuidv4();
    }

    public initSocket(serviceInfo: ServiceInfo, config: SocketConfig) {
        if (this.instance === null) {
            const now = new Date();
            const socketHost = this.resolveSocketHost(
                serviceInfo.chatbotApiUrl,
                config.productSuffix,
            );
            const uri = this.resolveSocketURI(socketHost);
            const path = this.resolveSocketPath(socketHost, config.socketPath);

            this.instance = io(uri, {
                path,
                autoConnect: false,
                withCredentials: config.withCredentials ?? false,
                auth: {
                    token: null,
                    mode: serviceInfo.chatbotMode,
                    chat_id: this.chatId,
                    timezone_offset: now.getTimezoneOffset() * -1,
                },
                reconnectionAttempts: 2,
            });

            this.addListeners();
        }
    }

    public asObservable() {
        return this.subject.asObservable();
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

    public getNewMessageId() {
        return uuidv4();
    }

    public subscribe(handlers: SocketSubscribeHandlers) {
        if (this.instance === null) {
            throw new Error("[TBD] Socket wasn't initialized");
        }

        const subscription = this.subject.subscribe(async ({ data, type }) => {
            switch (type) {
                case SocketMessageType.chunk: {
                    handlers.onChunk(data);
                    break;
                }
                case SocketMessageType.connected: {
                    handlers.onConnected(data);
                    break;
                }
                case SocketMessageType.connectionError: {
                    handlers.onConnectionError(data);
                    break;
                }
                case SocketMessageType.connectionInfoError: {
                    handlers.onConnectionInfoError(data);
                    break;
                }
                case SocketMessageType.disconnected: {
                    handlers.onDisconnected(data);
                    break;
                }
                case SocketMessageType.reconnectError: {
                    handlers.onReconnectError(data);
                    break;
                }
                case SocketMessageType.reconnectFailed: {
                    handlers.onReconnectFailed(data);
                    break;
                }
                case SocketMessageType.responseError: {
                    handlers.onResponseError(data);
                    break;
                }
                case SocketMessageType.tokenInvalid: {
                    handlers.onTokenInvalid(data);
                    break;
                }
                case SocketMessageType.tokenRequired: {
                    handlers.onTokenRequired(data);
                    break;
                }
                case SocketMessageType.toolInvocation: {
                    handlers.onToolInvocation(data);
                    break;
                }
                case SocketMessageType.unknownProduct: {
                    handlers.onUnknownProduct(data);
                    break;
                }
                case SocketMessageType.processStart: {
                    handlers.onProcessStart(data);
                    break;
                }
                case SocketMessageType.processEnd: {
                    handlers.onProcessEnd(data);
                    break;
                }
                case SocketMessageType.processUpdate: {
                    handlers.onProcessUpdate(data);
                    break;
                }
                default: {
                    throw new Error(`[TBD] Unknown socket message type captured: ${type}`);
                }
            }
        });

        return subscription;
    }

    private addListeners() {
        this.getInstance().on('connect', () => {
            if (this.currentSessionId === null) {
                this.currentSessionId = uuidv4();

                const message = `[VAIA Socket] Connection established successfully. Session id: ${this.currentSessionId}`;

                this.subject.next({
                    type: SocketMessageType.connected,
                    data: { message },
                });
            } else {
                this.getInstance().disconnect();
            }
        });

        this.getInstance().on('connect_error', (error) => {
            if (this.getInstance().active === false) {
                const connectionError = JSON.parse(error.message) as ConnectionError;

                this.subject.next({
                    type: this.mapConnectionError(connectionError.code),
                    data: {
                        message: connectionError.details,
                    },
                });
            }
        });

        this.getInstance().on('disconnect', () => {
            const message = `[VAIA Socket] Connection ${this.currentSessionId} is terminated`;
            this.currentSessionId = null;

            this.subject.next({
                type: SocketMessageType.disconnected,
                data: { message },
            });
        });

        this.getInstance().on('response_chunk', (chunk: ResponseChunk | undefined) => {
            if (this.currentSessionId === null || chunk === undefined) {
                return;
            }

            this.subject.next({
                type: SocketMessageType.chunk,
                data: {
                    message: JSON.stringify(chunk),
                },
            });
        });

        this.getInstance().on('tool_invocation', (config: ToolInvocationConfig) => {
            if (this.currentSessionId === null) {
                return;
            }

            this.subject.next({
                type: SocketMessageType.toolInvocation,
                data: {
                    message: JSON.stringify(config),
                },
            });
        });

        this.getInstance().on('process_start', () => {
            if (this.currentSessionId === null) {
                return;
            }

            this.subject.next({
                type: SocketMessageType.processStart,
                data: {
                    message: '',
                },
            });
        });

        this.getInstance().on('process_end', () => {
            if (this.currentSessionId === null) {
                return;
            }

            this.subject.next({
                type: SocketMessageType.processEnd,
                data: {
                    message: '',
                },
            });
        });

        this.getInstance().on('process_update', (payload: ProcessUpdatePayload) => {
            if (this.currentSessionId === null) {
                return;
            }

            this.subject.next({
                type: SocketMessageType.processUpdate,
                data: {
                    message: JSON.stringify(payload),
                },
            });
        });

        this.getInstance().on('response_error', (config: ResponseErrorConfig) => {
            if (this.currentSessionId === null) {
                return;
            }

            this.subject.next({
                type: SocketMessageType.responseError,
                data: {
                    message: config.details,
                },
            });
        });

        this.getInstance().io.on('reconnect_error', () => {
            this.subject.next({
                type: SocketMessageType.reconnectError,
                data: {
                    message: '',
                },
            });
        });

        this.getInstance().io.on('reconnect_failed', () => {
            this.subject.next({
                type: SocketMessageType.reconnectFailed,
                data: {
                    message: '',
                },
            });
        });
    }

    public setAuthToken(token: string | null) {
        const inst = this.getInstance();

        inst.auth = {
            ...inst.auth,
            token,
        };
    }

    public setMode(mode: ChatbotMode) {
        const inst = this.getInstance();

        inst.auth = {
            ...inst.auth,
            mode,
        };
    }

    // INFO: we use any here because auth in socket is also any
    // eslint-disable-next-line
    public extendConnectionInfo(info: { [key: string]: any }) {
        const inst = this.getInstance();

        inst.auth = {
            ...inst.auth,
            ...info,
        };
    }

    private getInstance() {
        if (this.instance === null) {
            throw new Error("[TBD] Socket wasn't initialized");
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
            return `${base}${productSuffix}`;
        }

        return base;
    }

    private resolveSocketURI(host: string) {
        const url = new URL(host);

        return url.origin;
    }

    private mapConnectionError(code: ConnectionErrorCode) {
        switch (code) {
            case ConnectionErrorCode.ConnectionInfo:
                return SocketMessageType.connectionInfoError;
            case ConnectionErrorCode.TokenRequired:
                return SocketMessageType.tokenRequired;
            case ConnectionErrorCode.TokenInvalid:
                return SocketMessageType.tokenInvalid;
            case ConnectionErrorCode.UnknownProduct:
                return SocketMessageType.unknownProduct;
        }
    }
}
