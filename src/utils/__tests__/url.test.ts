/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { describe, it, expect } from '@jest/globals';
import { mergeUrlParts } from '../url';

describe('url utilities', () => {
  describe('mergeUrlParts', () => {
    it('should merge base URL and suffix with single slash', () => {
      const result = mergeUrlParts('https://example.com', 'api/v1');
      expect(result).toBe('https://example.com/api/v1');
    });

    it('should keep single slash', () => {
      const result = mergeUrlParts('https://example.com/', 'api/v1');
      expect(result).toBe('https://example.com/api/v1');
    });

    it('should keep single slash', () => {
      const result = mergeUrlParts('https://example.com', '/api/v1');
      expect(result).toBe('https://example.com/api/v1');
    });

    it('should keep single slash', () => {
      const result = mergeUrlParts('https://example.com/', '/api/v1');
      expect(result).toBe('https://example.com/api/v1');
    });

    it('should remove multiple slashes from base URL', () => {
      const result = mergeUrlParts('https://example.com///', 'api/v1');
      expect(result).toBe('https://example.com/api/v1');
    });

    it('should remove multiple slashes from base URL', () => {
      const result = mergeUrlParts('https://example.com', '///api/v1');
      expect(result).toBe('https://example.com/api/v1');
    });
  });
});
