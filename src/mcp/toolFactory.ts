/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { ChatbotMode, ServiceInfo } from '@/common/types';
import { createProductRestClient } from '@/product/ProductClientFactory';
import { getProductCode, getProductName } from '@/config/settings';
import { resolveActionsConfig } from '@/actions/resolveActionsConfig';
import { log } from '@/utils/logger';

export interface ToolConfig {
    title: string;
    description: string;
    /** Mode used in the Veeam Intelligence handshake. */
    mode: ChatbotMode;
    /** Mode reported by the product. */
    productMode: ChatbotMode;
    actionsEnabled: boolean;
    serviceInfo: ServiceInfo;
}

export async function createTool(): Promise<ToolConfig> {
    const productRestClient = createProductRestClient();
    const serviceInfo = await productRestClient.getServiceInfo();
    const actions = resolveActionsConfig(serviceInfo, getProductCode());

    log.info(
        `${serviceInfo.productName} ${serviceInfo.productVersion}: product chatbot mode "${actions.productMode}", effective mode "${actions.effectiveMode}"`,
    );
    actions.notes.forEach((note) => log.info(note));

    return createToolMetadata(actions.effectiveMode, actions.productMode, actions.actionsEnabled, serviceInfo);
}

export function createToolMetadata(
    mode: ChatbotMode,
    productMode: ChatbotMode,
    actionsEnabled: boolean,
    serviceInfo: ServiceInfo,
): ToolConfig {
    const productName = getProductName();

    let description =
        'Use this tool for any request involving Veeam operational knowledge or data, including troubleshooting Veeam products, ' +
        `displaying Veeam jobs, alerts, or other product data, and answering questions about Veeam documentation or procedures for ${productName}. ` +
        "It returns authoritative Veeam product guidance backed by internal telemetry and documented procedures. Preserve the user's wording; " +
        'forward questions verbatim to ensure intent is not altered. Responses arrive as JSON with top-level "message" and "artifacts" fields; ' +
        'when an artifact has type "dataframe", treat it as tabular output and render it as a table.';

    if (actionsEnabled) {
        description +=
            ' Veeam Intelligence may also propose product actions (for example starting or disabling a job). When the response contains ' +
            '"pending_action", the action has NOT run yet: show the user the title, description, the exact request (method, path, body) and ' +
            "Veeam Intelligence's own description, ask for explicit approval, and only then call veeam-confirm-action with the action_id and " +
            "approve=true, or approve=false if the user declines. Never approve on the user's behalf and never answer a confirmation by calling " +
            'this tool again. The "actions" field lists actions that were executed, declined, rejected by policy or expired during the answer.';
    }

    return {
        title: 'Answer Veeam Question',
        description,
        mode,
        productMode,
        actionsEnabled,
        serviceInfo,
    };
}
