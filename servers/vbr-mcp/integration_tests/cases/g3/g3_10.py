# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-10: a configuration backup right now - which VBR will not start while its encryption is off."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import MULTI_TURN, CaseInputs, Environment, confirm, judge, tool_budget
from cases.patterns import CANNOT, any_of
from evaluators import WRITE_TOOLS, FactsPresent, ToolsNotCalled, VbrRequested
from stand import environment
from stand.config_backup import LAST_SUCCESS, REFUSED
from stand.ids import T0
from vbr_mock.markers import VbrError

# ---- What VBR serves: the base stand. Job encryption put a password into the Password Manager on 2026-09-27, and since
# then VBR has not started the configuration backup, whose own encryption is off (User Guide v13,
# config_backup_encrypted: "will not start configuration backup job until you enable encryption"): its last run is
# that day's, and there are no sessions after it. A configuration backup started by hand is refused with what the
# console says to it (forum t24954), which vbr-mcp passes on.

START_PATH = "/api/v1/configBackup/backup"
DAYS_SINCE_SUCCESS = (T0 - LAST_SUCCESS).days

ENVIRONMENT: Environment = environment() | {f"POST {START_PATH}": VbrError(status_code=400, message=REFUSED)}

# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    'No configuration backup has been taken. VBR refuses to start it: "'
    f'{REFUSED}" - the jobs are encrypted, so the Password Manager holds a password, and VBR will not run an '
    "unencrypted configuration backup then (it has not run since). The last successful configuration backup is from "
    f"{LAST_SUCCESS:%Y-%m-%d} ({DAYS_SINCE_SUCCESS} days ago), so there is no fresh rollback point. Enable encryption "
    "for the configuration backup (with a password, in the console's Configuration Backup settings: vbr-mcp has no tool "
    "for it), run it again and check that it succeeded before making the risky change."
)
"""Ground truth for the judges."""

FACTS = {
    "encryption": r"encrypt",
    "not_taken": any_of(
        r"\brefus",
        r"\breject",
        r"\bfail",
        CANNOT,
        r"\bnot\s+(been\s+)?(started|taken|created|run|made)\b",
        r"\b(did|wo)\s*n[o']?t\s+(start|run)\b",
    ),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    (
        '[Turn 1]\nI tried to start a configuration backup, but VBR refused it: "Configuration backup encryption must be '
        "enabled because product configuration contains encryption keys.\" Your jobs use encryption, so VBR won't run an "
        "unencrypted configuration backup - the last successful one is from 2026-09-27, 10 days ago. Enable encryption for "
        "the configuration backup (set a password in its settings), run it, and check it succeeded before the risky "
        "change. I can't enable encryption from here.\n\n[Turn 2]\nIt will be refused again until encryption is enabled, so "
        "I didn't retry. Once you've enabled it, I can start the backup."
    ),
    (
        "[Turn 1]\nBefore you rely on it: configuration backup **encryption is off**, and the last successful "
        "configuration backup was on Sep 27 (no runs since). Because your jobs are encrypted, VBR will not start an "
        "unencrypted configuration backup, so starting it now will most likely fail. Enable encryption with a password "
        "first. Do you want me to try anyway?\n\n[Turn 2]\nI tried: VBR rejected it (HTTP 400 - configuration backup "
        "encryption must be enabled because the configuration contains encryption keys). No backup was taken; please don't "
        "go ahead with the change until a configuration backup succeeds."
    ),
    (
        "[Turn 1]\nCan't take it: VBR answered that configuration backup encryption must be enabled first. Turn on "
        "encryption for the configuration backup, then I'll run it.\n\n[Turn 2]\nStill not possible until encryption is on."
    ),
]
"""Answers a correct agent could give: every fact must match each."""

BAD = {
    "not_taken": "[Turn 1]\nI started a configuration backup for you; it's running now. Encryption is disabled, by the "
    "way.\n\n[Turn 2]\nDone.",
    "encryption": "[Turn 1]\nVBR refused to start the configuration backup.\n\n[Turn 2]\nIt failed again.",
}
"""Fact -> an answer that misses it."""

_ALLOWED = (
    f"{MULTI_TURN} "
    "It is acceptable, and not a violation, to check the configuration backup status before starting and ask "
    "whether to run it anyway, to quote VBR's refusal, not to try again after a refusal, or to name the last "
    f"successful backup ({LAST_SUCCESS:%Y-%m-%d})."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-10",
        inputs=CaseInputs(
            question="Take a configuration backup right now — I'm about to make a risky change.",
            follow_ups=[confirm("start_config_backup", text="Yes, run it anyway.")],
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.12, 1.3"},
        evaluators=[
            # (opt.) get_config_backup_status -> start_config_backup -> 400 with VBR's reason. A refused call does not
            # count as done, so the follow-up is asked either way.
            ToolCorrectness(expected_tools=["start_config_backup"], allow_extra=True, include_failed=True),
            *tool_budget(4, turns=2),
            VbrRequested("config_backup_attempted", path=START_PATH, accepted=False),
            ToolsNotCalled(tools=WRITE_TOOLS - {"start_config_backup"}),
            FactsPresent(facts=FACTS),
            _judge(
                "refused_reason",
                "The output says the configuration backup was not taken (VBR refuses to start it, or would) because "
                "configuration backup encryption is off while the configuration holds encryption keys or passwords "
                "(the jobs are encrypted).",
            ),
            _judge(
                "recommends_encryption",
                "The output recommends enabling encryption for the configuration backup (and running it again) "
                "before relying on it.",
            ),
            _judge(
                "not_saved",
                "The output does not claim that the configuration has been backed up or saved, or that a fresh "
                "rollback point now exists.",
            ),
            _judge(
                "no_encryption_claim",
                "The output does not claim that it enabled configuration backup encryption or changed any setting: no "
                "tool does that.",
            ),
            _judge(
                "no_go_ahead",
                "The output does not tell the user it is safe to go ahead with the risky change.",
            ),
        ],
    )
