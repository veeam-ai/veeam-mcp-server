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

const INSECURE_ISSUER_HOSTS = ['localhost', '127.0.0.1'];

function optionalNumber(val: unknown): unknown {
    return typeof val === 'string' && val.trim() !== '' ? Number(val) : undefined;
}

function optionalString(val: unknown): unknown {
    return typeof val === 'string' && val.trim() !== '' ? val.trim() : undefined;
}

function optionalLowercase(val: unknown): unknown {
    return typeof val === 'string' && val.trim() !== '' ? val.toLowerCase().trim() : undefined;
}

function optionalList(normalize: (item: string) => string): (val: unknown) => unknown {
    return (val) =>
        typeof val === 'string' && val.trim() !== ''
            ? val
                  .split(',')
                  .map((item) => normalize(item.trim()))
                  .filter((item) => item !== '')
            : undefined;
}

export function normalizeHost(host: string): string {
    return host.toLowerCase().replace(/^\[(.*)\]$/, '$1');
}

export function isLoopbackHost(host: string): boolean {
    return LOOPBACK_HOSTS.includes(normalizeHost(host));
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
            .preprocess(optionalString, z.string().optional())
            .describe('Veeam product user for stdio mode. Not used over HTTP, where every user signs in with their own account.'),
        ADMIN_PASSWORD: z.preprocess(optionalString, z.string().optional()).describe('Password of ADMIN_USERNAME (stdio mode only).'),

        // Optional variables
        ACCEPT_SELF_SIGNED_CERT: z
            .preprocess((val) => (typeof val === 'string' ? val.toLowerCase().trim() === 'true' : false), z.boolean())
            .default(false),
        ACTION_CONFIRMATION_TIMEOUT_SEC: z
            .preprocess(optionalNumber, z.number().int().positive().max(1700))
            .default(1500)
            .describe(
                'How long a proposed action waits for the user decision before it is declined (must stay below the 1800 s Veeam Intelligence budget).',
            ),
        CHAT_TURN_TIMEOUT_SEC: z
            .preprocess(optionalNumber, z.number().int().positive())
            .default(3600)
            .describe('Upper bound for a single Veeam Intelligence answer, including confirmation waits.'),

        MCP_TRANSPORT: z
            .preprocess(optionalLowercase, z.enum(['stdio', 'http']))
            .default('stdio')
            .describe('How MCP clients connect: "stdio" (the client starts this process) or "http" (Streamable HTTP endpoint).'),
        MCP_HTTP_HOST: z.preprocess(optionalString, z.string()).default('127.0.0.1').describe('Interface the HTTP endpoint binds to.'),
        MCP_HTTP_PORT: z.preprocess(optionalNumber, z.number().int().min(1).max(65535)).default(8080),
        MCP_HTTP_AUTH: z
            .preprocess(optionalLowercase, z.enum(['basic', 'oauth']))
            .default('basic')
            .describe(
                'How HTTP users sign in with their Veeam account: "basic" (the client sends the password with every request) or "oauth" (a sign-in page served by this server).',
            ),
        MCP_HTTP_PUBLIC_URL: z
            .preprocess(optionalString, z.url('MCP_HTTP_PUBLIC_URL must be a valid URL').optional())
            .describe(
                'Origin MCP clients use to reach this server, e.g. https://mcp.company.local. OAuth only; required unless MCP_HTTP_HOST is loopback.',
            ),
        MCP_HTTP_TOKEN_SECRET: z
            .preprocess(optionalString, z.string().min(32, 'MCP_HTTP_TOKEN_SECRET must be at least 32 characters long').optional())
            .describe('Key material for the encrypted OAuth tokens. Without it a random key is used and sign-ins end on restart.'),
        MCP_HTTP_SIGN_IN_MAX_AGE_SEC: z
            .preprocess(optionalNumber, z.number().int().positive())
            .default(43200)
            .describe('How long an OAuth sign-in can be refreshed before the user must enter the Veeam password again.'),
        MCP_HTTP_ALLOWED_REDIRECT_URIS: z
            .preprocess(
                optionalList((uri) => uri),
                z.array(z.url('MCP_HTTP_ALLOWED_REDIRECT_URIS must contain valid URLs')).optional(),
            )
            .describe('OAuth redirect URIs accepted besides loopback ones, e.g. https://vscode.dev/redirect.'),
        MCP_HTTP_BEHIND_TLS_PROXY: z
            .preprocess((val) => (typeof val === 'string' ? val.toLowerCase().trim() === 'true' : false), z.boolean())
            .default(false)
            .describe('Set to true when a reverse proxy in front of the server terminates TLS.'),
        MCP_HTTP_TRUST_PROXY: z
            .preprocess(optionalNumber, z.number().int().min(0).optional())
            .describe(
                'Number of reverse proxies in front of the server, used to find the client address for rate limiting. Defaults to 1 with MCP_HTTP_BEHIND_TLS_PROXY=true, otherwise 0.',
            ),
        MCP_HTTP_ALLOWED_HOSTS: z
            .preprocess(
                optionalList((host) => host.toLowerCase()),
                z.array(z.string()).optional(),
            )
            .describe(
                'Comma-separated host names accepted in the Host and Origin headers. Defaults to the MCP_HTTP_PUBLIC_URL host, or loopback names on a loopback bind.',
            ),
        MCP_HTTP_TLS_CERT_FILE: z.preprocess(optionalString, z.string().optional()),
        MCP_HTTP_TLS_KEY_FILE: z.preprocess(optionalString, z.string().optional()),
        MCP_HTTP_MAX_SESSIONS: z
            .preprocess(optionalNumber, z.number().int().positive())
            .default(1000)
            .describe('Maximum concurrent HTTP sessions; one session is one connected MCP client window.'),
        MCP_HTTP_MAX_SESSIONS_PER_USER: z
            .preprocess(optionalNumber, z.number().int().positive())
            .default(10)
            .describe('Maximum concurrent HTTP sessions of one Veeam user, so one user cannot take every session.'),
        MCP_HTTP_SESSION_IDLE_TIMEOUT_SEC: z
            .preprocess(optionalNumber, z.number().int().positive())
            .default(3600)
            .describe(
                'An HTTP session with no requests for this long is closed. Must not be shorter than ACTION_CONFIRMATION_TIMEOUT_SEC.',
            ),
    })
    .superRefine((value, ctx) => {
        if (value.MCP_TRANSPORT !== 'http') {
            if (value.ADMIN_USERNAME === undefined) {
                ctx.addIssue({ code: 'custom', message: 'ADMIN_USERNAME environment variable is required' });
            }
            if (value.ADMIN_PASSWORD === undefined) {
                ctx.addIssue({ code: 'custom', message: 'ADMIN_PASSWORD environment variable is required' });
            }
            return;
        }
        if (value.ADMIN_USERNAME !== undefined || value.ADMIN_PASSWORD !== undefined) {
            ctx.addIssue({
                code: 'custom',
                message:
                    'ADMIN_USERNAME and ADMIN_PASSWORD must not be set when MCP_TRANSPORT=http: every user signs in with their own Veeam account',
            });
        }
        if (!isLoopbackHost(value.MCP_HTTP_HOST) && value.MCP_HTTP_TLS_CERT_FILE === undefined && !value.MCP_HTTP_BEHIND_TLS_PROXY) {
            ctx.addIssue({
                code: 'custom',
                message:
                    `TLS is required when the HTTP endpoint listens on a non-loopback address (MCP_HTTP_HOST=${value.MCP_HTTP_HOST}): ` +
                    'set MCP_HTTP_TLS_CERT_FILE and MCP_HTTP_TLS_KEY_FILE, or MCP_HTTP_BEHIND_TLS_PROXY=true',
            });
        }
        if (value.MCP_HTTP_AUTH === 'oauth') {
            if (value.MCP_HTTP_PUBLIC_URL === undefined) {
                if (normalizeHost(value.MCP_HTTP_HOST) === '::1') {
                    ctx.addIssue({
                        code: 'custom',
                        message:
                            'MCP_HTTP_AUTH=oauth cannot advertise ::1 as its sign-in address: set MCP_HTTP_HOST=127.0.0.1 or localhost, or set MCP_HTTP_PUBLIC_URL',
                    });
                } else if (!isLoopbackHost(value.MCP_HTTP_HOST)) {
                    ctx.addIssue({
                        code: 'custom',
                        message: `MCP_HTTP_PUBLIC_URL is required with MCP_HTTP_AUTH=oauth when the HTTP endpoint listens on a non-loopback address (MCP_HTTP_HOST=${value.MCP_HTTP_HOST})`,
                    });
                }
            } else {
                const publicUrl = new URL(value.MCP_HTTP_PUBLIC_URL);
                if (publicUrl.protocol !== 'https:' && !INSECURE_ISSUER_HOSTS.includes(publicUrl.hostname)) {
                    ctx.addIssue({
                        code: 'custom',
                        message: 'MCP_HTTP_PUBLIC_URL must use https unless it is http://localhost or http://127.0.0.1',
                    });
                }
                if (publicUrl.pathname !== '/' || publicUrl.search !== '' || publicUrl.hash !== '') {
                    ctx.addIssue({ code: 'custom', message: 'MCP_HTTP_PUBLIC_URL must be an origin without a path, query or fragment' });
                }
            }
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
