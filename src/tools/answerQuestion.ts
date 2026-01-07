/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { ChatService } from '@/services';
import { ProductClient } from '@/product';

export async function answerQuestion(question: string, log: (message: string) => void = () => {}) {
    try {
        // Initialize Veeam Product Client
        log('Initializing ProductClient...');
        const client = new ProductClient();

        // Initialize Veeam Intelligence service
        log('Initializing Veeam Intelligence Service...');
        const chat: ChatService = new ChatService(client);

        log('Connecting to service (authentication and service info retrieval)...');
        await chat.initialize();

        // Send message
        const { message, artifacts } = await chat.sendMessage(question);
        log('Answer: ' + message);
        log('Artifacts: ' + JSON.stringify(artifacts));

        // Cleanup
        chat.disconnect();

        return { message, artifacts };
    } catch (error: any) {
        const errorMessage = error?.message || String(error);
        throw new Error(`Error occurred: ${errorMessage}`, { cause: error.cause });
    }
}
