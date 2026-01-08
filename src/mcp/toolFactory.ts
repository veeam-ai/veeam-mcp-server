/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { ChatbotMode, PRODUCT_NAMES, ProductCode } from '@/common/types';
import { createProductClient } from '@/product/ProductClientFactory';

interface ToolConfig {
    title: string;
    description: string;
}

function getProductName(): string {
    const productCode = process.env.PRODUCT_NAME?.trim().toLowerCase() || '';
    if (!productCode) {
        throw new Error('PRODUCT_NAME environment variable is required. Valid values are: ' + Object.keys(PRODUCT_NAMES).join(', '));
    }

    if (productCode in PRODUCT_NAMES) {
        return PRODUCT_NAMES[productCode as ProductCode];
    }

    throw new Error(
        `PRODUCT_NAME environment variable has unexpected value ${productCode}. Valid values are: ` + Object.keys(PRODUCT_NAMES).join(', '),
    );
}

function createBasicModeTool(): ToolConfig {
    const productName = getProductName();
    const basicModeToolDescription = `Use this tool whenever to answer question based on ${productName} documentation. To answer questions on product data, enable Advanced mode in the product settings.`;

    return {
        title: `Answer Question on ${productName} Documentation`,
        description: basicModeToolDescription,
    };
}

function createAdvancedModeTool(): ToolConfig {
    const productName = getProductName();
    const advancedModeToolDescription =
        `Use this tool whenever a request involves Veeam operational knowledge—health checks, alert triage, remediation steps, configuration advice, integrations, or runbooks—for ${productName}. ` +
        'It returns authoritative Veeam product guidance backed by internal telemetry and documented procedures. ' +
        'Preserve the user wording; forward questions verbatim so intent is not altered. ' +
        'Responses arrive as JSON with top-level "message" and "artifacts" fields; when an artifact has type "dataframe" treat it as tabular output and render it as a table.';

    return {
        title: 'Answer Veeam Question',
        description: advancedModeToolDescription,
    };
}

export async function createTool(): Promise<ToolConfig> {
    const productClient = createProductClient();
    const serviceInfo = await productClient.getServiceInfo();

    if (serviceInfo.chatbotMode === ChatbotMode.Base) {
        return createBasicModeTool();
    } else if (serviceInfo.chatbotMode === ChatbotMode.Advanced) {
        return createAdvancedModeTool();
    } else {
        throw new Error(`Unsupported chatbot mode: ${serviceInfo.chatbotMode as string}`);
    }
}
