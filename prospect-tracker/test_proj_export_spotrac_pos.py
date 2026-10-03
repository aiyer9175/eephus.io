"""EPOCH-SPOTRAC-1 (2026-10-03): a numeric Spotrac 'Pos' code never decides a
veteran card's side.

On 2026-10-03 Spotrac's team contract pages began serving numeric codes in
the 'Pos' column ("Jhoan Duran | 33 | 29"). proj_export's inline vet join
copied that code onto the served row without the P-POSVAL check
(_valid_pos) that _apply_contract already ran, so 242 vets shipped pos '33',
'32', '34' and so on, and the 128 pitchers among them rendered as hitter
cards with a 0.0 career WAR line (mlb_player_export reads isPit from pos).
The repair validates the position where the row is built and falls back to
the engine's role token (SP, RP or H); the exporter holds no StatsAPI
primary position to prefer.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import mlb_player_export
import proj_export

ROOT = Path(__file__).resolve().parent
PROJ = ROOT / "data" / "mlb_projections.json"

NUMERIC_CODES = ["33", "32", "34", "37", "40", "62", " 35 ", "0"]


@pytest.mark.parametrize("code", NUMERIC_CODES)
@pytest.mark.parametrize("role", ["SP", "RP"])
def test_numeric_spotrac_code_keeps_a_pitcher_a_pitcher(code, role):
    pos = proj_export._vet_pos(False, {"position": code}, role)
    assert pos == role
    assert proj_export._row_sides({"pos": pos}) == ["pit"]
    assert mlb_player_export._is_pitcher_pos(pos) is True


@pytest.mark.parametrize("code", NUMERIC_CODES)
def test_numeric_spotrac_code_keeps_a_hitter_a_hitter(code):
    pos = proj_export._vet_pos(False, {"position": code}, "H")
    assert pos == "H"
    assert proj_export._row_sides({"pos": pos}) == ["hit"]
    assert mlb_player_export._is_pitcher_pos(pos) is False


def test_real_spotrac_position_still_wins_and_two_way_is_twp():
    assert proj_export._vet_pos(False, {"position": "ss"}, "H") == "SS"
    assert proj_export._vet_pos(False, {"position": "RP"}, "SP") == "RP"
    assert proj_export._vet_pos(False, None, "SP") == "SP"
    assert proj_export._vet_pos(False, {"position": None}, "RP") == "RP"
    assert proj_export._vet_pos(True, {"position": "33"}, "SP") == "TWP"


def test_row_sides_reads_the_pitcher_vocabulary_the_card_reads():
    for pos in sorted(proj_export._VALID_POS):
        assert (proj_export._row_sides({"pos": pos}) == ["pit"]) == \
            mlb_player_export._is_pitcher_pos(pos), pos


def _vets():
    if not PROJ.exists():
        pytest.skip("data/mlb_projections.json not built")
    return json.loads(PROJ.read_text(encoding="utf-8")).get("vets") or []


def test_served_vet_positions_are_positions_or_roles():
    allowed = proj_export._VALID_POS | {"H"}
    bad = [(v.get("key"), v.get("pos")) for v in _vets()
           if str(v.get("pos") or "").strip().upper() not in allowed]
    assert not bad, f"{len(bad)} vets serve a non-position pos: {bad[:10]}"


def test_served_vet_side_matches_its_stat_line():
    """A one-sided vet's pitching line (fip) and a pitcher pos go together, so
    every pitcher keeps a pitcher card and every hitter a hitter card."""
    wrong = []
    for v in _vets():
        if v.get("twoWay"):
            continue
        has_pit = v.get("fip") is not None
        has_hit = v.get("woba") is not None
        if has_pit == has_hit:
            continue
        if mlb_player_export._is_pitcher_pos(v.get("pos")) != has_pit:
            wrong.append((v.get("key"), v.get("pos")))
    assert not wrong, f"{len(wrong)} vets on the wrong side: {wrong[:10]}"
