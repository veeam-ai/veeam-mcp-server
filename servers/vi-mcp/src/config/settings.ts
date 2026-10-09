/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { z } from 'zod';

const Product = {
    vbr: 'Veeam Backup & Replication',
    vone: 'Veeam One',
    vspc: 'Veeam Service Provider Console',
} as const;

type ProductCode = keyof typeof Product;

export function getProductCode(): ProductCode {
    return settings.PRODUCT_NAME as ProductCode;
}

export function getProductName(): string {
    return Product[getProductCode()];
}

export const ProductCodeEnum = z.enum(Object.keys(Product), {
    error: (issue: any) => {
        if (issue.code === 'invalid_type' && issue.input === undefined) {
            return `PRODUCT_NAME environment variable is required. Valid values are: ${Object.keys(Product).join(', ')}`;
        }
        return `PRODUCT_NAME environment variable has unexpected value "${issue.input}". Valid values are: ${Object.keys(Product).join(', ')}.`;
    },
});

export const LOOPBACK_HOSTS = ['localhost', '127.0.0.1', '::1'];

function optionalNumber(val: unknown): unknown {
    return typeof val === 'string' && val.trim() !== '' ? Number(val) : undefined;
}

function optionalString(val: unknown): unknown {
    return typeof val === 'string' && val.trim() !== '' ? val.trim() : undefined;
}

const settingsSchema = z
    .object({
        // Required variables
        PRODUCT_NAME: z
            .preprocess((val) => (typeof val === 'string' ? val.toLowerCase().trim() : val), ProductCodeEnum)
            .describe(
                `Product code: "vbr" for Veeam Backup & Replication, "vone" for Veeam One, "vspc" for Veeam Service Provider Console`,
            ),
        WEB_URL: z.url('WEB_URL must be a valid Veeam product web UI URL').describe('Veeam product web UI endpoint URL'),
        ADMIN_USERNAME: z
            .string()
            .min(1, 'ADMIN_USERNAME environment variable is required')
            .describe('Administrator username for Veeam product authentication'),
        ADMIN_PASSWORD: z
            .string()
            .min(1, 'ADMIN_PASSWORD environment variable is required')
            .describe('Administrator password for Veeam product authentication'),

        // Optional variables
        ACCEPT_SELF_SIGNED_CERT: z
            .preprocess((val) => (typeof val === 'string' ? val.toLowerCase().trim() === 'true' : false), z.boolean())
            .default(false),
        ACTION_CONFIRMATION_TIMEOUT_SEC: z
            .preprocess(
                (val) => (typeof val === 'string' && val.trim() !== '' ? Number(val) : undefined),
                z.number().int().positive().max(1700),
            )
            .default(1500)
            .describe(
                'How long a proposed action waits for the user decision before it is declined (must stay below the 1800 s Veeam Intelligence budget).',
            ),
        CHAT_TURN_TIMEOUT_SEC: z
            .preprocess((val) => (typeof val === 'string' && val.trim() !== '' ? Number(val) : undefined), z.number().int().positive())
            .default(3600)
            .describe('Upper bound for a single Veeam Intelligence answer, including confirmation waits.'),

        MCP_TRANSPORT: z
            .preprocess(
                (val) => (typeof val === 'string' && val.trim() !== '' ? val.toLowerCase().trim() : undefined),
                z.enum(['stdio', 'http']),
            )
            .default('stdio')
            .describe('How MCP clients connect: "stdio" (the client starts this process) or "http" (Streamable HTTP endpoint).'),
        MCP_HTTP_HOST: z.preprocess(optionalString, z.string()).default('127.0.0.1').describe('Interface the HTTP endpoint binds to.'),
        MCP_HTTP_PORT: z.preprocess(optionalNumber, z.number().int().min(1).max(65535)).default(8080),
        MCP_HTTP_AUTH_TOKEN: z
            .preprocess(optionalString, z.string().min(32, 'MCP_HTTP_AUTH_TOKEN must be at least 32 characters long').optional())
            .describe('Bearer token every HTTP request must present. Required unless MCP_HTTP_HOST is a loopback address.'),
        MCP_HTTP_ALLOWED_HOSTS: z
            .preprocess(
                (val) =>
                    typeof val === 'string' && val.trim() !== ''
                        ? val
                              .split(',')
                              .map((host) => host.trim().toLowerCase())
                              .filter((host) => host !== '')
                        : undefined,
                z.array(z.string()).optional(),
            )
            .describe('Comma-separated host names accepted in the Host and Origin headers. Defaults to loopback names on a loopback bind.'),
        MCP_HTTP_TLS_CERT_FILE: z.preprocess(optionalString, z.string().optional()),
        MCP_HTTP_TLS_KEY_FILE: z.preprocess(optionalString, z.string().optional()),
        MCP_HTTP_MAX_SESSIONS: z.preprocess(optionalNumber, z.number().int().positive()).default(100),
        MCP_HTTP_SESSION_IDLE_TIMEOUT_SEC: z
            .preprocess(optionalNumber, z.number().int().positive())
            .default(3600)
            .describe(
                'An HTTP session with no requests for this long is closed. Must not be shorter than ACTION_CONFIRMATION_TIMEOUT_SEC.',
            ),
    })
    .superRefine((value, ctx) => {
        if (value.MCP_TRANSPORT !== 'http') {
            return;
        }
        if (value.MCP_HTTP_AUTH_TOKEN === undefined && !LOOPBACK_HOSTS.includes(value.MCP_HTTP_HOST.toLowerCase())) {
            ctx.addIssue({
                code: 'custom',
                message: `MCP_HTTP_AUTH_TOKEN is required when the HTTP endpoint listens on a non-loopback address (MCP_HTTP_HOST=${value.MCP_HTTP_HOST})`,
            });
        }
        if ((value.MCP_HTTP_TLS_CERT_FILE === undefined) !== (value.MCP_HTTP_TLS_KEY_FILE === undefined)) {
            ctx.addIssue({ code: 'custom', message: 'MCP_HTTP_TLS_CERT_FILE and MCP_HTTP_TLS_KEY_FILE must be set together' });
        }
        if (value.MCP_HTTP_SESSION_IDLE_TIMEOUT_SEC < value.ACTION_CONFIRMATION_TIMEOUT_SEC) {
            ctx.addIssue({
                code: 'custom',
                message: 'MCP_HTTP_SESSION_IDLE_TIMEOUT_SEC must not be shorter than ACTION_CONFIRMATION_TIMEOUT_SEC',
            });
        }
    });

export type Settings = z.infer<typeof settingsSchema>;

export function parseSettings(env: NodeJS.ProcessEnv = process.env): Settings {
    try {
        return settingsSchema.parse(env);
    } catch (err) {
        if (err instanceof z.ZodError) {
            const errorMessages = err.issues.map((issue) => issue.message);
            if (errorMessages.length == 1) {
                throw new Error(errorMessages[0], { cause: err });
            } else if (errorMessages.length > 1) {
                const message = 'Configuration errors:\n' + errorMessages.map((msg) => ` - ${msg}`).join('\n');
                throw new Error(message, { cause: err });
            }
        }

        throw err;
    }
}

export const settings = parseSettings();
