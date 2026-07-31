# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""WAR-projection ML challenger guards (model-audit Phase 1, WS-1):
feature-schema alignment, quantile monotonicity, champion pinning, the
no-zero-floor contract, and (when a bundle is shipped) determinism +
registry linkage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import fa_projection as fp
import proj_ml

ROOT = Path(__file__).parent


def _toy_history(side: str):
    if side == "hit":
        return [{"mlbam": 1, "season": 2025, "age": 27, "role": "H", "pa": 600,
                 "k_pct": 0.20, "bb_pct": 0.10, "iso": 0.200, "babip": 0.300,
                 "hr_pa": 0.04, "war": 4.0},
                {"mlbam": 1, "season": 2024, "age": 26, "role": "H", "pa": 580,
                 "k_pct": 0.21, "bb_pct": 0.09, "iso": 0.190, "babip": 0.295,
                 "hr_pa": 0.035, "war": 3.5}]
    return [{"mlbam": 2, "season": 2025, "age": 27, "role": "SP", "bf": 750,
             "ip": 180.0, "k_pct": 0.28, "bb_pct": 0.07, "hr_bf": 0.03,
             "fip": 3.40, "war": 3.8},
            {"mlbam": 2, "season": 2024, "age": 26, "role": "SP", "bf": 700,
             "ip": 165.0, "k_pct": 0.27, "bb_pct": 0.08, "hr_bf": 0.032,
             "fip": 3.60, "war": 3.2}]


@pytest.fixture(scope="module")
def fitted():
    corpus = fp.build_corpus()
    curves, war_map = fp.fitted_models(corpus, 2025)
    return corpus, curves, war_map


def test_feature_vector_matches_schema(fitted):
    corpus, curves, war_map = fitted
    for side in ("hit", "pit"):
        feats = proj_ml.build_features(_toy_history(side), side, 2026, 28.0,
                                       curves, war_map, corpus["league"])
        assert feats is not None
        names = proj_ml.feature_names(side)
        assert len(feats) == len(names), (side, len(feats), len(names))
        # champion stack features present and ordered last
        champ = feats[-proj_ml.HORIZONS:]
        assert all(isinstance(v, float) for v in champ)
        assert champ[0] > 0.5                       # a 4-WAR vet projects positive


def test_no_population_drift_vs_champion(fitted):
    """build_features returns None exactly when the champion can't project
    — challenger and champion always score the same population."""
    corpus, curves, war_map = fitted
    assert proj_ml.build_features([], "hit", 2026, 28.0, curves, war_map,
                                  corpus["league"]) is None


def test_def_prior_leakage_shrink_and_missing(monkeypatch):
    """The defensive prior reads ONLY completed seasons base-1..3 (leakage-free,
    same window as the WAR lags), reliability-shrinks per-650 by PA exposure, and
    flags players with no MLB defensive history."""
    hist = {
        "10:2023": {"war_def": 2.0, "runs_position": 3.0, "pa": 600},
        "10:2022": {"war_def": 2.0, "runs_position": 3.0, "pa": 600},
        "10:2021": {"war_def": 2.0, "runs_position": 3.0, "pa": 600},
        # base-year season: a (fake) collapse that must NEVER enter a base-2024 read
        "10:2024": {"war_def": -9.0, "runs_position": -9.0, "pa": 600},
    }
    monkeypatch.setattr(proj_ml, "_DEF_HIST_CACHE", hist)
    p = proj_ml._def_prior(10, 2024)            # reads 2023/2022/2021 only
    assert p["def_missing"] == 0.0
    # leakage trap: the negative 2024 season must not pull the prior down
    assert p["pos_adj_prior"] > 1.0
    # exact shrink: sum_pos 9 * 650 / (sum_pa 1800 + shrink 600)
    assert abs(p["pos_adj_prior"] - (9 * 650.0 / (1800 + proj_ml._DEF_SHRINK_PA))) < 1e-6
    # no history -> missing flag, zero prior
    assert proj_ml._def_prior(999, 2024) == {
        "def_war_prior": 0.0, "pos_adj_prior": 0.0, "def_missing": 1.0}


def test_def_prior_is_hit_only_and_shipped():
    """pos_adj_prior is in the HIT schema only (defense ~ irrelevant to the pitcher
    WAR target), and ships in DEF_FEATURE_KEYS (gate-validated 2026-06-29)."""
    assert "pos_adj_prior" in proj_ml.feature_names("hit")
    assert "pos_adj_prior" not in proj_ml.feature_names("pit")
    assert proj_ml.DEF_FEATURE_KEYS == ("pos_adj_prior",)


def test_predict_path_quantiles_monotone_and_unfloored(fitted):
    """Quantile heads must come back sorted (q10<=...<=q90) and the floor
    contract is NO floor: synthetic models that cross + go negative are
    sorted, not clipped."""
    class _Stub:
        def __init__(self, v):
            self.v = v
        def predict(self, x):
            return [self.v]
    models = {"meta": {"quantiles": list(proj_ml.QUANTILES)},
              "hit": {h: {0.10: _Stub(0.5), 0.25: _Stub(-1.2), 0.50: _Stub(1.0),
                          0.75: _Stub(0.8), 0.90: _Stub(2.0)}
                      for h in range(1, proj_ml.HORIZONS + 1)}}
    out = proj_ml.predict_path(models, [0.0] * 10, "hit")
    assert out["war_by_year_p10"][0] == -1.2        # negative survives (no floor)
    for h in range(proj_ml.HORIZONS):
        assert (out["war_by_year_p10"][h] <= out["war_by_year_p25"][h]
                <= out["war_by_year"][h] <= out["war_by_year_p75"][h]
                <= out["war_by_year_p90"][h])


def test_champion_pinned_in_eval_baseline():
    """proj_eval's default predict_fn must pass use_ml=False — the
    champion baseline can never silently become the ML model."""
    import inspect
    import proj_eval
    src = inspect.getsource(proj_eval.default_predict_fn)
    assert "use_ml=False" in src


def test_ml_config_gate_defaults_off_until_shipped():
    """projection.ml.enabled may only be true when a bundle is committed
    (the ship decision flips both together)."""
    import fa_class
    cfg = (fa_class.get_config().get("projection") or {}).get("ml") or {}
    bundle = (ROOT / "model" / "proj_lgbm" / "models.joblib").exists()
    if cfg.get("enabled"):
        assert bundle, "ml enabled but no committed bundle"
        meta = json.loads((ROOT / "model" / "proj_lgbm" / "meta.json")
                          .read_text(encoding="utf-8"))
        assert meta.get("train_hash"), "bundle missing training-data hash"
        # the registry must record the shipped challenger
        reg = json.loads((ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))
        row = next(m for m in reg["models"] if m["model_id"] == "fa_war_paths_decay")
        assert proj_ml.MODEL_VERSION.split("_v")[0] in str(row.get("champion", "")) or \
            "lgbm" in str(row.get("champion", "")).lower(), \
            "registry champion not updated for the shipped ML model"


def test_training_frame_no_lookahead_property(fitted):
    """Every label season in a frame respects <= max_label_season — the
    forward-chaining contract, asserted on a small real frame."""
    corpus, *_ = fitted
    frame = proj_ml.build_training_frame(corpus, first_base=2018,
                                         max_label_season=2019, use_cache=False)
    for side in ("hit", "pit"):
        for h in range(1, proj_ml.HORIZONS + 1):
            ls = frame[side]["label_season"][h]
            if len(ls):
                assert ls.max() <= 2019, (side, h, int(ls.max()))
            assert len(ls) == len(frame[side]["rows"][h])


def test_star_blend_pinned_to_artifact():
    """The live bundle's star_blend meta must match the committed
    data/proj_star_blend.json lambdas — and only horizons that survived
    holdout confirmation (or were honestly disclosed as unconfirmable)
    may carry a positive lambda. h2 FAILED confirmation 2026-06-11 and
    must stay 0/absent."""
    art_p = ROOT / "data" / "proj_star_blend.json"
    meta_p = ROOT / "model" / "proj_lgbm" / "meta.json"
    if not (art_p.exists() and meta_p.exists()):
        pytest.skip("star blend not shipped")
    art = json.loads(art_p.read_text(encoding="utf-8"))
    meta = json.loads(meta_p.read_text(encoding="utf-8"))
    lam = {k: v for k, v in art["lambda_by_horizon"].items() if v > 0}
    stamped = {k: v for k, v in (meta.get("star_blend") or {}).items() if v > 0}
    assert stamped == lam, (stamped, lam)
    # h2 failed the 2022-24 holdout confirmation - it may never blend
    assert lam.get("2", 0.0) == 0.0
    # anything shipped must be recorded as confirmed or disclosed
    assert art.get("ship") is True
    assert "holdout_confirmation" in art


def test_mean_blend_pinned_to_artifact():
    """P-MBLEND regression guard. The GLOBAL lift-only recenter in
    data/proj_mean_blend.json is registered as SHIPPED, but for a month the
    live bundle carried no `mean_blend` key at all, so predict_path's
    `gblend` block read None and the recenter was inert in production while
    every lane benchmarked against an injected copy of it. star_blend had
    this exact test and never drifted; the mean blend had none, which is
    why nobody noticed. Bundle meta and artifact must agree, both ways."""
    art_p = ROOT / "data" / "proj_mean_blend.json"
    meta_p = ROOT / "model" / "proj_lgbm" / "meta.json"
    if not (art_p.exists() and meta_p.exists()):
        pytest.skip("mean blend not shipped")
    art = json.loads(art_p.read_text(encoding="utf-8"))
    meta = json.loads(meta_p.read_text(encoding="utf-8"))
    lam = {str(k): float(v) for k, v in art["lambda_by_horizon"].items() if v > 0}
    stamped = {str(k): float(v)
               for k, v in (meta.get("mean_blend") or {}).items() if v > 0}
    assert stamped == lam, (
        "bundle meta.mean_blend does not match data/proj_mean_blend.json - "
        "run tools/apply_mean_blend.py --apply", stamped, lam)
    # every shipped lambda must carry holdout evidence or an explicit disclosure
    hold = art.get("holdout_2022_2024") or {}
    for h in lam:
        assert h in hold or "disclosed_residual" in art, h


def test_pitcher_ip_proj_tracks_aged_exposure():
    """P-IPAGE regression guard. The pitcher BF exposure (pt_proj) is aged by
    the fitted pt curve; ip_proj used to be stamped BEFORE that delta, so
    war_from_projection (which reads ip_proj alone) never saw the aging and
    the FIP algebra divided an aged numerator by an un-aged denominator.
    rate_path's docstring already asserts the invariant restored here."""
    import os
    corpus = fp.build_corpus()
    curves, _ = fp.fitted_models(corpus, corpus["last"] - 1)
    hist = _toy_history("pit")
    prev = os.environ.get("EEPHUS_PIT_IP_AGE")
    os.environ["EEPHUS_PIT_IP_AGE"] = "1"
    try:
        proj = fp.project_player(hist, "pit", 2026, curves, corpus["league"], 38)
    finally:
        if prev is None:
            os.environ.pop("EEPHUS_PIT_IP_AGE", None)
        else:
            os.environ["EEPHUS_PIT_IP_AGE"] = prev
    assert proj is not None
    assert abs(proj["pt_proj"] - 4.3 * proj["ip_proj"]) <= 0.5, (
        proj["pt_proj"], proj["ip_proj"])
