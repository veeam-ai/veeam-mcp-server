# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G2-10: are all computers in the protection groups covered by a working Veeam Agent."""

from datetime import timedelta
from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import CaseInputs, judge, tool_budget
from cases.patterns import about, any_of
from evaluators import FactsPresent, ToolsNotCalled
from stand import agents, by_name, environment
from stand.ids import PG01, PG02, T0, mnemonic
from vbr_models.protection_groups import DiscoveredCluster, DiscoveredComputer

# ---- What VBR serves: the base stand, with two changes to the protection groups' discovered entities (1.14).
#
# - Agent versions match the 13.1 server. On a 13.1 server an agent 13.0 would itself read UpgradeRequired once a
#   newer one is available (User Guide v13, agents_protected_computers_upgrade_console), so only laptop-hr-02's 6.3
#   agent is behind.
# - SQLCLUSTER01 has its nodes. An Active Directory protection group discovers a failover cluster's nodes, and the
#   agent goes on the nodes (User Guide v13, how_to_protect_failover_cluster): they are computers whose parent is the
#   cluster. sql-node-02 was added to the cluster later and has no agent yet.

AGENT_VERSION = "13.1.0.1810"
CLUSTER = next(e for e in agents.DISCOVERED_ENTITIES[PG02] if isinstance(e, DiscoveredCluster))
NODE_01 = agents.computer(
    7, "sql-node-01", PG02, parent_id=CLUSTER.id, state="Online", agent_status="Installed",
    agent_version=AGENT_VERSION, driver_status="Installed", last_connected=T0 - timedelta(minutes=25),
    operating_system="WindowsServer2022",
)  # fmt: skip
NODE_02 = agents.computer(
    8, "sql-node-02", PG02, parent_id=CLUSTER.id, state="Online", agent_status="NotInstalled",
    driver_status="NotInstalled", last_connected=None, operating_system="WindowsServer2022",
)  # fmt: skip


def _current(entity: DiscoveredComputer) -> DiscoveredComputer:
    """``entity`` with an agent of the server's version where the stand has the previous release."""
    if entity.agent_version == agents.AGENT_VERSION:
        return entity.model_copy(update={"agent_version": AGENT_VERSION})
    return entity


ENTITIES = {
    PG01: [_current(e) for e in agents.DISCOVERED_ENTITIES[PG01] if isinstance(e, DiscoveredComputer)],
    PG02: [
        *(_current(e) for e in agents.DISCOVERED_ENTITIES[PG02] if isinstance(e, DiscoveredComputer)),
        CLUSTER,
        NODE_01,
        NODE_02,
    ],
}
assert NODE_01.id == mnemonic("81000000", 7) and len(ENTITIES[PG02]) == 5

ENVIRONMENT = environment(discovered_entities=ENTITIES)

# ---- What a correct answer says, derived from the data above.

_COMPUTERS = {group: [e for e in entities if isinstance(e, DiscoveredComputer)] for group, entities in ENTITIES.items()}
_SERVERS = _COMPUTERS[PG02]
_SERVERS_COVERED = [e for e in _SERVERS if e.agent_status == "Installed"]
_FIN_01 = by_name(_COMPUTERS[PG01], "laptop-fin-01")
assert _FIN_01.last_connected is not None
_LAST_CONTACT = _FIN_01.last_connected
_AGE = T0 - _LAST_CONTACT  # 5 days 20 hours: "about 6 days"

EXPECTED = (
    f"No. {agents.PG_LAPTOPS.name}: the agent is installed on all 3 laptops, but laptop-hr-02 runs an older agent "
    f"({agents.OLD_AGENT_VERSION}, status UpgradeRequired) that should be upgraded - version drift, not a missing "
    f"agent - and laptop-fin-01 is Offline, last connected {_LAST_CONTACT:%Y-%m-%d %H:%M} by the server clock, about "
    f"6 days ago. {agents.PG_SERVERS.name}: {len(_SERVERS)} computers - srv-app-01, srv-app-02 and the two nodes of "
    "the failover cluster SQLCLUSTER01 (a container, not a computer of its own): sql-node-01 and sql-node-02. "
    "srv-app-01 and sql-node-02 have no agent installed; srv-app-02 has the agent but its driver waits for a reboot. "
    f"Coverage in {agents.PG_SERVERS.name}: {len(_SERVERS_COVERED)} of {len(_SERVERS)} computers (50%). Recommended: "
    "install the agent on srv-app-01 and sql-node-02 (a cluster is protected only when every node has it), reboot "
    "srv-app-02, upgrade laptop-hr-02, check why laptop-fin-01 is offline."
)
"""Ground truth for the judges."""

_NO_AGENT = any_of(
    r"not\s*installed",
    r"\bno\s+(veeam\s+)?agent",
    r"\bmissing",
    r"\bwithout\s+(an?\s+|the\s+)?(veeam\s+)?agent",
    r"\babsent",
    r"\black(s|ing)?\b",
    r"\bnot\s+(been\s+)?deployed",
    r"\b(un|not\s+)covered",
)
_OFF = any_of(
    r"off-?line",
    r"\bnot\s+(online|connected|reachable)",
    r"\bunreachable",
    r"\b(hasn't|has\s+not|not)\s+(been\s+)?(seen|connected|checked\s+in)",
    r"\blast\s+(connected|seen|contact)",
)

_OTHERS = r"(?:srv-app-0\d|sql-node-0\d|laptop-[a-z]+-\d+)"  # another computer: its own row begins


def _about(computer: str, condition: str) -> str:
    """``condition`` said of ``computer``, not of the computer next to it in the answer.

    As ``patterns.about`` reads it ("srv-app-01 and sql-node-02 have no agent", "No agent: srv-app-01, sql-node-02"),
    or heading a bullet list that holds it ("No agent installed:", then a "- srv-app-01" line): a heading names no
    computer, so a condition in another computer's bullet ("- srv-app-02: reboot pending") heads nothing.
    """
    heading = rf"(?<![^\n])(?:(?!{_OTHERS})[^\n]){{0,80}}?(?:{condition})(?:(?!{_OTHERS})[^\n]){{0,80}}\n"
    listed = rf"{heading}(?:[ \t]*[-*+][^\n]{{0,80}}\n){{0,5}}[ \t]*[-*+][ \t]*[^\n]{{0,10}}{computer}"
    return any_of(about(computer, condition, others=_OTHERS, within=160), listed)


FACTS = {
    "srv_app_01_no_agent": _about(r"srv-app-01", _NO_AGENT),
    "sql_node_02_no_agent": _about(r"sql-node-02", _NO_AGENT),
    "hr02_upgrade": _about(
        r"laptop-hr-02",
        any_of(r"upgrad", r"outdated", r"out[\s-]of[\s-]date", r"old(er)?\s+(agent\s+)?version", r"\b6\.3", r"updat"),
    ),
    "fin01_offline": _about(r"laptop-fin-01", _OFF),
    "srv_app_02_reboot": _about(r"srv-app-02", r"reboot|restart"),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    """No - not every computer is covered by a working agent.

**PG-Laptops** (3 computers)
- laptop-hr-01: agent installed, online - OK
- laptop-hr-02: agent installed but outdated (6.3.2.1205, status UpgradeRequired) - upgrade it; it is version drift, not a missing agent
- laptop-fin-01: agent installed, but the computer is Offline - last connected 2026-10-01 12:31, about 6 days ago

**PG-Servers** (4 computers; SQLCLUSTER01 is the failover cluster itself, a container, so I count its nodes instead)
- srv-app-01: no agent installed
- srv-app-02: agent installed, the driver needs a reboot to finish
- sql-node-01 (SQLCLUSTER01 node): agent installed - OK
- sql-node-02 (SQLCLUSTER01 node): agent not installed

Coverage in PG-Servers is 2 of 4 computers. Next steps: deploy the agent to srv-app-01 and sql-node-02, reboot srv-app-02, upgrade laptop-hr-02 and find out why laptop-fin-01 has been offline since October 1st.""",
    """Short answer: no.

| Group | Computer | Agent | Notes |
|---|---|---|---|
| PG-Laptops | laptop-hr-01 | Installed | fine |
| PG-Laptops | laptop-hr-02 | UpgradeRequired | older agent version - needs an upgrade |
| PG-Laptops | laptop-fin-01 | Installed | offline, last seen Oct 1 (almost 6 days) |
| PG-Servers | srv-app-01 | Not installed | uncovered |
| PG-Servers | srv-app-02 | Installed | pending restart for the driver |
| PG-Servers | sql-node-01 | Installed | node of SQLCLUSTER01 |
| PG-Servers | sql-node-02 | Not installed | node of SQLCLUSTER01 - the cluster is only half covered |

SQLCLUSTER01 is a cluster object, not a computer, so it is not counted on its own.""",
    (
        "No. srv-app-01 and sql-node-02 have no agent installed; srv-app-02 has the agent but its driver waits for a "
        "reboot. laptop-hr-02 runs an older agent and should be upgraded, and laptop-fin-01 is offline (last connected "
        "on 2026-10-01). SQLCLUSTER01 is the cluster, a container of its two nodes."
    ),
]

BAD = {
    "sql_node_02_no_agent": (
        "PG-Servers: srv-app-01 has no agent installed and srv-app-02 needs a reboot. SQLCLUSTER01 is a cluster "
        "container, not a computer, so it is skipped. PG-Laptops: laptop-hr-02 needs an upgrade, laptop-fin-01 is "
        "offline."
    ),
    "srv_app_01_no_agent": (
        "srv-app-01 and srv-app-02 both have the agent; srv-app-02 waits for a reboot. sql-node-02 lacks the agent. "
        "laptop-hr-02 needs an upgrade and laptop-fin-01 is offline."
    ),
    "hr02_upgrade": (
        "laptop-hr-02 has no agent at all. srv-app-01 and sql-node-02 have no agent installed, srv-app-02 needs a "
        "reboot, laptop-fin-01 is offline."
    ),
    "srv_app_02_reboot": (
        "srv-app-02 has no agent installed and srv-app-01 needs a reboot; laptop-fin-01 needs an upgrade and "
        "laptop-hr-02 is offline. sql-node-02 is missing the agent."
    ),
    "fin01_offline": (
        "srv-app-01 and sql-node-02 have no agent installed, srv-app-02 needs a reboot. laptop-fin-01 needs an upgrade "
        "and laptop-hr-02 is offline."
    ),
}

_ALLOWED = (
    "It is acceptable, and not a violation, to recommend installing the agent on srv-app-01 and sql-node-02, "
    "upgrading laptop-hr-02, rebooting srv-app-02 or checking laptop-fin-01, as advice; to give agent version "
    "numbers; to count PG-Laptops coverage either as 3 of 3 (by install) or 2 of 3 (by a plain Installed status) "
    "when the output says which it counts; and to add that no backup job includes the PG-Servers computers "
    "(Agent-Laptops covers only the laptops), so an installed agent there does not mean a backup."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G2-10",
        inputs=CaseInputs(
            question="Are all computers in our protection groups actually covered by a working Veeam Agent?",
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G2", "base_stand": "1.14"},
        evaluators=[
            # one call per group; get_server_status (what "now" is) is a read the case allows on top
            ToolCorrectness(
                expected_tools=[
                    "list_protection_groups",
                    "get_protection_group_entities",
                    "get_protection_group_entities",
                ],
                allow_extra=True,
            ),
            *tool_budget(4),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "cluster_not_a_computer",
                "The output does not count SQLCLUSTER01 itself as a computer, with or without an agent: it is the "
                "failover cluster, a container whose nodes sql-node-01 and sql-node-02 are the computers.",
            ),
            _judge(
                "cluster_not_covered",
                "The output does not present SQLCLUSTER01 or its SQL servers as fully covered: its node sql-node-02 "
                "has no agent.",
            ),
            _judge(
                "upgrade_is_not_missing",
                "The output does not present laptop-hr-02 (agent status UpgradeRequired) as a computer without an "
                "agent: it has an older agent version installed.",
            ),
            _judge(
                "servers_coverage",
                "If the output gives PG-Servers' coverage as a ratio or a percentage, it counts the four computers "
                "(srv-app-01, srv-app-02, sql-node-01, sql-node-02) and not the cluster: 2 of 4, or 50%. An output "
                "that names the uncovered computers without a ratio meets this criterion.",
            ),
            _judge(
                "staleness_by_server_clock",
                "If the output gives laptop-fin-01's last contact as an age or a date, it is about 6 days ago (last "
                "connected 2026-10-01 12:31 by the server clock) as in the expected output, not an age that "
                "contradicts this. Do not use your own notion of the current date; compare only with the expected "
                "output.",
            ),
        ],
    )
