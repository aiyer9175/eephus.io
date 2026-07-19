# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
distribution_features_test.py — Does modeling the DISTRIBUTION of swing
variables (percentiles, CV, skew, IQR, entropy) beat using just the mean/std?

Current model uses mean of 7 tracking vars + std of bat_speed & attack_angle.
This adds distributional shape for the two outcome-driving variables
(bat_speed, attack_angle):
    p10 p25 p50 p75 p90, CV (std/|mean|), skew, IQR (p75-p25),
    entropy (normalized, fixed global bins)

All from swing geometry -> no leakage. Tested concurrent + predictive
(GroupKFold OOF on batter) against base9 and appr17, on the contact-quality
targets the swing distribution should drive.
"""

import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
from scipy import stats
from sklearn.model_selection import GroupKFold
from swing_plus import SwingPlusModel
from train_pa_value import make_pipe, BASELINE_FEATS
from pa_features import compute_approach_features, APPROACH_FEATS

PROJECT = Path(__file__).parent
RAW = PROJECT / "data" / "raw"
PROC = PROJECT / "data" / "processed"
HALVES = ["2023_H2", "2024_H1", "2024_H2", "2025_H1", "2025_H2"]
MODEL = SwingPlusModel(PROJECT / "swing_plus_model_v1.joblib")

DIST_VARS = {"swing_length": "sl",
             "intercept_ball_minus_batter_pos_x_inches": "ix",
             "intercept_ball_minus_batter_pos_y_inches": "iy"}
# global bin edges for entropy (filled at runtime)
BIN_EDGES = {}

TARGETS = [
    ("obs_avg_ev", "Avg EV", 1),
    ("obs_barrel_pct", "Barrel %", 1),
    ("obs_xwobacon", "xwOBAcon", 3),
]


def _dist_for(x, short):
    # CV (std/|mean|) is intentionally OMITTED: attack_angle is interval-scaled
    # (mean can be ~0), so CV explodes and corrupts the poly expansion. Spread
    # is captured cleanly by IQR; std is already a base feature.
    out = {}
    for q, nm in [(10, "p10"), (25, "p25"), (50, "p50"), (75, "p75"), (90, "p90")]:
        out[f"{short}_{nm}"] = np.percentile(x, q)
    out[f"{short}_skew"] = float(stats.skew(x))
    out[f"{short}_iqr"] = np.percentile(x, 75) - np.percentile(x, 25)
    h, _ = np.histogram(x, bins=BIN_EDGES[short])
    p = h / h.sum() if h.sum() else h
    out[f"{short}_entropy"] = float(stats.entropy(p + 1e-12) / np.log(len(BIN_EDGES[short]) - 1))
    return out


def dist_per_half(label):
    df = pd.read_parquet(RAW / f"statcast_{label}.parquet",
                         columns=["batter", "bat_speed", "swing_length", "attack_angle",
                                  "attack_direction", "swing_path_tilt",
                                  "intercept_ball_minus_batter_pos_x_inches",
                                  "intercept_ball_minus_batter_pos_y_inches", "type"])
    sw = MODEL.filter_swings(df)
    rows = []
    for bid, g in sw.groupby("batter"):
        r = {"batter": bid, "half": label}
        ok = True
        for var, short in DIST_VARS.items():
            x = g[var].dropna().to_numpy()
            if len(x) < 30:
                ok = False; break
            r.update(_dist_for(x, short))
        if ok:
            rows.append(r)
    return pd.DataFrame(rows)


DIST_FEATS = []
for short in DIST_VARS.values():
    DIST_FEATS += [f"{short}_{s}" for s in
                   ["p10", "p25", "p50", "p75", "p90", "skew", "iqr", "entropy"]]


def oof_r(frame, feats, target):
    sub = frame.dropna(subset=feats + [target])
    X, y, g = sub[feats], sub[target], sub["batter"]
    oof = np.full(len(y), np.nan)
    for tr, te in GroupKFold(5).split(X, y, g):
        oof[te] = make_pipe().fit(X.iloc[tr], y.iloc[tr]).predict(X.iloc[te])
    return float(np.corrcoef(oof, y)[0, 1])


def next_half(h):
    s, sh = h.split("_"); return f"{s}_H2" if sh == "H1" else f"{int(s)+1}_H1"


def main():
    # global bin edges from a sample
    sample = pd.read_parquet(RAW / "statcast_2024_H2.parquet",
                             columns=["bat_speed", "attack_angle", "swing_length",
                                      "attack_direction", "swing_path_tilt",
                                      "intercept_ball_minus_batter_pos_x_inches",
                                      "intercept_ball_minus_batter_pos_y_inches", "type"])
    sw = MODEL.filter_swings(sample)
    for var, short in DIST_VARS.items():
        x = sw[var].dropna()
        BIN_EDGES[short] = np.linspace(x.quantile(.01), x.quantile(.99), 13)

    print("Computing distributional features...")
    dist = pd.concat([dist_per_half(h) for h in HALVES], ignore_index=True)
    base = pd.read_csv(PROC / "validation_concurrent.csv")
    appr = pd.concat([compute_approach_features(
        pd.read_parquet(RAW / f"statcast_{h}.parquet").assign(half=h), ["batter", "half"])
        for h in HALVES], ignore_index=True)
    m = base.merge(appr, on=["batter", "half"]).merge(dist, on=["batter", "half"])
    # Winsorize dist features at [0.5, 99.5] pct so no outlier corrupts poly(2).
    for c in DIST_FEATS:
        lo, hi = m[c].quantile(0.005), m[c].quantile(0.995)
        m[c] = m[c].clip(lo, hi)
    print(f"  {len(m)} player-halves with full distributional features\n")

    # quick: how non-normal are these dists? (if ~0 skew, percentiles add nothing)
    sk = "  ".join(f"{v} skew={m[f'{s}_skew'].mean():+.2f}" for v, s in DIST_VARS.items())
    print(f"  {sk}   (0 = normal; |skew|>0.3 = shape beyond mean/std)\n")

    sets = {
        "base9": BASELINE_FEATS,
        "base9 + dist": BASELINE_FEATS + DIST_FEATS,
        "appr17": BASELINE_FEATS + APPROACH_FEATS,
        "appr17 + dist": BASELINE_FEATS + APPROACH_FEATS + DIST_FEATS,
    }

    print("=" * 78)
    print("CONCURRENT  features(H) -> target(H)")
    print("=" * 78)
    print(f"{'target':<10} " + "".join(f"{k:>16}" for k in sets))
    for tcol, lbl, _ in TARGETS:
        rs = {k: oof_r(m, f, tcol) for k, f in sets.items()}
        print(f"{lbl:<10} " + "".join(f"{rs[k]:>16.3f}" for k in sets))

    # predictive
    m["next_half"] = m["half"].map(next_half)
    nxt = m[["batter", "half"] + [t for t, _, _ in TARGETS]].rename(
        columns={"half": "next_half", **{t: t + "_n" for t, _, _ in TARGETS}})
    pf = m.merge(nxt, on=["batter", "next_half"])
    print("\n" + "=" * 78)
    print(f"PREDICTIVE  features(H_t) -> target(H_t+1)   VERDICT   (n={len(pf)})")
    print("=" * 78)
    print(f"{'target':<10} " + "".join(f"{k:>16}" for k in sets) + f"{'dist|base':>12}{'dist|appr':>12}")
    for tcol, lbl, _ in TARGETS:
        rs = {k: oof_r(pf, f, tcol + "_n") for k, f in sets.items()}
        db = rs["base9 + dist"] - rs["base9"]
        da = rs["appr17 + dist"] - rs["appr17"]
        print(f"{lbl:<10} " + "".join(f"{rs[k]:>16.3f}" for k in sets) + f"{db:>+12.3f}{da:>+12.3f}")


if __name__ == "__main__":
    main()
