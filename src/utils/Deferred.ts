/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

export class Deferred<T = void> {
    public promise: Promise<T>;
    public resolve!: (value: T | PromiseLike<T>) => void;
    public reject!: (reason?: any) => void;

    constructor() {
        this.promise = new Promise<T>((resolve, reject) => {
            this.resolve = resolve;
            this.reject = reject;
        });
    }
}
