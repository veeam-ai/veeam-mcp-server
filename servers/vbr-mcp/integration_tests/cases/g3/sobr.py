# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""SOBR-Prod's extent actions as VBR performs them, for the G3 cases on maintenance mode, sealed mode and evacuation.

Each action changes exactly the extents its body names, starting from the state the earlier actions left: the mock
holds no state of its own, so every accepted action mocks the next actions with the new state (``effects_of``). Taking
one extent out of maintenance therefore leaves the other as it is, and two requests do what one request for both
does. An extent busy with a task goes ``Pending`` rather than into maintenance (User Guide v13, sobr_maintenance).
"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext

from cases import Environment
from cases.patterns import any_of
from evaluators import VbrRequested, body_ids, matching, requests
from stand import repositories
from stand.ids import FIRST_G3_SESSION, R05, R06, R07, S01
from stand.sessions import started
from vbr_mock.markers import VbrAction, VbrError
from vbr_models.infrastructure import ExtentStatus, PerformanceExtent, PerformanceTier, ScaleOutRepository
from vbr_models.sessions import Session

SOBR_PATH = "/api/v1/backupInfrastructure/scaleOutRepositories"
_STAND_EXTENTS = repositories.SCALE_OUT_REPOSITORIES[0].performance_tier.performance_extents
EXTENTS: dict[UUID, str] = {extent.id: extent.name for extent in _STAND_EXTENTS}
EXT_01, EXT_02, EXT_03 = R05, R06, R07

_MODES: dict[str, tuple[ExtentStatus, bool]] = {
    "enableMaintenanceMode": ("Maintenance", True),
    "disableMaintenanceMode": ("Maintenance", False),
    "enableSealedMode": ("Sealed", True),
    "disableSealedMode": ("Sealed", False),
}

Modes = dict[UUID, frozenset[ExtentStatus]]
"""Extent -> the modes it is in: ``Maintenance``, ``Pending`` (maintenance asked for, a task still running), ``Sealed``.
An extent in none is ``Normal``. Sealed and maintenance can be on together (User Guide v13, sobr_seal)."""

STAND_MODES: Modes = {extent.id: frozenset(extent.status) - {"Normal"} for extent in _STAND_EXTENTS}
"""The base stand: SOBR-Ext-03 is in maintenance."""


def extent(number: int) -> str:
    """An extent's name as answers write it: ``SOBR-Ext-01``, ``Ext-01``, ``Ext 01``."""
    return rf"(?:SOBR[-\s]?)?Ext[-\s]?0{number}\b"


ONLY = any_of(
    r"\b(only|left|remains?|remaining|single|sole|lone|alone)\b",
    r"\bjust\s+(?:one|(?:SOBR[-\s]?)?Ext)",
    r"\blast\s+(?:remaining\s+|writable\s+|usable\s+|healthy\s+)?(?:extent|one)\b",
)
"""An extent named as the one left for new backups."""

_RESTORES = r"\brestor(?:es?|ing|e\s+(?:operations?|jobs?|sessions?|tasks?))\b(?!\s+points?)"
_SAME_CLAUSE = (
    r"(?:(?![;\n]|[.!?](?=\s|$)|\b(?:but|and|while|whereas|only|still|keeps?|continues?|works?|working|fine|"
    r"unaffected)\b)[^\n]){0,100}?"
)
"""What may stand between "restores" and what is said of them: their qualifier ("from backup files on it - including
chains partly stored on it -"), not another clause or a predicate of their own ("still work", "keep working")."""

RESTORE_BLOCKED = any_of(
    rf"{_RESTORES}{_SAME_CLAUSE}\b(?:unavailable|blocked|impossible|disabled|not\s+(?:be\s+)?(?:possible|available|"
    r"allowed|supported)|fail|stop)\b",
    rf"{_RESTORES}{_SAME_CLAUSE}\b(?:isn't|is\s+not|aren't|are\s+not|won't\s+be|will\s+not\s+be|wouldn't\s+be)\s+"
    r"(?:possible|available|allowed|supported)\b",
    rf"{_RESTORES}{_SAME_CLAUSE}\b(?:won't|will\s+not|wouldn't|would\s+not|can't|cannot|can\s+not)\s+"
    r"(?:work|run|succeed|happen)\b",
    r"\b(?:can\s*not|can't|cannot|couldn't|could\s+not|won't|will\s+not|unable\s+to|not\s+be\s+able\s+to|"
    r"won't\s+be\s+able\s+to)\s+(?:be\s+)?(?:\w+\s+){0,3}?restor",
    r"\bno\s+(?:more\s+)?restores?\b",
    r"\b(?:blocks?|prevents?|stops?|disables?|rules?\s+out)\s+(?:\w+\s+){0,3}?restor",
    r"\b(?:not\s+restorable|unrestorable)\b",
)
"""Restores from the extent stop working - not merely "no new backups": "Restores still work; only new backup writes are
blocked" says the opposite."""


def path(action: str, sobr_id: UUID = S01) -> str:
    """``POST .../scaleOutRepositories/{sobr_id}/{action}``."""
    return f"{SOBR_PATH}/{sobr_id}/{action}"


def sobr(modes: Modes) -> ScaleOutRepository:
    """SOBR-Prod with its performance extents in ``modes``."""
    base = repositories.SCALE_OUT_REPOSITORIES[0]
    extents = [
        PerformanceExtent(id=extent, name=name, status=sorted(modes[extent]) or ["Normal"])
        for extent, name in EXTENTS.items()
    ]
    return base.model_copy(update={"performance_tier": PerformanceTier(performance_extents=extents)})


def _named(body: Any) -> set[str]:
    return body_ids(body, "repositoryIds")


def _not_extents(body: Any) -> VbrError | None:
    """VBR refuses a body naming no repository, or one that is not a performance extent of the SOBR in the path."""
    named = _named(body)
    if not named or named - {str(extent) for extent in EXTENTS}:
        return VbrError(
            status_code=400, message="The specified repository is not an extent of this scale-out repository."
        )
    return None


def _session(number: int) -> Session:
    """The RepositoryMaintenance session an extent action answers with (G3 sessions are numbered from S-ID20)."""
    return started(number, "SOBR-Prod extent maintenance", session_type="RepositoryMaintenance")


def extent_actions(
    modes: Modes = STAND_MODES, *, busy: frozenset[UUID] = frozenset(), number: int = FIRST_G3_SESSION
) -> Environment:
    """The four extent actions of SOBR-Prod, its extents in ``modes``.

    Each changes the extents its body names, and on acceptance mocks ``/scaleOutRepositories`` and the four actions
    anew, from the state it leaves. ``busy`` extents run a task, so maintenance leaves them ``Pending``.
    """

    def act(action: str) -> VbrAction:
        mode, on = _MODES[action]

        def effects(body: Any) -> dict[str, Any]:
            new = dict(modes)
            for extent in EXTENTS:
                if str(extent) not in _named(body):
                    continue
                current: set[ExtentStatus] = set(new[extent])
                if on:
                    current.add("Pending" if mode == "Maintenance" and extent in busy else mode)
                else:
                    current -= {"Maintenance", "Pending"} if mode == "Maintenance" else {mode}
                new[extent] = frozenset(current)
            return {SOBR_PATH: [sobr(new)], **extent_actions(new, busy=busy, number=number + 1)}

        return VbrAction(response=_session(number), reject=_not_extents, effects_of=effects)

    return {path(action): act(action) for action in _MODES}


WRONG_SOBR: Environment = {
    path(action, repository.id): VbrError(status_code=404, message="Scale-out backup repository not found.")
    for repository in repositories.REPOSITORIES
    for action in _MODES
}
"""A repository's id (an extent's, typically) where the SOBR's belongs: there is no such scale-out repository."""


def environment_routes(modes: Modes = STAND_MODES, *, busy: frozenset[UUID] = frozenset()) -> Environment:
    """What a case adds to ``stand.environment()`` for SOBR-Prod's extents.

    SOBR-Prod in ``modes``, its four extent actions, and the 404s of an extent id passed as the SOBR's.
    """
    return {SOBR_PATH: [sobr(modes)], **extent_actions(modes, busy=busy), **WRONG_SOBR}


def extents_in(
    sent: list[dict[str, Any]], action: str, turns: tuple[int, ...] | None = None, *, accepted: bool = True
) -> set[str]:
    """The extent ids of the ``action`` requests on SOBR-Prod among ``sent`` (in ``turns``; accepted ones by default)."""
    return {
        extent
        for request in matching(sent, path(action), turns=turns, accepted=accepted)
        for extent in _named(request["body"])
    }


def sent_extents(
    ctx: EvaluatorContext[Any, str, Any], action: str, turns: tuple[int, ...] | None = None, *, accepted: bool = True
) -> set[str]:
    """The extent ids of the ``action`` requests on SOBR-Prod in the run (see ``extents_in``)."""
    return extents_in(ctx.attributes.get("vbr_requests", []), action, turns, accepted=accepted)


@dataclass
class SobrIdNotAnExtent(Evaluator[Any, str, Any]):
    """Assert that no extent action named the SOBR's own id among the extents (``repositoryIds``).

    VBR refuses it, and the agent may then correct itself; the mix-up of the two ids is still the mistake. The other
    mix-up, an extent's id in the path, is ``VbrNotRequested`` on the path.
    """

    evaluation_name: str = "no_sobr_id_as_extent"

    def evaluate(self, ctx: EvaluatorContext[Any, str, Any]) -> dict[str, EvaluationReason]:
        mixed = [
            f"turn {request['turn']}: {request['path']}"
            for request in requests(ctx, f"{SOBR_PATH}*")
            if str(S01) in _named(request["body"])
        ]
        return {self.evaluation_name: EvaluationReason(value=not mixed, reason="; ".join(mixed) or "none")}


def id_mixups() -> list[Evaluator[Any, str, Any]]:
    """The mix-ups of SOBR-Prod's id and its extents' ids, each a mistake whether or not VBR refuses the request.

    An extent's id (``20000000-...``) in the path where the SOBR's belongs, and the SOBR's id among the extents.
    """
    return [
        VbrRequested("no_extent_id_as_sobr", path=f"{SOBR_PATH}/20000000-*", accepted=False, times=0),
        SobrIdNotAnExtent(),
    ]
