# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
attack_angle_pitchtype_test.py — Does VERTICAL ATTACK ANGLE by pitch type
(and the adaptability across types) carry signal beyond appr17?

Idea: fastballs arrive flatter/higher, breaking balls drop — staying on-plane
means adjusting attack angle by pitch type. Maybe the *level* per type, or the
*adaptability* (how much a hitter changes plane FB->breaking, or the spread
across types) predicts contact quality.

Clean: all from swing geometry (attack_angle by pitch type on competitive
swings), no launch metrics -> no leakage.

Features per (batter, half):
  aa_fastball, aa_breaking, aa_offspeed   per-type mean attack angle (>=10 swings)
  aa_fb_minus_br                          adaptability: FB minus breaking
  aa_type_spread                          std across the per-type means

Descriptive league view + concurrent/predictive CV vs base9 and appr17.
"""

import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.model_selection import GroupKFold
from swing_plus import SwingPlusModel
from train_pa_value import make_pipe, BASELINE_FEATS
from pa_features import compute_approach_features, APPROACH_FEATS

PROJECT = Path(__file__).parent
RAW = PROJECT / "data" / "raw"
PROC = PROJECT / "data" / "processed"
HALVES = ["2023_H2", "2024_H1", "2024_H2", "2025_H1", "2025_H2"]
MODEL = SwingPlusModel(PROJECT / "swing_plus_model_v1.joblib")

FASTBALLS = {"FF", "SI", "FC", "FA", "FT"}
BREAKING = {"SL", "ST", "CU", "KC", "SV", "CS", "KN", "SC", "EP"}
OFFSPEED = {"CH", "FS", "FO"}
AA_PT_FEATS = ["aa_fastball", "aa_breaking", "aa_offspeed", "aa_fb_minus_br", "aa_type_spread"]
TARGETS = [("obs_avg_ev", "Avg EV", 1), ("obs_barrel_pct", "Barrel %", 1),
           ("obs_xwobacon", "xwOBAcon", 3)]


def grp(pt):
    if pt in FASTBALLS: return "fastball"
    if pt in BREAKING: return "breaking"
    if pt in OFFSPEED: return "offspeed"
    return "other"


def per_half(label):
    df = pd.read_parquet(RAW / f"statcast_{label}.parquet",
                         columns=["batter", "pitch_type", "bat_speed", "swing_length",
                                  "attack_angle", "attack_direction", "swing_path_tilt",
                                  "intercept_ball_minus_batter_pos_x_inches",
                                  "intercept_ball_minus_batter_pos_y_inches", "type"])
    sw = MODEL.filter_swings(df).copy()
    sw["g"] = sw["pitch_type"].map(grp)
    rows = []
    for bid, gg in sw.groupby("batter"):
        means = {}
        for name in ("fastball", "breaking", "offspeed"):
            x = gg[gg["g"] == name]["attack_angle"]
            means[name] = x.mean() if len(x) >= 10 else np.nan
        vals = [v for v in means.values() if np.isfinite(v)]
        rows.append({
            "batter": bid, "half": label,
            "aa_fastball": means["fastball"], "aa_breaking": means["breaking"],
            "aa_offspeed": means["offspeed"],
            "aa_fb_minus_br": means["fastball"] - means["breaking"],
            "aa_type_spread": float(np.std(vals)) if len(vals) >= 2 else np.nan,
        })
    return pd.DataFrame(rows)


def oof_r(frame, feats, target):
    sub = frame.dropna(subset=feats + [target])
    X, y, g = sub[feats], sub[target], sub["batter"]
    oof = np.full(len(y), np.nan)
    for tr, te in GroupKFold(5).split(X, y, g):
        oof[te] = make_pipe().fit(X.iloc[tr], y.iloc[tr]).predict(X.iloc[te])
    return float(np.corrcoef(oof, y)[0, 1]), len(sub)


def nh(h):
    s, sh = h.split("_"); return f"{s}_H2" if sh == "H1" else f"{int(s)+1}_H1"


def main():
    aapt = pd.concat([per_half(h) for h in HALVES], ignore_index=True)
    base = pd.read_csv(PROC / "validation_concurrent.csv")
    appr = pd.concat([compute_approach_features(
        pd.read_parquet(RAW / f"statcast_{h}.parquet").assign(half=h), ["batter", "half"])
        for h in HALVES], ignore_index=True)
    m = base.merge(appr, on=["batter", "half"]).merge(aapt, on=["batter", "half"])
    # winsorize the engineered features
    for c in AA_PT_FEATS:
        lo, hi = m[c].quantile(0.005), m[c].quantile(0.995)
        m[c] = m[c].clip(lo, hi)
    m = m.dropna(subset=AA_PT_FEATS).reset_index(drop=True)
    print(f"n = {len(m)} player-halves with all pitch-type AA features\n")

    print("=" * 70)
    print("DESCRIPTIVE: league mean attack angle by pitch type")
    print("=" * 70)
    print(f"  fastball {m.aa_fastball.mean():+.2f}   breaking {m.aa_breaking.mean():+.2f}   "
          f"offspeed {m.aa_offspeed.mean():+.2f}")
    print(f"  mean FB-minus-breaking adjustment: {m.aa_fb_minus_br.mean():+.2f}  "
          f"(>0 = steeper vs FB than breaking)")
    print(f"  attack-angle spread across types: mean {m.aa_type_spread.mean():.2f}, "
          f"p90 {m.aa_type_spread.quantile(.9):.2f}")
    # biggest adjusters vs one-plane
    car = m.groupby("batter").agg(name=("name", "first"),
                                  spread=("aa_type_spread", "mean"),
                                  fbmbr=("aa_fb_minus_br", "mean"),
                                  n=("half", "size")).query("n>=3")
    print("\n  Biggest plane-ADJUSTERS (high cross-type spread):")
    print("   " + car.nlargest(5, "spread")[["name", "spread", "fbmbr"]].round(2)
          .to_string(index=False).replace("\n", "\n   "))
    print("  Most ONE-PLANE (low spread):")
    print("   " + car.nsmallest(5, "spread")[["name", "spread", "fbmbr"]].round(2)
          .to_string(index=False).replace("\n", "\n   "))

    sets = {"base9": BASELINE_FEATS, "base9 + AApt": BASELINE_FEATS + AA_PT_FEATS,
            "appr17": BASELINE_FEATS + APPROACH_FEATS,
            "appr17 + AApt": BASELINE_FEATS + APPROACH_FEATS + AA_PT_FEATS}

    print("\n" + "=" * 70)
    print("CONCURRENT  features(H) -> target(H)")
    print("=" * 70)
    print(f"{'target':<10}" + "".join(f"{k:>16}" for k in sets))
    for t, lbl, _ in TARGETS:
        rs = {k: oof_r(m, f, t)[0] for k, f in sets.items()}
        print(f"{lbl:<10}" + "".join(f"{rs[k]:>16.3f}" for k in sets))

    m["next_half"] = m["half"].map(nh)
    nxt = m[["batter", "half"] + [t for t, _, _ in TARGETS]].rename(
        columns={"half": "next_half", **{t: t + "_n" for t, _, _ in TARGETS}})
    pf = m.merge(nxt, on=["batter", "next_half"])
    print("\n" + "=" * 70)
    print(f"PREDICTIVE  features(H_t) -> target(H_t+1)  VERDICT  (n={len(pf)})")
    print("=" * 70)
    print(f"{'target':<10}" + "".join(f"{k:>16}" for k in sets) + f"{'AA|base':>10}{'AA|appr':>10}")
    for t, lbl, _ in TARGETS:
        rs = {k: oof_r(pf, f, t + "_n")[0] for k, f in sets.items()}
        db = rs["base9 + AApt"] - rs["base9"]; da = rs["appr17 + AApt"] - rs["appr17"]
        print(f"{lbl:<10}" + "".join(f"{rs[k]:>16.3f}" for k in sets) + f"{db:>+10.3f}{da:>+10.3f}")


if __name__ == "__main__":
    main()
