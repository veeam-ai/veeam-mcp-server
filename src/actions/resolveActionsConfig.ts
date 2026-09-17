/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { ChatbotMode, ServiceInfo } from '@/common/types';
import { FetchGate } from './fetchGate';
import { FetchPolicy, getFetchPolicy } from './policies';

export interface ActionsConfig {
    productMode: ChatbotMode;
    effectiveMode: ChatbotMode;
    actionsEnabled: boolean;
    policy?: FetchPolicy;
    fetchGate: FetchGate;
    notes: string[];
}

export function resolveActionsConfig(serviceInfo: ServiceInfo, productCode: string): ActionsConfig {
    const productMode = serviceInfo.chatbotMode;
    const notes: string[] = [];

    if (productMode !== ChatbotMode.AdvancedWithActions) {
        return {
            productMode,
            effectiveMode: productMode,
            actionsEnabled: false,
            fetchGate: new FetchGate(undefined),
            notes,
        };
    }

    const policy = getFetchPolicy(productCode, serviceInfo.productVersion);
    if (policy === undefined) {
        notes.push(
            `product offers AdvancedWithActions but the MCP server has no action policy for "${productCode}" version "${serviceInfo.productVersion}"; using Advanced mode (read-only)`,
        );
        return {
            productMode,
            effectiveMode: ChatbotMode.Advanced,
            actionsEnabled: false,
            fetchGate: new FetchGate(undefined),
            notes,
        };
    }

    notes.push(`actions enabled with policy "${policy.label}"; state-changing calls require user confirmation`);
    return {
        productMode,
        effectiveMode: ChatbotMode.AdvancedWithActions,
        actionsEnabled: true,
        policy,
        fetchGate: new FetchGate(policy.registry, policy.texts),
        notes,
    };
}
