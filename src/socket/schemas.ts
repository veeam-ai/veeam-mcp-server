/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { z } from 'zod';

const httpMethodSchema = z.enum(['GET', 'POST', 'PUT', 'PATCH', 'DELETE']);

const fetchDataParametersSchema = z.looseObject({
    endpoint_path: z.string().min(1),
    query_params: z.record(z.string(), z.unknown()).default({}),
    method: httpMethodSchema.default('GET'),
    body: z.string().optional(),
    headers: z.record(z.string(), z.string()).optional(),
    description: z.string().optional(),
});

const fetchDataInvocationSchema = z.looseObject({
    invocation_id: z.string().min(1),
    tool_name: z.literal('fetch_data_from_endpoint'),
    parameters: fetchDataParametersSchema,
});

const userInteractionParametersSchema = z.looseObject({
    request_id: z.string().optional(),
    kind: z.enum(['confirmation', 'singleSelect', 'multiSelect', 'treeSelect']),
    label: z.string().optional(),
    title: z.string().optional(),
    description: z.string().optional(),
    options: z.array(z.unknown()).optional(),
    default_value: z.unknown().optional(),
    accept_custom_input: z.boolean().optional(),
});

const userInteractionInvocationSchema = z.looseObject({
    invocation_id: z.string().min(1),
    tool_name: z.literal('request_user_interaction'),
    parameters: userInteractionParametersSchema,
});

export const toolInvocationSchema = z.discriminatedUnion('tool_name', [fetchDataInvocationSchema, userInteractionInvocationSchema]);

export const responseChunkSchema = z.discriminatedUnion('type', [
    z.looseObject({ type: z.literal('token'), payload: z.string() }),
    z.looseObject({
        type: z.literal('artifact'),
        payload: z.looseObject({ id: z.string().min(1), type: z.string().min(1), data: z.unknown() }),
    }),
]);

/** The pre-validation wire shape: `method` and `query_params` may be absent here. */
export type ToolInvocationInput = z.input<typeof toolInvocationSchema>;

export const invocationIdSchema = z.looseObject({ invocation_id: z.string().min(1) });

export function describeParseError(error: z.ZodError): string {
    const issue = error.issues[0];
    if (issue === undefined) {
        return 'invalid payload';
    }

    const path = issue.path.join('.');
    return path.length > 0 ? `${path}: ${issue.message}` : issue.message;
}
