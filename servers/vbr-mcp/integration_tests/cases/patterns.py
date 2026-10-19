# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

"""Regex building blocks for the cases' facts: the ways a correct answer writes a date, a size or a verdict.

A fact must accept every way a reader would accept, or it fails a correct answer; and it must still tell a wrong
one apart, or it checks nothing. Each case used to write its own variant of "started" and of a date, and the variants
drifted. These are matched against ``evaluators.normalize``d text (ASCII hyphens and spaces, no Markdown emphasis),
case-insensitively.
"""

import re
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

_ORDINAL = r"(?:st|nd|rd|th)?"


def name(text: str) -> str:
    """An object name, written with a hyphen, a space or neither between its parts: ``Daily-VMs``, ``Daily VMs``."""
    return r"[-\s]?".join(re.escape(part) for part in re.split(r"[-\s]", text))


def any_of(*patterns: str) -> str:
    """A pattern matching any of ``patterns``."""
    return "(?:" + "|".join(patterns) + ")"


def near(first: str, second: str, within: int = 200) -> str:
    """``first`` and ``second`` within ``within`` characters of each other, in either order (lines included)."""
    return rf"(?:{first})[\s\S]{{0,{within}}}(?:{second})|(?:{second})[\s\S]{{0,{within}}}(?:{first})"


_CLAUSE_END = r"(?:[.;!?](?=\s|$)|\b(?:and|but|while|whereas)\b)"
"""Where a clause ends: at the end of a sentence, or at a conjunction that begins the next clause."""

_CLAUSE_START = r"(?:(?<![^\n])|(?<=[.;!?]\s)|(?<=\band\s)|(?<=\bbut\s)|(?<=\bwhile\s)|(?<=\bwhereas\s))"
"""Where a clause begins: at the start of a line, after the end of a sentence or after a conjunction."""

_LIST_SEPARATOR = r"\s*(?:,\s*(?:and\b|&)?|\band\b|&|/)\s*"


def about(subject: str, condition: str, *, others: str, within: int, before: int = 80) -> str:
    """``condition`` said of ``subject``, not of the one next to it in the answer.

    After ``subject``, or after a list it heads ("srv-app-01 and sql-node-02 have no agent"), within ``within``
    characters and before any of ``others`` (a pattern) or a blank line - and not as the label of another object
    ("Proxy-02 is fine. Offline: Proxy-03"). Or ahead of ``subject`` in the clause it stands in, with no other object
    ahead of the condition there - in "Proxy-02 is disabled and Proxy-03 is offline" the disabled one is Proxy-02 - and
    nothing but a list of other objects between the condition and ``subject`` ("No agent: srv-app-01, sql-node-02";
    "the disabled one is Proxy-03"), within ``before`` characters each.
    """
    gap = rf"(?:(?!{others})(?:[^\n]|\n(?!\s*\n))){{0,{within}}}?"
    after = rf"{subject}(?:{_LIST_SEPARATOR}(?:{others})){{0,8}}{gap}(?:{condition})(?!\s*:\s*(?:{others}))"
    clause = rf"(?:(?!{others}|{_CLAUSE_END})[^\n])"
    listed = rf"(?:(?:{others}){_LIST_SEPARATOR}){{0,8}}"
    ahead = rf"{_CLAUSE_START}{clause}{{0,{before}}}?(?:{condition}){clause}{{0,{before}}}?{listed}{subject}"
    return any_of(after, ahead)


def day(when: date | datetime, *, weekday: bool = True) -> str:
    """A calendar day in any common format, with or without the year.

    ``2026-10-06``, ``10-06`` (as the stand writes a day without its year), ``Oct 6``, ``October 6th, 2026``, ``6 Oct``,
    ``6th of October``, ``06.10.2026``, ``10/06/2026``, ``6/10`` is not accepted (ambiguous); with ``weekday``, also
    ``Tuesday`` alone.
    """
    d, m, y = when.day, when.month, when.year
    month = rf"(?:{when:%B}|{when:%b}\.?)"
    forms = [
        rf"{y}-{m:02d}-{d:02d}",
        rf"(?<![\w./-]){m:02d}-{d:02d}(?![\w/-]|[.,]\d)",
        rf"(?<!\d){d:02d}\.{m:02d}\.(?:{y}|{y % 100:02d})\b",
        rf"(?<!\d){m:02d}/{d:02d}/{y}",
        rf"(?<!\d){m}/{d}/{y}",
        rf"{month}\s+0?{d}{_ORDINAL}\b",
        rf"(?<!\d)0?{d}{_ORDINAL}\s+(?:of\s+)?{month}",
    ]
    if weekday:
        forms.append(rf"\b{when:%A}\b")
    return any_of(*forms)


def _meridiem(hour: int) -> str:
    """``AM`` or ``PM`` for ``hour``, also written ``a.m.``, ``am`` or ``a. m.``."""
    letter = "a" if hour < 12 else "p"
    return rf"{letter}\.?\s?m\b\.?"


def clock(when: datetime) -> str:
    """A time of day as ``22:06``, ``22:06:05``, ``10:06 PM``, ``10:06pm`` or ``10:06 p.m.``; on the hour also ``10 PM``.

    00:00 is also ``midnight``, 12:00 ``noon``. A 12-hour time is accepted only with its own meridiem: ``8:40 PM`` is
    not 08:40, and ``12:30 AM`` not 12:30.
    """
    hour12 = when.hour % 12 or 12
    meridiem = _meridiem(when.hour)
    misread = _meridiem(when.hour + 12) if when.hour < 12 else _meridiem(0) if when.hour == 12 else None
    plain = rf"(?<!\d)0?{when.hour}:{when:%M}(?!\d)"
    if misread is not None:  # 08:40 written as 8:40 is fine, as 8:40 PM it is 20:40
        plain += rf"(?!(?::\d\d)?\s*{misread})"
    forms = [plain, rf"(?<!\d){hour12}:{when:%M}(?::\d\d)?\s*{meridiem}"]
    if when.minute == 0:
        forms.append(rf"(?<![\d:.])0?{hour12}\s*{meridiem}")
        if when.hour in (0, 12):
            forms.append(r"\bmidnight\b" if when.hour == 0 else r"\b(?:noon|midday)\b")
    return any_of(*forms)


def _numeral(texts: set[str]) -> str:
    """A pattern for the decimal numerals ``texts``, with or without thousands separators and trailing zeros."""
    variants = set()
    for text in texts:
        whole, _, fraction = text.partition(".")
        fraction = fraction.rstrip("0")
        tail = rf"\.{fraction}0*" if fraction else r"(?:\.0+)?"
        grouped = f"{int(whole):,}" if whole.isdigit() else whole
        for integer in {whole, grouped, grouped.replace(",", " ")}:
            variants.add(re.escape(integer) + tail)
    body = any_of(*sorted(variants, key=len, reverse=True))
    return rf"(?<![\d.,]){body}(?!\d|[.,]\d)"


def _rounded(value: float, places: int) -> set[str]:
    """``value`` to ``places`` decimals as people round it: half up, and as Python formats it (half to even)."""
    half_up = Decimal(str(value)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    return {f"{value:.{places}f}", f"{half_up:f}"}


def number(value: float, *, decimals: int = 1) -> str:
    """A number rounded to up to ``decimals`` decimals, with or without thousands separators: 3576 -> ``3,576``.

    Never matches inside a longer number, and a sentence-final period does not count as a decimal point.
    """
    exact = f"{value:f}".rstrip("0").rstrip(".") if isinstance(value, float) else str(value)
    return _numeral({exact} | {text for places in range(decimals + 1) for text in _rounded(value, places)})


def gb(value: float, *, tb: bool = True) -> str:
    """A size given in GB: ``860 GB``, ``860.0 GB``, ``860 GiB`` and, with ``tb``, the same in TB (``0.86 TB``).

    TB is accepted with one or two decimals, decimal or binary (860 GB = ``0.86 TB`` or ``0.84 TiB``); a coarser
    rounding (``1 TB``) is not the number the tools gave.
    """
    forms = [rf"{number(value)}[\s-]*(?:GB|GiB|gigabytes?)\b"]
    if tb and value >= 100:
        terabytes = {text for base in (1000, 1024) for places in (1, 2) for text in _rounded(value / base, places)}
        forms.append(rf"{_numeral(terabytes)}[\s-]*(?:TB|TiB|terabytes?)\b")
    return any_of(*forms)


def percent(value: float, *, decimals: int = 1) -> str:
    """A percentage rounded to whole or up to ``decimals``: 4.2 -> ``4.2%``, ``4 %``, ``4.2 percent``; not ``14.2%``."""
    return rf"{number(value, decimals=decimals)}\s*(?:%|percent\b)"


def days(count: int, *, slack: int = 0) -> str:
    """``count`` days (or ``count``±``slack``): ``44 days``, ``44-day``, ``in 44 days``, ``44 day(s)``."""
    values = "|".join(str(n) for n in range(count - slack, count + slack + 1))
    return rf"(?<![\d.])(?:{values})[-\s]*days?\b"


# ---- Verdicts, written the many ways an answer says them.

STARTED = any_of(
    r"\bstart(ed|ing)\b",
    r"\b(kicked|fired)\s+off\b",
    r"\btriggered\b",
    r"\binitiated\b",
    r"\blaunched\b",
    r"\bqueued\b",
    r"\b(is|now)\s+(running|in\s+progress|underway)\b",
    r"\bhas\s+begun\b",
    r"\bunderway\b",
)
"""An action reported as set in motion. Combine with ``NOT_DONE`` checks where finished must not be claimed."""

ALREADY_RUNNING = any_of(
    r"\balready\s+(running|in\s+progress|active|processing|underway|has\s+a\s+(running|active)\s+session)\b",
    r"\b(is|'s|was)\s+(currently|still)\s+(running|in\s+progress|active|processing)\b",
    r"\b(currently|still)\s+running\b",
    r"\bhas\s+a\s+session\s+(running|in\s+progress)\b",
    r"\bsession\s+(is\s+)?(still\s+)?(running|in\s+progress)\b",
)

CANNOT = any_of(
    r"\bcan(?:\s*not|'?t)\b",
    r"\bcould(?:\s+not|n'?t)\b",
    r"\b(?:can|could)\s+only\b",
    r"\b(?:wo|would)n'?t\s+(?:be\s+able|let|allow|accept|support|work)\b",
    r"\b(?:will|would)\s+not\s+(?:be\s+able|let|allow|accept|support|work)\b",
    r"\b(?:is|are|was|were)(?:n'?t|\s+not)\s+(?:possible|supported|available|exposed|permitted|allowed|able|"
    r"\w+(?:able|ible)|an?\s+(?:option|way|tool))\b",
    r"\b(?:does|do|did)(?:n'?t|\s+not)\s+(?:have|support|expose|offer|provide|allow|permit|let|include|accept|"
    r"cover)\b",
    r"\b(?:unable|not\s+able|not\s+possible|impossible|no\s+way)\b",
    r"\bnot\s+(?:supported|available|exposed|possible|permitted|allowed)\b",
    r"\bno\s+(?:[\w-]+\s+){0,2}?(?:tools?|ways?|options?|parameters?|capabilit(?:y|ies)|support|endpoints?|means)\b",
    r"\bnone\s+of\s+(?:the\s+|my\s+|these\s+|your\s+)?(?:[\w-]+\s+){0,2}?tools\b",
    r"\b(?:lacks?|lacking|without)\s+(?:a\s+|an\s+|any\s+|the\s+)?(?:[\w-]+\s+){0,2}?(?:tool|option|parameter|"
    r"capability|support|endpoint)\b",
)
"""A refusal or a limit: "I can't", "cannot", "there is no tool", "none of the available tools can", "isn't supported".

Not a mere negation: "you don't need to do anything else" refuses nothing.
"""

NOT_AUTHORIZED = any_of(
    r"\bnot\s+(authori[sz]ed|permitted|allowed)\b",
    r"\bpermission",
    r"\bprivilege",
    r"\b(access\s+(is\s+)?denied|accessdenied)\b",
    r"\bforbidden\b",
    r"\b403\b",
    r"\b(lacks?|lacking|without|insufficient|missing)\s+(the\s+)?(necessary\s+|required\s+)?(rights|role|access)\b",
    r"\b(does|do)\s*n[o']?t\s+have\s+(the\s+)?(necessary\s+|required\s+)?(rights|role|access|permission)",
)

OFFLINE = any_of(
    r"\boff-?line\b",
    r"\b(?:is|are|was|were)(?:n't|\s+not)\s+online\b",
    r"\bnot\s+online\b",
    r"\bunreachable\b",
    r"\bunavailable\b",
    r"\bnot\s+(reachable|available|responding)\b",
    r"\bdown\b",
    r"isOnline\W+false",
)

OUT_OF_DATE = any_of(
    r"\bout[\s-]of[\s-]date\b",
    r"\boutdated\b",
    r"\bisOutOfDate\b",
    r"\b(needs?|requires?|requiring|pending)\s+(an?\s+)?(component\s+|components\s+)?(update|upgrade)",
    r"\b(needs?|requires?|must\s+be|ha(?:s|ve)\s+to\s+be)\s+(?:updated|upgraded|updating|upgrading)\b",
    r"\b(update|upgrade)\s+(of\s+)?(its\s+|the\s+)?(veeam\s+)?components?\b",
    r"\bcomponents?\s+(are\s+|is\s+)?(not\s+up[\s-]to[\s-]date|stale|old)\b",
    r"\bcomponents?\s+(?:[\w-]+\s+){0,2}?(?:are|is|were|was|have|has)(?:n't|\s+not)\s+(?:yet\s+)?(?:been\s+)?"
    r"(?:up[\s-]to[\s-]date|current|updated|upgraded)\b",
    r"\bolder\s+(component|version)",
)

DISABLED = any_of(
    r"\bdisabled\b", r"\bturned\s+off\b", r"\bswitched\s+off\b", r"\bnot\s+enabled\b", r"isDisabled\W+true"
)

NOT_FOUND = any_of(
    r"\bnot\s+found\b",
    r"\b(no|isn't\s+a|is\s+not\s+a)\s+(such\s+)?(job|object|vm|backup|session)\b"
    r"(?!\s+(was\s+|has\s+been\s+)?(started|is\s+running))",
    r"\b(does\s*n[o']?t|did\s*n[o']?t)\s+(exist|find)\b",
    r"\bnon-?existent\b",
    r"\b(?:can'?t|can\s*not|could\s*n[o']?t|could\s+not|unable\s+to)\s+(?:find|locate)\b",
    r"\b(?:isn'?t|is\s+not|wasn'?t|was\s+not)\s+(?:one\s+of|among|listed|in\s+(?:the|your)\s+(?:list|jobs))\b",
    r"\bthere\s+is\s+no\b",
    r"\bno\s+(job|match)\w*\s+(named|called|matching|by\s+that\s+name|with\s+that\s+name)\b",
)
"""The target does not exist. Every alternative is anchored on a word boundary: a bare ``no`` would match "now"."""
