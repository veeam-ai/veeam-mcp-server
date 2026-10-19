# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""VBR's flexible filtration: the ``filter`` and ``sorting`` expressions some reads take in their request body.

The inventory browser (``POST /api/v1/inventory``) filters and sorts with expression models rather than ``<x>Filter``
query parameters (swagger ``FilterExpressionModel``, ``SortExpressionModel``). ``select`` applies them to records as
VBR's ``CCollectionFilter`` applies them to its models (Veeam.Backup.RestApi.Framework, ``FlexibleFiltration``):

- a property is named without regard to case, and one the model does not have fails the request;
- ``Contains``, ``StartsWith`` and ``EndsWith`` compare text ignoring case and never match a null; ``Equals``,
  ``NotEquals`` and ``In`` (comma-separated values) compare text exactly, an enum's name ignoring case;
- ``And`` and ``Or`` group expressions, ``Not`` holds when none of its items does.
"""

from collections.abc import Callable
from typing import Any


class ExpressionError(ValueError):
    """An expression VBR refuses: a property the model does not have, an operation it does not know."""


def select[Item](
    items: list[Item],
    record: Callable[[Item], dict[str, Any]],
    filter_expression: Any,
    sorting: Any,
    *,
    model: str,
    enums: frozenset[str] = frozenset(),
) -> list[Item]:
    """The ``items`` whose ``record`` (their JSON) matches ``filter_expression``, ordered by ``sorting``.

    ``model`` is the name of the type VBR filters (for its error message), ``enums`` the properties it holds as enums.
    """
    found = [item for item in items if _matches(record(item), filter_expression, model, enums)]
    if not isinstance(sorting, dict):
        return found
    prop = str(sorting.get("property", ""))
    descending = str(sorting.get("direction") or "Ascending").lower() == "descending"

    def key(item: Item) -> tuple[bool, str]:
        value = _property(record(item), prop, model, "")
        return (value is not None, "" if value is None else str(value))  # .NET orders a null first, ascending

    return sorted(found, key=key, reverse=descending)


def _matches(record: dict[str, Any], expression: Any, model: str, enums: frozenset[str]) -> bool:
    if not isinstance(expression, dict):
        return True
    kind = str(expression.get("type", "")).lower()
    operation = str(expression.get("operation", "")).lower()
    if kind == "groupexpression":
        items = expression.get("items") or []
        if not items:
            raise ExpressionError("Group filter expression should have at least 1 item.")
        results = [_matches(record, item, model, enums) for item in items]
        groups = {"and": all, "or": any, "not": lambda found: not any(found)}
        if operation not in groups:
            raise ExpressionError(f"Unknown group operation: {expression.get('operation')}.")
        return groups[operation](results)
    if kind != "predicateexpression":
        raise ExpressionError(f"Unknown filter expression type: {expression.get('type')}.")
    prop, wanted = str(expression.get("property", "")), str(expression.get("value", ""))
    return _predicate(operation, _property(record, prop, model, wanted), wanted, prop.lower() in enums)


def _predicate(operation: str, actual: Any, wanted: str, is_enum: bool) -> bool:
    """Whether a property's value ``actual`` satisfies ``operation`` with ``wanted``."""
    if operation in _TEXT:
        return actual is not None and _TEXT[operation](str(actual).lower(), wanted.lower())
    if operation in ("equals", "notequals", "in"):
        candidates = [value.strip() for value in wanted.split(",") if value.strip()] if operation == "in" else [wanted]
        equal = actual is not None and any(_equal(actual, candidate, is_enum) for candidate in candidates)
        return not equal if operation == "notequals" else equal
    if operation in _ORDER:
        left, right = _ordered(actual), _ordered(wanted)
        return actual is not None and type(left) is type(right) and _ORDER[operation](left, right)
    raise ExpressionError(f"Unknown predicate operation: {operation}.")


_TEXT: dict[str, Callable[[str, str], bool]] = {
    "contains": lambda text, part: part in text,
    "startswith": str.startswith,
    "endswith": str.endswith,
}
_ORDER: dict[str, Callable[[Any, Any], bool]] = {
    "lessthan": lambda left, right: left < right,
    "lessthanorequal": lambda left, right: left <= right,
    "greaterthan": lambda left, right: left > right,
    "greaterthanorequal": lambda left, right: left >= right,
}


def _property(record: dict[str, Any], prop: str, model: str, value: str) -> Any:
    """The record's ``prop``, named without regard to case, as VBR's ``PropertyMatcher`` finds it."""
    wanted = prop.upper()
    for key, actual in record.items():
        if key.upper() == wanted:
            return actual
    raise ExpressionError(f"Property is not found in type: [{model}]. Property: [Name:{prop}, Value:{value}].")


def _equal(actual: Any, wanted: str, is_enum: bool) -> bool:
    if isinstance(actual, bool):
        return wanted.strip().lower() == str(actual).lower()
    if isinstance(actual, int | float):
        try:
            return actual == type(actual)(wanted)
        except ValueError:
            return False
    return str(actual).lower() == wanted.lower() if is_enum else str(actual) == wanted


def _ordered(value: Any) -> Any:
    """A value as an ordered comparison sees it: a number if it reads as one, text otherwise."""
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    try:
        return float(str(value))
    except ValueError:
        return str(value)
