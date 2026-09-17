/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { describe, it, expect, beforeEach, afterEach, jest } from '@jest/globals';
import { Observable, Subject } from 'rxjs';

import { ChatService } from '../chatService';
import { ChatbotMode, CommonInvokeConfig, ServiceInfo, SocketConfig, ToolCallResult } from '@/common/types';
import { ChatTransport, ConnectionErrorCode, SocketEmitConfig, TransportInboundEvent } from '@/socket/types';
import type { ProductRestClient } from '@/product/ProductRestClient';

process.env.PRODUCT_NAME = 'vbr';

/** Subject-backed ChatTransport double: drives session logic with no server and no socket. */
class FakeChatTransport implements ChatTransport {
    public sent: SocketEmitConfig[] = [];
    public tokens: (string | null)[] = [];
    public initializeCalls = 0;
    public connectCalls = 0;
    public disconnectCalls = 0;

    private subject = new Subject<TransportInboundEvent>();

    public readonly events: Observable<TransportInboundEvent> = this.subject.asObservable();

    public initialize(_serviceInfo: ServiceInfo, _config: SocketConfig): void {
        this.initializeCalls += 1;
    }

    public setAuthToken(token: string | null): void {
        this.tokens.push(token);
    }

    public connect(): void {
        this.connectCalls += 1;
    }

    public disconnect(): void {
        this.disconnectCalls += 1;
    }

    public emit(config: SocketEmitConfig): void {
        this.sent.push(config);
    }

    /** Fires a wire event into the service under test. */
    public fire(event: TransportInboundEvent): void {
        this.subject.next(event);
    }
}

function createClient(mode: ChatbotMode, toolCall: () => Promise<ToolCallResult>) {
    const serviceInfo: ServiceInfo = {
        chatbotApiUrl: 'https://vbr.local/',
        chatbotEnabled: true,
        chatbotMode: mode,
        productName: 'Veeam Backup and Replication',
        productVersion: '13.1.0.411',
    };
    const authenticateChatService = jest.fn(async () => ({
        source: 'Direct' as const,
        response: { access_token: 'token', issued_unix_ts: 0, ttl_sec: 3600, product_suffix: 'vbr' },
    }));
    const getToolCallData = jest.fn(async (_config: CommonInvokeConfig) => toolCall());
    const client: ProductRestClient = {
        getServiceInfo: async () => serviceInfo,
        authenticateChatService,
        getToolCallData,
    };
    return { client, authenticateChatService, getToolCallData };
}

const okResult: ToolCallResult = { status: 'success', data: { status: 200, body: [] } };

describe('ChatService over an injected transport', () => {
    let transport: FakeChatTransport;
    let stderr: jest.SpiedFunction<typeof process.stderr.write>;

    beforeEach(() => {
        transport = new FakeChatTransport();
        stderr = jest.spyOn(process.stderr, 'write').mockImplementation(() => true);
    });

    afterEach(() => {
        stderr.mockRestore();
    });

    const logged = (): string => stderr.mock.calls.map((call) => String(call[0])).join('');

    it('accumulates tokens and artifacts and completes the turn on disconnect', async () => {
        const { client } = createClient(ChatbotMode.AdvancedWithActions, async () => okResult);
        const chat = new ChatService(client, { productCode: 'vbr', confirmationTimeoutMs: 5000, turnTimeoutMs: 5000 }, transport);
        await chat.initialize();

        expect(transport.initializeCalls).toBe(1);
        expect(transport.connectCalls).toBe(1);
        expect(transport.tokens).toEqual(['token']);

        const turn = chat.sendMessage('List the jobs');
        transport.fire({ type: 'connected', sessionId: 'session-1' });
        transport.fire({ type: 'chunk', payload: { type: 'token', payload: 'Here ' } });
        transport.fire({ type: 'chunk', payload: { type: 'token', payload: 'you go.' } });
        transport.fire({ type: 'chunk', payload: { type: 'artifact', payload: { id: 'a1', type: 'string', data: 'x' } } });
        transport.fire({ type: 'disconnected' });

        const outcome = await turn;

        expect(outcome.kind).toBe('complete');
        expect(outcome.message).toBe('Here you go.');
        expect(outcome.artifacts).toHaveLength(1);
        expect(transport.sent[0].name).toBe('chat');
    });

    it('re-authenticates and re-arms the token when the handshake reports an invalid token', async () => {
        const { client, authenticateChatService } = createClient(ChatbotMode.Advanced, async () => okResult);
        const chat = new ChatService(client, { productCode: 'vbr', confirmationTimeoutMs: 5000, turnTimeoutMs: 5000 }, transport);
        await chat.initialize();
        expect(authenticateChatService).toHaveBeenCalledTimes(1);

        transport.fire({ type: 'connectError', error: { code: ConnectionErrorCode.TokenInvalid, details: 'expired' } });
        await new Promise((resolve) => setImmediate(resolve));

        expect(authenticateChatService).toHaveBeenCalledTimes(2);
        expect(transport.tokens).toEqual(['token', 'token']);
    });

    it('reports an unrecognised connection error instead of throwing inside the subscription', async () => {
        const { client } = createClient(ChatbotMode.Advanced, async () => okResult);
        const chat = new ChatService(client, { productCode: 'vbr', confirmationTimeoutMs: 5000, turnTimeoutMs: 5000 }, transport);
        await chat.initialize();

        expect(() => {
            transport.fire({ type: 'connectError', error: { code: ConnectionErrorCode.Unknown, details: 'xhr poll error' } });
        }).not.toThrow();

        expect(logged()).toContain('xhr poll error');
    });

    it('expires a pending confirmation when the service is disconnected locally', async () => {
        const { client, getToolCallData } = createClient(ChatbotMode.AdvancedWithActions, async () => okResult);
        const chat = new ChatService(client, { productCode: 'vbr', confirmationTimeoutMs: 60_000, turnTimeoutMs: 60_000 }, transport);
        await chat.initialize();

        const turn = chat.sendMessage('Start the job');
        transport.fire({ type: 'connected', sessionId: 'session-1' });
        transport.fire({
            type: 'toolInvocation',
            payload: {
                invocation_id: 'inv-start',
                tool_name: 'fetch_data_from_endpoint',
                parameters: { endpoint_path: '/api/v1/jobs/abc/start', query_params: {}, method: 'POST', body: '{}' },
            },
        });
        const first = await turn;
        if (first.kind !== 'awaiting_confirmation') throw new Error('expected a confirmation');

        chat.disconnect();

        await expect(chat.whenSettled(first.request.id)).resolves.toBe('expired');
        expect(chat.resolveConfirmation(first.request.id, true)).toBe(false);
        expect(getToolCallData).not.toHaveBeenCalled();
        expect(transport.disconnectCalls).toBe(1);
    });

    it('answers with an error tool_result when a tool invocation throws, and still completes the turn', async () => {
        const { client } = createClient(ChatbotMode.AdvancedWithActions, async () => {
            throw new Error('product REST client exploded');
        });
        const chat = new ChatService(client, { productCode: 'vbr', confirmationTimeoutMs: 5000, turnTimeoutMs: 5000 }, transport);
        await chat.initialize();

        const turn = chat.sendMessage('List the jobs');
        transport.fire({ type: 'connected', sessionId: 'session-1' });
        // `/api/v1/acl` is a whitelisted POST, so this runs without a confirmation.
        transport.fire({
            type: 'toolInvocation',
            payload: {
                invocation_id: 'inv-boom',
                tool_name: 'fetch_data_from_endpoint',
                parameters: { endpoint_path: '/api/v1/acl', query_params: {}, method: 'POST', body: '{}' },
            },
        });
        await new Promise((resolve) => setImmediate(resolve));
        transport.fire({ type: 'disconnected' });

        const outcome = await turn;

        expect(outcome.kind).toBe('complete');
        expect(logged()).toContain('inv-boom');
        expect(logged()).toContain('product REST client exploded');
        expect(transport.sent).toContainEqual({
            name: 'tool_result',
            value: {
                invocation_id: 'inv-boom',
                status: 'error',
                data: { message: expect.stringContaining('product REST client exploded') },
            },
        });
    });
});
