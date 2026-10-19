/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { describe, it, expect } from '@jest/globals';

import { describeParseError, invocationIdSchema, responseChunkSchema, toolInvocationSchema } from '../schemas';

describe('toolInvocationSchema', () => {
    it('defaults an omitted method to GET (a read omits it on the wire)', () => {
        const parsed = toolInvocationSchema.parse({
            invocation_id: 'inv-get',
            tool_name: 'fetch_data_from_endpoint',
            parameters: { endpoint_path: '/api/v1/jobs', query_params: { limit: 5 } },
        });

        expect(parsed.tool_name).toBe('fetch_data_from_endpoint');
        if (parsed.tool_name !== 'fetch_data_from_endpoint') throw new Error('unreachable');
        expect(parsed.parameters.method).toBe('GET');
    });

    it('keeps an explicit method and the action fields', () => {
        const parsed = toolInvocationSchema.parse({
            invocation_id: 'inv-1',
            tool_name: 'fetch_data_from_endpoint',
            parameters: {
                endpoint_path: '/api/v1/jobs/abc/start',
                query_params: {},
                method: 'POST',
                body: '{"performActiveFull":false}',
                headers: { 'Content-Type': 'application/json' },
                description: 'Start the job',
            },
        });

        if (parsed.tool_name !== 'fetch_data_from_endpoint') throw new Error('unreachable');
        expect(parsed.parameters.method).toBe('POST');
        expect(parsed.parameters.body).toBe('{"performActiveFull":false}');
        expect(parsed.parameters.description).toBe('Start the job');
    });

    // Forward compatibility for a frame the server acts on: a field Veeam Intelligence adds must
    // never fail the connection. It is dropped rather than carried, so the inferred type stays
    // exact for the gate and the REST client; an unmodelled field nothing reads is not content.
    it('accepts, and drops, fields the MCP server does not model yet', () => {
        const parsed = toolInvocationSchema.parse({
            invocation_id: 'inv-1',
            tool_name: 'fetch_data_from_endpoint',
            parameters: { endpoint_path: '/api/v1/jobs', query_params: {}, future_field: 'keep me' },
            another_future_field: 42,
        });

        expect(parsed).not.toHaveProperty('another_future_field');
        expect(parsed.parameters).not.toHaveProperty('future_field');
        expect(parsed.parameters.endpoint_path).toBe('/api/v1/jobs');
    });

    it('rejects an unsupported HTTP method rather than passing it to the gate', () => {
        const result = toolInvocationSchema.safeParse({
            invocation_id: 'inv-1',
            tool_name: 'fetch_data_from_endpoint',
            parameters: { endpoint_path: '/api/v1/jobs', query_params: {}, method: 'TRACE' },
        });

        expect(result.success).toBe(false);
    });

    it.each([
        ['a missing endpoint_path', { invocation_id: 'i', tool_name: 'fetch_data_from_endpoint', parameters: { query_params: {} } }],
        ['an empty endpoint_path', { invocation_id: 'i', tool_name: 'fetch_data_from_endpoint', parameters: { endpoint_path: '' } }],
        ['an unknown tool name', { invocation_id: 'i', tool_name: 'rm_minus_rf', parameters: {} }],
        ['a missing invocation_id', { tool_name: 'fetch_data_from_endpoint', parameters: { endpoint_path: '/api/v1/jobs' } }],
        ['a non-object payload', 'not an object'],
    ])('rejects %s', (_label, payload) => {
        expect(toolInvocationSchema.safeParse(payload).success).toBe(false);
    });

    it('accepts a user interaction request', () => {
        const parsed = toolInvocationSchema.parse({
            invocation_id: 'inv-q',
            tool_name: 'request_user_interaction',
            parameters: { kind: 'confirmation', title: 'Proceed?', description: 'Removes restore points.' },
        });

        if (parsed.tool_name !== 'request_user_interaction') throw new Error('unreachable');
        expect(parsed.parameters.kind).toBe('confirmation');
    });
});

describe('invocationIdSchema', () => {
    it('recovers the id from a payload that failed full validation, so it can be answered', () => {
        const result = invocationIdSchema.safeParse({ invocation_id: 'inv-bad', tool_name: 'fetch_data_from_endpoint' });

        expect(result.success).toBe(true);
        expect(result.success && result.data.invocation_id).toBe('inv-bad');
    });
});

describe('responseChunkSchema', () => {
    it('accepts token and both artifact shapes', () => {
        expect(responseChunkSchema.safeParse({ type: 'token', payload: 'hello' }).success).toBe(true);
        expect(responseChunkSchema.safeParse({ type: 'artifact', payload: { id: 'a1', type: 'string', data: 'x' } }).success).toBe(true);
        expect(
            responseChunkSchema.safeParse({
                type: 'artifact',
                payload: { id: 'a2', type: 'dataframe', data: { columns: ['a'], index: [0], data: [[1]] } },
            }).success,
        ).toBe(true);
    });

    // Veeam Intelligence already emits these two kinds (ArtifactType in ai-core); the MCP server
    // forwards artifacts verbatim, so validating the kind would silently drop real content.
    it.each(['chart', 'hero-metric', 'some-future-kind'])('forwards the unmodelled %s artifact kind', (type) => {
        const result = responseChunkSchema.safeParse({ type: 'artifact', payload: { id: 'a1', type, data: { anything: true } } });

        expect(result.success).toBe(true);
        expect(result.success && result.data.type === 'artifact' && result.data.payload.data).toEqual({ anything: true });
    });

    // Unlike a tool invocation, an artifact is forwarded to the MCP client untouched, so a field
    // the MCP server does not model yet has to survive parsing or the client silently loses it.
    it('preserves unmodelled fields on an artifact, which is forwarded verbatim', () => {
        const parsed = responseChunkSchema.parse({
            type: 'artifact',
            payload: { id: 'a1', type: 'chart', data: { series: [1] }, title: 'Job durations' },
        });

        expect(parsed.type === 'artifact' && parsed.payload).toMatchObject({ title: 'Job durations' });
    });

    it.each([
        ['a non-string token payload', { type: 'token', payload: { nested: true } }],
        ['an unknown chunk type', { type: 'thinking', payload: 'x' }],
        ['an artifact with no id', { type: 'artifact', payload: { type: 'string', data: 'x' } }],
        ['an artifact with no type', { type: 'artifact', payload: { id: 'a1', data: 'x' } }],
        ['a non-object artifact payload', { type: 'artifact', payload: 'nope' }],
    ])('rejects %s', (_label, payload) => {
        expect(responseChunkSchema.safeParse(payload).success).toBe(false);
    });
});

describe('describeParseError', () => {
    it('names the offending field', () => {
        const result = toolInvocationSchema.safeParse({
            invocation_id: 'i',
            tool_name: 'fetch_data_from_endpoint',
            parameters: { endpoint_path: '/api/v1/jobs', query_params: {}, method: 'TRACE' },
        });

        expect(result.success).toBe(false);
        if (result.success) throw new Error('unreachable');
        expect(describeParseError(result.error)).toContain('parameters.method');
    });
});
