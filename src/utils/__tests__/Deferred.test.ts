/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { describe, it, expect } from '@jest/globals';
import { Deferred } from '../Deferred';

describe('Deferred', () => {
  it('should create a deferred promise', () => {
    const deferred = new Deferred();
    expect(deferred.promise).toBeInstanceOf(Promise);
    expect(typeof deferred.resolve).toBe('function');
    expect(typeof deferred.reject).toBe('function');
  });

  it('should resolve the promise when resolve is called', async () => {
    const deferred = new Deferred<string>();
    const testValue = 'test value';

    deferred.resolve(testValue);

    const result = await deferred.promise;
    expect(result).toBe(testValue);
  });

  it('should reject the promise when reject is called', async () => {
    const deferred = new Deferred<string>();
    const testError = new Error('test error');

    deferred.reject(testError);

    await expect(deferred.promise).rejects.toThrow('test error');
  });

  it('should handle void type resolution', async () => {
    const deferred = new Deferred<void>();

    deferred.resolve();

    await expect(deferred.promise).resolves.toBeUndefined();
  });

  it('should allow resolving with a promise', async () => {
    const deferred = new Deferred<number>();
    const promiseValue = Promise.resolve(42);

    deferred.resolve(promiseValue);

    const result = await deferred.promise;
    expect(result).toBe(42);
  });

  it('should handle multiple awaits on the same promise', async () => {
    const deferred = new Deferred<number>();
    const testValue = 123;

    deferred.resolve(testValue);

    const result1 = await deferred.promise;
    const result2 = await deferred.promise;
    const result3 = await deferred.promise;

    expect(result1).toBe(testValue);
    expect(result2).toBe(testValue);
    expect(result3).toBe(testValue);
  });

  it('should handle resolve with complex objects', async () => {
    interface TestData {
      id: number;
      name: string;
      nested: { value: boolean };
    }

    const deferred = new Deferred<TestData>();
    const testData: TestData = {
      id: 1,
      name: 'test',
      nested: { value: true }
    };

    deferred.resolve(testData);

    const result = await deferred.promise;
    expect(result).toEqual(testData);
  });

  it('should handle reject with different error types', async () => {
    const deferred1 = new Deferred<string>();
    const deferred2 = new Deferred<string>();
    const deferred3 = new Deferred<string>();

    deferred1.reject('string error');
    deferred2.reject(new Error('Error object'));
    deferred3.reject({ code: 'ERR_CUSTOM', message: 'Custom error' });

    await expect(deferred1.promise).rejects.toBe('string error');
    await expect(deferred2.promise).rejects.toThrow('Error object');
    await expect(deferred3.promise).rejects.toEqual({ code: 'ERR_CUSTOM', message: 'Custom error' });
  });

  it('should allow attaching handlers before resolution', async () => {
    const deferred = new Deferred<number>();
    const results: number[] = [];

    deferred.promise.then(value => results.push(value));
    deferred.promise.then(value => results.push(value * 2));

    deferred.resolve(10);

    await deferred.promise;
    
    // Give a tick for all then handlers to execute
    await new Promise(resolve => setTimeout(resolve, 0));

    expect(results).toContain(10);
    expect(results).toContain(20);
  });
});
