# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G1-10: the WAN accelerators, their cache, high-bandwidth mode and health."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import CaseInputs, judge, tool_budget
from cases.patterns import any_of, gb
from evaluators import FactsPresent, ToolsNotCalled
from stand import environment
from stand.proxies import WAN_ACCELERATORS
from vbr_models.infrastructure import WanAccelerator

# ---- What VBR serves: the base stand. wan01 (HQ) has high-bandwidth mode off, wan02 (DR site) on; Copy-to-DR copies
# through wan01 to wan02. The API reports no online or health state for WAN accelerators, and their endpoint carries
# no source/target role. High-bandwidth mode works only when both accelerators of a pair have it: "To use the High
# bandwidth mode, enable the option for WAN accelerators at both sites" (User Guide v13, wan_server).

ENVIRONMENT = environment()

# ---- What a correct answer says, derived from the stand.

_WAN01, _WAN02 = WAN_ACCELERATORS
assert not _WAN01.server.high_bandwidth_mode_enabled and _WAN02.server.high_bandwidth_mode_enabled


def _summary(wan: WanAccelerator) -> str:
    mode = "on" if wan.server.high_bandwidth_mode_enabled else "off"
    return (
        f"{wan.name} ({wan.server.description}): {wan.cache.cache_size} {wan.cache.cache_size_unit} cache in "
        f"{wan.cache.cache_folder}, high-bandwidth mode {mode}, {wan.server.streams_count} streams"
    )


EXPECTED = (
    f"{_summary(_WAN01)}; {_summary(_WAN02)}. The API exposes no online or health state for WAN accelerators, so "
    "whether they are healthy cannot be told from this data. The accelerator endpoint carries no source/target role; "
    "the Copy-to-DR job copies through wan01 to wan02. As high-bandwidth mode needs both sides, that pair does not "
    "run in high-bandwidth mode although wan02 has it on."
)
"""Ground truth for the judges."""

FACTS = {
    "wan01": r"\bwan01\b",
    "wan02": r"\bwan02\b",
    "wan01_cache": gb(_WAN01.cache.cache_size or 0, tb=False),
    "wan02_cache": gb(_WAN02.cache.cache_size or 0, tb=False),
    "high_bandwidth": any_of(r"high[\s-]*bandwidth", r"\bHBM\b"),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

_ALLOWED = (
    "It is acceptable, and not a violation, to give the cache folders, the streams count and the traffic port, to "
    "derive the roles from the Copy-to-DR job configuration (wan01 to wan02) when the output got them from that job, "
    "or to explain that high-bandwidth mode suits links of about 100 Mbps or more."
)

GOOD = [
    (
        "| WAN accelerator | Cache | High-bandwidth mode |\n|---|---|---|\n| wan01.lab.local (HQ) | 100 GB (D:\\VeeamWAN) "
        "| Off |\n| wan02.lab.local (DR site) | 200 GB (E:\\VeeamWAN) | On |\n\nHealth: VBR's API exposes no online or "
        "health state for WAN accelerators, so I can't tell whether they're healthy from here."
    ),
    (
        "wan01.lab.local - 100-GB cache, HBM disabled; wan02.lab.local - 200 GB cache, high bandwidth mode enabled. There "
        "is no health status for WAN accelerators in the API. Note that HBM has to be on at both ends, and Copy-to-DR "
        "goes from wan01 to wan02, so that link isn't in high-bandwidth mode."
    ),
]

BAD = {
    "wan02_cache": "wan01.lab.local: 100 GB cache, high-bandwidth mode off. wan02.lab.local: 100 GB cache, "
    "high-bandwidth mode on. Health is not reported.",
    "high_bandwidth": "wan01.lab.local has a 100 GB cache and wan02.lab.local a 200 GB cache. Health is not reported.",
}
"""Answers that each miss one fact."""


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G1-10",
        inputs=CaseInputs(
            question="List our WAN accelerators with their cache size and whether high-bandwidth mode is on. Are they healthy?",
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G1", "base_stand": "1.6"},
        evaluators=[
            # list_wan_accelerators is the answer; list_jobs (roles from Copy-to-DR) is allowed on top.
            ToolCorrectness(expected_tools=["list_wan_accelerators"], allow_extra=True),
            *tool_budget(2),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "high_bandwidth_per_accelerator",
                f"The output says high-bandwidth mode is off on {_WAN01.name} and on on {_WAN02.name}.",
            ),
            _judge(
                "health_unknown",
                "The output says honestly that the API does not report an online or health state for WAN "
                "accelerators, and does not claim they are online, healthy or working.",
            ),
            _judge(
                "no_role_from_endpoint",
                "The output does not state as fact which accelerator is the source and which the target based on "
                "the WAN accelerator data alone, which carries no role. Roles taken from the Copy-to-DR job, saying "
                "the roles cannot be told from this data, or a guess clearly marked as such are fine.",
            ),
            _judge(
                "pair_not_high_bandwidth",
                f"The output does not claim that the link between {_WAN01.name} and {_WAN02.name}, or Copy-to-DR's "
                "traffic, runs in high-bandwidth mode: that needs the mode on both accelerators, and it is off on "
                f"{_WAN01.name}. Saying that the mode is on for {_WAN02.name} is fine.",
            ),
        ],
    )
