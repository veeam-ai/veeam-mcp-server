/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

const invalidTypes = ['string', 'number', 'undefined', 'boolean', 'function'];

export function isNotObject(value: unknown) {
    return value === null || Number.isNaN(value) || invalidTypes.includes(typeof value);
}
