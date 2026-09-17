/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { describe, it, expect } from '@jest/globals';
import { FetchGate } from '../fetchGate';
import { getFetchPolicy } from '../policies';
import { vbr_13_1_FetchPolicies } from '../policies/vbr_13.1';
import { vbr_13_1_FetchPolicyTexts } from '../policies/vbr_13.1.texts';

const gate = new FetchGate(vbr_13_1_FetchPolicies, vbr_13_1_FetchPolicyTexts);

describe('FetchGate with the VBR 13.1 policy', () => {
    it('always allows GET', () => {
        expect(gate.decide('GET', '/api/v1/jobs')).toEqual({ kind: 'allowed' });
        expect(gate.decide('GET', '/anything/at/all')).toEqual({ kind: 'allowed' });
    });

    it('allows whitelisted POST reads silently', () => {
        expect(gate.decide('POST', '/api/v1/acl')).toEqual({ kind: 'allowed' });
        expect(gate.decide('POST', '/api/v1/backupInfrastructure/managedServers/abc/rescan')).toEqual({ kind: 'allowed' });
    });

    it('requires confirmation for checklist actions and resolves the texts', () => {
        const decision = gate.decide('POST', '/api/v1/jobs/e9b6424b-0000/start');
        expect(decision.kind).toBe('confirm');
        if (decision.kind === 'confirm') {
            expect(decision.title).toBe('Start this backup job?');
            expect(decision.description).toContain('Veeam Intelligence wants to start the selected job');
        }
    });

    it('ignores a query string when matching', () => {
        expect(gate.decide('POST', '/api/v1/jobs/abc/disable?force=true').kind).toBe('confirm');
    });

    it('rejects non-GET calls that match neither list', () => {
        const decision = gate.decide('DELETE', '/api/v1/jobs/abc');
        expect(decision.kind).toBe('rejected');
        if (decision.kind === 'rejected') {
            expect(decision.reason).toContain('not allowed');
        }
        expect(gate.decide('POST', '/api/v1/jobs').kind).toBe('rejected');
    });

    it('falls back to the key when a text is missing', () => {
        const bareGate = new FetchGate(vbr_13_1_FetchPolicies);
        const decision = bareGate.decide('POST', '/api/v1/jobs/abc/start');
        expect(decision).toEqual({ kind: 'confirm', title: 'start_job_title', description: 'start_job_description' });
    });
});

describe('FetchGate without a registry', () => {
    const noPolicy = new FetchGate(undefined);

    it('allows GET but rejects every state-changing call', () => {
        expect(noPolicy.decide('GET', '/api/v1/jobs')).toEqual({ kind: 'allowed' });
        expect(noPolicy.decide('POST', '/api/v1/acl').kind).toBe('rejected');
        expect(noPolicy.decide('POST', '/api/v1/jobs/abc/start').kind).toBe('rejected');
    });
});

describe('getFetchPolicy', () => {
    it('returns the VBR 13.1 policy for 13.1 and newer', () => {
        expect(getFetchPolicy('vbr', '13.1.0.411')?.label).toBe('vbr_13.1');
        expect(getFetchPolicy('vbr', '13.2.0.10')?.label).toBe('vbr_13.1');
        expect(getFetchPolicy('vbr', '14.0')?.label).toBe('vbr_13.1');
    });

    it('returns nothing for older VBR or other products', () => {
        expect(getFetchPolicy('vbr', '13.0.1.1071')).toBeUndefined();
        expect(getFetchPolicy('vone', '13.1')).toBeUndefined();
        expect(getFetchPolicy('vspc', '9.4')).toBeUndefined();
    });

    it('ships texts for every checklist entry', () => {
        for (const entry of vbr_13_1_FetchPolicies.checklist) {
            expect(vbr_13_1_FetchPolicyTexts[entry.titleKey]).toBeDefined();
            expect(vbr_13_1_FetchPolicyTexts[entry.descriptionKey]).toBeDefined();
        }
    });
});
