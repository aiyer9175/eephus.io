# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Gate-3 + option-pricing guards (model-audit Phase 3): rank-metric math,
the committed artifact's contract, the fitted-weights<->config sync, and
the band-priced P(enter) directionality."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import fa_class
import fa_fit_backtest as g3
import fa_market as fm

ROOT = Path(__file__).parent


def test_rank_metrics_math():
    groups = {
        "a": [{"signed": 0, "x": 0.1}, {"signed": 1, "x": 0.9}, {"signed": 0, "x": 0.5}],
        "b": [{"signed": 1, "x": 0.2}, {"signed": 0, "x": 0.8}, {"signed": 0, "x": 0.5}],
    }
    r = g3._rank_metrics(groups, lambda row: row["x"])
    assert r["n"] == 2
    assert r["top1"] == 0.5                  # winner ranked 1st in 'a', 3rd in 'b'
    assert r["top3"] == 1.0
    assert r["mrr"] == pytest.approx((1.0 + 1 / 3) / 2, abs=1e-3)


def test_leverage_peaks_at_center():
    assert g3._leverage(86) > g3._leverage(70)
    assert g3._leverage(86) > g3._leverage(102)
    assert g3._leverage(None) == 0.5


def test_gate3_artifact_contract():
    p = ROOT / "data" / "fa_gate3_eval.json"
    if not p.exists():
        pytest.skip("gate3 artifact not generated on this machine")
    d = json.loads(p.read_text(encoding="utf-8"))
    res = d["results"]
    for model in ("random", "payroll_only", "behavior_only", "live_analog",
                  "fitted_transfer", "fitted_full"):
        assert model in res, model
        assert res[model]["n"] > 500
        assert 0 <= res[model]["mrr"] <= 1
    # the documented findings can't silently vanish from the artifact
    assert res["fitted_full"]["mrr"] > res["fitted_transfer"]["mrr"], \
        "incumbency ceiling note no longer holds — re-examine"
    assert any("REDUCED-FEATURE ANALOG" in n for n in d["notes"])


def test_shipped_weights_match_gate3_decision():
    """The live fit weights must equal the artifact's committed ship
    decision (shipped_balanced — gate-equivalent-or-better than the
    fitted logistic AND player-discriminative; see ship_decision)."""
    p = ROOT / "data" / "fa_gate3_eval.json"
    if not p.exists():
        pytest.skip("gate3 artifact not generated on this machine")
    d = json.loads(p.read_text(encoding="utf-8"))
    shipped = d["weight_mix_comparison"]["shipped_balanced"]
    weights = fa_class.get_config()["fit"]["weights"]
    assert abs(sum(weights.values()) - 1.0) < 0.02
    for k, v in shipped["weights"].items():
        assert weights[k] == pytest.approx(v, abs=0.01), (k, weights[k], v)
    # the shipped mix must remain gate-equivalent-or-better vs the logistic
    assert shipped["mrr"] >= d["weight_mix_comparison"]["fitted_logistic"]["mrr"]
    assert "player-discriminative" in d["ship_decision"]


def test_enter_probability_v2_directionality():
    pred = {"proj_aav_usd": 20_000_000, "proj_aav_p10_usd": 12_000_000,
            "proj_aav_p90_usd": 33_000_000}
    # player option priced WELL below market -> player walks (enter ~1)
    lo = fm.enter_probability_v2(pred, "player_option", 8_000_000)
    assert lo["enter_prob"] > 0.85
    # player option priced WELL above market -> player takes it (enter ~0)
    hi = fm.enter_probability_v2(pred, "player_option", 45_000_000)
    assert hi["enter_prob"] < 0.15
    # club option flips the comparison
    club_cheap = fm.enter_probability_v2(pred, "club_option", 8_000_000)
    assert club_cheap["enter_prob"] < 0.15           # bargain -> club exercises
    club_rich = fm.enter_probability_v2(pred, "club_option", 45_000_000)
    assert club_rich["enter_prob"] > 0.85            # overpriced -> declined
    # mutual/conditional types and missing bands pass through to v1
    assert fm.enter_probability_v2(pred, "mutual_option", 20_000_000) is None
    assert fm.enter_probability_v2({}, "player_option", 20_000_000) is None


def test_gate_scores_the_weights_that_actually_ship():
    """The team-fit gate must score the SHIPPED weight vector, not a stale copy.

    REGRESSION GUARD, 2026-07-25. fa_fit_backtest.LIVE_WEIGHTS was a hard-coded
    literal labelled "(fa_config fit.weights)" that had silently diverged from it:
    it carried the retired hand_v2 mix {need .31, window .19, afford .22, park .04,
    behavior .24} while fa_config.fit.weights read {need .40, window .05, afford .05,
    park .05, behavior .45}. Every `live_analog` number and all four registered
    verdicts therefore described a model that never shipped, and the registered
    verdict live_analog_beats_behavior_only=False flipped to TRUE once the gate
    scored the real thing (shipped MRR 0.1673 vs hand_v2 0.1418, n=1,173, shipped
    better in 7 of 9 winters).

    LIVE_WEIGHTS now reads fa_config, so the two cannot drift apart. This test fails
    if anyone re-hardcodes it."""
    import yaml
    from pathlib import Path

    import fa_fit_backtest as fbt

    cfg = yaml.safe_load(
        (Path(__file__).parent / "fa_config.yaml").read_text(encoding="utf-8"))
    shipped = {k: float(v) for k, v in cfg["fit"]["weights"].items()}
    assert fbt.LIVE_WEIGHTS == shipped, (
        f"gate weights {fbt.LIVE_WEIGHTS} != shipped fa_config.fit.weights {shipped}; "
        f"the gate is scoring a model that does not ship")
    assert abs(sum(fbt.LIVE_WEIGHTS.values()) - 1.0) < 1e-9
    assert set(fbt.LIVE_WEIGHTS) == set(fbt.FEATS)
