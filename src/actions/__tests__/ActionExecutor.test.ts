/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { describe, it, expect, jest, beforeEach, afterEach } from '@jest/globals';

import { ActionExecutor } from '../ActionExecutor';
import { ConfirmationBroker } from '../ConfirmationBroker';
import { FetchGate } from '../fetchGate';
import { InteractionHandler } from '../InteractionHandler';
import { FetchPolicyRegistry } from '../types';
import { CommonInvokeConfig, RequestUserInteractionConfig, ToolCallResult } from '@/common/types';
import type { ProductRestClient } from '@/product/ProductRestClient';

const registry: FetchPolicyRegistry = {
    whitelist: [{ method: 'POST', pathPattern: '/api/v1/acl', titleKey: '', descriptionKey: '' }],
    checklist: [{ method: 'POST', pathPattern: '/api/v1/jobs/:id/start', titleKey: 'start_title', descriptionKey: 'start_description' }],
};

const texts = { start_title: 'Start this backup job?', start_description: 'It will run now.' };

function fetchConfig(overrides: Partial<CommonInvokeConfig['parameters']> = {}): CommonInvokeConfig {
    return {
        invocation_id: 'inv-1',
        tool_name: 'fetch_data_from_endpoint',
        parameters: { endpoint_path: '/api/v1/jobs/abc/start', query_params: {}, method: 'POST', ...overrides },
    };
}

function createExecutor(result: ToolCallResult, timeoutMs = 60_000) {
    const getToolCallData = jest.fn(async (_config: CommonInvokeConfig) => result);
    const client = { getToolCallData } as unknown as ProductRestClient;
    const confirmations = new ConfirmationBroker(timeoutMs);
    const executor = new ActionExecutor(new FetchGate(registry, texts), client, confirmations, timeoutMs);
    return { executor, confirmations, getToolCallData };
}

const okResult: ToolCallResult = { status: 'success', data: { status: 201, body: { id: 's1' } } };
const flush = () => new Promise((resolve) => setImmediate(resolve));

describe('ActionExecutor', () => {
    let stderr: jest.SpiedFunction<typeof process.stderr.write>;

    beforeEach(() => {
        stderr = jest.spyOn(process.stderr, 'write').mockImplementation(() => true);
    });

    afterEach(() => {
        stderr.mockRestore();
    });

    it('runs a GET without asking and reports no action', async () => {
        const { executor, getToolCallData } = createExecutor({ status: 'success', data: { status: 200, body: [] } });

        const handled = await executor.execute(fetchConfig({ endpoint_path: '/api/v1/jobs', method: 'GET' }));

        expect(handled.outcome).toBeUndefined();
        expect(handled.result).toEqual({ status: 'success', data: { status: 200, body: [] } });
        expect(getToolCallData).toHaveBeenCalledTimes(1);
    });

    it('runs a whitelisted POST without asking', async () => {
        const { executor, getToolCallData } = createExecutor(okResult);

        const handled = await executor.execute(fetchConfig({ endpoint_path: '/api/v1/acl', body: '{}' }));

        expect(handled.outcome).toBeUndefined();
        expect(getToolCallData).toHaveBeenCalledTimes(1);
    });

    it('rejects a call the policy does not list, without calling the product', async () => {
        const { executor, getToolCallData } = createExecutor(okResult);

        const handled = await executor.execute(fetchConfig({ endpoint_path: '/api/v1/jobs/abc', method: 'DELETE' }));

        expect(handled.result.status).toBe('error');
        expect(handled.outcome).toEqual(
            expect.objectContaining({ decision: 'rejected', executed: false, method: 'DELETE', action_id: '' }),
        );
        expect(JSON.stringify(handled.result.data)).toContain('not allowed');
        expect(getToolCallData).not.toHaveBeenCalled();
    });

    it('builds the confirmation from the policy text plus the invocation details', async () => {
        const { executor, confirmations } = createExecutor(okResult);

        const running = executor.execute(fetchConfig({ body: '{"performActiveFull":false}', description: 'Start Nightly SQL' }));
        const pending = await confirmations.awaitNextRequest(new Promise<void>(() => {}));
        if (pending === 'complete') throw new Error('expected a confirmation');

        expect(pending.title).toBe('Start this backup job?');
        expect(pending.description).toBe('It will run now.');
        expect(pending.dynamicDescription).toBe('Start Nightly SQL');
        expect(pending.body).toBe('{"performActiveFull":false}');
        expect(pending.method).toBe('POST');
        expect(pending.kind).toBe('action');

        confirmations.answer(pending.id, true);
        await running;
    });

    it('omits empty query params and an empty body from the confirmation', async () => {
        const { executor, confirmations } = createExecutor(okResult);

        const running = executor.execute(fetchConfig({ query_params: {}, body: '' }));
        const pending = await confirmations.awaitNextRequest(new Promise<void>(() => {}));
        if (pending === 'complete') throw new Error('expected a confirmation');

        expect(pending.queryParams).toBeUndefined();
        expect(pending.body).toBeUndefined();

        confirmations.answer(pending.id, true);
        await running;
    });

    it('executes after approval and records the http status', async () => {
        const { executor, confirmations, getToolCallData } = createExecutor(okResult);

        const running = executor.execute(fetchConfig());
        const pending = await confirmations.awaitNextRequest(new Promise<void>(() => {}));
        if (pending === 'complete') throw new Error('expected a confirmation');
        expect(getToolCallData).not.toHaveBeenCalled();

        confirmations.answer(pending.id, true);
        const handled = await running;

        expect(handled.outcome).toEqual(
            expect.objectContaining({ decision: 'approved', executed: true, http_status: 201, action_id: pending.id }),
        );
        expect(getToolCallData).toHaveBeenCalledTimes(1);
    });

    it('does not call the product when the user declines, and answers user_cancelled_action', async () => {
        const { executor, confirmations, getToolCallData } = createExecutor(okResult);

        const running = executor.execute(fetchConfig());
        const pending = await confirmations.awaitNextRequest(new Promise<void>(() => {}));
        if (pending === 'complete') throw new Error('expected a confirmation');

        confirmations.answer(pending.id, false);
        const handled = await running;

        expect(handled.outcome).toEqual(expect.objectContaining({ decision: 'declined', executed: false }));
        expect(handled.result).toEqual({ status: 'error', data: { code: 'user_cancelled_action' } });
        expect(getToolCallData).not.toHaveBeenCalled();
    });

    it('treats an unanswered confirmation as expired and does not execute', async () => {
        const { executor, getToolCallData } = createExecutor(okResult, 20);

        const handled = await executor.execute(fetchConfig());

        expect(handled.outcome).toEqual(expect.objectContaining({ decision: 'expired', executed: false }));
        expect(handled.result.data).toEqual({ code: 'user_cancelled_action' });
        expect(getToolCallData).not.toHaveBeenCalled();
    });

    it('records the upstream failure when an approved action fails', async () => {
        const failure: ToolCallResult = { status: 'error', data: { status: 409, body: 'job already running' } };
        const { executor, confirmations } = createExecutor(failure);

        const running = executor.execute(fetchConfig());
        const pending = await confirmations.awaitNextRequest(new Promise<void>(() => {}));
        if (pending === 'complete') throw new Error('expected a confirmation');

        confirmations.answer(pending.id, true);
        const handled = await running;

        expect(handled.outcome).toEqual(
            expect.objectContaining({ decision: 'approved', executed: false, http_status: 409, error: 'HTTP 409: job already running' }),
        );
    });

    it('prefers an explicit message when describing a failure', async () => {
        const failure: ToolCallResult = { status: 'error', data: { message: 'Failed to call POST /x: socket hang up' } };
        const { executor, confirmations } = createExecutor(failure);

        const running = executor.execute(fetchConfig());
        const pending = await confirmations.awaitNextRequest(new Promise<void>(() => {}));
        if (pending === 'complete') throw new Error('expected a confirmation');

        confirmations.answer(pending.id, true);
        const handled = await running;

        expect(handled.outcome?.error).toBe('Failed to call POST /x: socket hang up');
        expect(handled.outcome?.http_status).toBeUndefined();
    });

    it('rejects every non-GET call when the product has no policy', async () => {
        const getToolCallData = jest.fn(async (_config: CommonInvokeConfig) => okResult);
        const client = { getToolCallData } as unknown as ProductRestClient;
        const confirmations = new ConfirmationBroker(60_000);
        const executor = new ActionExecutor(new FetchGate(undefined), client, confirmations, 60_000);

        const handled = await executor.execute(fetchConfig());

        expect(handled.outcome).toEqual(expect.objectContaining({ decision: 'rejected' }));
        expect(getToolCallData).not.toHaveBeenCalled();
    });
});

describe('InteractionHandler', () => {
    let stderr: jest.SpiedFunction<typeof process.stderr.write>;

    beforeEach(() => {
        stderr = jest.spyOn(process.stderr, 'write').mockImplementation(() => true);
    });

    afterEach(() => {
        stderr.mockRestore();
    });

    function interactionConfig(parameters: RequestUserInteractionConfig['parameters']): RequestUserInteractionConfig {
        return { invocation_id: 'inv-q', tool_name: 'request_user_interaction', parameters };
    }

    it('relays a confirmation and answers with the resolved value', async () => {
        const confirmations = new ConfirmationBroker(60_000);
        const handler = new InteractionHandler(confirmations, 60_000);

        const running = handler.handle(interactionConfig({ kind: 'confirmation', title: 'Proceed?', description: 'Removes points.' }));
        const pending = await confirmations.awaitNextRequest(new Promise<void>(() => {}));
        if (pending === 'complete') throw new Error('expected a confirmation');

        expect(pending.kind).toBe('interaction');
        expect(pending.title).toBe('Proceed?');

        confirmations.answer(pending.id, true);
        const handled = await running;

        expect(handled.result).toEqual({ status: 'success', data: { status: 'resolved', value: true } });
        expect(handled.outcome).toEqual(expect.objectContaining({ decision: 'approved', executed: false }));
    });

    it('reports value false when the user declines', async () => {
        const confirmations = new ConfirmationBroker(60_000);
        const handler = new InteractionHandler(confirmations, 60_000);

        const running = handler.handle(interactionConfig({ kind: 'confirmation', title: 'Proceed?' }));
        const pending = await confirmations.awaitNextRequest(new Promise<void>(() => {}));
        if (pending === 'complete') throw new Error('expected a confirmation');

        confirmations.answer(pending.id, false);

        expect((await running).result).toEqual({ status: 'success', data: { status: 'resolved', value: false } });
    });

    it('answers cancelled when the confirmation expires', async () => {
        const confirmations = new ConfirmationBroker(20);
        const handler = new InteractionHandler(confirmations, 20);

        const handled = await handler.handle(interactionConfig({ kind: 'confirmation', title: 'Proceed?' }));

        expect(handled.result).toEqual({ status: 'success', data: { status: 'cancelled' } });
        expect(handled.outcome).toEqual(expect.objectContaining({ decision: 'expired' }));
    });

    it('falls back to the label, then to a generic title', async () => {
        const confirmations = new ConfirmationBroker(60_000);
        const handler = new InteractionHandler(confirmations, 60_000);

        void handler.handle(interactionConfig({ kind: 'confirmation', label: 'From the label' }));
        const labelled = await confirmations.awaitNextRequest(new Promise<void>(() => {}));
        if (labelled === 'complete') throw new Error('expected a confirmation');
        expect(labelled.title).toBe('From the label');
        confirmations.answer(labelled.id, true);
        await flush();

        void handler.handle(interactionConfig({ kind: 'confirmation' }));
        const generic = await confirmations.awaitNextRequest(new Promise<void>(() => {}));
        if (generic === 'complete') throw new Error('expected a confirmation');
        expect(generic.title).toBe('Veeam Intelligence asks for confirmation');
        expect(generic.description).toBe('');
        confirmations.answer(generic.id, true);
    });

    it.each(['singleSelect', 'multiSelect', 'treeSelect'] as const)('answers cancelled for the unsupported %s kind', async (kind) => {
        const confirmations = new ConfirmationBroker(60_000);
        const handler = new InteractionHandler(confirmations, 60_000);

        const handled = await handler.handle(interactionConfig({ kind, options: ['a', 'b'] }));

        expect(handled.result).toEqual({ status: 'success', data: { status: 'cancelled' } });
        expect(handled.outcome).toBeUndefined();
        expect(confirmations.hasUndecided()).toBe(false);
    });
});
