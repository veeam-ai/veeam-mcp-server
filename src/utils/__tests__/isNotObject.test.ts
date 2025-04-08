/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { describe, it, expect } from '@jest/globals';
import { isNotObject } from '../isNotObject';

describe('isNotObject', () => {
    it('should return true for strings', () => {
        expect(isNotObject('hello')).toBe(true);
        expect(isNotObject('')).toBe(true);
    });

    it('should return true for numbers', () => {
        expect(isNotObject(42)).toBe(true);
        expect(isNotObject(0)).toBe(true);
        expect(isNotObject(-1)).toBe(true);
        expect(isNotObject(3.14)).toBe(true);
    });

    it('should return true for undefined', () => {
        expect(isNotObject(undefined)).toBe(true);
    });

    it('should return true for booleans', () => {
        expect(isNotObject(true)).toBe(true);
        expect(isNotObject(false)).toBe(true);
    });

    it('should return true for functions', () => {
        expect(isNotObject(() => {})).toBe(true);
        expect(isNotObject(function () {})).toBe(true);
    });

    it('should return true for null', () => {
        expect(isNotObject(null)).toBe(true);
    });

    it('should return true for NaN', () => {
        expect(isNotObject(NaN)).toBe(true);
    });

    it('should return false for objects', () => {
        expect(isNotObject({})).toBe(false);
        expect(isNotObject({ key: 'value' })).toBe(false);
    });

    it('should return false for arrays', () => {
        expect(isNotObject([])).toBe(false);
        expect(isNotObject([1, 2, 3])).toBe(false);
    });

    it('should return false for Date objects', () => {
        expect(isNotObject(new Date())).toBe(false);
    });

    it('should return false for RegExp objects', () => {
        expect(isNotObject(/test/)).toBe(false);
    });

    it('should return false for Error objects', () => {
        expect(isNotObject(new Error('test'))).toBe(false);
    });

    it('should return false for custom class instances', () => {
        class CustomClass {}
        expect(isNotObject(new CustomClass())).toBe(false);
    });
});
