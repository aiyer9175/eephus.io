# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Lineup Charts PLT margin, re-derived on platoon_ratio_v1 (owner answer
M17HEM-1 (b), 2026-10-01) by the recipe that set the first value.

The recipe (tools/plt_margin_lab.py): the population SD of (vs-LHP minus vs-RHP
HEM+) within a bat side and vs-LHP PA band, over cells of 8+ hitters, its low end
rounded up to a multiple of 5. Each test names the mutation it exists to catch.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

import hem_plus as H

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "tools"))
import plt_margin_lab as LAB  # noqa: E402

D = H.PLATOON_OPTION_MARGIN_DERIVATION
BOARD = ROOT / "data" / "hitter_leaderboards.json"
GLOSSARY = ROOT / "data" / "glossary.json"


def test_the_margin_is_the_rederived_value():
    """Mutation: the constant edited by hand away from its derivation, or the
    old 15 restored without a new derivation."""
    low = min(c["sd"] for c in D["cells"])
    assert D["spread_low"] == low
    assert D["spread_high"] == max(c["sd"] for c in D["cells"])
    assert H.PLATOON_OPTION_MARGIN == D["round_to"] * math.ceil(low / D["round_to"])
    assert H.PLATOON_OPTION_MARGIN == 5


def test_the_derivation_inputs_are_the_recipe():
    """Mutation: a band, the cell floor or the rounding step changed in the lab
    without the frozen record (or the other way round)."""
    assert D["estimator"] == H.SPLIT_ESTIMATOR
    assert D["bands"] == [list(b) for b in LAB.BANDS]
    assert D["bands"] == [[20, 60], [60, 100], [100, 150], [150, 250], [250, 900]]
    assert D["min_cell_n"] == LAB.MIN_CELL_N == 8
    assert D["round_to"] == LAB.ROUND_TO == 5
    assert D["n_hitters_both_hands"] == 644
    assert all(c["n"] >= D["min_cell_n"] for c in D["cells"])
    assert all(c["bats"] in LAB.SIDES for c in D["cells"])
    assert all(c["vs_lhp_pa"] in D["bands"] for c in D["cells"])
    assert sum(c["n"] for c in D["cells"]) <= D["n_hitters_both_hands"]


@pytest.mark.parametrize("low, want", [(13.5, 15), (13.23, 15), (1.24, 5), (5.0, 5), (5.01, 10)])
def test_the_rounding_rule_reproduces_the_first_value(low, want):
    """Mutation: rounding to the nearest 5, which keeps 15 on the first
    construction (13.5) and the bridge (13.23) but gives 0, no gate, now."""
    assert LAB.margin_from([{"sd": low}]) == (low, want)
    assert D["previous"]["margin"] == LAB.margin_from([{"sd": D["previous"]["spread_low"]}])[1]


def test_a_rerun_of_the_recipe_reproduces_the_frozen_cells():
    """Mutation: the split construction changed under the frozen margin. Reads
    the lab's cached 2026 inputs; skipped on a box that never ran the lab."""
    need = ["2026_season_rows.json", "2026_players.json", "2026_vl.json", "2026_vr.json"]
    if not all((LAB.CACHE / n).exists() for n in need):
        pytest.skip("tools/plt_margin_lab.py inputs not cached on this box")
    rows, bats, counts = LAB.load_inputs()
    n_both, cells = LAB.cells(LAB.split_map(rows, bats, counts), bats)
    assert n_both == D["n_hitters_both_hands"]
    assert cells == D["cells"]


def test_the_served_board_echoes_the_margin_and_its_basis():
    """Mutation: the export typing a margin of its own, or the basis drifting
    from the frozen record the glossary cites."""
    lc = json.loads(BOARD.read_text(encoding="utf-8"))["lineup_cards"]
    assert lc["constants"]["margin"] == H.PLATOON_OPTION_MARGIN
    mb = lc["margin_basis"]
    assert (mb["spread_low"], mb["spread_high"], mb["round_to"]) == (
        D["spread_low"], D["spread_high"], D["round_to"])
    assert mb["estimator"] == D["estimator"]
    assert mb["n_hitters_both_hands"] == D["n_hitters_both_hands"]


def test_every_served_chip_clears_the_margin_and_recomputes():
    """Mutation: chips served at the old margin, or a chip under the new one."""
    d = json.loads(BOARD.read_text(encoding="utf-8"))
    n = 0
    for t in d["teams"]:
        po = t.get("platoon_options") or {}
        for side, hand in (("vl", "L"), ("vr", "R")):
            served = po.get(side) or []
            assert all(o["delta"] >= H.PLATOON_OPTION_MARGIN for o in served)
            mine, withheld = H.platoon_options(t["orders"][side], t.get("bench") or [],
                                               t.get("slot_meta") or {}, hand)
            assert mine == served, (t["team"], side)
            assert withheld == int((po.get("n_withheld") or {}).get(side) or 0)
            n += len(served)
    assert n == sum(d["lineup_cards"]["n_platoon_options"].values())


def test_the_glossary_states_the_margin_and_its_derivation():
    """Mutation: the reader-facing rule still saying 15, or citing numbers the
    frozen record does not hold."""
    g = json.loads(GLOSSARY.read_text(encoding="utf-8"))
    e = next(x for x in g["entries"] if x["id"] == "platoon_option")
    m = H.PLATOON_OPTION_MARGIN
    assert f"by {m}+" in e["definition"]
    assert f"is {m} or more" in e["methodology"]
    assert f">= {m}" in e["formula"]
    for v in (D["spread_low"], D["spread_high"], D["previous"]["spread_low"],
              D["previous"]["spread_high"]):
        assert f"{v}" in e["methodology"], v
    assert "15 or more" not in e["methodology"] and ">= 15" not in e["formula"]
