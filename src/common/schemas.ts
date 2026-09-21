/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { z } from 'zod';

/**
 * The Veeam Intelligence wire contract. These schemas are the single source of truth: every type
 * in `common/types.ts` that describes an inbound frame is inferred from here, so a schema and the
 * type the rest of the server reasons about cannot drift apart.
 *
 * Frames the server consumes are `z.object` (unknown fields are accepted and stripped, so a new
 * field never breaks the connection, and the inferred type stays exact). Frames the server only
 * forwards are `z.looseObject`, because dropping a field we do not model yet would lose content.
 */

export const httpMethodSchema = z.enum(['GET', 'POST', 'PUT', 'PATCH', 'DELETE']);

export const userInteractionKindSchema = z.enum(['confirmation', 'singleSelect', 'multiSelect', 'treeSelect']);

/** Forwarded verbatim to the MCP client, so unmodelled fields must survive parsing. */
export const artifactSchema = z.looseObject({
    id: z.string().min(1),
    type: z.string().min(1),
    data: z.unknown(),
});

export const responseChunkSchema = z.discriminatedUnion('type', [
    z.object({ type: z.literal('token'), payload: z.string() }),
    z.object({ type: z.literal('artifact'), payload: artifactSchema }),
]);

const fetchDataParametersSchema = z.object({
    endpoint_path: z.string().min(1),
    query_params: z.record(z.string(), z.unknown()).default({}),
    method: httpMethodSchema.default('GET'),
    body: z.string().optional(),
    headers: z.record(z.string(), z.string()).optional(),
    description: z.string().optional(),
});

const fetchDataInvocationSchema = z.object({
    invocation_id: z.string().min(1),
    tool_name: z.literal('fetch_data_from_endpoint'),
    parameters: fetchDataParametersSchema,
});

const userInteractionParametersSchema = z.object({
    request_id: z.string().optional(),
    kind: userInteractionKindSchema,
    label: z.string().optional(),
    title: z.string().optional(),
    description: z.string().optional(),
    options: z.array(z.unknown()).optional(),
    default_value: z.unknown().optional(),
    accept_custom_input: z.boolean().optional(),
});

const userInteractionInvocationSchema = z.object({
    invocation_id: z.string().min(1),
    tool_name: z.literal('request_user_interaction'),
    parameters: userInteractionParametersSchema,
});

export const toolInvocationSchema = z.discriminatedUnion('tool_name', [fetchDataInvocationSchema, userInteractionInvocationSchema]);

/** Recovers the id from an invocation that failed full validation, so it can still be answered. */
export const invocationIdSchema = z.looseObject({ invocation_id: z.string().min(1) });

/** The pre-validation wire shape: `method` and `query_params` may be absent here. */
export type ToolInvocationInput = z.input<typeof toolInvocationSchema>;

export function describeParseError(error: z.ZodError): string {
    const issue = error.issues[0];
    if (issue === undefined) {
        return 'invalid payload';
    }

    const path = issue.path.join('.');
    return path.length > 0 ? `${path}: ${issue.message}` : issue.message;
}
