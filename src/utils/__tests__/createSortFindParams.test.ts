/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { describe, it, expect } from '@jest/globals';
import { createSortFindParams } from '../createSortFindParams';

describe('createSortFindParams', () => {
  it('should create URLSearchParams from simple key-value pairs', () => {
    const params = { name: 'John', age: 30 };
    const result = createSortFindParams(params);

    expect(result).toBeInstanceOf(URLSearchParams);
    expect(result.get('name')).toBe('John');
    expect(result.get('age')).toBe('30');
  });

  it('should convert numbers to strings', () => {
    const params = { count: 42, price: 99.99 };
    const result = createSortFindParams(params);

    expect(result.get('count')).toBe('42');
    expect(result.get('price')).toBe('99.99');
  });

  it('should convert booleans to strings', () => {
    const params = { active: true, deleted: false };
    const result = createSortFindParams(params);

    expect(result.get('active')).toBe('true');
    expect(result.get('deleted')).toBe('false');
  });

  it('should stringify objects using JSON.stringify', () => {
    const params = {
      filter: { status: 'active', role: 'admin' }
    };
    const result = createSortFindParams(params);

    expect(result.get('filter')).toBe('{"status":"active","role":"admin"}');
  });

  it('should stringify arrays using JSON.stringify', () => {
    const params = {
      tags: ['typescript', 'nodejs', 'jest']
    };
    const result = createSortFindParams(params);

    expect(result.get('tags')).toBe('["typescript","nodejs","jest"]');
  });

  it('should handle undefined values', () => {
    const params = { name: 'John', value: undefined };
    const result = createSortFindParams(params);

    expect(result.get('name')).toBe('John');
    expect(result.get('value')).toBe('undefined');
  });

  it('should handle null values', () => {
    const params = { name: 'John', value: null };
    const result = createSortFindParams(params);

    expect(result.get('name')).toBe('John');
    expect(result.get('value')).toBe('null');
  });

  it('should handle mixed types in params', () => {
    const params = {
      name: 'John',
      age: 30,
      active: true,
      metadata: { city: 'NYC' },
      tags: ['user', 'admin']
    };
    const result = createSortFindParams(params);

    expect(result.get('name')).toBe('John');
    expect(result.get('age')).toBe('30');
    expect(result.get('active')).toBe('true');
    expect(result.get('metadata')).toBe('{"city":"NYC"}');
    expect(result.get('tags')).toBe('["user","admin"]');
  });

  it('should handle empty object', () => {
    const params = {};
    const result = createSortFindParams(params);

    expect(result).toBeInstanceOf(URLSearchParams);
    expect(result.toString()).toBe('');
  });

  it('should handle nested objects', () => {
    const params = {
      user: {
        profile: {
          name: 'John',
          settings: {
            theme: 'dark'
          }
        }
      }
    };
    const result = createSortFindParams(params);

    expect(result.get('user')).toBe('{"profile":{"name":"John","settings":{"theme":"dark"}}}');
  });

  it('should handle Date objects', () => {
    const date = new Date('2024-01-01T00:00:00.000Z');
    const params = { timestamp: date };
    const result = createSortFindParams(params);

    const timestampValue = result.get('timestamp');
    expect(timestampValue).toContain('2024-01-01');
  });

  it('should handle symbols in object values', () => {
    const params = {
      data: { id: 123, [Symbol('hidden')]: 'value' }
    };
    const result = createSortFindParams(params);

    // Symbols are ignored by JSON.stringify
    expect(result.get('data')).toBe('{"id":123}');
  });

  it('should create properly formatted query string', () => {
    const params = {
      search: 'hello world',
      page: 1,
      limit: 10
    };
    const result = createSortFindParams(params);

    const queryString = result.toString();
    expect(queryString).toContain('search=hello+world');
    expect(queryString).toContain('page=1');
    expect(queryString).toContain('limit=10');
  });
});
