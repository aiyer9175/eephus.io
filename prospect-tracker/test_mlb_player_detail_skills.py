# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""skills.lev and skills.def on the MLB player card payload.

THE DEFECT (D3-03, found 2026-09-11). _skill_index built a leverage block for
651 page batters and 347 starters, and build_payload copied only "hem" and
"pitch" onto the card, so the served payload carried 0 skills.lev blocks and the
renderer's leverage line was dead code. Nothing failed because no invariant was
asserted over the served artifact. The Defense board (skills.def) joins the same
way and gets the same guard.

Two layers:
  - fixtures through _skill_index and _card_skills (always run);
  - the served data/mlb_player_detail.json against the boards it joins. That
    artifact is rebuilt nightly and gitignored, so these skip when it is absent,
    and skip (saying so) when it was baked before the per-block coverage keys
    existed, i.e. before this bake shipped.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import mlb_player_export as mpe

ROOT = Path(__file__).parent
DATA = ROOT / "data"

DEF_KEYS = {"season", "pos", "inn", "posInn", "qualified", "demPlus", "demPlusPct",
            "demPlusPosPct", "fldTotal", "frmRuns", "posRuns", "defRuns"}
LEV_KEYS = {"kind", "season", "wpa", "wpaLi", "pli", "clutch", "wpaPerStart"}


def _write(d: Path, name: str, obj) -> None:
    (d / name).write_text(json.dumps(obj), encoding="utf-8")


@pytest.fixture
def index(tmp_path, monkeypatch):
    monkeypatch.setattr(mpe, "DATA_DIR", tmp_path)
    _write(tmp_path, "hitter_leaderboards.json", {"season": 2026, "hitters": [
        {"mlbam": 1, "hem_plus": 113, "qualified": True},
        {"mlbam": 3, "hem_plus": 170, "qualified": True}]})
    _write(tmp_path, "bullpen_leaderboards.json", {"season": 2026, "relievers": []})
    _write(tmp_path, "starter_leaderboards.json", {"season": 2026, "starters": [
        {"mlbam": 2, "sem_plus": 104, "qualified": True}]})
    _write(tmp_path, "leverage_leaderboards.json", {"season": 2026,
        "batters": [{"mlbam": 1, "wpa": 1.5, "wpa_li": 0.9, "pli": 1.02, "clutch": 0.3},
                    {"mlbam": 3, "wpa": 2.0, "wpa_li": 1.0, "pli": 1.10, "clutch": 0.1}],
        "starters": [{"mlbam": 2, "wpa": 0.8, "wpa_li": 0.5, "wpa_per_start": 0.03},
                     {"mlbam": 3, "wpa": -0.4, "wpa_li": -0.2, "wpa_per_start": -0.02}]})
    _write(tmp_path, "defense_leaderboards.json", {"season": 2026, "fielders": [
        {"mlbam": 1, "pos": "C", "inn": 908.7, "pos_inn": {"C": 908.7}, "qualified": True,
         "tier": "Elite", "dem_plus": 133, "dem_plus_raw": 133.08, "rel": 0.685,
         "rate_1000": 15.83, "fld_runs": 6.2, "fld_total": 14.4, "frm_runs": 8.2,
         "pos_runs": 4.8, "def_runs": 19.1, "dem_plus_pct": 100, "dem_plus_pos_pct": 99,
         "hem_plus": 104, "dem_plus_3yr": 124}]})
    return mpe._skill_index()


def test_def_block_is_its_own_key_with_only_the_card_columns(index):
    d = index[1]["def"]
    assert set(d) <= DEF_KEYS, set(d) - DEF_KEYS
    assert (d["demPlus"], d["fldTotal"], d["frmRuns"], d["defRuns"]) == (133, 14.4, 8.2, 19.1)
    assert d["season"] == 2026 and d["posInn"] == {"C": 908.7}
    # never folded into the hem block, whose ruler (88/112) DEM+ does not share
    assert not DEF_KEYS & (set(index[1]["hem"]) - {"season", "qualified"})


def test_lev_is_kept_per_side(index):
    """One merged dict let the starter row's None pLI overwrite the batter's."""
    lev = index[3]["lev"]
    assert lev["bat"]["wpa"] == 2.0 and lev["bat"]["pli"] == 1.10
    assert lev["sp"]["wpa"] == -0.4 and lev["sp"]["wpaPerStart"] == -0.02
    assert "pli" not in lev["sp"]                 # None columns are dropped
    for side in lev.values():
        assert set(side) <= LEV_KEYS


def test_card_skills_hand_each_card_its_own_side(index):
    hitter = mpe._card_skills(index[1], is_pit=False, two_way=False)
    assert set(hitter) == {"hem", "lev", "def"} and hitter["lev"]["kind"] == "bat"
    pitcher = mpe._card_skills(index[2], is_pit=True, two_way=False)
    assert set(pitcher) == {"pitch", "lev"} and pitcher["lev"]["kind"] == "sp"
    two_way = mpe._card_skills(index[3], is_pit=False, two_way=True)
    assert two_way["lev"]["kind"] == "bat" and two_way["levPit"]["kind"] == "sp"
    # a pitcher card never carries a fielding block, even if the index had one
    assert "def" not in mpe._card_skills({"def": {"demPlus": 100}}, is_pit=True, two_way=False)
    assert mpe._card_skills(None, is_pit=False, two_way=False) == {}


# ---------------------------------------------------------------------------
# served artifact
# ---------------------------------------------------------------------------

def _detail(block: str) -> dict:
    p = DATA / "mlb_player_detail.json"
    if not p.exists():
        pytest.skip("data/mlb_player_detail.json not built on this machine")
    d = json.loads(p.read_text(encoding="utf-8"))
    if block not in (d.get("coverage") or {}):
        pytest.skip(f"mlb_player_detail.json predates the skills.{block} bake; "
                    "rebuild with mlb_player_export")
    return d


def _board(name: str) -> dict:
    p = DATA / name
    if not p.exists():
        pytest.skip(f"data/{name} not built on this machine")
    return json.loads(p.read_text(encoding="utf-8"))


def _cards(d: dict):
    for p in (d.get("players") or {}).values():
        if p.get("mlbam"):
            yield int(p["mlbam"]), p


def test_served_lev_on_nine_in_ten_page_players_on_the_leverage_board():
    d = _detail("lev")
    lb = _board("leverage_leaderboards.json")
    bat = {int(r["mlbam"]) for r in lb.get("batters") or [] if r.get("mlbam")}
    sp = {int(r["mlbam"]) for r in lb.get("starters") or [] if r.get("mlbam")}
    on_board = [p for mid, p in _cards(d)
                if (mid in bat and (not p.get("isPit") or p.get("twoWay")))
                or (mid in sp and p.get("isPit"))]
    assert len(on_board) > 300, len(on_board)
    have = sum(1 for p in on_board if (p.get("skills") or {}).get("lev"))
    assert have >= 0.9 * len(on_board), f"skills.lev on {have} of {len(on_board)}"
    for _, p in _cards(d):
        lev = (p.get("skills") or {}).get("lev")
        if lev:
            assert set(lev) <= LEV_KEYS and lev["kind"] in ("bat", "sp")
            assert lev["kind"] == ("sp" if p.get("isPit") else "bat")


def test_served_def_on_fielders_only_and_on_nine_in_ten_of_them():
    d = _detail("def")
    fb = _board("defense_leaderboards.json")
    fielders = {int(r["mlbam"]) for r in fb.get("fielders") or [] if r.get("mlbam")}
    on_board = [p for mid, p in _cards(d)
                if mid in fielders and (not p.get("isPit") or p.get("twoWay"))]
    assert len(on_board) > 300, len(on_board)
    have = sum(1 for p in on_board if (p.get("skills") or {}).get("def"))
    assert have >= 0.9 * len(on_board), f"skills.def on {have} of {len(on_board)}"
    for _, p in _cards(d):
        sk = p.get("skills") or {}
        if sk.get("def"):
            assert not (p.get("isPit") and not p.get("twoWay")), p.get("key")
            assert set(sk["def"]) <= DEF_KEYS, set(sk["def"]) - DEF_KEYS
        assert "demPlus" not in (sk.get("hem") or {}) and "demPlus" not in (sk.get("pitch") or {})


def test_served_payload_under_the_soft_budget():
    p = DATA / "mlb_player_detail.json"
    if not p.exists():
        pytest.skip("data/mlb_player_detail.json not built on this machine")
    size = p.stat().st_size
    assert size <= mpe._PAYLOAD_SOFT_BUDGET, (
        f"mlb_player_detail.json is {size} bytes, over the "
        f"{mpe._PAYLOAD_SOFT_BUDGET}-byte soft budget it is lazy-fetched under")
