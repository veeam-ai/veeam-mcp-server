/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { v4 as uuidv4 } from 'uuid';

import { CommonInvokeConfig, ToolCallResult } from '@/common/types';
import type { ProductRestClient } from '@/product/ProductRestClient';
import { log } from '@/utils/logger';

import { ConfirmationBroker } from './ConfirmationBroker';
import { FetchGate } from './fetchGate';
import { ActionOutcome, ConfirmationRequest, HandledInvocation, USER_CANCELLED_ACTION_RESULT } from './types';

export class ActionExecutor {
    constructor(
        private readonly gate: FetchGate,
        private readonly productRestClient: ProductRestClient,
        private readonly confirmations: ConfirmationBroker,
        private readonly confirmationTimeoutMs: number,
    ) {}

    public async execute(config: CommonInvokeConfig): Promise<HandledInvocation> {
        const { method, endpoint_path: path } = config.parameters;
        const decision = this.gate.decide(method, path);

        switch (decision.kind) {
            case 'allowed': {
                const result = await this.productRestClient.getToolCallData(config);
                return { result: { status: result.status, data: result.data } };
            }
            case 'rejected': {
                log.warn(`action rejected by policy: ${decision.reason}`);
                return {
                    result: { status: 'error', data: { message: decision.reason } },
                    outcome: {
                        action_id: '',
                        title: `${method} ${path}`,
                        method,
                        path,
                        decision: 'rejected',
                        executed: false,
                        error: decision.reason,
                    },
                };
            }
            case 'confirm':
                return this.confirmAndRun(config, decision.title, decision.description);
        }
    }

    private async confirmAndRun(config: CommonInvokeConfig, title: string, description: string): Promise<HandledInvocation> {
        const { method, endpoint_path: path } = config.parameters;

        const request: ConfirmationRequest = {
            id: uuidv4(),
            invocationId: config.invocation_id,
            kind: 'action',
            title,
            description,
            method,
            path,
            createdAt: Date.now(),
            expiresAt: Date.now() + this.confirmationTimeoutMs,
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

        const decision = await this.confirmations.awaitDecision(request);
        const outcome: ActionOutcome = {
            action_id: request.id,
            title: request.title,
            method,
            path,
            decision,
            executed: false,
        };

        if (decision !== 'approved') {
            log.info(`action ${decision}: ${method} ${path}`);
            return { result: { status: 'error', data: USER_CANCELLED_ACTION_RESULT }, outcome };
        }

        const result = await this.productRestClient.getToolCallData(config);
        outcome.executed = result.status === 'success';

        const httpStatus = extractHttpStatus(result);
        if (httpStatus !== undefined) {
            outcome.http_status = httpStatus;
        }
        if (result.status !== 'success') {
            outcome.error = describeError(result);
        }

        log.info(`action ${decision}: ${method} ${path} → ${result.status}${httpStatus !== undefined ? ` (${httpStatus})` : ''}`);

        return { result: { status: result.status, data: result.data }, outcome };
    }
}

function extractHttpStatus(result: ToolCallResult): number | undefined {
    const data = result.data as { status?: unknown } | null;
    return typeof data?.status === 'number' ? data.status : undefined;
}

function describeError(result: ToolCallResult): string {
    const data = result.data as { status?: unknown; body?: unknown; message?: unknown } | null;
    if (typeof data?.message === 'string') {
        return data.message;
    }
    const body = typeof data?.body === 'string' ? data.body : JSON.stringify(data?.body ?? '');
    const status = typeof data?.status === 'number' ? String(data.status) : '?';
    return `HTTP ${status}: ${body}`;
}
