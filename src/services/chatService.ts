/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { Subscription } from 'rxjs';
import { v4 as uuidv4 } from 'uuid';

import { Socket } from '@/socket/Socket';
import {
    ServiceInfo,
    ChatBotAuthResult,
    Artifact,
    ChatbotMode,
    ToolInvocationConfig,
    CommonInvokeConfig,
    RequestUserInteractionConfig,
    MessageRole,
    isAdvancedMode,
    ToolCallResult,
} from '@/common/types';
import { SocketEmitConfig, SocketMessageData, SocketSubscribeHandlers, ResponseChunk } from '@/socket/types';
import type { ProductRestClient } from '@/product/ProductRestClient';
import { Deferred } from '@/utils';
import { log } from '@/utils/logger';
import { ActionOutcome, ConfirmationDecision, ConfirmationRequest, USER_CANCELLED_ACTION_RESULT } from '@/actions/types';
import { FetchGate } from '@/actions/fetchGate';
import { resolveActionsConfig } from '@/actions/resolveActionsConfig';
import { ChatServiceOptions, TurnOutcome } from './types';

interface PendingConfirmation {
    request: ConfirmationRequest;
    decision: Deferred<ConfirmationDecision>;
}

const DEFAULT_OPTIONS: ChatServiceOptions = {
    productCode: process.env.PRODUCT_NAME ?? '',
    confirmationTimeoutMs: 1500 * 1000,
    turnTimeoutMs: 3600 * 1000,
};

/**
 * One Veeam Intelligence chat connection. A turn starts with `sendMessage()` and ends when the
 * server closes the socket. When Veeam Intelligence proposes an action that needs the user's
 * approval, the turn pauses: the outcome is `awaiting_confirmation`, the socket stays open, and
 * the caller continues with `resolveConfirmation()` + `resume()`.
 */
export class ChatService implements SocketSubscribeHandlers {
    private socket: Socket;
    private serviceInfo!: ServiceInfo;
    private authResponse!: ChatBotAuthResult;
    private productRestClient: ProductRestClient;
    private readonly options: ChatServiceOptions;

    private effectiveMode: ChatbotMode = ChatbotMode.Base;
    private fetchGate: FetchGate = new FetchGate(undefined);

    private message: string = '';
    private artifacts: Artifact[] = [];
    private actions: ActionOutcome[] = [];
    private reported = { message: 0, artifacts: 0, actions: 0 };

    // Resolved by onDisconnected(): the server closes the socket when the answer is complete.
    private messageComplete: Deferred<void> = new Deferred<void>();
    // Resolved when a tool invocation needs the user's decision before the turn can continue.
    private confirmationRequested: Deferred<ConfirmationRequest> = new Deferred<ConfirmationRequest>();
    private confirmationQueue: ConfirmationRequest[] = [];
    // `true` while awaitOutcome() is racing and can take a confirmation directly (not via the queue).
    private waiterActive = false;
    private pending = new Map<string, PendingConfirmation>();

    private subscription: Subscription | null = null;
    private turnTimer: NodeJS.Timeout | null = null;
    private turnTimedOut = false;
    private turnActive = false;
    private connected = false;

    constructor(productRestClient: ProductRestClient, options: Partial<ChatServiceOptions> = {}) {
        this.productRestClient = productRestClient;
        this.options = { ...DEFAULT_OPTIONS, ...options };
        this.socket = new Socket();
    }

    public async initialize(): Promise<void> {
        const serviceInfo = await this.productRestClient.getServiceInfo();
        const authResult = await this.productRestClient.authenticateChatService();

        this.serviceInfo = serviceInfo;
        this.authResponse = authResult.response;

        const actionsConfig = resolveActionsConfig(serviceInfo, this.options.productCode);
        this.effectiveMode = actionsConfig.effectiveMode;
        this.fetchGate = actionsConfig.fetchGate;

        this.setupSocket();
    }

    public getEffectiveMode(): ChatbotMode {
        return this.effectiveMode;
    }

    public getServiceInfo(): ServiceInfo {
        return this.serviceInfo;
    }

    private setupSocket(): void {
        this.socket.initSocket(this.serviceInfo, {
            socketPath: '/socket.io',
            withCredentials: true,
            mode: this.effectiveMode,
        });
        this.socket.setAuthToken(this.authResponse.access_token);

        // Subscribe exactly once per connection; re-subscribing on every message duplicates handlers.
        this.subscription?.unsubscribe();
        this.subscription = this.socket.subscribe(this);

        this.socket.connect();
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
        this.confirmationQueue = [];
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
        this.socket.emit(config);

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
        const entry = this.pending.get(id);
        if (entry === undefined) {
            return false;
        }

        entry.decision.resolve(approve ? 'approved' : 'declined');
        return true;
    }

    /** Resolves once the confirmation is approved, declined, expired or abandoned. */
    public whenSettled(id: string): Promise<ConfirmationDecision> {
        const entry = this.pending.get(id);
        return entry === undefined ? Promise.resolve('expired') : entry.decision.promise;
    }

    public hasPendingConfirmations(): boolean {
        return this.pending.size > 0;
    }

    public async reset(): Promise<void> {
        this.disconnect();
        await this.initialize();
    }

    public disconnect(): void {
        this.clearTurnTimer();
        this.subscription?.unsubscribe();
        this.subscription = null;
        this.turnActive = false;

        try {
            this.socket.disconnect();
        } catch {
            // socket was never initialised
        }
    }

    public getMessage(): string {
        return this.message;
    }

    public getArtifacts(): Artifact[] {
        return this.artifacts;
    }

    private async awaitOutcome(): Promise<TurnOutcome> {
        const queued = this.confirmationQueue.shift();
        if (queued !== undefined) {
            return this.snapshot('awaiting_confirmation', queued);
        }

        this.confirmationRequested = new Deferred<ConfirmationRequest>();
        this.waiterActive = true;

        const winner = await Promise.race([
            this.messageComplete.promise.then(() => 'complete' as const),
            this.confirmationRequested.promise,
        ]);

        this.waiterActive = false;

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
            this.socket.disconnect();
        }, this.options.turnTimeoutMs);
    }

    private clearTurnTimer(): void {
        if (this.turnTimer !== null) {
            clearTimeout(this.turnTimer);
            this.turnTimer = null;
        }
    }

    // Socket io handlers
    public async onChunk(data: SocketMessageData): Promise<void> {
        const chunk = JSON.parse(data.message) as ResponseChunk;

        switch (chunk.type) {
            case 'token':
                this.message += chunk.payload;
                break;
            case 'artifact':
                this.artifacts.push(chunk.payload);
                break;
        }
    }

    public async onConnected(_: SocketMessageData): Promise<void> {
        this.connected = true;
    }

    public async onConnectionError(_: SocketMessageData): Promise<void> {}

    public async onConnectionInfoError(_: SocketMessageData): Promise<void> {}

    public async onDisconnected(_: SocketMessageData): Promise<void> {
        this.connected = false;

        // Anything still waiting for the user can no longer be answered on this socket.
        for (const entry of this.pending.values()) {
            entry.decision.resolve('expired');
        }

        this.messageComplete.resolve();
    }

    public async onReconnectError(_: SocketMessageData): Promise<void> {}

    public async onReconnectFailed(_: SocketMessageData): Promise<void> {}

    public async onResponseError(data: SocketMessageData): Promise<void> {
        log.warn(`Veeam Intelligence response error: ${data.message}`);
        this.message += `${this.message.length > 0 ? '\n\n' : ''}[Veeam Intelligence error] ${data.message}`;
    }

    public async onTokenInvalid(_: SocketMessageData): Promise<void> {
        const authResult = await this.productRestClient.authenticateChatService();
        this.authResponse = authResult.response;
        this.socket.setAuthToken(this.authResponse.access_token);
    }

    public async onTokenRequired(_: SocketMessageData): Promise<void> {
        const authResult = await this.productRestClient.authenticateChatService();
        this.authResponse = authResult.response;
        this.socket.setAuthToken(this.authResponse.access_token);
    }

    public async onToolInvocation(data: SocketMessageData): Promise<void> {
        const config = JSON.parse(data.message) as ToolInvocationConfig;
        const invocationId = config.invocation_id;
        const toolName = String(config.tool_name);

        if (!isAdvancedMode(this.effectiveMode)) {
            this.emitToolResult(invocationId, 'error', {
                message: 'Chatbot running in "Base" mode. Tool calls are restricted in this mode',
            });
            return;
        }

        switch (config.tool_name) {
            case 'fetch_data_from_endpoint':
                await this.handleFetchInvocation(config);
                return;
            case 'request_user_interaction':
                await this.handleUserInteraction(config);
                return;
            default: {
                log.warn(`unsupported client tool requested by Veeam Intelligence: ${toolName}`);
                this.emitToolResult(invocationId, 'error', {
                    message: `Failed to provide Veeam Intelligence response. Unsupported client tool ${toolName}`,
                });
            }
        }
    }

    public async onUnknownProduct(_: SocketMessageData): Promise<void> {}

    private async handleFetchInvocation(config: CommonInvokeConfig): Promise<void> {
        const method = config.parameters.method ?? 'GET';
        const path = config.parameters.endpoint_path;
        const decision = this.fetchGate.decide(method, path);

        switch (decision.kind) {
            case 'allowed': {
                const result = await this.productRestClient.getToolCallData(config);
                this.emitToolResult(config.invocation_id, result.status, result.data);
                return;
            }
            case 'rejected': {
                log.warn(`action rejected by policy: ${decision.reason}`);
                this.actions.push({
                    action_id: '',
                    title: `${method} ${path}`,
                    method,
                    path,
                    decision: 'rejected',
                    executed: false,
                    error: decision.reason,
                });
                this.emitToolResult(config.invocation_id, 'error', { message: decision.reason });
                return;
            }
            case 'confirm': {
                const request: ConfirmationRequest = {
                    id: uuidv4(),
                    invocationId: config.invocation_id,
                    kind: 'action',
                    title: decision.title,
                    description: decision.description,
                    method,
                    path,
                    createdAt: Date.now(),
                    expiresAt: Date.now() + this.options.confirmationTimeoutMs,
                };
                if (config.parameters.description !== undefined) {
                    request.dynamicDescription = config.parameters.description;
                }
                if (config.parameters.query_params && Object.keys(config.parameters.query_params).length > 0) {
                    request.queryParams = config.parameters.query_params;
                }
                if (config.parameters.body !== undefined && config.parameters.body.length > 0) {
                    request.body = config.parameters.body;
                }

                const outcome = await this.waitForDecision(request);
                const actionOutcome: ActionOutcome = {
                    action_id: request.id,
                    title: request.title,
                    method,
                    path,
                    decision: outcome,
                    executed: false,
                };

                if (outcome === 'approved') {
                    const result = await this.productRestClient.getToolCallData(config);
                    actionOutcome.executed = result.status === 'success';
                    const httpStatus = ChatService.extractHttpStatus(result);
                    if (httpStatus !== undefined) {
                        actionOutcome.http_status = httpStatus;
                    }
                    if (result.status !== 'success') {
                        actionOutcome.error = ChatService.describeError(result);
                    }
                    log.info(
                        `action ${outcome}: ${method} ${path} → ${result.status}${httpStatus !== undefined ? ` (${httpStatus})` : ''}`,
                    );
                    this.emitToolResult(config.invocation_id, result.status, result.data);
                } else {
                    log.info(`action ${outcome}: ${method} ${path}`);
                    this.emitToolResult(config.invocation_id, 'error', USER_CANCELLED_ACTION_RESULT);
                }

                this.actions.push(actionOutcome);
                return;
            }
        }
    }

    private async handleUserInteraction(config: RequestUserInteractionConfig): Promise<void> {
        const { kind, title, label, description } = config.parameters;

        if (kind !== 'confirmation') {
            log.warn(`user interaction of kind "${kind}" is not supported by the MCP server; answering "cancelled"`);
            this.emitToolResult(config.invocation_id, 'success', { status: 'cancelled' });
            return;
        }

        const request: ConfirmationRequest = {
            id: uuidv4(),
            invocationId: config.invocation_id,
            kind: 'interaction',
            title: title ?? label ?? 'Veeam Intelligence asks for confirmation',
            description: description ?? '',
            createdAt: Date.now(),
            expiresAt: Date.now() + this.options.confirmationTimeoutMs,
        };

        const outcome = await this.waitForDecision(request);
        this.actions.push({ action_id: request.id, title: request.title, decision: outcome, executed: false });

        if (outcome === 'expired') {
            this.emitToolResult(config.invocation_id, 'success', { status: 'cancelled' });
            return;
        }

        this.emitToolResult(config.invocation_id, 'success', { status: 'resolved', value: outcome === 'approved' });
    }

    /**
     * Publish the confirmation to the current `sendMessage()`/`resume()` waiter and block until the
     * user decides or the confirmation times out.
     */
    private async waitForDecision(request: ConfirmationRequest): Promise<ConfirmationDecision> {
        const entry: PendingConfirmation = {
            request,
            decision: new Deferred<ConfirmationDecision>(),
        };
        this.pending.set(request.id, entry);

        // Hand the request to whoever is awaiting the turn outcome, or queue it for the next awaiter.
        if (this.waiterActive) {
            this.waiterActive = false;
            this.confirmationRequested.resolve(request);
        } else {
            this.confirmationQueue.push(request);
        }

        const timer = setTimeout(() => entry.decision.resolve('expired'), this.options.confirmationTimeoutMs);
        const decision = await entry.decision.promise;
        clearTimeout(timer);

        this.pending.delete(request.id);

        return decision;
    }

    private emitToolResult(invocationId: string, status: string, data: unknown): void {
        if (!this.connected) {
            log.warn(`cannot send tool result for ${invocationId}: Veeam Intelligence connection is closed`);
            return;
        }

        this.socket.emit({
            name: 'tool_result',
            value: {
                invocation_id: invocationId,
                status,
                data,
            },
        });
    }

    private static extractHttpStatus(result: ToolCallResult): number | undefined {
        const data = result.data as { status?: unknown } | null;
        return typeof data?.status === 'number' ? data.status : undefined;
    }

    private static describeError(result: ToolCallResult): string {
        const data = result.data as { status?: unknown; body?: unknown; message?: unknown } | null;
        if (typeof data?.message === 'string') {
            return data.message;
        }
        const body = typeof data?.body === 'string' ? data.body : JSON.stringify(data?.body ?? '');
        const status = typeof data?.status === 'number' ? String(data.status) : '?';
        return `HTTP ${status}: ${body}`;
    }
}
