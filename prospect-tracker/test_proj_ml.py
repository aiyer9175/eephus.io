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
