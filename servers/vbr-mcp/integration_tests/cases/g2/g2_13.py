# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""G2-13: which NAS sources would fail to back up because of their configuration."""

from functools import partial
from typing import Literal
from uuid import UUID

from pydantic_ai.models import Model
from pydantic_evals import Case
from pydantic_evals.evaluators import ToolCorrectness

from cases import CaseInputs, judge, tool_budget
from cases.patterns import about, any_of
from evaluators import FactsPresent, ToolsNotCalled
from stand import by_id, environment, nas, proxies, replace, repositories
from stand.ids import M01, N03, R03, mnemonic
from vbr_models.infrastructure import Proxy, ProxyServer, ProxyState
from vbr_models.unstructured_data import BackupProxiesSettings, NfsShareServer

# ---- What VBR serves: the base stand, with what can really stop a NAS source (1.15). VBR requires backup proxies
# and a cache repository for every source (swagger SMBShareServerProcessingModel and siblings), so a source is never
# broken in its own record: it fails when what it uses cannot work, which only shows when the sources are joined with
# the proxies and the repositories (list_unstructured_data_servers says so).
#
# - The general-purpose backup proxies that process file shares (User Guide v13, backup_proxy_general): the backup
#   server's own, as VBR assigns it by default, and nas-prx02, which is offline with out-of-date components.
# - nfs01's export uses the selected proxies only - nas-prx02 alone ("Use the selected backup proxies only",
#   file_share_backup_smb_share_processing_settings): nothing can process it.
# - \\fs01\hr keeps its cache on Repo-Branch, the branch office's SMB share \\nas02\veeam, which is offline.


class GeneralPurposeProxy(Proxy):
    """``GeneralPurposeProxyModel``: a proxy for file shares, object storage and agents."""

    type: Literal["GeneralPurposeProxy"] = "GeneralPurposeProxy"


class GeneralPurposeProxyState(ProxyState):
    """``ProxyStateModel`` of a general-purpose proxy."""

    type: Literal["GeneralPurposeProxy"] = "GeneralPurposeProxy"


NAS_PROXY_HOST = mnemonic("31000000", 14), "nas-prx02.lab.local"


def _general_purpose(
    number: int, host: tuple[UUID, str], *, is_online: bool, is_out_of_date: bool
) -> tuple[GeneralPurposeProxy, GeneralPurposeProxyState]:
    host_id, host_name = host
    proxy_id = mnemonic("30000000", number)
    config = GeneralPurposeProxy(
        id=proxy_id,
        name=host_name,
        description="",
        server=ProxyServer(host_id=host_id, host_name=host_name, max_task_count=4),
    )
    state = GeneralPurposeProxyState(
        id=proxy_id,
        name=host_name,
        description="",
        host_id=host_id,
        host_name=host_name,
        is_disabled=False,
        is_online=is_online,
        is_out_of_date=is_out_of_date,
    )
    return config, state


BACKUP_SERVER_PROXY = _general_purpose(4, (M01, proxies.MANAGED_SERVERS[M01]), is_online=True, is_out_of_date=False)
NAS_PROXY = _general_purpose(5, NAS_PROXY_HOST, is_online=False, is_out_of_date=True)

_NFS = by_id(nas.UNSTRUCTURED_DATA_SERVERS, N03)
assert isinstance(_NFS, NfsShareServer)
NFS = _NFS.model_copy(
    update={
        "processing": _NFS.processing.model_copy(
            update={"backup_proxies": BackupProxiesSettings(auto_select_enabled=False, proxy_ids=[NAS_PROXY[0].id])}
        )
    }
)
SOURCES = [NFS if source.id == N03 else source for source in nas.UNSTRUCTURED_DATA_SERVERS]

ENVIRONMENT = environment(
    proxies=[*proxies.PROXIES, BACKUP_SERVER_PROXY[0], NAS_PROXY[0]],
    proxy_states=[*proxies.PROXY_STATES, BACKUP_SERVER_PROXY[1], NAS_PROXY[1]],
    repository_states=replace(repositories.REPOSITORY_STATES, R03, is_online=False),
    unstructured_data_servers=SOURCES,
)

# ---- What a correct answer says, derived from the data above.

_FINANCE, _HR, _NFS_SOURCE, _S3 = SOURCES
assert _HR.processing.cache_repository_id == R03

EXPECTED = (
    "Two sources would fail to back up. \\\\fs01\\hr: its cache repository is Repo-Branch (\\\\nas02\\veeam), which "
    "is offline, so a backup of the share cannot run. nfs01.lab.local:/exports/eng: it uses selected backup proxies "
    f"only, and the one selected, {NAS_PROXY_HOST[1]}, is offline and its components are out of date, so no proxy "
    "can process it. \\\\fs01\\finance (cache on Repo-Main, proxies chosen automatically - the backup server's own "
    "general-purpose proxy is online) and the Amazon S3 account Lab AWS are fine. VBR keeps no online/offline state "
    "for NAS sources themselves: this follows from the state of their proxies and cache repositories. Neither "
    "\\\\fs01\\hr nor the NFS export is in a backup job yet."
)
"""Ground truth for the judges."""

_SOURCES = r"(?:fs01\\+finance|fs01\\+hr|nfs01|Lab\s+AWS|Amazon\s+S3|lab-docs-prod)"
_UNAVAILABLE = (
    r"(?:off-?line|unavailable|unreachable|down|not\s+(online|reachable|available)|out[\s-]of[\s-]date|outdated)"
)


_about = partial(about, others=_SOURCES, within=240)


FACTS = {
    "hr": r"fs01\\+hr",
    "hr_cache_offline": _about(r"fs01\\+hr", any_of(r"Repo-Branch", r"nas02", rf"cache[\s\S]{{0,80}}?{_UNAVAILABLE}")),
    "nfs": r"nfs01",
    "nfs_proxy_unavailable": _about(
        r"nfs01",
        any_of(
            r"nas-prx02",
            rf"(?:selected|its|only|assigned|chosen|manual\w*)\s+(?:backup\s+)?prox\w*[\s\S]{{0,80}}?{_UNAVAILABLE}",
            r"\bno\s+(?:available|usable|working|online)\s+(?:backup\s+)?prox",
        ),
    ),
}
"""Case-insensitive regexes, one per fact, that a correct answer must match."""

GOOD = [
    """Two of the four sources would fail:

1. **\\\\fs01\\hr** - its cache repository is Repo-Branch (\\\\nas02\\veeam), and Repo-Branch is offline. Without its cache repository the share cannot be backed up.
2. **nfs01.lab.local:/exports/eng** - proxies are selected manually and the only selected proxy, nas-prx02.lab.local, is offline (and its components are out of date).

\\\\fs01\\finance and the Lab AWS (Amazon S3) source look fine: their cache is Repo-Main, which is online, and proxies are chosen automatically. NAS sources have no online state of their own, so this is based on their proxies and cache repositories. Neither \\\\fs01\\hr nor the NFS export is used by a job yet.""",
    """| Source | Problem |
|---|---|
| \\\\fs01\\finance | none |
| \\\\fs01\\hr | cache repository Repo-Branch is not online |
| nfs01.lab.local:/exports/eng | manually selected proxy nas-prx02 is unavailable (offline, outdated) |
| Lab AWS (S3) | none |

To fix: bring \\\\nas02\\veeam back or move hr's cache to another repository; for nfs01, bring nas-prx02 online and update it, or switch the export to automatic proxy selection.""",
]

BAD = {
    "hr_cache_offline": (
        "\\\\fs01\\hr is fine. nfs01.lab.local:/exports/eng would fail: its only selected proxy, nas-prx02, is "
        "offline. \\\\fs01\\finance uses the cache repository Repo-Main, which is online."
    ),
    "nfs_proxy_unavailable": (
        "\\\\fs01\\hr would fail: its cache repository Repo-Branch is offline. nfs01.lab.local:/exports/eng has a "
        "cache repository and looks fine. Proxy-02 is offline, but it is a VMware proxy."
    ),
}

_ALLOWED = (
    "It is acceptable, and not a violation, to add that \\\\fs01\\hr and the NFS export are not used by any job, to "
    "give steps to fix the two sources (bring Repo-Branch or nas-prx02 back, move the cache, select another proxy or "
    "automatic selection, update nas-prx02's components) as advice, or to mention that Repo-Main has free space."
)


def case(judge_model: Model) -> Case[CaseInputs, str, dict[str, str]]:
    _judge = partial(judge, model=judge_model, allowed=_ALLOWED)
    return Case(
        name="G2-13",
        inputs=CaseInputs(
            question="Which of our NAS / file share sources would fail to back up because of configuration problems?",
            environment=ENVIRONMENT,
        ),
        expected_output=EXPECTED,
        metadata={"group": "G2", "base_stand": "1.15, 1.6, 1.4"},
        evaluators=[
            # the sources, then the proxies and repositories they use: a blocker shows only in the join;
            # one source by id and list_jobs are reads the case allows on top
            ToolCorrectness(
                expected_tools=["list_unstructured_data_servers", "list_proxies", "list_repositories"],
                allow_extra=True,
            ),
            *tool_budget(5),
            ToolsNotCalled(),
            FactsPresent(facts=FACTS),
            _judge(
                "exact_blockers",
                "The output names exactly two sources that would fail to back up, with these reasons: \\\\fs01\\hr, "
                "because its cache repository Repo-Branch is offline; and nfs01.lab.local:/exports/eng, because the "
                "only proxy selected for it, nas-prx02.lab.local, is offline (and out of date). Wording may differ.",
            ),
            _judge(
                "healthy_sources_not_flagged",
                "The output does not flag \\\\fs01\\finance or the Amazon S3 source (Lab AWS) as having a "
                "configuration problem that would make its backup fail.",
            ),
            _judge(
                "no_missing_settings",
                "The output does not claim that a source has no cache repository, no proxy or no credentials "
                "configured: every source has them; the problems are the state of the cache repository and the "
                "proxy they use.",
            ),
            _judge(
                "no_online_state",
                "The output does not claim that a NAS source itself is online, offline, reachable or unreachable: "
                "VBR keeps no such state for these sources. Saying that a source's proxy or cache repository is "
                "offline is fine, and so is saying that no state is available for the sources.",
            ),
        ],
    )
