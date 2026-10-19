/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { describe, it, expect } from '@jest/globals';
import { answerQuestion, confirmAction, listPendingActions } from '@/tools/answerQuestion';

const BUCKET_JOB_ID = '28f489c4-e0f1-4240-8585-54149759b420';

describe('E2E: start bucket-job', () => {
    it(
        'parks the action, verifies it, then approves it',
        async () => {
            // No confirmationHandler -> the turn parks as pending_action (the two-step flow).
            const first = await answerQuestion('Start the backup job bucket-job.');
            const pending = first.pending_action;

            console.log('\n===== STEP 1 message:\n' + first.message);
            console.log('===== STEP 1 pending_action:', JSON.stringify(pending, null, 1));
            console.log('===== registry:', JSON.stringify(listPendingActions().map((p) => p.action_id)));

            if (pending === undefined) {
                console.log('!!! No action proposed - nothing to approve.');
                return;
            }

            // Guard: only approve the exact call we expect.
            const expected = pending.method === 'POST' && pending.path?.includes(BUCKET_JOB_ID) && pending.path?.endsWith('/start');
            console.log('===== guard: expected call?', expected);
            if (!expected) {
                console.log('!!! Unexpected call, declining:', pending.method, pending.path);
                const declined = await confirmAction(pending.action_id, false);
                console.log('===== declined:', JSON.stringify(declined.actions));
                return;
            }

            const second = await confirmAction(pending.action_id, true);
            console.log('\n===== STEP 2 message:\n' + second.message);
            console.log('===== STEP 2 actions:', JSON.stringify(second.actions, null, 1));
            console.log('===== STEP 2 artifacts:', JSON.stringify(second.artifacts.map((a) => ({ id: a.id, type: a.type }))));

            expect(second.actions.length).toBeGreaterThan(0);
        },
        10 * 60 * 1000,
    );
});
