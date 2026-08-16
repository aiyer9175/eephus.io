# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Rank-basis guards for the dynasty board (the 2026-08-16 driver swap).

Two things are pinned here, each against a named mutation:

  1. THE SCORE DRIVER IS THE BOARD GRADE. The fixture makes the retired
     xfv_grade_quantile order and the board-grade order disagree outright, so a
     mutant that reverts _dynasty_prospects' driver to the quantile produces
     the reversed ranking and fails.

  2. RANK CANNOT CONTRADICT THE SHOWN COLUMN BY MORE THAN 4.0 FV. Within the
     served top 300 and within a tier, a row never shows an eFV more than 4.0
     below a row ranked beneath it. This is the property the live probe
     measured at 3.4 worst (tools/dynasty_basis_probe.py); the bound is the
     approved-plan ceiling, not the measured value, so ordinary star/bust/ETA
     leapfrogs stay legal. The mutation that must break it is tripling
     dynasty_blend.W_STAR (10 -> 30), and the file PROVES that mutation has
     teeth by running it under a restored-on-exit weight override.
"""
from __future__ import annotations

import dynasty_blend
import fantasy_export as fe

INVERSION_BOUND_FV = 4.0


def _ts_row(key, mid, eta_year=2026):
    return {"player_key": key, "player_name": key.title(), "mlbam_id": mid,
            "position": "SS", "org": "MIL",
            "eta": {"year": eta_year} if eta_year else None}


def _xfv_row(grade, star=0.0, bust=0.0, surplus=0.0, quantile=None):
    row = {"xfv_grade": grade, "p_bucket": {"star": star, "bust": bust},
           "p_bust": bust, "surplus_mm": surplus,
           "band_p10_mm": 0.0, "band_p90_mm": 50.0}
    if quantile is not None:
        row["xfv_grade_quantile"] = quantile
    return row


# ---- (a) the driver is the board grade, not the quantile -------------------
def test_rank_follows_board_grade_when_quantile_disagrees():
    """Quantile order a > b > c; board-grade order c > b > a. All other blend
    legs identical, so the ranking is decided by the driver alone: the board
    grade must win, and the shown column must be the board grade too. A mutant
    scoring on the quantile returns [1, 2, 3] and fails."""
    ts = {"players": [_ts_row("a", 1), _ts_row("b", 2), _ts_row("c", 3)]}
    xfv = {"by_player": {
        "a": _xfv_row(44.0, quantile=70.0),
        "b": _xfv_row(50.0, quantile=60.0),
        "c": _xfv_row(56.0, quantile=50.0),
    }}
    rows = fe._dynasty_prospects(ts, 2026, xfv=xfv)
    assert [r["mlbam"] for r in rows] == [3, 2, 1], rows
    assert [r["efv"] for r in rows] == [56.0, 50.0, 44.0], rows
    # scores are grade + 4.0 (eta 2026 in season 2026, every other leg zero)
    assert [r["score"] for r in rows] == [60.0, 54.0, 48.0], rows


# ---- (b) bounded inversion between rank and the shown column ---------------
# Grades and star odds chosen so the LARGEST blend-driven leapfrog under the
# shipped W_STAR=10 is 0.3 star x 10 = 3.0 FV of grade, keeping every inversion
# under the 4.0 bound (and the fixture does contain a real 0.5-point inversion,
# so the property is exercised, not vacuous). Under W_STAR=30 the same 0.3-star
# rows leapfrog 9 FV of grade and blow the bound by design.
_POOL = [
    # (key, mlbam, board grade, p_star)
    ("a", 1, 60.0, 0.0),
    ("b", 2, 55.0, 0.3),
    ("f", 6, 53.5, 0.3),   # scores past c on star odds: shown 53.5 above 54.0
    ("c", 3, 54.0, 0.0),
    ("d", 4, 48.0, 0.3),
    ("e", 5, 47.0, 0.0),
]


def _pool_inputs():
    ts = {"players": [_ts_row(k, m) for k, m, _, _ in _POOL]}
    xfv = {"by_player": {k: _xfv_row(g, star=s) for k, m, g, s in _POOL}}
    return ts, xfv


def _bound_violations(rows, bound=INVERSION_BOUND_FV):
    """Every (i, j) pair with i ranked above j, same tier, inside the top 300,
    where the shown eFV contradicts the rank by more than `bound`."""
    out = []
    for i in range(len(rows)):
        if rows[i]["rank"] > 300:
            break
        for j in range(i + 1, len(rows)):
            if rows[j]["rank"] > 300 or rows[i]["tier"] != rows[j]["tier"]:
                continue
            if rows[i]["efv"] < rows[j]["efv"] - bound:
                out.append((rows[i]["mlbam"], rows[j]["mlbam"],
                            rows[i]["efv"], rows[j]["efv"]))
    return out


def test_shown_efv_inversions_are_bounded_within_tier():
    ts, xfv = _pool_inputs()
    rows = fe._dynasty_prospects(ts, 2026, xfv=xfv)
    assert len(rows) == len(_POOL)
    assert {r["tier"] for r in rows} == {"Elite"}, "fixture must stay one tier"
    # the fixture's designed 0.5-point inversion is present (property exercised)
    shown = [r["efv"] for r in rows]
    assert any(b > a for a, b in zip(shown, shown[1:])), shown
    assert _bound_violations(rows) == []


def test_inversion_bound_has_teeth_under_a_tripled_star_weight():
    """Self-proof that the property test can fail: the named mutation
    (dynasty_blend.W_STAR tripled, 10 -> 30) must produce a violation on the
    SAME fixture. If this ever stops breaking, the property above has gone
    vacuous and both tests need a harder fixture."""
    ts, xfv = _pool_inputs()
    original = dynasty_blend.W_STAR
    dynasty_blend.W_STAR = original * 3
    try:
        rows = fe._dynasty_prospects(ts, 2026, xfv=xfv)
        assert _bound_violations(rows), (
            "tripling W_STAR no longer violates the bound; the fixture has "
            "lost its teeth")
    finally:
        dynasty_blend.W_STAR = original


if __name__ == "__main__":
    import sys
    mod = sys.modules[__name__]
    fns = [f for n, f in vars(mod).items() if n.startswith("test_") and callable(f)]
    for f in fns:
        f()
    print(f"ALL {len(fns)} dynasty rank-basis tests PASS")
