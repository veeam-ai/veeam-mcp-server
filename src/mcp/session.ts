/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { PendingActionRegistry } from '@/tools';
import { registerTools } from './registerTools';

export interface McpSession {
    server: McpServer;
    close(): Promise<void>;
}

export function createMcpSession(): McpSession {
    const server = new McpServer({
        name: 'Veeam Intelligence',
        version: '1.0.0',
    });
    const pendingActions = new PendingActionRegistry();

    registerTools(server, pendingActions);

    return {
        server,
        async close() {
            pendingActions.abandonAll();
            await server.close();
        },
    };
}
