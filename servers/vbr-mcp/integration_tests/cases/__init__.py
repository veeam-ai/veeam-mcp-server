# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""The cases of the test plan: one subpackage per group (``g1``, ``g2``, ...), one module per case.

Each case module exposes ``case(judge_model)``, which builds its ``Case``: the question, the VBR data it is asked
against (the base stand of ``stand/`` plus the case's own changes), what a correct answer says (derived from that
data, so the two cannot drift apart) and its evaluators. A module may also give answers to check its facts against
offline (``check.py``): ``GOOD``, answers a correct agent could give, which must state every fact, and ``BAD``, a
fact name -> an answer that must not state it.

``patterns`` holds the regex building blocks the facts share.
"""

import pkgutil
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic_ai.models import Model
from pydantic_evals.evaluators import Evaluator, LLMJudge, MaxModelRequests, MaxToolCalls

from vbr_mock.server import Mockable


def modules() -> list[str]:
    """Every module under ``cases/``, in order: a case module exposes ``case``, a shared one (``patterns``) does not."""
    return sorted(info.name for info in pkgutil.walk_packages(__path__, prefix=f"{__name__}.") if not info.ispkg)


def picks(name: str, case_name: str | None) -> bool:
    """Whether ``name``, given on the command line, selects the case ``case_name``: its name, or its group (G2)."""
    return case_name is not None and (case_name == name or case_name.startswith(f"{name}-"))


Environment = dict[str, Mockable]
"""VBR route -> its response: a model is served as is, a list of models paged like VBR, a string as plain text, a
``VbrError`` as that error, a ``VbrSequence`` step by step and a ``VbrAction`` as an action VBR performs. A route
may name its verb, ``"POST /api/v1/jobs/{id}/start"``; one path can then be mocked once per verb."""


Done = Callable[[list[dict[str, Any]]], bool]
"""Whether an action is complete, judged by the requests VBR received since the last plain question (as ``run.py``
records them, ``evaluators.matching`` reads them)."""


class FollowUp(BaseModel):
    """A later turn that is asked only if the conversation still needs it.

    Typically the user's "yes" to an agent that asked to confirm an action: when the agent has already called one
    of ``unless_called`` successfully since the last plain question, there is nothing left to confirm, and the turn
    is skipped instead of confirming an action that already ran (or prompting a second one). ``done`` decides
    instead, from the requests VBR received since: an action on several targets is not done after its first call
    (an agent that changed one and asks before the next still gets its answer), and a write VBR refuses is done
    once it was tried.
    """

    text: str
    unless_called: frozenset[str] = Field(default=frozenset(), exclude=True)
    done: Done | None = Field(default=None, exclude=True)


def confirm(*tools: str, text: str = "Yes, go ahead.", done: Done | None = None) -> FollowUp:
    """The user's confirmation of an action the agent asked about, skipped if it already called one of ``tools``.

    Name the action in ``text`` whenever the agent may have offered more than one ("Yes, disable Daily-VMs only."):
    a bare "yes" to a question with options leaves it to the agent which one was confirmed. For an action on several
    targets, or one VBR refuses, pass ``done``: the turn is skipped once it holds.
    """
    return FollowUp(text=text, unless_called=frozenset(tools), done=done)


TIMEOUT_SEC = 3
"""vbr-mcp's request timeout for a case whose VBR never answers (``vbr="timeout"``), not the default 30 s."""


class CaseInputs(BaseModel):
    """What a case runs: a question, asked against a VBR that serves ``environment``."""

    question: str
    follow_ups: list[str | FollowUp] = []
    """Later turns of the same conversation, asked in order after ``question``. The run's output is then every
    turn's answer, each headed ``[Turn N]``; a ``FollowUp`` the conversation no longer needs is skipped, and its
    heading says so."""
    environment: Environment = Field(default_factory=dict, exclude=True)
    """Excluded from serialization, so the judges see the questions only."""
    vbr: Literal["mock", "unreachable", "wrong_password", "timeout", "untrusted_tls"] = Field(
        default="mock", exclude=True
    )
    """How vbr-mcp reaches VBR: the mock serving ``environment``, a port nothing listens on, the mock with a password
    it rejects, a server that accepts connections and never answers, or the mock over HTTPS with a self-signed
    certificate (VBR's default) that vbr-mcp, verifying TLS as it does by default, does not trust."""

    @property
    def turns(self) -> list[str]:
        return [self.question, *(turn if isinstance(turn, str) else turn.text for turn in self.follow_ups)]


MULTI_TURN = (
    "The output holds every turn's answer, each headed [Turn N]; a turn the agent did not need is marked as not asked."
)
"""How a multi-turn case's output reads, for its judges' ``allowed``."""

_ONE_CRITERION = (
    "Judge only the criterion above. Other requirements of the case are checked separately: a gap the criterion "
    "does not mention must not fail it."
)


def judge(name: str, rubric: str, model: Model, *, allowed: str) -> LLMJudge:
    """An LLM judge asserting ``rubric``, told what the case allows so allowed remarks are not read as violations.

    Each judge checks one item of the case; it is told so, or a single gap in the answer fails every judge.
    """
    return LLMJudge(
        rubric=f"{rubric} {allowed} {_ONE_CRITERION}",
        model=model,
        include_input=True,
        include_expected_output=True,
        assertion={"evaluation_name": name, "include_reason": True},
    )


EXTRA_CALLS = 15
"""Calls a run may make beyond the ones its case expects: extra reads, re-checks of the state after an action, a retry
with corrected arguments, a thorough look around. None of these is a mistake (test plan 0.1), so the budget is wide:
it stops a run that runs away. A call repeated in a loop is ``NoRepeatedCalls``'s to catch."""


def tool_budget(calls: int, *, turns: int = 1) -> list[Evaluator]:
    """Budgets for a case that expects ``calls`` tool calls over ``turns`` questions, with ``EXTRA_CALLS`` to spare.

    The budget is a guard against a run that runs away, not a check of the trajectory: which tools are called is
    asserted by ``ToolCorrectness``/``ToolsCalled`` and ``ToolsNotCalled``, and a call repeated in a loop by
    ``NoRepeatedCalls``, which ``run.py`` adds to every case.
    """
    return [
        MaxToolCalls(max_calls=calls + EXTRA_CALLS),
        MaxModelRequests(max_requests=calls + EXTRA_CALLS + turns),
    ]
