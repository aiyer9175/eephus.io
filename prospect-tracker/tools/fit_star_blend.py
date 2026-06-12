# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Star mean-blend fitter (the Phase-1 disclosed-miss follow-up).

proj_lgbm_v1 shipped with a known miss: long-horizon medians run ~0.2
WAR deeper than the champion on the STAR slice (base-season WAR >= 4)
because zero-inflated labels pull q50 toward the attrition mass. The
registry-recorded fix candidates were a mean head or a star-slice
recalibration; this is the latter, WITHOUT retraining:

  q50' = q50 + lambda_h * (implied_mean - q50)   [star rows only]

implied_mean = the trapezoid mean of the five existing quantile heads -
the right-tail mass the median ignores. The star gate is EX-ANTE (the
star_l1 feature: base-season WAR >= 4, observable at prediction time).

PROTOCOL (the Phase-1 discipline):
  fit      lambda_h per horizon by grid on the DEV bases (2017-2021,
           forward-chained: per base B the heads train on labels <= B-1).
           Objective: minimize |star bias|; guard: star MAE must not
           degrade by more than 0.02 and pooled MAE is untouched by
           construction (non-star rows never blend).
  confirm  the blended bundle re-runs --gate1 targets and the holdout
           through tools/train_proj_models.eval_bases (predict_path
           applies the blend from bundle meta automatically).
  ship     lambdas land in data/proj_star_blend.json + the live bundle
           meta (train hash unchanged - the heads are untouched).

Run: python tools/fit_star_blend.py          (fit on dev, write JSON)
     python tools/fit_star_blend.py --apply  (stamp the live bundle meta)
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import fa_projection as fp                                    # noqa: E402
import proj_ml                                                # noqa: E402

log = logging.getLogger(__name__)
OUT = ROOT / "data" / "proj_star_blend.json"

DEV_BASES = (2017, 2018, 2019, 2021)
LAMBDA_GRID = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
SEASON_IDX = 16          # feature_names index of season_idx (= base)
STAR_IDX = proj_ml._STAR_FLAG_IDX
MAE_GUARD = 0.02         # star MAE may not degrade by more than this


def _collect(corpus) -> dict:
    """Per (side, h): arrays of the five quantile predictions + actuals
    for STAR rows on the dev bases, predictions from heads trained
    forward-chained (labels <= B-1)."""
    frame = proj_ml.build_training_frame(corpus, min(DEV_BASES),
                                         corpus["last"] - 1)
    out = {s: {h: {"q": [], "y": []} for h in range(1, proj_ml.HORIZONS + 1)}
           for s in ("hit", "pit")}
    for B in DEV_BASES:
        models = proj_ml.train(corpus, max_label_season=B - 1)
        for side in ("hit", "pit"):
            f = frame[side]
            base_mask = f["X"][:, SEASON_IDX] == B
            star_mask = base_mask & (f["X"][:, STAR_IDX] >= 1.0)
            if not star_mask.any():
                continue
            Xs = f["X"][star_mask]
            star_rows = set(np.flatnonzero(star_mask).tolist())
            preds = {}
            for h in range(1, proj_ml.HORIZONS + 1):
                heads = models[side].get(h)
                if not heads:
                    continue
                qp = np.stack([heads[q].predict(Xs)
                               for q in proj_ml.QUANTILES], axis=1)
                qp.sort(axis=1)                       # monotone per row
                preds[h] = qp
            # labels: rows arrays index into X; map star row -> position
            pos_of = {r: i for i, r in enumerate(np.flatnonzero(star_mask).tolist())}
            for h in range(1, proj_ml.HORIZONS + 1):
                if h not in preds:
                    continue
                rows_h = f["rows"][h]
                y_h = f["y"][h]
                for j, r in enumerate(rows_h.tolist()):
                    if r in star_rows:
                        out[side][h]["q"].append(preds[h][pos_of[r]])
                        out[side][h]["y"].append(float(y_h[j]))
        log.info("collected dev base %d", B)
    return out


def fit() -> dict:
    corpus = fp.build_corpus()
    coll = _collect(corpus)
    # pool sides per horizon (the miss was measured pooled)
    blend, table = {}, {}
    for h in range(1, proj_ml.HORIZONS + 1):
        Q = (np.array([q for s in ("hit", "pit") for q in coll[s][h]["q"]])
             if any(coll[s][h]["q"] for s in ("hit", "pit")) else None)
        if Q is None or not len(Q):
            continue
        y = np.array([v for s in ("hit", "pit") for v in coll[s][h]["y"]])
        mean = (Q[:, 0] + 2 * Q[:, 1] + 2 * Q[:, 2] + 2 * Q[:, 3] + Q[:, 4]) / 8.0
        q50 = Q[:, 2]
        base_bias = float(np.mean(q50 - y))
        base_mae = float(np.mean(np.abs(q50 - y)))
        best = (0.0, base_bias, base_mae)
        for lam in LAMBDA_GRID[1:]:
            p = q50 + lam * (mean - q50)
            bias = float(np.mean(p - y))
            mae = float(np.mean(np.abs(p - y)))
            if mae <= base_mae + MAE_GUARD and abs(bias) < abs(best[1]):
                best = (lam, bias, mae)
        blend[str(h)] = best[0]
        table[str(h)] = {"n_star": int(len(y)),
                         "bias_before": round(base_bias, 4),
                         "bias_after": round(best[1], 4),
                         "mae_before": round(base_mae, 4),
                         "mae_after": round(best[2], 4),
                         "lambda": best[0]}
    ship = any(v > 0 for v in blend.values())
    out = {
        "fitted_at": "2026-06-11",
        "protocol": "forward-chained dev bases 2017-2021; star slice = "
                    "base-season WAR >= 4 (ex-ante star_l1); lambda grid "
                    f"{list(LAMBDA_GRID)}; guard: star MAE +{MAE_GUARD} max; "
                    "pooled MAE untouched by construction (non-star rows "
                    "never blend)",
        "lambda_by_horizon": blend,
        "dev_table": table,
        "ship": ship,
    }
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    log.info("wrote %s", OUT)
    return out


def apply_to_bundle() -> None:
    """Stamp the fitted lambdas into the LIVE bundle meta (heads
    untouched; train hash unchanged - recorded in meta)."""
    import joblib
    d = json.loads(OUT.read_text(encoding="utf-8"))
    if not d.get("ship"):
        log.warning("blend fit says ship=False - not applying")
        return
    p = proj_ml.MODEL_DIR / "models.joblib"
    models = joblib.load(p)
    models["meta"]["star_blend"] = d["lambda_by_horizon"]
    models["meta"]["star_blend_note"] = ("post-hoc star mean blend "
                                         "(tools/fit_star_blend.py); heads "
                                         "untouched, train hash unchanged")
    joblib.dump(models, p, compress=3)
    (proj_ml.MODEL_DIR / "meta.json").write_text(
        json.dumps(models["meta"], indent=1), encoding="utf-8")
    log.info("stamped star_blend into %s", p)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if "--apply" in sys.argv:
        apply_to_bundle()
    else:
        rep = fit()
        print(json.dumps(rep["dev_table"], indent=1))
        print("lambdas:", rep["lambda_by_horizon"], "| ship:", rep["ship"])
