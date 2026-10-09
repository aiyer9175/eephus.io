# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""PROSPX copy and claims pass (DISPLAY_prospx, quality audit 2026-10-02 QPRC03 to
QPRC16 and the site-pass notes).

Before the pass the page served V1 wording on V2 grades ('outcome-grounded' in the
sort menu, headers, badge tooltips, card surplus labels and the meta description),
starred the larger of two point estimates in the Debuted track record, promised a
recalibration 'in the review queue' that the registry rejected, printed
'normalized grade not in this payload' on every per-source hover, printed a zero
eFV gap as a bare '0', and printed 'None FB', '42th percentile', 'high confidence'
(a count of ETA inputs), 'elevated' and a past overseas season with no marker. Each
test pins one repair in the page source.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
PAGE = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")


def _fn(name: str, span: int = 6000) -> str:
    i = PAGE.index(f"function {name}(")
    return PAGE[i:i + span]


def test_qprc03_v2_surfaces_drop_the_v1_wording():
    head = PAGE[:PAGE.index("<body")]
    assert "outcome-grounded" not in head  # meta, og and twitter descriptions
    assert '<option value="xfv">eFV (consensus order reordered by drivers)</option>' in PAGE
    assert "our outcome-grounded ranking" not in PAGE
    assert 'title="eFV - our outcome-grounded Future Value' not in PAGE
    assert "SHAPE of the modeled eFV outcome" not in PAGE
    tip = _fn("efvTooltip", 1500)
    # COPY_3 (P3): the V2 badge tooltip carries the row's numbers; the method line
    # prints once, in the eFV column header.
    assert "efvIsV2(x) ? `eFV ${efvGradeDisplay(x)} (V2)`" in tip
    assert "outcome-grounded" not in tip
    assert "the consensus FV order within each side, reordered by admitted drivers" in PAGE
    assert '"eFV V2 · consensus order reordered by drivers"' in PAGE


def test_qprc04_track_record_marks_no_winner_and_names_v1():
    td = _fn("_efvTrkWinTd", 400)
    assert "★" not in td
    bars = _fn("_efvTrackBars", 2500)
    assert "★" not in bars and "win" not in bars.split("return `")[1]
    assert "the better grade starred" not in PAGE
    assert "eFV V1 (graduates' locked grade) vs consensus FV" in PAGE


def test_qprc05_calibration_caption_states_the_failed_gates():
    assert "Honest read" not in PAGE
    assert "review queue" not in PAGE
    assert "the served distribution is uncalibrated" in PAGE


def test_qprc06_no_per_source_hover_promise_for_a_missing_field():
    assert "normalized grade not in this payload" not in PAGE
    assert "Hover a row for published vs normalized vs weight" not in PAGE


def test_qprc07_zero_gap_prints_as_plus_minus_zero():
    fn = _fn("efvDeltaText", 200)
    assert 'd === 0 ? "±0"' in fn
    assert "eFV - consensus ${dtxt}" in PAGE


def test_qprc10_baseball_america_key_has_a_label_and_footer_separator():
    labels = PAGE[PAGE.index("const SOURCE_LABELS = {"):][:400]
    assert 'baseballamerica: "Baseball America"' in labels
    assert '${sourceBadge && publishingTxt ? " · " : ""}' in PAGE


def test_qprc11_quick_read_and_percentile_copy():
    assert '_fgExtras.fb_type !== "None"' in PAGE
    assert 'ex.fb_type !== "None"' in PAGE
    assert not re.search(r"\}th(?![a-z])", PAGE)  # no template ordinal like ${pct}th
    o = _fn("_ord", 400)
    assert '{ 1: "st", 2: "nd", 3: "rd" }' in o and "t >= 11 && t <= 13" in o
    assert "too few to tier vs the MLB pool" not in PAGE
    assert ':"")+(m.st?")":"")' not in PAGE  # the unbalanced stabilizes paren


def test_qprc12_consensus_values_print_on_the_grade_scale():
    assert "Consensus ${fvCeil(consensusVal)}" in PAGE
    assert "${fvCeil(td.first)}" in PAGE and "${fvCeil(td.last)}" in PAGE
    pill = _fn("tradeValuePillHTML", 2000)
    assert "toFixed(1)\n" not in pill and "at FV ?" not in pill
    assert 'month: "short", year: "numeric"' in PAGE


def test_qprc13_and_qprc16_labels():
    assert "Conviction board" not in PAGE.replace("// Conviction board", "")
    assert "Largest eFV - consensus gaps" in PAGE
    assert "elevated bust risk" not in PAGE
    assert "the full tracked board · eFV, consensus FV" in PAGE


def test_qprc14_eta_tier_prints_as_an_input_count():
    assert "} confidence`" not in PAGE
    assert "' confidence'" not in PAGE
    assert "${escapeHtml(eta.confidence)} confidence" not in PAGE
    fn = _fn("_etaInputs", 300)
    assert '"3+ input signals"' in fn and '"2 input signals"' in fn


def test_qprc15_section_rows_print_no_star_odds_and_name_the_signing_grade():
    assert "the production grade from his MiLB line or the signing grade" in PAGE
    cell = _fn("makeStarOddsCell", 600)
    assert "inProvSection(p)" in cell


def test_sitepass_spotlights_prints_the_owner_decision():
    assert "stays up pending the owner's decision" not in PAGE
    assert "the owner kept it on 2026-10-01" in PAGE


def test_sitepass_time_machine_note_says_what_the_ranking_reads():
    fn = _fn("_tmRenderControls", 20000)
    assert "ranked by consensus FV." not in fn
    assert "ranked and graded by the point-in-time eFV" in fn


def test_sitepass_overseas_marks_a_past_season_line():
    assert "function _ovLeagueSeason(lg)" in PAGE
    assert "` · no ${lgCur} line`" in PAGE


def test_sitepass_level_filter_offers_no_empty_mlb_chip():
    assert 'data-filter-level="MLB"' not in PAGE
    ts = ROOT / "data" / "timeseries.json"
    if not ts.exists():
        pytest.skip("data/timeseries.json not built")
    d = json.loads(ts.read_text(encoding="utf-8"))
    players = d["players"] if isinstance(d, dict) else d
    n = sum(1 for p in players if (p.get("statline") or {}).get("level") == "MLB")
    assert n == 0, f"{n} board rows sit at MLB; restore the MLB level chip"


def test_sitepass_charts_lead_with_an_efv_axis():
    axes = PAGE[PAGE.index("const CHART_AXES = {"):][:1500]
    keys = re.findall(r'\{ key: "(\w+)"', axes)
    assert keys[:3] == ["age", "efv", "fv"]  # default Y is axes[1]: eFV
    assert 'label: "Consensus FV"' in axes


def test_display_trim_method_copy_sits_in_collapsed_how_blocks():
    # Above-the-fold prose on the eight tab views fell from 550 to 285 words (1280,
    # light); the method paragraphs moved into collapsed 'How this works' blocks.
    assert PAGE.count('<details class="px-how"><summary>How this works</summary>') >= 2
    assert "Pick a prospect group, then any two stats" not in PAGE
    assert "Journeymen past" not in PAGE
    assert "Each card shows its league + country flag" not in PAGE
    fn = _fn("renderSpotlightTrackRecord", 4000)
    assert '<details><summary class="str-head">' in fn and "</details>" in fn
