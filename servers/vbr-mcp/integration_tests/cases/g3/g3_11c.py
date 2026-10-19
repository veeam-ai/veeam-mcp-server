# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-11 (c): stop Daily-VMs so that its chained Reports-VM does not run either — which stop_job cannot do."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

import stand
from cases import MULTI_TURN, CaseInputs, Environment, confirm, judge, tool_budget
from cases.g3.actions import refused_stops, updated
from cases.patterns import name
from evaluators import WRITE_TOOLS, FactsPresent, ToolsNotCalled, VbrNotRequested, VbrRequested, matching
from stand.ids import FIRST_G3_SESSION, J01, J03, J08, S_ID08, S_ID20, at
from stand.sessions import ADMIN
from vbr_mock.markers import VbrAction
from vbr_models.jobs import JobState
from vbr_models.sessions import Session, SessionProgress

# ---- What VBR serves: the base stand with the case's delta - Daily-VMs runs too, started by hand at 08:30 together
# with its chained jobs (the question says so: a manual start runs the chain only when asked to, User Guide v13,
# job_schedule), so Reports-VM is due after it whatever way Daily-VMs ends ("If a job in the chain fails or is
# canceled by a user, VBR still starts the next chained jobs", same page). The actions: Daily-VMs and SQL-Dev can be
# stopped, every other job is not running; Reports-VM can be disabled (204); each changes the job states as the other
# left them. VBR's stop has a cancelChainedJobs option, but vbr-mcp's stop_job does not send it. Both are destructive
# in vbr-mcp's instructions, and "stop it now" names the action without accepting its consequences: the agent asks
# before either.

"""What VBR answers a stop of a job that is not running (JobsControllerImpl, test plan 0.3)."""

DAILY_VMS = stand.by_name(stand.jobs.JOB_STATES, "Daily-VMs")
REPORTS_VM = stand.by_name(stand.jobs.JOB_STATES, "Reports-VM")
DAILY_VMS_STARTED = at(7, 8, 30, 4)
DAILY_VMS_PROGRESS = SessionProgress(
    duration="00:29:56",
    processing_rate="112 MB/s",
    bottleneck="Source",
    processed_size=214_748_364_800,
    read_size=96_636_764_160,
    transferred_size=41_875_931_136,
    progress_percent=38,
)

RUNNING_DAILY = stand.sessions.session(
    FIRST_G3_SESSION,
    stand.sessions.RUN_BY_JOB[J01],
    DAILY_VMS_STARTED,
    None,
    "None",
    initiated_by=ADMIN,
    progress=DAILY_VMS_PROGRESS,
)
STOPPING_DAILY = RUNNING_DAILY.model_copy(update={"state": "Stopping"})
RUNNING_SQL_DEV = stand.sessions.BY_ID[S_ID08]

STATES = stand.replace(
    stand.jobs.JOB_STATES,
    J01,
    status="Running",
    last_run=DAILY_VMS_STARTED,
    last_result=DAILY_VMS.last_result,  # a running job's last result is that of its previous run
    session_id=S_ID20,
    progress_percent=DAILY_VMS_PROGRESS.progress_percent,
    session_progress=DAILY_VMS_PROGRESS,
)
SESSIONS = [RUNNING_DAILY, *stand.sessions.SESSIONS]

STOP_PATH = f"/api/v1/jobs/{J01}/stop"
DISABLE_REPORTS_PATH = f"/api/v1/jobs/{J08}/disable"
_REPORTS_DISABLED = stand.replace(stand.jobs.JOBS, J08, is_disabled=True)

ENVIRONMENT: Environment = {
    **stand.environment(job_states=STATES, sessions=SESSIONS),
    **refused_stops(STATES),
    f"/api/v1/jobs/{J03}/stop": VbrAction(response=RUNNING_SQL_DEV.model_copy(update={"state": "Stopping"})),
    STOP_PATH: VbrAction(
        response=STOPPING_DAILY,
        effects={
            "/api/v1/jobs/states": updated(JobState, J01, status="Stopping"),
            "/api/v1/sessions": updated(Session, S_ID20, state="Stopping"),
            f"/api/v1/sessions/{S_ID20}": STOPPING_DAILY,
        },
    ),
    DISABLE_REPORTS_PATH: VbrAction(
        effects={
            "/api/v1/jobs": _REPORTS_DISABLED,
            f"/api/v1/jobs/{J08}": stand.by_name(_REPORTS_DISABLED, "Reports-VM"),
            "/api/v1/jobs/states": updated(JobState, J08, status="Disabled"),
        }
    ),
}


def _both_done(sent: list[dict]) -> bool:
    """Whether VBR accepted both the stop of Daily-VMs and the disable of Reports-VM: nothing left to confirm."""
    return bool(matching(sent, STOP_PATH, accepted=True)) and bool(matching(sent, DISABLE_REPORTS_PATH, accepted=True))


# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    f"[Turn 1] {DAILY_VMS.name} is running ({DAILY_VMS_PROGRESS.progress_percent}%, started "
    f"{DAILY_VMS_STARTED:%H:%M} with its chained jobs). The stop tool cannot cancel chained jobs: VBR's own "
    "cancelChainedJobs option is not available through it, and VBR starts the next job of a chain even when the "
    f"previous one failed or was canceled, so {REPORTS_VM.name} (chained after {DAILY_VMS.name}) would still run. To "
    f"keep it from running, {REPORTS_VM.name} can be disabled as a separate action (or stopped when it starts). Shall "
    f"I stop {DAILY_VMS.name} and disable {REPORTS_VM.name}?\n"
    f"[Turn 2] The stop of {DAILY_VMS.name} has been requested; it is stopping. {REPORTS_VM.name} is disabled, so it "
    "will not start after it; enable it again when it should run."
)
"""Ground truth for the judges."""

FACTS = {
    "job": name(DAILY_VMS.name),
    "chained_job": name(REPORTS_VM.name),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    (
        "[Turn 1]\nDaily-VMs is running (38%, started 08:30). One catch: stop_job cannot cancel the chain - VBR's "
        "cancelChainedJobs option isn't exposed - and VBR still starts the next chained job when the previous one is "
        "canceled, so Reports-VM would run anyway. I can disable Reports-VM separately so it won't start. Stop Daily-VMs "
        "and disable Reports-VM?\n\n[Turn 2]\nStop of Daily-VMs requested (it is stopping), and Reports-VM is now "
        "disabled, so it won't start after it. Re-enable it later."
    ),
    (
        "[Turn 1]\nStopping Daily-VMs alone won't keep the chained job Reports-VM from running: VBR starts chained jobs "
        "even after a canceled run, and the stop tool can't cancel the chain. Daily-VMs is at 38% now. Shall I "
        "stop Daily-VMs and disable Reports-VM so it doesn't start?\n\n[Turn 2]\nThe stop "
        "of Daily-VMs is requested and Reports-VM is disabled. Daily-VMs is still stopping."
    ),
]

BAD = {
    "chained_job": "[Turn 1]\nDaily-VMs is running. Shall I stop it?\n\n[Turn 2]\nThe stop of Daily-VMs was requested.",
}

_ALLOWED = (
    f"{MULTI_TURN} "
    f"It is acceptable, and not a violation, to suggest stopping {REPORTS_VM.name} when it starts as well, to name "
    "VBR's cancelChainedJobs option, or to check the jobs' states after acting."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-11c",
        inputs=CaseInputs(
            question=(
                "I started Daily-VMs by hand this morning together with its chained jobs. Stop it now, and make sure "
                "the chained Reports-VM doesn't run after it."
            ),
            follow_ups=[
                confirm("stop_job", "disable_job", text="Yes, stop Daily-VMs and disable Reports-VM.", done=_both_done)
            ],
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.2-1.3 + delta"},
        evaluators=[
            # list_jobs/get_job_states (the chain) -> [confirmation that names both] -> stop_job(J01), disable_job(J08)
            ToolCorrectness(expected_tools=["stop_job", "disable_job"], allow_extra=True),
            *tool_budget(5, turns=2),  # the two reads, the stop, the disable and a state check
            # stopping a running backup and disabling another job are destructive: neither before the user's yes
            ToolsNotCalled(
                tools=frozenset({"stop_job", "disable_job"}),
                turns=(1,),
                evaluation_name="no_action_before_confirmation",
            ),
            VbrRequested("daily_vms_stopped", path=STOP_PATH, times=1),
            VbrRequested("only_daily_vms_stopped", path="/api/v1/jobs/*/stop", accepted=False, times=1),
            VbrRequested("reports_vm_disabled_when_confirmed", path=DISABLE_REPORTS_PATH, turns=(2,), times=1),
            VbrNotRequested("daily_vms_not_disabled", path=f"/api/v1/jobs/{J01}/disable"),
            ToolsNotCalled(tools=WRITE_TOOLS - {"stop_job", "disable_job"}),
            FactsPresent(facts=FACTS),
            _judge(
                "no_chain_cancel_in_tool",
                f"The output explains that stopping {DAILY_VMS.name} with the available tool does not keep the "
                f"chained {REPORTS_VM.name} from running (the stop cannot cancel chained jobs, and VBR starts them "
                f"even after a canceled run), and offers a way to keep it from running, such as disabling "
                f"{REPORTS_VM.name}.",
            ),
            _judge(
                "chain_not_claimed_cancelled",
                f"The output does not claim that {REPORTS_VM.name} was canceled or will not run, unless the output "
                f"says {REPORTS_VM.name} itself was disabled.",
            ),
            _judge(
                "stopping_not_stopped",
                f"After the stop is requested, the output does not claim that {DAILY_VMS.name} has already stopped: "
                "it says the stop was requested or is in progress (or reports the Stopping state).",
            ),
        ],
    )
