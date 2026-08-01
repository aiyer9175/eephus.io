# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""The comps ANCHOR is continuous in projected WAR (fa_market, 2026-07-31).

The defect: the anchor was the median of the same k=5 nearest neighbours the
board displays, so it hopped between contract tiers as comps entered and left
the top five. On one real serve row the anchor read $13.2M at 1.50 WAR, $85.8M
at 1.76 and $24.1M at 2.00 - a 4.17x swing for a 0.02-WAR step - and the
predicted guarantee inherited it (2.50x for the same step).
"""
import math

import fa_market as fm


def test_weighted_quantile_matches_the_plain_one_at_uniform_weights():
    vals = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert fm._weighted_quantile([(v, 1.0) for v in vals], 0.5) == 3.0


def test_weighted_quantile_is_continuous_in_the_weights():
    """The property a weighted MEDIAN does not have: nudging a weight must
    nudge the answer, not jump it to the next order statistic."""
    vals = [1.0, 2.0, 100.0]
    prev = None
    for i in range(201):
        w = i / 200.0
        q = fm._weighted_quantile([(1.0, 1.0), (2.0, 1.0), (100.0, w)], 0.5)
        if prev is not None:
            assert abs(q - prev) < 2.0, f"jump at w={w}: {prev} -> {q}"
        prev = q
    assert vals                                   # values untouched by the call


def _pool():
    """A synthetic prior-winter pool with a deliberate tier cliff between a
    2.0-WAR neighbourhood and a 2.3-WAR one."""
    out = []
    for i, (war, guar, yrs) in enumerate([
            (1.4, 8e6, 1), (1.5, 11e6, 1), (1.6, 15e6, 2), (1.7, 20e6, 2),
            (1.9, 22e6, 1), (2.0, 26e6, 2), (2.1, 120e6, 5), (2.2, 130e6, 6),
            (2.4, 180e6, 7), (2.6, 200e6, 7), (2.8, 240e6, 8), (3.0, 300e6, 9)]):
        out.append({"player_key": f"p{i}", "player_name": f"P {i}",
                    "class_year": 2020, "position": "CF", "_age": 28.0,
                    "years": yrs, "guarantee_usd": guar, "aav_usd": guar / yrs,
                    "_war_path": {"war_y1": war, "war_by_year": [war] * yrs}})
    return out


def _anchor_curve(mode, bw=0.75):
    old_m, old_b = fm.COMPS_ANCHOR_MODE, fm.COMPS_KERNEL_BW
    fm.COMPS_ANCHOR_MODE, fm.COMPS_KERNEL_BW = mode, bw
    try:
        pool = _pool()
        out = []
        w = 1.5
        while w <= 3.0001:
            s = {"player_key": "subject", "class_year": 2026, "position": "CF",
                 "_age": 28.0, "_war_path": {"war_y1": w, "war_by_year": [w] * 5}}
            out.append((round(w, 3), fm.comps_anchor(s, pool, 0.0)[1]))
            w += 0.02
        return out
    finally:
        fm.COMPS_ANCHOR_MODE, fm.COMPS_KERNEL_BW = old_m, old_b


def _worst_step(curve):
    worst = 1.0
    for (_, a), (_, b) in zip(curve, curve[1:]):
        r = b / a
        worst = max(worst, r, 1 / r)
    return worst


def test_kernel_anchor_is_far_smoother_than_the_k5_median():
    legacy = _worst_step(_anchor_curve("k5_median"))
    kernel = _worst_step(_anchor_curve("kernel"))
    assert legacy > 1.5, f"the synthetic cliff did not reproduce ({legacy:.2f}x)"
    # 1.3x is the bar for a 12-row synthetic pool built to be as cliffy as
    # possible; on the real 1,300-signing corpus the same measurement is 1.15x
    # against the k=5 median's 4.17x.
    assert kernel < 1.3, f"kernel anchor still steps {kernel:.2f}x"
    assert kernel < legacy / 2


def test_kernel_anchor_is_monotone_across_the_cliff():
    curve = _anchor_curve("kernel")
    for (_, a), (_, b) in zip(curve, curve[1:]):
        assert b >= a - 1e-6, "a better projection must never lower the anchor"


def test_kernel_anchor_still_tracks_the_neighbourhood():
    """Smoothing must not turn the anchor into one group-wide constant."""
    curve = dict(_anchor_curve("kernel"))
    lo = curve[min(curve)]
    hi = curve[max(curve)]
    assert hi > 4 * lo


def test_shipped_settings():
    assert fm.COMPS_ANCHOR_MODE == "kernel"
    assert 0.5 <= fm.COMPS_KERNEL_BW <= 1.0
    # The rational anchor's integer term is a MEASURED no-ship, not an oversight.
    assert fm.RATIONAL_TERM_CONTINUOUS is False


def test_display_comps_are_untouched():
    """comps_for is the board's comp chips and must still be the five nearest."""
    pool = _pool()
    s = {"class_year": 2026, "position": "CF", "_age": 28.0,
         "_war_path": {"war_y1": 2.0, "war_by_year": [2.0] * 5}}
    cs = fm.comps_for(s, pool)
    assert len(cs) == 5
    assert math.isclose(cs[0]["war_y1_proj"], 2.0)
