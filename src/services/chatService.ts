/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { Socket } from '@/socket/Socket';
import { ServiceInfo, ChatBotAuthResult, Artifact, ChatbotMode, ToolInvocationConfig, MessageRole } from '@/common/types';
import { SocketEmitConfig, SocketMessageData, SocketSubscribeHandlers, ResponseChunk } from '@/socket/types';
import { ProductRestClient } from '@/product';
import { ToolCallingError } from '@/common/errors';
import { Deferred } from '@/utils';
import { SendMessageResponse } from './types';

export class ChatService implements SocketSubscribeHandlers {
    private socket: Socket;
    private serviceInfo!: ServiceInfo;
    private authResponse!: ChatBotAuthResult;
    private productRestClient: ProductRestClient;
    private message: string = '';
    private artifacts: Artifact[] = [];

    // Used to coordinate async message streaming: sendMessage() waits on this promise
    // until onDisconnected() resolves it, ensuring we've received all chunks before returning
    private messageComplete!: Deferred<void>;

    constructor(productRestClient: ProductRestClient) {
        this.productRestClient = productRestClient;
        this.socket = new Socket();
    }

    public async initialize(): Promise<void> {
        const serviceInfo = await this.productRestClient.getServiceInfo();
        const authResult = await this.productRestClient.authenticateChatService();

        this.serviceInfo = serviceInfo;
        this.authResponse = authResult.response;

        this.setupSocket();
    }

    private setupSocket(): void {
        this.socket.initSocket(this.serviceInfo, {
            socketPath: '/socket.io',
            withCredentials: true,
        });
        this.socket.setAuthToken(this.authResponse.access_token);
        this.socket.connect();
    }

    public async sendMessage(message: string): Promise<SendMessageResponse> {
        this.message = '';
        this.artifacts = [];
        this.messageComplete = new Deferred<void>();

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

        this.socket.subscribe(this);
        this.socket.emit(config);

        await this.messageComplete.promise;

        return { message: this.message, artifacts: this.artifacts };
    }

    public async reset(): Promise<void> {
        this.socket.disconnect();
        await this.initialize();
    }

    public disconnect(): void {
        this.socket.disconnect();
    }

    public getMessage(): string {
        return this.message;
    }

    public getArtifacts(): Artifact[] {
        return this.artifacts;
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

    public async onConnected(_: SocketMessageData): Promise<void> {}

    public async onConnectionError(_: SocketMessageData): Promise<void> {}

    public async onConnectionInfoError(_: SocketMessageData): Promise<void> {}

    public async onDisconnected(_: SocketMessageData): Promise<void> {
        this.messageComplete?.resolve();
    }

    public async onReconnectError(_: SocketMessageData): Promise<void> {}

    public async onReconnectFailed(_: SocketMessageData): Promise<void> {}

    public async onResponseError(_: SocketMessageData): Promise<void> {}

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

        if (this.serviceInfo.chatbotMode === ChatbotMode.Base) {
            this.emitToolResult(config.invocation_id, 'error', 'Chatbot running in "Base" mode. Tool calls are restricted in this mode');
            return;
        }

        try {
            const { data, status } = await this.productRestClient.getToolCallData(config);
            this.emitToolResult(config.invocation_id, status, data);
        } catch (err) {
            const error = err as ToolCallingError;
            this.emitToolResult(config.invocation_id, 'error', error.data);
        }
    }

    public async onUnknownProduct(_: SocketMessageData): Promise<void> {}

    private emitToolResult(invocationId: string, status: string, data: unknown): void {
        this.socket.emit({
            name: 'tool_result',
            value: {
                invocation_id: invocationId,
                status,
                data,
            },
        });
    }
}
