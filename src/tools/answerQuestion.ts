/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { ChatService } from '@/services';
import { TurnOutcome } from '@/services/types';
import { createProductRestClient, ProductRestClient } from '@/product';
import { settings, getProductCode } from '@/config/settings';
import { pendingActions } from './pendingActions';
import { ActionOutcome, ConfirmationRequest } from '@/actions/types';
import { Artifact } from '@/common/types';
import { log } from '@/utils/logger';

/** Asks the user (through the MCP client) whether an action may run. Resolves `true` to approve. */
export type ConfirmationHandler = (request: ConfirmationRequest) => Promise<boolean>;

export interface AskOptions {
    /**
     * When provided (client supports elicitation), confirmations are resolved inside the tool call.
     * Otherwise the call returns early with `pending_action` and the client must call
     * `veeam-confirm-action` (two-step flow).
     */
    confirmationHandler?: ConfirmationHandler;
    log?: (message: string) => void;
}

/** `pending_action` as exposed to MCP clients. */
export interface PendingActionView {
    action_id: string;
    kind: 'action' | 'interaction';
    title: string;
    description: string;
    dynamic_description?: string;
    method?: string;
    path?: string;
    query_params?: Record<string, unknown>;
    body?: string;
    expires_at: string;
    expires_in_sec: number;
}

export interface AskResult {
    message: string;
    artifacts: Artifact[];
    actions: ActionOutcome[];
    pending_action?: PendingActionView;
    instructions?: string;
}

export function toPendingActionView(request: ConfirmationRequest): PendingActionView {
    const view: PendingActionView = {
        action_id: request.id,
        kind: request.kind,
        title: request.title,
        description: request.description,
        expires_at: new Date(request.expiresAt).toISOString(),
        expires_in_sec: Math.max(0, Math.round((request.expiresAt - Date.now()) / 1000)),
    };

    if (request.dynamicDescription !== undefined) view.dynamic_description = request.dynamicDescription;
    if (request.method !== undefined) view.method = request.method;
    if (request.path !== undefined) view.path = request.path;
    if (request.queryParams !== undefined) view.query_params = request.queryParams;
    if (request.body !== undefined) view.body = request.body;

    return view;
}

export function pendingActionInstructions(view: PendingActionView): string {
    const what = view.kind === 'action' ? 'wants to run a product action' : 'asks the user a question';
    return (
        `Veeam Intelligence ${what} and is waiting for the user's decision. The action has NOT been executed. ` +
        `Show the user the title, the description, the exact request (${view.method ?? ''} ${view.path ?? ''}` +
        `${view.body ? ' with the body' : ''}) and Veeam Intelligence's own description, then ask for an explicit yes/no. ` +
        `Only after the user answers, call the veeam-confirm-action tool with action_id "${view.action_id}" and approve=true ` +
        `(user approved) or approve=false (user declined). Never approve on the user's behalf and do not answer by calling ` +
        `veeam-question-answering again. The request expires at ${view.expires_at}.`
    );
}

function createChatService(client: ProductRestClient): ChatService {
    return new ChatService(client, {
        productCode: getProductCode(),
        confirmationTimeoutMs: settings.ACTION_CONFIRMATION_TIMEOUT_SEC * 1000,
        turnTimeoutMs: settings.CHAT_TURN_TIMEOUT_SEC * 1000,
    });
}

/**
 * Consume turn outcomes until the answer is complete, resolving confirmations in-band when a
 * handler is available, or parking the turn in the pending-action registry otherwise.
 */
async function driveTurn(chat: ChatService, outcome: TurnOutcome, options: AskOptions, acc: AskResult): Promise<AskResult> {
    let current = outcome;

    for (;;) {
        acc.message += current.message;
        acc.artifacts.push(...current.artifacts);
        acc.actions.push(...current.actions);

        if (current.kind === 'complete') {
            chat.disconnect();
            return acc;
        }

        const { request } = current;

        if (options.confirmationHandler === undefined) {
            const entry = { request, chat };
            pendingActions.add(entry);
            void chat.whenSettled(request.id).then(() => {
                if (pendingActions.get(request.id) === entry) {
                    pendingActions.delete(request.id);
                }
            });

            const view = toPendingActionView(request);
            acc.pending_action = view;
            acc.instructions = pendingActionInstructions(view);
            log.info(`action awaiting user confirmation via MCP client: ${request.title} (${request.id})`);
            return acc;
        }

        let approve = false;
        try {
            approve = await options.confirmationHandler(request);
        } catch (error: any) {
            log.warn(`confirmation request failed, declining action: ${error?.message || String(error)}`);
        }

        chat.resolveConfirmation(request.id, approve);
        current = await chat.resume();
    }
}

export async function answerQuestion(question: string, options: AskOptions = {}): Promise<AskResult> {
    const debug = options.log ?? (() => {});
    let chat: ChatService | undefined;

    try {
        debug('Initializing ProductClient...');
        const client: ProductRestClient = createProductRestClient();

        debug('Initializing Veeam Intelligence Service...');
        chat = createChatService(client);

        debug('Connecting to service (authentication and service info retrieval)...');
        await chat.initialize();

        const outcome = await chat.sendMessage(question);
        const result = await driveTurn(chat, outcome, options, { message: '', artifacts: [], actions: [] });

        debug('Answer: ' + result.message);
        debug('Artifacts: ' + JSON.stringify(result.artifacts));

        return result;
    } catch (error: any) {
        chat?.disconnect();
        const errorMessage = error?.message || String(error);
        throw new Error(`Error occurred: ${errorMessage}`, { cause: error });
    }
}

/**
 * Second step of the two-step flow: apply the user's decision to a parked action and return the
 * rest of the Veeam Intelligence answer (or the next pending action).
 */
export async function confirmAction(actionId: string, approve: boolean, options: AskOptions = {}): Promise<AskResult> {
    const entry = pendingActions.get(actionId);
    if (entry === undefined) {
        throw new Error(
            `Unknown or expired action id "${actionId}". The action was not executed. Ask Veeam Intelligence again if it is still needed.`,
        );
    }

    pendingActions.delete(actionId);

    if (!entry.chat.resolveConfirmation(actionId, approve)) {
        throw new Error(`Action "${actionId}" has already expired. The action was not executed.`);
    }

    log.info(`user ${approve ? 'approved' : 'declined'} action ${entry.request.title} (${actionId})`);

    try {
        const outcome = await entry.chat.resume();
        return await driveTurn(entry.chat, outcome, options, { message: '', artifacts: [], actions: [] });
    } catch (error: any) {
        entry.chat.disconnect();
        const errorMessage = error?.message || String(error);
        throw new Error(`Error occurred: ${errorMessage}`, { cause: error });
    }
}

export function listPendingActions(): PendingActionView[] {
    return pendingActions.list().map(toPendingActionView);
}
