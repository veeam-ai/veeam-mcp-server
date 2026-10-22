/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import axios from 'axios';
import type { AuthInfo } from '@modelcontextprotocol/sdk/server/auth/types.js';
import type { ProductUserAuth } from '@/product';

export interface CallerIdentity {
    username: string;
    owner: string;
    productAuth: ProductUserAuth;
}

export function identityOf(authInfo: AuthInfo | undefined): CallerIdentity | undefined {
    return authInfo?.extra?.identity as CallerIdentity | undefined;
}

export function productAuthOf(authInfo: AuthInfo | undefined): ProductUserAuth | undefined {
    return identityOf(authInfo)?.productAuth;
}

export function rejectedByProduct(error: unknown): boolean {
    return axios.isAxiosError(error) && (error.response?.status === 400 || error.response?.status === 401);
}

export function describeFailure(error: unknown): string {
    if (axios.isAxiosError(error)) {
        return error.response !== undefined ? `HTTP ${error.response.status}` : (error.code ?? error.message);
    }
    return error instanceof Error ? error.message : String(error);
}
