/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { describe, it, expect } from '@jest/globals';

import { ConfirmationBroker } from '../ConfirmationBroker';
import { ConfirmationRequest } from '../types';

function makeRequest(id: string): ConfirmationRequest {
    return {
        id,
        invocationId: `inv-${id}`,
        kind: 'action',
        title: `Confirm ${id}?`,
        description: 'risk',
        createdAt: Date.now(),
        expiresAt: Date.now() + 60_000,
    };
}

/** Lets pending microtasks run so a `request()` in flight reaches the waiter. */
const flush = () => new Promise((resolve) => setImmediate(resolve));

const never = new Promise<void>(() => {});

describe('ConfirmationBroker', () => {
    it('hands a request straight to a receiver that is already waiting', async () => {
        const broker = new ConfirmationBroker(60_000);

        const next = broker.awaitNextRequest(never);
        await flush();

        const decided = broker.awaitDecision(makeRequest('a'));
        const winner = await next;

        expect(winner).not.toBe('complete');
        expect(winner === 'complete' ? '' : winner.id).toBe('a');

        expect(broker.answer('a', true)).toBe(true);
        await expect(decided).resolves.toBe('approved');
    });

    it('holds a request as undelivered when no receiver is waiting yet', async () => {
        const broker = new ConfirmationBroker(60_000);

        const decided = broker.awaitDecision(makeRequest('a'));
        await flush();

        const winner = await broker.awaitNextRequest(never);

        expect(winner === 'complete' ? '' : winner.id).toBe('a');
        broker.answer('a', false);
        await expect(decided).resolves.toBe('declined');
    });

    it('delivers an undelivered confirmation even when the turn has already completed', async () => {
        const broker = new ConfirmationBroker(60_000);

        const decided = broker.awaitDecision(makeRequest('a'));
        await flush();

        // Completion is already settled, but the queued confirmation must still win.
        const winner = await broker.awaitNextRequest(Promise.resolve());

        expect(winner === 'complete' ? '' : winner.id).toBe('a');
        broker.answer('a', true);
        await expect(decided).resolves.toBe('approved');
    });

    it('delivers two concurrent requests one at a time, in arrival order', async () => {
        const broker = new ConfirmationBroker(60_000);

        const first = broker.awaitDecision(makeRequest('a'));
        const second = broker.awaitDecision(makeRequest('b'));
        await flush();

        const firstWinner = await broker.awaitNextRequest(never);
        expect(firstWinner === 'complete' ? '' : firstWinner.id).toBe('a');

        const secondWinner = await broker.awaitNextRequest(never);
        expect(secondWinner === 'complete' ? '' : secondWinner.id).toBe('b');

        broker.answer('b', true);
        broker.answer('a', false);

        await expect(first).resolves.toBe('declined');
        await expect(second).resolves.toBe('approved');
    });

    it("reports 'complete' when the turn finishes and nothing is undecided", async () => {
        const broker = new ConfirmationBroker(60_000);

        await expect(broker.awaitNextRequest(Promise.resolve())).resolves.toBe('complete');
    });

    it('holds a request that arrives after completion won the race', async () => {
        const broker = new ConfirmationBroker(60_000);

        await expect(broker.awaitNextRequest(Promise.resolve())).resolves.toBe('complete');

        const decided = broker.awaitDecision(makeRequest('late'));
        await flush();

        const winner = await broker.awaitNextRequest(never);
        expect(winner === 'complete' ? '' : winner.id).toBe('late');

        broker.answer('late', true);
        await expect(decided).resolves.toBe('approved');
    });

    it('expires a request that is never answered', async () => {
        const broker = new ConfirmationBroker(20);

        const decided = broker.awaitDecision(makeRequest('a'));
        await flush();
        expect(broker.hasUndecided()).toBe(true);

        await expect(decided).resolves.toBe('expired');
        expect(broker.hasUndecided()).toBe(false);
        expect(broker.answer('a', true)).toBe(false);
    });

    it('expires everything outstanding when the connection drops', async () => {
        const broker = new ConfirmationBroker(60_000);

        const first = broker.awaitDecision(makeRequest('a'));
        const second = broker.awaitDecision(makeRequest('b'));
        await flush();

        broker.expireAll();

        await expect(first).resolves.toBe('expired');
        await expect(second).resolves.toBe('expired');
        expect(broker.hasUndecided()).toBe(false);
    });

    it('reports an unknown id as expired rather than hanging', async () => {
        const broker = new ConfirmationBroker(60_000);

        await expect(broker.whenDecided('nope')).resolves.toBe('expired');
        expect(broker.answer('nope', true)).toBe(false);
    });

    it('lets a caller observe the decision through whenDecided', async () => {
        const broker = new ConfirmationBroker(60_000);

        const decided = broker.awaitDecision(makeRequest('a'));
        await flush();

        const observed = broker.whenDecided('a');
        broker.answer('a', true);

        await expect(observed).resolves.toBe('approved');
        await expect(decided).resolves.toBe('approved');
    });

    it('drops what the previous turn left undelivered', async () => {
        const broker = new ConfirmationBroker(60_000);

        const decided = broker.awaitDecision(makeRequest('stale'));
        await flush();

        broker.dropUndelivered();

        // The queue is empty, so a fresh waiter sees completion rather than the stale request.
        await expect(broker.awaitNextRequest(Promise.resolve())).resolves.toBe('complete');

        // The producer is still blocked and is released by the disconnect, not by the new turn.
        broker.expireAll();
        await expect(decided).resolves.toBe('expired');
    });

    it('does not deliver an undelivered request that expired before anyone asked for it', async () => {
        const broker = new ConfirmationBroker(60_000);

        const blocked = broker.awaitDecision(makeRequest('stale'));
        await flush();
        broker.expireAll();
        await expect(blocked).resolves.toBe('expired');

        await expect(broker.awaitNextRequest(Promise.resolve())).resolves.toBe('complete');
    });

    it('skips an expired undelivered request and delivers the next undecided one', async () => {
        const broker = new ConfirmationBroker(60_000);

        const stale = broker.awaitDecision(makeRequest('stale'));
        await flush();
        broker.expireAll();
        await expect(stale).resolves.toBe('expired');

        const live = broker.awaitDecision(makeRequest('live'));
        await flush();

        const winner = await broker.awaitNextRequest(never);
        expect(winner === 'complete' ? '' : winner.id).toBe('live');

        broker.answer('live', true);
        await expect(live).resolves.toBe('approved');
    });

    it('ignores a second answer to the same confirmation', async () => {
        const broker = new ConfirmationBroker(60_000);

        const decided = broker.awaitDecision(makeRequest('a'));
        await flush();

        expect(broker.answer('a', true)).toBe(true);
        await expect(decided).resolves.toBe('approved');

        expect(broker.answer('a', false)).toBe(false);
    });
});
