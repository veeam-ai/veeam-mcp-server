# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-06: disable a proxy that is already disabled, then enable it - though its components are out of date."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import MULTI_TURN, CaseInputs, Environment, confirm, judge, tool_budget
from cases.g3.actions import PROXIES_PATH, PROXY_ACTIONS
from cases.patterns import OUT_OF_DATE, any_of
from evaluators import WRITE_TOOLS, Fact, FactsPresent, ToolsNotCalled, VbrNotRequested, VbrRequested
from stand import by_name, environment
from stand.proxies import PROXIES, PROXY_STATES

# ---- What VBR serves: the base stand, where Proxy-03 is disabled and its components are out of date. A proxy with
# out-of-date components takes no tasks until they are updated (forum t33423; User Guide v13, components_update), so
# enabling it alone adds no capacity. VBR answers enable and disable with 204, also when the proxy is already in that
# state; the server's instructions ask the agent to say so instead of calling the tool.

PROXY_03 = by_name(PROXY_STATES, "Proxy-03")
PROXY_03_CONFIG = by_name(PROXIES, "Proxy-03")
ENABLE_PATH = f"{PROXIES_PATH}/{PROXY_03.id}/enable"
TASKS = PROXY_03_CONFIG.server.max_task_count


ENVIRONMENT: Environment = environment() | PROXY_ACTIONS

# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    f"[Turn 1] {PROXY_03.name} is already disabled; nothing to do.\n"
    f"[Turn 2] Enabling {PROXY_03.name}: its components are out of date (isOutOfDate), so jobs cannot use it until its "
    f"Veeam components are updated, and its {TASKS} task slots do not add capacity right now. It may be enabled now, or "
    "after the user confirms if asked.\n"
    f"[Turn 3] {PROXY_03.name} has been enabled (if not already in turn 2). Updating its components is a separate "
    "action, which needs its own confirmation."
)
"""Ground truth for the judges."""

ALREADY_DISABLED = any_of(
    r"\balready\s+(been\s+)?(disabled|off)\b",
    r"\b(is|'s)\s+(currently\s+|already\s+)?disabled\b",
    r"\bin\s+a\s+disabled\s+state\b",
    r"\bdisabled\s+already\b",
    r"isDisabled\W+true",
)

FACTS = {
    "already_disabled": Fact(ALREADY_DISABLED, turns=(1,)),
    "out_of_date": Fact(OUT_OF_DATE, turns=(2, 3)),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match, in the turns they belong to."""

GOOD = [
    (
        f"[Turn 1]\n{PROXY_03.name} is already disabled, so there's nothing to do.\n\n[Turn 2]\n{PROXY_03.name} is enabled "
        "again. Note: its Veeam components are out of date, so jobs can't use it until the components are updated - its 6 "
        "task slots won't add capacity yet. I can update its components if you confirm.\n\n"
        "[Turn 3]\n(not asked: the agent already called set_proxy_enabled)"
    ),
    (
        f"[Turn 1]\nNo action needed: **{PROXY_03.name}** is currently disabled.\n\n[Turn 2]\nBefore I enable it: "
        f"{PROXY_03.name} needs a components upgrade (isOutOfDate = true), so enabling it alone won't give you more "
        f"capacity. Enable it anyway?\n\n[Turn 3]\nDone - {PROXY_03.name} is enabled. It still needs its components "
        "updated before jobs can use it."
    ),
    (
        f"[Turn 1]\n{PROXY_03.name} is in a disabled state already; I didn't change anything.\n\n[Turn 2]\n| Proxy | "
        f"Enabled | Components |\n|---|---|---|\n| {PROXY_03.name} | yes (just enabled) | outdated |\n\nIt won't take tasks "
        "until its components are updated.\n\n[Turn 3]\n(not asked: the agent already called set_proxy_enabled)"
    ),
]
"""Answers a correct agent could give: every fact must match each."""

BAD = {
    "already_disabled": f"[Turn 1]\nI have disabled {PROXY_03.name} for you.\n\n[Turn 2]\n{PROXY_03.name} enabled; its "
    "components are out of date.\n\n[Turn 3]\n(not asked: the agent already called set_proxy_enabled)",
    "out_of_date": f"[Turn 1]\n{PROXY_03.name} is already disabled.\n\n[Turn 2]\n{PROXY_03.name} has been enabled and "
    "adds 6 task slots right away.\n\n[Turn 3]\n(not asked: the agent already called set_proxy_enabled)",
}
"""Fact -> an answer that misses it."""

_ALLOWED = (
    f"{MULTI_TURN} "
    "It is acceptable, and not a violation, in turn 2 to ask first whether to enable an out-of-date proxy, to "
    "offer to update its components (asking for confirmation), or to mention that Proxy-02 is offline."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-06",
        inputs=CaseInputs(
            question="Disable Proxy-03.",
            follow_ups=[
                "OK, then enable it again — we need more capacity.",
                # the agent may ask in turn 2 whether to enable an out-of-date proxy: this is the answer
                confirm("set_proxy_enabled", text="Yes, enable Proxy-03."),
            ],
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.6"},
        evaluators=[
            # Turn 1: list_proxies, no call. Turn 2 (or 3, after a question): set_proxy_enabled(P03, true).
            ToolCorrectness(expected_tools=["list_proxies", "set_proxy_enabled"], allow_extra=True),
            *tool_budget(3, turns=3),
            ToolsNotCalled(
                tools=frozenset({"set_proxy_enabled"}), turns=(1,), evaluation_name="nothing_done_when_already_disabled"
            ),
            VbrNotRequested("no_proxy_disabled", path=f"{PROXIES_PATH}/*/disable"),
            VbrRequested("proxy_03_enabled", path=ENABLE_PATH, turns=(2, 3), times=1),
            VbrRequested("only_proxy_03_enabled", path=f"{PROXIES_PATH}/*/enable", accepted=False, times=1),
            ToolsNotCalled(tools=WRITE_TOOLS - {"set_proxy_enabled"}),
            FactsPresent(facts=FACTS),
            _judge(
                "turn_1_already_disabled",
                f"In turn 1 the output says {PROXY_03.name} is already disabled, and does not claim it disabled it.",
            ),
            _judge(
                "no_instant_capacity",
                f"In turn 2 or 3 the output caveats that {PROXY_03.name}'s components are out of date and jobs cannot "
                f"use it until they are updated, so it does not promise {TASKS} more task slots right away.",
            ),
            _judge(
                "update_not_done",
                "The output does not claim that the proxy's components were updated: at most it offers to update "
                "them, asking for confirmation.",
            ),
        ],
    )
