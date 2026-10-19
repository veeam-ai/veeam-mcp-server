/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

/**
 * Minimal stderr logger. stdout is the MCP stdio transport and must never receive log output.
 */
export const log = {
    info(message: string): void {
        process.stderr.write(`[veeam-intelligence] ${message}\n`);
    },
    warn(message: string): void {
        process.stderr.write(`[veeam-intelligence] WARNING: ${message}\n`);
    },
    error(message: string): void {
        process.stderr.write(`[veeam-intelligence] ERROR: ${message}\n`);
    },
};
