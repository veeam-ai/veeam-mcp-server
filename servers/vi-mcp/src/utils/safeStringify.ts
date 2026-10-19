/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

const safeStringify = (obj: any): string => {
    try {
        return JSON.stringify(obj);
    } catch {
        return '';
    }
};

export default safeStringify;
