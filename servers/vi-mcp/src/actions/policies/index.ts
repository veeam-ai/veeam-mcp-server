/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { FetchPolicyRegistry } from '../types';
import { isVersionAtLeast } from '../version';
import { vbr_13_1_FetchPolicies } from './vbr_13.1';
import { vbr_13_1_FetchPolicyTexts } from './vbr_13.1.texts';

export interface FetchPolicy {
    registry: FetchPolicyRegistry;
    texts: Record<string, string>;
    /** Human-readable label of the registry that was selected, for logs. */
    label: string;
}

/** Minimum product version that offers Veeam Intelligence actions, per product code. */
export const ACTIONS_MIN_VERSION: Partial<Record<string, string>> = {
    vbr: '13.1',
};

/**
 * Resolve the fetch policy for a product/version. Returns `undefined` when the product has no
 * actions support (the gate then rejects every non-GET call).
 * VBR 13.1 and 13.2 ship identical policies, so the 13.1 registry is used for 13.1+.
 */
export function getFetchPolicy(productCode: string, productVersion: string): FetchPolicy | undefined {
    const minVersion = ACTIONS_MIN_VERSION[productCode];
    if (minVersion === undefined || !isVersionAtLeast(productVersion, minVersion)) {
        return undefined;
    }

    switch (productCode) {
        case 'vbr':
            return { registry: vbr_13_1_FetchPolicies, texts: vbr_13_1_FetchPolicyTexts, label: 'vbr_13.1' };
        default:
            return undefined;
    }
}
