# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, field_validator

from vbr_mock.markers import Reject
from vbr_mock.presenters import PRESENTERS

Method = Literal["GET", "POST"]


class MockEndpoint(BaseModel):
    """One VBR route of an environment and what the mock answers on it."""

    route: str
    """The VBR path, e.g. ``/api/v1/serverInfo``. Leading and trailing slashes do not matter."""

    presenter: str
    """How ``data`` is turned into the response: ``as-is``, ``vbr-page`` (VBR's paged list envelope) or ``error``."""

    data: Any
    """The stored payload. ``vbr-page`` requires a list of records."""

    hidden: frozenset[str] = frozenset()
    """Properties of the records the mock filters and sorts by but strips from the response (see ``MockOnly``)."""

    method: Method | None = None
    """The HTTP verb VBR serves this route over, when the test knows it.

    ``None`` means unspecified, and the route then answers either verb. A route that does name its
    verb is held to it, so a client reaching for a read over the wrong one gets the 405 a real
    server would give rather than a helpful 200. A route can be mocked once per verb: a VBR read and a
    VBR action may share a path (``GET`` lists Instant Recovery mounts, ``POST`` starts one).
    """

    status_code: int = 200
    """The status a successful answer carries: ``201`` for an action that started a session, ``204`` for one
    with nothing to say."""

    reject: Reject | None = None
    """For an action: reads the request body and returns the error VBR would refuse it with, or ``None``."""

    effects: list["MockEndpoint"] = []
    """For an action: the routes mocked into the environment once it is accepted."""

    effects_of: Callable[[Any], list["MockEndpoint"]] | None = None
    """For an action: routes computed from the accepted request's body, mocked after ``effects``."""

    respond: Callable[[Any, dict], Any] | None = None
    """Computes the answer from the request's body and query parameters (JSON-ready data or a string), in place of
    ``data``."""

    then: "MockEndpoint | None" = None
    """What the route answers after this answer has been served once (see ``VbrSequence``)."""

    change: Callable[[Any], Any] | None = None
    """For an effect (``VbrUpdate``): changes the data the route already serves, in place of ``data``."""

    @field_validator("presenter")
    @classmethod
    def _known_presenter(cls, value: str) -> str:
        if value not in PRESENTERS:
            raise ValueError(f"Invalid presenter: {value}. Valid presenters: {sorted(PRESENTERS)}")
        return value


class RecordedRequest(BaseModel):
    """A request the mock received, as a case may assert it: what VBR was asked, and what it answered."""

    method: str
    path: str
    """With a leading slash, e.g. ``/api/v1/jobs/{id}/start``."""
    body: Any
    """The JSON body, or ``None``."""
    status_code: int
    unmocked: bool = False
    """The request reached a route the environment does not mock. VBR has it, so the case's environment is
    incomplete: the agent was told the object does not exist."""
    error: str | None = None
    """The exception the mock itself raised serving the request (``Type: message``), answered with a 500: a bug in the
    case's environment (its ``reject``, ``effects_of`` or ``response_of``) or in the mock, not VBR's answer. ``None``
    when the mock served the request, an error VBR would answer included."""
