/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { describe, it, expect, beforeEach } from '@jest/globals';

import { PendingActionRegistry } from '../pendingActions';
import type { ChatService } from '@/services/chatService';
import { ConfirmationRequest } from '@/actions/types';

function request(id: string, overrides: Partial<ConfirmationRequest> = {}): ConfirmationRequest {
    return {
        id,
        invocationId: `inv-${id}`,
        kind: 'action',
        title: `Start job ${id}?`,
        description: 'Runs the job now.',
        createdAt: 0,
        expiresAt: 1_000,
        ...overrides,
    };
}

/** The registry only ever stores the chat; it never calls into it. */
const chat = {} as ChatService;

describe('PendingActionRegistry', () => {
    let registry: PendingActionRegistry;

    beforeEach(() => {
        registry = new PendingActionRegistry();
    });

    it('starts empty', () => {
        expect(registry.size).toBe(0);
        expect(registry.list()).toEqual([]);
    });

    it('stores an entry under its request id and hands back the same object', () => {
        const entry = { request: request('a'), chat };
        registry.add(entry);

        expect(registry.size).toBe(1);
        expect(registry.get('a')).toBe(entry);
    });

    it('lists requests in insertion order', () => {
        registry.add({ request: request('a'), chat });
        registry.add({ request: request('b'), chat });
        registry.add({ request: request('c'), chat });

        expect(registry.list().map((r) => r.id)).toEqual(['a', 'b', 'c']);
    });

    it('replaces an entry re-added under the same id rather than duplicating it', () => {
        const first = { request: request('a', { title: 'first' }), chat };
        const second = { request: request('a', { title: 'second' }), chat };

        registry.add(first);
        registry.add(second);

        expect(registry.size).toBe(1);
        expect(registry.get('a')).toBe(second);
        expect(registry.list()).toHaveLength(1);
    });

    it('deletes a known entry and reports whether anything was removed', () => {
        registry.add({ request: request('a'), chat });

        expect(registry.delete('a')).toBe(true);
        expect(registry.delete('a')).toBe(false);
        expect(registry.get('a')).toBeUndefined();
        expect(registry.size).toBe(0);
    });

    it('treats an unknown id as absent instead of throwing', () => {
        expect(registry.get('missing')).toBeUndefined();
        expect(registry.delete('missing')).toBe(false);
    });
});
