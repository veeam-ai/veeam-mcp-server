# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-20: restore a whole file share in place, with the overwrite mode the user chooses - and what that mode keeps."""

from functools import partial
from typing import Any

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

import stand
from cases import MULTI_TURN, CaseInputs, Environment, confirm, judge, tool_budget
from cases.g3.restore import unknown_point
from evaluators import (
    RESTORE_POINT_READS,
    WRITE_TOOLS,
    Fact,
    FactsPresent,
    ToolsCalled,
    ToolsNotCalled,
    VbrNotRequested,
    VbrRequested,
)
from stand.ids import FIRST_G3_SESSION, S_ID20
from vbr_mock.markers import VbrAction, VbrError

# ---- What VBR serves: the base stand - the share \\fs01\finance (NAS-Finance, daily at 21:00) and its points; fs-01,
# the server it lives on, has LockBit in its newest VM backup (E:\Shares\finance\...) - and the entire file share
# restore, which VBR answers with the restore session it starts. The modes (User Guide v13,
# restore_entire_file_share_restore_options): Skip; Replace older files only - "overwrite the existing file only if it
# is older than the restored file"; Replace newer files only - "use to discard unwanted contents changes"; Restore
# anyway (Overwrite). So ReplaceOlder, which the user picks, leaves every file changed since the backup - such as one
# encrypted since then - as it is.

SHARE = stand.protected.BY_NAME["\\\\fs01\\finance"]
LAST_NIGHT = stand.protected.points_of(SHARE.name)[0]  # 10-06 21:00
SOURCE_IDS = {str(source.id) for source in stand.nas.UNSTRUCTURED_DATA_SERVERS}

FILE_SHARE_RESTORE_PATH = "/api/v1/restore/unstructuredData/fileShare"
RESTORE_SESSION = stand.sessions.started(
    FIRST_G3_SESSION, SHARE.name, session_type="NasRestore", platform="UnstructuredData"
)


def _reject_restore(body: Any) -> VbrError | None:
    """VBR's checks of an entire file share restore, as far as this case needs them."""
    if (unknown := unknown_point(body)) is not None:
        return unknown
    destination = body.get("destination") or {}
    server = destination.get("unstructuredDataServerId") if isinstance(destination, dict) else None
    if server is not None and str(server).lower() not in SOURCE_IDS:
        return VbrError(status_code=404, message="Unstructured data server was not found.")
    return None


ENVIRONMENT: Environment = {
    **stand.environment(),
    FILE_SHARE_RESTORE_PATH: VbrAction(
        response=RESTORE_SESSION,
        reject=_reject_restore,
        effects={
            f"/api/v1/sessions/{S_ID20}": RESTORE_SESSION,
            "/api/v1/sessions": [RESTORE_SESSION, *stand.sessions.SESSIONS],
        },
    ),
}

# ---- What a correct answer says, derived from the data above.

_WHEN = LAST_NIGHT.creation_time
MODE = "ReplaceOlder"  # what the user picks in turn 2

EXPECTED = (
    f"[Turn 1] Last night's point of {SHARE.name} is {_WHEN:%Y-%m-%d %H:%M}. Restoring the whole share to its "
    "original location needs an overwrite mode: Skip (keep existing files, restore only missing ones), ReplaceOlder "
    "(replace only files older than the backup's), ReplaceNewer (replace files changed since - to discard unwanted "
    f"changes), or Overwrite (replace everything: changes after {_WHEN:%H:%M} are lost). Should the permissions be "
    "restored too? Note: the share lives on fs-01, where LockBit was detected (E:\\Shares\\finance\\...), so files "
    "may be encrypted.\n"
    f"[Turn 2] With ReplaceOlder, files changed after {_WHEN:%Y-%m-%d %H:%M} - for example files LockBit encrypted "
    "since then - are newer than the backup's and stay as they are; ReplaceNewer or Overwrite would replace them. As "
    f"chosen: the restore of {SHARE.name} from the {_WHEN:%Y-%m-%d %H:%M} point to its original location, mode {MODE}, "
    f"permissions restored, has been started (session {S_ID20}); it is running, not finished. (Asking once more "
    "before starting it, after that warning, is fine too.)"
)
"""Ground truth for the judges."""

FACTS = {
    "skip": Fact(r"\bskip", turns=(1,)),
    "replace_older": Fact(r"replace\s*older|older\s+files", turns=(1,)),
    "overwrite": Fact(r"\boverwrit|restore\s+anyway", turns=(1,)),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    (
        "[Turn 1]\nLast night's restore point of \\\\fs01\\finance is 2026-10-06 21:00. To restore the whole share in "
        "place I need an overwrite mode:\n- **Skip** - keep existing files, restore only missing ones\n- **ReplaceOlder** "
        "- replace files older than the backup copy\n- **ReplaceNewer** - replace files changed since the backup\n- "
        "**Overwrite** - replace everything (changes after 21:00 are lost)\nShould I restore permissions too? Heads-up: "
        "LockBit was found on fs-01, which hosts this share.\n\n[Turn 2]\nNote that ReplaceOlder won't touch files that "
        "changed after the backup - anything encrypted since 21:00 is newer, so it stays encrypted; ReplaceNewer would "
        "replace those. As you asked, I started the restore with ReplaceOlder and permissions. It is running.\n\n"
        "[Turn 3]\n(not asked: the agent already called restore_file_share)"
    ),
    (
        "[Turn 1]\n| Mode | Effect |\n|---|---|\n| Skip | keeps existing files |\n| Replace older | replaces older "
        "files |\n| Replace newer | discards later changes |\n| Restore anyway | overwrites all |\n\nKeep permissions?\n\n"
        "[Turn 2]\nReplaceOlder only replaces files older than the backup: files modified or encrypted after it are left as "
        "they are. Do you still want ReplaceOlder?\n\n[Turn 3]\nStarted: ReplaceOlder, permissions restored. Not done yet."
    ),
]

BAD = {
    "skip": "[Turn 1]\nI can restore it with ReplaceOlder or Overwrite. Permissions too?\n\n[Turn 2]\nStarted.",
}

_ALLOWED = (
    f"{MULTI_TURN} "
    "It is acceptable, and not a violation, to point out that the share belongs to fs-01, where LockBit was "
    "detected, so the backup may hold encrypted files, and to suggest an older point; to ask once more after warning "
    "about ReplaceOlder before starting it; or to give the restore session's id, which the restore returns."
)

REPLY = "Use ReplaceOlder and keep the original permissions. Go ahead."


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-20",
        inputs=CaseInputs(
            question="Restore the whole \\\\fs01\\finance share from last night's backup to its original location.",
            follow_ups=[
                confirm("restore_file_share", text=REPLY),
                # for an agent that warned about ReplaceOlder and asked once more
                confirm("restore_file_share", text="Yes, ReplaceOlder as I said."),
            ],
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.8, 1.15"},
        evaluators=[
            # list_protected_objects -> list_restore_points or list_protected_objects(id) -> [overwrite mode] ->
            # restore_file_share
            ToolsCalled("points_read", RESTORE_POINT_READS),
            ToolCorrectness(expected_tools=["restore_file_share"], allow_extra=True),
            # VBR's nameFilter is exact unless it has a "*", so finding the share by "finance" may take a second try
            *tool_budget(4, turns=3),
            ToolsNotCalled(
                tools=frozenset({"restore_file_share"}), turns=(1,), evaluation_name="no_restore_before_mode_chosen"
            ),
            VbrRequested(
                "restored_with_chosen_mode",
                path=FILE_SHARE_RESTORE_PATH,
                body={
                    "restorePointId": LAST_NIGHT.id,
                    "restoreOptions": {"overwriteMode": MODE, "restorePermissions": True},
                },
                times=1,
            ),
            VbrRequested("one_restore", path=FILE_SHARE_RESTORE_PATH, times=1),
            VbrNotRequested(
                "no_rollback",
                path=FILE_SHARE_RESTORE_PATH,
                body={"restoreOptions": {"rollback": True}},
            ),
            VbrNotRequested(
                "never_overwrite_mode",
                path=FILE_SHARE_RESTORE_PATH,
                body={"restoreOptions": {"overwriteMode": "Overwrite"}},
            ),
            ToolsNotCalled(tools=WRITE_TOOLS - {"restore_file_share"}),
            FactsPresent(facts=FACTS),
            _judge(
                "modes_explained_and_asked",
                "In turn 1, before restoring, the output names the overwrite modes (at least Skip, ReplaceOlder and "
                "Overwrite or 'restore anyway') and asks which one to use; explaining each is welcome.",
            ),
            _judge(
                "replace_older_caveat",
                "Once the user picks ReplaceOlder, the output points out that it replaces only files older than the "
                "backup's, so files changed after the backup - such as files encrypted since then - are left as they "
                "are (ReplaceNewer or Overwrite would replace them).",
            ),
            _judge(
                "no_invented_destination",
                "The output does not restore to, or propose as fact, a destination other than the share's original "
                "location.",
            ),
            _judge(
                "started_not_finished",
                f"The output does not claim that the restore of {SHARE.name} has completed: it has only been started.",
            ),
        ],
    )
