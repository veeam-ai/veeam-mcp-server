# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""``/api/v1/license``, ``/license/instances``, ``/license/sockets``, ``/license/capacity``."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from vbr_models import VbrDateTime, VbrModel

CapacityObjectType = Literal["FileShare", "ObjectStorage"]


class SocketLicenseSummary(VbrModel):
    """``SocketLicenseSummaryModel``."""

    licensed_sockets_number: int
    used_sockets_number: int
    remaining_sockets_number: int


class InstanceLicenseObject(VbrModel):
    """``InstanceLicenseObjectModel``: instance consumption of one object type."""

    type: str
    count: int
    multiplier: float
    used_instances_number: float


class InstanceLicenseSummary(VbrModel):
    """``InstanceLicenseSummaryModel``."""

    licensed_instances_number: float
    used_instances_number: float
    new_instances_number: float
    rental_instances_number: float
    objects: list[InstanceLicenseObject] | None = None


class CapacityLicenseSummary(VbrModel):
    """``CapacityLicenseSummaryModel``."""

    licensed_capacity_tb: float
    used_capacity_tb: float


class InstalledLicense(VbrModel):
    """``InstalledLicenseModel``, ``GET /api/v1/license``."""

    status: Literal["Expired", "Invalid", "Valid"]
    expiration_date: VbrDateTime | None = None
    type: Literal["Empty", "Evaluation", "Free", "NFR", "Perpetual", "Rental", "Subscription", "Promo"] | None = None
    edition: Literal["Community", "Enterprise", "EnterprisePlus", "Standard", "Unspecified"]
    licensed_to: str
    socket_license_summary: SocketLicenseSummary | None = None
    instance_license_summary: InstanceLicenseSummary | None = None
    capacity_license_summary: CapacityLicenseSummary | None = None
    support_id: str
    support_expiration_date: VbrDateTime | None = None
    auto_update_enabled: bool
    free_agent_instance_consumption_enabled: bool
    cloud_connect: Literal["Disabled", "Enabled", "Enterprise", "Invalid"]
    is_multi_section: bool = Field(alias="IsMultiSection")  # sic: the API's own casing
    proactive_support_enabled: bool


class InstanceLicenseWorkload(VbrModel):
    """``InstanceLicenseWorkloadModel``, an item of ``GET /api/v1/license/instances``."""

    name: str
    display_name: str | None = None
    host_name: str
    used_instances_number: float
    type: str
    instance_id: UUID
    platform_type: Literal["VMware", "HyperV", "WindowsWorkstation", "WindowsServer", "LinuxServer"] | None = None
    can_be_revoked: bool


class CapacityLicenseWorkload(VbrModel):
    """``CapacityLicenseWorkloadModel``."""

    name: str
    used_capacity_tb: float
    type: CapacityObjectType
    instance_id: UUID


class CapacityLicenseWorkloads(VbrModel):
    """``CapacityLicenseWorkloadResult``, ``GET /api/v1/license/capacity``: not paged, a bare ``workloads`` list."""

    workloads: list[CapacityLicenseWorkload]


class SocketLicenseWorkload(VbrModel):
    """``SocketLicenseWorkloadModel``, an item of ``GET /api/v1/license/sockets``."""

    name: str
    host_name: str
    host_id: UUID
    sockets_number: int
    cores_number: int
    type: Literal["HyperV", "Universal", "Unlicensed", "vSphere"]
