/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { describe, it, expect } from '@jest/globals';
import { resolveActionsConfig } from '../resolveActionsConfig';
import { ChatbotMode, ServiceInfo } from '@/common/types';

const serviceInfo = (chatbotMode: ChatbotMode, productVersion = '13.1.0.411'): ServiceInfo => ({
    chatbotApiUrl: 'https://rest-ai.example.com/v2/',
    chatbotEnabled: true,
    chatbotMode,
    productName: 'Veeam Backup and Replication',
    productVersion,
});

describe('resolveActionsConfig', () => {
    it('follows the product when it offers AdvancedWithActions and a policy exists', () => {
        const config = resolveActionsConfig(serviceInfo(ChatbotMode.AdvancedWithActions), 'vbr');
        expect(config.effectiveMode).toBe(ChatbotMode.AdvancedWithActions);
        expect(config.actionsEnabled).toBe(true);
        expect(config.policy?.label).toBe('vbr_13.1');
        expect(config.fetchGate.decide('POST', '/api/v1/jobs/1/start').kind).toBe('confirm');
    });

    it('accepts newer product versions with the same policy', () => {
        const config = resolveActionsConfig(serviceInfo(ChatbotMode.AdvancedWithActions, '13.2.0.55'), 'vbr');
        expect(config.effectiveMode).toBe(ChatbotMode.AdvancedWithActions);
        expect(config.actionsEnabled).toBe(true);
    });

    it('downgrades to Advanced when no policy exists for the product/version', () => {
        const config = resolveActionsConfig(serviceInfo(ChatbotMode.AdvancedWithActions, '13.0.1.1071'), 'vbr');
        expect(config.productMode).toBe(ChatbotMode.AdvancedWithActions);
        expect(config.effectiveMode).toBe(ChatbotMode.Advanced);
        expect(config.actionsEnabled).toBe(false);
        expect(config.notes.join(' ')).toContain('no action policy');
        expect(config.fetchGate.decide('POST', '/api/v1/jobs/1/start').kind).toBe('rejected');
    });

    it('downgrades to Advanced for products without an action policy', () => {
        const config = resolveActionsConfig(serviceInfo(ChatbotMode.AdvancedWithActions, '13.1'), 'vone');
        expect(config.effectiveMode).toBe(ChatbotMode.Advanced);
        expect(config.actionsEnabled).toBe(false);
    });

    it('keeps Base and Advanced exactly as reported', () => {
        expect(resolveActionsConfig(serviceInfo(ChatbotMode.Base), 'vbr').effectiveMode).toBe(ChatbotMode.Base);

        const advanced = resolveActionsConfig(serviceInfo(ChatbotMode.Advanced), 'vbr');
        expect(advanced.effectiveMode).toBe(ChatbotMode.Advanced);
        expect(advanced.actionsEnabled).toBe(false);
        expect(advanced.notes).toEqual([]);
    });
});
