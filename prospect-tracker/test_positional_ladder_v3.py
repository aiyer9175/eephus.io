# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for the positional ladder v3 re-read (LADDER_V3_REREAD, owner EW3-29,
2026-10-15; docs/ewar/LADDER_V3_GATE.md).

1. The method, on fixtures (hermetic): Statcast runs centred within (position,
   season); the amended within-group fit (A1, player fixed effects) recovers a
   planted ladder on the gate's simulation; the assembly puts the group levels,
   1B and DH on the offense anchor and carries C from v1; the fold masks keep
   the held-out season out of every row that reads it.
2. The record: the verdict follows its own five criteria, and nothing serves
   or is written as a ladder artifact unless all five pass.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "tools"))

import ladder_v2 as L2  # noqa: E402
import ladder_v3 as L3  # noqa: E402

EVAL = ROOT / "data" / "positional_ladder_v3_eval.json"
ALL = set(range(2016, 2027))


@pytest.fixture(scope="module")
def fixture():
    import ladder_v2_lab as lab
    recs, target, e9 = lab.fixture_records()
    return recs, target, e9


def test_statcast_runs_are_centred_within_position_and_season(fixture):
    recs, _t, _e9 = fixture
    rc = L3.centre_savant(recs)
    acc = {}
    for (m, t), r in rc.items():
        for p, v in (r.get("sav") or {}).items():
            acc[(p, t)] = acc.get((p, t), 0.0) + v
    assert acc and max(abs(v) for v in acc.values()) < 1e-6


def test_the_fixed_effects_fit_recovers_a_planted_ladder(fixture):
    """Amendment A1: on the gate's part 6 construction the within-group gaps
    come back at 0.80 to 1.25 of their size, averaged over two seeds."""
    recs, _t, e9 = fixture
    ratios = {}
    for sd in (7, 8):
        sim, G, _q = L3.simulate(recs, e9, sd)
        for p, v in L3.recovery(sim, G, e9, ALL)["ratios"].items():
            ratios.setdefault(p, []).append(v)
    mean = {p: float(np.mean(v)) for p, v in ratios.items()}
    assert set(mean) == {"2B", "3B", "LF", "RF"}
    assert all(0.8 <= v <= 1.25 for v in mean.values()), mean


def test_assembly_puts_levels_on_the_anchor_and_carries_c(fixture):
    _r, _t, e9 = fixture
    off = L2.recentre({"C": 4.0, "1B": -6.0, "2B": 3.0, "3B": -1.0, "SS": 5.0,
                       "LF": -2.0, "CF": 4.0, "RF": -4.0, "DH": -9.0}, e9)
    shapes = {"IF": {"2B": -1.0, "3B": -2.0, "SS": 2.5}, "OF": {"LF": -3.0, "CF": 3.5, "RF": -1.0}}
    for g, grp in L3.GROUPS.items():   # shapes centred as pool_shapes leaves them
        mu = L3.group_level(shapes[g], grp, e9)
        shapes[g] = {p: v - mu for p, v in shapes[g].items()}
    v1 = L2.recentre({"C": 10.0, "1B": -8.0, "2B": 5.0, "3B": 3.5, "SS": 9.0,
                      "LF": -6.0, "CF": 4.0, "RF": -6.5, "DH": -13.0}, e9)
    L = L3.assemble(shapes, off, v1, e9)
    assert abs(sum(e9[p] * L[p] for p in L2.LADDER9)) < 1e-3   # e9 sums to 1 to 4 dp
    for g, grp in L3.GROUPS.items():
        # group level relative to 1B is the anchor's
        assert abs((L3.group_level(L, grp, e9) - L["1B"])
                   - (L3.group_level(off, grp, e9) - off["1B"])) < 1e-9
        for p in grp:   # gaps inside the group are the switchers'
            q = L3.GROUP_REF[g]
            assert abs((L[p] - L[q]) - (shapes[g][p] - shapes[g][q])) < 1e-9
    assert abs((L["DH"] - L["1B"]) - (off["DH"] - off["1B"])) < 1e-9
    assert abs((L["C"] - L2.mean7(L, e9)) - (v1["C"] - L2.mean7(v1, e9))) < 1e-9


def test_the_fold_masks_keep_the_held_out_season_out():
    A = {"t": np.array([2016, 2017, 2018, 2019, 2020, 2021])}
    mk = L3.mask_A(A, ALL, drop=2017)
    # rows whose seasons t-3..t include 2017: later seasons 2017 to 2020
    assert mk.tolist() == [True, False, False, False, False, True]
    S = {"t": np.array([2016, 2017, 2018])}
    assert L3.mask_S(S, ALL, drop=2017).tolist() == [True, False, True]


def test_the_scoring_separates_a_planted_ladder_from_zero(fixture):
    """The power check of gate part 6 on the fixture design."""
    recs, _t, e9 = fixture
    sim, G, q = L3.simulate(recs, e9, 7)
    rows = L3.build_rows(L3.centre_savant(sim))
    Gl = {p: G.get(p, q[p]) for p in L2.LADDER9}
    zero = {p: (Gl[p] if p in ("C", "DH") else 0.0) for p in L2.LADDER9}
    loss = []
    for t in sorted(ALL):
        loss.extend(L3.score_rows(rows, {"G": Gl, "zero": zero}, t, ALL - {t})[0])
    sm = L2.summarize(loss, ["G", "zero"])
    assert sm["G"]["mae"] < sm["zero"]["mae"]


# ---- 2. the record --------------------------------------------------------------

def _eval():
    if not EVAL.exists():
        pytest.skip("positional_ladder_v3_eval.json not built")
    return json.loads(EVAL.read_text(encoding="utf-8"))


def test_the_verdict_follows_its_five_criteria():
    ev = _eval()
    v, t = ev["verdict"], ev["tests"]
    pm = {k: (d or {}).get("mae") for k, d in ev["scores"]["pooled"].items()}
    assert v["1_beats_zero"] == (t["zero_minus_v3_pooled"]["ci95"][0] > 0)
    assert v["2_beats_v1"] == (t["v1_minus_v3_pooled"]["ci95"][0] > 0)
    rivals = [k for k in pm if k.startswith("v1_x")] + ["fg_table"]
    assert len(rivals) == 6
    assert v["3_below_scaled_v1_and_fg_table"] == all(pm["v3"] < pm[k] for k in rivals)
    assert v["4_not_worse_than_zero_next_season"] == (t["zero_minus_v3_across"]["ci95"][1] >= 0)
    ratios = ev["simulation"]["base"]["mean_ratio"]
    assert len(ev["simulation"]["base"]["seeds"]) == 5
    assert v["5_recovers_planted_ladder"] == all(0.8 <= r <= 1.25 for r in ratios.values())
    crit = [v[k] for k in ("1_beats_zero", "2_beats_v1", "3_below_scaled_v1_and_fg_table",
                           "4_not_worse_than_zero_next_season", "5_recovers_planted_ladder")]
    assert v["passed"] == all(crit)


def test_no_ladder_artifact_unless_v3_passed():
    ev = _eval()
    if ev["verdict"]["passed"]:
        assert L3.OUT_PATH.exists()
        assert "positional_ladder_v3.json" in (ROOT / "deploy" / "data_exclude.txt").read_text(
            encoding="utf-8")
    else:
        assert not L3.OUT_PATH.exists()
    import positional_fit as pf
    assert pf.POSFIT_LADDER == "v1"
