/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { createCipheriv, createDecipheriv, hkdfSync, randomBytes } from 'node:crypto';

const IV_BYTES = 12;
const TAG_BYTES = 16;

export type SealPurpose = 'client' | 'authorize' | 'code' | 'access' | 'refresh';

export interface Sealed {
    exp?: number;
}

export function nowSec(): number {
    return Math.floor(Date.now() / 1000);
}

export class TokenSealer {
    private constructor(private readonly key: Buffer) {}

    static fromSecret(secret: string | undefined): TokenSealer {
        if (secret === undefined) {
            return new TokenSealer(randomBytes(32));
        }
        return new TokenSealer(Buffer.from(hkdfSync('sha256', secret, '', 'veeam-mcp-server/oauth-tokens', 32)));
    }

    seal(purpose: SealPurpose, payload: Sealed): string {
        const iv = randomBytes(IV_BYTES);
        const cipher = createCipheriv('aes-256-gcm', this.key, iv);
        cipher.setAAD(Buffer.from(purpose));
        const ciphertext = Buffer.concat([cipher.update(JSON.stringify(payload), 'utf8'), cipher.final()]);
        return Buffer.concat([iv, ciphertext, cipher.getAuthTag()]).toString('base64url');
    }

    unseal<T extends Sealed>(purpose: SealPurpose, token: string): T | undefined {
        const raw = Buffer.from(token, 'base64url');
        if (raw.length <= IV_BYTES + TAG_BYTES) {
            return undefined;
        }

        try {
            const decipher = createDecipheriv('aes-256-gcm', this.key, raw.subarray(0, IV_BYTES));
            decipher.setAAD(Buffer.from(purpose));
            decipher.setAuthTag(raw.subarray(raw.length - TAG_BYTES));
            const plaintext = Buffer.concat([decipher.update(raw.subarray(IV_BYTES, raw.length - TAG_BYTES)), decipher.final()]);
            const payload = JSON.parse(plaintext.toString('utf8')) as T;
            return payload.exp !== undefined && payload.exp <= nowSec() ? undefined : payload;
        } catch {
            return undefined;
        }
    }
}
