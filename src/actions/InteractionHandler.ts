/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { v4 as uuidv4 } from 'uuid';

import { RequestUserInteractionConfig } from '@/common/types';
import { log } from '@/utils/logger';

import { ConfirmationBroker } from './ConfirmationBroker';
import { ConfirmationRequest, HandledInvocation } from './types';

export class InteractionHandler {
    constructor(
        private readonly confirmations: ConfirmationBroker,
        private readonly confirmationTimeoutMs: number,
    ) {}

    public async handle(config: RequestUserInteractionConfig): Promise<HandledInvocation> {
        const { kind, title, label, description } = config.parameters;

        if (kind !== 'confirmation') {
            log.warn(`user interaction of kind "${kind}" is not supported by the MCP server; answering "cancelled"`);
            return { result: { status: 'success', data: { status: 'cancelled' } } };
        }

        const request: ConfirmationRequest = {
            id: uuidv4(),
            invocationId: config.invocation_id,
            kind: 'interaction',
            title: title ?? label ?? 'Veeam Intelligence asks for confirmation',
            description: description ?? '',
            createdAt: Date.now(),
            expiresAt: Date.now() + this.confirmationTimeoutMs,
        };

        const decision = await this.confirmations.awaitDecision(request);
        const outcome = { action_id: request.id, title: request.title, decision, executed: false };

        if (decision === 'expired') {
            return { result: { status: 'success', data: { status: 'cancelled' } }, outcome };
        }

        return { result: { status: 'success', data: { status: 'resolved', value: decision === 'approved' } }, outcome };
    }
}
