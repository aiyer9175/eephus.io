"""Third-party scouting reports ship as an excerpt plus a source link or name.

Owner answer 2026-09-25 (final-pass batch 1, census X07-02 option b): the
public data files carry at most report_excerpt.EXCERPT_MAX_CHARS characters of
any FanGraphs, MLB Pipeline, Baseball America, ESPN or Just Baseball report,
cut at a sentence or word boundary, and every excerpt carries a link to the
source's page or names the source and list. The full text stays in
prospects.db. The served payloads are pipeline outputs (gitignored), so each
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


def _assert_linked_or_named(where: str, url, source, label):
    assert source, f"{where}: excerpt names no source"
    if url:
        assert re.match(r"^https://", url), f"{where}: bad link {url!r}"
    else:
        assert label, f"{where}: excerpt has neither a link nor a list name"


@pytest.mark.parametrize("name", [f"scout_reports_{i}.json" for i in range(8)]
                         + ["scout_reports.json"])
def test_scout_report_sidecar_serves_excerpts_only(name):
    doc = _load(name)
    n = 0
    for pk, by_src in doc.items():
        for src, entries in by_src.items():
            if src.startswith("_") or not isinstance(entries, list):
                continue
            for e in entries:
                txt = e.get("text") or ""
                assert len(txt) <= MAX, f"{name} {pk}/{src}: {len(txt)} chars served"
                _assert_linked_or_named(f"{name} {pk}/{src}", e.get("url"),
                                        e.get("source"), e.get("label"))
                n += 1
    assert n > 0, f"{name} carries no reports"


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
    for pk, src, tools in _draft_report_extras(doc):
        ex = (tools or {}).get("_extras") or {}
        if not ex.get("report"):
            continue
        assert len(ex["report"]) <= MAX, f"draft {pk}/{src}: {len(ex['report'])} chars"
        _assert_linked_or_named(f"draft {pk}/{src}", ex.get("report_url"),
                                ex.get("report_source"), ex.get("report_label"))
        n += 1
    assert n > 0


def test_overseas_board_serves_excerpts_only():
    doc = _load("overseas_timeseries.json")
    for lg in doc.get("leagues") or []:
        for p in lg.get("prospects") or []:
            for src, tools in (p.get("tool_grades") or {}).items():
                ex = (tools or {}).get("_extras") or {}
                if ex.get("report"):
                    assert len(ex["report"]) <= MAX, (p.get("player_key"), src)
                    _assert_linked_or_named(f"overseas {p.get('player_key')}/{src}",
                                            ex.get("report_url"), ex.get("report_source"),
                                            ex.get("report_label"))


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
                                rep.get("label"))
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


def test_copy_states_the_excerpt_limit():
    import build_site as B
    page = B.build_sources()
    assert f"at most {MAX} characters" in page
    assert "full text" not in page.split('id="api"')[0]
    gl = (ROOT / "assets" / "glossary.js").read_text(encoding="utf-8")
    assert f"at most {MAX} characters" in gl
