/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { matchTemplate } from './matchTemplate';
import { FetchPolicyRegistry, GateDecision, HttpMethod } from './types';

/**
 * Host fetch gate: decides whether a product REST call proposed by Veeam Intelligence may run
 * silently, needs the user's confirmation, or is blocked. Mirrors the product web UI behaviour
 * (`HostFetchGateService.gate`) with one deliberate difference: with no registry, non-GET calls
 * are rejected rather than allowed, because an MCP server has no UI to fall back on.
 */
export class FetchGate {
    constructor(
        private readonly registry: FetchPolicyRegistry | undefined,
        private readonly texts: Record<string, string> = {},
    ) {}

    public decide(method: HttpMethod, endpointPath: string): GateDecision {
        if (method === 'GET') {
            return { kind: 'allowed' };
        }

        if (this.registry === undefined) {
            return {
                kind: 'rejected',
                reason: `${method} ${endpointPath} is not allowed: this product/version has no action policy in the MCP server`,
            };
        }

        const path = FetchGate.stripQuery(endpointPath);

        const whitelistHit = this.registry.whitelist.find((entry) => entry.method === method && matchTemplate(entry.pathPattern, path));
        if (whitelistHit !== undefined) {
            return { kind: 'allowed' };
        }

        const checklistHit = this.registry.checklist.find((entry) => entry.method === method && matchTemplate(entry.pathPattern, path));
        if (checklistHit === undefined) {
            return {
                kind: 'rejected',
                reason: `${method} ${path} is not allowed by the MCP server action policy`,
            };
        }

        return {
            kind: 'confirm',
            title: this.texts[checklistHit.titleKey] ?? checklistHit.titleKey,
            description: this.texts[checklistHit.descriptionKey] ?? checklistHit.descriptionKey,
        };
    }

    private static stripQuery(endpointPath: string): string {
        const index = endpointPath.indexOf('?');
        return index === -1 ? endpointPath : endpointPath.slice(0, index);
    }
}
