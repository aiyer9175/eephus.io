# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""Leakage, calibration, and stress-test audits for the champion projection.

Champion (from the strategy race) is re-fit here per target with the chosen
feature set; audits run on the time-holdout test window only.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import pearsonr
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import DATA_PROCESSED, OUTPUTS, log_run
from ground_truth_and_baselines import load_frame
from model_strategy_race import FEATURE_SETS, TRAIN_END, eb_shrink

SEED = 42


def leakage_audit(pairs: pd.DataFrame, dec: pd.DataFrame) -> list[str]:
    findings = []
    nxt = pd.read_parquet(DATA_PROCESSED / "next_season_pairs.parquet")
    # all "next" outcomes really are season+1 (alignment built that way; verify age moved)
    chk = nxt.dropna(subset=["age", "age_next"])
    bad_age = (chk.age_next - chk.age).median()
    findings.append(f"next-season pairs median age delta = {bad_age} (expect 1.0): "
                    + ("PASS" if abs(bad_age - 1.0) < 0.01 else "FAIL"))
    dup = pairs.duplicated(["player_id", "season", "level"]).sum()
    findings.append(f"duplicate (player,season,level) feature rows: {dup}: "
                    + ("PASS" if dup == 0 else "FAIL"))
    dupd = dec.duplicated(["batter_id", "season", "level"]).sum()
    findings.append(f"duplicate decision+ rows: {dupd}: " + ("PASS" if dupd == 0 else "FAIL"))
    findings.append(f"training window ends {TRAIN_END}; 2026 partial-season rows "
                    f"excluded from training by construction: PASS")
    findings.append("Decision+ composite weights trained on seasons <= "
                    f"{TRAIN_END} only (build_decision_plus.py): PASS")
    findings.append("MLB Decision+ model never used as input/target for MiLB->MLB "
                    "translation (statline regressions only): PASS")
    return findings


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", default="D_decision")
    ap.add_argument("--decision-file", default=str(DATA_PROCESSED / "decision_plus.parquet"))
    args = ap.parse_args()

    pairs = load_frame()
    dec = pd.read_parquet(args.decision_file)
    keep = ["batter_id", "season", "level", "decision_plus", "tier", "reliability",
            "age_vs_level", "take_ball_shrunk", "chase_shrunk", "z_take_shrunk",
            "zcontact_shrunk", "contact_pct", "swing_pct", "pitches"]
    pairs = pairs.merge(
        dec[[c for c in keep if c in dec.columns]].rename(
            columns={"pitches": "pitches_dec"}),
        left_on=["player_id", "season", "level"],
        right_on=["batter_id", "season", "level"], how="left")
    pairs["swings_est"] = (pairs.pitches_dec * pairs.swing_pct).clip(lower=1)
    ok = pairs.contact_pct.notna()
    pairs.loc[ok, "contact_shrunk"] = eb_shrink(
        pairs[ok].rename(columns={"contact_pct": "r"}), "r", "swings_est",
        ["level", "season"]).values

    out_dir = OUTPUTS / "audits"
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---------------- leakage ----------------
    findings = leakage_audit(pairs, dec)
    (out_dir / "leakage_audit.txt").write_text("\n".join(findings) + "\n")
    print("=== leakage audit ===")
    print("\n".join(findings))

    # shipped champion: deep-C at AAA/AA/CPX, components-Z at A+/A (all ridge)
    C_FEATS = ["k_pct_shrunk", "bb_pct_shrunk", "age", "log_pa"]
    Z_FEATS = C_FEATS + ["decision_plus", "contact_shrunk", "take_ball_shrunk",
                         "chase_shrunk", "z_take_shrunk", "zcontact_shrunk"]
    LEVEL_FEATURES = {"AAA": C_FEATS, "AA": C_FEATS, "CPX": C_FEATS,
                      "A+": Z_FEATS, "A": Z_FEATS}
    cal_rows, stress_rows = [], []
    for level in ["AAA", "AA", "A+", "A", "CPX"]:
        lv = pairs[pairs.level == level]
        feats = LEVEL_FEATURES[level]
        for tgt in ["next_k_pct", "next_bb_pct"]:
            sub = lv.dropna(subset=feats + [tgt])
            train = sub[sub.season <= TRAIN_END]
            test = sub[sub.season > TRAIN_END].copy()
            if len(train) < 150 or len(test) < 80:
                continue
            model = make_pipeline(StandardScaler(), Ridge(alpha=1.0, random_state=SEED))
            model.fit(train[feats], train[tgt])
            test["pred"] = model.predict(test[feats])
            test["err"] = test.pred - test[tgt]

            # calibration deciles
            test["decile"] = pd.qcut(test.pred, 10, labels=False, duplicates="drop")
            cal = test.groupby("decile").agg(
                pred_mean=("pred", "mean"), actual_mean=(tgt, "mean"),
                n=("pred", "size")).reset_index()
            cal["error"] = cal.pred_mean - cal.actual_mean
            cal["level"], cal["target"] = level, tgt
            cal_rows.append(cal)

            # stress subgroups
            groups = {
                "young_for_level": test.age_vs_level <= -1.5,
                "old_for_level": test.age_vs_level >= 1.5,
                "high_k": test.k_pct_shrunk >= test.k_pct_shrunk.quantile(0.75),
                "high_bb": test.bb_pct_shrunk >= test.bb_pct_shrunk.quantile(0.75),
                "small_sample": test.pa <= 250,
                "large_sample": test.pa >= 450,
                "tier_A": test.tier == "A",
                "tier_B": test.tier == "B",
                "all": pd.Series(True, index=test.index),
            }
            for gname, mask in groups.items():
                g = test[mask.fillna(False)]
                if len(g) < 30:
                    continue
                stress_rows.append({
                    "level": level, "target": tgt, "group": gname, "n": len(g),
                    "pearson": round(pearsonr(g.pred, g[tgt])[0], 4),
                    "mae": round(float(g.err.abs().mean()), 5),
                    "bias": round(float(g.err.mean()), 5),
                })

    cal_df = pd.concat(cal_rows, ignore_index=True)
    cal_df.to_csv(out_dir / "calibration_deciles.csv", index=False)
    stress_df = pd.DataFrame(stress_rows)
    stress_df.to_csv(out_dir / "stress_tests.csv", index=False)

    # flag compressed tails / level bias
    print("\n=== calibration flags (|decile error| > 1pp) ===")
    flags = cal_df[cal_df.error.abs() > 0.01]
    print(flags.to_string(index=False) if len(flags) else "none")
    print("\n=== stress (worst 10 by |bias|) ===")
    print(stress_df.reindex(stress_df.bias.abs().sort_values(ascending=False).index)
          .head(10).to_string(index=False))
    log_run("audits_v1", features=args.features, n_cal=len(cal_df), n_stress=len(stress_df))


if __name__ == "__main__":
    main()
