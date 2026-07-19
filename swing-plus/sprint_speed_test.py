# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
sprint_speed_test.py — Does sprint speed improve prediction of actual
offensive value (wOBA)?

Theory: xwOBA is speed-blind by construction (it's EV/LA-based). A fast
hitter's real wOBA exceeds his xwOBA via infield hits / beaten-out grounders.
So sprint speed — a clean, stable, non-launch-derived trait — should help
predict next-half wOBA but NOT next-half xwOBA. The xwOBA case is a built-in
falsification check: if speed "helps" xwOBA too, something's leaking.

Test: appr17 vs appr17+sprint_speed, GroupKFold(5) OOF on batter, predicting
next-half wOBA and xwOBA. Plus whether it improves the blended product.
"""

import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.model_selection import GroupKFold
from pybaseball import statcast_sprint_speed
from pa_value import PAValueModel
from train_pa_value import make_pipe

PROC = Path(__file__).parent / "data" / "processed"
PV = PAValueModel(Path(__file__).parent / "pa_value_models.joblib")
FEATS = PV.features


def sprint_table() -> pd.DataFrame:
    parts = []
    for yr in (2023, 2024, 2025):
        s = statcast_sprint_speed(yr, min_opp=10)[["player_id", "sprint_speed", "hp_to_1b"]]
        s["season"] = str(yr)
        parts.append(s)
    out = pd.concat(parts, ignore_index=True).rename(columns={"player_id": "batter"})
    return out


def next_half(h):
    s, sh = h.split("_"); return f"{s}_H2" if sh == "H1" else f"{int(s)+1}_H1"


def oof_r(frame, feats, target):
    sub = frame.dropna(subset=feats + [target])
    X, y, g = sub[feats], sub[target], sub["batter"]
    oof = np.full(len(y), np.nan)
    for tr, te in GroupKFold(5).split(X, y, g):
        oof[te] = make_pipe().fit(X.iloc[tr], y.iloc[tr]).predict(X.iloc[te])
    return float(np.corrcoef(oof, y)[0, 1]), oof, sub


def main():
    half = pd.read_parquet(PROC / "leaderboard_half.parquet")
    half["season"] = half["half"].str.split("_").str[0]
    sp = sprint_table()
    m = half.merge(sp, on=["batter", "season"], how="left")
    cov = m["sprint_speed"].notna().mean() * 100
    print(f"sprint speed coverage: {cov:.0f}% of player-halves "
          f"(range {m['sprint_speed'].min():.1f}-{m['sprint_speed'].max():.1f} ft/s)\n")

    # quick: does speed correlate with the wOBA - xwOBA gap (the thing it should explain)?
    g = m.dropna(subset=["sprint_speed", "obs_woba", "obs_xwoba"])
    gap = g["obs_woba"] - g["obs_xwoba"]
    print(f"corr(sprint_speed, wOBA-xwOBA gap) = {np.corrcoef(g['sprint_speed'], gap)[0,1]:+.3f}  "
          f"(speed should create positive gap)\n")

    # predictive frame
    m["next_half"] = m["half"].map(next_half)
    nxt = m[["batter", "half", "obs_woba", "obs_xwoba", "n_pa"]].rename(columns={
        "half": "next_half", "obs_woba": "woba_next", "obs_xwoba": "xwoba_next",
        "n_pa": "n_pa_next"})
    pf = m.merge(nxt, on=["batter", "next_half"], how="inner")
    pf = pf[(pf["n_pa"] >= 100) & (pf["n_pa_next"] >= 100)].dropna(
        subset=FEATS + ["sprint_speed"]).reset_index(drop=True)

    print(f"PREDICTIVE (H_t -> H_t+1), n={len(pf)}, GroupKFold OOF on batter")
    print("=" * 64)
    for target, lbl in [("woba_next", "next-half wOBA (speed SHOULD help)"),
                        ("xwoba_next", "next-half xwOBA (falsification: should NOT)")]:
        r_base, _, _ = oof_r(pf, FEATS, target)
        r_sp, _, _ = oof_r(pf, FEATS + ["sprint_speed"], target)
        print(f"\n{lbl}")
        print(f"  appr17               r = {r_base:.3f}")
        print(f"  appr17 + sprint_speed r = {r_sp:.3f}   (Δ {r_sp - r_base:+.3f})")

    # Does speed help the blended wOBA product?
    print("\n" + "=" * 64)
    print("BLEND check (next-half wOBA):")
    _, oof_base, sub = oof_r(pf, FEATS, "obs_woba")
    pf_b = sub.copy(); pf_b["_pred"] = oof_base
    k = PV.blend_k["woba"]
    w = pf_b["n_pa"] / (pf_b["n_pa"] + k)
    blend_base = w * pf_b["obs_woba"] + (1 - w) * pf_b["_pred"]
    rb = np.corrcoef(blend_base, pf_b["woba_next"])[0, 1]
    _, oof_sp, sub2 = oof_r(pf, FEATS + ["sprint_speed"], "obs_woba")
    pf_s = sub2.copy(); pf_s["_pred"] = oof_sp
    w2 = pf_s["n_pa"] / (pf_s["n_pa"] + k)
    blend_sp = w2 * pf_s["obs_woba"] + (1 - w2) * pf_s["_pred"]
    rbs = np.corrcoef(blend_sp, pf_s["woba_next"])[0, 1]
    print(f"  blend (appr17 model)            r = {rb:.3f}")
    print(f"  blend (appr17 + speed model)    r = {rbs:.3f}   (Δ {rbs - rb:+.3f})")


if __name__ == "__main__":
    main()
