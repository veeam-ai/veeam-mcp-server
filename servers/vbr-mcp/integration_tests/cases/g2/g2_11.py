# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G2-11: how much of the license is consumed, by what, and how close it is to the limit."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import CaseInputs, judge, tool_budget
from cases.patterns import any_of, near, number
from evaluators import FactsPresent, ToolsNotCalled
from stand import environment, license

# ---- What VBR serves: the base stand. Its license (1.11): a Subscription of 11 instances (VUL), 10 used by nine VMs
# and three workstations at 1/3 each, and a capacity license for the unstructured data, 1.5 of 5 TB.

ENVIRONMENT = environment()

# ---- What a correct answer says, derived from the data above.

_INSTANCES = license.LICENSE.instance_license_summary
_CAPACITY = license.LICENSE.capacity_license_summary
assert _INSTANCES is not None and _INSTANCES.objects is not None and _CAPACITY is not None
_USED, _LICENSED = _INSTANCES.used_instances_number, _INSTANCES.licensed_instances_number
_FREE = _LICENSED - _USED
_VMS, _WORKSTATIONS = _INSTANCES.objects
_SHARE, _BUCKET = license.CAPACITY.workloads
assert (_USED, _LICENSED, _FREE, _VMS.count, _WORKSTATIONS.count) == (10, 11, 1, 9, 3)

EXPECTED = (
    f"Instances (VUL): {_USED:g} of {_LICENSED:g} used ({100 * _USED / _LICENSED:.1f}%): {_VMS.count} VMs at 1 "
    f"instance each and {_WORKSTATIONS.count} workstations at 1/3 instance each (VBR shows "
    f"{_WORKSTATIONS.multiplier:g}), {_WORKSTATIONS.used_instances_number:g} in total. legacy-erp-01 is among the VMs: "
    "its job has been disabled for 25 days, and VBR counts a workload processed in the past 31 days. Capacity: "
    f"{_CAPACITY.used_capacity_tb:g} of {_CAPACITY.licensed_capacity_tb:g} TB (30%) - {_SHARE.name} "
    f"{_SHARE.used_capacity_tb:g} TB and {_BUCKET.name} {_BUCKET.used_capacity_tb:g} TB; the unstructured data uses "
    "the capacity license, not instances. The socket model is not in use. The instance license is nearly used up: "
    f"{_FREE:g} instance is left. Exceeding it does not stop backups at once: with license autoupdate enabled, as "
    "here, VBR keeps processing every workload up to 10 instances over the limit without a warning, warns weekly up "
    "to 20 over, and only beyond that leaves the excess unprocessed - though going over is out of compliance with "
    "the licensing policy. The capacity license is far from its limit."
)
"""Ground truth for the judges."""

_ONE = r"(?<![\d.,])(?:1(?:\.0+)?(?![\d.,])|\bone\b|\ba\s+single\b)"

FACTS = {
    # "10 of 11", "11 licensed, 10 used", "| Instances | 11 | 10 |", or the share of it
    "instances": any_of(near(number(_USED), number(_LICENSED), 60), r"(?<![\d.])(?:90\.9|91)\s*%"),
    "vms": near(r"\b(VMs?|virtual\s+machines?)\b", r"(?<![\d.])(9|nine)(?!\d|[.,]\d)", 40),
    "workstations": near(r"\b(workstations?|laptops?)\b", r"(?<![\d.])(3|three)(?!\d|[.,]\d)", 40),
    "workstation_weight": any_of(
        r"(?<!\d)0?\.33", r"\b1\s*/\s*3\b", r"\bone[\s-]third\b", r"\ba\s+third\s+of\s+an?\s+instance"
    ),
    "capacity": near(rf"{number(_CAPACITY.used_capacity_tb)}\s*(TB)?", r"(?<![\d.])5(\.0+)?\s*TB", 60),
    "share": near(r"fs01\\+finance", r"(?<![\d.])1\.20?(?!\d)", 100),
    "bucket": near(r"lab-docs-prod", r"(?<![\d.])0?\.30?(?!\d)", 100),
    "one_free": near(_ONE, r"\b(free|left|remain\w*|available|spare|headroom|unused|room)\b", 40),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    """**Instances (VUL):** 10 of 11 licensed instances are used (90.9%).
- 9 VMs at 1 instance each = 9 (web-01, web-02, app-01, fs-01, sql-prod-01, sql-prod-02, sql-dev-01, report-01, legacy-erp-01)
- 3 workstations (laptop-hr-01, laptop-hr-02, laptop-fin-01) at 0.33 instance each = 1

**Capacity license:** 1.5 of 5 TB used - \\\\fs01\\finance 1.2 TB and lab-docs-prod 0.3 TB.

The socket model is not used. You are close to the instance limit: only 1 instance is left. legacy-erp-01 still counts although Legacy-Archive is disabled, because it was backed up in the last 31 days; revoking it would free an instance. Going over would not stop backups right away - with autoupdate on, VBR keeps processing up to 10 instances over the limit without warnings - but you would be out of compliance.""",
    """| Model | Licensed | Used |
|---|---|---|
| Instances (VUL) | 11 | 10 |
| Capacity | 5 TB | 1.5 TB |

What consumes the instances: nine VMs (one instance each) and three laptops, each counted as 1/3 of an instance. The capacity license covers the file share \\\\fs01\\finance (1.2 TB) and the bucket lab-docs-prod (0.3 TB). There is room for one more instance, so the VUL license is nearly full; capacity is only at 30%.""",
]

BAD = {
    "instances": (
        "You use 9 of 11 instances: 9 VMs; the 3 laptops at 0.33 each round down. Capacity 1.5 of 5 TB: "
        "\\\\fs01\\finance 1.2 TB, lab-docs-prod 0.3 TB. One instance is free."
    ),
    "workstation_weight": (
        "10 of 11 instances used: 9 VMs and 3 workstations counted as a single instance together. Capacity 1.5 of "
        "5 TB: \\\\fs01\\finance 1.2 TB, lab-docs-prod 0.3 TB. 1 instance is left."
    ),
    "one_free": (
        "10 of 11 instances used by 9 VMs and 3 laptops at 1/3 each. Capacity 1.5 of 5 TB: \\\\fs01\\finance 1.2 "
        "TB, lab-docs-prod 0.3 TB. You have no instances to spare."
    ),
    "capacity": (
        "10 of 11 instances used by 9 VMs and 3 laptops at 1/3 each; 1 instance is free. The file share and the "
        "bucket are not licensed."
    ),
}

_ALLOWED = (
    "It is acceptable, and not a violation, to note that legacy-erp-01 still consumes an instance although its job "
    "Legacy-Archive has been disabled for 25 days (VBR counts a workload for 31 days after it was last processed), "
    "and to suggest revoking it as advice; to quote VBR's own license report counters; to give the license "
    "expiration (2026-11-21, in 44 days); or to explain what happens when the instance count is exceeded."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G2-11",
        inputs=CaseInputs(
            question="How much of our license are we consuming, what is consuming it, and are we close to the limit?",
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G2", "base_stand": "1.11"},
        evaluators=[
            # the capacity workloads come from get_license_status only; create_license_report (VBR's own counters),
            # list_protected_objects and get_job_states are reads the case allows on top
            ToolCorrectness(expected_tools=["get_license_status"], allow_extra=True),
            *tool_budget(3),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "fractional_instances",
                "The output does not round the workstations' fractional instance weight (1/3, shown as 0.33, each) "
                "down to zero, and does not claim the workstations consume no instances.",
            ),
            _judge(
                "no_socket_model",
                "The output does not present the socket license model as being in use: it is not used at all on "
                "this server. Saying that it is not used is fine.",
            ),
            _judge(
                "close_to_limit",
                "The output says the instance (VUL) license is nearly used up: about one instance of 11 is left.",
            ),
            _judge(
                "no_hard_limit",
                "The output does not claim that backups stop, fail or are refused as soon as the 11 licensed "
                "instances are exceeded (for example at a 12th instance). With license autoupdate enabled VBR keeps "
                "processing every workload up to 10 instances over the limit without a warning, warns weekly up to "
                "20 over, and only beyond that leaves the excess unprocessed. Saying that exceeding the license puts "
                "the server out of compliance, or not discussing exceeding at all, is fine.",
            ),
            _judge(
                "capacity_not_close",
                "The output does not present the capacity license (1.5 of 5 TB, 30%) as close to its limit.",
            ),
            _judge(
                "unstructured_not_instances",
                "The output does not count the file share or the bucket in instances (for example at 500 GB per "
                "instance): they are covered by the capacity license.",
            ),
        ],
    )
