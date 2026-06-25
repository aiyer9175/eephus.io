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
