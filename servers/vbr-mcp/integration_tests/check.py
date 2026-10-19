# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""Check every case offline, with no LLM and no vbr-mcp: what can be wrong with a case before a run shows it.

    uv run check.py               # every case
    uv run check.py G3-14 G1      # these cases, or groups

A fact that fails a correct answer, or passes a wrong one, costs a run to find and then reads as the model's fault.
So each case's facts are matched against the answers the case module gives (``GOOD``: every fact must match, also
after the Unicode a model writes - non-breaking hyphens and spaces, Markdown emphasis -, which ``normalize`` must
fold back to the answer as written; ``BAD``: fact name -> an answer that must not match it), and to the case's own
``EXPECTED``, the answer its judges hold the agent to. And the case's references are checked against what exists:
tool names against vbr-mcp's tools; ``VbrRequested`` and ``VbrNotRequested`` paths and verbs against the requests
vbr-mcp's tools can send (read from its source) - a check of a request it never sends checks nothing - and, where only
an accepted request counts, against a route the environment mocks that can accept it; turn numbers against its
turns; the environment's collections against the base stand's. Exits non-zero on any problem.
"""

import ast
import functools
import importlib
import re
import sys
from collections.abc import Iterator
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

from pydantic_ai.models.test import TestModel
from pydantic_evals.evaluators import ToolCorrectness

import cases
import stand
from cases import CaseInputs, Environment, FollowUp
from evaluators import (
    TOOLS,
    Fact,
    FactsPresent,
    ToolsCalled,
    ToolsNotCalled,
    VbrNotRequested,
    VbrRequested,
    normalize,
)
from vbr_mock.markers import VbrAction, VbrError, VbrSequence
from vbr_mock.server import endpoint, split_route

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)


def perturbed(answer: str) -> Iterator[tuple[str, str]]:
    """``answer`` as models also write it: the same words in other code points, and with Markdown emphasis."""
    yield "non-breaking hyphens", answer.replace("-", "\u2011")
    yield "no-break spaces", answer.replace(" ", "\u00a0")
    yield "narrow no-break spaces", re.sub(r"(\d) ", "\\1\u202f", answer)
    yield "curly apostrophes", answer.replace("'", "\u2019")
    yield "bold names", re.sub(r"\b([A-Za-z]+-[A-Za-z0-9-]+)\b", r"**\1**", answer)


def _routes(environment: Environment) -> list[tuple[str | None, str, Any]]:
    """Every route an environment mocks, also those an action mocks once it is accepted: ``(verb, path, data)``.

    The verb is ``None`` for a route that answers either verb.
    """
    found: list[tuple[str | None, str, Any]] = []

    def visit(route: str, data: Any) -> None:
        verb, path = split_route(route)
        found.append((verb, path, data))
        if isinstance(data, VbrAction):
            for effect_route, effect in data.effects.items():
                visit(effect_route, effect)
        elif isinstance(data, VbrSequence):
            for step in data.steps:
                visit(route, step)

    for route, data in environment.items():
        visit(route, data)
    return found


def _path(route: str) -> str:
    """A route's path without its verb or the slashes around it, as the mock's store keys it."""
    return split_route(route)[1].strip("/")


def _can_succeed(data: Any) -> bool:
    """Whether a route mocked with ``data`` can answer a request with success: not an error at every step."""
    if isinstance(data, VbrSequence):
        return any(_can_succeed(step) for step in data.steps)
    return not isinstance(data, VbrError)


# ---- The requests vbr-mcp's tools send, read from its source

_TOOLS_SOURCE = Path(__file__).resolve().parent.parent / "src" / "vbr_mcp" / "tools"
_CLIENT_VERBS = {"get": "GET", "post": "POST", "post_text": "POST"}
_PAGING_HELPERS = {"fetch_all", "fetch_total"}  # (client, path, ...): pages with GET


def _strings(node: ast.expr, constants: dict[str, list[str]]) -> list[str]:
    """The texts an expression of a tool module can evaluate to, a placeholder ``{...}`` for any value it formats in."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.Name):
        return constants.get(node.id, [])
    if isinstance(node, ast.JoinedStr):
        texts = [""]
        for part in node.values:
            if isinstance(part, ast.FormattedValue):
                options = _strings(part.value, constants) or ["{...}"]
            else:
                options = _strings(part, constants)
            texts = [text + option for text in texts for option in options]
        return texts
    if isinstance(node, ast.Dict):
        return [text for value in node.values if value is not None for text in _strings(value, constants)]
    if isinstance(node, ast.Subscript):  # _PATHS[kind]: any of the mapping's values
        return _strings(node.value, constants)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format":
        return _strings(node.func.value, constants)
    return []


@functools.cache
def vbr_mcp_requests() -> frozenset[tuple[str, str]]:
    """Every ``(verb, path glob)`` vbr-mcp's tools can send to VBR, a path parameter read as ``*``."""
    found = set()
    for source in sorted(_TOOLS_SOURCE.glob("*.py")):
        tree = ast.parse(source.read_text())
        constants: dict[str, list[str]] = {}
        for statement in tree.body:
            if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
                target = statement.targets[0]
                if isinstance(target, ast.Name):
                    constants[target.id] = _strings(statement.value, constants)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "vbr_client"
                and func.attr in _CLIENT_VERBS
                and node.args
            ):
                verb, path = _CLIENT_VERBS[func.attr], node.args[0]
            elif isinstance(func, ast.Name) and func.id in _PAGING_HELPERS and len(node.args) > 1:
                verb, path = "GET", node.args[1]
            else:
                continue
            found |= {
                (verb, re.sub(r"\{[^{}]*\}", "*", text))
                for text in _strings(path, constants)
                if text.startswith("/api/")
            }
    if not found:  # every request check would read as "never sent": the scan must not have found nothing
        raise RuntimeError(f"No VBR requests found in {_TOOLS_SOURCE}")
    return frozenset(found)


def _glob_tokens(glob: str) -> list[str]:
    """A path glob as ``fnmatch`` reads it: ``*``, ``?``, a ``[...]`` class or a single character per token."""
    return re.findall(r"\*|\?|\[!?\]?[^\]]*\]|.", glob.lower().rstrip("/"))


def _one_char(token: str, char: str) -> bool:
    return token == "?" or (token.startswith("[") and fnmatchcase(char, token)) or token == char


def _overlap(first: str, second: str) -> bool:
    """Whether the path globs ``first`` and ``second`` can match the same path (``*`` spans ``/``, as in ``fnmatch``).

    Two character classes are taken to share a character: a guess on the safe side, as overlap only clears a check.
    """
    a, b = _glob_tokens(first), _glob_tokens(second)

    @functools.cache
    def meet(i: int, j: int) -> bool:
        if i < len(a) and a[i] == "*":
            return meet(i + 1, j) or (j < len(b) and meet(i, j + 1))
        if j < len(b) and b[j] == "*":
            return meet(i, j + 1) or (i < len(a) and meet(i + 1, j))
        if i == len(a) or j == len(b):
            return i == len(a) and j == len(b)
        x, y = a[i], b[j]
        if len(x) == 1 and x != "?" and not _one_char(y, x):
            return False
        if len(y) == 1 and y != "?" and not _one_char(x, y):
            return False
        return meet(i + 1, j + 1)

    return meet(0, 0)


def _facts(case: Any) -> dict[str, Fact]:
    facts: dict[str, Fact] = {}
    for evaluator in case.evaluators:
        if isinstance(evaluator, FactsPresent):
            facts |= {name: spec if isinstance(spec, Fact) else Fact(spec) for name, spec in evaluator.facts.items()}
    return facts


def _check_environment(environment: Environment, stand_environment: Environment) -> list[str]:
    """Every route builds as the mock serves it; the base stand's own data (``stand_environment``) is built once."""
    problems = []
    for route, data in environment.items():
        if stand_environment.get(route) == data:
            continue
        try:
            endpoint(route, data)
        except Exception as exc:
            problems.append(f"route {route} does not build: {exc}")
    return problems


def _check_references(case: Any, tools: set[str]) -> list[str]:
    """Tool names, turns and VBR requests the evaluators and follow-ups name exist."""
    problems = []
    inputs: CaseInputs = case.inputs
    turns = len(inputs.turns)
    routes = _routes(inputs.environment)
    for evaluator in case.evaluators:
        kind = type(evaluator).__name__
        named: set[str] = set()
        if isinstance(evaluator, ToolCorrectness):
            named = set(evaluator.expected_tools)
        elif isinstance(evaluator, ToolsCalled | ToolsNotCalled):
            named = set(evaluator.tools)
        problems += [f"{kind} names {tool!r}, which vbr-mcp does not have" for tool in sorted(named - tools)]
        scoped = getattr(evaluator, "turns", None)
        if scoped and max(scoped) > turns:
            problems.append(f"{kind} checks turn {max(scoped)} of a {turns}-turn case")
        if isinstance(evaluator, VbrRequested | VbrNotRequested):
            problems += _check_request(evaluator, routes)
    for follow_up in inputs.follow_ups:
        if isinstance(follow_up, FollowUp):
            problems += [
                f"confirm() names {tool!r}, which vbr-mcp does not have"
                for tool in sorted(follow_up.unless_called - tools)
            ]
    return problems


def _check_request(evaluator: VbrRequested | VbrNotRequested, routes: list[tuple[str | None, str, Any]]) -> list[str]:
    """A request check names a request vbr-mcp sends, and one the environment can accept where only that counts.

    A path or verb vbr-mcp never sends makes the check pass (``VbrNotRequested``) or fail (``VbrRequested``) whatever
    the agent does; so does an accepted request no mocked route can answer with success.
    """
    kind, name = type(evaluator).__name__, evaluator.evaluation_name
    method, pattern = evaluator.method, evaluator.path
    if not any(verb == method and _overlap(pattern, glob) for verb, glob in vbr_mcp_requests()):
        return [f"{kind} {name}: vbr-mcp never sends {method} {pattern}, so it checks nothing"]
    if not evaluator.accepted:
        return []
    accepting = [
        path
        for verb, path, data in routes
        if verb in (None, method)
        and _can_succeed(data)
        and fnmatchcase(path.strip("/").lower(), pattern.strip("/").lower())
    ]
    if not accepting:
        return [f"{kind} {name}: no mocked route can accept {method} {pattern}, so it checks nothing"]
    return []


def _check_facts(facts: dict[str, Fact], turns: int) -> list[str]:
    problems = []
    for name, fact in facts.items():
        try:
            re.compile(fact.pattern)
        except re.error as exc:
            problems.append(f"fact {name}: does not compile: {exc}")
            continue
        if any(normalize(char) != char for char in fact.pattern):
            problems.append(f"fact {name}: has a typographic character the answer is normalized away from")
        if fact.turns and max(fact.turns) > turns:
            problems.append(f"fact {name}: in turn {max(fact.turns)} of a {turns}-turn case")
    return problems


def _check_answers(facts: dict[str, Fact], module: Any) -> list[str]:
    """Every fact matches every ``GOOD`` answer, also as models write it, and misses its ``BAD`` one."""
    problems = []
    good: list[str] = list(getattr(module, "GOOD", []))
    bad: dict[str, str] = dict(getattr(module, "BAD", {}))
    if facts and not good:
        problems.append("no GOOD answers to check its facts against")
    for n, answer in enumerate(good, 1):
        problems += [
            f"fact {name} fails GOOD[{n}]: {fact.describe()}" for name, fact in facts.items() if not fact.search(answer)
        ]
        problems += [
            f"GOOD[{n}] with {variant} does not normalize to it as written: a fact would read another text"
            for variant, text in perturbed(answer)
            if normalize(text) != normalize(answer)
        ]
    for name, answer in bad.items():
        if name not in facts:
            problems.append(f"BAD names fact {name!r}, which the case does not have")
        elif facts[name].search(answer):
            problems.append(f"fact {name} passes its BAD answer: {facts[name].describe()}")
    return problems


_EXPECTED_TURN = re.compile(r"^\[Turn (\d+)\][ \t]*\n?", re.MULTILINE)


def as_output(expected: str) -> str:
    """A case's ``EXPECTED`` as ``run.py``'s output reads: every ``[Turn N]`` heading on a line of its own."""
    return _EXPECTED_TURN.sub(lambda heading: f"[Turn {heading.group(1)}]\n", expected)


def _check_expected(facts: dict[str, Fact], case: Any, module: Any) -> list[str]:
    """Every fact matches the case's own ``EXPECTED``: the judges hold the agent to it, so a fact must not fail it.

    ``EXPECTED_SKIPS`` (fact name -> why) exempts a fact ``EXPECTED`` does not state as an answer would, e.g. where
    it describes the alternatives the case accepts instead of giving one.
    """
    expected = case.expected_output
    if not isinstance(expected, str) or not facts:
        return []
    skips: dict[str, str] = dict(getattr(module, "EXPECTED_SKIPS", {}))
    problems = [
        f"EXPECTED_SKIPS names fact {name!r}, which the case does not have" for name in skips if name not in facts
    ]
    output = as_output(expected)
    problems += [
        f"fact {name} fails the case's own EXPECTED: {fact.describe()}"
        for name, fact in facts.items()
        if name not in skips and not fact.search(output)
    ]
    problems += [
        f"fact {name} matches EXPECTED, yet EXPECTED_SKIPS exempts it"
        for name in skips
        if name in facts and facts[name].search(output)
    ]
    return problems


def _check_stand(inputs: CaseInputs, stand_routes: set[str]) -> list[str]:
    """A case asked against the mock serves the base stand's collections: VBR always has them."""
    if inputs.vbr != "mock":
        return []
    mocked = {_path(route) for route in inputs.environment}
    missing = sorted(route for route in stand_routes if route not in mocked)
    return [f"lacks base-stand routes a read tool can ask for: {', '.join(missing)}"] if missing else []


def check_case(
    case: Any, module: Any, tools: set[str], stand_environment: Environment, stand_routes: set[str]
) -> list[str]:
    facts = _facts(case)
    return [
        *_check_environment(case.inputs.environment, stand_environment),
        *_check_references(case, tools),
        *_check_facts(facts, len(case.inputs.turns)),
        *_check_answers(facts, module),
        *_check_expected(facts, case, module),
        *_check_stand(case.inputs, stand_routes),
    ]


def _stand_collections(stand_environment: Environment) -> set[str]:
    """The base stand's routes that hold no id: they exist on every VBR, whatever it holds."""
    return {_path(route) for route in stand_environment if _UUID.search(route) is None}


def main(names: list[str]) -> int:
    tools = set(TOOLS)
    stand_environment = stand.environment()
    stand_routes = _stand_collections(stand_environment)
    stand_problems = _check_environment(stand_environment, {})
    for problem in stand_problems:
        print(f"stand: {problem}")  # noqa: T201
    seen: dict[str, str] = {}
    failed = 0
    checked = 0
    for module_name in cases.modules():
        try:
            module = importlib.import_module(module_name)
            case = module.case(TestModel()) if hasattr(module, "case") else None
        except Exception as exc:  # a module that does not load is a finding, not the end of the check
            print(f"{module_name}: does not load: {type(exc).__name__}: {exc}")  # noqa: T201
            failed += 1
            continue
        if case is None:
            continue
        if names and not any(cases.picks(name, case.name) for name in names):
            continue
        checked += 1
        problems = check_case(case, module, tools, stand_environment, stand_routes)
        if case.name in seen:
            problems.append(f"name taken by {seen[case.name]} too")
        seen[case.name] = module_name
        for problem in problems:
            print(f"{case.name}: {problem}")  # noqa: T201
        failed += bool(problems)
    print(f"{checked} cases checked, {failed} with problems.")  # noqa: T201
    return 1 if failed or stand_problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
