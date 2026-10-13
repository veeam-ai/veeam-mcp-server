/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { describe, it, expect, beforeAll, jest } from '@jest/globals';
import type { IncomingMessage } from 'node:http';
import type { ProductCredentials, ProductUserToken } from '@/product';

process.env.PRODUCT_NAME = 'vbr';
process.env.WEB_URL = 'https://vbr.example.test:9419';
process.env.ADMIN_USERNAME = 'x';
process.env.ADMIN_PASSWORD = 'x';

let BasicAuthenticator: typeof import('../basicAuth').BasicAuthenticator;
let LoginThrottle: typeof import('../loginThrottle').LoginThrottle;
let productAuthOf: typeof import('../identity').productAuthOf;

beforeAll(async () => {
    ({ BasicAuthenticator } = await import('../basicAuth'));
    ({ LoginThrottle } = await import('../loginThrottle'));
    ({ productAuthOf } = await import('../identity'));
});

function request(username: string, password: string): IncomingMessage {
    return { headers: { authorization: `Basic ${Buffer.from(`${username}:${password}`).toString('base64')}` } } as IncomingMessage;
}

describe('BasicAuthenticator', () => {
    it('renews a token once for parallel calls and hands the new token to later requests', async () => {
        let logins = 0;
        const requestUserToken = jest.fn(async (_credentials: ProductCredentials): Promise<ProductUserToken> => ({
            accessToken: `token-${++logins}`,
            expiresAt: Date.now() + 900_000,
        }));
        const authenticator = new BasicAuthenticator({ requestUserToken }, new LoginThrottle());

        const auth = productAuthOf(await authenticator.authenticate(request('alice', 'pw'), '10.0.0.1'));
        if (auth?.kind !== 'token' || auth.renew === undefined) {
            throw new Error('expected a renewable token');
        }
        const renewed = await Promise.all([auth.renew(auth.token), auth.renew(auth.token)]);
        const later = productAuthOf(await authenticator.authenticate(request('alice', 'pw'), '10.0.0.1'));

        expect(renewed.map((token) => token.accessToken)).toEqual(['token-2', 'token-2']);
        expect(later).toMatchObject({ token: { accessToken: 'token-2' } });
        expect(requestUserToken).toHaveBeenCalledTimes(2);
    });
});
