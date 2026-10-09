/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { createMcpSession } from './mcp/session';
import { LOOPBACK_HOSTS, settings } from './config/settings';
import { httpServerOptionsFromSettings, startHttpServer } from './transports/http';
import { log } from './utils/logger';

async function serveStdio(): Promise<void> {
    const { server } = createMcpSession();
    await server.connect(new StdioServerTransport());
    log.info('MCP server started on stdio; the chatbot mode is read from the Veeam product on every request');
}

async function serveHttp(): Promise<void> {
    const options = httpServerOptionsFromSettings(settings, createMcpSession);
    const running = await startHttpServer(options);

    log.info(`MCP server listening on ${running.url}; the chatbot mode is read from the Veeam product on every request`);
    if (options.authToken === undefined) {
        log.warn('MCP_HTTP_AUTH_TOKEN is not set: any local process can use this endpoint');
    }
    if (options.tls === undefined && !LOOPBACK_HOSTS.includes(options.host.toLowerCase())) {
        log.warn('TLS is not configured: the bearer token travels in clear text unless a TLS-terminating proxy is in front');
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
