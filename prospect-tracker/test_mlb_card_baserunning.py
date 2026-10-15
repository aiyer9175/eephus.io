# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""skills.br on the MLB player card (task EBR_2_BUILD_DARK; integration.md 3.1).

The block joins the Baserunning board by MLBAM in mlb_player_export._skill_index,
reaches hitter-side and two-way cards through _card_skills, and only while
baserunning_export.CARD_BASERUNNING_LIVE is on. The Hitting tab renders it as a
Baserunning section (no new tab): eBR and its parts on run bars, FanGraphs' BsR
and Savant's BRV as neutral rows, one line of counts and rates. Three layers:
fixtures through the index, the served artifact (skipped until it is baked with
the block), and the rendered tab through the card smoke prelude.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import baserunning_export as bre
import mlb_player_export as mpe
import test_projections_smoke as psmoke

ROOT = Path(__file__).parent
DATA = ROOT / "data"
BR_KEYS = {"season", "qualified", "ebr", "ebrSb", "ebrXb", "ebrDp", "sb", "cs", "pk", "sbPct", "attRate",
           "xbtPct", "gidpPct", "sprint", "sprintPct", "bsrFg", "brvSavant"}
# The raw bytes the block adds to data/mlb_player_detail.json. integration.md
# 3.1 estimated 100 KB for about 700 hitter cards; measured on the 2026
# preview (EBR_2_BUILD_DARK, 2026-10-15) the 17 fields above add 134,695 B
# over 659 hitter-side cards, 2.6 percent of the 5,129,325 B file, and no trim
# short of a positional encoding reaches 100 KB (parts at 1 dp, pickoffs
# dropped at zero, Att%, GIDP% and the season dropped still measure 100,597 B).
# The fields the design names are kept and the pin carries the measured size
# with headroom; the owner question is recorded in the task report.
BUDGET_RAW = 160 * 1024


def _write(d: Path, name: str, obj) -> None:
    (d / name).write_text(json.dumps(obj), encoding="utf-8")


_ROWS = [
    {"mlbam": 1, "qualified": True, "ebr": 15.589, "ebr_sb": 3.15, "ebr_xb": 6.929, "ebr_dp": 5.51, "sb": 41,
     "cs": 7, "pk": 1, "sb_pct": 0.854, "att_rate": 0.194, "xbt_pct": 0.545, "gidp_pct": 0.017, "sprint": 29.5,
     "sprint_pct": 95, "bsr": 8.2, "brv": 7.9, "x13": [8, 21], "lead_p": 11.8},
    {"mlbam": 2, "qualified": False, "ebr": 0.41, "ebr_sb": 0.3, "ebr_xb": 0.11, "ebr_dp": 0.0, "sb": 2, "cs": 0,
     "pk": 0, "sb_pct": None, "att_rate": None, "xbt_pct": None, "gidp_pct": None},
    {"mlbam": 3, "qualified": True, "ebr": None, "sb": 0, "cs": 0},
]


@pytest.fixture
def boards(tmp_path, monkeypatch):
    monkeypatch.setattr(mpe, "DATA_DIR", tmp_path)
    for name, key in (("hitter_leaderboards.json", "hitters"), ("bullpen_leaderboards.json", "relievers"),
                      ("starter_leaderboards.json", "starters"), ("defense_leaderboards.json", "fielders")):
        _write(tmp_path, name, {"season": 2026, key: []})
    _write(tmp_path, "leverage_leaderboards.json", {"season": 2026, "batters": [], "starters": []})
    _write(tmp_path, bre.OUT_NAME, {"season": 2026, "runners": _ROWS})
    return tmp_path


def test_the_block_is_absent_while_the_card_flag_is_off(boards, monkeypatch):
    monkeypatch.setattr(bre, "CARD_BASERUNNING_LIVE", False)
    idx = mpe._skill_index()
    assert not any("br" in v for v in idx.values()), idx


def test_the_block_carries_only_the_card_columns_and_drops_absent_ones(boards, monkeypatch):
    monkeypatch.setattr(bre, "CARD_BASERUNNING_LIVE", True)
    idx = mpe._skill_index()
    b = idx[1]["br"]
    assert set(b) == BR_KEYS, set(b) ^ BR_KEYS
    assert (b["ebr"], b["ebrSb"], b["ebrXb"], b["ebrDp"]) == (15.589, 3.15, 6.929, 5.51)
    assert (b["sb"], b["cs"], b["pk"], b["sbPct"], b["sprint"], b["sprintPct"]) == (41, 7, 1, 0.854, 29.5, 95)
    assert (b["bsrFg"], b["brvSavant"], b["season"], b["qualified"]) == (8.2, 7.9, 2026, True)
    assert "x13" not in b and "lead_p" not in b, "the by-base splits and leads stay on the board"
    thin = idx[2]["br"]
    assert thin["qualified"] is False and "sbPct" not in thin and "sprint" not in thin, thin
    assert 3 not in idx or "br" not in idx[3], "a row with no eBR carries no block"


def test_card_skills_hand_the_block_to_hitter_side_and_two_way_cards_only(boards, monkeypatch):
    monkeypatch.setattr(bre, "CARD_BASERUNNING_LIVE", True)
    idx = mpe._skill_index()
    assert "br" in mpe._card_skills(idx[1], is_pit=False, two_way=False)
    assert "br" in mpe._card_skills(idx[1], is_pit=False, two_way=True)
    assert "br" not in mpe._card_skills(idx[1], is_pit=True, two_way=False)
    assert "br" in mpe._card_skills(idx[1], is_pit=True, two_way=True)


def test_the_block_values_equal_the_boards_on_the_preview(monkeypatch):
    """The dark build's own board (the preview the exporter writes while the
    flag is off), read through the same join: every value on the card is the
    board's value, and the block stays under its raw budget."""
    src = ROOT / ".cache" / "baserunning" / "preview" / bre.OUT_NAME
    if not src.exists():
        pytest.skip("no baserunning preview on this machine")
    board = json.loads(src.read_text(encoding="utf-8"))
    tmp = ROOT / ".cache" / "baserunning" / "preview"
    monkeypatch.setattr(mpe, "DATA_DIR", tmp)
    monkeypatch.setattr(bre, "CARD_BASERUNNING_LIVE", True)
    idx = mpe._skill_index()
    rows = {int(r["mlbam"]): r for r in board["runners"] if r.get("ebr") is not None}
    assert rows and all("br" in idx[m] for m in rows)
    for m, r in rows.items():
        b = idx[m]["br"]
        assert b["ebr"] == r["ebr"] and b.get("bsrFg") == r.get("bsr") and b.get("sprint") == r.get("sprint")
    # The addition is measured over the cards that would carry the block (the
    # hitter-side cards of the served detail file) when that file is on the
    # machine, else over every runner as an upper bound.
    detail = DATA / "mlb_player_detail.json"
    take = list(rows)
    if detail.exists():
        cards = {int(c["mlbam"]): c for c in json.loads(detail.read_text(encoding="utf-8"))["players"].values()
                 if c.get("mlbam")}
        take = [m for m in rows if m in cards and (not cards[m].get("isPit") or cards[m].get("twoWay"))]
        assert len(take) > 300, len(take)
    raw = sum(len(json.dumps(idx[m]["br"], separators=(",", ":"))) + len('"br":') for m in take)
    assert raw < BUDGET_RAW, raw


# ---------------------------------------------------------------- served artifact
def test_the_served_card_block_equals_the_served_board():
    p = DATA / "mlb_player_detail.json"
    if not p.exists():
        pytest.skip("data/mlb_player_detail.json not built on this machine")
    d = json.loads(p.read_text(encoding="utf-8"))
    if "br" not in (d.get("coverage") or {}):
        pytest.skip("mlb_player_detail.json predates the skills.br bake")
    board_p = DATA / bre.OUT_NAME
    if not bre.CARD_BASERUNNING_LIVE or not board_p.exists():
        assert d["coverage"]["br"] == 0
        assert not any((c.get("skills") or {}).get("br") for c in d["players"].values())
        return
    board = {int(r["mlbam"]): r for r in json.loads(board_p.read_text(encoding="utf-8"))["runners"]}
    n = raw = 0
    for c in d["players"].values():
        b = (c.get("skills") or {}).get("br")
        if not b:
            continue
        assert not c.get("isPit") or c.get("twoWay"), c["key"]
        r = board[int(c["mlbam"])]
        assert b["ebr"] == r["ebr"] and b.get("bsrFg") == r.get("bsr"), c["key"]
        n += 1
        raw += len(json.dumps(b, separators=(",", ":"))) + len('"br":')
    assert n == d["coverage"]["br"] and raw < BUDGET_RAW, (n, raw)


# ---------------------------------------------------------------- the rendered tab
_BR = {"season": 2026, "qualified": True, "ebr": 15.6, "ebrSb": 3.2, "ebrXb": 6.9, "ebrDp": 5.5, "sb": 41,
       "cs": 7, "pk": 1, "sbPct": 0.854, "attRate": 0.194, "xbtPct": 0.545, "gidpPct": 0.017, "sprint": 29.5,
       "sprintPct": 95, "bsrFg": 8.2, "brvSavant": 7.9}


def _render_with_br(key: str, blk, hash_: str) -> dict:
    detail = json.loads(psmoke.DETAIL)
    sk = detail["players"][key].setdefault("skills", {})
    if blk is None:
        sk.pop("br", None)
    else:
        sk["br"] = blk
    src = psmoke._prelude(hash_).replace("var DETAIL=" + psmoke.DETAIL + ";", "var DETAIL=" + json.dumps(detail) + ";")
    assert "var DETAIL=" + json.dumps(detail) + ";" in src
    ctx = psmoke.MiniRacer()
    ctx.eval(src + psmoke.TIERS_JS + psmoke.JS)
    return json.loads(ctx.eval("JSON.stringify(__html)"))


def test_the_hitting_tab_renders_the_baserunning_section_from_the_block():
    html = _render_with_br("vet_guy", _BR, "#player=vet_guy&ptab=hitting")["proj-rows"]
    sec = psmoke._section(html, "hitting-baserunning")
    for label in ("SB runs", "XB runs", "DP runs", "eBR", "BsR (FG, published)", "BRV (Savant)"):
        assert label in sec, label
    for val in ("+15.6", "+3.2", "+6.9", "+5.5", "+8.2", "+7.9"):
        assert val in sec, val
    assert "41 SB / 7 CS (85.4%)" in sec and "XBT% 54.5%" in sec and "Sprint 29.5 ft/s (p95)" in sec
    assert 'href="/mlbstats/#section=baserunning"' in sec
    assert "undefined" not in sec and "NaN" not in sec
    for gl in ("ebr", "ebr_sb", "ebr_xb", "ebr_dp", "bsr", "savant_brv"):
        assert f'data-gl="{gl}"' in sec, gl
    assert "Baserunning: eBR counted here" in html
    order = [m for m in ("hitting-statcast", "hitting-baserunning", "hitting-context") if f'data-mlbp-section="{m}"' in html]
    assert order == ["hitting-statcast", "hitting-baserunning", "hitting-context"], order
    tabs = [t for t, _ in psmoke._tabs(html)]
    assert "baserunning" not in tabs and "hitting" in tabs, tabs
    assert "baserunning" not in psmoke.JS.split("const PTABS = [")[1].split("]")[0], "no new tab (PTABS unchanged)"


def test_the_comparison_rows_are_neutral_and_the_parts_are_toned():
    html = _render_with_br("vet_guy", _BR, "#player=vet_guy&ptab=hitting")["proj-rows"]
    sec = psmoke._section(html, "hitting-baserunning")
    import re
    bars = re.findall(r'<div class="mlbp-runbar([^"]*)">.*?<span class="mlbp-runbar-fill ([^"]*)"', sec, re.S)
    assert len(bars) == 6, bars
    assert bars[3][0] == " is-total" and "proj-pos" in bars[3][1]
    assert all("is-sub" in cls and tone.strip() == "" for cls, tone in bars[4:]), bars[4:]


def test_without_the_block_the_tab_is_the_tab_it_was():
    html = _render_with_br("vet_guy", None, "#player=vet_guy&ptab=hitting")["proj-rows"]
    assert 'data-mlbp-section="hitting-baserunning"' not in html
    assert "Baserunning:" not in html
    html = _render_with_br("ace_arm", _BR, "#player=ace_arm&ptab=hitting")["proj-rows"]
    assert 'data-mlbp-section="hitting-baserunning"' not in html, "a pitcher card has no hitting tab to carry it"


def test_a_provisional_block_says_so_and_prints_no_rate_it_lacks():
    blk = {"season": 2026, "qualified": False, "ebr": 0.4, "ebrSb": 0.3, "ebrXb": 0.1, "ebrDp": 0.0, "sb": 2, "cs": 0}
    sec = psmoke._section(_render_with_br("vet_guy", blk, "#player=vet_guy&ptab=hitting")["proj-rows"], "hitting-baserunning")
    import re
    text = re.sub(r"<[^>]+>", " ", sec)              # the printed words, not the bars' CSS widths
    assert "provisional" in text and "2 SB / 0 CS" in text
    assert "Att%" not in text and "XBT%" not in text and "Sprint" not in text and "0.0%" not in text
    assert "BsR" not in text and "BRV" not in text


def test_the_section_copy_carries_no_forecast_word():
    src = psmoke.JS.split("function baserunningBlock(")[1].split("\n  }\n")[0].lower()
    for w in ("luck", " due", "regress", "trending", "will ", "clutch", "sleeper", "better", "accurate"):
        assert w not in src, w
