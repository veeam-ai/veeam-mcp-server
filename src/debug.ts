/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { config } from 'dotenv';
import { answerQuestion } from '@/tools/answerQuestion';

// Load environment variables from .env file
config();

async function main() {
    const question = 'Show me alarms';
    const answer = await answerQuestion(question, (message) => console.log(message));
    console.log('Answer:', answer);
}

await main();
