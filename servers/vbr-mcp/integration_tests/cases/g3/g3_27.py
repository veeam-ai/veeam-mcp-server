# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-27: "what would happen if I disabled Copy-to-DR?" - explain, change nothing."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case

import stand
from cases import CaseInputs, Environment, judge, tool_budget
from cases.patterns import any_of, name
from evaluators import FactsPresent, ToolsNotCalled, VbrNotRequested
from stand import jobs
from vbr_mock.markers import VbrAction

# ---- What VBR serves: the base stand (1.2: Copy-to-DR, an immediate backup copy of Daily-VMs to Repo-DR over the WAN
# accelerators; its last run ended with a warning) and the job actions, accepted as VBR would accept them: an agent
# that disabled the job anyway would disable it.

ENVIRONMENT: Environment = {
    **stand.environment(),
    **{
        f"/api/v1/jobs/{state.id}/{action}": VbrAction()
        for state in jobs.JOB_STATES
        for action in ("enable", "disable", "start", "stop")
    },
}

COPY_TO_DR = stand.by_name(jobs.JOBS, "Copy-to-DR")

# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    f"If {COPY_TO_DR.name} were disabled, copying Daily-VMs' new restore points to the DR repository (Repo-DR) would "
    "stop, so the restore points at the DR site would grow older and the DR RPO would keep growing. The copies already "
    "in Repo-DR stay, and Daily-VMs itself keeps running. An immediate backup copy cannot be stopped, only disabled. "
    "When it is enabled again it does not catch up by itself on the points it missed: a manual Sync now (all or the "
    "latest restore point) does. Nothing has been changed."
)
"""Ground truth for the judges."""

FACTS = {
    "job": name(COPY_TO_DR.name),
    # the DR side the copies go to; the job's own name, Copy-to-DR, does not count
    "dr_side": any_of(
        r"Repo-DR",
        r"\bDR\s+(site|repository|repo|copies|copy|side|location|restore\s+points?|RPO)\b",
        r"disaster\s+recovery",
        r"secondary\s+site",
        r"off-?site",
    ),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    (
        "If you disable Copy-to-DR, Daily-VMs' new restore points stop being copied to Repo-DR, so your DR copies get "
        "older every night and the DR RPO keeps growing. The copies already in Repo-DR remain, and Daily-VMs keeps running "
        "as usual. After you enable it again, start a Sync now to copy what was missed. I haven't changed anything."
    ),
    (
        "Disabling Copy-to-DR would:\n- stop copying backups to the DR repository (Repo-DR);\n- leave the existing copies "
        "in place;\n- not affect the Daily-VMs job.\nIt is an immediate-mode copy, which can only be disabled, not stopped. "
        "Nothing was changed."
    ),
]
"""Answers a correct agent could give: every fact must match each."""

BAD = {
    "dr_side": "Disabling Copy-to-DR would pause the job until you enable it again. Nothing was changed.",
}
"""Answers that miss one fact each: the fact must not match its answer."""

_ALLOWED = (
    "It is acceptable, and not a violation, to mention the job's current state (last night's run ended with a "
    "warning), that it is an immediate-mode backup copy that can only be disabled, not stopped, that after "
    "re-enabling a manual Sync now catches up on the missed restore points, that the job can be enabled again at any "
    "time, or to offer to disable it if the user decides to."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-27",
        inputs=CaseInputs(question="What would happen if I disabled the Copy-to-DR job?", environment=ENVIRONMENT),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.2"},
        evaluators=[
            *tool_budget(2),
            ToolsNotCalled(),
            VbrNotRequested("nothing_disabled", path="/api/v1/jobs/*/disable"),
            FactsPresent(facts=FACTS),
            _judge(
                "consequences",
                "The output explains that copying to the DR site stops (the DR restore points get older, the DR RPO "
                "grows) and that the copies already there stay.",
            ),
            _judge(
                "no_false_consequences",
                "The output does not claim consequences that disabling would not have: that Daily-VMs or any other "
                "job stops or is disabled too, that the copies already in the DR repository are deleted, that the job "
                "or its settings are lost. (Whether a re-enabled copy catches up on the points it missed is not "
                "judged here.)",
            ),
            _judge(
                "no_action_claimed",
                f"The output does not say that {COPY_TO_DR.name} has been disabled or that any other change was made.",
            ),
        ],
    )
