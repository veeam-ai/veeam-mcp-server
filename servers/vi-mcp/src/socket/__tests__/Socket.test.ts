/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { describe, it, expect, beforeAll, beforeEach, afterEach, jest } from '@jest/globals';

import { ChatbotMode, ServiceInfo, SocketConfig } from '@/common/types';
import { ConnectionErrorCode, TransportInboundEvent } from '../types';

/** Captures what `Socket` asked socket.io for, and lets the test play the server's side. */
class FakeIoSocket {
    public auth: Record<string, unknown> = {};
    public active = false;
    public connectCalls = 0;
    public disconnectCalls = 0;
    public readonly emitted: { name: string; value: unknown }[] = [];

    private readonly handlers = new Map<string, (arg?: any) => void>();
    private readonly managerHandlers = new Map<string, (arg?: any) => void>();

    public readonly io = {
        on: (event: string, handler: (arg?: any) => void) => {
            this.managerHandlers.set(event, handler);
        },
    };

    public on(event: string, handler: (arg?: any) => void): void {
        this.handlers.set(event, handler);
    }

    public connect(): void {
        this.connectCalls += 1;
    }

    public disconnect(): void {
        this.disconnectCalls += 1;
    }

    public emit(name: string, value: unknown): void {
        this.emitted.push({ name, value });
    }

    /** Delivers a server-side event to the listener `Socket` registered. */
    public fire(event: string, arg?: unknown): void {
        const handler = this.handlers.get(event) ?? this.managerHandlers.get(event);
        if (handler === undefined) {
            throw new Error(`Socket registered no listener for "${event}"`);
        }
        handler(arg);
    }
}

const ioCalls: { uri: string; opts: any }[] = [];
let nextSocket: FakeIoSocket;

jest.unstable_mockModule('socket.io-client', () => ({
    io: (uri: string, opts: any) => {
        ioCalls.push({ uri, opts });
        // The real client exposes the handshake auth as `socket.auth`; setAuthToken merges into it.
        nextSocket.auth = { ...opts.auth };
        return nextSocket;
    },
}));

type SocketModule = typeof import('../Socket');
let SocketClass: SocketModule['Socket'];

beforeAll(async () => {
    SocketClass = (await import('../Socket')).Socket;
});

const serviceInfo: ServiceInfo = {
    chatbotApiUrl: 'https://vbr.local/',
    chatbotEnabled: true,
    chatbotMode: ChatbotMode.Base,
    productName: 'Veeam Backup and Replication',
    productVersion: '13.1.0.411',
};

function setup(info: Partial<ServiceInfo> = {}, config: SocketConfig = {}) {
    const socket = new SocketClass();
    const received: TransportInboundEvent[] = [];
    socket.events.subscribe((event) => received.push(event));
    socket.initialize({ ...serviceInfo, ...info }, config);

    return { socket, received, wire: nextSocket, handshake: ioCalls[ioCalls.length - 1] };
}

/** Brings the connection to the state where inbound events are accepted. */
function connected(...args: Parameters<typeof setup>) {
    const ctx = setup(...args);
    ctx.wire.fire('connect');
    ctx.received.length = 0;

    return ctx;
}

describe('Socket handshake', () => {
    beforeEach(() => {
        ioCalls.length = 0;
        nextSocket = new FakeIoSocket();
        process.env.PRODUCT_NAME = 'vbr';
    });

    it('requires PRODUCT_NAME, since it selects the server-side chat namespace', () => {
        delete process.env.PRODUCT_NAME;

        expect(() => new SocketClass().initialize(serviceInfo, {})).toThrow(/PRODUCT_NAME environment variable is required/);
    });

    it('connects to the API origin and appends the product to the socket.io path', () => {
        const { handshake } = setup();

        expect(handshake.uri).toBe('https://vbr.local');
        expect(handshake.opts.path).toBe('/vbr/socket.io');
        expect(handshake.opts.autoConnect).toBe(false);
    });

    it('keeps a base path from the API url ahead of the socket.io path', () => {
        const { handshake } = setup({ chatbotApiUrl: 'https://host.local/api/chat/' });

        expect(handshake.uri).toBe('https://host.local');
        expect(handshake.opts.path).toBe('/api/chat/vbr/socket.io');
    });

    it('honours an explicit socket path override', () => {
        const { handshake } = setup({}, { socketPath: '/ws' });

        expect(handshake.opts.path).toBe('/vbr/ws');
    });

    it('sends the chat id, mode and inverted timezone offset in the handshake auth', () => {
        const { handshake } = setup();

        expect(handshake.opts.auth).toMatchObject({
            token: null,
            mode: ChatbotMode.Base,
            chat_id: expect.stringMatching(/^[0-9a-f-]{36}$/),
            timezone_offset: new Date().getTimezoneOffset() * -1,
        });
        expect(handshake.opts.auth).not.toHaveProperty('user_role');
    });

    it('includes the user role only when the product reports one', () => {
        const { handshake } = setup({ userRole: 'Administrator' });

        expect(handshake.opts.auth.user_role).toBe('Administrator');
    });

    it('lets the caller override the mode the product advertised', () => {
        const { handshake } = setup({ chatbotMode: ChatbotMode.Base }, { mode: ChatbotMode.Advanced });

        expect(handshake.opts.auth.mode).toBe(ChatbotMode.Advanced);
    });

    it('is idempotent: a second initialize does not build a second socket', () => {
        const { socket } = setup();
        socket.initialize(serviceInfo, {});

        expect(ioCalls).toHaveLength(1);
    });

    it('refuses to be used before initialization', () => {
        const socket = new SocketClass();

        expect(() => socket.connect()).toThrow(/wasn't initialized/);
        expect(() => socket.disconnect()).toThrow(/wasn't initialized/);
    });

    it('merges the auth token into the handshake without dropping the rest', () => {
        const { socket, wire } = setup();

        socket.setAuthToken('jwt-token');

        expect(wire.auth).toMatchObject({ token: 'jwt-token', mode: ChatbotMode.Base });
        expect(wire.auth.chat_id).toBe(ioCalls[0].opts.auth.chat_id);
    });

    it('forwards connect, disconnect and emit to the underlying socket', () => {
        const { socket, wire } = setup();

        socket.connect();
        socket.emit({ name: 'tool_result', value: { invocation_id: 'inv-1' } });
        socket.disconnect();

        expect(wire.connectCalls).toBe(1);
        expect(wire.disconnectCalls).toBe(1);
        expect(wire.emitted).toEqual([{ name: 'tool_result', value: { invocation_id: 'inv-1' } }]);
    });
});

describe('Socket session lifecycle', () => {
    beforeEach(() => {
        ioCalls.length = 0;
        nextSocket = new FakeIoSocket();
        process.env.PRODUCT_NAME = 'vbr';
    });

    it('opens a session on the first connect', () => {
        const { received } = setup();
        nextSocket.fire('connect');

        expect(received).toEqual([{ type: 'connected', sessionId: expect.stringMatching(/^[0-9a-f-]{36}$/) }]);
    });

    it('drops a reconnect onto an open session rather than resuming a stale turn', () => {
        const { received, wire } = connected();

        wire.fire('connect');

        expect(wire.disconnectCalls).toBe(1);
        expect(received).toEqual([]);
    });

    it('closes the session on disconnect and allows a later one to open', () => {
        const { received, wire } = connected();

        wire.fire('disconnect');
        expect(received).toEqual([{ type: 'disconnected' }]);

        wire.fire('connect');
        expect(received[1]).toMatchObject({ type: 'connected' });
    });

    it('ignores inbound traffic that arrives while no session is open', () => {
        const { received, wire } = setup();

        wire.fire('response_chunk', { type: 'token', payload: 'hello' });
        wire.fire('tool_invocation', {
            invocation_id: 'inv-1',
            tool_name: 'fetch_data_from_endpoint',
            parameters: { endpoint_path: '/x' },
        });
        wire.fire('response_error', { details: 'boom' });

        expect(received).toEqual([]);
    });

    it('reports manager-level reconnect failures', () => {
        const { received, wire } = connected();

        wire.fire('reconnect_error');
        wire.fire('reconnect_failed');

        expect(received).toEqual([{ type: 'reconnectError' }, { type: 'reconnectFailed' }]);
    });

    it('surfaces a response error from the server', () => {
        const { received, wire } = connected();

        wire.fire('response_error', { details: 'model unavailable' });

        expect(received).toEqual([{ type: 'responseError', details: 'model unavailable' }]);
    });
});

describe('Socket inbound validation', () => {
    let stderr: jest.SpiedFunction<typeof process.stderr.write>;

    beforeEach(() => {
        ioCalls.length = 0;
        nextSocket = new FakeIoSocket();
        process.env.PRODUCT_NAME = 'vbr';
        stderr = jest.spyOn(process.stderr, 'write').mockImplementation(() => true);
    });

    afterEach(() => {
        stderr.mockRestore();
    });

    const logged = () => stderr.mock.calls.map((call) => String(call[0])).join('');

    it('passes a valid chunk through in parsed form', () => {
        const { received, wire } = connected();

        wire.fire('response_chunk', { type: 'token', payload: 'hello' });

        expect(received).toEqual([{ type: 'chunk', payload: { type: 'token', payload: 'hello' } }]);
    });

    it('drops a malformed chunk instead of letting it reach the answer', () => {
        const { received, wire } = connected();

        wire.fire('response_chunk', { type: 'token', payload: 42 });

        expect(received).toEqual([]);
        expect(logged()).toContain('discarding malformed Veeam Intelligence response chunk');
    });

    it('ignores an undefined chunk', () => {
        const { received, wire } = connected();

        wire.fire('response_chunk', undefined);

        expect(received).toEqual([]);
    });

    it('applies wire defaults to a valid tool invocation', () => {
        const { received, wire } = connected();

        wire.fire('tool_invocation', {
            invocation_id: 'inv-1',
            tool_name: 'fetch_data_from_endpoint',
            parameters: { endpoint_path: '/api/v1/jobs' },
        });

        expect(received).toEqual([
            {
                type: 'toolInvocation',
                payload: expect.objectContaining({
                    invocation_id: 'inv-1',
                    parameters: expect.objectContaining({ endpoint_path: '/api/v1/jobs', method: 'GET', query_params: {} }),
                }),
            },
        ]);
    });

    it('reports an invalid invocation that still carries an id, so it can be answered with an error', () => {
        const { received, wire } = connected();

        wire.fire('tool_invocation', { invocation_id: 'inv-1', tool_name: 'fetch_data_from_endpoint', parameters: {} });

        expect(received).toEqual([{ type: 'toolInvocationInvalid', invocationId: 'inv-1', reason: expect.any(String) }]);
    });

    it('discards an invocation with no id, since there is nothing to answer', () => {
        const { received, wire } = connected();

        wire.fire('tool_invocation', { tool_name: 'fetch_data_from_endpoint' });

        expect(received).toEqual([]);
        expect(logged()).toContain('discarding unidentifiable Veeam Intelligence tool invocation');
    });
});

describe('Socket connect errors', () => {
    beforeEach(() => {
        ioCalls.length = 0;
        nextSocket = new FakeIoSocket();
        process.env.PRODUCT_NAME = 'vbr';
    });

    it('stays quiet while socket.io is still retrying', () => {
        const { received, wire } = setup();
        wire.active = true;

        wire.fire('connect_error', new Error('xhr poll error'));

        expect(received).toEqual([]);
    });

    it('maps a Veeam Intelligence error envelope to its code', () => {
        const { received, wire } = setup();

        wire.fire('connect_error', new Error(JSON.stringify({ code: 'TOKEN_INVALID', details: 'token expired' })));

        expect(received).toEqual([{ type: 'connectError', error: { code: ConnectionErrorCode.TokenInvalid, details: 'token expired' } }]);
    });

    it('reports an unrecognised envelope code as Unknown rather than passing it through', () => {
        const { received, wire } = setup();

        wire.fire('connect_error', new Error(JSON.stringify({ code: 'SOMETHING_NEW', details: 'huh' })));

        expect(received).toEqual([{ type: 'connectError', error: { code: ConnectionErrorCode.Unknown, details: 'huh' } }]);
    });

    it('reports a non-JSON transport failure as Unknown with the raw message', () => {
        const { received, wire } = setup();

        wire.fire('connect_error', new Error('xhr poll error'));

        expect(received).toEqual([{ type: 'connectError', error: { code: ConnectionErrorCode.Unknown, details: 'xhr poll error' } }]);
    });

    it('reports a JSON payload that is not an error envelope as Unknown', () => {
        const { received, wire } = setup();

        wire.fire('connect_error', new Error(JSON.stringify({ code: 500 })));

        expect(received[0]).toMatchObject({ type: 'connectError', error: { code: ConnectionErrorCode.Unknown } });
    });
});
