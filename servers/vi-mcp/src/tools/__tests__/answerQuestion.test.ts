/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { describe, it, expect, beforeAll, beforeEach, afterEach, jest } from '@jest/globals';

import type { ChatService } from '@/services/chatService';
import type { TurnOutcome } from '@/services/types';
import type { ActionOutcome, ConfirmationDecision, ConfirmationRequest } from '@/actions/types';
import type { Artifact } from '@/common/types';
import { ChatbotMode } from '@/common/types';

// `@/config/settings` validates process.env at import time, so the modules under test are pulled in
// dynamically after the environment is in place.
process.env.PRODUCT_NAME = 'vbr';
process.env.WEB_URL = 'https://vbr.local';
process.env.ADMIN_USERNAME = 'admin';
process.env.ADMIN_PASSWORD = 'password';

type AnswerQuestionModule = typeof import('../answerQuestion');
type PendingActionsModule = typeof import('../pendingActions');

let tools: AnswerQuestionModule;
let registry: PendingActionsModule['pendingActions'];

beforeAll(async () => {
    tools = await import('../answerQuestion');
    registry = (await import('../pendingActions')).pendingActions;
});

/**
 * ChatService double for the turn-driving logic: `resume()` replays a scripted queue of outcomes,
 * and `whenSettled()` hands back a promise the test resolves to simulate expiry.
 */
class FakeChat {
    public readonly resolved: { id: string; approve: boolean }[] = [];
    public disconnects = 0;
    public resumes = 0;
    /** `false` models a confirmation that expired before the user's decision arrived. */
    public resolvable = true;
    public resumeError: Error | null = null;

    private readonly queue: TurnOutcome[];
    private readonly settlers = new Map<string, (decision: ConfirmationDecision) => void>();

    constructor(...outcomes: TurnOutcome[]) {
        this.queue = outcomes;
    }

    public resolveConfirmation(id: string, approve: boolean): boolean {
        this.resolved.push({ id, approve });
        return this.resolvable;
    }

    public async resume(): Promise<TurnOutcome> {
        this.resumes += 1;
        if (this.resumeError !== null) {
            throw this.resumeError;
        }

        const next = this.queue.shift();
        if (next === undefined) {
            throw new Error('FakeChat.resume() called more times than the test scripted');
        }

        return next;
    }

    public whenSettled(id: string): Promise<ConfirmationDecision> {
        return new Promise((resolve) => this.settlers.set(id, resolve));
    }

    public disconnect(): void {
        this.disconnects += 1;
    }

    public getEffectiveMode(): ChatbotMode {
        return ChatbotMode.AdvancedWithActions;
    }

    /** Fires the `whenSettled` promise the parking code subscribed to. */
    public settle(id: string, decision: ConfirmationDecision): void {
        this.settlers.get(id)?.(decision);
    }

    public get asChatService(): ChatService {
        return this as unknown as ChatService;
    }
}

function request(id: string, overrides: Partial<ConfirmationRequest> = {}): ConfirmationRequest {
    return {
        id,
        invocationId: `inv-${id}`,
        kind: 'action',
        title: 'Start this backup job?',
        description: 'Starts a backup job on the Veeam server.',
        method: 'POST',
        path: '/api/v1/jobs/e9b6424b/start',
        createdAt: Date.now(),
        expiresAt: Date.now() + 60_000,
        ...overrides,
    };
}

function complete(message: string, artifacts: Artifact[] = [], actions: ActionOutcome[] = []): TurnOutcome {
    return { kind: 'complete', message, artifacts, actions };
}

function awaiting(req: ConfirmationRequest, message = '', artifacts: Artifact[] = [], actions: ActionOutcome[] = []): TurnOutcome {
    return { kind: 'awaiting_confirmation', request: req, message, artifacts, actions };
}

function outcome(id: string, decision: ConfirmationDecision, executed: boolean): ActionOutcome {
    return { action_id: id, title: 'Start this backup job?', decision, executed };
}

/** Parks a confirmation in the shared registry the way `driveTurn` does, without running a turn. */
function park(chat: FakeChat, req: ConfirmationRequest): void {
    registry.add({ request: req, chat: chat.asChatService });
}

describe('pending action views', () => {
    it('maps a request to the MCP-facing shape and omits optional fields that are absent', () => {
        const req = request('a1', { method: undefined, path: undefined, expiresAt: Date.now() + 30_000 });

        const view = tools.toPendingActionView(req);

        expect(view).toEqual({
            action_id: 'a1',
            kind: 'action',
            title: 'Start this backup job?',
            description: 'Starts a backup job on the Veeam server.',
            expires_at: new Date(req.expiresAt).toISOString(),
            expires_in_sec: 30,
        });
    });

    it('carries the request details through when they are present', () => {
        const view = tools.toPendingActionView(
            request('a1', {
                dynamicDescription: 'Runs the nightly job ahead of schedule.',
                queryParams: { force: true },
                body: '{"mode":"full"}',
            }),
        );

        expect(view).toMatchObject({
            method: 'POST',
            path: '/api/v1/jobs/e9b6424b/start',
            dynamic_description: 'Runs the nightly job ahead of schedule.',
            query_params: { force: true },
            body: '{"mode":"full"}',
        });
    });

    it('never reports a negative remaining lifetime for an already-expired request', () => {
        const view = tools.toPendingActionView(request('a1', { expiresAt: Date.now() - 60_000 }));

        expect(view.expires_in_sec).toBe(0);
    });

    it('instructs the client to ask the user and names the id and tool to call back with', () => {
        const view = tools.toPendingActionView(request('a1'));

        const instructions = tools.pendingActionInstructions(view);

        expect(instructions).toContain('wants to run a product action');
        expect(instructions).toContain('has NOT been executed');
        expect(instructions).toContain('POST /api/v1/jobs/e9b6424b/start');
        expect(instructions).toContain('veeam-confirm-action');
        expect(instructions).toContain('"a1"');
        expect(instructions).toContain(view.expires_at);
    });

    it('describes an interaction as a question rather than an action', () => {
        const view = tools.toPendingActionView(request('a1', { kind: 'interaction', method: undefined, path: undefined }));

        expect(tools.pendingActionInstructions(view)).toContain('asks the user a question');
    });
});

describe('confirmAction', () => {
    let stderr: jest.SpiedFunction<typeof process.stderr.write>;

    beforeEach(() => {
        stderr = jest.spyOn(process.stderr, 'write').mockImplementation(() => true);
    });

    afterEach(() => {
        stderr.mockRestore();
        for (const pending of registry.list()) {
            registry.delete(pending.id);
        }
    });

    it('rejects an unknown id and states that nothing ran', async () => {
        await expect(tools.confirmAction('nope', true)).rejects.toThrow(/Unknown or expired action id "nope"/);
        await expect(tools.confirmAction('nope', true)).rejects.toThrow(/was not executed/);
    });

    it('rejects an id that expired before the decision arrived, and forgets it', async () => {
        const chat = new FakeChat();
        chat.resolvable = false;
        park(chat, request('a1'));

        await expect(tools.confirmAction('a1', true)).rejects.toThrow(/already expired/);

        expect(registry.get('a1')).toBeUndefined();
        expect(chat.resumes).toBe(0);
    });

    it('approves the action, resumes the turn and returns the completed answer', async () => {
        const artifact: Artifact = { id: 'art-1', type: 'string', data: 'job started' };
        const chat = new FakeChat(complete('The job is running.', [artifact], [outcome('a1', 'approved', true)]));
        park(chat, request('a1'));

        const result = await tools.confirmAction('a1', true);

        expect(chat.resolved).toEqual([{ id: 'a1', approve: true }]);
        expect(result.message).toBe('The job is running.');
        expect(result.artifacts).toEqual([artifact]);
        expect(result.actions).toEqual([outcome('a1', 'approved', true)]);
        expect(result.pending_action).toBeUndefined();
        expect(chat.disconnects).toBe(1);
        expect(registry.size).toBe(0);
    });

    it('passes a decline through to the turn instead of executing', async () => {
        const chat = new FakeChat(complete('Understood, I left the job alone.', [], [outcome('a1', 'declined', false)]));
        park(chat, request('a1'));

        const result = await tools.confirmAction('a1', false);

        expect(chat.resolved).toEqual([{ id: 'a1', approve: false }]);
        expect(result.actions[0]?.executed).toBe(false);
    });

    it('parks a follow-up confirmation when the client cannot elicit, leaving the turn open', async () => {
        const followUp = request('a2', { title: 'Delete this backup?' });
        const chat = new FakeChat(awaiting(followUp, 'First job done. ', [], [outcome('a1', 'approved', true)]));
        park(chat, request('a1'));

        const result = await tools.confirmAction('a1', true);

        expect(result.message).toBe('First job done. ');
        expect(result.actions).toEqual([outcome('a1', 'approved', true)]);
        expect(result.pending_action?.action_id).toBe('a2');
        expect(result.pending_action?.title).toBe('Delete this backup?');
        expect(result.instructions).toContain('veeam-confirm-action');

        // The socket turn must stay open — the follow-up is still waiting on the user.
        expect(chat.disconnects).toBe(0);
        expect(registry.list().map((pending) => pending.id)).toEqual(['a2']);
        expect(tools.listPendingActions().map((view) => view.action_id)).toEqual(['a2']);
    });

    it('forgets a parked action once the underlying confirmation settles', async () => {
        const followUp = request('a2');
        const chat = new FakeChat(awaiting(followUp));
        park(chat, request('a1'));

        await tools.confirmAction('a1', true);
        expect(registry.get('a2')).toBeDefined();

        chat.settle('a2', 'expired');
        await Promise.resolve();

        expect(registry.get('a2')).toBeUndefined();
        expect(tools.listPendingActions()).toEqual([]);
    });

    it('resolves follow-up confirmations in-band when the client supports elicitation', async () => {
        const first = request('a2', { title: 'Delete this backup?' });
        const second = request('a3', { title: 'Remove the repository?' });
        const chat = new FakeChat(
            awaiting(first, 'Step one done. ', [], [outcome('a1', 'approved', true)]),
            awaiting(second, 'Step two done. ', [], [outcome('a2', 'approved', true)]),
            complete('All three steps are finished.', [], [outcome('a3', 'declined', false)]),
        );
        park(chat, request('a1'));

        const asked: string[] = [];
        const confirmationHandler = async (req: ConfirmationRequest) => {
            asked.push(req.id);
            return req.id !== 'a3';
        };

        const result = await tools.confirmAction('a1', true, { confirmationHandler });

        expect(asked).toEqual(['a2', 'a3']);
        expect(chat.resolved).toEqual([
            { id: 'a1', approve: true },
            { id: 'a2', approve: true },
            { id: 'a3', approve: false },
        ]);
        expect(result.message).toBe('Step one done. Step two done. All three steps are finished.');
        expect(result.actions.map((action) => action.action_id)).toEqual(['a1', 'a2', 'a3']);
        expect(result.pending_action).toBeUndefined();
        expect(chat.disconnects).toBe(1);
        // Nothing is parked: every confirmation was answered inside the call.
        expect(registry.size).toBe(0);
    });

    it('declines the action when the elicitation handler fails, rather than failing the turn', async () => {
        const chat = new FakeChat(awaiting(request('a2')), complete('Left it alone.'));
        park(chat, request('a1'));

        const confirmationHandler = async () => {
            throw new Error('client closed the elicitation');
        };

        const result = await tools.confirmAction('a1', true, { confirmationHandler });

        expect(chat.resolved).toContainEqual({ id: 'a2', approve: false });
        expect(result.message).toBe('Left it alone.');
        expect(stderr.mock.calls.map((call) => String(call[0])).join('')).toContain('client closed the elicitation');
    });

    it('disconnects and wraps the failure when resuming the turn throws', async () => {
        const chat = new FakeChat();
        chat.resumeError = new Error('socket closed');
        park(chat, request('a1'));

        await expect(tools.confirmAction('a1', true)).rejects.toThrow(/Error occurred: socket closed/);

        expect(chat.disconnects).toBe(1);
    });
});

describe('listPendingActions', () => {
    afterEach(() => {
        for (const pending of registry.list()) {
            registry.delete(pending.id);
        }
    });

    it('is empty when nothing is waiting', () => {
        expect(tools.listPendingActions()).toEqual([]);
    });

    it('reports every parked request as a client-facing view', () => {
        const chat = new FakeChat();
        park(chat, request('a1', { title: 'Start this backup job?' }));
        park(chat, request('a2', { title: 'Delete this backup?', kind: 'interaction' }));

        expect(tools.listPendingActions()).toEqual([
            expect.objectContaining({ action_id: 'a1', kind: 'action', title: 'Start this backup job?' }),
            expect.objectContaining({ action_id: 'a2', kind: 'interaction', title: 'Delete this backup?' }),
        ]);
    });
});
