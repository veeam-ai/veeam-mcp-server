# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""Shared parsing for VBR's ISO-8601 timestamps."""

from __future__ import annotations

import re
from datetime import UTC, datetime

# VBR emits 7-digit fractional seconds; trim any beyond the 6 fromisoformat accepts.
_OVERLONG_FRACTION = re.compile(r"(\.\d{6})\d+")


def parse_vbr_datetime(raw: str) -> datetime:
    """Parse a VBR ISO-8601 timestamp string into a timezone-aware datetime.

    Truncates the fraction to the 6 digits ``fromisoformat`` accepts, normalizes
    ``Z``, and assumes a naive value (no offset) is UTC.
    """
    text = _OVERLONG_FRACTION.sub(r"\1", raw.strip().replace("Z", "+00:00"))
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed
