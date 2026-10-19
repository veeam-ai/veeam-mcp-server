# vbr_mock

A test double of the Veeam Backup & Replication REST API. `run.py` serves it inside the test process on a
free local port (`VbrMock`), mocks each run's VBR data straight into its store, and points that run's vbr-mcp
at it. vbr-mcp cannot tell it from a real VBR.

The mock knows VBR's login, error shape and list paging. It does not know any concrete route or model: what a
route answers is plain JSON the test puts there, dumped from the test's pydantic models.

## Environments
Every route is mocked under an **environment id**, and the mock holds any number of environments at once.
A client picks its environment by logging in the way it would with VBR, `POST /api/oauth2/token` with a
password-grant form, with the **environment id as the username** and the password `mock`
(`VbrMock.PASSWORD`); any other password is rejected with `400 invalid_grant`, as VBR rejects bad credentials. The token it
gets back routes each of its reads to that environment, and a `refresh_token` grant keeps it. So a vbr-mcp
started with `VBR_USERNAME=<environment id>` sees exactly that environment, and environments with the same
routes never see each other's data.

```python
async with VbrMock() as mock:  # serves on mock.url until the block exits
    mock.mock("run-1", "/api/v1/serverInfo", server_info)  # a model: served as is
    mock.mock("run-1", "/api/v1/jobs/states", [job_a, job_b])  # a list of models: paged like VBR
    ...
    mock.delete("run-1")
```

A route key that names its verb (`"GET /api/v1/..."`) holds a route to the verb VBR serves it over; without one
the route answers both, in place of whatever the path answered before over either verb. A path can be mocked once per
verb: VBR's Instant Recovery mounts are listed by `GET /api/v1/restore/instantRecovery/vSphere/vm` and started by a
`POST` to the same path.

## Actions
A `VbrAction` mocks something VBR *does* — a job start, a restore, a proxy disable — as a `POST`:

```python
mock.mock(
    "run-1",
    f"/api/v1/jobs/{job_id}/start",
    VbrAction(
        response=session,  # 201 with this SessionModel; without a response, 204 No Content
        reject=lambda body: VbrError(status_code=400, message="...") if body.get("performActiveFull") else None,
        effects={"/api/v1/jobs/states": states_with_the_job_running},  # what VBR reads like once it is done
    ),
)
```

- `reject` reads the JSON request body and returns the error VBR would refuse it with, or `None` to accept it.
- `effects` are mocked into the environment once the action is accepted, as in a case's environment: an effect
  can be a model, a list, a `VbrSequence`, another `VbrAction` or a `VbrUpdate`, which changes what the route serves
  at that moment instead of replacing it (`VbrUpdate(change=...)`, the route's current data in and the new data out):
  of two actions on one list - stop one job, disable another - both then show.
- `effects_of` reads the accepted request's body and returns more effects: the state that depends on what was
  asked, such as maintenance mode for exactly the extents the body names. All effects are applied, in order, to a
  copy of the environment that replaces it only once they all applied, so an `effects_of` or a change that raises
  leaves the environment as it was.
- `response_of` reads the request's body and returns the answer, in place of `response`: a model, a list, a string or
  a `VbrError`, served as a route mocked with it would be (a list paged like VBR, `MOCK_ONLY` fields stripped).
- A `VbrError` mocked on a `"POST /api/v1/..."` route is an action VBR refuses outright (a `403` for the
  account's role).

A `VbrSequence(steps=[...])` answers its steps one per request and then keeps answering the last: a mount that is
`Mounting` on the first read and `Mounted` from the second on.

## Recorded requests
Every request the mock routes to an environment is recorded with its method, path, JSON body, the status it was
answered with, whether the route was mocked at all and, when the mock itself raised serving it, the exception
(`error`); `VbrMock.requests(environment_id)` returns them, oldest first. `run.py` hands them to the evaluators, which
assert what VBR was asked to do (`VbrRequested`, `VbrNotRequested` in `evaluators.py`).

An exception the mock raises - in a case's `reject`, `effects_of` or `response_of`, or in the mock - is answered with
a `500`, logged with its traceback, and recorded as the request's `error`: a bug in the case, not VBR's answer.

## Responses
- A route that is mocked answers `200` with its data. A route mocked with a string answers it as a plain-text
  body, for the reads VBR answers with a document instead of JSON (`POST /api/v1/license/createReport`).
- A route mocked with a `VbrError(status_code=..., message=...)` answers that error with VBR's body — e.g. a
  `403` for a read the account's role does not allow.
- `401` — no bearer token from the mock's login.
- `201` / `204` — a `VbrAction` that was accepted, with its response or without one.
- `404` — the route is not mocked in the environment, an action included, or nothing is mocked in it at all.
- `405` — the route declares a different `method`.

Errors use VBR's own body, `{"errorCode": ..., "message": ...}`, with the codes of VBR's `Error` enum
(`UnexpectedContent` for a 400, `AccessDenied` for a 403, `NotFound`, `MethodNotAllowed`, `UnknownError` for a
500...). vbr-mcp passes the message on to the model, so it must read like VBR's: a route the environment lacks is
answered as VBR answers an object that does not exist, `The requested resource /api/v1/... was not found.`, never
with a word about the mock. Such a request is recorded with `unmocked: true`, and `run.py` lists them per case: the
case's environment is incomplete, and the agent was told something VBR would not tell it.

POST is served for VBR's actions, and because some VBR reads *are* POSTs: the inventory browser is
`POST /api/v1/inventory` (the roots of VBR's inventory) and `POST /api/v1/inventory/{hostname}` (the objects inside
one), which filter, sort and page through the request body. Such a read is a `VbrAction` with a `response_of`, which
answers by the body: the stand's inventory browser applies the body's `filter` and `sorting` with
`presenters/expressions.py`, VBR's flexible filtration (a predicate or a group of them, on a property named without
regard to case), and the objects browser also its `hierarchyType`.

## Paged lists
A list is wrapped in VBR's list envelope
`{"data": [...], "pagination": {"total": <n>, "count": <m>, "skip": <s>, "limit": <l>}}`, where `total` is
the number of records matching the filters (before paging), `count` the number returned in `data`, and
`skip`/`limit` the effective paging values. Honored parameters:

- `skip` — records to skip. `null` or negative is normalized to `0` (mirrors VBR's `SFilterValuesHelper.GetSkip`).
- `limit` — maximum records to return. `null` or non-positive is normalized to `200` (mirrors `GetLimit`).
- `orderColumn` — property to sort by, with `orderAsc` (`"true"`/`"false"`, ascending by default). Records
  where the column is `null` sort last ascending, the way VBR's PostgreSQL back end orders NULLs. An enum column
  (`Result`, `State`, `SessionType` of a session) sorts by the integer VBR stores, not by its name: by result,
  descending, Failed comes before Warning and Success.
- `nameFilter` — a wildcard `*` pattern matched case-sensitively against `name`, reproducing VBR's
  `SRestFilterHelper.NameFilter` (`*x*` contains, `*x` ends-with, `x*` starts-with, otherwise exact).
- `<x>Filter` — every other `*Filter` narrows the set, and `total` is counted after it:
  - **The property may be named differently.** `resultFilter` reads the nested `result.result`, `typeFilter` reads `sessionType` on sessions, `machineNameFilter` a malware event's `machine.displayName`.
  - **Comparison is not always equality.** `createdAfterFilter`/`createdBeforeFilter` and `detectedAfterTimeUtcFilter`/`detectedBeforeTimeUtcFilter` are range bounds. Timestamps compare by instant.
  - **Values are read as the record's own type.** A number compares as a number, a boolean as a boolean. A value the property could never hold matches nothing.
  - **A repeated parameter matches any of its values** — `resultFilter=Failed&resultFilter=Warning`.
  - **A filter no record of the route can answer is ignored** rather than emptying the result: VBR resolves some through joins a flat store cannot follow. Whether it can is decided on all the route's records, not on those an earlier filter left.

**Mock-only fields.** Some VBR filters read a relation VBR keeps in its database and leaves out of the
response: a restore point does not carry the protected object it belongs to, yet `backupObjectIdFilter`
selects by it. A model states that relation as a field marked `MOCK_ONLY`
(`backup_object_id: Annotated[UUID | None, MOCK_ONLY] = None`, from `vbr_mock.markers`), named like the
property the filter reads. The mock filters and sorts by it and strips it from what it serves, so a client
sees exactly VBR's JSON.

On a POST, `skip` and `limit` are also read from the body's `pagination` object
(`{"pagination": {"skip": 0, "limit": 100}}`); an explicit query parameter still wins.

## HTTPS
`VbrMock(tls=(cert_file, key_file))` also serves the same environments over HTTPS on `mock.tls_url`. `run.py` gives
it a self-signed certificate, as a VBR server has by default, for the case where vbr-mcp, verifying TLS, refuses it.

## Layout
- `server.py` — `VbrMock`: serves the app in-process and fills the store from models.
- `app.py` — the HTTP surface: VBR login, the catch-all handler, VBR error bodies, request recording.
- `store.py` — environments in memory: their routes, per verb, and the requests they received.
- `markers.py` — `MOCK_ONLY`, `VbrError`, `VbrSequence`, `VbrAction` and `VbrUpdate`, what a test hands the mock
  besides plain models.
- `presenters/` — `as-is`, `vbr-page` and `error`, the functions of `PRESENTERS` in `presenters/__init__.py`, and
  `expressions.py`, VBR's filter and sorting expressions for the reads that take them in their body.
