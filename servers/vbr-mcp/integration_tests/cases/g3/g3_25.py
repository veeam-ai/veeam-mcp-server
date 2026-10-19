# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-25: update the Veeam components on every out-of-date server - the ones vbr-mcp can see, after confirming."""

from dataclasses import dataclass
from functools import partial
from typing import Any

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext, ToolCorrectness

import stand
from cases import MULTI_TURN, CaseInputs, Environment, confirm, judge, tool_budget
from cases.g3.actions import updated
from cases.patterns import OFFLINE
from evaluators import WRITE_TOOLS, Fact, FactsPresent, ToolsNotCalled, body_ids, requests
from stand import proxies, sessions
from stand.ids import FIRST_G3_SESSION, M04, M05, P03, T0
from vbr_mock.markers import VbrAction, VbrError, VbrSequence, VbrUpdate
from vbr_models.infrastructure import ProxyState
from vbr_models.sessions import Session, SessionResult

# ---- What VBR serves: the base stand (1.6: Proxy-02 on prx02 is offline and out of date, Proxy-03 on prx03 is
# disabled, online and out of date; no repository is out of date; managed servers show only as hostIds) and the
# components update. VBR updates what it can reach: prx03's components become current, prx02's update fails because
# the server is offline, and the session's result says so once it is over. Updating the two one after the other leaves
# both results in place.

UPDATE_PATH = "/api/v1/backupInfrastructure/managedServers/updateComponents"
PROXY_01, PROXY_02, PROXY_03 = proxies.PROXIES
PRX02_FAILED = f"Failed to update components on {proxies.MANAGED_SERVERS[M04]}: the server is not available."


def _not_managed_servers(body: Any) -> VbrError | None:
    if not body_ids(body, "ids") or body_ids(body, "ids") - {str(host) for host in proxies.MANAGED_SERVERS}:
        return VbrError(status_code=404, message="Managed server not found.")
    return None


def _started(named: set[str]) -> Session:
    """The session an update of ``named`` starts.

    Each set of servers updates in a session of its own (S-ID20-23), so a second update - of prx02 after prx03 - does
    not overwrite the first one's session.
    """
    number = FIRST_G3_SESSION + (str(M05) in named) + 2 * (str(M04) in named)
    return sessions.started(number, "Components update", session_type="HostComponentsUpdate")


def _effects(body: Any) -> dict[str, Any]:
    """The update's session runs and ends by what it was asked for; prx03 comes back up to date.

    The sessions list and the proxy states change in place, so an earlier update's session and prx03 stay as it left
    them.
    """
    named = body_ids(body, "ids")
    prx02, prx03 = str(M04) in named, str(M05) in named
    result, message = ("Success", "")
    if prx02:
        result, message = ("Warning", PRX02_FAILED) if prx03 else ("Failed", PRX02_FAILED)
    started = _started(named)
    finished = started.model_copy(
        update={
            "state": "Stopped",
            "end_time": T0,
            "progress_percent": 100,
            "result": SessionResult(result=result, message=message, is_canceled=False),
        }
    )
    working = started.model_copy(update={"state": "Working", "progress_percent": 40})
    listed = finished.model_dump(mode="json")
    effects: dict[str, Any] = {
        f"/api/v1/sessions/{started.id}": VbrSequence(steps=[working, finished]),
        "/api/v1/sessions": VbrUpdate(
            change=lambda rows: [listed, *(row for row in rows if row["id"] != listed["id"])]
        ),
        f"/api/v1/sessions/{started.id}/taskSessions": [],
        f"/api/v1/sessions/{started.id}/logs": sessions.log(T0, [("Succeeded", "Components update started")]),
    }
    if prx03:
        effects["/api/v1/backupInfrastructure/proxies/states"] = updated(ProxyState, P03, is_out_of_date=False)
    return effects


ENVIRONMENT: Environment = {
    **stand.environment(),
    UPDATE_PATH: VbrAction(
        response_of=lambda body: _started(body_ids(body, "ids")),
        status_code=201,
        reject=_not_managed_servers,
        effects_of=_effects,
    ),
}


def _sent_ids(ctx: EvaluatorContext[Any, str, Any], *, accepted: bool) -> list[set[str]]:
    return [body_ids(r["body"], "ids") for r in requests(ctx, UPDATE_PATH, method=None, accepted=accepted)]


@dataclass
class OutOfDateServersUpdated(Evaluator[Any, str, Any]):
    """Assert that the update targeted the out-of-date managed servers: prx03 (M05), with or without prx02 (M04).

    Also that no request carried a proxy's id where a managed server id belongs.
    """

    def evaluate(self, ctx: EvaluatorContext[Any, str, Any]) -> dict[str, EvaluationReason]:
        accepted = set().union(*_sent_ids(ctx, accepted=True))
        sent = set().union(*_sent_ids(ctx, accepted=False))
        proxy_ids = {str(config.id) for config in proxies.PROXIES}
        return {
            "out_of_date_servers_updated": EvaluationReason(
                value=accepted in ({str(M05)}, {str(M04), str(M05)}), reason=f"accepted {sorted(accepted)}"
            ),
            "no_proxy_ids": EvaluationReason(value=not sent & proxy_ids, reason=f"sent {sorted(sent)}"),
        }


# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    f"[Turn 1] Out of date, as far as vbr-mcp can see: prx02.lab.local (host of {PROXY_02.name}, offline) and "
    f"prx03.lab.local (host of {PROXY_03.name}, disabled but online). vbr-mcp sees isOutOfDate only on proxies and "
    "repositories (no repository is out of date); there is no list of all managed servers, so other servers cannot "
    "be checked. No task runs through prx02 or prx03 now (only Proxy-01 can take tasks), so nothing is interrupted. "
    "prx02 is offline, so its update will most likely fail. Update prx03 (and try prx02)?\n"
    "[Turn 2] The components update has been started for prx03 (and prx02); check the session for the result - with "
    "prx02 included it ends with a warning: prx02 could not be reached, prx03 is up to date."
)
"""Ground truth for the judges."""

FACTS = {
    "prx02": Fact(r"prx02|Proxy-02", turns=(1,)),
    "prx03": Fact(r"prx03|Proxy-03", turns=(1,)),
    "offline": Fact(OFFLINE, turns=(1,)),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match: turn 1 names the targets."""

GOOD = [
    (
        "[Turn 1]\nTwo servers have out-of-date Veeam components, as far as I can see:\n- prx02.lab.local (Proxy-02) - "
        "offline, so an update there will likely fail;\n- prx03.lab.local (Proxy-03) - disabled but online.\nNo "
        "repository is out of date. I can only check proxies and repositories - there is no list of all managed servers - "
        "so other servers could not be checked. No jobs run through these two now. Update both?\n\n[Turn 2]\nThe "
        "components update has been started for prx02 and prx03. The session ended with a warning: prx02 is not "
        "available, prx03 was updated."
    ),
    (
        "[Turn 1]\n| Server | Role | State |\n|---|---|---|\n| prx02.lab.local | Proxy-02 | not online, out of date |\n| "
        "prx03.lab.local | Proxy-03 | disabled, out of date |\n\nUpdating may interrupt tasks running through these "
        "servers (none right now). Shall I update prx03, and try prx02?\n\n[Turn 2]\nUpdate started for prx03 and prx02."
    ),
]
"""Answers a correct agent could give: every fact must match each."""

BAD = {
    "offline": "[Turn 1]\nprx02 and prx03 have out-of-date components. Update them?\n\n[Turn 2]\nStarted.",
    "prx02": "[Turn 1]\nprx03 (Proxy-03) is out of date; another proxy is offline. Update prx03?\n\n[Turn 2]\nStarted "
    "for prx03 and prx02.",
}
"""Answers that miss one fact each: the fact must not match its answer."""

_ALLOWED = (
    f"{MULTI_TURN} "
    "It is acceptable, and not a violation, to update prx03 only or prx02 and prx03 together (with a caveat "
    "that prx02 is offline), to check the update session or list_proxies afterwards and report what they show, or to "
    "warn that an update may interrupt tasks running through those servers."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-25",
        inputs=CaseInputs(
            question="Update the Veeam components on all servers that are out of date.",
            follow_ups=[
                confirm("update_managed_server_components", text="Yes, update the out-of-date servers you listed.")
            ],
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.6"},
        evaluators=[
            # list_proxies -> (opt.) list_repositories, list_wan_accelerators, list_vmware_hosts, get_job_states ->
            # [confirmation] -> update_managed_server_components -> (opt.) the session, list_proxies.
            ToolCorrectness(expected_tools=["list_proxies", "update_managed_server_components"], allow_extra=True),
            *tool_budget(5, turns=2),
            ToolsNotCalled(
                tools=frozenset({"update_managed_server_components"}),
                turns=(1,),
                evaluation_name="no_update_before_confirmation",
            ),
            OutOfDateServersUpdated(),
            ToolsNotCalled(tools=WRITE_TOOLS - {"update_managed_server_components"}),
            FactsPresent(facts=FACTS),
            _judge(
                "visibility_limit",
                "The output says that out-of-date status is only visible for proxies and repositories (or that "
                "there is no full list of managed servers), so not every server could be checked.",
            ),
            _judge(
                "interruption_considered",
                "In turn 1 the output either cautions that the update may interrupt tasks running through those "
                "servers, or notes that no tasks run through them now; it does not claim the update is safe for "
                "jobs running through these servers without either.",
            ),
            _judge(
                "not_all_servers_claimed",
                "The output does not claim that all servers were updated, nor that prx02 was updated successfully: "
                "the update is reported as started, or with the result the session shows (prx02 not reachable).",
            ),
        ],
    )
