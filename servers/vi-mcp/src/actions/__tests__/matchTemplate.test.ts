/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { describe, it, expect } from '@jest/globals';
import { matchTemplate } from '../matchTemplate';

describe('matchTemplate', () => {
    it('matches identical paths', () => {
        expect(matchTemplate('/api/v1/jobs', '/api/v1/jobs')).toBe(true);
    });

    it('matches :param segments against any non-empty segment', () => {
        expect(matchTemplate('/api/v1/jobs/:id/start', '/api/v1/jobs/e9b6424b-1/start')).toBe(true);
    });

    it('rejects an empty segment for :param', () => {
        expect(matchTemplate('/api/v1/jobs/:id/start', '/api/v1/jobs//start')).toBe(false);
    });

    it('rejects different segment counts', () => {
        expect(matchTemplate('/api/v1/jobs/:id', '/api/v1/jobs/1/start')).toBe(false);
        expect(matchTemplate('/api/v1/jobs/:id/start', '/api/v1/jobs/1')).toBe(false);
    });

    it('rejects literal mismatches and is case-sensitive', () => {
        expect(matchTemplate('/api/v1/jobs/:id/start', '/api/v1/jobs/1/stop')).toBe(false);
        expect(matchTemplate('/api/v1/Jobs', '/api/v1/jobs')).toBe(false);
    });
});
