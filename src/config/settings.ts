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

const settingsSchema = z.object({
    // Required variables
    PRODUCT_NAME: z
        .preprocess((val) => (typeof val === 'string' ? val.toLowerCase().trim() : val), ProductCodeEnum)
        .describe(`Product code: "vbr" for Veeam Backup & Replication, "vone" for Veeam One, "vspc" for Veeam Service Provider Console`),
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
});

function parseSettings() {
    try {
        return settingsSchema.parse(process.env);
    } catch (err) {
        if (err instanceof z.ZodError) {
            const errorMessages = err.issues.map((issue) => issue.message);
            if (errorMessages.length == 1) {
                throw new Error(errorMessages[0]);
            } else if (errorMessages.length > 1) {
                const message = 'Configuration errors:\n' + errorMessages.map((msg) => ` - ${msg}`).join('\n');
                throw new Error(message);
            }
        }

        throw err;
    }
}

export const settings = parseSettings();
