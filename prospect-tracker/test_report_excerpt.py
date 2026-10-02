"""Third-party scouting reports ship as an excerpt plus a source link or name.

Owner answer 2026-09-25 (final-pass batch 1, census X07-02 option b): the
public data files carry at most report_excerpt.EXCERPT_MAX_CHARS characters of
any FanGraphs, MLB Pipeline, Baseball America, ESPN or Just Baseball report,
cut at a sentence or word boundary, and every excerpt carries a link to the
source's page or names the source and list. The full text stays in
prospects.db. Owner answer 2026-10-01 (REPEX-1 option b): an excerpt with no
page of the player's own links to the publisher's list page instead
(report_excerpt.report_list_url), so every served excerpt has a link. The served payloads are pipeline outputs (gitignored), so each
payload check skips on a checkout that has not built it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import report_excerpt as R

ROOT = Path(__file__).parent
DATA = ROOT / "data"
MAX = R.EXCERPT_MAX_CHARS


# ---------------------------------------------------------------- the cutter

def _long(n_words: int = 120) -> str:
    return " ".join(f"word{i}" for i in range(n_words))


def test_short_text_comes_back_whole():
    txt = "Plus raw power and a strong arm. Projects as an everyday right fielder."
    assert R.report_excerpt(txt) == (txt, False)


def test_whitespace_is_cleaned_not_reworded():
    exc, cut = R.report_excerpt("Plus  raw\tpower. \n\n\n\nStrong   arm.\r\nType: RF")
    assert (exc, cut) == ("Plus raw power.\n\nStrong arm.\nType: RF", False)


def test_dashes_follow_the_site_rule_before_measuring():
    exc, _ = R.report_excerpt("A 20\u201380 grade \u2014 plus arm.")
    assert exc == "A 20-80 grade - plus arm."


def test_long_text_cuts_on_a_word_boundary_with_an_ellipsis():
    src = _long()
    exc, cut = R.report_excerpt(src)
    assert cut and len(exc) <= MAX and exc.endswith("\u2026")
    body = exc[:-1]
    assert src.startswith(body) and src[len(body)] == " ", "cut mid-word"


def test_long_text_prefers_a_sentence_end_past_half_the_limit():
    first = "He has plus bat speed and an advanced approach for his age " * 3
    src = first.strip() + ". " + _long()
    exc, cut = R.report_excerpt(src)
    assert cut and exc == first.strip() + "." and len(exc) <= MAX


def test_an_abbreviation_is_not_a_sentence_end():
    lead = "He has a plus arm and real raw power to all fields " * 4   # 204 chars
    src = (lead + "much like Smith Jr. " + "and more words follow here " * 10).strip()
    exc, cut = R.report_excerpt(src)
    assert cut and not exc.endswith("Jr.") and exc.endswith("\u2026") and len(exc) <= MAX


def test_links_are_built_only_where_an_address_is_known():
    assert R.report_url("fangraphs", fg_id="sa3022864") == \
        "https://www.fangraphs.com/players/x/sa3022864/stats"
    assert R.report_url("fangraphs") is None
    assert R.report_url("mlb_pipeline", mlbam_id=675085) == "https://www.mlb.com/player/675085"
    assert R.report_url("mlb_pipeline_draft") is None
    assert R.report_url("baseballamerica", label="Baseball America 2026 Cubs Top 30") is None
    from scrapers import ESPN_INTERVALS, JB_ROLLING_URL
    url, label, _d = ESPN_INTERVALS[0]
    assert R.report_url("espn", label=label) == url
    assert R.report_url("espn", label="not a scraped list") is None
    assert R.report_url("just_baseball") == JB_ROLLING_URL


def test_list_links_use_the_recorded_list_page_for_each_list():
    import scrapers as S
    recorded = [(u, lab, "mlb_pipeline") for u, lab, *_r in S.MLB_PIPELINE_INTERVALS]
    recorded += [(u, lab, "mlb_pipeline") for u, lab, *_r in S.MLB_PIPELINE_ORG_INTERVALS]
    recorded += [(u, lab, "mlb_pipeline_draft") for u, lab, *_r
                 in S.MLB_PIPELINE_DRAFT_HISTORY_INTERVALS]
    recorded += [(u, lab, "espn") for u, lab, *_r in S.ESPN_INTERVALS]
    recorded += [(u, lab, "espn_draft") for u, lab, *_r in S.ESPN_DRAFT_INTERVALS]
    assert len(recorded) > 500
    for url, label, src in recorded:
        assert R.report_list_url(src, label) == (url, True), label
    # Pipeline lists the module constants do not enumerate take the same
    # year-keyed page forms the scrapers fetch.
    assert R.report_list_url("mlb_pipeline", "MLB Pipeline Live 2026-08-13") == \
        ("https://www.mlb.com/milb/prospects/2026/top100/", True)
    assert R.report_list_url("mlb_pipeline", "MLB Pipeline 2027 Red Sox Top 30") == \
        ("https://www.mlb.com/prospects/2027/redsox", True)
    # A past draft class takes its year-keyed page, never the rolling current one.
    assert R.report_list_url("mlb_pipeline_draft", "MLB Pipeline 2026 Draft Top 250") == \
        ("https://www.mlb.com/milb/prospects/2026/draft/", True)
    assert R.report_list_url("just_baseball") == (S.JB_ROLLING_URL, True)


def test_list_links_fall_back_to_the_list_family_home():
    assert set(R.REPORT_SOURCE_NAMES) <= set(R.LIST_FAMILY_HOMES)
    for src, home in R.LIST_FAMILY_HOMES.items():
        assert home.startswith("https://"), src
    assert R.report_list_url("baseballamerica", "Baseball America 2026 Cubs Top 30") == \
        ("https://www.baseballamerica.com/rankings/", False)
    assert R.report_list_url("baseballamerica_draft",
                             "Baseball America 2028 Draft HS Top 100") == \
        ("https://www.baseballamerica.com/rankings/", False)
    assert R.report_list_url("fangraphs", "2026tradedeadline") == \
        ("https://www.fangraphs.com/prospects/the-board", False)
    assert R.report_list_url("espn", "not a scraped list") == ("https://www.espn.com/mlb/", False)
    assert R.report_list_url("not_a_source", "x") is None


def test_excerpt_fields_carry_the_list_link_only_without_a_player_page():
    f = R.excerpt_fields("Plus arm.", "mlb_pipeline", label="MLB Pipeline 2014 Angels Top 30",
                         mlbam_id=675085)
    assert f["url"] == "https://www.mlb.com/player/675085" and "list_url" not in f
    f = R.excerpt_fields("Plus arm.", "mlb_pipeline", label="MLB Pipeline 2014 Angels Top 30")
    assert f["url"] is None
    assert (f["list_url"], f["list_page"]) == ("https://www.mlb.com/prospects/2014/angels", True)


def test_excerpt_tools_replaces_the_report_and_leaves_the_grades():
    tools = {"fb": 60.0, "_extras": {"report": _long(), "age": 21.8}}
    out = R.excerpt_tools(tools, "baseballamerica_draft",
                          label="Baseball America 2027 Draft Top 100")
    ex = out["_extras"]
    assert out["fb"] == 60.0 and ex["age"] == 21.8
    assert len(ex["report"]) <= MAX and ex["report_truncated"] is True
    assert ex["report_source"] == "Baseball America"
    assert ex["report_label"] == "Baseball America 2027 Draft Top 100"
    assert ex["report_url"] is None
    assert ex["report_list_url"] == "https://www.baseballamerica.com/rankings/"
    assert ex["report_list_page"] is False
    assert len(tools["_extras"]["report"]) > MAX, "the input dict must not be mutated"
    no_report = {"fb": 55.0, "_extras": {"age": 20.0}}
    assert R.excerpt_tools(no_report, "fangraphs") is no_report


# ---------------------------------------------------------- served payloads

def _load(name: str):
    path = DATA / name
    if not path.is_file():
        pytest.skip(f"data/{name} not built here")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


_SRC_KEY_BY_NAME = {"FanGraphs": "fangraphs", "MLB Pipeline": "mlb_pipeline",
                    "Baseball America": "baseballamerica", "ESPN": "espn",
                    "Just Baseball": "just_baseball"}


def _year(label, date=None):
    m = re.search(r"(?<!\d)(20\d\d)(?!\d)", str(label or ""))
    return m.group(1) if m else (str(date or "")[:4] or None)


def _assert_linked_or_named(where: str, url, source, label, list_url=None,
                            list_page=None, src_key=None, seen=None, date=None):
    """Every served excerpt names its source and carries a link: the player's
    own page, or the publisher's list page that report_list_url maps its
    source and list to."""
    assert source, f"{where}: excerpt names no source"
    if url:
        assert re.match(r"^https://", url), f"{where}: bad link {url!r}"
        return
    assert label, f"{where}: excerpt has neither a link nor a list name"
    assert list_url and re.match(r"^https://", list_url), f"{where}: no link"
    key = src_key or _SRC_KEY_BY_NAME.get(source, source)
    assert R.report_list_url(key, label) == (list_url, bool(list_page)), \
        f"{where}: served list link {list_url!r} is not the mapping's"
    if key.startswith("mlb_pipeline"):
        assert list_page is True, f"{where}: {label!r} has no recorded list page"
    if seen is not None:
        seen.add((key, _year(label, date)))


def _assert_mapping_covers(seen):
    """The mapping gives a link for every source and year served (an MLB
    Pipeline list always gets the page of that list and year, checked per
    excerpt above)."""
    assert seen
    for key, year in sorted(seen, key=str):
        assert year, f"{key}: an unlinked excerpt with no year"
        assert key in R.LIST_FAMILY_HOMES, f"{key} {year}: no list mapping"


@pytest.mark.parametrize("name", [f"scout_reports_{i}.json" for i in range(8)]
                         + ["scout_reports.json"])
def test_scout_report_sidecar_serves_excerpts_only(name):
    doc = _load(name)
    n = 0
    seen: set = set()
    for pk, by_src in doc.items():
        for src, entries in by_src.items():
            if src.startswith("_") or not isinstance(entries, list):
                continue
            for e in entries:
                txt = e.get("text") or ""
                assert len(txt) <= MAX, f"{name} {pk}/{src}: {len(txt)} chars served"
                _assert_linked_or_named(f"{name} {pk}/{src}", e.get("url"),
                                        e.get("source"), e.get("label"),
                                        e.get("list_url"), e.get("list_page"),
                                        src_key=src, seen=seen, date=e.get("date"))
                n += 1
    assert n > 0, f"{name} carries no reports"
    if seen:
        _assert_mapping_covers(seen)


def _draft_report_extras(doc):
    for cls in doc.get("classes") or []:
        for p in cls.get("prospects") or []:
            for src, tools in (p.get("tool_grades") or {}).items():
                yield p.get("player_key"), src, tools
            for pt in p.get("points") or []:
                yield p.get("player_key"), pt.get("source"), pt.get("tools")


def test_draft_board_serves_excerpts_only():
    doc = _load("draft_timeseries.json")
    n = 0
    seen: set = set()
    for pk, src, tools in _draft_report_extras(doc):
        ex = (tools or {}).get("_extras") or {}
        if not ex.get("report"):
            continue
        assert len(ex["report"]) <= MAX, f"draft {pk}/{src}: {len(ex['report'])} chars"
        _assert_linked_or_named(f"draft {pk}/{src}", ex.get("report_url"),
                                ex.get("report_source"), ex.get("report_label"),
                                ex.get("report_list_url"), ex.get("report_list_page"),
                                src_key=src, seen=seen)
        n += 1
    assert n > 0
    _assert_mapping_covers(seen)


def test_overseas_board_serves_excerpts_only():
    doc = _load("overseas_timeseries.json")
    seen: set = set()
    for lg in doc.get("leagues") or []:
        for p in lg.get("prospects") or []:
            for src, tools in (p.get("tool_grades") or {}).items():
                ex = (tools or {}).get("_extras") or {}
                if ex.get("report"):
                    assert len(ex["report"]) <= MAX, (p.get("player_key"), src)
                    _assert_linked_or_named(f"overseas {p.get('player_key')}/{src}",
                                            ex.get("report_url"), ex.get("report_source"),
                                            ex.get("report_label"), ex.get("report_list_url"),
                                            ex.get("report_list_page"), src_key=src,
                                            seen=seen)
    if seen:
        _assert_mapping_covers(seen)


def _long_reports(obj, found, path="$"):
    """Every `report` string longer than the excerpt limit, anywhere."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "report" and isinstance(v, str) and len(v) > MAX:
                found.append(path)
            else:
                _long_reports(v, found, f"{path}.{k}")
    elif isinstance(obj, list):
        for v in obj:
            _long_reports(v, found, f"{path}[]")


@pytest.mark.parametrize("name", ["timeseries.json", "debuts.json", "inactive.json"])
def test_board_payloads_carry_no_full_report(name):
    found: list[str] = []
    _long_reports(_load(name), found)
    assert not found, f"{name}: {len(found)} full reports, first at {found[0]}"


@pytest.mark.parametrize("subdir", ["player_detail", "debuts_full"])
def test_player_shards_carry_no_full_report(subdir):
    d = DATA / subdir
    files = sorted(d.glob("*.json")) if d.is_dir() else []
    if not files:
        pytest.skip(f"data/{subdir}/ not built here")
    bad = []
    for f in files:
        found: list[str] = []
        with open(f, encoding="utf-8") as fh:
            _long_reports(json.load(fh), found)
        if found:
            bad.append(f.name)
    assert not bad, f"{len(bad)} {subdir} shards carry a full report, e.g. {bad[:3]}"


def test_mlb_card_report_is_an_excerpt():
    doc = _load("mlb_player_detail.json")
    n = 0
    for key, card in (doc.get("players") or {}).items():
        rep = (card.get("scout") or {}).get("report")
        if not rep:
            continue
        assert len(rep.get("text") or "") <= MAX, key
        _assert_linked_or_named(f"mlb card {key}", rep.get("url"), rep.get("source"),
                                rep.get("label"), rep.get("list_url"), rep.get("list_page"),
                                date=rep.get("date"))
        n += 1
    assert n > 0


# ------------------------------------------------------------ the renderers

def test_prospx_renders_the_excerpt_link_on_cards_and_the_draft_board():
    src = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")
    assert "function _reportLinkHtml(url, label)" in src
    # Player card: each cycle's meta line uses the served link first.
    assert "_reportLinkHtml(e.url, s.label)" in src
    assert '{ key: "baseballamerica", label: "Baseball America"}' in src
    # Draft and overseas detail: excerpt plus link or named source and list.
    assert "_reportLinkHtml(ext.report_url, srcName)" in src
    assert "ext.report_label" in src
    # An excerpt with no player page links to the publisher's list, and the
    # link text says it lands on a list.
    assert "function _reportListLinkHtml(url, isListPage, label, listName)" in src
    assert "_reportListLinkHtml(e.list_url, e.list_page, s.label, e.label)" in src
    assert "list_url: e.list_url || null, list_page: !!e.list_page" in src
    assert ("_reportListLinkHtml(ext.report_list_url, ext.report_list_page, srcName, "
            "ext.report_label)") in src
    helper = src.split("function _reportListLinkHtml(")[1].split("\n}")[0]
    assert 'rel="noopener"' in helper
    assert "View the list on ${label}" in helper and "View lists on ${label}" in helper
    js = (ROOT / "assets" / "projections.js").read_text(encoding="utf-8")
    assert "r.list_url" in js and "View the list on ${srcName}" in js


def test_copy_states_the_excerpt_limit():
    import build_site as B
    page = B.build_sources()
    assert f"at most {MAX} characters" in page
    assert "full text" not in page.split('id="api"')[0]
    gl = (ROOT / "assets" / "glossary.js").read_text(encoding="utf-8")
    assert f"at most {MAX} characters" in gl
