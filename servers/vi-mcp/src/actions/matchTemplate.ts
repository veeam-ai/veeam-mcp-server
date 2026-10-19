/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

/**
 * Segment-wise path template match. `:param` segments match any single non-empty segment.
 * Ported from veeam-intelligence `hostFetchGateService/matchTemplate.ts` (no regex, no wildcards).
 */
export const matchTemplate = (pathPattern: string, endpointPath: string): boolean => {
    const patternSegments = pathPattern.split('/');
    const pathSegments = endpointPath.split('/');

    if (patternSegments.length !== pathSegments.length) {
        return false;
    }

    for (let i = 0; i < patternSegments.length; i += 1) {
        const patternSegment = patternSegments[i];
        const pathSegment = pathSegments[i];

        if (patternSegment.startsWith(':')) {
            if (pathSegment.length === 0) {
                return false;
            }
            continue;
        }

        if (patternSegment !== pathSegment) {
            return false;
        }
    }

    return true;
};
