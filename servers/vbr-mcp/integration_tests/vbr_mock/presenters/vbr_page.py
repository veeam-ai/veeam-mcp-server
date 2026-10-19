# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

from datetime import UTC, datetime
from typing import Any, NamedTuple


def vbr_page(data: list[dict], query_params: dict, hidden: frozenset[str]) -> dict:
    """Wraps a list in VBR's list envelope ``{data, pagination}``.

    Supports the ``skip``/``limit``/``orderColumn``/``orderAsc``/``<x>Filter`` query
    parameters, mirroring the VBR REST API. ``pagination.total`` is the post-filter,
    pre-paging count (VBR's ``PaginationResult.Total``), which vbr-mcp's
    ``fetch_all`` relies on to loop pages.
    """
    # Mirrors VBR's list controllers: filter -> sort -> count total -> page.
    items = _apply_filters(data, query_params)
    if "orderColumn" in query_params:
        items = _apply_sort(items, query_params["orderColumn"], query_params.get("orderAsc"))
    skip, limit = _normalize_paging(query_params.get("skip"), query_params.get("limit"))
    page = _apply_paging(items, skip, limit)
    if hidden:  # filtered and sorted by, never served
        page = [{key: value for key, value in item.items() if key not in hidden} for item in page]
    # total is the count of all matching records (after filtering) BEFORE paging,
    # mirroring VBR's PaginationResult.Total (computed on the un-limited result set).
    return {
        "data": page,
        "pagination": {"total": len(items), "count": len(page), "skip": skip, "limit": limit},
    }


_MISSING = object()
_UNREADABLE = object()


class _Filter(NamedTuple):
    """Where a filter parameter reads from, and how it compares."""

    fields: tuple[str, ...]
    """Candidate property paths, most specific first; the first one the records carry wins.

    More than one because the same parameter reads a different property per endpoint —
    `typeFilter` is `type` on backup objects but `sessionType` on sessions — and the presenter
    is deliberately route-agnostic. Paths may be dotted for filters VBR resolves into a
    sub-object.
    """

    compare: str
    """``eq``, ``ge`` or ``le``."""


# VBR implements filtering per endpoint in its DB layer, so a parameter's name does not always
# name the property it reads, and some are range bounds rather than equality. This map is the
# mock's equivalent of that layer for the parameters vbr-mcp sends; every entry is grounded in
# the parameters the OpenAPI spec declares and the fields the corresponding records actually
# carry. Anything absent here falls back to equality on the parameter name minus the `Filter`
# suffix.
_FILTERS: dict[str, _Filter] = {
    # /backups, /restorePoints, /sessions
    "createdAfterFilter": _Filter(("creationTime", "creationTimeUtc"), "ge"),
    "createdBeforeFilter": _Filter(("creationTime", "creationTimeUtc"), "le"),
    # /sessions
    "resultFilter": _Filter(("result.result",), "eq"),
    "typeFilter": _Filter(("type", "sessionType"), "eq"),
    # /malwareDetection/events
    "detectedAfterTimeUtcFilter": _Filter(("detectionTimeUtc",), "ge"),
    "detectedBeforeTimeUtcFilter": _Filter(("detectionTimeUtc",), "le"),
    "backupObjectIdFilter": _Filter(("backupObjectId", "machine.backupObjectId"), "eq"),
    "machineNameFilter": _Filter(("machine.displayName",), "eq"),
}


def _apply_filters(items: list[dict], query_params: dict) -> list[dict]:
    # Every query param ending in "Filter" narrows the result set. `nameFilter` uses VBR's
    # wildcard semantics; the rest are resolved through `_FILTERS`. Filtering runs before
    # `total` is counted, which vbr-mcp's `fetch_all` loop depends on.
    # A parameter given more than once arrives as a list of values, and a record matches when it
    # matches any of them — how VBR reads a repeated filter such as `resultFilter`.
    records = items
    for param, value in query_params.items():
        if not param.endswith("Filter"):
            continue
        values = value if isinstance(value, list) else [value]
        if param == "nameFilter":
            items = [i for i in items if any(_name_filter(str(i.get("name", "")), v) for v in values)]
            continue
        # Which property the filter reads is a question about the route's records, not about the
        # ones an earlier filter left: asked of those, the answer would depend on the order of the
        # parameters (no record left to carry the field, so the filter would be dropped).
        field = filter_field(records, param)
        # A filter VBR answers through a join has no field to read here. Narrowing to nothing
        # would have the assistant report "no data" with full confidence, so leave the set
        # alone instead: unfiltered is wrong in a way a reader can notice, empty is not.
        if field is None:
            continue
        compare = _filter_spec(param).compare
        items = [i for i in items if any(_matches(_resolve(i, field), v, compare) for v in values)]
    return items


def filter_field(items: list[dict], param: str) -> str | None:
    """The property a filter parameter reads on these records, or ``None`` if none carry it.

    ``None`` is what makes a filter unanswerable here, so this is also the honest answer to
    "which of the filters the spec declares can this route actually serve".
    """
    fields = _filter_spec(param).fields
    return next((field for field in fields if any(_resolve(i, field) is not _MISSING for i in items)), None)


def _filter_spec(param: str) -> _Filter:
    return _FILTERS.get(param) or _Filter((param[: -len("Filter")],), "eq")


def _resolve(item: dict, field: str) -> Any:
    """Read a possibly dotted property path off a record, or ``_MISSING``."""
    current: Any = item
    for part in field.split("."):
        if not isinstance(current, dict) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _matches(actual: Any, expected: str, compare: str) -> bool:
    if actual is _MISSING or actual is None:
        # An absent property cannot equal the value asked for, and cannot fall inside a range.
        # VBR's lists are polymorphic, so "the subtype does not carry this field" is ordinary
        # rather than exceptional.
        return False
    value = _as_typed(actual, expected)
    if value is _UNREADABLE:  # a value the property could never hold is not equal to it
        return False
    if compare == "eq":
        return actual == value
    left, right = _comparable(actual), _comparable(value)
    if left is None or right is None:
        return False
    if isinstance(left, datetime) != isinstance(right, datetime):
        # One side is a timestamp and the other text no ISO reader accepts: there is no order
        # between them, and comparing a datetime with a str would raise a 500.
        return False
    return left >= right if compare == "ge" else left <= right


def _as_typed(sample: Any, text: str) -> Any:
    """Read a query parameter as the type the record's own value has.

    Query parameters arrive as text while VBR's models are typed, so comparing them raw makes an
    integer field match nothing and an ordered comparison raise. Text the type cannot read yields
    ``_UNREADABLE`` rather than an error: a value VBR would reject is not a reason to fail the
    request.
    """
    if isinstance(sample, bool):  # before int — in Python a bool *is* an int
        lowered = text.strip().lower()
        if lowered in ("true", "false"):
            return lowered == "true"
        return _UNREADABLE
    if isinstance(sample, int | float):
        try:
            return type(sample)(text)
        except ValueError:
            return _UNREADABLE
    return text


def _comparable(value: Any) -> Any:
    """Normalize a range bound so the two sides compare by instant, not by spelling.

    VBR clients send `...Z` while records carry an explicit offset, so a plain string
    comparison mis-orders the same instant. Non-timestamps fall through unchanged.
    """
    if not isinstance(value, str):
        return value
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return value
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment


def _name_filter(name: str, filter: str) -> bool:
    # Reproduces VBR's SRestFilterHelper.NameFilter verbatim, including the trailing-`*`
    # branch's Substring(0, len-2) off-by-one and its case-sensitive comparisons.
    if filter.startswith("*") and filter.endswith("*") and len(filter) > 1:
        return filter[1:-1] in name
    if filter.startswith("*"):
        return name.endswith(filter[1:])
    if filter.endswith("*"):
        return name.startswith(filter[: len(filter) - 2])
    return name == filter


def _normalize_paging(skip: str | None, limit: str | None) -> tuple[int, int]:
    # Mirrors VBR's SFilterValuesHelper: GetSkip (None/<0 -> 0), GetLimit (None/<=0 -> 200).
    # Text that is not an integer is treated as absent rather than raising a 500.
    parsed_skip, parsed_limit = _as_int(skip), _as_int(limit)
    normalized_skip = 0 if parsed_skip is None or parsed_skip < 0 else parsed_skip
    normalized_limit = 200 if parsed_limit is None or parsed_limit <= 0 else parsed_limit
    return normalized_skip, normalized_limit


def _as_int(text: str | None) -> int | None:
    if text is None:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _apply_sort(items: list[dict], order_column: str, order_asc: str | None) -> list[dict]:
    # VBR sorts by `orderColumn` with direction `orderAsc` (ascending by default).
    # The column is VBR's PascalCase enum name (`CreationTime`) while records carry camelCase
    # properties (`creationTime`), so the property is matched without regard to case.
    descending = order_asc is not None and order_asc.lower() == "false"
    return sorted(items, key=lambda i: _sort_key(i, order_column), reverse=descending)


def _column_value(item: dict, order_column: str) -> object:
    if order_column in item:
        value = item[order_column]
    else:
        wanted = order_column.lower()
        value = next((value for key, value in item.items() if key.lower() == wanted), None)
    # Some columns hold an object rather than a scalar: a session's `result` is
    # `{"result": "Success", "message": ..., "isCanceled": ...}`. VBR orders those by the
    # same-named inner property, and dicts don't compare, so descend into it.
    if isinstance(value, dict):
        return _column_value(value, order_column)
    return value


# VBR orders an enum column by the integer its database stores, not by the name the API serves
# (Sp_Rest.sql: "ORDER BY js.result", "ORDER BY js.state", "ORDER BY js.job_type"): sessions by
# result descending put Failed (2) before Warning (1) and Success (0). Keyed by the lowercased
# column.
_ENUM_ORDER: dict[str, dict[str, int]] = {
    # CBaseSessionInfo.EResult
    "result": {"None": -1, "Success": 0, "Warning": 1, "Failed": 2},
    # CBaseSessionInfo.EState
    "state": {
        "Stopped": -1, "Starting": 3, "Stopping": 4, "Working": 5, "Pausing": 6, "Resuming": 7, "WaitingTape": 8,
        "Idle": 9, "Postprocessing": 10, "WaitingRepository": 11, "WaitingSlot": 12, "ActionRequired": 14,
    },
    # EDbJobType, through CRestSessionTypeConverter
    "sessiontype": {
        "BackupJob": 0, "RestoreVm": 4, "QuickMigration": 8, "FileLevelRestore": 10, "InstantRecovery": 12,
        "VolumesDiscover": 19, "BackupCopyJob": 63, "ConfigurationBackup": 100, "ConfigurationResynchronize": 102,
        "RepositoryMaintenance": 105, "Infrastructure": 7000, "HostComponentsUpdate": 7001, "AgentBackup": 12003,
        "NasRestore": 13002, "MalwareDetection": 32000, "SureBackup": 33001,
    },
}  # fmt: skip
_NAS_BACKUP = 13000
"""EDbJobType.NasBackup: a file share or object storage backup run, which the API calls ``BackupJob`` too."""


def _sort_key(item: dict, order_column: str) -> tuple[int, int, object]:
    # Nullable columns are ordinary in VBR: a running session has no `endTime`, an unscheduled
    # job no `nextRun`. Comparing None with a str raises, so sort missing values last
    # (ascending) the way VBR's PostgreSQL back end orders NULLs, instead of raising a 500.
    # Timestamps sort by instant: records carry their own offsets (+01:00 in winter, +02:00 in
    # summer), and as text those would order by wall-clock time instead. An enum value sorts by
    # its stored integer, ahead of any value the map does not know.
    value = _column_value(item, order_column)
    if value is None:
        return (1, 1, "")
    ranks = _ENUM_ORDER.get(order_column.lower(), {})
    if isinstance(value, str) and value in ranks:
        nas = (
            order_column.lower() == "sessiontype"
            and value == "BackupJob"
            and item.get("platformName") == "UnstructuredData"
        )
        return (0, 0, _NAS_BACKUP if nas else ranks[value])
    return (0, 1, _comparable(value))


def _apply_paging(items: list[dict], skip: int, limit: int) -> list[dict]:
    return items[skip : skip + limit]
