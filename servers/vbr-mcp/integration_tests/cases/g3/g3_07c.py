# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-07 (c): rescan vcenter01 - by its managed server id from VBR's list of managed servers, not its inventory id."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import CaseInputs, Environment, judge, tool_budget
from cases.patterns import STARTED
from evaluators import WRITE_TOOLS, FactsPresent, ToolsNotCalled, VbrNotRequested, VbrRequested
from stand import environment
from stand.ids import FIRST_G3_SESSION, M02
from stand.inventory import VCENTER
from stand.proxies import MANAGED_SERVER_LIST, MANAGED_SERVERS
from stand.repositories import REPOSITORIES
from stand.sessions import started
from vbr_mock.markers import VbrAction, VbrError

# ---- What VBR serves: the base stand, whose vcenter01 has its inventory objectId as VBR 13 gives it, a GUID (swagger
# ServersInventoryBrowserResultExample): a value that passes as a UUID is the trap of handing an inventory reference
# to rescan_managed_server, and VBR answers 404 for it. vcenter01's managed server id (M02) is in VBR's list of managed
# servers (GET /api/v1/backupInfrastructure/managedServers, read with api_get), where it is the ViHost of type VC; the
# hostIds of proxies, repositories and WAN accelerators are other servers'. A rescan is a write tool the user asked for
# by name, so the agent runs it without asking first (vbr-mcp's instructions); VBR answers it with the session it
# starts.

INFRASTRUCTURE = "/api/v1/backupInfrastructure"
VCENTER_OBJECT_ID = VCENTER.object_id
VCENTER_RESCAN_PATH = f"{INFRASTRUCTURE}/managedServers/{M02}/rescan"

SERVER_RESCAN_SESSION = started(FIRST_G3_SESSION, "Rescan of managed server", session_type="VolumesDiscover")

ENVIRONMENT: Environment = environment() | {
    f"GET {INFRASTRUCTURE}/managedServers": MANAGED_SERVER_LIST,
    **{
        f"{INFRASTRUCTURE}/managedServers/{server_id}/rescan": VbrAction(
            response=SERVER_RESCAN_SESSION,
            effects={f"/api/v1/sessions/{SERVER_RESCAN_SESSION.id}": SERVER_RESCAN_SESSION},
        )
        for server_id in MANAGED_SERVERS
    },
    # ids that are not managed servers: a repository's, vcenter01's inventory reference
    **{
        f"{INFRASTRUCTURE}/managedServers/{wrong_id}/rescan": VbrError(
            status_code=404, message="Managed server not found."
        )
        for wrong_id in [*(config.id for config in REPOSITORIES), VCENTER_OBJECT_ID]
    },
}

# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    f"A rescan of {VCENTER.name} has been started. Its managed server id, {M02}, comes from VBR's list of managed "
    f"servers, where it is the vCenter Server (ViHost, VC); its inventory objectId {VCENTER_OBJECT_ID} is a different "
    "id. The rescan is running, not finished."
)
"""Ground truth for the judges."""

FACTS = {
    "vcenter": r"vcenter01",
    "started": STARTED,
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    (
        f"I started a rescan of vcenter01.lab.local (managed server {M02}, from VBR's list of managed servers). It's "
        "running now; I can check its session when you want."
    ),
    (
        "Rescan of **vcenter01** kicked off. Note: the id it needs is the managed server id, not the inventory objectId "
        f"{VCENTER_OBJECT_ID} - VBR lists vcenter01 as a managed server with its own id. Not finished yet."
    ),
]
"""Answers a correct agent could give: every fact must match each."""

BAD = {
    "started": f"vcenter01's managed server id is {M02}. I can rescan it if you want.",
    "vcenter": "The rescan has started; it is still running.",
}
"""Fact -> an answer that misses it."""

_ALLOWED = (
    "It is acceptable, and not a violation, to give vcenter01's managed server id, to explain that the inventory "
    "objectId is a different id, to read the rescan's session, or to say what a rescan refreshes."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-07c",
        inputs=CaseInputs(question="Rescan vcenter01.", environment=ENVIRONMENT),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.6, 1.7"},
        evaluators=[
            # api_get(/api/v1/backupInfrastructure/managedServers) -> rescan_managed_server(M02) -> (opt.) the session.
            # list_vmware_hosts and browse_inventory give vCenter's inventory objectId, which is no managed server id.
            ToolCorrectness(expected_tools=["api_get", "rescan_managed_server"], allow_extra=True),
            *tool_budget(3),
            ToolsNotCalled(tools=WRITE_TOOLS - {"rescan_managed_server"}),
            VbrRequested("vcenter01_rescanned", path=VCENTER_RESCAN_PATH, accepted=True, times=1),
            VbrNotRequested(
                "no_other_server_rescanned",
                path=f"{INFRASTRUCTURE}/managedServers/*/rescan",
                accepted=True,
                besides=(VCENTER_RESCAN_PATH,),
            ),
            FactsPresent(facts=FACTS),
            _judge(
                "started_not_finished",
                f"The output says a rescan of {VCENTER.name} was started, and does not claim that it has completed.",
            ),
            _judge(
                "no_guessed_id",
                f"The output does not present vCenter's inventory objectId ({VCENTER_OBJECT_ID}) or another object's "
                f"id (a proxy's, a repository's, a WAN accelerator's or a host's) as vcenter01's managed server id, "
                f"which is {M02}.",
            ),
        ],
    )
