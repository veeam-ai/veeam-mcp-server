/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { ProductRestClient } from './ProductRestClient';
import { VoneRestClient, VspcRestClient, VbrRestClient } from './clients';
import { ProductRestClientConfig } from './clients/types';
import { settings, getProductCode } from '@/config/settings';

export function createProductRestClient(): ProductRestClient {
    const productCode = getProductCode();

    const productRestClientConfig: ProductRestClientConfig = {
        baseURL: settings.WEB_URL,
        username: settings.ADMIN_USERNAME,
        password: settings.ADMIN_PASSWORD,
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
