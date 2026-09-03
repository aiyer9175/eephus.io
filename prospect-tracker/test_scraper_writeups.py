# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Tests for prospect-writeup extraction across ESPN, Just Baseball, and
MLB Pipeline scrapers.

Each scraper now populates `tools._extras.report` with the prospect's
narrative scout-report prose. The harvester in `storage.py` carries
that prose through to `data/scout_reports.json`, which the frontend
renders in the per-source Scouting Reports tab strip.

These tests feed each scraper a minimal HTML/JSON fixture (via the
on-disk cache path the scrapers already check first) and assert:
  * The narrative reaches `_extras.report` when present and substantial.
  * The structured tool-grade text is stripped from the report.
  * Short/empty blurbs don't populate the field (`>60` char guard).
  * The 8000-char ceiling holds.

For the MLB Pipeline cleaner (`_clean_pipeline_writeup`), we also exercise
the pure function directly — it's the most intricate of the three since
the Apollo cache ships a mix of structured grades + escaped newlines +
embedded HTML.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import scrapers
from scrapers import (
    _clean_pipeline_writeup,
    scrape_espn_top100,
    scrape_just_baseball,
    scrape_mlb_pipeline,
)


# ---------------------------------------------------------------------------
# Shared helper — point CACHE_DIR at a tmpdir so the scrapers read our
# fixture HTML instead of hitting the network.
# ---------------------------------------------------------------------------

@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(scrapers, "CACHE_DIR", tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# ESPN
# ---------------------------------------------------------------------------

ESPN_FIXTURE = """
<html><body>
<div class="article-body">
  <h2>55 FV tier</h2>
  <h2>1. Roman Anthony, OF, Boston Red Sox</h2>
  <p><strong>Age: 19 | Bats: Left | Throws: Right</strong></p>
  <p><strong>Hit</strong>: 55/65<br />
  <strong>Game Power</strong>: 50/60<br />
  <strong>Raw Power</strong>: 60/70<br />
  <strong>Speed</strong>: 55/55<br />
  <strong>Fielding</strong>: 50/55<br />
  <strong>Throwing</strong>: 55/55</p>
  <p>Anthony posts elite contact rates with plus raw power that already
  shows up in games. Above-average runner who profiles in a corner OF
  spot long-term. Sources are split on whether the hit tool plays to
  a 70 grade, but everyone agrees the bat is the carrying tool.</p>
  <h2>2. Stub Player, SS, New York Yankees</h2>
  <p>too short</p>
  <h2>50. Edge Case, RHP, Tampa Bay Rays</h2>
  <p>Edge Case mirrors the rank-50 entries from in-season updates — a
  brief paragraph beneath the rank header. The scraper's `1 <= rank <= 100`
  gate must pass rank 50 unchanged so this player still emits a Snapshot.</p>
</div>
</body></html>
"""


def test_espn_extracts_writeup(cache_dir):
    (cache_dir / "espn_test_label.html").write_text(ESPN_FIXTURE,
                                                     encoding="utf-8")
    rows = scrape_espn_top100(
        url="http://example.invalid/espn",
        label="test_label",
        snap_date="2026-01-01",
    )
    assert rows, "expected at least one ESPN row"
    anthony = next((r for r in rows if "anthony" in r.player_key), None)
    assert anthony is not None
    extras = (anthony.tools or {}).get("_extras", {})
    report = extras.get("report")
    assert report, "Roman Anthony row should carry a writeup"
    # Rank-line prefix must be stripped — the report should not start
    # with "1. Roman Anthony, OF, Boston Red Sox".
    assert "1. Roman Anthony" not in report
    # Structured preamble (Age/Bats/Throws + tool grades) must be gone —
    # _parse_espn_tools already ingested those.
    assert "Age:" not in report
    assert "Bats:" not in report
    assert "Throws:" not in report
    assert "55/65" not in report  # Hit grade value
    assert "Game Power" not in report
    # Narrative survives intact.
    assert "elite contact rates" in report
    assert len(report) <= 8000


def test_espn_handles_high_rank_articles(cache_dir):
    # Regression guard for the rank-50 path — used by the 2026 in-season
    # top-50 article added to ESPN_INTERVALS. Confirms the gate +
    # rank-line regex pass rank 50 unchanged.
    (cache_dir / "espn_test_label.html").write_text(ESPN_FIXTURE,
                                                     encoding="utf-8")
    rows = scrape_espn_top100(
        url="http://example.invalid/espn",
        label="test_label",
        snap_date="2026-01-01",
    )
    edge = next((r for r in rows if "edge_case" in r.player_key), None)
    assert edge is not None, (
        f"rank-50 entry didn't produce a Snapshot — "
        f"got keys {[r.player_key for r in rows]}"
    )
    assert edge.rank == 50
    extras = (edge.tools or {}).get("_extras", {}) if edge.tools else {}
    assert "report" in extras, "rank-50 entry should still carry a writeup when prose exists"


def test_espn_skips_short_blurbs(cache_dir):
    (cache_dir / "espn_test_label.html").write_text(ESPN_FIXTURE,
                                                     encoding="utf-8")
    rows = scrape_espn_top100(
        url="http://example.invalid/espn",
        label="test_label",
        snap_date="2026-01-01",
    )
    stub = next((r for r in rows if "stub" in r.player_key), None)
    assert stub is not None
    extras = (stub.tools or {}).get("_extras", {}) if stub.tools else {}
    # "too short" is <60 chars → must NOT have a report.
    assert "report" not in extras


# ---------------------------------------------------------------------------
# Just Baseball
# ---------------------------------------------------------------------------

JB_FIXTURE = """
<html><body>
<section class="toc-list__entry">
  <h2>1. Roman Anthony - OF - Boston Red Sox</h2>
  <figure class="wp-block-table"><table>
    <tr><th>Hit</th><th>Power</th><th>Run</th><th>Field</th><th>Arm</th><th>FV</th></tr>
    <tr><td>55/60</td><td>50/65</td><td>55/55</td><td>50/55</td><td>50/50</td><td>55</td></tr>
  </table></figure>
  <p>Anthony's swing decisions stand out — he posts elite contact rates
  with a willingness to take a walk. The raw power has continued to
  tick up year over year.</p>
  <p>Defensively he profiles in a corner. Average runner with average
  arm, both of which play up due to instincts.</p>
</section>
<section class="toc-list__entry">
  <h2>2. Bare Section - SS - NYY</h2>
  <figure class="wp-block-table"><table>
    <tr><th>Hit</th></tr><tr><td>40/45</td></tr>
  </table></figure>
</section>
</body></html>
"""


def test_just_baseball_extracts_writeup_from_paragraphs(cache_dir):
    (cache_dir / "jb_test_label.html").write_text(JB_FIXTURE, encoding="utf-8")
    rows = scrape_just_baseball(
        url="http://example.invalid/jb",
        label="test_label",
        snap_date="2026-01-01",
    )
    assert rows, "expected at least one JB row"
    anthony = next((r for r in rows if "anthony" in r.player_key), None)
    assert anthony is not None
    extras = (anthony.tools or {}).get("_extras", {})
    report = extras.get("report")
    assert report, "Anthony row should carry a writeup"
    # Table contents must NOT leak into prose.
    assert "55/60" not in report
    assert "Hit" not in report or "hit tool" in report.lower()
    # Paragraph breaks preserved.
    assert "\n\n" in report
    assert "elite contact rates" in report
    assert "Average runner" in report


def test_just_baseball_no_prose_no_report(cache_dir):
    (cache_dir / "jb_test_label.html").write_text(JB_FIXTURE, encoding="utf-8")
    rows = scrape_just_baseball(
        url="http://example.invalid/jb",
        label="test_label",
        snap_date="2026-01-01",
    )
    bare = next((r for r in rows if "bare_section" in r.player_key), None)
    assert bare is not None
    extras = (bare.tools or {}).get("_extras", {}) if bare.tools else {}
    assert "report" not in extras


# ---------------------------------------------------------------------------
# MLB Pipeline — pure-function cleaner
# ---------------------------------------------------------------------------

class TestCleanPipelineWriteup:
    def test_strips_scouting_grades_line(self):
        bio = (
            "Scouting grades: Hit: 55 | Power: 60 | Run: 45 | Arm: 50 | "
            "Field: 55 | Overall: 60\\nAnthony's bat is the carrying "
            "tool. He posts elite contact and plus raw power."
        )
        out = _clean_pipeline_writeup(bio)
        assert out is not None
        assert "Scouting grades" not in out
        assert "Overall: 60" not in out
        assert "carrying tool" in out

    def test_unescapes_html_entities(self):
        bio = "Scouting grades: Overall: 55\\nHe&#39;s a plus runner &amp; defender."
        out = _clean_pipeline_writeup(bio)
        assert out is not None
        assert "He's a plus runner & defender." in out
        assert "&#39;" not in out
        assert "&amp;" not in out

    def test_strips_html_tags(self):
        bio = "Scouting grades: Overall: 55\\n<p>Pure prose without <em>any</em> tags surviving.</p>"
        out = _clean_pipeline_writeup(bio)
        assert out is not None
        assert "<p>" not in out
        assert "<em>" not in out
        assert "Pure prose without any tags surviving" in out

    def test_preserves_paragraph_breaks(self):
        bio = (
            "Scouting grades: Overall: 60\\nFirst paragraph here.\\n\\n"
            "Second paragraph after a blank line."
        )
        out = _clean_pipeline_writeup(bio)
        assert out is not None
        assert "\n\n" in out

    def test_empty_or_only_grades_returns_none(self):
        bio = "Scouting grades: Hit: 50 | Overall: 55"
        out = _clean_pipeline_writeup(bio)
        # Nothing left after stripping the grades line.
        assert out is None or out == ""

    def test_handles_none_input(self):
        assert _clean_pipeline_writeup(None) is None
        assert _clean_pipeline_writeup("") is None


# ---------------------------------------------------------------------------
# MLB Pipeline — full scraper with a minimal Apollo-cache fixture
# ---------------------------------------------------------------------------

# Pipeline parses an Apollo Client cache that's HTML-escaped inside the
# page body. We provide a minimal cache with one RankedPlayerEntity, one
# Person, and one Team — the scraper handles _apollo_entities walking +
# the bio_text extraction internally.
# Apollo cache is shipped as compact JSON inside a script tag — the
# scraper's regex anchors on the literal `{"__typename":"RankedPlayerEntity",`
# pattern with no whitespace, so the fixture mirrors that compact shape.
PIPELINE_FIXTURE = (
    '<html><body><script id="__APOLLO_CACHE__">{'
    '"Team:111":{"__typename":"Team","id":111,"name":"Boston Red Sox","parentOrgName":null},'
    '"Person:9999":{"__typename":"Person","id":9999,"useName":"Roman","useLastName":"Anthony","activeRoster":{"__ref":"Team:111"}},'
    '"RankedPlayerEntity:1":{"__typename":"RankedPlayerEntity","rank":1,'
    '"player":{"__ref":"Person:9999"},"position":"OF",'
    '"prospectBio":[{"contentText":'
    '"Scouting grades: Hit: 55 | Power: 60 | Run: 55 | Arm: 50 | Field: 55 | Overall: 60\\\\n'
    'Anthony has emerged as one of the top hitters in the minors with elite contact and plus raw power. The bat is the carrying tool and projects to play in the heart of an MLB lineup."'
    ',"contentTitle":"2026"}]}'
    '}</script></body></html>'
)


def test_mlb_pipeline_extracts_writeup(cache_dir):
    (cache_dir / "mlb_pipeline_2026_top100.html").write_text(
        PIPELINE_FIXTURE, encoding="utf-8"
    )
    rows = scrape_mlb_pipeline(
        url="http://example.invalid/pipeline",
        label="2026 top 100",
        snap_date="2026-01-01",
        year=2026,
    )
    assert rows, "expected at least one Pipeline row"
    anthony = next((r for r in rows if "anthony" in r.player_key), None)
    assert anthony is not None, f"got {[r.player_key for r in rows]}"
    extras = (anthony.tools or {}).get("_extras", {})
    report = extras.get("report")
    assert report, "Anthony row should carry a writeup"
    # Structured grades line must be gone.
    assert "Scouting grades" not in report
    assert "Overall: 60" not in report
    # Narrative survives.
    assert "carrying tool" in report
    assert "elite contact" in report
    # FV was still extracted correctly.
    assert anthony.fv == 60
    assert len(report) <= 8000


# ---------------------------------------------------------------------------
# 8000-char ceiling — exercise the cap across all three scrapers via the
# Pipeline cleaner (other two share the same `[:8000]` slice).
# ---------------------------------------------------------------------------

def test_pipeline_cleaner_respects_8000_char_cap_at_scraper_layer(cache_dir):
    long_paragraph = "lorem ipsum dolor sit amet " * 600  # ~16,200 chars
    fixture = (
        "<html><body>"
        '<script>{'
        '"Team:111":{"__typename":"Team","id":111,"name":"Boston Red Sox","parentOrgName":null},'
        '"Person:9999":{"__typename":"Person","id":9999,"useName":"Long","useLastName":"Writeup","activeRoster":{"__ref":"Team:111"}},'
        '"RankedPlayerEntity:1":{"__typename":"RankedPlayerEntity",'
        '"rank":1,"player":{"__ref":"Person:9999"},"position":"OF",'
        '"prospectBio":[{"contentText":"Scouting grades: Overall: 50\\\\n'
        + long_paragraph
        + '","contentTitle":"2026"}]}}'
        "</script></body></html>"
    )
    (cache_dir / "mlb_pipeline_2026_top100.html").write_text(
        fixture, encoding="utf-8"
    )
    rows = scrape_mlb_pipeline(
        url="http://example.invalid/pipeline",
        label="2026 top 100",
        snap_date="2026-01-01",
        year=2026,
    )
    long_row = next((r for r in rows if "writeup" in r.player_key), None)
    assert long_row is not None
    extras = (long_row.tools or {}).get("_extras", {})
    report = extras.get("report")
    assert report is not None
    assert len(report) <= 8000


# ---------------------------------------------------------------------------
# ESPN, 2026 Midseason layout (published 2026-08-20, wired 2026-08-30).
# Rank lines carry an ", Age: x.y, Level: lvl" tail, the team (sometimes the
# name) is wrapped in an <a>, inline <aside> modules (Editor's Picks, an
# inline-track promo with its own <h2>/<p>, an inline-photo figure with a
# credit) sit between rank lines and their prose, ranks in the lower tiers
# are <br/>-packed with no commentary, and the May 2026 edition's
# "(Previous: N)" tail is covered by the same splitter. Before the fix 15 of
# 18 stored reports began with their own header line, one carried the
# Editor's Picks module, and 32 preseason reports were empty.
# ---------------------------------------------------------------------------

import json  # noqa: E402  (probe fixtures below)

ESPN_2026_MIDSEASON_FIXTURE = """
<html><body>
<div class="article-body">
<p>Intro paragraph about the update.</p>
<hr><h2><strong>60 FV tier</strong></h2>
<img alt="" class="floatleft" src="x.png" width="30">
<p><strong>1. Jesús Made, SS, <a href="/mlb/team/_/name/mil/milwaukee-brewers">Milwaukee Brewers</a>, Age: 19.3, Level: Double-A</strong></p>
<aside class="inline float-r inline-track"><h2 class="img-title">Prospect tracker promo</h2><p>Follow every move.</p></aside>
<p>Made's grip on the top spot isn't as strong as it was in <a href="/x">May</a>, but he's still
got it in this update. He hit .301/.405/.471 with a .792 OPS in July. He has a tremendous
combination of bat control, raw power, speed, defense and instincts.</p>
<hr><img alt="" class="floatleft" src="x.png" width="30">
<p><strong>2. <a href="https://www.espn.com/mlb/player/_/id/1/max-clark">Max Clark</a>, CF, Detroit Tigers, Age: 21.7, Level: MLB</strong></p>
<aside class="inline editorial float-r" data-behavior="article_related"><h2 class="editorial-title">Editor's Picks</h2><ul><li><a href="/mlb/story/_/id/1/x">Updated top 10 prospect rankings for all 30 MLB teams</a></li></ul></aside>
<p>Now that he's in the big leagues, I'll be interested to see how the power plays
against velocity that he rarely saw in Triple-A over a longer stretch.</p>
<hr><img alt="" class="floatleft" src="x.png" width="30">
<p><strong>3. Roch Cholowsky, SS, <a href="/mlb/team/_/name/chw/chicago-white-sox">Chicago White Sox</a>, Age: 21.4, Level: High-A</strong></p>
<img alt="" class="floatleft" src="x.png" width="30">
<p><strong>4. Grady Emerson, SS, Tampa Bay Rays, Age: 18.5, Level: Pro</strong></p>
<aside class="inline inline-photo full"><figure><picture><img src="p.jpg"></picture><figcaption><cite>AP Photo/Lindsey Wasson</cite></figcaption></figure></aside>
<p>Maybe it's a copout to put my top two draft picks back-to-back at the end of
this tier, but neither has played enough to change his predraft report yet.</p>
<hr><h2>55 FV tier</h2><p>5. Mike Sirota, CF, Los Angeles Dodgers, Age: 23.2, Level: Double-A<br />
6. Rainiel Rodriguez, C, <a href="/mlb/team/_/name/stl/st-louis-cardinals">St. Louis Cardinals</a>, Age: 19.6, Level: Double-A<br />
7. Luis Peña, SS, Milwaukee Brewers, Age: 19.8, Level: High-A</p>
<hr><h2>50 FV tier</h2><p>8. Colt Emerson, SS, Seattle Mariners (Previous: 6)<br />
9. Jamie Arnold, LHP, Athletics (Previous: NR)</p>
</div>
<div class="article-footer">footer</div>
</body></html>
"""


def _espn_rows(cache_dir, fixture, label):
    (cache_dir / f"espn_{label}.html").write_text(fixture, encoding="utf-8")
    return scrape_espn_top100(url=f"http://example.invalid/espn-{label}",
                              label=label, snap_date="2026-01-01")


def _espn_midseason_rows(cache_dir):
    return _espn_rows(cache_dir, ESPN_2026_MIDSEASON_FIXTURE, "test_midseason")


def _report_of(row):
    return ((row.tools or {}).get("_extras") or {}).get("report")


def test_espn_2026_midseason_layout(cache_dir):
    rows = _espn_midseason_rows(cache_dir)
    by_rank = {r.rank: r for r in rows}
    assert sorted(by_rank) == list(range(1, 10)), [r.rank for r in rows]

    # Tier headers reset FV for the block beneath, in both <h2><strong> and
    # bare <h2> forms; the <br/>-packed tiers ride the same tier.
    assert [by_rank[i].fv for i in range(1, 10)] == [60, 60, 60, 60, 55, 55, 55, 50, 50]

    # Orgs canonical whether the team was wrapped in an <a> (1, 3, 6) or
    # bare (2, 4, 5, 7). (canonical_org substring-matches, so this also held
    # on the unsplit string; the split itself is pinned by
    # test_split_espn_rank_tail_forms.)
    assert [by_rank[i].org for i in range(1, 8)] == [
        "MIL", "DET", "CHW", "TBR", "LAD", "STL", "MIL"]
    assert by_rank[1].position == "SS" and by_rank[2].position == "CF"
    assert by_rank[1].player_name == "Jesús Made"
    assert by_rank[2].player_name == "Max Clark"       # name inside the <a>
    assert by_rank[7].player_key == "luis_pena"

    # The rank-line tail is parsed off the team but NOT persisted: an
    # _extras-only tools dict would make storage/prospx/org_tendencies count
    # ESPN as a tool-grade publisher on rows with no grade. Bare rows keep
    # tools=None exactly as before the change.
    for r in rows:
        ex = (r.tools or {}).get("_extras") or {}
        for k in ("espn_age", "espn_level", "espn_previous_rank", "age", "level"):
            assert k not in ex, (r.rank, k)
    for i in (3, 5, 6, 7, 8, 9):
        assert by_rank[i].tools is None, (i, by_rank[i].tools)


def test_espn_2026_midseason_reports_are_clean(cache_dir):
    rows = _espn_midseason_rows(cache_dir)
    by_rank = {r.rank: r for r in rows}

    # Wrapped team (1) and wrapped name (2): header line stripped, prose kept.
    r1, r2 = _report_of(by_rank[1]), _report_of(by_rank[2])
    assert r1 and r1.startswith("Made's grip on the top spot"), r1
    assert r2 and r2.startswith("Now that he's in the big leagues"), r2
    for rep in (r1, r2):
        assert "Age:" not in rep and "Level:" not in rep
        assert not rep[:1].isdigit(), rep[:40]
    assert "Milwaukee Brewers" not in r1

    # Closed-tag gaps are healed ("in May , but" -> "in May, but") without
    # gluing leading-dot stat lines ("hit .301/.405/.471", ".792 OPS").
    assert "in May, but" in r1, r1
    assert "hit .301/.405/.471" in r1 and "a .792 OPS" in r1, r1
    assert " ," not in r1 and " ." not in r1.replace(" .3", "").replace(" .7", "")

    # Every inline <aside> shape is gone: promo (1), Editor's Picks (2),
    # photo credit (4).
    assert "Prospect tracker promo" not in r1 and "Follow every move" not in r1
    assert "Editor's Picks" not in r2 and "top 10 prospect" not in r2
    r4 = _report_of(by_rank[4])
    assert r4 and r4.startswith("Maybe it's a copout"), r4
    assert "AP Photo" not in r4 and "Lindsey Wasson" not in r4

    # The next tier's header is a boundary, not the tail of the last report.
    assert not r4.rstrip().endswith("FV tier"), r4[-40:]
    assert "55 FV tier" not in r4

    # A rank line with nothing beneath it is not a report (used to survive
    # the >60-char guard as "17. Roch Cholowsky, SS, Chicago White Sox , ...").
    assert _report_of(by_rank[3]) is None

    # <br/>-packed list rows have no commentary and therefore no report.
    for i in (5, 6, 7, 8, 9):
        assert _report_of(by_rank[i]) is None, (i, _report_of(by_rank[i]))


def test_espn_previous_rank_tail_is_split_off_the_team(cache_dir):
    rows = _espn_midseason_rows(cache_dir)
    by_rank = {r.rank: r for r in rows}
    assert by_rank[8].org == "SEA" and by_rank[8].tools is None
    assert by_rank[9].org == "ATH" and by_rank[9].tools is None


def test_split_espn_rank_tail_forms():
    from scrapers import _split_espn_rank_tail as split
    assert split("Milwaukee Brewers") == ("Milwaukee Brewers", {})
    assert split("Milwaukee Brewers, Age: 19.3, Level: Double-A") == (
        "Milwaukee Brewers", {"espn_age": 19.3, "espn_level": "Double-A"})
    assert split("Athletics, Age: 19.9, Level: Double-A") == (
        "Athletics", {"espn_age": 19.9, "espn_level": "Double-A"})
    assert split("St. Louis Cardinals, Age: 22, Level: Triple-A") == (
        "St. Louis Cardinals", {"espn_age": 22.0, "espn_level": "Triple-A"})
    assert split("Seattle Mariners (Previous: 6)") == (
        "Seattle Mariners", {"espn_previous_rank": 6})
    assert split("Athletics (Previous: NR)") == (
        "Athletics", {"espn_previous_rank": None})
    assert split("Boston Red Sox, Age: 20.7") == (
        "Boston Red Sox", {"espn_age": 20.7})
    assert split("Los Angeles Dodgers") == ("Los Angeles Dodgers", {})


def test_espn_unclosed_aside_does_not_swallow_rank_lines(cache_dir):
    fixture = """
<html><body><div class="article-body">
<h2>60 FV tier</h2>
<p><strong>1. First Guy, SS, Detroit Tigers, Age: 20.0, Level: Double-A</strong></p>
<aside class="inline editorial float-r"><h2>Editor's Picks</h2><ul><li>never closed
<p>Prose for First Guy that is long enough to count as a scouting report for him.</p>
<p><strong>2. Second Guy, RHP, Seattle Mariners, Age: 21.0, Level: Triple-A</strong></p>
<p>Prose for Second Guy that is also long enough to count as a scouting report.</p>
<aside class="inline float-r inline-track"><h2>Promo</h2></aside>
<p><strong>3. Third Guy, C, Boston Red Sox, Age: 19.0, Level: High-A</strong></p>
</div></body></html>
"""
    rows = _espn_rows(cache_dir, fixture, "test_unclosed")
    assert [r.rank for r in rows] == [1, 2, 3], [(r.rank, r.player_name) for r in rows]
    assert [r.fv for r in rows] == [60, 60, 60]
    r2 = _report_of(rows[1])
    assert r2 and r2.startswith("Prose for Second Guy"), r2


def test_espn_existing_preseason_layout_still_parses(cache_dir):
    # The original <h2> layout with Age/Bats/Throws + tool lines on the
    # following paragraphs must be unaffected by the tail splitter.
    (cache_dir / "espn_test_label.html").write_text(ESPN_FIXTURE, encoding="utf-8")
    rows = scrape_espn_top100(url="http://example.invalid/espn",
                              label="test_label", snap_date="2026-01-01")
    anthony = next(r for r in rows if "anthony" in r.player_key)
    assert anthony.org == "BOS"
    ex = anthony.tools["_extras"]
    assert "espn_age" not in ex and "espn_level" not in ex
    assert "elite contact rates" in ex["report"]


# ---------------------------------------------------------------------------
# ESPN structured tool lines. The generic label capture used to start at the
# letters preceding a label ("Throws: Right   Hit: 45/50" read as the label
# "right   hit") and dropped the Hit grade for 14 of the 15 preseason 2026
# hitters that carried a block; "Four-Seam Fastball" never matched at all.
# A known-label alternation then over-corrected ("Body Control: 30/40" graded
# as Command); the whole normalised label must be known.
# ---------------------------------------------------------------------------

def test_espn_tool_lines_survive_preceding_bio_text():
    from scrapers import _parse_espn_tools
    block = ("1. Konnor Griffin, SS, Pittsburgh Pirates Age: 19 | Bats: Right | "
             "Throws: Right   Hit : 45/50 Game Power : 50/65 Raw Power : 60/70 "
             "Speed : 70/70 Fielding : 45/55 Throwing : 65/65 Reminds me of : "
             "Fernando Tatis Jr.")
    tools = _parse_espn_tools(block)
    assert tools == {"hit": 50, "game_pwr": 65, "raw_pwr": 70, "speed": 70,
                     "field": 55, "throw": 65}


def test_espn_tool_lines_pitch_names():
    from scrapers import _parse_espn_tools
    block = ("Age: 21 | Bats: Left | Throws: Left   Four-Seam Fastball : 55/60 "
             "Sweeper : 55/65 Splitter : 70/70 Cutter : 45/50 Command : 40/50")
    assert _parse_espn_tools(block) == {"fb": 60, "sl": 65, "ch": 70, "ct": 50,
                                        "cmd": 50}
    # Sinker rides the fb slot, and the first fastball-family line wins.
    assert _parse_espn_tools("Sinker: 60/70 Four-Seam Fastball: 40/45")["fb"] == 70


def test_espn_tool_lines_unknown_multiword_labels_are_not_graded():
    from scrapers import _parse_espn_tools
    block = ("Fastball: 60/70 Slider: 55/65 Changeup: 40/50 Body Control: 30/40 "
             "Bat Speed: 70/70 Command: 45/50")
    tools = _parse_espn_tools(block)
    assert tools == {"fb": 70, "sl": 65, "ch": 50, "cmd": 50}, tools
    assert "speed" not in tools


def test_espn_tool_lines_game_power_not_overwritten_by_bare_power():
    from scrapers import _parse_espn_tools
    tools = _parse_espn_tools("Hit: 50/55 Game Power: 50/60 Power: 30/30")
    assert tools["game_pwr"] == 60


def test_espn_preseason_report_strips_pitch_lines(cache_dir):
    fixture = """
<html><body><div class="article-body">
<h2><strong>60 FV tier</strong></h2>
<h2><strong>1. <a href="/p">Kade Anderson</a>, LHP, <a href="/t">Seattle Mariners</a></strong></h2>
<p><strong>Age: 22 | Bats: Left | Throws: Left</strong></p>
<p><strong>Four-Seam Fastball</strong>: 55/60<br />
<strong>Sweeper</strong>: 55/65<br />
<strong>Changeup</strong>: 50/55<br />
<strong>Command</strong>: 45/55</p>
<p><strong>Reminds me of</strong>: A lefty <a href="/x">Somebody</a>, with better feel.
Anderson's stuff and command have both been better than expected this year and
the delivery repeats without effort.</p>
</div></body></html>
"""
    rows = _espn_rows(cache_dir, fixture, "test_pitch")
    assert len(rows) == 1
    r = rows[0]
    assert r.org == "SEA" and r.fv == 60
    assert {k: v for k, v in r.tools.items() if k != "_extras"} == {
        "fb": 60, "sl": 65, "ch": 55, "cmd": 55}
    report = r.tools["_extras"]["report"]
    assert report.startswith("Reminds me of: A lefty Somebody, with better feel."), report
    assert "Four-Seam" not in report and "Age:" not in report
    assert " ," not in report and " :" not in report


# ---------------------------------------------------------------------------
# ESPN probe: feed leg (short window, Akamai 403s any Mozilla/* UA) plus two
# site-search legs (long window). _fetch must honour a headers override
# without touching the project HEADERS used everywhere else.
# ---------------------------------------------------------------------------

def test_fetch_headers_override(monkeypatch, cache_dir):
    captured = {}

    class _Resp:
        status_code = 200
        text = '{"articles": []}'

    def fake_get(url, headers=None, timeout=None):
        captured["headers"] = dict(headers or {})
        return _Resp()

    monkeypatch.setattr(scrapers.requests, "get", fake_get)
    monkeypatch.setattr(scrapers, "RATE_LIMIT_SECONDS", 0)
    fr = scrapers._fetch("http://example.invalid/feed", "espn_news_feed",
                         force=True, accept_json=True,
                         headers=scrapers.ESPN_FEED_HEADERS)
    assert fr.status == 200
    assert "User-Agent" not in captured["headers"]
    assert captured["headers"]["Accept"] == "application/json"
    # Default path still sends the project UA.
    scrapers._fetch("http://example.invalid/other", "other_key", force=True)
    assert captured["headers"]["User-Agent"] == scrapers.HEADERS["User-Agent"]


def test_probe_cache_keys_refresh_within_the_day():
    # 24h against a fixed nightly cron skipped the network every other night.
    assert scrapers._cache_ttl_for_key("espn_news_feed") <= 6 * 3600
    for key, _url in scrapers.ESPN_SEARCH_QUERIES:
        assert scrapers._cache_ttl_for_key(key) <= 6 * 3600, key


_FEED_BODY = json.dumps({"articles": [
    {"id": 11111111, "headline": "Twins call up top prospect Jenkins",
     "links": {"web": {"href": "https://www.espn.com/mlb/story/_/id/11111111/x"}},
     "published": "2026-08-30T00:00:00Z"},
    {"id": 22222222, "headline": "Updated 2026 MLB top 100 prospect rankings: Made, Arias",
     "links": {"web": {"href": "https://www.espn.com/mlb/story/_/id/22222222/y?ex=1"}},
     "published": "2026-08-30T01:00:00Z"},
]})

_SEARCH_BODY = json.dumps({"results": [
    {"type": "clips", "contents": [{"id": "9", "type": "clip",
                                    "displayName": "prospect rankings clip",
                                    "link": {"web": "https://www.espn.com/mlb/video/9"}}]},
    {"type": "article", "contents": [
        {"id": "22222222", "type": "story",
         "displayName": "Updated 2026 MLB top 100 prospect rankings: Made, Arias",
         "link": {"web": "https://www.espn.com/mlb/story/_/id/22222222/y"},
         "date": "2026-08-20T19:07:00.000+00:00", "byline": "Kiley McDaniel"},
        {"id": "33333333", "type": "story",
         "displayName": "2026 top 50 MLB prospect rankings update: Made, Emerson",
         "link": {"web": "https://www.espn.com/mlb/story/_/id/33333333/z"},
         "date": "2026-05-21T16:10:49.000+00:00", "byline": "Kiley McDaniel"},
        {"id": "44444444", "type": "story",
         "displayName": "Top NHL prospect rankings: Schaefer, Hagens",
         "link": {"web": "https://www.espn.com/nhl/story/_/id/44444444/n"},
         "date": "2025-10-30T14:03:51.000+00:00", "byline": "Rachel Kryshak"},
        {"id": "55555555", "type": "headlinenews",
         "displayName": "Sources: MLB suspends prospect over false rankings claim",
         "link": {"web": "https://www.espn.com/mlb/story/_/id/55555555/h"},
         "date": "2026-08-28T23:05:21.000+00:00", "byline": "ESPN News Services"},
        {"id": "48825315", "type": "story",
         "displayName": "2026 top 50 MLB prospect rankings update (already wired)",
         "link": {"web": "https://www.espn.com/mlb/story/_/id/48825315/w"},
         "date": "2026-05-21T16:10:49.000+00:00", "byline": "Kiley McDaniel"},
    ]},
]})

_SEARCH_KEYS = tuple(k for k, _u in scrapers.ESPN_SEARCH_QUERIES)


def _fake_fetch_factory(feed_status, search_status):
    """Fake _fetch. Contract checks are RECORDED into .violations and
    asserted by the test afterwards: an assert inside the fake would be
    swallowed by the probe's per-leg except clause."""
    def fake_fetch(url, cache_key, force=False, accept_json=False, headers=None):
        if headers is not scrapers.ESPN_FEED_HEADERS or not accept_json:
            fake_fetch.violations.append((cache_key, headers, accept_json))
        fake_fetch.calls.append(cache_key)
        if cache_key == "espn_news_feed":
            return scrapers.FetchResult(body=_FEED_BODY if feed_status == 200 else "",
                                        status=feed_status, from_cache=False, url=url)
        if cache_key not in _SEARCH_KEYS:
            fake_fetch.violations.append(("unknown cache key", cache_key))
        return scrapers.FetchResult(body=_SEARCH_BODY if search_status == 200 else "",
                                    status=search_status, from_cache=False, url=url)
    fake_fetch.violations = []
    fake_fetch.calls = []
    return fake_fetch


def _search_legs(value):
    return {"search:" + k.replace("espn_search_", "", 1): value for k in _SEARCH_KEYS}


def test_espn_probe_sends_feed_headers_on_every_leg(monkeypatch):
    fake = _fake_fetch_factory(200, 200)
    monkeypatch.setattr(scrapers, "_fetch", fake)
    out = scrapers.probe_espn_new_prospect_article(force=True)
    assert fake.violations == []
    assert fake.calls == ["espn_news_feed", *_SEARCH_KEYS]
    assert "error" not in out and "User-Agent" not in scrapers.ESPN_FEED_HEADERS


def test_espn_probe_search_leg_finds_old_articles_when_feed_is_403(monkeypatch):
    fake = _fake_fetch_factory(403, 200)
    monkeypatch.setattr(scrapers, "_fetch", fake)
    out = scrapers.probe_espn_new_prospect_article(force=True)
    assert fake.violations == []
    assert "error" not in out
    # 5 search hits per query, of which the NHL story and the headlinenews
    # item are dropped before counting: 3 MLB stories reach the filter.
    assert out["legs"] == {"feed": "HTTP 403", **_search_legs(3)}
    ids = [c["id"] for c in out["candidates"]]
    # Both ranking stories surface; NHL, headlinenews and the wired id do not.
    assert ids == ["22222222", "33333333"]
    assert out["candidates"][0]["byline"] == "Kiley McDaniel"
    assert out["candidates"][0]["published"].startswith("2026-08-20")
    # The failed leg is named in the one-line summary that reaches
    # ingest_health even though the probe as a whole is not an error.
    assert "feed=HTTP 403" in out["summary"] and "22222222" in out["summary"]


def test_espn_probe_feed_leg_alone_still_works(monkeypatch):
    fake = _fake_fetch_factory(200, 500)
    monkeypatch.setattr(scrapers, "_fetch", fake)
    out = scrapers.probe_espn_new_prospect_article(force=True)
    assert fake.violations == []
    assert "error" not in out
    assert out["legs"] == {"feed": 2, **_search_legs("HTTP 500")}
    assert [c["id"] for c in out["candidates"]] == ["22222222"]
    assert out["candidates"][0]["url"].endswith("/22222222/y")   # query stripped


def test_espn_probe_dedupes_across_legs(monkeypatch):
    fake = _fake_fetch_factory(200, 200)
    monkeypatch.setattr(scrapers, "_fetch", fake)
    out = scrapers.probe_espn_new_prospect_article(force=True)
    assert [c["id"] for c in out["candidates"]] == ["22222222", "33333333"]
    # checked counts UNIQUE ids: 2 feed + 3 search stories, 22222222 shared.
    assert out["checked"] == 4


def test_espn_probe_errors_only_when_all_legs_fail(monkeypatch):
    fake = _fake_fetch_factory(403, 403)
    monkeypatch.setattr(scrapers, "_fetch", fake)
    out = scrapers.probe_espn_new_prospect_article(force=True)
    assert out["candidates"] == [] and out["checked"] == 0
    assert out["error"].startswith("feed: HTTP 403; search:")
    assert out["summary"].startswith("all legs failed")


def test_espn_probe_skips_reviewed_ids(monkeypatch):
    # A McDaniel piece that was looked at and deliberately NOT wired (team
    # top-10s, farm-system rankings, 101-200 superlatives) must not be
    # re-flagged every run. An undated entry silences the id outright.
    monkeypatch.setattr(scrapers, "_fetch", _fake_fetch_factory(403, 200))
    monkeypatch.setattr(scrapers, "ESPN_PROBE_REVIEWED_IDS",
                        {"33333333": "test: reviewed, not a top-100 list"})
    out = scrapers.probe_espn_new_prospect_article(force=True)
    assert [c["id"] for c in out["candidates"]] == ["22222222"]


def test_espn_probe_reviewed_id_fires_again_after_an_in_place_rewrite(monkeypatch):
    # ESPN reuses ids when it rewrites an article: a dated ledger entry covers
    # editions up to that date only. 33333333 is dated 2026-05-21 in the
    # search fixture; reviewing it as of 2026-05-01 must NOT silence it,
    # reviewing it as of 2026-05-21 must.
    monkeypatch.setattr(scrapers, "_fetch", _fake_fetch_factory(403, 200))
    monkeypatch.setattr(scrapers, "ESPN_PROBE_REVIEWED_IDS",
                        {"33333333": "2026-05-01 reviewed the May 1 edition"})
    out = scrapers.probe_espn_new_prospect_article(force=True)
    assert [c["id"] for c in out["candidates"]] == ["22222222", "33333333"]
    monkeypatch.setattr(scrapers, "ESPN_PROBE_REVIEWED_IDS",
                        {"33333333": "2026-05-21 reviewed this edition"})
    out = scrapers.probe_espn_new_prospect_article(force=True)
    assert [c["id"] for c in out["candidates"]] == ["22222222"]
    from scrapers import _espn_reviewed_covers as covers
    assert covers(None, "2026-05-21T00:00:00Z") is False
    assert covers("no date here", "2026-05-21T00:00:00Z") is True
    assert covers("2026-05-21 x", None) is True


def test_espn_real_ledger_entries_are_dated():
    import re as _re
    for aid, entry in scrapers.ESPN_PROBE_REVIEWED_IDS.items():
        assert aid.isdigit(), aid
        assert _re.match(r"\d{4}-\d{2}-\d{2} ", entry), (aid, entry)


def test_espn_interval_outcomes_reports_every_wired_list(monkeypatch):
    # A wired interval that yields nothing must surface as (label, 0), not
    # vanish; a future-dated one is skipped; other sources do not count.
    monkeypatch.setattr(scrapers, "ESPN_INTERVALS", [
        ("http://x/a", "ESPN 2026 Preseason", "2026-01-27"),
        ("http://x/b", "ESPN 2026 Midseason", "2026-08-20"),
        ("http://x/c", "ESPN 2099 Preseason", "2099-01-01"),
    ])
    snaps = [
        scrapers.Snapshot(source="espn", snapshot_date="2026-01-27",
                          interval_label="ESPN 2026 Preseason", player_key="a",
                          player_name="A", position="SS", org="PIT", rank=1,
                          fv=60.0, status="active"),
        scrapers.Snapshot(source="espn", snapshot_date="2026-01-27",
                          interval_label="ESPN 2026 Preseason", player_key="b",
                          player_name="B", position="SS", org="PIT", rank=2,
                          fv=55.0, status="active"),
        scrapers.Snapshot(source="fangraphs", snapshot_date="2026-08-02",
                          interval_label="ESPN 2026 Midseason", player_key="c",
                          player_name="C", position="SS", org="PIT", rank=1,
                          fv=50.0, status="active"),
    ]
    assert scrapers.espn_interval_outcomes(snaps) == [
        ("ESPN 2026 Preseason", 2), ("ESPN 2026 Midseason", 0)]
    assert scrapers.espn_interval_outcomes([]) == [
        ("ESPN 2026 Preseason", 0), ("ESPN 2026 Midseason", 0)]
