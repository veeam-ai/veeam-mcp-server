# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""Evaluate a Pydantic AI agent driving vbr-mcp against a mocked VBR, with Pydantic Evals.

    uv run run.py                 # every case
    uv run run.py G1-03 G1-07     # only these
    uv run run.py G2              # one group

Settings and secrets go in ``.env`` next to this script; copy ``.env.example`` and fill it in. The LLM is Azure
OpenAI, authenticated with an Azure AD service principal (no API key); the judges use the same deployment unless
``JUDGE_DEPLOYMENT`` names another one.

Nothing has to be started first. The run serves the VBR mock (``vbr_mock/``) in this process, and every run of
every case gets an environment of its own: its VBR data is mocked under a fresh environment id, and a vbr-mcp
server is started for it over stdio, logged in to the mock with that id as its VBR username. Runs are therefore
isolated from each other and can go in parallel. vbr-mcp runs from the repository's own project, as a user would
run it, and ignores the repository's ``.env``; its stderr (the fastmcp banner) is discarded. The agent gets the
server's instructions, as an MCP client that honors them passes them on.

Each turn of a conversation runs in a span with a ``turn`` attribute (1, 2, ...), so an evaluator can tell which
turn a tool was called in. Every request the run's vbr-mcp sent to the mock is handed to the evaluators as the
``vbr_requests`` attribute, each with the turn it was sent in: what VBR was asked to do, not only which tool the
agent picked. Every tool result the agent saw is handed over as ``tool_returns``.

The verdict has two tiers (``evaluators.HARD_EVALUATORS``). A hard assertion - the agent wrote when it must not,
made up an id, looped - fails the run on its first failure in any repeat. Facts, judges and trajectory checks vary
between runs of the same model, so they are held to a pass rate (``MIN_SOFT_PASS_RATE``) over the whole run instead.
The run exits non-zero if either fails, or if the mock itself raised serving a request (a bug in the case), and
writes its assertions to ``.results/last.json``, reporting those that passed in the previous run and fail now;
``.results/last_runs.json`` holds each run's answer, failed assertions and requests to VBR, to read a failure by. A
run of some cases replaces only their entries in both, so the other cases keep their baseline.
"""

import asyncio
import contextlib
import importlib
import ipaddress
import json
import os
import socket
import sys
import tempfile
from collections import defaultdict
from collections.abc import AsyncGenerator, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import logfire
from azure.identity import ClientSecretCredential, get_bearer_token_provider
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from fastmcp.client.transports import StdioTransport
from openai import AsyncAzureOpenAI
from pydantic_ai import Agent, ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.azure import AzureProvider
from pydantic_core import to_json
from pydantic_evals import Case, Dataset
from pydantic_evals.dataset import set_eval_attribute
from pydantic_evals.reporting import EvaluationReport

import cases
from cases import TIMEOUT_SEC, CaseInputs, FollowUp
from evaluators import HARD_EVALUATORS, NoInventedIds, NoRepeatedCalls, format_turns, not_asked
from settings import Settings
from vbr_mock.server import VbrMock

CaseFactory = Callable[[Model], Case[CaseInputs, str, dict[str, str]]]

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS = Path(__file__).resolve().parent / ".results"


def _case_factories() -> list[CaseFactory]:
    """``case`` of every case module under ``cases/`` (one subpackage per group), in module order.

    Adding a case is adding its module; a module without ``case`` (shared patterns) is not one.
    """
    return [module.case for name in cases.modules() if hasattr(module := importlib.import_module(name), "case")]


def _dataset(judge_model: Model, names: list[str]) -> Dataset[CaseInputs, str, dict[str, str]]:
    selected = [factory(judge_model) for factory in _case_factories()]
    if names:
        unknown = [name for name in names if not any(cases.picks(name, case.name) for case in selected)]
        if unknown:
            raise SystemExit(f"No such case or group: {', '.join(unknown)}")
        selected = [case for case in selected if any(cases.picks(name, case.name) for name in names)]
    # every case: no made-up ids, no loops
    return Dataset(name="vbr-mcp", cases=selected, evaluators=[NoInventedIds(), NoRepeatedCalls()])


def _closed_port_url() -> str:
    """A local URL nothing listens on, for a VBR that cannot be reached."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    return f"http://127.0.0.1:{port}"


@contextlib.asynccontextmanager
async def _silent_server() -> AsyncGenerator[str]:
    """A local URL that accepts connections and never answers, for a VBR that does not respond in time."""
    held: list[asyncio.StreamWriter] = []

    async def hold(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        held.append(writer)  # read nothing, answer nothing, keep the connection open

    server = await asyncio.start_server(hold, "127.0.0.1", 0)
    try:
        yield f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}"
    finally:
        for writer in held:
            writer.close()
        server.close()


def _self_signed_certificate(directory: Path) -> tuple[Path, Path]:
    """A certificate for 127.0.0.1 that no one signed, as a VBR server installs by default, and its key."""
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "vbr-lab01.lab.local")])
    now = datetime.now(UTC)
    certificate = (
        x509
        .CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), False)
        .sign(key, hashes.SHA256())
    )
    cert_file, key_file = directory / "vbr.crt", directory / "vbr.key"
    cert_file.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    return cert_file, key_file


def _vbr_mcp(base_url: str, environment_id: str, inputs: CaseInputs) -> MCPToolset:
    """A vbr-mcp server of its own for one run, logged in to the VBR at ``base_url`` as ``environment_id``.

    ``inputs.vbr`` picks ``base_url`` (see ``main``); ``wrong_password`` logs in with a password the mock rejects.
    """
    password = "not-the-password" if inputs.vbr == "wrong_password" else VbrMock.PASSWORD
    env = {
        "ENV_FILE_OVERRIDE": os.devnull,  # not the repository's .env, which points at a real VBR
        "VBR_BASE_URL": base_url,
        "VBR_USERNAME": environment_id,
        "VBR_PASSWORD": password,
    }
    if inputs.vbr == "timeout":
        env["VBR_REQUEST_TIMEOUT_SEC"] = str(TIMEOUT_SEC)
    return MCPToolset(
        StdioTransport(
            command="uv",
            args=["run", "--quiet", "--project", str(REPO_ROOT), "vbr-mcp"],
            env=env,
            keep_alive=False,
            log_file=Path(os.devnull),  # its stderr is only the fastmcp banner, once per run
        ),
        # A tool error (a 404, a 403, an unreachable VBR) goes back to the model as a retry; past the limit Pydantic
        # AI aborts the run. How the agent copes with errors is under test, so allow a few, and leave catching a loop
        # to the cases' tool budgets and NoRepeatedCalls.
        max_retries=3,
        include_instructions=True,  # as Claude, VS Code and other MCP clients pass the server's instructions on
        # A cold start under load (several servers at once, `uv run` checking the environment) can take longer than
        # Pydantic AI's default 5 s; a server that never starts is a failure of the run, not of the case.
        init_timeout=60,
    )


def _settled(follow_up: FollowUp, messages: list, sent: list[dict[str, Any]]) -> str | None:
    """The tool that already did what ``follow_up`` would confirm, or ``None`` while something is left to confirm.

    The agent has acted once it called one of ``unless_called`` successfully in ``messages``. With ``follow_up.done``
    that decides instead, from ``sent``, the requests VBR received since: an action on several targets is done once
    every target was acted on, a write VBR refused once it was tried.
    """
    if follow_up.done is None:
        return _called(messages, follow_up.unless_called)
    if not follow_up.done(sent):
        return None
    return _called(messages, follow_up.unless_called, failed=True) or min(follow_up.unless_called)


def _called(messages: list, tools: frozenset[str], *, failed: bool = False) -> str | None:
    """The first of ``tools`` the agent called successfully in ``messages`` (with ``failed``, at all), if any.

    A call that failed (VBR refused it, or vbr-mcp rejected its arguments) went back to the model as a retry
    prompt rather than a tool return: it did not act, so there is still something to confirm.
    """
    succeeded = {
        part.tool_call_id
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    }
    return next(
        (
            part.tool_name
            for message in messages
            if isinstance(message, ModelResponse)
            for part in message.parts
            if isinstance(part, ToolCallPart) and part.tool_name in tools and (failed or part.tool_call_id in succeeded)
        ),
        None,
    )


async def _warm_up() -> None:
    """Start vbr-mcp's environment once, so the first runs do not all pay for a cold start at the same time."""
    process = await asyncio.create_subprocess_exec(
        "uv", "run", "--quiet", "--project", str(REPO_ROOT), "python", "-c", "import vbr_mcp.server",
        env={**os.environ, "ENV_FILE_OVERRIDE": os.devnull},
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )  # fmt: skip
    await process.wait()


def _tool_returns(messages: list) -> list[str]:
    """What every successful tool call returned to the agent, as JSON text."""
    return [
        part.content if isinstance(part.content, str) else to_json(part.content, fallback=str).decode()
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    ]


# ---- The verdict


def _assertions(report: EvaluationReport[CaseInputs, str, dict[str, str]]) -> list[dict[str, Any]]:
    """Every assertion of every run, with its tier."""
    return [
        {
            "case": case.source_case_name or case.name,
            "assertion": name,
            "passed": bool(result.value),
            "hard": result.source.name in HARD_EVALUATORS,
            "reason": result.reason,
        }
        for case in report.cases
        for name, result in case.assertions.items()
    ]


def _unmocked(report: EvaluationReport[CaseInputs, str, dict[str, str]]) -> dict[str, set[str]]:
    """Per case, the routes its runs asked VBR for that the environment does not mock: gaps in the environment."""
    gaps: dict[str, set[str]] = defaultdict(set)
    for case in report.cases:
        for request in case.attributes.get("vbr_requests", []):
            if request.get("unmocked"):
                gaps[case.source_case_name or case.name].add(f"{request['method']} {request['path']}")
    return gaps


def _mock_errors(report: EvaluationReport[CaseInputs, str, dict[str, str]]) -> list[str]:
    """Every request the mock failed to serve because it raised itself: a bug in the case, not the agent's mistake.

    The agent read a bare 500 there, so whatever it made of it says nothing about the agent.
    """
    return sorted({
        f"{case.source_case_name or case.name}: the mock raised serving {r['method']} {r['path']}: {r['error']}"
        for case in report.cases
        for r in case.attributes.get("vbr_requests", [])
        if r.get("error")
    })  # fmt: skip


def _ran(report: EvaluationReport[CaseInputs, str, dict[str, str]]) -> set[str]:
    """The cases this run ran, also those whose every run raised."""
    return {case.source_case_name or case.name for case in [*report.cases, *report.failures]}


def _merged(file: Path, current: list[dict[str, Any]], ran: set[str]) -> list[dict[str, Any]]:
    """``current`` in place of what ``file`` holds for the cases in ``ran``; the other cases' entries kept."""
    previous = json.loads(file.read_text()) if file.exists() else []
    return [entry for entry in previous if entry["case"] not in ran] + current


def _runs(report: EvaluationReport[CaseInputs, str, dict[str, str]]) -> list[dict[str, Any]]:
    """Every run as it went - the answer, the failed assertions and what VBR was asked - to read a failure by."""
    return [
        {
            "case": case.source_case_name or case.name,
            "turns": case.inputs.turns,
            "output": case.output,
            "failed": {name: result.reason for name, result in case.assertions.items() if not result.value},
            "vbr_requests": [
                f"turn {r['turn']}: {r['method']} {r['path']} -> {r['status_code']}"
                + (f" {json.dumps(r['body'])}" if r.get("body") is not None else "")
                for r in case.attributes.get("vbr_requests", [])
            ],
        }
        for case in report.cases
    ] + [
        {
            "case": failure.source_case_name or failure.name,
            "turns": failure.inputs.turns,
            "error": failure.error_message,
        }
        for failure in report.failures
    ]


def _always(assertions: list[dict[str, Any]], *, passed: bool) -> set[tuple[str, str]]:
    """The ``(case, assertion)`` pairs that passed (or failed) in every run of ``assertions``."""
    outcomes: dict[tuple[str, str], set[bool]] = defaultdict(set)
    for a in assertions:
        outcomes[a["case"], a["assertion"]].add(a["passed"])
    return {key for key, seen in outcomes.items() if seen == {passed}}


def _verdict(report: EvaluationReport[CaseInputs, str, dict[str, str]], settings: Settings) -> int:
    """Print the two-tier verdict and the regressions against the previous run; the exit status."""
    assertions = _assertions(report)
    hard = [a for a in assertions if a["hard"] and not a["passed"]]
    errors = [f"{failure.name}: task raised {failure.error_message}" for failure in report.failures]
    errors += [
        f"{case.name}: {f.name} raised {f.error_message}" for case in report.cases for f in case.evaluator_failures
    ]
    errors += _mock_errors(report)
    soft = [a for a in assertions if not a["hard"]]
    passed = sum(a["passed"] for a in soft)
    rate = passed / len(soft) if soft else 1.0

    by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for a in soft:
        by_case[a["case"]].append(a)
    print("\nSoft assertions (facts, judges, trajectory) per case:", file=sys.stderr)  # noqa: T201
    for case, rows in sorted(by_case.items()):
        failed = sorted({a["assertion"] for a in rows if not a["passed"]})
        ok = sum(a["passed"] for a in rows)
        print(f"  {case:8} {ok:3}/{len(rows):<3} {', '.join(failed)}", file=sys.stderr)  # noqa: T201
    for case, routes in sorted(_unmocked(report).items()):
        print(f"NOTE {case}: asked for routes its environment lacks: {', '.join(sorted(routes))}", file=sys.stderr)  # noqa: T201
    for error in errors:
        print(f"ERROR {error}", file=sys.stderr)  # noqa: T201
    for a in hard:
        print(f"FAIL {a['case']}: {a['assertion']} ({a['reason']})", file=sys.stderr)  # noqa: T201

    RESULTS.mkdir(exist_ok=True)
    last, last_runs = RESULTS / "last.json", RESULTS / "last_runs.json"
    previous = json.loads(last.read_text()) if last.exists() else []
    for case, assertion in sorted(_always(previous, passed=True) & _always(assertions, passed=False)):
        print(f"REGRESSION {case}: {assertion} passed in the previous run", file=sys.stderr)  # noqa: T201
    # a run of some cases replaces only their results: the others' stay the baseline of the next run
    ran = _ran(report)
    last.write_text(json.dumps(_merged(last, assertions, ran), indent=1))
    last_runs.write_text(json.dumps(_merged(last_runs, _runs(report), ran), indent=1, ensure_ascii=False))

    print(  # noqa: T201
        f"\nHard: {len(hard)} failed, {len(errors)} errors. Soft: {passed}/{len(soft)} passed ({rate:.1%}, "
        f"minimum {settings.MIN_SOFT_PASS_RATE:.0%}).",
        file=sys.stderr,
    )
    return 1 if hard or errors or rate < settings.MIN_SOFT_PASS_RATE else 0


async def main(names: list[str]) -> int:
    os.environ["PYDANTIC_AI_NO_BANNER"] = "1"
    settings = Settings()
    # Span capture only: the agentic evaluators read tool calls from the local span tree. Nothing leaves the machine.
    logfire.configure(send_to_logfire=False, console=False)
    credential = ClientSecretCredential(
        settings.AZURE_TENANT_ID, settings.AZURE_CLIENT_ID, settings.AZURE_CLIENT_SECRET
    )
    client = AsyncAzureOpenAI(
        azure_endpoint=settings.AZURE_ENDPOINT,
        api_version=settings.AZURE_API_VERSION,
        azure_ad_token_provider=get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default"),
        max_retries=settings.LLM_MAX_RETRIES,
    )
    model = OpenAIChatModel(settings.AZURE_DEPLOYMENT, provider=AzureProvider(openai_client=client))
    judge_model = (
        OpenAIChatModel(settings.JUDGE_DEPLOYMENT, provider=AzureProvider(openai_client=client))
        if settings.JUDGE_DEPLOYMENT
        else model
    )

    await _warm_up()
    with tempfile.TemporaryDirectory() as certificates:
        cert_file, key_file = _self_signed_certificate(Path(certificates))
        async with VbrMock(tls=(cert_file, key_file)) as mock, _silent_server() as silent_url:
            base_urls = {
                "mock": mock.url,
                "wrong_password": mock.url,
                "unreachable": _closed_port_url(),
                "timeout": silent_url,
                "untrusted_tls": mock.tls_url,
            }

            async def answer(inputs: CaseInputs) -> str:
                environment_id = f"run-{uuid4().hex[:12]}"
                for route, data in inputs.environment.items():
                    mock.mock(environment_id, route, data)
                agent = Agent(
                    model,
                    toolsets=[_vbr_mcp(base_urls[inputs.vbr], environment_id, inputs)],
                    instructions="You are a Veeam Backup & Replication assistant. Answer using the VBR tools available to you.",
                )
                logfire.instrument_pydantic_ai(agent)  # tool-call spans for ToolCorrectness / MaxToolCalls
                answers: list[tuple[int, str]] = []
                requests: list[dict] = []
                messages: list | None = None
                turn = 0

                def collect_requests() -> None:  # those sent since the last call, as sent in the current turn
                    requests.extend(
                        request.model_dump(mode="json") | {"turn": turn}
                        for request in mock.requests(environment_id)[len(requests) :]
                    )

                try:
                    async with agent:  # starts this run's vbr-mcp, and stops it on the way out
                        # where the last plain question starts, in messages and in turns: a FollowUp answers what
                        # came after it
                        asked_from, asked_turn = 0, 1
                        for turn, question in enumerate([inputs.question, *inputs.follow_ups], 1):
                            if isinstance(question, FollowUp):
                                since = [request for request in requests if request["turn"] >= asked_turn]
                                if called := _settled(question, (messages or [])[asked_from:], since):
                                    answers.append((turn, not_asked(called)))
                                    continue
                                question = question.text
                            else:
                                asked_from, asked_turn = len(messages or []), turn
                            with logfire.span("turn {turn}", turn=turn):
                                result = await agent.run(question, message_history=messages)
                            messages = result.all_messages()
                            answers.append((turn, result.output))
                            collect_requests()
                finally:
                    collect_requests()
                    set_eval_attribute("vbr_requests", requests)
                    set_eval_attribute("tool_returns", _tool_returns(messages or []))
                    mock.delete(environment_id)
                return format_turns(answers)

            report = await _dataset(judge_model, names).evaluate(
                answer,
                repeat=settings.EVAL_REPEAT,
                max_concurrency=settings.EVAL_MAX_CONCURRENCY,
            )
    report.print(
        include_input=True,
        input_config={"value_formatter": lambda inputs: "\n".join(inputs.turns)},  # the questions, not the environment
        include_output=True,
        include_reasons=True,
        include_durations=False,
    )
    return _verdict(report, settings)


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
