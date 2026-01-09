/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { PRODUCT_NAMES, ProductCode } from '@/common/types';
import { ProductRestClient } from './ProductRestClient';
import { VoneRestClient, VspcRestClient, VbrRestClient } from './clients';
import { mergeUrlParts } from '@/utils/url';
import { ProductRestClientConfig } from './clients/types';

export function createProductRestClient(): ProductRestClient {
    // TODO: to separate function - prevalidation of env vars
    if (!process.env.PRODUCT_NAME || !process.env.WEB_URL || !process.env.ADMIN_USERNAME || !process.env.ADMIN_PASSWORD) {
        throw new Error('Missing required environment variables: PRODUCT_NAME, WEB_URL, ADMIN_USERNAME, ADMIN_PASSWORD');
    }

    const productCode = getProductCode();

    const baseURL = process.env.WEB_URL || '';
    const username = process.env.ADMIN_USERNAME || '';
    const password = process.env.ADMIN_PASSWORD || '';

    if (!baseURL || !username || !password) {
        throw new Error('Missing required environment variables: PRODUCT_NAME, WEB_URL, ADMIN_USERNAME, ADMIN_PASSWORD');
    }

    const authUrlSuffix = getProductAuthUrlSuffix(productCode);
    const productRestClientConfig: ProductRestClientConfig = {
        baseURL,
        username,
        password,
        authUrl: mergeUrlParts(baseURL, authUrlSuffix),
        acceptSelfSignedCert: process.env.ACCEPT_SELF_SIGNED_CERT === 'true',
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

export function getProductCode(): ProductCode {
    const productCode = process.env.PRODUCT_NAME?.trim().toLowerCase() || '';
    if (!productCode) {
        throw new Error('PRODUCT_NAME environment variable is required. Valid values are: ' + Object.keys(PRODUCT_NAMES).join(', '));
    }

    if (productCode in PRODUCT_NAMES) {
        return productCode as ProductCode;
    }

    throw new Error(
        `PRODUCT_NAME environment variable has unexpected value ${productCode}. Valid values are: ` +
            Object.keys(PRODUCT_NAMES).join(', ') +
            '. Verify mcp server configuration.',
    );
}

function getProductAuthUrlSuffix(productCode: ProductCode): string {
    switch (productCode) {
        case 'vone':
            return '/api/token';
        case 'vspc':
            return '/api/v3/token';
        case 'vbr':
            return '/private-api/oauth2/token';
    }
}
