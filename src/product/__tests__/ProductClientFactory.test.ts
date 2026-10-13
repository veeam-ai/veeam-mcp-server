/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { describe, it, expect, beforeAll, jest } from '@jest/globals';

// `@/config/settings` validates process.env at import time, so env is set before the dynamic import.
process.env.PRODUCT_NAME = 'vspc';
process.env.WEB_URL = 'http://127.0.0.1:9/';
process.env.ADMIN_USERNAME = 'admin';
process.env.ADMIN_PASSWORD = 'admin-password';

let factory: typeof import('../ProductClientFactory');

beforeAll(async () => {
    factory = await import('../ProductClientFactory');
});

describe('createProductRestClient', () => {
    it('never falls back to the configured admin account when a caller has no Veeam identity', async () => {
        const consoleError = jest.spyOn(console, 'error').mockImplementation(() => {});

        await expect(factory.createProductRestClient(undefined).getServiceInfo()).rejects.toThrow(/No Veeam credentials/);

        consoleError.mockRestore();
    });

    it('uses the configured account only when stdio asks for it explicitly', () => {
        expect(factory.productAuthFromSettings()).toEqual({
            kind: 'password',
            credentials: { username: 'admin', password: 'admin-password' },
        });
    });
});
