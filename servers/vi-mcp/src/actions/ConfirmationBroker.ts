/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { Deferred } from '@/utils';
import { ConfirmationDecision, ConfirmationRequest } from './types';

interface UndecidedConfirmation {
    request: ConfirmationRequest;
    decision: Deferred<ConfirmationDecision>;
}

export class ConfirmationBroker {
    private readonly undecided = new Map<string, UndecidedConfirmation>();
    private undelivered: ConfirmationRequest[] = [];
    private waitingReceiver: Deferred<ConfirmationRequest> | null = null;

    constructor(private readonly decisionTimeoutMs: number) {}

    public async awaitDecision(request: ConfirmationRequest): Promise<ConfirmationDecision> {
        const confirmation: UndecidedConfirmation = { request, decision: new Deferred<ConfirmationDecision>() };
        this.undecided.set(request.id, confirmation);

        const receiver = this.waitingReceiver;
        if (receiver !== null) {
            this.waitingReceiver = null;
            receiver.resolve(request);
        } else {
            this.undelivered.push(request);
        }

        const timer = setTimeout(() => confirmation.decision.resolve('expired'), this.decisionTimeoutMs);
        const decision = await confirmation.decision.promise;
        clearTimeout(timer);

        this.undecided.delete(request.id);

        return decision;
    }

    public async awaitNextRequest(turnComplete: Promise<void>): Promise<ConfirmationRequest | 'complete'> {
        for (let candidate = this.undelivered.shift(); candidate !== undefined; candidate = this.undelivered.shift()) {
            if (this.undecided.has(candidate.id)) {
                return candidate;
            }
        }

        const receiver = new Deferred<ConfirmationRequest>();
        this.waitingReceiver = receiver;

        const result = await Promise.race([turnComplete.then(() => 'complete' as const), receiver.promise]);
        this.waitingReceiver = null;

        return result;
    }

    public answer(id: string, approve: boolean): boolean {
        const confirmation = this.undecided.get(id);
        if (confirmation === undefined) {
            return false;
        }

        confirmation.decision.resolve(approve ? 'approved' : 'declined');
        return true;
    }

    public whenDecided(id: string): Promise<ConfirmationDecision> {
        const confirmation = this.undecided.get(id);
        return confirmation === undefined ? Promise.resolve('expired') : confirmation.decision.promise;
    }

    public hasUndecided(): boolean {
        return this.undecided.size > 0;
    }

    public expireAll(): void {
        for (const confirmation of this.undecided.values()) {
            confirmation.decision.resolve('expired');
        }
    }

    public dropUndelivered(): void {
        this.undelivered = [];
    }
}
