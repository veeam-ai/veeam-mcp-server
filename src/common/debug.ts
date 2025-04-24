/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

export function debug(): void {
    if (process.env.NODE_ENV === 'development') {
        debugger;
    }
} 