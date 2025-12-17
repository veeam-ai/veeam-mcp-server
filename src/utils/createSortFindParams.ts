/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { isNotObject } from './isNotObject';

export const createSortFindParams = (params: Record<string, unknown>) => {
    const queryParams = new URLSearchParams();
    const keys = Object.keys(params);

    keys.forEach((key) => {
        if (isNotObject(params[key])) {
            queryParams.append(key, String(params[key]));
        } else {
            queryParams.append(key, JSON.stringify(params[key]));
        }
    });

    return queryParams;
};
