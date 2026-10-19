# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-09: a YARA scan of fs-01's backups with one named rule."""

import re
from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import CaseInputs, Environment, judge, tool_budget
from cases.g3.actions import SCAN_PATH, SCAN_SESSION, reject_scan
from cases.patterns import STARTED, name
from evaluators import WRITE_TOOLS, FactsPresent, ToolsNotCalled, VbrNotRequested, VbrRequested
from stand import environment
from stand.malware import YARA_RULES
from stand.protected import BY_NAME
from stand.sessions import SESSIONS
from vbr_mock.markers import VbrAction

# ---- What VBR serves: the base stand, and the scan. VBR runs a YARA scan with the rule its request names
# (scanEngine.yaraRule.fileName, swagger MalwareBackupScanSpecEngine; the rule files are get_yara_rules'), which
# vbr-mcp's start_malware_scan passes as yara_rule_file_name. VBR refuses a YARA request without a rule or with a rule
# file it does not have, in its own words (cases/g3/actions.py). An accepted scan without YARA runs only the antivirus
# engine, which is not what the user asked for.

FS_01 = BY_NAME["fs-01"]
RULE = YARA_RULES[1]

ENVIRONMENT: Environment = environment() | {
    SCAN_PATH: VbrAction(
        response=SCAN_SESSION,
        reject=reject_scan,
        effects={"/api/v1/sessions": [SCAN_SESSION, *SESSIONS], f"/api/v1/sessions/{SCAN_SESSION.id}": SCAN_SESSION},
    ),
}

# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    f"A YARA scan of {FS_01.name}'s backups with the rule {RULE.file_name} (a rule file the server has) has been "
    "started: VBR runs it as a Scan Backup session. It has started, it has not finished: the session and the malware "
    "events show what it finds."
)
"""Ground truth for the judges."""

FACTS = {
    "vm": name(FS_01.name),
    "rule": re.escape(RULE.file_name),
    "started": STARTED,
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    (
        f"I started a YARA scan of {FS_01.name}'s backups with {RULE.file_name}. It runs as a Scan Backup session; "
        "there is no result yet - the malware events will show any detection."
    ),
    (
        f"The rule **{RULE.file_name}** exists on the server, so I kicked off a scan of {FS_01.name} with it (YARA "
        "engine, all restore points in the interval). It's in progress."
    ),
    (
        f"| VM | Rule | Status |\n|---|---|---|\n| {FS_01.name} | {RULE.file_name} | scan started |\n\nI'll check the "
        "session for the outcome when you want."
    ),
]
"""Answers a correct agent could give: every fact must match each."""

BAD = {
    "started": f"The rule {RULE.file_name} exists on the server. Shall I scan {FS_01.name}'s backups with it?",
    "rule": f"I started a YARA scan of {FS_01.name}'s backups; no result yet.",
    "vm": f"A YARA scan with {RULE.file_name} has been started.",
}
"""Fact -> an answer that misses it."""

_ALLOWED = (
    "It is acceptable, and not a violation, to check first that the rule exists (get_yara_rules), to scan with the "
    "antivirus engine as well as the YARA rule, to pick any scan mode, to report a request VBR refused before the one "
    "it accepted, or to offer to check the result later."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-09",
        inputs=CaseInputs(
            question=f"Scan fs-01's backups with the YARA rule {RULE.file_name}.", environment=ENVIRONMENT
        ),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.10"},
        evaluators=[
            # (opt.) get_yara_rules -> list_protected_objects / list_backups -> start_malware_scan(yara_rule_file_name)
            ToolCorrectness(expected_tools=["start_malware_scan"], allow_extra=True),
            *tool_budget(4),
            VbrRequested(
                "yara_scan_with_the_rule",
                path=SCAN_PATH,
                body={
                    "backupObjectPair": [{"backupObjectId": FS_01.id}],
                    "scanEngine": {"useYaraRule": True, "yaraRule": {"fileName": RULE.file_name}},
                },
                times=1,
            ),
            # a scan without the YARA rule runs in place of the one asked for
            VbrNotRequested(
                "no_scan_without_yara", path=SCAN_PATH, body={"scanEngine": {"useYaraRule": False}}, accepted=True
            ),
            ToolsNotCalled(tools=WRITE_TOOLS - {"start_malware_scan"}),
            FactsPresent(facts=FACTS),
            _judge(
                "started_not_result",
                f"The output says a YARA scan of {FS_01.name}'s backups with {RULE.file_name} has been started, and "
                "reports no scan result (clean, infected or anything found) as if the scan had already finished.",
            ),
        ],
    )
