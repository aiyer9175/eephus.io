"""Risk-adjusted Surplus (Sortino) guards. Downside-only risk from the persisted
eFV surplus fan: a bunched high-floor profile must read safer than a boom/bust
one at the same mean, the $ fields must scale with the shown value while the
ratio stays scale-invariant, and rows without a distribution return nothing.
"""
import bayes_trade_value as b

LOW = {"p10_mm": 30, "p25_mm": 42, "p50_mm": 50, "p75_mm": 62, "p90_mm": 80,
       "mean_mm": 52, "p_bust": 0.06}
BOOM = {"p10_mm": 2, "p25_mm": 8, "p50_mm": 30, "p75_mm": 60, "p90_mm": 110,
        "mean_mm": 40, "p_bust": 0.30}


def test_none_when_no_distribution():
    assert b._sortino_fields(None, 1.0) is None
    assert b._sortino_fields({"mean_mm": 5}, 1.0) is None  # incomplete fan


def test_low_risk_scores_safer_than_boom_bust():
    lo = b._sortino_fields(LOW, 1.0)
    bm = b._sortino_fields(BOOM, 1.0)
    assert lo["sortino"] > bm["sortino"]        # tighter downside = safer
    assert lo["downside_mm"] < bm["downside_mm"]
    assert lo["p_bust"] < bm["p_bust"]


def test_risk_mm_below_mean_and_passes_bust():
    lo = b._sortino_fields(LOW, 1.0)
    assert lo["risk_mm"] < LOW["mean_mm"]       # haircut for downside
    assert lo["p_bust"] == LOW["p_bust"]        # passthrough


def test_dollar_fields_scale_ratio_invariant():
    full = b._sortino_fields(LOW, 1.0)
    half = b._sortino_fields(LOW, 0.5)
    assert abs(half["downside_mm"] - full["downside_mm"] * 0.5) <= 0.11
    assert abs(half["risk_mm"] - full["risk_mm"] * 0.5) <= 0.11
    assert half["sortino"] == full["sortino"]   # ratio is scale-invariant


def test_sortino_capped_and_nonnegative():
    tight = {"p10_mm": 49.9, "p25_mm": 50, "p50_mm": 50, "p75_mm": 50,
             "p90_mm": 50.1, "mean_mm": 50, "p_bust": 0.0}
    f = b._sortino_fields(tight, 1.0)
    assert 0.0 <= f["sortino"] <= 99.0
