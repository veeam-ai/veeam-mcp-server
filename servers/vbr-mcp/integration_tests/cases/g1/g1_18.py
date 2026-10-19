# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G1-18: whether any VMs are still running from backup via Instant Recovery - one has been for three days."""

from datetime import date
from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import CaseInputs, Environment, judge, tool_budget
from cases.patterns import name
from evaluators import FactsPresent, ToolsNotCalled
from stand import environment, protected, sessions
from stand.ids import at, mnemonic
from stand.inventory import ESX01, ESX02
from vbr_models.instant_recovery import InstantRecoveryMount, InstantRecoverySpec, SecureRestore

# ---- What VBR serves: the base stand, plus two Instant Recovery mounts (1.16 has none). On 10-04 an admin published
# legacy-erp-01's 2026-09-12 restore point as legacy-erp-01_restored to look something up in the old ERP, and left it
# Mounted: the VM still runs from the backup file through vPower NFS (User Guide v13, instant_recovery). This morning
# a second mount, a test copy of web-01, failed. An empty answer is G1-20's subject; this one is the forgotten mount.

ERP_SESSION, WEB_TEST_SESSION = mnemonic("40000000", 25), mnemonic("40000000", 26)
ERP_MOUNT, WEB_TEST_MOUNT = ERP_SESSION, WEB_TEST_SESSION  # a mount's id is its Instant Recovery session's

ERP_POINT = protected.point_on("legacy-erp-01", date(2026, 9, 12))
WEB_POINT = protected.point_on("web-01", date(2026, 10, 6))
MOUNTED_SINCE = at(4, 14, 12, 8)
FAILED_AT = at(7, 8, 5, 30)
MOUNT_ERROR = (
    f"Failed to publish VM web-01_test: unable to mount the vPower NFS datastore VeeamBackup_repo-win01 to host "
    f"{ESX01.name}."
)

MOUNTS = [
    InstantRecoveryMount(
        id=ERP_MOUNT,
        session_id=ERP_SESSION,
        state="Mounted",
        spec=InstantRecoverySpec(
            restore_point_id=ERP_POINT.id,
            type="Customized",
            secure_restore=SecureRestore(antivirus_scan_enabled=False, yara_scan_enabled=False),
            nics_enabled=False,
            power_up=True,
            reason="Look up the Q2 2025 invoices in the old ERP",
        ),
        vm_name="legacy-erp-01_restored",
        job_name="Legacy-Archive",
        restore_point_date=ERP_POINT.creation_time,
        host_name=ESX02.name,
    ),
    InstantRecoveryMount(
        id=WEB_TEST_MOUNT,
        session_id=WEB_TEST_SESSION,
        state="Failed",
        spec=InstantRecoverySpec(
            restore_point_id=WEB_POINT.id,
            type="Customized",
            secure_restore=SecureRestore(antivirus_scan_enabled=False, yara_scan_enabled=False),
            nics_enabled=False,
            power_up=True,
            reason="Test the IIS patch on a copy",
        ),
        vm_name="web-01_test",
        job_name="Daily-VMs",
        restore_point_date=WEB_POINT.creation_time,
        host_name=ESX01.name,
        error_message=MOUNT_ERROR,
    ),
]

IR_SESSIONS = [
    sessions.session(25, "legacy-erp-01_restored", MOUNTED_SINCE, None, "None", initiated_by=sessions.ADMIN,
                     session_type="InstantRecovery", platform="VMware"),
    sessions.session(26, "web-01_test", FAILED_AT, at(7, 8, 7, 2), "Failed", message=MOUNT_ERROR,
                     initiated_by=sessions.ADMIN, session_type="InstantRecovery", platform="VMware"),
]  # fmt: skip

SESSION_LOGS = {
    ERP_SESSION: sessions.log(MOUNTED_SINCE, [
        ("Succeeded", f"Starting Instant Recovery of legacy-erp-01 to {ESX02.name}"),
        ("Succeeded", f"Publishing restore point of {ERP_POINT.creation_time:%Y-%m-%d %H:%M} via vPower NFS"),
        ("Succeeded", "VM legacy-erp-01_restored has been registered"),
        ("Succeeded", "VM legacy-erp-01_restored has been powered on"),
    ]),
    WEB_TEST_SESSION: sessions.log(FAILED_AT, [
        ("Succeeded", f"Starting Instant Recovery of web-01 to {ESX01.name}"),
        ("Failed", MOUNT_ERROR),
    ], at(7, 8, 7, 2)),
}  # fmt: skip

ENVIRONMENT: Environment = environment(
    instant_recovery_mounts=MOUNTS,
    sessions=sorted([*sessions.SESSIONS, *IR_SESSIONS], key=lambda s: s.creation_time, reverse=True),
    session_logs=SESSION_LOGS,
)

# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    f"Yes, one VM: legacy-erp-01, published as legacy-erp-01_restored on {ESX02.name} from its "
    f"{ERP_POINT.creation_time:%Y-%m-%d} restore point, is Mounted - it has been running from the backup file "
    f"through vPower NFS since {MOUNTED_SINCE:%Y-%m-%d %H:%M} (its Instant Recovery session), about three days. "
    "Instant Recovery is meant to be temporary: the VM runs from the backup repository with limited performance and "
    "its changes are kept outside production storage. To keep it, migrate it to production (Quick Migration); if it "
    "is no longer needed, stop the Instant Recovery (unmount it), which discards its changes. A second mount, "
    f"web-01_test, failed this morning ({MOUNT_ERROR}) and is not running."
)
"""Ground truth for the judges."""

FACTS = {
    "vm": name("legacy-erp-01"),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

_ALLOWED = (
    "It is acceptable, and not a violation, to give the restore point the VM was published from, the host, the "
    "reason recorded for the mount or since when it has been running, to mention the failed web-01_test mount and "
    "its error, or to offer (without doing it) to migrate or unmount legacy-erp-01_restored."
)

GOOD = [
    (
        "Yes - one VM is still running from backup: **legacy-erp-01**, published as legacy-erp-01_restored on "
        "esx02.lab.local from its 2026-09-12 restore point (mount state: Mounted). It has been running from the backup "
        "via vPower NFS since 2026-10-04 14:12. Instant Recovery is meant to be temporary: migrate it to production "
        "storage (Quick Migration) if you need to keep it, or stop the session to discard it. A second mount, "
        "web-01_test, failed this morning and is not running."
    ),
    (
        "One: legacy-erp-01 (as legacy-erp-01_restored) is Mounted and running off its backup - since Oct 4. Next step: "
        "finalize it - quick-migrate it to a production datastore or unmount it. (web-01_test is listed too, but its "
        "mount Failed: the vPower NFS datastore could not be mounted to esx01.)"
    ),
    (
        "| VM | State | From restore point | Host |\n|---|---|---|---|\n| legacy-erp-01_restored | Mounted | 2026-09-12 "
        "03:04 | esx02.lab.local |\n| web-01_test | Failed | 2026-10-06 22:06 | esx01.lab.local |\n\n"
        "legacy-erp-01 is running from the backup, which is only meant as a temporary state - migrate it or unmount it."
    ),
]
"""Answers a correct agent could give: every fact must match each of them."""

BAD = {
    "vm": "No VMs are running from backup via Instant Recovery right now; the only mount, web-01_test, failed.",
}
"""Per fact, an answer that gets that fact wrong: the fact must not match it."""


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G1-18",
        inputs=CaseInputs(
            question="Do we have any VMs still running from backup via Instant Recovery?",
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G1", "base_stand": "1.16 + delta"},
        evaluators=[
            # The mount list is the answer; the mount's session (since when) is a read the case allows on top of it.
            ToolCorrectness(expected_tools=["get_instant_recovery_mount_status"], allow_extra=True),
            *tool_budget(2),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "ir_is_temporary",
                "The output does not present legacy-erp-01_restored as a finished restore or a normal production VM: "
                "it says the VM runs from the backup via Instant Recovery. Adding that this is meant to be temporary "
                "(migrate it to keep it, or unmount it) is welcome, as advice, not as something done.",
            ),
            _judge(
                "failed_not_running",
                "The output does not present web-01_test as running from backup: its mount failed. Leaving it out, "
                "or saying it failed, is fine.",
            ),
            _judge(
                "since_from_session",
                "If the output says since when legacy-erp-01_restored has been running, that is 2026-10-04 (its "
                "Instant Recovery session), not 2026-09-12, which is the date of the restore point it was published "
                "from.",
            ),
            _judge(
                "no_invented_mounts",
                "The output names no other VM as running via Instant Recovery, and does not claim to have migrated, "
                "unmounted or started anything.",
            ),
        ],
    )
