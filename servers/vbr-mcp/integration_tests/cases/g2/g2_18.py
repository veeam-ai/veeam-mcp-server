# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G2-18: a partial failure - the protection groups read fine, their computers answer 403."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import CaseInputs, judge, tool_budget
from cases.patterns import NOT_AUTHORIZED, any_of
from evaluators import FactsPresent, ToolsNotCalled
from stand import agents, environment
from stand.ids import PG01, PG02
from vbr_mock.markers import VbrError

# ---- What VBR serves: the base stand, read with an account that is no Veeam Backup Administrator. The protection
# groups (1.14) list for a Restore Operator too, but reading what a group discovered is for administrators only
# (swagger: GetAllProtectionGroups is available to Backup Administrator, Restore Operator and Tape Operator,
# GetDiscoveredEntities to Backup Administrator), so VBR answers it with 403 AccessDenied.

DENIED = VbrError(status_code=403, message="Access denied: insufficient permissions to perform this operation.")

ENVIRONMENT = environment() | {
    f"/api/v1/agents/protectionGroups/{group}/discoveredEntities": DENIED for group in (PG01, PG02)
}

# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    f"There are 2 protection groups: {agents.PG_LAPTOPS.name} (three computers listed in its configuration: "
    f"laptop-hr-01, laptop-hr-02, laptop-fin-01) and {agents.PG_SERVERS.name} (the Servers OU of lab.local). Their "
    "computers' agent status cannot be shown: reading a group's discovered entities requires the Veeam Backup "
    "Administrator role, and the account vbr-mcp uses is not authorized for it (VBR answered 403 AccessDenied). Run "
    "the report under an administrator account to get agent coverage."
)
"""Ground truth for the judges."""

FACTS = {
    "pg_laptops": r"PG-Laptops",
    "pg_servers": r"PG-Servers",
    "not_authorized": NOT_AUTHORIZED,
    "administrator": any_of(
        r"administrator",
        r"\badmin\b",
        r"\belevated\b",
        r"\bhigher\s+(privileges?|role|rights|permissions?|access)",
        r"\bfull\s+(rights|access|permissions?)",
        r"\bmore\s+(rights|privileges|permissions)",
    ),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    """I could only partly do this. There are two protection groups, **PG-Laptops** (laptop-hr-01, laptop-hr-02, laptop-fin-01 in its configuration) and **PG-Servers** (the lab.local/Servers OU), but reading the computers they discovered failed with 403 AccessDenied: the account vbr-mcp uses does not have the rights for it - that endpoint requires the Veeam Backup Administrator role. Rerun the report with an administrator account to see agent coverage.""",
    """Protection groups: PG-Laptops, PG-Servers.

Agent coverage: not available - VBR refused the request for the groups' discovered computers (insufficient privileges). Ask someone with an admin account, or grant the service account the Backup Administrator role, and run it again.""",
]

BAD = {
    "not_authorized": (
        "There are two protection groups, PG-Laptops and PG-Servers, but their computers could not be found: VBR "
        "says the discovered entities do not exist. Ask an administrator to rescan the groups."
    ),
    "administrator": (
        "PG-Laptops and PG-Servers exist, but listing their computers failed with 403 Forbidden. Try again later."
    ),
}

_ALLOWED = (
    "It is acceptable, and not a violation, not to ask for the second group's computers after the first was denied, "
    "to say which computers PG-Laptops lists in its own configuration (laptop-hr-01, laptop-hr-02, laptop-fin-01) "
    "or which OU PG-Servers covers, or to name the Veeam Restore Operator role as a likely current role."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G2-18",
        inputs=CaseInputs(question="Report on agent coverage in our protection groups.", environment=ENVIRONMENT),
        expected_output=EXPECTED,
        metadata={"group": "G2", "base_stand": "1.14"},
        evaluators=[
            # The entities read fails with a 403, so only a count that includes failed calls sees it. A retry of the
            # same denied call is caught by NoRepeatedCalls, which run.py adds to every case.
            ToolCorrectness(
                expected_tools=["list_protection_groups", "get_protection_group_entities"],
                allow_extra=True,
                include_failed=True,
            ),
            *tool_budget(3),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "no_invented_computers",
                "The output does not present an agent status, agent version or agent coverage of any computer as "
                "read from the protection groups: what they discovered could not be read. Naming the computers "
                "PG-Laptops lists in its own configuration is fine, and so is what other VBR data shows, presented "
                "as such - for example that laptop-fin-01 was offline in Agent-Laptops' last backup session, or "
                "when a laptop was last backed up.",
            ),
            _judge(
                "groups_not_empty",
                "The output does not claim that the protection groups have no computers.",
            ),
            _judge(
                "denied_not_missing",
                "The output presents the failure as missing permissions or access denied, not as the object or "
                "the groups not being found.",
            ),
        ],
    )
