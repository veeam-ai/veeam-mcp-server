/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

export interface AuthRequestConfig {
    cachePolicy: 'NoCache' | 'CacheAndReturn' | 'ReturnFromCacheOrCreate';
    cacheTtlSec: number;
    requestTemplate: {
        product_name: string;
        product_version: string;
        license: string;
        user_hash: string;
    };
}
