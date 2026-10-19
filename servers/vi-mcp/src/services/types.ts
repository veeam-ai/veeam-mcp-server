/**
 * Copyright © Veeam Software Group GmbH. All rights reserved.
 * Licensed under the MIT License. See LICENSE in the project root for license information.
 */

import { Artifact } from '@/common/types';
import { ActionOutcome, ConfirmationRequest } from '@/actions/types';

export interface ChatServiceOptions {
    /** Product code from settings (`vbr` | `vone` | `vspc`), selects the action policy. */
    productCode: string;
    /** How long a confirmation may stay unanswered before it is declined. */
    confirmationTimeoutMs: number;
    /** Upper bound for one turn (question → final answer), including confirmation waits. */
    turnTimeoutMs: number;
}

/**
 * Result of `sendMessage()` / `resume()`. `message` and `artifacts` hold only what arrived since
 * the previous outcome, so a paused turn can be reported incrementally to the MCP client.
 */
export type TurnOutcome =
    | {
          kind: 'complete';
          message: string;
          artifacts: Artifact[];
          actions: ActionOutcome[];
      }
    | {
          kind: 'awaiting_confirmation';
          request: ConfirmationRequest;
          message: string;
          artifacts: Artifact[];
          actions: ActionOutcome[];
      };
