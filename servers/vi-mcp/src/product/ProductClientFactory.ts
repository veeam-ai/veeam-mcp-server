/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { ProductRestClient } from './ProductRestClient';
import { VoneRestClient, VspcRestClient, VbrRestClient } from './clients';
import { ProductRestClientConfig, ProductUserAuth } from './clients/types';
import { settings, getProductCode } from '@/config/settings';

export function productAuthFromSettings(): ProductUserAuth | undefined {
    if (settings.ADMIN_USERNAME === undefined || settings.ADMIN_PASSWORD === undefined) {
        return undefined;
    }
    return { kind: 'password', credentials: { username: settings.ADMIN_USERNAME, password: settings.ADMIN_PASSWORD } };
}

export function createProductRestClient(auth: ProductUserAuth | undefined): ProductRestClient {
    const productCode = getProductCode();

    const productRestClientConfig: ProductRestClientConfig = {
        baseURL: settings.WEB_URL,
        auth,
        acceptSelfSignedCert: settings.ACCEPT_SELF_SIGNED_CERT,
    };

    switch (productCode) {
        case 'vone':
            return new VoneRestClient(productRestClientConfig);
        case 'vspc':
            return new VspcRestClient(productRestClientConfig);
        case 'vbr':
            return new VbrRestClient(productRestClientConfig);
    }
}
