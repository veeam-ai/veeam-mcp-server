/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { Chat } from "./chat/Chat.js";
import { VeeamApiClient } from "./rest/VeeamApiClient.js";

export async function answer_question(question: string, log: (message: string) => void = () => {}) {
    try {
        // Initialize Veeam One Rest API Client
        log('Initializing VeeamApiClient...');
        const client = new VeeamApiClient();

        log('Getting service info (this will trigger authentication)...');
        const serviceInfo = await client.getServiceInfo();
        log('Service info: ' + JSON.stringify(serviceInfo));

        log('Getting license info...');
        const authResult = await client.authenticate();
        log('Authenticate info: ' + JSON.stringify(authResult));

        // Initialize chat
        const chat: Chat = new Chat(authResult.response, serviceInfo);
        const answer: string = await chat.answer(question);
        log('Answer: ' + answer);
        return answer;
    } catch (error) {
        return `Error occurred: ${error}`;
    }
}