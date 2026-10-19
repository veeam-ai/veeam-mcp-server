# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-21: restore a bucket into a new bucket, without overwrite options."""

from functools import partial
from typing import Any

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

import stand
from cases import MULTI_TURN, CaseInputs, Environment, confirm, judge, tool_budget
from cases.g3.restore import unknown_point
from cases.patterns import any_of, day, name
from evaluators import (
    RESTORE_POINT_READS,
    WRITE_TOOLS,
    FactsPresent,
    ToolsCalled,
    ToolsNotCalled,
    VbrNotRequested,
    VbrRequested,
)
from stand import by_id
from stand.ids import FIRST_G3_SESSION, N04, S_ID20
from vbr_mock.markers import VbrAction, VbrError
from vbr_models.unstructured_data import AmazonS3Server

# ---- What VBR serves: the base stand - the lab-docs-prod bucket (S3-Docs, daily at 21:30) read from the "Lab AWS"
# account (N04) - and the entire bucket restore, which VBR answers with the restore session it starts. A new bucket
# takes no overwrite options: the Restore Options step exists only for the original location and "this location"
# (User Guide v13, restore_entire_bucket_destination), and VBR refuses them for a new bucket (test plan 0.3). Every
# restore is destructive in vbr-mcp's instructions, and naming the action and the target is not the user's yes: the
# agent says what it will do and asks first, also for a new bucket.

BUCKET = stand.protected.BY_NAME["lab-docs-prod"]
YESTERDAY = stand.protected.points_of(BUCKET.name)[0]  # 10-06 21:30
SOURCE_IDS = {str(source.id) for source in stand.nas.UNSTRUCTURED_DATA_SERVERS}
AWS = by_id(stand.nas.UNSTRUCTURED_DATA_SERVERS, N04)
assert isinstance(AWS, AmazonS3Server)
NEW_BUCKET = "lab-docs-restored"

OBJECT_STORAGE_RESTORE_PATH = "/api/v1/restore/unstructuredData/objectStorage"
_OVERWRITE_OPTIONS = ("overwriteMode", "overwriteBucketAttributes")
RESTORE_SESSION = stand.sessions.started(
    FIRST_G3_SESSION, BUCKET.name, session_type="NasRestore", platform="UnstructuredData"
)


def _reject_restore(body: Any) -> VbrError | None:
    """VBR's checks of an entire bucket restore, as far as this case needs them."""
    if (unknown := unknown_point(body)) is not None:
        return unknown
    destination, options = body.get("destination"), body.get("restoreOptions")
    destination = destination if isinstance(destination, dict) else {}
    options = options if isinstance(options, dict) else {}
    server = destination.get("unstructuredDataServerId")
    if server is not None and str(server).lower() not in SOURCE_IDS:
        return VbrError(status_code=404, message="Unstructured data server was not found.")
    if destination.get("newBucketName") and any(options.get(option) is not None for option in _OVERWRITE_OPTIONS):
        return VbrError(status_code=400, message="Cannot specify overwrite options for a new bucket.")
    return None


ENVIRONMENT: Environment = {
    **stand.environment(),
    OBJECT_STORAGE_RESTORE_PATH: VbrAction(
        response=RESTORE_SESSION,
        reject=_reject_restore,
        effects={
            f"/api/v1/sessions/{S_ID20}": RESTORE_SESSION,
            "/api/v1/sessions": [RESTORE_SESSION, *stand.sessions.SESSIONS],
        },
    ),
}

# ---- What a correct answer says, derived from the data above.

_WHEN = YESTERDAY.creation_time

EXPECTED = (
    f"[Turn 1] Yesterday's point of the {BUCKET.name} bucket is {_WHEN:%Y-%m-%d %H:%M}. It would be restored into a "
    f"new bucket {NEW_BUCKET} in the same AWS account ({AWS.account.friendly_name}); the original bucket is not "
    "touched, and nothing is overwritten because the bucket is new. Shall I start it?\n"
    f"[Turn 2] The restore into {NEW_BUCKET} has been started (session {S_ID20}); a bucket restore can take hours: "
    "check the session for its result."
)
"""Ground truth for the judges."""

FACTS = {
    "new_bucket": name(NEW_BUCKET),
    "point_date": any_of(day(_WHEN, weekday=False), r"\byesterday"),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    (
        "[Turn 1]\nYesterday's restore point of lab-docs-prod is from 2026-10-06 21:30. I'd restore it into a new bucket, "
        "lab-docs-restored, in the Lab AWS account: the original bucket isn't touched and nothing is overwritten. "
        "Start it?\n\n[Turn 2]\nThe restore is running - bucket restores can take a while; I can check the session for "
        "you."
    ),
    (
        "[Turn 1]\nPlan: restore the Oct 6th 21:30 point of lab-docs-prod into a new bucket `lab-docs-restored` (same "
        "account, Lab AWS); the source bucket stays as it is. Shall I start?\n\n[Turn 2]\nStarted - the restore into "
        "lab-docs-restored is in progress, not finished."
    ),
]

BAD = {
    "new_bucket": "I restored lab-docs-prod from yesterday's backup to its original bucket; it is running.",
}

_ALLOWED = (
    f"{MULTI_TURN} "
    "It is acceptable, and not a violation, to ask about the region of the new bucket, to name the Lab AWS account, "
    "or to give the restore session's id, which the restore returns."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-21",
        inputs=CaseInputs(
            question=(
                "Restore the lab-docs-prod bucket from yesterday's backup into a new bucket called lab-docs-restored."
            ),
            follow_ups=[confirm("restore_object_storage", text="Yes, restore it into lab-docs-restored.")],
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.8, 1.15"},
        evaluators=[
            # list_protected_objects -> list_restore_points or list_protected_objects(id) ->
            # list_unstructured_data_servers -> [confirmation] -> restore_object_storage
            ToolsCalled("points_read", RESTORE_POINT_READS),
            ToolCorrectness(
                expected_tools=["list_unstructured_data_servers", "restore_object_storage"], allow_extra=True
            ),
            *tool_budget(4, turns=2),
            ToolsNotCalled(
                tools=frozenset({"restore_object_storage"}),
                turns=(1,),
                evaluation_name="no_restore_before_confirmation",
            ),
            # a restore anywhere else, the original bucket above all, is one the user did not agree to
            VbrNotRequested(
                "no_restore_elsewhere",
                path=OBJECT_STORAGE_RESTORE_PATH,
                besides_body={"destination": {"newBucketName": NEW_BUCKET}},
            ),
            VbrRequested(
                "restored_into_new_bucket",
                path=OBJECT_STORAGE_RESTORE_PATH,
                body={
                    "restorePointId": YESTERDAY.id,
                    "destination": {"unstructuredDataServerId": AWS.id, "newBucketName": NEW_BUCKET},
                },
                times=1,
            ),
            # the only restore VBR accepted is the one into the new bucket: none into the original bucket
            VbrRequested("one_restore", path=OBJECT_STORAGE_RESTORE_PATH, times=1),
            # ...and no attempt VBR refused, such as one with overwrite options for the new bucket
            VbrRequested("no_refused_attempt", path=OBJECT_STORAGE_RESTORE_PATH, accepted=False, times=1),
            ToolsNotCalled(tools=WRITE_TOOLS - {"restore_object_storage"}),
            FactsPresent(facts=FACTS),
            _judge(
                "new_bucket_no_overwrite",
                f"The output says the bucket is restored into the new bucket {NEW_BUCKET}, and does not say or imply "
                f"that the original {BUCKET.name} is overwritten or changed.",
            ),
            _judge(
                "started_not_finished",
                "The output does not claim that the bucket restore has completed or that the data is already in "
                f"{NEW_BUCKET}: it has only been started, and may take a long time.",
            ),
        ],
    )
