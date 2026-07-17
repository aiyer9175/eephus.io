# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""Level translation framework: MiLB rates -> MLB-equivalent rates.

Two ingredients, both leak-free and statline-only:
  1. Promotion regressions per from-level (AAA->MLB on full 2008+ history):
     future MLB K%/BB% ~ current-level K%/BB% + age. Time-based holdout.
  2. Within-player same-season multi-level offsets (the level ladder):
     a player who plays two levels in one season measures the level gap
     directly; PA-weighted mean differences give additive offsets.

No MLB swing-decision model is used anywhere as an input or target here
(framework circularity rule).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr
from sklearn.linear_model import LinearRegression

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import DATA_PROCESSED, LEVEL_ORDER, OUTPUTS, log_run

TRAIN_END = 2020  # promotion pairs: train on seasons <= this, test on later


def promotion_models() -> pd.DataFrame:
    pairs = pd.read_parquet(DATA_PROCESSED / "milb_to_mlb_pairs.parquet")
    pairs = pairs[(pairs.pa >= 200) & (pairs.mlb_pa >= 100)].dropna(subset=["age"])
    rows = []
    preds_frames = []
    for level, g in pairs.groupby("level"):
        train, test = g[g.season <= TRAIN_END], g[g.season > TRAIN_END]
        for tgt, feats in [("mlb_k_pct", ["k_pct", "age"]),
                           ("mlb_bb_pct", ["bb_pct", "age"])]:
            if len(train) < 80 or len(test) < 40:
                continue
            lr = LinearRegression().fit(train[feats], train[tgt],
                                        sample_weight=train.mlb_pa)
            pred = lr.predict(test[feats])
            err = pred - test[tgt]
            ss_tot = ((test[tgt] - train[tgt].mean()) ** 2).sum()
            rows.append({
                "from_level": level, "target": tgt,
                "n_train": len(train), "n_test": len(test),
                "pearson": round(pearsonr(pred, test[tgt])[0], 4),
                "spearman": round(spearmanr(pred, test[tgt])[0], 4),
                "r2": round(float(1 - (err ** 2).sum() / ss_tot), 4),
                "mae": round(float(err.abs().mean()), 5),
                "rmse": round(float(np.sqrt((err ** 2).mean())), 5),
                "coef": {f: round(c, 4) for f, c in zip(feats, lr.coef_)},
                "intercept": round(float(lr.intercept_), 4),
            })
            tp = test[["player_id", "season", "level", "mlb_season"]].copy()
            tp["target"], tp["actual"], tp["pred"] = tgt, test[tgt].values, pred
            preds_frames.append(tp)
    pd.concat(preds_frames, ignore_index=True).to_csv(
        OUTPUTS / "translation" / "promotion_test_predictions.csv", index=False)
    return pd.DataFrame(rows)


def ladder_offsets() -> pd.DataFrame:
    """Same-season within-player level offsets for K% and BB%."""
    spine = pd.read_parquet(DATA_PROCESSED / "statline_spine.parquet")
    spine = spine[spine.pa >= 100]
    s = spine.merge(spine, on=["player_id", "season"], suffixes=("_lo", "_hi"))
    s = s[s.level_lo.map(LEVEL_ORDER) < s.level_hi.map(LEVEL_ORDER)]
    s["w"] = np.minimum(s.pa_lo, s.pa_hi)
    rows = []
    for (lo, hi), g in s.groupby(["level_lo", "level_hi"]):
        if len(g) < 30:
            continue
        rows.append({
            "from_level": lo, "to_level": hi, "n_players": len(g),
            "k_pct_offset": round(float(np.average(g.k_pct_hi - g.k_pct_lo, weights=g.w)), 4),
            "bb_pct_offset": round(float(np.average(g.bb_pct_hi - g.bb_pct_lo, weights=g.w)), 4),
        })
    return pd.DataFrame(rows).sort_values(
        ["from_level", "to_level"], key=lambda c: c.map(LEVEL_ORDER))


def main() -> None:
    out_dir = OUTPUTS / "translation"
    out_dir.mkdir(parents=True, exist_ok=True)

    ladder = ladder_offsets()
    ladder.to_csv(out_dir / "level_ladder_offsets.csv", index=False)
    print("=== same-season within-player level offsets ===")
    print(ladder.to_string(index=False))

    promo = promotion_models()
    promo.to_csv(out_dir / "promotion_model_metrics.csv", index=False)
    print("\n=== promotion regressions (train<=%d, test after) ===" % TRAIN_END)
    print(promo.to_string(index=False))
    log_run("level_translation_v1", train_end=TRAIN_END,
            n_ladder=len(ladder), n_promo=len(promo))


if __name__ == "__main__":
    main()
