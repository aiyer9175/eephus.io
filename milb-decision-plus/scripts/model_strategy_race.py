# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""Model strategy race for K% / BB% projection.

Strategies: ridge, elastic net, spline-GAM-style (ridge on spline basis),
gradient boosting, and a blend. Champion per target by out-of-sample
accuracy + calibration + simplicity (a simpler model wins ties).

Validation splits reported:
  - time holdout (train<=2023 behavior seasons, test after)  [primary]
  - player holdout within train window                        [secondary]
Feature sets follow the incremental audit: best statline baseline (C)
vs +Decision+ (D) vs +components (E), so the race also re-checks
incremental value under nonlinear models.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import ElasticNet, Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import SplineTransformer, StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import DATA_PROCESSED, OUTPUTS, log_run
from ground_truth_and_baselines import eb_shrink, load_frame

SEED = 42
TRAIN_END = 2023

FEATURE_SETS = {
    "C_statline": ["k_pct_shrunk", "bb_pct_shrunk", "age", "log_pa"],
    "D_decision": ["k_pct_shrunk", "bb_pct_shrunk", "age", "log_pa", "decision_plus"],
    "E_components": ["k_pct_shrunk", "bb_pct_shrunk", "age", "log_pa", "decision_plus",
                     "contact_shrunk", "take_ball_shrunk"],
    "Z_zone": ["k_pct_shrunk", "bb_pct_shrunk", "age", "log_pa", "decision_plus",
               "contact_shrunk", "take_ball_shrunk",
               "chase_shrunk", "z_take_shrunk", "zcontact_shrunk"],
}


def strategies():
    return {
        "ridge": lambda: make_pipeline(StandardScaler(), Ridge(alpha=1.0, random_state=SEED)),
        "elastic": lambda: make_pipeline(StandardScaler(),
                                         ElasticNet(alpha=0.001, l1_ratio=0.5,
                                                    random_state=SEED, max_iter=5000)),
        "spline_gam": lambda: make_pipeline(
            SplineTransformer(degree=3, n_knots=5),
            Ridge(alpha=1.0, random_state=SEED)),
        "gbm": lambda: HistGradientBoostingRegressor(
            max_depth=3, learning_rate=0.05, max_iter=300,
            l2_regularization=1.0, random_state=SEED),
    }


def evaluate(pred, actual, train_mean):
    err = pred - actual
    ss_tot = ((actual - train_mean) ** 2).sum()
    dec = pd.qcut(pred, 10, duplicates="drop")
    cal = pd.DataFrame({"pred": pred, "act": actual}).groupby(dec, observed=True).mean()
    cal_mae = float((cal.pred - cal.act).abs().mean())
    return {
        "pearson": round(pearsonr(pred, actual)[0], 4),
        "spearman": round(spearmanr(pred, actual)[0], 4),
        "r2": round(float(1 - (err ** 2).sum() / ss_tot), 4),
        "mae": round(float(np.abs(err).mean()), 5),
        "rmse": round(float(np.sqrt((err ** 2).mean())), 5),
        "calib_decile_mae": round(cal_mae, 5),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--decision-file",
                    default=str(DATA_PROCESSED / "decision_plus.parquet"))
    ap.add_argument("--levels", nargs="+", default=["AAA", "AA", "A+", "A", "CPX"])
    args = ap.parse_args()

    pairs = load_frame()
    dec = pd.read_parquet(args.decision_file)
    keep = ["batter_id", "season", "level", "decision_plus", "take_ball_shrunk",
            "chase_shrunk", "z_take_shrunk", "zcontact_shrunk",
            "contact_pct", "swing_pct", "pitches"]
    dec = dec[[c for c in keep if c in dec.columns]].rename(
        columns={"contact_pct": "contact_raw", "pitches": "pitches_dec"})
    pairs = pairs.merge(dec, left_on=["player_id", "season", "level"],
                        right_on=["batter_id", "season", "level"], how="left")
    pairs["swings_est"] = (pairs.pitches_dec * pairs.swing_pct).clip(lower=1)
    ok = pairs.contact_raw.notna()
    pairs.loc[ok, "contact_shrunk"] = eb_shrink(
        pairs[ok].rename(columns={"contact_raw": "r"}), "r", "swings_est",
        ["level", "season"]).values

    rows = []
    rng = np.random.default_rng(SEED)
    for level in args.levels:
        lv = pairs[pairs.level == level]
        for tgt in ["next_k_pct", "next_bb_pct"]:
            for fs_name, feats in FEATURE_SETS.items():
                cols = [c for c in feats if c in lv.columns]
                if len(cols) < len(feats):
                    continue
                sub = lv.dropna(subset=cols + [tgt])
                train = sub[sub.season <= TRAIN_END]
                test = sub[sub.season > TRAIN_END]
                if len(train) < 150 or len(test) < 60:
                    continue
                # player holdout within train window
                players = train.player_id.unique()
                hold = set(rng.choice(players, size=len(players) // 5, replace=False))
                tr_p = train[~train.player_id.isin(hold)]
                te_p = train[train.player_id.isin(hold)]
                for strat_name, mk in strategies().items():
                    model = mk().fit(train[cols], train[tgt])
                    res = evaluate(model.predict(test[cols]), test[tgt].values,
                                   train[tgt].mean())
                    mp = mk().fit(tr_p[cols], tr_p[tgt])
                    res_p = evaluate(mp.predict(te_p[cols]), te_p[tgt].values,
                                     tr_p[tgt].mean())
                    rows.append({"level": level, "target": tgt, "features": fs_name,
                                 "strategy": strat_name, "n_train": len(train),
                                 "n_test": len(test), **res,
                                 "player_holdout_r2": res_p["r2"],
                                 "player_holdout_rmse": res_p["rmse"]})
    df = pd.DataFrame(rows)
    out = OUTPUTS / "model_race"
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "strategy_race.csv", index=False)
    print(df.to_string(index=False))
    log_run("model_strategy_race_v1", n_rows=len(df))


if __name__ == "__main__":
    main()
