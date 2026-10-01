# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Third-party scouting reports are served as an EXCERPT plus a source link.

Owner answer 2026-09-25 (final-pass batch 1, census X07-02 option b): the
public data files carry the first part of each FanGraphs, MLB Pipeline,
Baseball America, ESPN and Just Baseball report, never the full text. The full
text stays in prospects.db (snapshots / draft_snapshots / overseas_snapshots
tools_json), which no deploy step copies. Every exporter that writes report
prose into a served payload goes through this module:

  storage.export_timeseries_json   scout_reports chunks (player cards), and the
                                   per-source extras rows on the boot, debuts,
                                   inactive, player_detail and debuts_full files
  draft_export.build_draft_export  the draft board (points and tool_grades)
  overseas_export                  the overseas board
  mlb_player_export                the MLB card's latest report slice

report_excerpt() cleans dashes and whitespace and cuts; it never rewrites a word. The cut
lands on the last sentence end inside the limit when that keeps at least half
of it, otherwise on the last word boundary with an ellipsis, so an excerpt is
never cut mid-word and never longer than EXCERPT_MAX_CHARS.

report_url() returns a link only where a real address for the report is known:
the player's own page at FanGraphs (stored FanGraphs id) or MLB Pipeline (MLBAM
id), the ESPN article a list was scraped from, or the Just Baseball board page.
Baseball America pages need an id we do not store, so those excerpts name the
source and the list instead. test_report_excerpt.py pins both rules over the
served payloads.
"""

from __future__ import annotations

import re
from urllib.parse import quote

EXCERPT_MAX_CHARS = 280
# A sentence end earlier than this is too short an excerpt; cut on a word
# boundary instead.
_MIN_SENTENCE_CUT = EXCERPT_MAX_CHARS // 2
_ELLIPSIS = "\u2026"

# Payload source key -> the name the site prints.
REPORT_SOURCE_NAMES = {
    "fangraphs": "FanGraphs",
    "mlb_pipeline": "MLB Pipeline",
    "mlb_pipeline_draft": "MLB Pipeline",
    "baseballamerica": "Baseball America",
    "baseballamerica_draft": "Baseball America",
    "espn": "ESPN",
    "espn_draft": "ESPN",
    "just_baseball": "Just Baseball",
}

# Tokens whose trailing period is not a sentence end.
_ABBREV = {"jr", "sr", "st", "mr", "dr", "vs", "no", "mt", "ft", "lb", "lbs",
           "approx", "etc", "ii", "iii", "iv"}
_SENTENCE_END = re.compile(r"[.!?][\"')\u201d\u2019]?(?=\s)")


def _clean(text) -> str:
    """Site copy rule applied before measuring: em and en dashes become the
    hyphen forms draft_export._strip_dashes writes (so a later pass there can
    never lengthen an excerpt). Runs of spaces and tabs collapse to one space
    and blank-line runs to one blank line; line breaks stay, because a report's
    header lines (ESPN's "Type: ...") read as run-on prose without them."""
    s = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    s = s.replace(" \u2014 ", " - ").replace("\u2014", " - ") \
         .replace(" \u2013 ", " - ").replace("\u2013", "-")
    s = re.sub(r"[^\S\n]+", " ", s)
    s = re.sub(r" ?\n ?", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def report_excerpt(text) -> tuple[str, bool]:
    """(excerpt, truncated) for one report, cleaned by _clean; text at or under
    EXCERPT_MAX_CHARS comes back whole."""
    s = _clean(text)
    if len(s) <= EXCERPT_MAX_CHARS:
        return s, False
    best = -1
    for m in _SENTENCE_END.finditer(s, 0, EXCERPT_MAX_CHARS + 1):
        end = m.end()
        if end > EXCERPT_MAX_CHARS:
            break
        if m.group(0)[0] == ".":
            tok = re.search(r"(\S*)$", s[:m.start()]).group(1).lower()
            if tok in _ABBREV or (len(tok) == 1 and tok.isalpha()):
                continue
        best = end
    if best >= _MIN_SENTENCE_CUT:
        return s[:best], True
    # Word boundary, leaving room for the ellipsis.
    sp = max(s.rfind(" ", 0, EXCERPT_MAX_CHARS), s.rfind("\n", 0, EXCERPT_MAX_CHARS))
    cut = s[:sp] if sp > 0 else s[:EXCERPT_MAX_CHARS - 1]
    cut = cut.rstrip(" \n,;:-(")
    return cut + _ELLIPSIS, True


_ESPN_URLS: dict[str, str] | None = None
_JB_URL: str | None = None


def _publisher_urls() -> tuple[dict[str, str], str | None]:
    """The ESPN article for each scraped list label and the Just Baseball board
    page, read from the scrapers that fetched them (one source of truth)."""
    global _ESPN_URLS, _JB_URL
    if _ESPN_URLS is None:
        try:
            from scrapers import ESPN_INTERVALS, JB_ROLLING_URL
            _ESPN_URLS = {label: url for url, label, _d in ESPN_INTERVALS}
            _JB_URL = JB_ROLLING_URL
        except Exception:                      # noqa: BLE001 - links are optional
            _ESPN_URLS, _JB_URL = {}, None
    return _ESPN_URLS, _JB_URL


def report_url(src: str, *, label: str | None = None, fg_id=None,
               mlbam_id=None) -> str | None:
    """The address of this report's source page, or None when none is known."""
    if src == "fangraphs" and fg_id is not None and str(fg_id).strip():
        return f"https://www.fangraphs.com/players/x/{quote(str(fg_id).strip())}/stats"
    if src in ("mlb_pipeline", "mlb_pipeline_draft") and mlbam_id:
        try:
            return f"https://www.mlb.com/player/{int(mlbam_id)}"
        except (TypeError, ValueError):
            return None
    if src == "espn" and label:
        return _publisher_urls()[0].get(label)
    if src == "just_baseball":
        return _publisher_urls()[1]
    return None


def excerpt_fields(text, src: str, *, label: str | None = None, fg_id=None,
                   mlbam_id=None) -> dict:
    """The served fields for one report: the excerpt, whether it was cut, the
    source's name and the link (None when only the name and list are known)."""
    exc, cut = report_excerpt(text)
    return {
        "text": exc,
        "truncated": cut,
        "source": REPORT_SOURCE_NAMES.get(src, src),
        "url": report_url(src, label=label, fg_id=fg_id, mlbam_id=mlbam_id),
    }


def excerpt_tools(tools, src: str, *, label: str | None = None, fg_id=None,
                  mlbam_id=None):
    """A copy of a snapshot's tools dict with `_extras.report` replaced by the
    excerpt and the link fields added beside it (report_truncated,
    report_source, report_label, report_url). Tools without a report come back
    unchanged (the same object)."""
    if not isinstance(tools, dict):
        return tools
    ex = tools.get("_extras")
    if not isinstance(ex, dict) or not ex.get("report"):
        return tools
    if fg_id is None:
        fg_id = ex.get("fg_player_id_str") or ex.get("fg_player_id")
    f = excerpt_fields(ex["report"], src, label=label, fg_id=fg_id, mlbam_id=mlbam_id)
    new_ex = dict(ex)
    new_ex["report"] = f["text"]
    new_ex["report_truncated"] = f["truncated"]
    new_ex["report_source"] = f["source"]
    new_ex["report_label"] = label
    new_ex["report_url"] = f["url"]
    out = dict(tools)
    out["_extras"] = new_ex
    return out
