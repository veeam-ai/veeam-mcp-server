/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { answerQuestion } from '@/tools/answerQuestion';

async function main() {
    const question = 'Show me list of Veeam One alerts with severity Critical and Warning';
    const answer = await answerQuestion(question, (message) => console.log(message));
    console.log('Answer:', answer);
}

await main();