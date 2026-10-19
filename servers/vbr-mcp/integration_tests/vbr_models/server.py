# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""``/api/v1/serverInfo``, ``/api/v1/serverTime``."""

from typing import Literal
from uuid import UUID

from vbr_models import VbrDateTime, VbrModel


class VeeamRegistration(VbrModel):
    """``VeeamRegistrationInfo``: registration of the backup server on the My Account portal."""

    is_registered: bool
    expiration_date: VbrDateTime | None = None
    thumprint: str | None = None  # sic: the API's own spelling


class ServerInfo(VbrModel):
    """``ServerInfoModel``, ``GET /api/v1/serverInfo``."""

    vbr_id: UUID
    name: str
    build_version: str
    patches: list[str]
    database_vendor: str
    sql_server_edition: str
    sql_server_version: str
    database_schema_version: str
    database_content_version: str
    veeam_registration: VeeamRegistration
    platform: Literal["Linux", "Windows"]


class ServerTime(VbrModel):
    """``ServerTimeModel``, ``GET /api/v1/serverTime``."""

    server_time: VbrDateTime
    time_zone: str | None = None
    iana_time_zone_id: str | None = None
