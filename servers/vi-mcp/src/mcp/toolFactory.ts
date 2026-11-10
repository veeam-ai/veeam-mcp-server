/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { getProductName } from '@/config/settings';

export interface ToolMetadata {
    title: string;
    description: string;
}

/**
 * Static metadata for the question-answering tool.
 *
 * Deliberately performs no network I/O: the chatbot mode (Base / Advanced / AdvancedWithActions)
 * is read from the product on every tool call, so the MCP server can register its tools and
 * finish the handshake even when the Veeam product is unreachable at startup.
 */
export function createToolMetadata(): ToolMetadata {
    const productName = getProductName();

    const description =
        'Use this tool for any request involving Veeam operational knowledge or data, including troubleshooting Veeam products, ' +
        `displaying Veeam jobs, alerts, or other product data, and answering questions about Veeam documentation or procedures for ${productName}. ` +
        "It returns authoritative Veeam product guidance backed by internal telemetry and documented procedures. Preserve the user's wording; " +
        'forward questions verbatim to ensure intent is not altered. Responses arrive as JSON with top-level "message" and "artifacts" fields; ' +
        'when an artifact has type "dataframe", treat it as tabular output and render it as a table. ' +
        'When the Veeam server runs in AdvancedWithActions mode, Veeam Intelligence may also propose product actions (for example starting or ' +
        'disabling a job). When the response contains "pending_action", the action has NOT run yet: show the user the title, description, the ' +
        "exact request (method, path, body) and Veeam Intelligence's own description, ask for explicit approval, and only then call " +
        "veeam-confirm-action with the action_id and approve=true, or approve=false if the user declines. Never approve on the user's behalf " +
        'and never answer a confirmation by calling this tool again. In clients that show confirmation dialogs, the user approves or declines ' +
        'in a dialog you cannot see, and the response contains no "pending_action". The "actions" field lists every action from the answer ' +
        'with its "decision": "approved" means the user approved it, "declined" means the user declined it, "expired" means the user did not ' +
        'answer in time, and "rejected" means the MCP server policy blocked it. Never report an approved action as approved by the server.';

    return {
        title: 'Answer Veeam Question',
        description,
    };
}
