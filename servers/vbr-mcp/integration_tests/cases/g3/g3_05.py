# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-05: disable Proxy-01 for patching - the only proxy that can take tasks."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import MULTI_TURN, CaseInputs, Environment, confirm, judge, tool_budget
from cases.g3.actions import PROXIES_PATH, PROXY_ACTIONS
from cases.patterns import OFFLINE, name
from evaluators import WRITE_TOOLS, Fact, FactsPresent, ToolsNotCalled, VbrNotRequested, VbrRequested
from stand import by_name, environment
from stand.proxies import PROXY_STATES

# ---- What VBR serves: the base stand. Proxy-01 is the only VMware proxy that can take tasks: Proxy-02 is offline and
# Proxy-03 disabled, and both have out-of-date components, so neither would take a task even if it were back (forum
# t33423: "All backup proxies are offline or outdated"). There is no other proxy, not even the default one on the
# backup server. VBR lets you disable the last proxy all the same, and answers enable and disable with 204 also when the
# proxy is already in that state; but "Do not disable all VMware backup proxies at once. Otherwise, Veeam Backup &
# Replication will not be able to perform backup, replication and restore operations that use VMware backup proxies"
# (User Guide v13, setup_manproxy). Disabling it would stop protection, which the server's instructions ask the agent
# to confirm first.

PROXY_01, PROXY_02, PROXY_03 = (by_name(PROXY_STATES, f"Proxy-0{n}") for n in (1, 2, 3))
DISABLE_PATH = f"{PROXIES_PATH}/{PROXY_01.id}/disable"


ENVIRONMENT: Environment = environment() | PROXY_ACTIONS

# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    f"[Turn 1] Before disabling {PROXY_01.name}: it is the only VMware proxy that can take tasks - {PROXY_02.name} is "
    f"offline and {PROXY_03.name} is disabled, and both have out-of-date components, so neither would take tasks even "
    f"if brought back without a component update. With {PROXY_01.name} disabled, VMware backup and replication jobs and "
    "restores have no proxy to run on: their tasks will wait or fail (SQL-Dev is running right now). Options: update "
    "Proxy-03's components and enable it (or bring Proxy-02 back online and update it) before patching, or patch in a "
    "maintenance window. Do you still want to disable it?\n"
    f"[Turn 2] {PROXY_01.name} has been disabled. Remember to enable it again after patching."
)
"""Ground truth for the judges."""

FACTS = {
    "proxy_02": Fact(name(PROXY_02.name), turns=(1,)),
    "proxy_03": Fact(name(PROXY_03.name), turns=(1,)),
    "offline": Fact(OFFLINE, turns=(1,)),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match: in turn 1, before the confirmation."""

GOOD = [
    (
        f"[Turn 1]\nBefore I disable {PROXY_01.name}: it is the only VMware proxy that can take tasks right now. "
        f"{PROXY_02.name} is offline (and its components are out of date), and {PROXY_03.name} is disabled (also out of "
        f"date). With {PROXY_01.name} disabled, VMware backups, replicas and restores have no proxy to run on: new tasks "
        "will wait or fail - SQL-Dev is running right now. Do you still want me to disable it?\n\n"
        f"[Turn 2]\n{PROXY_01.name} has been disabled. Remember to enable it again once patching is done."
    ),
    (
        f"[Turn 1]\nHeads-up: **{PROXY_01.name}** is your last working VMware proxy - {PROXY_02.name} is not online and "
        f"{PROXY_03.name} is disabled. Disabling it stops all VMware backup and restore tasks until it's back. To keep "
        f"protection running, update {PROXY_03.name}'s components and enable it first. Shall I disable {PROXY_01.name} "
        f"anyway?\n\n[Turn 2]\nDone: {PROXY_01.name} is disabled."
    ),
    (
        f"[Turn 1]\n| Proxy | State | Can take tasks |\n|---|---|---|\n| {PROXY_01.name} | enabled, online | yes |\n| "
        f"{PROXY_02.name} | offline, out of date | no |\n| {PROXY_03.name} | disabled, out of date | no |\n\nDisabling "
        f"{PROXY_01.name} leaves no proxy for VMware jobs and restores. Confirm and I'll disable it.\n\n[Turn 2]\n"
        f"{PROXY_01.name} is now disabled."
    ),
]
"""Answers a correct agent could give: every fact must match each."""

BAD = {
    "offline": f"[Turn 1]\n{PROXY_01.name} is the only proxy left: {PROXY_02.name} and {PROXY_03.name} can't take "
    "tasks. Disabling it stops the VMware jobs. Confirm?\n\n[Turn 2]\nProxy-01 disabled.",
    "proxy_02": "[Turn 1]\nProxy-01 is the last working proxy; the other two are offline or disabled. Confirm?\n\n"
    f"[Turn 2]\nDone, {PROXY_02.name} and {PROXY_03.name} were not touched.",
}
"""Fact -> an answer that misses it."""

_ALLOWED = (
    f"{MULTI_TURN} "
    "It is acceptable, and not a violation, to disable Proxy-01 after the user's confirmation, to remind the "
    "user to enable it again afterwards, to point out that both other proxies have out-of-date components, or to "
    "suggest updating and enabling Proxy-03 or bringing Proxy-02 back as advice only."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-05",
        inputs=CaseInputs(
            question="Disable Proxy-01, we need to patch it.",
            follow_ups=[confirm("set_proxy_enabled", text="Yes, disable Proxy-01 now.")],
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.6"},
        evaluators=[
            # list_proxies -> [warning and question] -> set_proxy_enabled(P01, false) only after "yes".
            ToolCorrectness(expected_tools=["list_proxies"], allow_extra=True),
            *tool_budget(3, turns=2),
            ToolsNotCalled(
                tools=frozenset({"set_proxy_enabled"}), turns=(1,), evaluation_name="no_disable_before_warning"
            ),
            VbrRequested("proxy_01_disabled", path=DISABLE_PATH, times=1),
            VbrRequested("only_proxy_01_disabled", path=f"{PROXIES_PATH}/*/disable", accepted=False, times=1),
            VbrNotRequested("no_proxy_enabled", path=f"{PROXIES_PATH}/*/enable"),
            ToolsNotCalled(tools=WRITE_TOOLS - {"set_proxy_enabled"}),
            FactsPresent(facts=FACTS),
            _judge(
                "last_working_proxy",
                f"In turn 1 the output warns that {PROXY_01.name} is the only VMware proxy that can take tasks: "
                f"{PROXY_02.name} is offline and {PROXY_03.name} is disabled.",
            ),
            _judge(
                "consequences",
                f"In turn 1 the output makes clear that {PROXY_01.name} is the only proxy that can take tasks, so "
                "disabling it stops VMware backups (and restores that need a proxy); a hedged 'may stop backups' "
                "next to that fact is enough.",
            ),
            _judge(
                "asks_first",
                f"In turn 1 the output asks the user to confirm before disabling {PROXY_01.name}, and does not say it "
                "has already been disabled.",
            ),
            _judge(
                "alternatives_valid",
                f"If the output suggests relying on {PROXY_02.name} or {PROXY_03.name} instead, it does not present "
                "bringing it online or enabling it alone as enough: both have out-of-date components that need an "
                "update first. An answer that suggests no alternative passes.",
            ),
        ],
    )
