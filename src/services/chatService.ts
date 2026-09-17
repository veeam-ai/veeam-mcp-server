/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { Subscription } from 'rxjs';

import { Socket } from '@/socket/Socket';
import { ServiceInfo, ChatBotAuthResult, Artifact, ChatbotMode, ToolInvocationConfig, MessageRole, isAdvancedMode } from '@/common/types';
import {
    ChatTransport,
    ConnectionError,
    ConnectionErrorCode,
    ResponseChunk,
    SocketEmitConfig,
    TransportInboundEvent,
} from '@/socket/types';
import type { ProductRestClient } from '@/product/ProductRestClient';
import { Deferred } from '@/utils';
import { log } from '@/utils/logger';
import { ActionOutcome, ConfirmationDecision, ConfirmationRequest, HandledInvocation } from '@/actions/types';
import { ActionExecutor } from '@/actions/ActionExecutor';
import { ConfirmationBroker } from '@/actions/ConfirmationBroker';
import { InteractionHandler } from '@/actions/InteractionHandler';
import { resolveActionsConfig } from '@/actions/resolveActionsConfig';
import { ChatServiceOptions, TurnOutcome } from './types';

const DEFAULT_OPTIONS: ChatServiceOptions = {
    productCode: process.env.PRODUCT_NAME ?? '',
    confirmationTimeoutMs: 1500 * 1000,
    turnTimeoutMs: 3600 * 1000,
};

function toMessage(error: unknown): string {
    return error instanceof Error ? error.message : String(error);
}

/**
 * One Veeam Intelligence chat connection. A turn starts with `sendMessage()` and ends when the
 * server closes the socket. When Veeam Intelligence proposes an action that needs the user's
 * approval, the turn pauses: the outcome is `awaiting_confirmation`, the socket stays open, and
 * the caller continues with `resolveConfirmation()` + `resume()`.
 */
export class ChatService {
    private transport: ChatTransport;
    private serviceInfo!: ServiceInfo;
    private authResponse!: ChatBotAuthResult;
    private productRestClient: ProductRestClient;
    private readonly options: ChatServiceOptions;

    private effectiveMode: ChatbotMode = ChatbotMode.Base;
    // Built in initialize(), once the product has told us which policy applies.
    private actionExecutor!: ActionExecutor;
    private readonly interactions: InteractionHandler;

    private message: string = '';
    private artifacts: Artifact[] = [];
    private actions: ActionOutcome[] = [];
    private reported = { message: 0, artifacts: 0, actions: 0 };

    // Resolved by onDisconnected(): the server closes the socket when the answer is complete.
    private messageComplete: Deferred<void> = new Deferred<void>();
    private readonly confirmations: ConfirmationBroker;

    private subscription: Subscription | null = null;
    private turnTimer: NodeJS.Timeout | null = null;
    private turnTimedOut = false;
    private turnActive = false;
    private connected = false;

    constructor(productRestClient: ProductRestClient, options: Partial<ChatServiceOptions> = {}, transport: ChatTransport = new Socket()) {
        this.productRestClient = productRestClient;
        this.options = { ...DEFAULT_OPTIONS, ...options };
        this.transport = transport;
        this.confirmations = new ConfirmationBroker(this.options.confirmationTimeoutMs);
        this.interactions = new InteractionHandler(this.confirmations, this.options.confirmationTimeoutMs);
    }

    public async initialize(): Promise<void> {
        const serviceInfo = await this.productRestClient.getServiceInfo();
        const authResult = await this.productRestClient.authenticateChatService();

        this.serviceInfo = serviceInfo;
        this.authResponse = authResult.response;

        const actionsConfig = resolveActionsConfig(serviceInfo, this.options.productCode);
        this.effectiveMode = actionsConfig.effectiveMode;
        this.actionExecutor = new ActionExecutor(
            actionsConfig.fetchGate,
            this.productRestClient,
            this.confirmations,
            this.options.confirmationTimeoutMs,
        );

        this.setupSocket();
    }

    public getEffectiveMode(): ChatbotMode {
        return this.effectiveMode;
    }

    private setupSocket(): void {
        this.transport.initialize(this.serviceInfo, {
            socketPath: '/socket.io',
            withCredentials: true,
            mode: this.effectiveMode,
        });
        this.transport.setAuthToken(this.authResponse.access_token);

        // Subscribe exactly once per connection; re-subscribing on every message duplicates handlers.
        this.subscription?.unsubscribe();
        this.subscription = this.transport.events.subscribe((event) => this.onTransportEvent(event));

        this.transport.connect();
    }

    public async sendMessage(message: string): Promise<TurnOutcome> {
        if (this.turnActive) {
            throw new Error('A Veeam Intelligence turn is already in progress on this connection');
        }

        this.message = '';
        this.artifacts = [];
        this.actions = [];
        this.reported = { message: 0, artifacts: 0, actions: 0 };
        this.messageComplete = new Deferred<void>();
        this.confirmations.dropUndelivered();
        this.turnTimedOut = false;
        this.turnActive = true;

        const config: SocketEmitConfig = {
            name: 'chat',
            value: {
                messages: [
                    {
                        role: MessageRole.user,
                        content: message,
                    },
                ],
                artifacts: [],
                metadata: {
                    pii_data_in_history: false,
                },
            },
        };

        this.startTurnTimer();
        this.transport.emit(config);

        return this.awaitOutcome();
    }

    /** Continue a turn that was paused by `awaiting_confirmation`. */
    public async resume(): Promise<TurnOutcome> {
        if (!this.turnActive) {
            throw new Error('No Veeam Intelligence turn is in progress on this connection');
        }

        return this.awaitOutcome();
    }

    /** Answer a pending confirmation. Returns `false` when the id is unknown (already settled). */
    public resolveConfirmation(id: string, approve: boolean): boolean {
        return this.confirmations.answer(id, approve);
    }

    /** Resolves once the confirmation is approved, declined, expired or abandoned. */
    public whenSettled(id: string): Promise<ConfirmationDecision> {
        return this.confirmations.whenDecided(id);
    }

    public disconnect(): void {
        this.clearTurnTimer();
        this.subscription?.unsubscribe();
        this.subscription = null;
        this.turnActive = false;
        this.onDisconnected();

        try {
            this.transport.disconnect();
        } catch {
            // socket was never initialised
        }
    }

    private async awaitOutcome(): Promise<TurnOutcome> {
        const winner = await this.confirmations.awaitNextRequest(this.messageComplete.promise);

        if (winner === 'complete') {
            this.clearTurnTimer();
            this.turnActive = false;

            if (this.turnTimedOut) {
                throw new Error(
                    `Veeam Intelligence did not complete the answer within ${Math.round(this.options.turnTimeoutMs / 1000)} seconds`,
                );
            }

            return this.snapshot('complete');
        }

        return this.snapshot('awaiting_confirmation', winner);
    }

    private snapshot(kind: 'complete'): TurnOutcome;
    private snapshot(kind: 'awaiting_confirmation', request: ConfirmationRequest): TurnOutcome;
    private snapshot(kind: 'complete' | 'awaiting_confirmation', request?: ConfirmationRequest): TurnOutcome {
        const message = this.message.slice(this.reported.message);
        const artifacts = this.artifacts.slice(this.reported.artifacts);
        const actions = this.actions.slice(this.reported.actions);

        this.reported = { message: this.message.length, artifacts: this.artifacts.length, actions: this.actions.length };

        if (kind === 'complete') {
            return { kind, message, artifacts, actions };
        }

        return { kind, request: request!, message, artifacts, actions };
    }

    private startTurnTimer(): void {
        this.clearTurnTimer();
        this.turnTimer = setTimeout(() => {
            this.turnTimedOut = true;
            log.warn(`turn exceeded ${Math.round(this.options.turnTimeoutMs / 1000)} s; closing the Veeam Intelligence connection`);
            this.transport.disconnect();
        }, this.options.turnTimeoutMs);
    }

    private clearTurnTimer(): void {
        if (this.turnTimer !== null) {
            clearTimeout(this.turnTimer);
            this.turnTimer = null;
        }
    }

    // Transport events

    /**
     * Single entry point for everything the connection reports. The `never` assignment in `default`
     * makes the compiler reject a new `TransportInboundEvent` member until it is handled here.
     */
    private onTransportEvent(event: TransportInboundEvent): void {
        switch (event.type) {
            case 'connected':
                this.connected = true;
                return;
            case 'chunk':
                this.onChunk(event.payload);
                return;
            case 'toolInvocation':
                // Deliberately not awaited: the turn advances through `messageComplete` and the
                // confirmation deferreds, not through this promise. Rejections would otherwise
                // escape as an unhandled rejection and take the MCP process down with them.
                void this.onToolInvocation(event.payload).catch((error: unknown) => {
                    log.error(`tool invocation ${event.payload.invocation_id} failed: ${toMessage(error)}`);
                    this.emitToolResult(event.payload.invocation_id, 'error', {
                        message: `The MCP server failed to handle this tool invocation: ${toMessage(error)}`,
                    });
                });
                return;
            case 'toolInvocationInvalid':
                log.warn(`rejecting malformed tool invocation ${event.invocationId}: ${event.reason}`);
                this.emitToolResult(event.invocationId, 'error', {
                    message: `Veeam Intelligence sent a tool invocation the MCP server could not read (${event.reason})`,
                });
                return;
            case 'responseError':
                this.onResponseError(event.details);
                return;
            case 'connectError':
                this.onConnectError(event.error);
                return;
            case 'disconnected':
                this.onDisconnected();
                return;
            case 'reconnectError':
            case 'reconnectFailed':
                // socket.io has stopped retrying; the `disconnected` that follows ends the turn.
                return;
            default: {
                const unhandled: never = event;
                log.warn(`unhandled Veeam Intelligence transport event: ${JSON.stringify(unhandled)}`);
                return;
            }
        }
    }

    private onChunk(chunk: ResponseChunk): void {
        switch (chunk.type) {
            case 'token':
                this.message += chunk.payload;
                break;
            case 'artifact':
                this.artifacts.push(chunk.payload);
                break;
        }
    }

    private onResponseError(details: string): void {
        log.warn(`Veeam Intelligence response error: ${details}`);
        this.message += `${this.message.length > 0 ? '\n\n' : ''}[Veeam Intelligence error] ${details}`;
    }

    private onDisconnected(): void {
        this.connected = false;

        // Anything still waiting for the user can no longer be answered on this socket.
        this.confirmations.expireAll();

        this.messageComplete.resolve();
    }

    /**
     * The handshake was refused. A missing or stale token is recoverable, so re-authenticate and
     * let the next connect carry a fresh one. The other codes are not handled yet: the socket stays
     * down and the turn ends through `disconnected` with whatever had already been streamed.
     */
    private onConnectError(error: ConnectionError): void {
        switch (error.code) {
            case ConnectionErrorCode.TokenInvalid:
            case ConnectionErrorCode.TokenRequired:
                void this.refreshAuthToken().catch((cause: unknown) => {
                    log.error(`could not refresh the Veeam Intelligence token: ${toMessage(cause)}`);
                });
                return;
            default:
                log.warn(`Veeam Intelligence connection error (${error.code}): ${error.details}`);
                return;
        }
    }

    private async refreshAuthToken(): Promise<void> {
        const authResult = await this.productRestClient.authenticateChatService();
        this.authResponse = authResult.response;
        this.transport.setAuthToken(this.authResponse.access_token);
    }

    private async onToolInvocation(config: ToolInvocationConfig): Promise<void> {
        const invocationId = config.invocation_id;

        if (!isAdvancedMode(this.effectiveMode)) {
            this.emitToolResult(invocationId, 'error', {
                message: 'Chatbot running in "Base" mode. Tool calls are restricted in this mode',
            });
            return;
        }

        switch (config.tool_name) {
            case 'fetch_data_from_endpoint':
                this.report(invocationId, await this.actionExecutor.execute(config));
                return;
            case 'request_user_interaction':
                this.report(invocationId, await this.interactions.handle(config));
                return;
            default: {
                // Unreachable: the wire schema admits only the tool names above.
                const unsupported: never = config;
                log.warn(`unsupported client tool requested by Veeam Intelligence: ${JSON.stringify(unsupported)}`);
                this.emitToolResult(invocationId, 'error', {
                    message: 'Failed to provide Veeam Intelligence response. Unsupported client tool',
                });
            }
        }
    }

    /** Record what the handler decided for the MCP client, then answer Veeam Intelligence. */
    private report(invocationId: string, handled: HandledInvocation): void {
        if (handled.outcome !== undefined) {
            this.actions.push(handled.outcome);
        }

        this.emitToolResult(invocationId, handled.result.status, handled.result.data);
    }

    private emitToolResult(invocationId: string, status: string, data: unknown): void {
        if (!this.connected) {
            log.warn(`cannot send tool result for ${invocationId}: Veeam Intelligence connection is closed`);
            return;
        }

        this.transport.emit({
            name: 'tool_result',
            value: {
                invocation_id: invocationId,
                status,
                data,
            },
        });
    }
}
