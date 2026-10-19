# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G3-08: an antivirus scan of web-02's latest backup - the backup and object ids put together from two sources."""

import json
from dataclasses import dataclass
from functools import partial
from typing import Any

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext, ToolCorrectness

from cases import CaseInputs, Environment, judge, tool_budget
from cases.g3.actions import SCAN_PATH, SCAN_SESSION, reject_scan
from cases.patterns import STARTED, name
from evaluators import WRITE_TOOLS, FactsPresent, ToolsNotCalled, VbrRequested, requests
from stand import environment
from stand.ids import B01
from stand.protected import BY_NAME, points_of
from stand.sessions import SESSIONS
from vbr_mock.markers import VbrAction

# ---- What VBR serves: the base stand, and the scan. POST /malwareDetection/scanBackup answers 201 with the session it
# starts, a SureBackup session named "Scan Backup" (swagger SureBackupSessionExample); MostRecent scans from the newest
# point back to the first clean one (swagger EMalwareBackupScanMode). VBR refuses what it could not run - a pair that
# is not in the backup, a Specific scan without its point, YARA without a rule - in its own words (cases/g3/actions.py).

WEB_02 = BY_NAME["web-02"]
LATEST_WEB_02 = points_of("web-02")[0]

SCANNING = SCAN_SESSION.model_copy(update={"state": "Working", "progress_percent": 5})


ENVIRONMENT: Environment = environment() | {
    SCAN_PATH: VbrAction(
        response=SCAN_SESSION,
        reject=reject_scan,
        effects={"/api/v1/sessions": [SCANNING, *SESSIONS], f"/api/v1/sessions/{SCAN_SESSION.id}": SCANNING},
    ),
}


@dataclass
class ScansLatestPoint(Evaluator[Any, str, Any]):
    """The scan VBR accepted starts from web-02's newest point: ``MostRecent``, or ``Specific`` with that point."""

    def evaluate(self, ctx: EvaluatorContext[Any, str, Any]) -> dict[str, EvaluationReason]:
        bodies = [r["body"] for r in requests(ctx, SCAN_PATH, accepted=True) if isinstance(r["body"], dict)]
        value = any(
            body.get("scanMode") == "MostRecent"
            or (
                body.get("scanMode") == "Specific"
                and str(body.get("restorePointId")).lower() == str(LATEST_WEB_02.id).lower()
            )
            for body in bodies
        )
        return {"scan_mode": EvaluationReason(value=value, reason=json.dumps(bodies))}


# ---- What a correct answer says, derived from the data above.

EXPECTED = (
    f"{WEB_02.name} is protected by the Daily-VMs backup (backup {B01}, object {WEB_02.id}); its latest restore point "
    f"is {LATEST_WEB_02.creation_time:%Y-%m-%d %H:%M}. An antivirus scan of it has been started (MostRecent mode, from "
    "the newest point back to the first clean one, or Specific with that point; antivirus engine only, no YARA). It "
    "is a scan that has started, not a result: it loads the mount server and the repository while it runs; check the "
    "session or the malware events later for the outcome. (web-02's 10-04 point is Informative: a bulk file deletion "
    "flagged it and the signature scan that followed found nothing.)"
)
"""Ground truth for the judges."""

FACTS = {
    "vm": name(WEB_02.name),
    "started": STARTED,
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    (
        f"I started an antivirus scan of {WEB_02.name}'s latest backup (Daily-VMs, restore point of 2026-10-06 22:12) in "
        "MostRecent mode with the antivirus engine only. It's running now - no result yet; it'll show up in the session "
        "and in the malware events when it's done."
    ),
    (
        f"Scan Backup for **{WEB_02.name}** has been initiated (Specific mode, the 6 Oct 22:12 restore point, antivirus "
        "engine). The scan is in progress; I'll check the outcome later if you want. It loads the mount server while it "
        "runs."
    ),
    (
        f"| VM | Backup | Point | Engine | Status |\n|---|---|---|---|---|\n| {WEB_02.name} | Daily-VMs | 2026-10-06 22:12 "
        "| antivirus | scan started |\n\nNo result yet."
    ),
]
"""Answers a correct agent could give: every fact must match each."""

BAD = {
    "started": f"{WEB_02.name}'s latest backup is from 2026-10-06 22:12. I can scan it with the antivirus - confirm?",
    "vm": "The antivirus scan of the latest restore point has started; no result yet.",
}
"""Fact -> an answer that misses it."""

_ALLOWED = (
    "It is acceptable, and not a violation, to mention that web-02's Informative event means a signature scan found "
    "nothing (after a bulk file deletion was flagged), to mention the load the scan puts on the mount server and "
    "repository, or to offer to check the result later."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G3-08",
        inputs=CaseInputs(
            question="Scan the latest backup of web-02 for malware with the antivirus.", environment=ENVIRONMENT
        ),
        expected_output=EXPECTED,
        metadata={"group": "G3", "base_stand": "1.8, 1.9, 1.10"},
        evaluators=[
            # list_protected_objects (or list_backups) -> (opt.) list_restore_points -> start_malware_scan
            ToolCorrectness(expected_tools=["start_malware_scan"], allow_extra=True),
            *tool_budget(4),
            VbrRequested(
                "scan_web_02_with_antivirus",
                path=SCAN_PATH,
                body={
                    "type": "Backup",
                    "backupObjectPair": [{"backupId": B01, "backupObjectId": WEB_02.id}],
                    "scanEngine": {"useAntivirusEngine": True, "useYaraRule": False},
                },
                times=1,
            ),
            ScansLatestPoint(),
            ToolsNotCalled(tools=WRITE_TOOLS - {"start_malware_scan"}),
            FactsPresent(facts=FACTS),
            _judge(
                "started_not_result",
                f"The output says a malware scan of {WEB_02.name}'s backup has been started, and does not report a "
                "scan result (clean, infected or anything found) as if the scan had already finished.",
            ),
            _judge(
                "no_yara",
                "The output does not say that a YARA scan was run or enabled: only the antivirus engine was asked for.",
            ),
        ],
    )
