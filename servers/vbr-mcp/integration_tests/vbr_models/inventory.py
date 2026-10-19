# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""``/api/v1/inventory/vmware/hosts``, ``POST /api/v1/inventory``, ``POST /api/v1/inventory/{hostname}``."""

from typing import Literal

from vbr_models import VbrModel


class VmwareObject(VbrModel):
    """``VmwareObjectModel``: the ``VSphere`` subtype of ``InventoryObjectModel``."""

    platform: Literal["VSphere"] = "VSphere"
    host_name: str
    name: str
    type: Literal[  # ``EVmwareInventoryType``, as far as the stand holds them
        "vCenterServer",
        "Datacenter",
        "Cluster",
        "Host",
        "ResourcePool",
        "Folder",
        "Datastore",
        "Network",
        "DVSNetwork",
        "VirtualMachine",
    ]
    object_id: str | None = None
    size: str | None = None


class PaginationResult(VbrModel):
    """``PaginationResult``: the ``pagination`` of a list answer."""

    total: int
    count: int
    skip: int | None = None
    limit: int | None = None


class InventoryBrowserResult(VbrModel):
    """``InventoryBrowserResult``: what ``POST /api/v1/inventory`` and ``POST /api/v1/inventory/{hostname}`` answer.

    ``hierarchyType`` names the hierarchy a request asked for, ``null`` when it asked for none (and for the roots).
    """

    data: list[VmwareObject]
    pagination: PaginationResult
    hierarchy_type: str | None = None
