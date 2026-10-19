# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G1-09: how many proxies can take tasks, and the total concurrent task capacity."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import CaseInputs, judge, tool_budget
from cases.patterns import DISABLED, OFFLINE, any_of, name
from evaluators import FactsPresent, ToolsNotCalled
from stand import environment
from stand.proxies import PROXIES, PROXY_STATES

# ---- What VBR serves: the base stand. A proxy takes tasks only when it is enabled, online and up to date: "All
# backup proxies are offline or outdated" is the error a job gets otherwise (forum t33423). Proxy-01 is the only one;
# Proxy-02 is offline and Proxy-03 disabled, and both have out-of-date components on top.

ENVIRONMENT = environment()

# ---- What a correct answer says, derived from the stand.

_STATE = {state.id: state for state in PROXY_STATES}
_USABLE = [
    p for p in PROXIES if not _STATE[p.id].is_disabled and _STATE[p.id].is_online and not _STATE[p.id].is_out_of_date
]
_OFFLINE = [p for p in PROXIES if not _STATE[p.id].is_disabled and not _STATE[p.id].is_online]
_DISABLED = [p for p in PROXIES if _STATE[p.id].is_disabled]
(_WORKING,), (_OFFLINE_PROXY,), (_DISABLED_PROXY,) = _USABLE, _OFFLINE, _DISABLED
SLOTS = sum(p.server.max_task_count or 0 for p in _USABLE)  # 8
_CONFIGURED_SLOTS = sum(p.server.max_task_count or 0 for p in PROXIES)  # 18
_WORDS = {4: "four", 6: "six", 8: "eight"}

EXPECTED = (
    f"Only one proxy can take tasks right now: {_WORKING.name} (hot-add / VirtualAppliance transport), with "
    f"{SLOTS} concurrent task slots, which is the total usable capacity. {_OFFLINE_PROXY.name} is enabled but offline, "
    f"and {_DISABLED_PROXY.name} is disabled; both also have out-of-date components, so neither would take tasks "
    f"before a components update even if it were back. The {_CONFIGURED_SLOTS} task slots configured across all three "
    "proxies are not usable now, and the task limit is a configured value, not measured hardware capacity."
)
"""Ground truth for the judges."""

FACTS = {
    "working_proxy": name(_WORKING.name),
    "task_slots": any_of(
        rf"(?<![\d.]){SLOTS}\s*(?:\w+\s+){{0,2}}(?:tasks?|slots?|concurrent)\b",
        rf"\b{_WORDS[SLOTS]}\s+(?:\w+\s+){{0,2}}(?:tasks?|slots?)\b",
        rf"\b(?:capacity|slots?|tasks?|maxTaskCount)\W+(?:\w+\W+){{0,3}}{SLOTS}(?!\d|[.,]\d)",
    ),
    "offline_proxy": name(_OFFLINE_PROXY.name),
    "offline": any_of(OFFLINE, r"\b(?:is|are|was)n't\s+online\b"),
    "disabled_proxy": name(_DISABLED_PROXY.name),
    "disabled": DISABLED,
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

_ALLOWED = (
    "It is acceptable, and not a violation, to note the out-of-date components on Proxy-02 and Proxy-03, to list "
    "the transport modes (VirtualAppliance, Network, DirectAccess), to give the configured total of "
    f"{_CONFIGURED_SLOTS} slots while making clear only {SLOTS} are usable, to point out that there is no redundancy "
    "with a single working proxy, or to advise updating and bringing back Proxy-02 or Proxy-03, as advice only."
)

GOOD = [
    (
        f"Only **one** proxy can take tasks right now: Proxy-01 (hot-add), with {SLOTS} concurrent task slots - that's "
        "your total usable capacity. Proxy-02 is offline and Proxy-03 is disabled; both also have out-of-date components, "
        "so they'd need a components update before taking tasks."
    ),
    (
        "| Proxy | State | Max tasks | Usable |\n|---|---|---|---|\n| Proxy-01 | online, enabled | 8 | yes |\n| Proxy-02 | "
        "offline, outdated | 4 | no |\n| Proxy-03 | disabled, outdated | 6 | no |\n\nUsable: 1 proxy, 8 concurrent tasks "
        f"({_CONFIGURED_SLOTS} configured)."
    ),
    "1 of 3 proxies is usable (Proxy-01) -> eight concurrent tasks. Proxy-02 isn't online and Proxy-03 is turned off.",
]

BAD = {
    "task_slots": f"Three proxies are configured: Proxy-01, Proxy-02 (offline) and Proxy-03 (disabled), "
    f"{_CONFIGURED_SLOTS} task slots in total.",
    "offline": "Proxy-01 works (8 tasks); Proxy-02 and Proxy-03 are disabled.",
    "working_proxy": "None of the proxies can take tasks: Proxy-02 is offline and Proxy-03 is disabled, so there are "
    "0 usable task slots.",
}
"""Answers that each miss one fact."""


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G1-09",
        inputs=CaseInputs(
            question="How many backup proxies can actually take tasks right now, and what is our total concurrent task capacity?",
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G1", "base_stand": "1.6"},
        evaluators=[
            ToolCorrectness(expected_tools=["list_proxies"], allow_extra=True),
            *tool_budget(1),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "proxy_states",
                f"The output says {_WORKING.name} is the only proxy that can take tasks, {_OFFLINE_PROXY.name} is "
                f"offline and {_DISABLED_PROXY.name} is disabled.",
            ),
            _judge(
                "usable_capacity",
                f"The output does not give {_CONFIGURED_SLOTS} tasks (or any figure above {SLOTS}) as the usable "
                "concurrent capacity and does not say that more than one proxy can take tasks. Mentioning "
                f"{_CONFIGURED_SLOTS} as the configured total while making clear only {SLOTS} are usable is fine.",
            ),
            _judge(
                "disabled_from_data",
                f"The output does not call {_OFFLINE_PROXY.name} disabled, nor {_DISABLED_PROXY.name} enabled: "
                f"only {_DISABLED_PROXY.name} is disabled, {_OFFLINE_PROXY.name} is enabled but offline.",
            ),
            _judge(
                "out_of_date_counts",
                f"If the output suggests bringing {_OFFLINE_PROXY.name} back online or enabling "
                f"{_DISABLED_PROXY.name} to add capacity, it says their components are out of date and need an "
                "update first; it does not present either as usable once merely online or enabled. Not suggesting "
                "anything is fine.",
            ),
            _judge(
                "no_hardware_verdict",
                "The output does not claim that the proxies' hardware is, or is not, adequate for the workload: "
                "the task limit is a configured value, not validated hardware capacity.",
            ),
        ],
    )
