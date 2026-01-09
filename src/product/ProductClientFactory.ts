/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { PRODUCT_NAMES, ProductCode } from '../common/types';
import { ProductClient, VoneClient, VspcClient, VbrClient } from './clients';
import { ProductApiTransport, ProductApiTransportConfig } from './ProductApiTransport';
import { mergeUrlParts } from '@/utils/url';

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
    throw new Error(`Unsupported product code: ${productCode as string}`);
}

function createProductApiTransport(productCode: ProductCode): ProductApiTransport {
    const baseURL = process.env.WEB_URL || '';
    const username = process.env.ADMIN_USERNAME || '';
    const password = process.env.ADMIN_PASSWORD || '';

    if (!baseURL || !username || !password) {
        throw new Error('Missing required environment variables: PRODUCT_NAME, WEB_URL, ADMIN_USERNAME, ADMIN_PASSWORD');
    }

    const authUrlSuffix = getProductAuthUrlSuffix(productCode);
    const productApiTransportConfig: ProductApiTransportConfig = {
        baseURL,
        username,
        password,
        authUrl: mergeUrlParts(baseURL, authUrlSuffix),
    };

    const apiTransport = new ProductApiTransport(productApiTransportConfig);
    return apiTransport;
}

export function createProductClient(): ProductClient {
    if (!process.env.PRODUCT_NAME || !process.env.WEB_URL || !process.env.ADMIN_USERNAME || !process.env.ADMIN_PASSWORD) {
        throw new Error('Missing required environment variables: PRODUCT_NAME, WEB_URL, ADMIN_USERNAME, ADMIN_PASSWORD');
    }

    const productCode = getProductCode();
    const apiTransport = createProductApiTransport(productCode);

    switch (productCode) {
        case 'vone':
            return new VoneClient(apiTransport);
        case 'vspc':
            return new VspcClient(apiTransport);
        case 'vbr':
            return new VbrClient(apiTransport);
    }
}
