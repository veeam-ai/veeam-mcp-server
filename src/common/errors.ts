/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

export class ToolCallingError extends Error {
    public data: unknown;

    constructor(data: unknown) {
        super();
        this.name = 'ToolCallingError';
        this.data = data;
    }
}
