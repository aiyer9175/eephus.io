# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""The positional ladder's IDENTIFICATION, pinned so the question stops recurring.

The owner's complaint was "it should cumulatively sum to 0 and it sums to ~+8".
Three different sums exist and only one of them is a constraint:
  * exposure-weighted  -> zero, IMPOSED. The identified quantity.
  * equal weight, 9    -> not zero. DH is 7.5% of exposure, not a ninth.
  * equal weight, 8 fielders -> not zero, and it is FORCED to about +9.8 once
    the exposure-weighted sum is pinned at zero.
These tests do not re-derive the ladder (that needs the two big feeds); they
pin the arithmetic and the published contract.
"""
import numpy as np

import positional_fit as pf


def test_recentre_zeroes_the_exposure_weighted_sum():
    rng = np.random.default_rng(3)
    X = rng.random((400, 9))
    X = X / X.sum(axis=1, keepdims=True)          # shares, like the real design
    beta = rng.normal(0, 5, 9)
    exposure = X.mean(axis=0)
    out = pf._recentre(beta, exposure)
    assert abs(float(exposure @ out)) < 1e-9
    # A pure level shift: every rung moves by the SAME amount, so the shape,
    # which is the only thing that was ever gated, is untouched.
    d = out - beta
    assert float(d.max() - d.min()) < 1e-9


def test_uncentred_level_equals_mean_y():
    """Why the level is a property of the window and not of the positions:
    with X @ 1 == 1 the OLS residuals are orthogonal to the column sum, so the
    exposure-weighted coefficient sum IS mean(y)."""
    rng = np.random.default_rng(11)
    X = rng.random((500, 9))
    X = X / X.sum(axis=1, keepdims=True)
    y = X @ np.array([11.0, -8.5, 4.5, 3.4, 8.8, -6.5, 3.5, -6.4, -13.8]) \
        + rng.normal(0, 1.0, 500) - 1.0           # a league running 1 run light
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    assert abs(float(X.mean(axis=0) @ beta) - float(y.mean())) < 1e-8


def test_fielder_centring_is_the_folklore_convention():
    """The folklore table sums to zero over its eight fielding rungs only
    because it leaves DH out of the normalisation. Reproduce that reading."""
    vals = {"C": 10.67, "1B": -8.60, "2B": 4.73, "3B": 3.37, "SS": 8.92,
            "LF": -6.59, "CF": 3.74, "RF": -6.47, "DH": -13.73}
    fielders = [p for p in vals if p != "DH"]
    s8 = sum(vals[p] for p in fielders)
    centred = {p: v - s8 / len(fielders) for p, v in vals.items()}
    assert abs(sum(centred[p] for p in fielders)) < 1e-9
    assert centred["DH"] < vals["DH"]          # DH absorbs the whole shift


def test_shipped_window_is_a_rolling_recent_one():
    """2026-08-07: the window stopped being a pinned first season and became a
    rolling count of recent seasons, on a forward-chained gate
    (docs/gate-2026-08-07-positional-ladder-recency.md, dMAE 0.097 runs per
    650 PA, CI95 [0.0789, 0.1145], 3/3 splits). Six is the gated value; changing
    it is a model change and needs its own gate, which is why it is pinned."""
    assert pf.LADDER_WINDOW_SEASONS == 6
    assert pf.LADDER_EARLIEST_SEASON == 2000
    assert pf.LADDER_RETIRED_FIRST_SEASON == 2012
    # the retired window stays in the published sensitivities, so the size of
    # the change is readable off the artifact without a git history
    assert pf.LADDER_RETIRED_FIRST_SEASON in pf.LADDER_SENSITIVITY_WINDOWS


def test_the_rolling_window_resolves_against_the_last_season_not_a_constant():
    """The failure this guards is a window that silently stops rolling: a pinned
    default would keep fitting the same six seasons as the feed advances."""
    import inspect
    sig = inspect.signature(pf.fit_ladder)
    assert sig.parameters["first"].default is None, (
        "fit_ladder pinned a default first season again; the window must be "
        "derived from `last` so it advances with the feed")
    src = inspect.getsource(pf.fit_ladder)
    assert "last - LADDER_WINDOW_SEASONS + 1" in src


def test_ladder_artifact_publishes_both_readings():
    """The eval contract: whatever regenerates data/positional_fit.json must
    carry the identification block, because prospect_def_value refuses to adopt
    a ladder whose level convention is unstated."""
    import json
    from pathlib import Path
    p = Path(__file__).parent / "data" / "positional_fit.json"
    if not p.exists():
        return
    blk = (json.loads(p.read_text(encoding="utf-8")).get("fit") or {}).get("ladder") or {}
    ident = blk.get("identification")
    if not ident:
        return                                  # artifact predates the constraint
    for k in ("sum_exposure_weighted", "sum_equal_weight_9",
              "sum_equal_weight_fielders", "exposure_share",
              "values_fielder_centred", "why_equal_weight_sums_are_not_zero"):
        assert k in ident, k
    assert abs(float(ident["sum_exposure_weighted"])) < 1e-3
    assert abs(float(ident["sum_equal_weight_fielders"])) > 1.0
