# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""What a test can hand the mock besides plain VBR models."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class MockOnly:
    """Marks a model field the mock filters by but never serves: ``Annotated[UUID | None, MOCK_ONLY]``.

    Some VBR list filters read a relation VBR keeps in its database and leaves out of the response. A restore
    point does not carry the protected object it belongs to, yet ``/restorePoints?backupObjectIdFilter=`` selects
    by it. A test states that relation as a mock-only field named like the property the filter reads
    (``backupObjectId``): the mock filters and sorts by it, then strips it, so a client sees exactly VBR's JSON.
    """


MOCK_ONLY = MockOnly()


class VbrError(BaseModel):
    """A route that answers with an error, served with VBR's error body.

    E.g. ``VbrError(status_code=403, message=...)`` for a read the VBR account's role does not allow. The body's
    ``errorCode`` is the one of VBR's ``Error`` enum that VBR answers that status with (``AccessDenied``...).
    """

    status_code: int = Field(ge=400)
    message: str


class VbrSequence(BaseModel):
    """A route that answers differently each time it is asked: ``steps`` in order, then the last one for good.

    Each step is anything a route can be mocked with: a model, a list of models, a string or a ``VbrError``. E.g.
    an Instant Recovery mount that is ``Mounting`` on the first read and ``Mounted`` from the second on.
    """

    steps: list[Any]


class VbrUpdate(BaseModel):
    """An action's effect that changes what a route serves now, instead of replacing it.

    ``change`` takes the route's current data as VBR's JSON (a list route's records) and returns the new data. Two
    actions on one list - stop one job, disable another - then both show: an effect that replaced ``/jobs/states``
    with the stand's states plus its own change would undo the other's.
    """

    change: Callable[[Any], Any]


Reject = Callable[[Any], VbrError | None]
"""Reads an action's JSON request body (``None`` when it has none) and returns the error VBR would refuse it with,
or ``None`` to accept it."""


class VbrAction(BaseModel):
    """A VBR action the mock performs: a ``POST`` that changes something, such as ``/jobs/{id}/start``.

    The action is answered with ``response`` (``201`` and the model, typically the ``SessionModel`` VBR starts), or
    with ``204 No Content`` when there is none. ``reject`` lets it refuse a request the way VBR would, e.g. a ``400``
    for a restore to the original location without ``overwrite``. Once accepted, ``effects`` are mocked into the
    environment: the state VBR is in after the action, such as the job now ``Running`` or a mount appearing. An effect
    can itself be a ``VbrSequence`` or another ``VbrAction``.

    Every request the mock receives is recorded (``VbrMock.requests``), so a case can assert what VBR was asked to do.
    """

    response: BaseModel | None = None
    status_code: int | None = None
    """``201`` with a ``response``, ``204`` without one, unless set."""
    reject: Reject | None = None
    effects: dict[str, Any] = {}
    """Route -> what it answers from now on, as in a case's ``Environment``."""
    effects_of: Callable[[Any], dict[str, Any]] | None = None
    """Effects that depend on what was asked: reads the accepted request's JSON body and returns routes as
    ``effects`` does, mocked after them. E.g. maintenance mode for exactly the extents the body names."""
    response_of: Callable[[Any], Any] | None = None
    """An answer that depends on what was asked, in place of ``response``: reads the request's JSON body and returns
    a model, a list of models, a string (a plain-text body) or a ``VbrError``, served as a route mocked with it would
    be (a list paged like VBR, ``MOCK_ONLY`` fields stripped). For a read VBR serves over ``POST`` and answers by its
    body, e.g. the license report in the format the body names; ``status_code`` defaults to ``200`` then."""
