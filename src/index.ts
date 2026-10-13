/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { createMcpSession } from './mcp/session';
import { settings } from './config/settings';
import { httpServerOptionsFromSettings, startHttpServer } from './transports/http';
import { productAuthOf } from './auth/identity';
import { productAuthFromSettings } from './product';
import { log } from './utils/logger';

async function serveStdio(): Promise<void> {
    const { server } = createMcpSession(productAuthFromSettings);
    await server.connect(new StdioServerTransport());
    log.info('MCP server started on stdio; the chatbot mode is read from the Veeam product on every request');
}

async function serveHttp(): Promise<void> {
    const options = httpServerOptionsFromSettings(settings, () => createMcpSession(productAuthOf));
    const running = await startHttpServer(options);

    log.info(
        `MCP server listening on ${running.url} (${settings.MCP_HTTP_AUTH} sign-in); every user signs in with their own Veeam account`,
    );
    if (settings.MCP_HTTP_AUTH === 'oauth' && settings.MCP_HTTP_TOKEN_SECRET === undefined) {
        log.warn('MCP_HTTP_TOKEN_SECRET is not set: OAuth sign-ins end when the server restarts and do not work across replicas');
    }

    let stopping = false;
    const shutdown = (signal: string) => {
        if (stopping) {
            return;
        }
        stopping = true;
        log.info(`${signal} received; closing ${running.sessionCount} HTTP session(s)`);
        void running.close().then(() => process.exit(0));
    };

    process.once('SIGINT', () => shutdown('SIGINT'));
    process.once('SIGTERM', () => shutdown('SIGTERM'));
}

switch (settings.MCP_TRANSPORT) {
    case 'stdio':
        await serveStdio();
        break;
    case 'http':
        await serveHttp();
        break;
}
