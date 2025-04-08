/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { describe, it, expect } from '@jest/globals';
import { answerQuestion } from '@/tools/answerQuestion';

describe('E2E: Validate answer test question', () => {
    it(
        'should answer question',
        async () => {
            // This test validates that the debug.ts entry point runs till the end
            const question = 'Show me list of Veeam One alerts with severity Critical and Warning';

            const mockLog = (message: string) => {
                console.log(message);
            };

            // Execute the main logic from debug.ts
            const result = await answerQuestion(question, mockLog);

            // Validate that the function completed successfully
            expect(result).toBeDefined();
            expect(result).toHaveProperty('message');
            expect(result).toHaveProperty('artifacts');

            console.log('Test completed successfully');
            console.log('Answer:', result);
        },
        60 * 60 * 1000,
    ); // 1 hour timeout for E2E test - in case used for debugging
});
