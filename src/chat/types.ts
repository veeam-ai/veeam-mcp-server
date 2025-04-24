/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { ServiceInfo, AuthResponse } from '../common/types.js';


export interface ChatInterface {
    /**
     * Sends a message to the chatbot and returns the response
     * @param message The message to send
     * @returns Promise with the chatbot's response
     */
    answer(message: string): Promise<string>;

    /**
     * Resets the current chat session
     */
    reset(): void;

    /**
     * Disconnects from the chat service
     */
    disconnect(): void;
} 