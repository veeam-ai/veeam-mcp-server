# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""VBR REST API 1.3-rev2 response models, as far as the tests mock them: one module per area of the API.

Each mirrors the swagger schema of the same name (``ServerInfoModel`` -> ``ServerInfo``). Fields are snake_case
in Python and serialize to VBR's camelCase, so a model dumps to exactly the JSON VBR would send.
"""

from datetime import datetime, timedelta
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, PlainSerializer
from pydantic.alias_generators import to_camel


def _vbr_datetime(value: datetime) -> str:
    """VBR's wire format.

    A UTC instant is written with ``Z`` and no fraction, e.g. ``2027-03-31T00:00:00Z``; any other offset with
    seven fractional digits and the offset, e.g. ``2026-10-07T09:00:00.0000000+02:00``.
    """
    if value.utcoffset() == timedelta(0):
        return f"{value:%Y-%m-%dT%H:%M:%S}Z"
    return value.strftime("%Y-%m-%dT%H:%M:%S.%f0%:z")


VbrDateTime = Annotated[AwareDatetime, PlainSerializer(_vbr_datetime, return_type=str)]


class VbrModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, validate_by_name=True, serialize_by_alias=True, extra="forbid")
