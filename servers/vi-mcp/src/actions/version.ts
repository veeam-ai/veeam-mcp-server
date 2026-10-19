/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

/** Parse a dotted product version ("13.1.0.411") into numeric parts; non-numeric tails are ignored. */
export function parseVersion(version: string): number[] {
    return version
        .trim()
        .split('.')
        .map((part) => parseInt(part, 10))
        .filter((part) => !Number.isNaN(part));
}

/** `true` when `version` >= `minimum`, comparing dotted numeric segments (missing segments count as 0). */
export function isVersionAtLeast(version: string, minimum: string): boolean {
    const actual = parseVersion(version);
    const required = parseVersion(minimum);

    if (actual.length === 0) {
        return false;
    }

    const length = Math.max(actual.length, required.length);
    for (let i = 0; i < length; i += 1) {
        const a = actual[i] ?? 0;
        const b = required[i] ?? 0;
        if (a !== b) {
            return a > b;
        }
    }

    return true;
}
