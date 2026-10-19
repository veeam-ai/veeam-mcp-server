# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""Group 3 of the test plan: questions that lead, or may lead, to write and destructive tools.

The actions are mocked as VBR performs them (``VbrAction``), and the cases assert what reached VBR
(``VbrRequested``), not only which tools the agent called. A destructive action needs the user's "yes" first: those
cases follow the question with ``confirm(...)``, a turn that is skipped if the agent did not wait for it.
"""
