# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

import csv
import io
import json
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from vbr_mcp.datetimes import parse_vbr_datetime
from vbr_mcp.pagination import fetch_all
from vbr_mcp.server import mcp, vbr_client
from vbr_mcp.server_time import get_server_time
from vbr_mcp.tool_annotations import DESTRUCTIVE, READ_ONLY

_REVOKE_PATHS = {
    "socket": "/api/v1/license/sockets/{id}/revoke",
    "instance": "/api/v1/license/instances/{id}/revoke",
    "capacity": "/api/v1/license/capacity/{id}/revoke",
}


@mcp.tool(annotations=READ_ONLY)
async def get_license_status() -> dict[str, Any]:
    """Return the installed license's status plus its per-workload breakdown for every active model.

    Models are per-socket, per-instance/VUL, and per-capacity. Adds `daysToExpiry`/`daysToSupportExpiry` (against
    the VBR server clock;
    `None` when the source date is absent). A model is in use when its summary
    (`socketLicenseSummary`/`instanceLicenseSummary`/`capacityLicenseSummary`)
    carries a licensed total, or its `*Workloads` list is non-empty - report
    only active models. `status` of `"Expired"`/`"Invalid"` is an alert on its
    own. `supportExpirationDate` (updates/support eligibility) is separate from
    license expiry and does not stop jobs running.

    VBR's rules behind the numbers (User Guide v13, licensing): a workload
    consumes an instance while it has been processed in the past 31 days - also
    when its job is now disabled - and is released after 31 days without a
    backup, or at once by `revoke_license`. A Subscription license that expired
    reads `"Expired"` but keeps everything working for a 30-day grace period;
    after it VBR stops processing workloads (jobs fail) while restores from
    existing backups still work. A VUL license with `autoUpdateEnabled` may be
    exceeded by less than 10 instances (or 10%, whichever is greater) with no
    effect, by 10-20 with a weekly warning; workloads beyond 20 over are not
    processed (without auto update: 5, 5-10 and 10).
    """
    now = await get_server_time(vbr_client)
    installed = await vbr_client.get("/api/v1/license")
    socket_rows = await fetch_all(vbr_client, "/api/v1/license/sockets")
    instance_rows = await fetch_all(vbr_client, "/api/v1/license/instances")
    capacity_response = await vbr_client.get("/api/v1/license/capacity")
    capacity_rows = capacity_response.get("workloads", []) if isinstance(capacity_response, dict) else []

    return {
        **installed,
        "socketWorkloads": socket_rows,
        "instanceWorkloads": instance_rows,
        "capacityWorkloads": capacity_rows,
        "daysToExpiry": _days_until(installed.get("expirationDate"), now),
        "daysToSupportExpiry": _days_until(installed.get("supportExpirationDate"), now),
    }


def _days_until(expiration_date: str | None, now: datetime) -> int | None:
    if not expiration_date:
        return None
    return (parse_vbr_datetime(expiration_date) - now).days


@mcp.tool(annotations=READ_ONLY)
async def create_license_report(report_format: Literal["Json", "Html", "Pdf"] = "Json") -> list[dict[str, Any]] | str:
    """Generate VBR's own point-in-time license usage report. Read-only despite the `POST`.

    This is the same report downloadable from the console. With `report_format="Json"` (default) returns one dict per licensed VBR
    installation, each with a flat `counters` list (the raw
    `data[] -> instances -> counters[]` nesting flattened, with `supportId`/
    `licenseId`/`licenseType` merged onto every counter row). Counter values are
    not coerced - some arrive as numbers, others as numeric strings; convert
    only where display/math needs it. With `"Html"`/`"Pdf"` returns the raw
    report text/bytes instead.
    """
    text = await vbr_client.post_text(
        "/api/v1/license/createReport", json={"reportFormat": report_format}, read_only=True
    )
    if report_format != "Json":
        return text
    if not text.strip():
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return _parse_csv_report(text)
    return [_flatten_product(product) for product in _normalize_products(parsed)]


def _normalize_products(parsed: object) -> list[dict[str, Any]]:
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        if "products" in parsed:
            return parsed.get("products") or []
        return [parsed]
    return []


def _flatten_product(product: dict[str, Any]) -> dict[str, Any]:
    counters: list[dict[str, Any]] = []
    for data_item in product.get("data") or []:
        instances = (data_item or {}).get("instances") or {}
        instance_fields = {
            "supportId": instances.get("supportId"),
            "licenseId": instances.get("licenseId"),
            "licenseType": instances.get("licenseType"),
        }
        for counter in instances.get("counters") or []:
            counters.append({**instance_fields, **counter})
    return {
        "productVersion": product.get("productVersion"),
        "edition": product.get("edition"),
        "package": product.get("package"),
        "installationId": product.get("installationId"),
        "counters": counters,
    }


_CSV_HEADER_MAP = {
    "Product Version": "productVersion",
    "Edition": "edition",
    "Installation ID": "installationId",
    "Support ID": "supportId",
    "License ID": "licenseId",
    "License Type": "licenseType",
    "Counter Type": "counterType",
    "Multiplier": "multiplier",
    "Instances In Grace": "instancesInGrace",
    "Number Of Objects": "numberOfObjects",
    "Number Of New Objects": "numberOfNewObjects",
    "Number Of Rental Objects": "numberOfRentalObjects",
    "Number Of Removed Objects": "numberOfRemovedObjects",
    "Consumed Instances": "consumedInstances",
    "New Instances": "newInstances",
    "Rental Instances": "rentalInstances",
    "Removed Instances": "removedInstances",
    "Reason For Removal": "reasonForRemoval",
}
_CSV_PRODUCT_KEYS = ("productVersion", "edition", "installationId")


def _parse_csv_report(text: str) -> list[dict[str, Any]]:
    products: dict[tuple, dict[str, Any]] = {}
    for row in csv.DictReader(io.StringIO(text)):
        mapped = {_CSV_HEADER_MAP.get(header, header): value for header, value in row.items()}
        key = tuple(mapped.get(field) for field in _CSV_PRODUCT_KEYS)
        product = products.setdefault(
            key,
            {
                "productVersion": mapped.get("productVersion"),
                "edition": mapped.get("edition"),
                "package": mapped.get("package"),
                "installationId": mapped.get("installationId"),
                "counters": [],
            },
        )
        counter = {field: value for field, value in mapped.items() if field not in _CSV_PRODUCT_KEYS}
        product["counters"].append(counter)
    return list(products.values())


@mcp.tool(annotations=DESTRUCTIVE)
async def revoke_license(license_type: Literal["socket", "instance", "capacity"], id: UUID) -> None:
    """Revoke one consumed license unit, freeing it back to the pool.

    `license_type` selects the model: `"socket"` (a licensed host), `"instance"`
    (a VUL workload), or `"capacity"` (a capacity/TB workload) - `id` is that
    unit's id from the matching `*Workloads` list in `get_license_status`.
    """
    await vbr_client.post(_REVOKE_PATHS[license_type].format(id=id))
