/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { describe, it, expect, beforeEach, afterEach, jest } from '@jest/globals';
import { createServer, Server as HttpServer } from 'node:http';
import { AddressInfo } from 'node:net';
import { Server as SocketIoServer, Socket as ServerSocket } from 'socket.io';

import { ChatService } from '../chatService';
import { ChatbotMode, CommonInvokeConfig, ServiceInfo, ToolCallResult } from '@/common/types';
import type { ToolInvocationInput } from '@/common/schemas';
import type { ProductRestClient } from '@/product/ProductRestClient';

process.env.PRODUCT_NAME = 'vbr';

interface ToolResultMessage {
    invocation_id: string;
    status: string;
    data: unknown;
}

/**
 * Minimal Veeam Intelligence (EDCP) fake: on `chat` it streams a token, sends the configured tool
 * invocations one after another (waiting for each `tool_result`), streams a closing token and
 * disconnects — exactly how the real server ends a turn.
 */
class FakeEdcpServer {
    public readonly http: HttpServer;
    public readonly io: SocketIoServer;
    public readonly toolResults: ToolResultMessage[] = [];
    public handshakeAuth: Record<string, unknown> = {};
    public invocations: ToolInvocationInput[] = [];

    constructor() {
        this.http = createServer();
        this.io = new SocketIoServer(this.http, { path: '/vbr/socket.io' });

        this.io.on('connection', (socket: ServerSocket) => {
            this.handshakeAuth = socket.handshake.auth as Record<string, unknown>;

            socket.on('chat', () => {
                socket.emit('response_chunk', { type: 'token', payload: 'Working on it.' });
                this.next(socket);
            });

            socket.on('tool_result', (result: ToolResultMessage) => {
                this.toolResults.push(result);
                this.next(socket);
            });
        });
    }

    private next(socket: ServerSocket): void {
        const invocation = this.invocations.shift();
        if (invocation !== undefined) {
            socket.emit('tool_invocation', invocation);
            return;
        }

        socket.emit('response_chunk', { type: 'token', payload: ' Done.' });
        socket.emit('response_chunk', { type: 'artifact', payload: { id: 'a1', type: 'string', data: 'artifact' } });
        socket.disconnect(true);
    }

    public async listen(): Promise<string> {
        await new Promise<void>((resolve) => this.http.listen(0, '127.0.0.1', resolve));
        const { port } = this.http.address() as AddressInfo;
        return `http://127.0.0.1:${port}/`;
    }

    public async close(): Promise<void> {
        this.io.disconnectSockets(true);
        await this.io.close();
    }
}

const startJobInvocation: ToolInvocationInput = {
    invocation_id: 'inv-1',
    tool_name: 'fetch_data_from_endpoint',
    parameters: {
        endpoint_path: '/api/v1/jobs/e9b6424b/start',
        query_params: {},
        method: 'POST',
        body: '{"performActiveFull":false}',
        headers: { 'Content-Type': 'application/json' },
        description: "Start backup job 'Nightly SQL' now",
    },
};

function createClient(chatbotApiUrl: string, mode: ChatbotMode, toolCallResult: ToolCallResult, productVersion = '13.1.0.411') {
    const serviceInfo: ServiceInfo = {
        chatbotApiUrl,
        chatbotEnabled: true,
        chatbotMode: mode,
        productName: 'Veeam Backup and Replication',
        productVersion,
    };
    const getToolCallData = jest.fn(async (_config: CommonInvokeConfig) => toolCallResult);
    const client: ProductRestClient = {
        getServiceInfo: async () => serviceInfo,
        authenticateChatService: async () => ({
            source: 'Direct',
            response: { access_token: 'token', issued_unix_ts: 0, ttl_sec: 3600, product_suffix: 'vbr' },
        }),
        getToolCallData,
    };
    return { client, getToolCallData };
}

describe('ChatService actions (AdvancedWithActions)', () => {
    let server: FakeEdcpServer;
    let apiUrl: string;
    let chat: ChatService | undefined;

    beforeEach(async () => {
        server = new FakeEdcpServer();
        apiUrl = await server.listen();
        chat = undefined;
    });

    afterEach(async () => {
        chat?.disconnect();
        await server.close();
    });

    const okResult: ToolCallResult = { status: 'success', data: { status: 201, body: { id: 'session-1' } } };

    it('pauses on a checklist action, executes it after approval and finishes the turn', async () => {
        server.invocations = [startJobInvocation];
        const { client, getToolCallData } = createClient(apiUrl, ChatbotMode.AdvancedWithActions, okResult);
        chat = new ChatService(client, { productCode: 'vbr', confirmationTimeoutMs: 5000, turnTimeoutMs: 5000 });
        await chat.initialize();

        const first = await chat.sendMessage('Start the Nightly SQL job');
        expect(first.kind).toBe('awaiting_confirmation');
        expect(first.message).toBe('Working on it.');
        if (first.kind !== 'awaiting_confirmation') throw new Error('unreachable');

        expect(first.request.title).toBe('Start this backup job?');
        expect(first.request.method).toBe('POST');
        expect(first.request.path).toBe('/api/v1/jobs/e9b6424b/start');
        expect(first.request.body).toBe('{"performActiveFull":false}');
        expect(first.request.dynamicDescription).toBe("Start backup job 'Nightly SQL' now");
        expect(getToolCallData).not.toHaveBeenCalled();
        expect(server.handshakeAuth.mode).toBe('AdvancedWithActions');

        expect(chat.resolveConfirmation(first.request.id, true)).toBe(true);
        const second = await chat.resume();

        expect(second.kind).toBe('complete');
        expect(second.message).toBe(' Done.');
        expect(second.artifacts).toHaveLength(1);
        expect(second.actions).toEqual([
            expect.objectContaining({
                action_id: first.request.id,
                decision: 'approved',
                executed: true,
                http_status: 201,
                method: 'POST',
                path: '/api/v1/jobs/e9b6424b/start',
            }),
        ]);
        expect(getToolCallData).toHaveBeenCalledTimes(1);
        expect(getToolCallData.mock.calls[0][0]).toEqual(startJobInvocation);
        expect(server.toolResults).toEqual([
            { invocation_id: 'inv-1', status: 'success', data: { status: 201, body: { id: 'session-1' } } },
        ]);
    });

    it('sends the user_cancelled_action code when the user declines', async () => {
        server.invocations = [startJobInvocation];
        const { client, getToolCallData } = createClient(apiUrl, ChatbotMode.AdvancedWithActions, okResult);
        chat = new ChatService(client, { productCode: 'vbr', confirmationTimeoutMs: 5000, turnTimeoutMs: 5000 });
        await chat.initialize();

        const first = await chat.sendMessage('Start the job');
        if (first.kind !== 'awaiting_confirmation') throw new Error('expected confirmation');

        chat.resolveConfirmation(first.request.id, false);
        const second = await chat.resume();

        expect(second.kind).toBe('complete');
        expect(second.actions[0]).toEqual(expect.objectContaining({ decision: 'declined', executed: false }));
        expect(getToolCallData).not.toHaveBeenCalled();
        expect(server.toolResults).toEqual([{ invocation_id: 'inv-1', status: 'error', data: { code: 'user_cancelled_action' } }]);
    });

    it('declines automatically when the confirmation times out', async () => {
        server.invocations = [startJobInvocation];
        const { client, getToolCallData } = createClient(apiUrl, ChatbotMode.AdvancedWithActions, okResult);
        chat = new ChatService(client, { productCode: 'vbr', confirmationTimeoutMs: 50, turnTimeoutMs: 5000 });
        await chat.initialize();

        const first = await chat.sendMessage('Start the job');
        if (first.kind !== 'awaiting_confirmation') throw new Error('expected confirmation');

        const settled = await chat.whenSettled(first.request.id);
        expect(settled).toBe('expired');
        expect(chat.resolveConfirmation(first.request.id, true)).toBe(false);

        const second = await chat.resume();
        expect(second.kind).toBe('complete');
        expect(second.actions[0]).toEqual(expect.objectContaining({ decision: 'expired', executed: false }));
        expect(getToolCallData).not.toHaveBeenCalled();
        expect(server.toolResults[0].data).toEqual({ code: 'user_cancelled_action' });
    });

    it('rejects state-changing calls that are not in the policy without asking', async () => {
        server.invocations = [
            {
                invocation_id: 'inv-del',
                tool_name: 'fetch_data_from_endpoint',
                parameters: { endpoint_path: '/api/v1/jobs/e9b6424b', query_params: {}, method: 'DELETE' },
            },
        ];
        const { client, getToolCallData } = createClient(apiUrl, ChatbotMode.AdvancedWithActions, okResult);
        chat = new ChatService(client, { productCode: 'vbr', confirmationTimeoutMs: 5000, turnTimeoutMs: 5000 });
        await chat.initialize();

        const outcome = await chat.sendMessage('Delete the job');

        expect(outcome.kind).toBe('complete');
        expect(outcome.actions[0]).toEqual(expect.objectContaining({ decision: 'rejected', executed: false, method: 'DELETE' }));
        expect(getToolCallData).not.toHaveBeenCalled();
        expect(server.toolResults[0].status).toBe('error');
        expect(JSON.stringify(server.toolResults[0].data)).toContain('not allowed');
    });

    it('runs whitelisted POST reads and GET reads silently', async () => {
        server.invocations = [
            {
                invocation_id: 'inv-acl',
                tool_name: 'fetch_data_from_endpoint',
                parameters: { endpoint_path: '/api/v1/acl', query_params: {}, method: 'POST', body: '{}' },
            },
            {
                invocation_id: 'inv-get',
                tool_name: 'fetch_data_from_endpoint',
                parameters: { endpoint_path: '/api/v1/jobs', query_params: { limit: 5 } },
            },
        ];
        const getResult: ToolCallResult = { status: 'success', data: { status: 200, body: [] } };
        const { client, getToolCallData } = createClient(apiUrl, ChatbotMode.AdvancedWithActions, getResult);
        chat = new ChatService(client, { productCode: 'vbr', confirmationTimeoutMs: 5000, turnTimeoutMs: 5000 });
        await chat.initialize();

        const outcome = await chat.sendMessage('List jobs');

        expect(outcome.kind).toBe('complete');
        expect(outcome.actions).toEqual([]);
        expect(getToolCallData).toHaveBeenCalledTimes(2);
        expect(server.toolResults.map((r) => r.invocation_id)).toEqual(['inv-acl', 'inv-get']);
        expect(server.toolResults[1]).toEqual({ invocation_id: 'inv-get', status: 'success', data: { status: 200, body: [] } });
    });

    it('downgrades the handshake to Advanced when the product version has no action policy and rejects writes', async () => {
        server.invocations = [startJobInvocation];
        const { client, getToolCallData } = createClient(apiUrl, ChatbotMode.AdvancedWithActions, okResult, '13.0.1.1071');
        chat = new ChatService(client, { productCode: 'vbr', confirmationTimeoutMs: 5000, turnTimeoutMs: 5000 });
        await chat.initialize();

        const outcome = await chat.sendMessage('Start the job');

        expect(chat.getEffectiveMode()).toBe(ChatbotMode.Advanced);
        expect(server.handshakeAuth.mode).toBe('Advanced');
        expect(outcome.kind).toBe('complete');
        expect(getToolCallData).not.toHaveBeenCalled();
        expect(server.toolResults[0].status).toBe('error');
    });

    it('relays an assistant-posed confirmation question and answers with the resolved value', async () => {
        server.invocations = [
            {
                invocation_id: 'inv-q',
                tool_name: 'request_user_interaction',
                parameters: { kind: 'confirmation', title: 'Proceed with cleanup?', description: 'Removes stale restore points.' },
            },
        ];
        const { client } = createClient(apiUrl, ChatbotMode.AdvancedWithActions, okResult);
        chat = new ChatService(client, { productCode: 'vbr', confirmationTimeoutMs: 5000, turnTimeoutMs: 5000 });
        await chat.initialize();

        const first = await chat.sendMessage('Clean up');
        if (first.kind !== 'awaiting_confirmation') throw new Error('expected confirmation');
        expect(first.request.kind).toBe('interaction');
        expect(first.request.title).toBe('Proceed with cleanup?');

        chat.resolveConfirmation(first.request.id, true);
        const second = await chat.resume();

        expect(second.kind).toBe('complete');
        expect(server.toolResults).toEqual([{ invocation_id: 'inv-q', status: 'success', data: { status: 'resolved', value: true } }]);
    });

    it('fails the turn when it exceeds the turn timeout', async () => {
        server.invocations = [startJobInvocation];
        const { client } = createClient(apiUrl, ChatbotMode.AdvancedWithActions, okResult);
        chat = new ChatService(client, { productCode: 'vbr', confirmationTimeoutMs: 5000, turnTimeoutMs: 100 });
        await chat.initialize();

        const first = await chat.sendMessage('Start the job');
        if (first.kind !== 'awaiting_confirmation') throw new Error('expected confirmation');

        await expect(chat.resume()).rejects.toThrow('did not complete');
    });
});
