/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import type { ChatService } from '@/services/chatService';
import { ConfirmationRequest } from './types';

export interface PendingActionEntry {
    request: ConfirmationRequest;
    /** The live chat turn that is paused waiting for this decision. */
    chat: ChatService;
}

/**
 * Process-wide registry of confirmations that were handed to the MCP client as `pending_action`
 * (two-step flow for clients without elicitation). Entries are removed when the confirmation is
 * settled (approved, declined, expired or the turn ended).
 */
export class PendingActionRegistry {
    private readonly entries = new Map<string, PendingActionEntry>();

    public add(entry: PendingActionEntry): void {
        this.entries.set(entry.request.id, entry);
    }

    public get(id: string): PendingActionEntry | undefined {
        return this.entries.get(id);
    }

    public delete(id: string): boolean {
        return this.entries.delete(id);
    }

    public list(): ConfirmationRequest[] {
        return Array.from(this.entries.values(), (entry) => entry.request);
    }

    public get size(): number {
        return this.entries.size;
    }
}

export const pendingActions = new PendingActionRegistry();
