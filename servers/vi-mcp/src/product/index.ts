/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

export { createProductRestClient, productAuthFromSettings } from './ProductClientFactory';
export { ProductRestClient } from './ProductRestClient';
export type { ProductCredentials, ProductUserAuth, ProductUserToken } from './clients/types';
export { USER_TOKEN_EXPIRY_SKEW_MS } from './clients/types';
