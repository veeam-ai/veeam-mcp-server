# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G2-14: why SQL-Dev is slow - its bottleneck, and whether the proxy setup is part of the problem."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import CaseInputs, judge, tool_budget
from cases.patterns import DISABLED, OFFLINE, about, near
from evaluators import FactsPresent, ToolsCalled, ToolsNotCalled
from stand import by_name, environment, jobs, proxies, sessions
from stand.ids import J03

# ---- What VBR serves: the base stand. SQL-Dev (1.2) runs, started by hand at 08:40, 45% through with a Source
# bottleneck; its nightly run of 02:00 took under 17 minutes. Of the proxies (1.6) only Proxy-01 (hot-add) can take
# tasks: Proxy-02 is offline and Proxy-03 (direct storage access) disabled, both with out-of-date components.

ENVIRONMENT = environment()

# ---- What a correct answer says, derived from the data above.

_STATE = by_name(jobs.JOB_STATES, "SQL-Dev")
_PROGRESS = sessions.SQL_DEV_PROGRESS
_NIGHTLY = next(s for s in sessions.SESSIONS if s.job_id == J03 and s.end_time is not None)
assert _NIGHTLY.end_time is not None
_NIGHTLY_MINUTES = round((_NIGHTLY.end_time - _NIGHTLY.creation_time).total_seconds() / 60)
_WORKING, _OFFLINE, _DISABLED = (by_name(proxies.PROXY_STATES, name) for name in ("Proxy-01", "Proxy-02", "Proxy-03"))
assert _WORKING.is_online and not _WORKING.is_disabled and not _OFFLINE.is_online and _DISABLED.is_disabled

EXPECTED = (
    f"{_STATE.name}, started by hand at 08:40, is {_PROGRESS.progress_percent}% done after about 20 minutes, at "
    f"{_PROGRESS.processing_rate} as VBR reports it; its nightly run of 02:00 took about {_NIGHTLY_MINUTES} minutes "
    f"in all, so today's run is clearly slower. VBR names {_PROGRESS.bottleneck} as the bottleneck: the slowest "
    "stage is reading the data from the source storage and getting it to the proxy - the datastore, or the "
    "transport between it and the proxy - not the proxy's own processing and not the network to the repository. "
    "The proxy setup is part of the picture: only Proxy-01 can take tasks (configured for hot-add, with failover to "
    "network allowed, so the run may be reading over the network); Proxy-02 is offline and Proxy-03 disabled, both "
    "with out-of-date components, so there is no redundancy. Proxy-03 is the one with direct storage access, which "
    "could speed up the source reads - after its components are updated and it is enabled."
)
"""Ground truth for the judges."""

_PROXIES = r"(?:Proxy-0\d)"


_about = partial(about, others=_PROXIES, within=120, before=40)


FACTS = {
    # "the bottleneck is Source", "Source (reading from the datastore) is the bottleneck", "limited by the source"
    "bottleneck": near(r"bottleneck|limit(?:ed|ing)|slowest|constrain", r"\bsource\b", 80),
    "working_proxy": r"Proxy-01",
    "offline_proxy": _about(r"Proxy-02", OFFLINE),
    "disabled_proxy": _about(r"Proxy-03", DISABLED),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    """SQL-Dev is 45% done after ~20 minutes (86 MB/s, started manually at 08:40), while its scheduled 02:00 run finished in about 17 minutes - so yes, it is slow today.

**Bottleneck: Source.** The slowest stage is getting data off the source datastore and to the proxy, not the proxy processing it or the network to the repository. So look at the datastore's load and latency first, and at how the proxy reads it.

**Proxies:** only Proxy-01 can take tasks right now (it is set to hot-add, with failover to network allowed). Proxy-02 is offline and Proxy-03 is disabled, and both have out-of-date components - so there is no redundancy. Proxy-03 has direct storage access and could take load off the source reads, but it would need a components update before enabling it.""",
    """| | |
|---|---|
| Bottleneck | Source - reading from the source storage |
| Rate | 86 MB/s (as reported by VBR) |
| Usable proxies | Proxy-01 only |

Proxy-02 is not online and Proxy-03 is turned off; both are outdated. The proxy setup is a risk (one proxy, no failover) and may play a part, since the Source stage includes moving data to the proxy, but the reported bottleneck points at the datastore side.""",
]

BAD = {
    "bottleneck": (
        "The bottleneck is the network between Proxy-01 and the repository. Proxy-02 is offline and Proxy-03 is "
        "disabled."
    ),
    "offline_proxy": (
        "Bottleneck: Source (datastore reads). Proxy-01 is the only proxy online; Proxy-03 is disabled. Proxy-02 "
        "is healthy but idle."
    ),
    "disabled_proxy": (
        "Bottleneck: Source (datastore reads). Only Proxy-01 can take tasks: Proxy-02 is disabled and Proxy-03 is "
        "offline."
    ),
}

_ALLOWED = (
    "It is acceptable, and not a violation, to give SQL-Dev's progress and rate as VBR reports them, to compare with "
    f"the nightly 02:00 run (about {_NIGHTLY_MINUTES} minutes), to look at the task of the VM sql-dev-01, to mention "
    "that the run was started manually by LAB\\admin, to give Proxy-01's 8 task slots, or to suggest checking the "
    "datastore's load and latency or updating and enabling Proxy-03 (direct storage access), as advice only."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G2-14",
        inputs=CaseInputs(
            question="SQL-Dev seems slow today. Where is the bottleneck, and is our proxy setup part of the problem?",
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G2", "base_stand": "1.2, 1.3, 1.6"},
        evaluators=[
            # the bottleneck is in the job's state and in its session's progress; the proxies only in list_proxies
            ToolsCalled("job_progress_read", frozenset({"get_job_states", "list_sessions"})),
            ToolCorrectness(expected_tools=["list_proxies"], allow_extra=True),
            *tool_budget(4),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "bottleneck_not_blamed_elsewhere",
                f"The output does not blame the network to the repository, the target storage or the proxy's CPU "
                f"for the slowness, contrary to the {_PROGRESS.bottleneck} bottleneck VBR reports.",
            ),
            _judge(
                "source_stage_explained",
                "The output treats the Source bottleneck as the stage of reading the data from the source storage "
                "(the datastore) and getting it to the proxy. It does not state as a fact that the proxy setup "
                "plays no part at all: the transport mode the proxy reads with belongs to that stage. Saying that "
                "the proxies are probably not the main cause is fine.",
            ),
            _judge(
                "no_redundancy",
                "The output makes clear that only one proxy, Proxy-01, can take tasks, so the setup has no redundancy.",
            ),
            _judge(
                "proxy_03_caveat",
                "If the output suggests using Proxy-03 (direct storage access), it also says that Proxy-03 has "
                "out-of-date components, so it has to be updated, not only enabled, before it can take tasks. An "
                "output that does not suggest Proxy-03 meets this criterion.",
            ),
            _judge(
                "transport_mode_not_asserted",
                "The output does not claim as a fact that SQL-Dev is reading its disks with hot-add: that is "
                "Proxy-01's configured transport mode, and with failover to network allowed the run may be using "
                "network mode. Mentioning the configured mode is fine.",
            ),
            _judge(
                "rate_as_reported",
                f"If the output gives a processing rate for {_STATE.name}, it is {_PROGRESS.processing_rate} as VBR "
                "reports it, not a rate the output computed from the sizes and the duration.",
            ),
            _judge(
                "no_proxy_changes",
                "The output does not claim to have enabled, disabled, updated or otherwise changed any proxy; "
                "suggesting such a change as advice is fine.",
            ),
        ],
    )
