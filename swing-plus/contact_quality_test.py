# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
contact_quality_test.py — Does adding contact QUALITY (chase + in-zone
xwOBAcon) improve prediction of xwOBA?

Contact quality is launch-derived, so:
  - CONCURRENT (same half): adding it is leakage (it's part of the target).
  - PREDICTIVE (H_t -> H_{t+1}): lagged contact quality is a legit predictor,
    but it's essentially the persistence/observed signal the BLEND already uses.

We test both, GroupKFold(5) OOF on batter, all sets on identical rows, and
compare against the blend (the current product, r~0.57 next-half).
"""

import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.model_selection import GroupKFold
from pa_value import PAValueModel
from train_pa_value import make_pipe

PROC = Path(__file__).parent / "data" / "processed"
RAW = Path(__file__).parent / "data" / "raw"
HALVES = ["2023_H2", "2024_H1", "2024_H2", "2025_H1", "2025_H2"]
PV = PAValueModel(Path(__file__).parent / "pa_value_models.joblib")
FEATS = PV.features


def per_half_quality(label):
    df = pd.read_parquet(RAW / f"statcast_{label}.parquet",
                         columns=["batter", "type", "zone", "estimated_woba_using_speedangle"])
    df["_out"] = ~df["zone"].between(1, 9).fillna(False)
    bip = df[df["type"] == "X"]
    ooz = bip[bip["_out"]].groupby("batter")["estimated_woba_using_speedangle"].mean()
    iz = bip[~bip["_out"]].groupby("batter")["estimated_woba_using_speedangle"].mean()
    out = pd.DataFrame({"ooz_xwobacon": ooz, "iz_xwobacon": iz}).reset_index()
    out["half"] = label
    return out


def next_half(h):
    s, sh = h.split("_")
    return f"{s}_H2" if sh == "H1" else f"{int(s)+1}_H1"


def oof_r(frame, feats, target):
    sub = frame.dropna(subset=feats + [target])
    X, y, g = sub[feats], sub[target], sub["batter"]
    oof = np.full(len(y), np.nan)
    for tr, te in GroupKFold(5).split(X, y, g):
        oof[te] = make_pipe().fit(X.iloc[tr], y.iloc[tr]).predict(X.iloc[te])
    return float(np.corrcoef(oof, y)[0, 1]), oof, sub


def main():
    half = pd.read_parquet(PROC / "leaderboard_half.parquet")
    q = pd.concat([per_half_quality(h) for h in HALVES], ignore_index=True)
    m = half.merge(q, on=["batter", "half"], how="inner")
    m = m[m["n_pa"] >= 100].dropna(subset=FEATS + ["obs_xwoba", "ooz_xwobacon", "iz_xwobacon"]).reset_index(drop=True)

    CQ = ["ooz_xwobacon", "iz_xwobacon"]
    print(f"n = {len(m)} player-halves (PA>=100, all features present)\n")

    print("=" * 78)
    print("CONCURRENT  features(H) -> obs_xwoba(H)   ** same-half = leakage for CQ **")
    print("=" * 78)
    for lbl, feats in [("appr17", FEATS),
                       ("appr17 + chase-quality", FEATS + ["ooz_xwobacon"]),
                       ("appr17 + all contact-quality", FEATS + CQ)]:
        r, _, _ = oof_r(m, feats, "obs_xwoba")
        print(f"  {lbl:<30} r = {r:.3f}")

    # Build predictive frame
    m["next_half"] = m["half"].map(next_half)
    nxt = m[["batter", "half", "obs_xwoba", "n_pa"]].rename(
        columns={"half": "next_half", "obs_xwoba": "xwoba_next", "n_pa": "n_pa_next"})
    pf = m.merge(nxt, on=["batter", "next_half"], how="inner")
    pf = pf[pf["n_pa_next"] >= 100].reset_index(drop=True)

    print("\n" + "=" * 78)
    print(f"PREDICTIVE  features(H_t) -> obs_xwoba(H_t+1)   ** honest **  (n={len(pf)})")
    print("=" * 78)
    results = {}
    for lbl, feats in [
        ("appr17 (pure skill)", FEATS),
        ("appr17 + chase-quality", FEATS + ["ooz_xwobacon"]),
        ("appr17 + all contact-quality", FEATS + CQ),
        ("contact-quality only", CQ),
        ("persistence (last-half xwOBA)", ["obs_xwoba"]),
    ]:
        r, _, _ = oof_r(pf, feats, "xwoba_next")
        results[lbl] = r
        print(f"  {lbl:<32} r = {r:.3f}")

    # The blend (current product): blend OOF appr17 model pred with observed, then predict next
    _, oof_pred, sub = oof_r(pf, FEATS, "obs_xwoba")   # OOF same-half pred on pf rows
    pf2 = sub.copy()
    pf2["_pred"] = oof_pred
    w = pf2["n_pa"] / (pf2["n_pa"] + PV.blend_k["xwoba"])
    pf2["_blend"] = w * pf2["obs_xwoba"] + (1 - w) * pf2["_pred"]
    rb = float(np.corrcoef(pf2["_blend"], pf2["xwoba_next"])[0, 1])
    print(f"  {'BLEND (obs + appr17 model)':<32} r = {rb:.3f}   <- current product")

    # blend + contact quality: does adding CQ to the blend's model side help next-half?
    _, oof_cq, subcq = oof_r(pf, FEATS + CQ, "obs_xwoba")
    pf3 = subcq.copy(); pf3["_pred"] = oof_cq
    w3 = pf3["n_pa"] / (pf3["n_pa"] + PV.blend_k["xwoba"])
    pf3["_blend"] = w3 * pf3["obs_xwoba"] + (1 - w3) * pf3["_pred"]
    rb3 = float(np.corrcoef(pf3["_blend"], pf3["xwoba_next"])[0, 1])
    print(f"  {'BLEND + contact-quality model':<32} r = {rb3:.3f}")


if __name__ == "__main__":
    main()
