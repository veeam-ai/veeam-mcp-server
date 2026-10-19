# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""How a mocked route's stored data becomes the response, keyed by the ``presenter`` field of its endpoint.

A presenter takes the stored ``data``, the request's query parameters and the ``hidden`` record properties (filtered
and sorted by, never served). To add one (e.g. for another VBR list shape), add its function to ``PRESENTERS``.
"""

from collections.abc import Callable
from typing import Any

from vbr_mock.presenters.vbr_page import vbr_page

Presenter = Callable[[Any, dict, frozenset[str]], Any]


class MockedError(Exception):
    """A route mocked to fail: the app answers with ``status_code`` and VBR's error body."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def as_is(data: Any, query_params: dict, hidden: frozenset[str]) -> Any:
    """The stored data verbatim, ignoring query parameters."""
    if hidden and isinstance(data, dict):
        return {key: value for key, value in data.items() if key not in hidden}
    return data


def error(data: Any, query_params: dict, hidden: frozenset[str]) -> Any:
    """Answers every request with the stored error, ``{"status_code": ..., "message": ...}``."""
    raise MockedError(data["status_code"], data["message"])


PRESENTERS: dict[str, Presenter] = {"as-is": as_is, "vbr-page": vbr_page, "error": error}
