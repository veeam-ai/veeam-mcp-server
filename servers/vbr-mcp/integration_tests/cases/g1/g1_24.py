# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G1-24: after a VBR upgrade, which proxies can take tasks — online and enabled is not enough."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import CaseInputs, Environment, judge, tool_budget
from cases.patterns import OUT_OF_DATE, any_of, name, near, number
from evaluators import FactsPresent, ToolsNotCalled
from stand import by_name, environment, proxies, replace
from stand.ids import P01, P02, P03

# ---- What VBR serves: the base stand, with the proxies as they stand the day after an upgrade of the backup server:
# all three are online and enabled, but only Proxy-03's components have been updated. A proxy with out-of-date
# components takes no tasks until they are updated (forum t33423, "All backup proxies are offline or outdated"; User
# Guide v13, components_update), so of the 18 configured task slots only Proxy-03's 6 are usable.

PROXY_STATES = replace(
    replace(
        replace(proxies.PROXY_STATES, P01, is_out_of_date=True),
        P02,
        is_online=True,
        is_out_of_date=True,
    ),
    P03,
    is_disabled=False,
    is_out_of_date=False,
)

ENVIRONMENT: Environment = environment(proxy_states=PROXY_STATES)

# ---- What a correct answer says, derived from the data above.

_CONFIG = {proxy.name: proxy for proxy in proxies.PROXIES}
USABLE = [
    state.name for state in PROXY_STATES if not state.is_disabled and state.is_online and not state.is_out_of_date
]
SLOTS = sum(_CONFIG[proxy].server.max_task_count or 0 for proxy in USABLE)
OUTDATED = [state.name for state in PROXY_STATES if state.is_out_of_date]
assert USABLE == ["Proxy-03"] and SLOTS == 6

_P01, _P02 = by_name(proxies.PROXIES, "Proxy-01"), by_name(proxies.PROXIES, "Proxy-02")

EXPECTED = (
    f"Right now only {USABLE[0]} (prx03, Direct SAN access) can take tasks: {SLOTS} concurrent tasks. Proxy-01 "
    f"({_P01.server.max_task_count} tasks) and Proxy-02 ({_P02.server.max_task_count} tasks) are online and enabled, "
    "but their Veeam components are out of date after the upgrade, so jobs cannot use them until the components are "
    "updated (Components Update / update_managed_server_components on prx01 and prx02)."
)
"""Ground truth for the judges."""

FACTS = {
    "proxy_03": name("Proxy-03"),
    "slots": near(number(SLOTS, decimals=0), any_of(r"\btasks?\b", r"\bslots?\b", r"\bconcurren"), within=40),
    "out_of_date": OUT_OF_DATE,
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

_ALLOWED = (
    "It is acceptable, and not a violation, to give each proxy's transport mode or host, to mention the 18 "
    "configured slots as a configured total (not as usable), or to offer (without doing it) to update the "
    "components of prx01 and prx02."
)

GOOD = [
    (
        "Only **Proxy-03** can take tasks right now - 6 concurrent tasks. Proxy-01 (8) and Proxy-02 (4) are online and "
        "enabled, but their components are out of date after yesterday's upgrade, so jobs won't use them until you "
        "update them (Components Update on prx01 and prx02)."
    ),
    (
        "| Proxy | Online | Enabled | Components | Usable |\n|---|---|---|---|---|\n| Proxy-01 | yes | yes | outdated | no |"
        "\n| Proxy-02 | yes | yes | outdated | no |\n| Proxy-03 | yes | yes | up to date | yes (6 tasks) |\n\n"
        "Usable capacity: 6 concurrent tasks."
    ),
    "Just one: Proxy-03, with 6 task slots. The other two need a component upgrade first.",
    (
        "Proxy-03 only (6 concurrent tasks): the Veeam components on Proxy-01 and Proxy-02 aren't up to date since the "
        "upgrade, so they must be updated before jobs use them."
    ),
]
"""Answers a correct agent could give: every fact must match each of them."""

BAD = {
    "proxy_03": "Proxy-01 and Proxy-02 can take tasks: 12 concurrent tasks.",
    "slots": "Only Proxy-03 can take tasks now; Proxy-01 and Proxy-02 are out of date. That gives 18 concurrent tasks.",
    "out_of_date": "All three proxies are online and enabled: Proxy-01, Proxy-02 and Proxy-03, 18 concurrent tasks.",
}
"""Per fact, an answer that gets that fact wrong: the fact must not match it."""


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G1-24",
        inputs=CaseInputs(
            question=(
                "We upgraded VBR yesterday. Which backup proxies can take tasks right now, and how many concurrent "
                "tasks is that?"
            ),
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G1", "base_stand": "1.6 + delta"},
        evaluators=[
            ToolCorrectness(expected_tools=["list_proxies"], allow_extra=True),
            *tool_budget(1),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "only_proxy_03_usable",
                f"The output names {USABLE[0]} as the only proxy that can take tasks now and gives {SLOTS} as the "
                "concurrent task capacity. It does not count Proxy-01 or Proxy-02, which are online and enabled but "
                "have out-of-date components, as usable.",
            ),
            _judge(
                "update_needed_not_done",
                "The output says that Proxy-01 and Proxy-02 need their components updated before they take tasks, "
                "and does not claim to have updated them. Offering to update them is fine.",
            ),
        ],
    )
