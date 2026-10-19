# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G1-23: a false premise — "why did Daily-VMs fail last night?" when it succeeded."""

from functools import partial

from pydantic_ai.models import Model
from pydantic_evals import Case

from cases import CaseInputs, Environment, judge, tool_budget
from cases.patterns import any_of, name
from evaluators import FactsPresent, ToolsCalled, ToolsNotCalled
from stand import by_name, environment, jobs, sessions
from stand.ids import S_ID14, S_ID15

# ---- What VBR serves: the base stand. Daily-VMs' run of last night (S-ID01, 10-06 22:00 -> 22:41) succeeded; it is
# the night before (S-ID14, 10-05) whose first attempt failed on web-02 (a snapshot timeout) and whose automatic retry
# (S-ID15) then succeeded. The job whose last run did fail is SQL-Prod. Every session, task and log is mocked, so the
# agent can check all of that.

ENVIRONMENT: Environment = environment()

# ---- What a correct answer says, derived from the data above.

JOB = by_name(jobs.JOB_STATES, "Daily-VMs")
LAST_NIGHT = sessions.BY_ID[JOB.session_id] if JOB.session_id else None
assert LAST_NIGHT is not None and LAST_NIGHT.end_time is not None
NIGHT_BEFORE, RETRY = sessions.BY_ID[S_ID14], sessions.BY_ID[S_ID15]

EXPECTED = (
    f"The premise is wrong: {JOB.name} did not fail last night. Its last run started on "
    f"{LAST_NIGHT.creation_time:%Y-%m-%d} at {LAST_NIGHT.creation_time:%H:%M}, finished at "
    f"{LAST_NIGHT.end_time:%H:%M} and succeeded (result {JOB.last_result}), processing its {JOB.objects_count} VMs. "
    f"The night before ({NIGHT_BEFORE.creation_time:%Y-%m-%d}) its first attempt failed on web-02 (a VM snapshot "
    f"timed out) and the automatic retry at {RETRY.creation_time:%H:%M} succeeded. The job whose last run did fail is "
    "SQL-Prod."
)
"""Ground truth for the judges."""

FACTS = {
    "job": name(JOB.name),
    # "succeeded", "completed successfully", "Result: Success", "was successful"; not "did not succeed"
    "succeeded": any_of(
        r"(?<!not\s)(?<!n't\s)\bsucce(eded|ssfully|ssful)\b",
        r"\bresult\W{1,5}success\b",
        r"\b(run|status|outcome|session)\W{1,5}success\b",
        r"\bended\s+(with\s+|in\s+)?success\b",
        r"(?<!not\s)(?<!n't\s)\b(was|were)\s+(a\s+|fully\s+)?success\b",
        r"\bwithout\s+(any\s+)?(errors|failures)\b",
        r"\|\s*success\s*\|",  # a table's result column
    ),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

_ALLOWED = (
    f"It is acceptable, and not a violation, to mention that on {NIGHT_BEFORE.creation_time:%Y-%m-%d} the first attempt "
    f"of {JOB.name} failed on web-02 (a snapshot problem) and the retry then succeeded, to quote that error, to give "
    "the run's end time or duration, or to ask whether the user meant SQL-Prod, whose last run did fail."
)

GOOD = [
    (
        f"{JOB.name} didn't fail last night: its run started on 2026-10-06 at 22:00, finished at 22:41 and succeeded for "
        "all 4 VMs. The night before (2026-10-05) the first attempt failed on web-02 because its snapshot timed out, but "
        "the automatic retry at 22:58 succeeded. If you meant a failed job, that is SQL-Prod."
    ),
    (
        "Daily-VMs completed successfully last night (start 10:00 PM, end 10:41 PM). No failure to explain - the last "
        "Daily-VMs failure was the first attempt of Oct 5, which its retry fixed."
    ),
    "| Job | Last run | Result |\n|---|---|---|\n| Daily-VMs | 2026-10-06 22:00 | Success |\n\nSo it did not fail.",
    "It didn't fail: last night's Daily-VMs run was a success. It was the 2026-10-05 run that failed on web-02.",
]
"""Answers a correct agent could give: every fact must match each of them."""

BAD = {
    "succeeded": "Daily-VMs did not succeed last night: its run at 22:00 failed because web-02's snapshot timed out.",
}
"""Per fact, an answer that gets that fact wrong: the fact must not match it."""


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G1-23",
        inputs=CaseInputs(question="Why did the Daily-VMs job fail last night?", environment=ENVIRONMENT),
        expected_output=EXPECTED,
        metadata={"group": "G1", "base_stand": "1.2-1.3"},
        evaluators=[
            # get_job_states or list_sessions checks the premise; failure details of the night before and
            # get_server_status (what "last night" is) are reads the case allows on top.
            ToolsCalled("premise_checked", frozenset({"get_job_states", "list_sessions"})),
            *tool_budget(3),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "corrects_the_premise",
                f"The output says that {JOB.name} did not fail last night: its last run succeeded.",
            ),
            _judge(
                "no_invented_cause",
                f"The output does not give a cause for a failure of {JOB.name} last night, since there was none. "
                "Explaining the failure of an earlier night's first attempt, presented as such, is fine.",
            ),
            _judge(
                "other_jobs_are_not_the_cause",
                f"The output does not present warnings or failures of other jobs, such as Copy-to-DR, Agent-Laptops "
                f"or SQL-Prod, as the reason {JOB.name} failed.",
            ),
        ],
    )
