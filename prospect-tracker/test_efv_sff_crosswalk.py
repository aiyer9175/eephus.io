# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""F-SIDE-FIX crosswalk endpoint guard.

The joint band reassigns display grades by expected WAR read off each side's
PAVA crosswalk. A curve ENDPOINT backed by a single player therefore decides
which side owns the top of the board. Measured 2026-07-31 on the live
artifacts: the pitcher terminal block was n=1 (shohei_ohtani, whose stored
first-6yr bWAR is his TWO-WAY total because career WAR carries no
pitching/batting split), reading 34.59 against 5.63 one knot below, while the
hitter side's terminal block naturally covered 7 players. Whichever pitcher
ranked first inherited that cliff and was promoted above every hitter.
"""

from __future__ import annotations

import efv_score as es


# ---- the pooling primitive ---------------------------------------------------

def test_tail_pooling_is_a_noop_when_the_block_is_already_wide():
    fit = [1.0] * 10 + [5.0] * 6
    assert es._sff_pool_tail(fit, 5) == fit


def test_tail_pooling_merges_a_single_player_endpoint():
    """One row at 34.59 on top of a block at 5.0 must not survive as its own
    knot: it pools backward until the endpoint has real support."""
    fit = [1.0] * 10 + [5.0] * 4 + [34.59]
    out = es._sff_pool_tail(fit, 5)
    assert out[-1] < 34.59, "terminal knot still defined by one row"
    # 4 rows at 5.0 + one at 34.59 -> pooled mean over the 5
    assert abs(out[-1] - (5.0 * 4 + 34.59) / 5) < 1e-9
    assert out[:10] == [1.0] * 10, "pooling must not reach past what it needs"


def test_tail_pooling_preserves_monotonicity():
    fit = [0.5] * 20 + [2.0] * 3 + [9.0] * 2 + [40.0]
    out = es._sff_pool_tail(fit, 8)
    assert all(a <= b + 1e-12 for a, b in zip(out, out[1:])), out[-12:]
    assert out[-1] <= 40.0 and out[-1] >= 2.0


def test_tail_pooling_conserves_the_pooled_total():
    """Merging by the pooled mean must not invent or destroy WAR."""
    fit = [1.0] * 6 + [4.0] * 2 + [30.0]
    out = es._sff_pool_tail(fit, 5)
    assert abs(sum(out) - sum(fit)) < 1e-9


def test_tail_pooling_degenerate_inputs():
    assert es._sff_pool_tail([], 5) == []
    assert es._sff_pool_tail([3.0], 5) == [3.0]
    assert es._sff_pool_tail([1.0, 2.0], 1) == [1.0, 2.0]


# ---- the curve ---------------------------------------------------------------

def _pairs(vals):
    """rank_war ascending, one row each."""
    return [(float(i), v) for i, v in enumerate(vals)]


def test_curve_endpoint_is_never_one_row():
    vals = [0.2] * 40 + [3.0] * 5 + [34.59]
    qs, fit = es._sff_crosswalk_curve(_pairs(vals))
    tail = sum(1 for v in fit if v == fit[-1])
    assert tail >= es._SFF_MIN_TAIL_N, f"terminal block only {tail} rows"


def test_curve_guard_leaves_a_healthy_tail_alone():
    """A side whose top block already has support must come back BYTE-IDENTICAL
    -- the guard has to be targeted at the degenerate side, not a re-scale.
    (This is what the live hitter curve does: its terminal block is 7.)"""
    vals = [0.2] * 40 + [12.0] * 7
    _, guarded = es._sff_crosswalk_curve(_pairs(vals))
    _, ungated = es._sff_crosswalk_curve(_pairs(vals), min_tail_n=1)
    assert guarded == ungated


def test_curve_still_refuses_a_pool_that_is_too_thin():
    assert es._sff_crosswalk_curve(_pairs([1.0] * 5)) is None


def test_expected_war_reads_the_guarded_endpoint():
    vals = [0.2] * 40 + [3.0] * 5 + [34.59]
    curve = es._sff_crosswalk_curve(_pairs(vals))
    assert es._sff_expected_war(curve, 1.0) == curve[1][-1] < 34.59
    # and the curve is still monotone across the quantile range it is read at
    reads = [es._sff_expected_war(curve, q / 20) for q in range(21)]
    assert all(a <= b + 1e-9 for a, b in zip(reads, reads[1:])), reads


# ---- the property the whole guard exists to protect --------------------------

def test_a_lone_outlier_cannot_take_the_top_of_the_joint_band():
    """End-to-end on the pure core: a pitcher pool whose top row carries an
    inflated (two-way) target must not out-rank a deeper hitter pool."""
    hit_vals = [0.2] * 40 + [12.0] * 7
    pit_vals = [0.2] * 40 + [3.0] * 5 + [34.59]
    curves = {"hit": es._sff_crosswalk_curve(_pairs(hit_vals)),
              "pit": es._sff_crosswalk_curve(_pairs(pit_vals))}
    rows = []
    for sd, n in (("hit", 3), ("pit", 3)):
        for i in range(n):
            q = i / (n - 1)
            rows.append({"side": sd, "idx": i, "rank_war": float(i),
                         "preside": 55.0 + i, "ew": es._sff_expected_war(curves[sd], q)})
    assign = es.joint_band_recal(rows)
    top_side = max(rows, key=lambda r: assign[(r["side"], r["idx"])])["side"]
    assert top_side == "hit", "single-row pitcher endpoint still owns the band"
