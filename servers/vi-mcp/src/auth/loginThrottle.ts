/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

export const LOGIN_FAILURE_WINDOW_MS = 15 * 60 * 1000;
const LOGIN_FAILURE_LIMIT = 10;

export class LoginThrottle {
    private readonly failures = new Map<string, number[]>();
    private readonly pending = new Map<string, number>();

    isLocked(address: string): boolean {
        return this.recent(address).length + (this.pending.get(address) ?? 0) >= LOGIN_FAILURE_LIMIT;
    }

    begin(address: string): () => void {
        this.pending.set(address, (this.pending.get(address) ?? 0) + 1);
        let done = false;
        return () => {
            if (done) {
                return;
            }
            done = true;
            const left = (this.pending.get(address) ?? 1) - 1;
            if (left === 0) {
                this.pending.delete(address);
            } else {
                this.pending.set(address, left);
            }
        };
    }

    recordFailure(address: string): void {
        this.failures.set(address, [...this.recent(address), Date.now()]);
    }

    prune(): void {
        for (const address of this.failures.keys()) {
            this.recent(address);
        }
    }

    private recent(address: string): number[] {
        const cutoff = Date.now() - LOGIN_FAILURE_WINDOW_MS;
        const failures = (this.failures.get(address) ?? []).filter((at) => at > cutoff);
        if (failures.length === 0) {
            this.failures.delete(address);
        } else {
            this.failures.set(address, failures);
        }
        return failures;
    }
}
