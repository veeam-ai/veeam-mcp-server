# vbr-mcp integration tests

An LLM agent (Pydantic AI, Azure OpenAI) drives a real vbr-mcp server against a mocked VBR, and Pydantic Evals checks
what it answered and what it asked VBR to do. The cases are the test plan's questions: G1 simple reads, G2 composite
questions, G3 questions that lead, or must not lead, to changing VBR.

```
uv run check.py              # offline: every case's facts, references and environment, no LLM
uv run run.py                # the eval: every case (EVAL_REPEAT times each)
uv run run.py G1-03 G3       # these cases, or whole groups
```

`run.py` needs `.env` (copy `.env.example`): the Azure OpenAI deployment and a service principal. `check.py` needs
nothing and takes seconds; run it after every change to a case.

## Layout
- `cases/` — one module per case, `cases/g1/g1_01.py` ... Each exposes `case(judge_model)`. `cases/__init__.py` has
  the shared pieces (`CaseInputs`, `confirm`, `judge`, `tool_budget`), `cases/patterns.py` the regex building blocks
  of facts.
- `stand/` — the base stand: one consistent VBR (jobs, sessions, repositories, malware events, license...) that every
  case starts from. `stand.environment(**overrides)` mocks every route vbr-mcp's read tools use.
- `vbr_mock/` — the VBR REST API double the run serves in-process (see its README).
- `vbr_models/` — VBR's response models, as far as the cases use them.
- `evaluators.py` — the custom evaluators; `run.py` — the eval; `check.py` — the offline check.

## How a run works
Every run of a case gets its own mock environment and its own vbr-mcp over stdio, with VBR credentials that log in to
that environment. The agent gets vbr-mcp's server instructions (its confirmation policy) as an MCP client passes them
on. Multi-turn cases ask their follow-ups in order; a `confirm(...)` follow-up is skipped when the agent already did
what it would confirm - for an action on several targets, or one VBR refuses, when its `done` says the requests VBR
received settle it. The evaluators see the answer, the tool-call spans, every request vbr-mcp sent to VBR
(`vbr_requests`) and every tool result the agent saw (`tool_returns`).

`inputs.vbr` breaks the connection on purpose: `unreachable`, `wrong_password`, `timeout` (a server that never
answers), `untrusted_tls` (the mock over HTTPS with a self-signed certificate).

## The verdict
Two tiers (`evaluators.HARD_EVALUATORS`):
- **Hard** — the agent wrote when it must not (`ToolsNotCalled`, `VbrNotRequested`), made up an id
  (`NoInventedIds`), looped within a turn (`NoRepeatedCalls`) or ran away (`MaxToolCalls`, `MaxModelRequests`). Any
  failure, in any repeat, fails the run.
- **Soft** — what the answer says (`FactsPresent`, LLM judges) and which road it took (`ToolCorrectness`,
  `ToolsCalled`, `VbrRequested`). These vary between runs of the same model, so the run must pass
  `MIN_SOFT_PASS_RATE` (default 90%) of them.

The run prints the soft results per case, the hard failures, the routes a run asked for that its environment lacks
(an incomplete environment), the requests the mock failed to serve because a case's callable raised (an `ERROR`, which
fails the run: the agent read a bare 500 there), and the assertions that passed in the previous run
(`.results/last.json`) and fail now. `.results/last_runs.json` keeps every run's answer, failed assertions (with the
judges' reasons) and requests to VBR: read a failure there before deciding whether the agent or the case is wrong. A run
of some cases replaces only their entries in both files.

## Writing a case
- **Environment:** `stand.environment(...)`, overriding the collections the case changes, plus its own actions
  (`VbrAction` with `reject`, `effects`, `effects_of`, `response_of`). An effect on a list that another action of the
  case also changes is a `VbrUpdate` (`cases.g3.actions.updated`, `prepended`), so the second action keeps what the
  first did. Derive the expected output, the facts and the judges from that data, never from literals.
- **Facts:** only what the question asks for, built from `cases.patterns` so that every way a reader would accept is
  accepted (`day`, `clock`, `number`, `gb`, `percent`, `name`, `STARTED`, `CANNOT`, ...). The answer is normalized
  first (ASCII hyphens, spaces and quotes, no Markdown emphasis). A fact that belongs to one turn is
  `Fact(pattern, turns=(n,))`.
- **Answers:** give `GOOD` (answers a correct agent could give, varied in form; multi-turn ones as `[Turn 1]\n...`)
  and `BAD` (fact name -> a plausible wrong answer that must not match it). `check.py` holds every fact to them,
  also after the Unicode a model writes, and to the case's own `EXPECTED`.
- **Trajectory:** `ToolCorrectness` only when one tool is the only road; `ToolsCalled` for any of several;
  `VbrRequested` / `VbrNotRequested` for what VBR was asked, with the body that matters (`check.py` holds their paths
  to the routes vbr-mcp sends). `VbrNotRequested(besides=..., besides_body=...)` forbids every request but the one
  the user asked for, `up_to=1` more than one target the case cannot name in advance.
- **Budget:** `tool_budget(calls, turns=n)`: the expected calls plus `EXTRA_CALLS`, a guard against runaway, not a
  trajectory check.
- **Confirmation (G3):** vbr-mcp's instructions are the policy. Demand a confirmation turn only where they do
  (destructive with consequences the request did not accept, several objects, a write that stops protection), guard
  the turn before it with `ToolsNotCalled(turns=...)`, and name the action in the confirmation text. Give `done` to a
  confirmation that covers several targets, and a confirmation turn to an agent that may ask first even where asking
  is not required.
- **Judges:** one criterion each, conditional where a focused correct answer would otherwise fail; never require
  knowledge the tools and the question do not give.
- **Mock texts:** an error the agent reads is VBR's own text where known (cite it), neutral otherwise.
