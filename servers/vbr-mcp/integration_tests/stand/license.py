# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""The license (1.11): ``/license``, its instance, socket and capacity workloads, and the license report.

A Subscription of 11 instances (VUL), 10 used: nine VMs at 1 and three workstations at 1/3; legacy-erp-01 still counts,
its last backup being under 31 days old. A capacity license covers the unstructured data, 1.5 of 5 TB. It expires on
2026-11-21, 44 days after T0 by vbr-mcp's count (``daysToExpiry``).
"""

import re
from datetime import UTC, datetime
from typing import Any

from stand.agents import LAPTOPS
from stand.ids import C01, C02, I01, I02, I03, I04, I05, I06, I07, I08, I09, I10, I11, I12
from stand.inventory import VMS
from vbr_mock.markers import VbrAction
from vbr_models.license import (
    CapacityLicenseSummary,
    CapacityLicenseWorkload,
    CapacityLicenseWorkloads,
    InstalledLicense,
    InstanceLicenseObject,
    InstanceLicenseSummary,
    InstanceLicenseWorkload,
    SocketLicenseSummary,
    SocketLicenseWorkload,
)

EXPIRES = datetime(2026, 11, 21, tzinfo=UTC)

LICENSE = InstalledLicense(
    status="Valid",
    expiration_date=EXPIRES,
    type="Subscription",
    edition="EnterprisePlus",
    licensed_to="Lab Corp",
    socket_license_summary=SocketLicenseSummary(
        licensed_sockets_number=0, used_sockets_number=0, remaining_sockets_number=0
    ),
    instance_license_summary=InstanceLicenseSummary(
        licensed_instances_number=11,
        used_instances_number=10.0,
        new_instances_number=0,
        rental_instances_number=0,
        objects=[
            # type names as VBR writes them (swagger InstalledLicenseModelExample: "Virtual Machines", "Applications")
            InstanceLicenseObject(type="Virtual Machines", count=9, multiplier=1, used_instances_number=9),
            InstanceLicenseObject(type="Workstations", count=3, multiplier=0.33, used_instances_number=1.0),
        ],
    ),
    capacity_license_summary=CapacityLicenseSummary(licensed_capacity_tb=5, used_capacity_tb=1.5),
    support_id="01234567",
    support_expiration_date=EXPIRES,
    auto_update_enabled=True,
    free_agent_instance_consumption_enabled=False,
    cloud_connect="Disabled",
    is_multi_section=False,
    proactive_support_enabled=False,
)
"""``GET /api/v1/license``."""

LICENSED_VMS = ["web-01", "web-02", "app-01", "fs-01", "sql-prod-01", "sql-prod-02", "sql-dev-01", "report-01",
                "legacy-erp-01"]  # fmt: skip

INSTANCES: list[InstanceLicenseWorkload] = [
    InstanceLicenseWorkload(
        name=name,
        host_name=VMS[name].host,
        used_instances_number=1,
        type="VM",
        instance_id=instance_id,
        platform_type="VMware",
        can_be_revoked=True,
    )
    for name, instance_id in zip(LICENSED_VMS, (I01, I02, I03, I04, I05, I06, I07, I08, I09), strict=True)
] + [
    InstanceLicenseWorkload(
        name=name,
        host_name=name,
        used_instances_number=0.33,
        type="Workstation",
        instance_id=instance_id,
        platform_type="WindowsWorkstation",
        can_be_revoked=name != "laptop-hr-01",  # VBR does not let this one be revoked
    )
    for name, instance_id in zip(LAPTOPS, (I10, I11, I12), strict=True)
]
"""``GET /api/v1/license/instances``: I01-I12."""

SOCKETS: list[SocketLicenseWorkload] = []
"""``GET /api/v1/license/sockets``: the socket model is not in use."""

CAPACITY = CapacityLicenseWorkloads(
    workloads=[
        CapacityLicenseWorkload(name="\\\\fs01\\finance", used_capacity_tb=1.2, type="FileShare", instance_id=C01),
        CapacityLicenseWorkload(name="lab-docs-prod", used_capacity_tb=0.3, type="ObjectStorage", instance_id=C02),
    ]
)
"""``GET /api/v1/license/capacity``: not paged, a bare ``workloads`` list."""

REPORT_TITLE = "License Usage Report"

WORKLOADS = {"Virtual Machines": "VM", "Workstations": "Workstation", "Servers": "Server"}
"""The workload type an instance license row names (``/license/instances``) for an object type of the summary."""

_COUNTERS = {"Virtual Machines": "VBR-VBR-VM-VSPHERE", "Workstations": "VBR-VAW-WORKSTATION"}
"""The ``Json`` report's counter per instance object type (swagger LicenseCreateReportExample; the workstation
counter's name is ours)."""

_INSTALLATION_ID, _LICENSE_ID = "5b1e9a7c-0d3f-4e61-9a2b-7c8d9e0f1a2b", "b3f0c2d4-6e8a-4c1b-9d7e-2a4b6c8d0e1f"


def _edition(installed: InstalledLicense) -> str:
    """The edition as the report writes it: ``Enterprise Plus`` for ``EnterprisePlus``."""
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", installed.edition)


def _objects(installed: InstalledLicense) -> list[InstanceLicenseObject]:
    summary = installed.instance_license_summary
    return list(summary.objects or []) if summary else []


def html_report(installed: InstalledLicense, capacity: CapacityLicenseWorkloads) -> str:
    """The ``Html`` license report of ``installed``: its instances by workload and its capacity workloads."""
    summary, capacity_summary = installed.instance_license_summary, installed.capacity_license_summary
    expires = f"{installed.expiration_date:%Y-%m-%d}" if installed.expiration_date else ""
    objects = _objects(installed)
    rows = [
        "<!DOCTYPE html>",
        "<html>",
        f'<head><meta charset="utf-8"><title>{REPORT_TITLE}</title></head>',
        "<body>",
        f"<h1>{REPORT_TITLE}</h1>",
        "<p>Backup server: vbr-lab01. Generated: 2026-10-07 09:00 (UTC+02:00).</p>",
        "<table>",
        f"<tr><th>Licensed to</th><td>{installed.licensed_to}</td></tr>",
        f"<tr><th>Edition</th><td>{_edition(installed)}</td></tr>",
        f"<tr><th>Type</th><td>{installed.type or ''}</td></tr>",
        f"<tr><th>Support ID</th><td>{installed.support_id}</td></tr>",
        f"<tr><th>Expiration date</th><td>{expires}</td></tr>",
        "</table>",
    ]
    if summary is not None:
        rows += [
            "<h2>Instances</h2>",
            "<table>",
            "<tr><th>Workload</th><th>Objects</th><th>Instances used</th></tr>",
            *(
                f"<tr><td>{WORKLOADS.get(obj.type, obj.type)}</td><td>{obj.count}</td>"
                f"<td>{obj.used_instances_number:g}</td></tr>"
                for obj in objects
            ),
            (
                f"<tr><th>Total</th><td>{sum(obj.count for obj in objects)}</td>"
                f"<td>{summary.used_instances_number:g} of {summary.licensed_instances_number:g}</td></tr>"
            ),
            "</table>",
        ]
    if capacity_summary is not None:
        rows += [
            "<h2>Capacity</h2>",
            "<table>",
            "<tr><th>Workload</th><th>Type</th><th>Used, TB</th></tr>",
            *(
                f"<tr><td>{workload.name}</td><td>{workload.type}</td><td>{workload.used_capacity_tb:g}</td></tr>"
                for workload in capacity.workloads
            ),
            (
                f"<tr><th>Total</th><td></td><td>{capacity_summary.used_capacity_tb:g} of "
                f"{capacity_summary.licensed_capacity_tb:g}</td></tr>"
            ),
            "</table>",
        ]
    return "\n".join([*rows, "</body>", "</html>", ""])


def json_report(installed: InstalledLicense) -> str:
    """The ``Json`` license report of ``installed`` as VBR answers it: a CSV row per instance counter.

    The column set is swagger LicenseCreateReportExample's. The capacity license is reported apart.
    """
    header = (
        "Product Version,Edition,Installation ID,Support ID,License ID,License Type,Counter Type,Multiplier,"
        "Instances In Grace,Number Of Objects,Number Of New Objects,Number Of Rental Objects,Number Of Removed Objects,"
        "Consumed Instances,New Instances,Rental Instances,Removed Instances,Reason For Removal"
    )
    rows = [
        f"13.1.0.344,{_edition(installed)},{_INSTALLATION_ID},{installed.support_id},{_LICENSE_ID},{installed.type or ''},"
        f"{_COUNTERS.get(obj.type, 'VBR-' + obj.type.upper().replace(' ', '-'))},{obj.multiplier:g},0,{obj.count},0,0,0,"
        f"{obj.used_instances_number:g},0,0,0,"
        for obj in _objects(installed)
    ]
    return "\n".join([header, *rows])


PDF_REPORT = "%PDF-1.7\n% License Usage Report, vbr-lab01, 2026-10-07\n%%EOF\n"
"""The ``Pdf`` license report, as far as a text tool can carry it."""


def report(installed: InstalledLicense, capacity: CapacityLicenseWorkloads) -> VbrAction:
    """What ``POST /api/v1/license/createReport`` answers for ``installed``, a read VBR serves over ``POST``.

    The report comes in the format the body asks for (``Json`` unless it says otherwise, as VBR defaults). Its numbers
    are those of the license and its capacity workloads, so a case that changes the license gets a report that agrees
    with it.
    """
    reports = {"Html": html_report(installed, capacity), "Pdf": PDF_REPORT}
    default = json_report(installed)

    def answer(body: Any) -> str:
        report_format = body.get("reportFormat") if isinstance(body, dict) else None
        return reports.get(report_format or "", default)

    return VbrAction(response_of=answer)


LICENSE_REPORT = report(LICENSE, CAPACITY)
"""The base stand's license report."""
