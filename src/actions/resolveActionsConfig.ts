/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { ChatbotMode, ServiceInfo } from '@/common/types';
import { FetchGate } from './fetchGate';
import { FetchPolicy, getFetchPolicy } from './policies';

export interface ActionsConfig {
    /** Mode reported by the product. */
    productMode: ChatbotMode;
    /** Mode the MCP server actually uses in the Veeam Intelligence handshake. */
    effectiveMode: ChatbotMode;
    /** `true` when actions can be proposed and will be gated for user confirmation. */
    actionsEnabled: boolean;
    policy?: FetchPolicy;
    fetchGate: FetchGate;
    /** Human-readable explanation of why the effective mode differs from the product mode. */
    notes: string[];
}

/**
 * Decide the handshake mode and the action policy for this process from the product's chatbot mode.
 * The product administrator enables actions by selecting `AdvancedWithActions` on the Veeam server;
 * the MCP server follows that choice as long as it has a fetch policy for the product/version, and
 * every state-changing call still requires the user's confirmation. Without a policy the mode is
 * downgraded to `Advanced` so Veeam Intelligence never proposes actions the server cannot gate.
 */
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
