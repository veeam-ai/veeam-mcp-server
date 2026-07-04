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
    try {
        const productRestClient = createProductRestClient();
        const serviceInfo = await productRestClient.getServiceInfo();

        return createToolMetadata(serviceInfo.chatbotMode);
    } catch (error) {
        // The Veeam product may not be reachable at startup — e.g. the MCP
        // server is launched before connectivity is established, or it is run
        // behind a network tunnel / by an MCP client that expects `tools/list`
        // to succeed without a live backend. Detecting the chatbot mode is the
        // ONLY reason we contact the product here, and it affects nothing but a
        // runtime advisory (the tool description is identical in both modes).
        // So rather than crash the process, start with default (advanced) tool
        // metadata; the tool handler authenticates on demand and surfaces any
        // connectivity/auth error as a normal tool error at call time.
        const cause = error instanceof Error ? error.message : String(error);
        console.error(
            `[veeam-mcp] Could not reach the Veeam product at startup to detect chatbot mode; ` +
                `starting with default tool metadata. Tool calls will authenticate on demand. Cause: ${cause}`,
        );
        return createToolMetadata(ChatbotMode.Advanced);
    }
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
