/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { describe, it, expect, beforeAll } from '@jest/globals';
import { ChatbotMode } from '@/common/types';

// Point at an unreachable backend (the reserved `.invalid` TLD never resolves,
// per RFC 2606) so the startup getServiceInfo() call fails — exercising the
// graceful fallback path directly, without module mocking. Set before the
// dynamic import below so settings parse succeeds.
process.env.PRODUCT_NAME = 'vbr';
process.env.WEB_URL = 'https://vbr.unreachable.invalid:9419';
process.env.ADMIN_USERNAME = 'x';
process.env.ADMIN_PASSWORD = 'x';
process.env.ACCEPT_SELF_SIGNED_CERT = 'true';

let createTool: typeof import('../toolFactory').createTool;

beforeAll(async () => {
    ({ createTool } = await import('../toolFactory'));
});

describe('createTool — graceful startup', () => {
    it('does not throw when the Veeam product is unreachable at startup', async () => {
        // Before this fix, an unreachable backend threw here and crashed the
        // whole MCP server at boot. Now it resolves with default metadata so
        // the server starts, advertises its tool, and defers auth to call time.
        const cfg = await createTool();
        expect(cfg.mode).toBe(ChatbotMode.Advanced);
        expect(cfg.title).toBe('Answer Veeam Question');
        expect(cfg.description).toContain('Veeam');
    });
});
