/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { ChatbotMode } from '@/common/types';
import { createProductRestClient } from '@/product/ProductClientFactory';
import { getProductName } from '@/config/settings';

interface ToolConfig {
    title: string;
    description: string;
    mode: ChatbotMode;
}

export async function createTool(): Promise<ToolConfig> {
    const productRestClient = createProductRestClient();
    const serviceInfo = await productRestClient.getServiceInfo();

    return createToolMetadata(serviceInfo.chatbotMode);
}

function createToolMetadata(mode: ChatbotMode): ToolConfig {
    const productName = getProductName();

    const advancedModeToolDescription =
        'Use this tool for any request involving Veeam operational knowledge or data—including troubleshooting Veeam products,' +
        `displaying Veeam jobs, alerts, or other product data, and answering questions about Veeam documentation or procedures for ${productName}.` +
        `It returns authoritative Veeam product guidance backed by internal telemetry and documented procedures. Preserve the user's wording;` +
        'forward questions verbatim to ensure intent is not altered. Responses arrive as JSON with top-level "message" and "artifacts" fields;' +
        'when an artifact has type "dataframe," treat it as tabular output and render it as a table.';

    return {
        title: 'Answer Veeam Question',
        description: advancedModeToolDescription,
        mode: mode,
    };
}
