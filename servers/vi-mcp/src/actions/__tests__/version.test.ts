/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { describe, it, expect } from '@jest/globals';
import { isVersionAtLeast, parseVersion } from '../version';

describe('parseVersion', () => {
    it('parses dotted numeric versions', () => {
        expect(parseVersion('13.1.0.411')).toEqual([13, 1, 0, 411]);
    });

    it('drops non-numeric parts', () => {
        expect(parseVersion('13.1-beta')).toEqual([13, 1]);
        expect(parseVersion('unknown')).toEqual([]);
    });
});

describe('isVersionAtLeast', () => {
    it('accepts equal and newer versions', () => {
        expect(isVersionAtLeast('13.1', '13.1')).toBe(true);
        expect(isVersionAtLeast('13.1.0.411', '13.1')).toBe(true);
        expect(isVersionAtLeast('13.2.0.1', '13.1')).toBe(true);
        expect(isVersionAtLeast('14.0', '13.1')).toBe(true);
    });

    it('rejects older versions', () => {
        expect(isVersionAtLeast('13.0.1.1071', '13.1')).toBe(false);
        expect(isVersionAtLeast('12.3', '13.1')).toBe(false);
        expect(isVersionAtLeast('13', '13.1')).toBe(false);
    });

    it('rejects unparsable versions', () => {
        expect(isVersionAtLeast('', '13.1')).toBe(false);
        expect(isVersionAtLeast('n/a', '13.1')).toBe(false);
    });
});
