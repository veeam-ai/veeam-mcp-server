/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { z } from 'zod';
import { answerQuestion, confirmAction, listPendingActions, AskResult, ConfirmationHandler } from '@/tools';
import { createToolMetadata } from './toolFactory';
import { ChatbotMode } from '@/common/types';
import { ConfirmationRequest } from '@/actions/types';
import { settings } from '@/config/settings';
import { log } from '@/utils/logger';

export const TOOL_NAMES = {
    answer: 'veeam-question-answering',
    confirm: 'veeam-confirm-action',
    listPending: 'veeam-list-pending-actions',
} as const;

export const BASE_MODE_WARNING =
    'IMPORTANT NOTE: Basic mode is active and answers are based on documentation only. If the user is asking questions about Veeam product data, suggest configuring advanced mode on the product.';

const pendingActionSchema = z
    .object({
        action_id: z.string().describe('Pass to veeam-confirm-action'),
        kind: z.enum(['action', 'interaction']),
        title: z.string(),
        description: z.string().describe('Static risk description of this kind of action'),
        dynamic_description: z.string().optional().describe("Veeam Intelligence's own description of this specific call"),
        method: z.string().optional(),
        path: z.string().optional(),
        query_params: z.record(z.string(), z.any()).optional(),
        body: z.string().optional().describe('Raw JSON request body that will be sent'),
        expires_at: z.string(),
        expires_in_sec: z.number(),
    })
    .optional()
    .describe('Present when Veeam Intelligence is waiting for the user to approve an action. The action has NOT run yet.');

const actionOutcomeSchema = z.object({
    action_id: z.string(),
    title: z.string(),
    method: z.string().optional(),
    path: z.string().optional(),
    decision: z.enum(['approved', 'declined', 'expired', 'rejected']),
    executed: z.boolean(),
    http_status: z.number().optional(),
    error: z.string().optional(),
});

const answerOutputSchema = {
    message: z.string().describe('Answer from Veeam Intelligence'),
    artifacts: z.array(z.any()).describe('Artifacts from Veeam Intelligence'),
    actions: z.array(actionOutcomeSchema).optional().describe('Product actions handled while producing this answer'),
    pending_action: pendingActionSchema,
    instructions: z.string().optional().describe('What to do next when pending_action is present'),
    warning: z.string().optional().describe('Warning message if any'),
};

type AnswerToolResponse = Omit<AskResult, 'mode'> & { warning?: string };

/**
 * Maps an answer to the MCP tool output. `mode` is the chatbot mode the product reported on this
 * very call, so the Base-mode advisory always reflects the current product configuration. It is
 * destructured away so it never leaks into structuredContent.
 */
export function toToolResult(result: AskResult) {
    const { mode, ...rest } = result;
    const tool_response: AnswerToolResponse = rest;

    if (mode === ChatbotMode.Base) {
        tool_response.warning = BASE_MODE_WARNING;
    }

    return {
        content: [{ type: 'text' as const, text: JSON.stringify(tool_response) }],
        structuredContent: tool_response as unknown as Record<string, unknown>,
    };
}

function formatConfirmationMessage(request: ConfirmationRequest): string {
    const lines = [request.title, '', request.description];

    if (request.method !== undefined && request.path !== undefined) {
        lines.push('', `Request: ${request.method} ${request.path}`);
    }
    if (request.body !== undefined) {
        lines.push(`Body: ${request.body}`);
    }
    if (request.dynamicDescription !== undefined) {
        lines.push('', `Veeam Intelligence: ${request.dynamicDescription}`);
    }

    return lines.join('\n');
}

/**
 * Native confirmation dialog through MCP elicitation (form mode). Only available when the client
 * declared the `elicitation` capability (Claude Code, VS Code); Claude Desktop falls back to the
 * two-step `pending_action` / `veeam-confirm-action` flow.
 */
function createElicitationHandler(server: McpServer): ConfirmationHandler | undefined {
    const capabilities = server.server.getClientCapabilities();
    if (!capabilities?.elicitation) {
        return undefined;
    }

    return async (request) => {
        const result = await server.server.elicitInput(
            {
                mode: 'form',
                message: formatConfirmationMessage(request),
                // No fields: accepting the prompt IS the approval. A boolean field would make the
                // user both toggle it and submit, so submitting the form as presented — the
                // obvious way to say yes — would silently count as a decline.
                requestedSchema: { type: 'object', properties: {} },
            },
            { timeout: settings.ACTION_CONFIRMATION_TIMEOUT_SEC * 1000 },
        );

        log.info(`confirmation prompt answered with "${result.action}": ${request.title}`);

        // `accept` is the approval. The veto covers a client that returns an `approve` field we
        // never asked for: an explicit `false` there means no, and must never be OR'd away.
        const content = result.content as { approve?: unknown } | undefined;
        return result.action === 'accept' && content?.approve !== false;
    };
}

/**
 * Registers every tool statically. Which chatbot mode the product runs in (and therefore whether
 * actions can actually be proposed) is discovered per call inside ChatService, so the tool list
 * never depends on the product being reachable at startup. The confirmation tools are harmless
 * when the product is not in AdvancedWithActions mode: nothing is ever parked for them to act on.
 */
export function registerTools(server: McpServer): void {
    const { title, description } = createToolMetadata();

    server.registerTool(
        TOOL_NAMES.answer,
        {
            title,
            description,
            inputSchema: {
                question: z.string().describe('Question to ask Veeam Intelligence'),
            },
            outputSchema: answerOutputSchema,
            annotations: {
                // Actions may run inside this call (elicitation flow) when the product allows them,
                // and that is only known per call, so the tool cannot be declared read-only.
                readOnlyHint: false,
                destructiveHint: false,
                openWorldHint: false,
            },
        },
        async ({ question }) => {
            const result = await answerQuestion(question, { confirmationHandler: createElicitationHandler(server) });
            return toToolResult(result);
        },
    );

    server.registerTool(
        TOOL_NAMES.confirm,
        {
            title: 'Confirm Veeam action',
            description:
                'Apply the user\'s decision to a product action proposed by Veeam Intelligence (see "pending_action" in a previous ' +
                'veeam-question-answering result). Call ONLY after the user explicitly approved or declined the action. approve=true executes ' +
                'the action on the Veeam server; approve=false tells Veeam Intelligence the user declined. Returns the rest of the answer, ' +
                'or another pending_action if Veeam Intelligence proposes a follow-up action.',
            inputSchema: {
                action_id: z.string().describe('action_id from pending_action'),
                approve: z.boolean().describe('true if the user explicitly approved the action, false if the user declined'),
            },
            outputSchema: answerOutputSchema,
            annotations: {
                readOnlyHint: false,
                destructiveHint: true,
                idempotentHint: false,
                openWorldHint: false,
            },
        },
        async ({ action_id, approve }) => {
            const result = await confirmAction(action_id, approve, { confirmationHandler: createElicitationHandler(server) });
            return toToolResult(result);
        },
    );

    server.registerTool(
        TOOL_NAMES.listPending,
        {
            title: 'List pending Veeam actions',
            description: 'List product actions proposed by Veeam Intelligence that are still waiting for the user to approve or decline.',
            inputSchema: {},
            outputSchema: {
                pending_actions: z.array(pendingActionSchema.unwrap()),
            },
            annotations: {
                readOnlyHint: true,
                openWorldHint: false,
            },
        },
        async () => {
            const pending_actions = listPendingActions();
            const structured = { pending_actions };
            return {
                content: [{ type: 'text' as const, text: JSON.stringify(structured) }],
                structuredContent: structured,
            };
        },
    );
}
