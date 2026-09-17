/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

/** One row of a host fetch policy: a method + `:param`-style path pattern. */
export interface FetchPolicyEntry {
    method: HttpMethod;
    pathPattern: string;
    /** Key into the policy texts; empty for whitelist entries (never shown). */
    titleKey: string;
    descriptionKey: string;
}

/**
 * Deny-by-default gate for state-changing product REST calls proposed by Veeam Intelligence.
 * - `whitelist`: non-GET calls that run silently (POST-shaped reads, routine maintenance).
 * - `checklist`: calls that require explicit user confirmation.
 * Anything else that is not a GET is rejected without asking.
 */
export interface FetchPolicyRegistry {
    whitelist: FetchPolicyEntry[];
    checklist: FetchPolicyEntry[];
}

export type GateDecision =
    { kind: 'allowed' } | { kind: 'rejected'; reason: string } | { kind: 'confirm'; title: string; description: string };

export type ConfirmationKind = 'action' | 'interaction';

/**
 * A confirmation Veeam Intelligence is waiting for. Exposed to MCP clients as `pending_action`.
 * The underlying socket turn stays open until the request is resolved or expires.
 */
export interface ConfirmationRequest {
    /** Opaque id handed to the MCP client (`action_id`). */
    id: string;
    /** Veeam Intelligence tool invocation id this confirmation answers. */
    invocationId: string;
    kind: ConfirmationKind;
    /** Static, policy-authored title, e.g. "Start this backup job?". */
    title: string;
    /** Static, policy-authored risk description. */
    description: string;
    /** Free-text description written by the assistant for this specific call, if any. */
    dynamicDescription?: string;
    method?: HttpMethod;
    path?: string;
    queryParams?: Record<string, unknown>;
    /** Raw request body (already-serialised JSON), if any. */
    body?: string;
    createdAt: number;
    expiresAt: number;
}

/** `rejected` is decided by policy without asking the user; the others are user/timeout outcomes. */
export type ConfirmationDecision = 'approved' | 'declined' | 'expired' | 'rejected';

/** What happened to a confirmed/declined action during a turn; reported back to the MCP client. */
export interface ActionOutcome {
    action_id: string;
    title: string;
    method?: HttpMethod;
    path?: string;
    decision: ConfirmationDecision;
    executed: boolean;
    http_status?: number;
    error?: string;
}

/** What the caller should send back to Veeam Intelligence as the `tool_result`. */
export interface ToolResultPayload {
    status: string;
    data: unknown;
}

/** One handled tool invocation: the reply to send, and the outcome to report (absent for silent reads). */
export interface HandledInvocation {
    result: ToolResultPayload;
    outcome?: ActionOutcome;
}

/** Sent as `tool_result.data` when the user declines/cancels; the only value the agent maps to "user cancelled". */
export const USER_CANCELLED_ACTION_RESULT = { code: 'user_cancelled_action' } as const;
