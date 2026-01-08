/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { ProductClient, VoneClient, VspcClient, VbrClient } from './clients';

export function createProductClient(): ProductClient {
    if (!process.env.PRODUCT_NAME || !process.env.WEB_URL || !process.env.ADMIN_USERNAME || !process.env.ADMIN_PASSWORD) {
        throw new Error('Missing required environment variables: PRODUCT_NAME, WEB_URL, ADMIN_USERNAME, ADMIN_PASSWORD');
    }

    const baseURL = process.env.WEB_URL;
    const username = process.env.ADMIN_USERNAME;
    const password = process.env.ADMIN_PASSWORD;

    switch (process.env.PRODUCT_NAME) {
        case 'vone':
            return new VoneClient(baseURL, username, password);
        case 'vspc':
            return new VspcClient(baseURL, username, password);
        case 'vbr':
            return new VbrClient(baseURL, username, password);
        default:
            throw new Error(
                'MCP server configuration error. Unknown or missing PRODUCT_NAME environment variable. Supported values: vone (Veeam One), vspc (Veeam Service Provider Console), vbr (Veeam Backup & Replication). Verify mcp server configuration.',
            );
    }
}
