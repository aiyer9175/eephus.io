# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
dcv_2026.py — extend DCV+ (Damage Conversion+, external damage-geometry framework)
to 2026, same pattern as b2b_2026/contact_2026:

  1. replicate the framework's raw damage-geometry rates from our raw Statcast
     (their cuts: spray +=pull, PULL_CUT 15°, air = LD/FB, HR window LA 20-35°),
     VALIDATED against the framework's own batter_season_damage.parquet (2023-25);
  2. calibrate dcv_plus ~ shrunk rates on 2023-25;
  3. predict 2026, shrink low-BIP toward 100 (K=100 BIP).

Output: data/processed/dcv_plus.parquet (2023-25 framework scores + 2026 calibrated,
columns: batter, season, dcv_plus, n_bip, source).
"""
import glob
import numpy as np, pandas as pd
from pathlib import Path

DCV_DIR = Path("/Users/willcahoon/damage_conversion_plus/data/processed")
OUT = Path("data/processed/dcv_plus.parquet")
PULL_CUT, HRW_LO, HRW_HI, K_BIP = 15.0, 20.0, 35.0, 100.0
RATES = ["pulled_air_rate", "pulled_barrel_rate", "hr_window_rate", "pull_rate"]


def my_rates() -> pd.DataFrame:
    """per (batter, season) damage-geometry rates from raw Statcast, their cuts."""
    cols = ["batter", "game_year", "stand", "type", "bb_type", "hc_x", "hc_y",
            "launch_angle", "launch_speed_angle"]
    df = pd.concat([pd.read_parquet(f, columns=cols)
                    for f in glob.glob("data/raw/statcast_*.parquet")], ignore_index=True)
    bip = df[(df["type"] == "X") & df["bb_type"].notna()].copy()
    raw = np.degrees(np.arctan((bip.hc_x - 125.42) / (198.27 - bip.hc_y)))
    bip["spray_deg"] = np.where(bip.stand == "L", raw, -raw)      # += pull
    bip["is_pull"] = bip.spray_deg > PULL_CUT
    air = bip.bb_type.isin(["line_drive", "fly_ball"])
    bip["pulled_air"] = bip.is_pull & air
    bip["pulled_barrel"] = bip.is_pull & (bip.launch_speed_angle == 6)
    bip["hr_window"] = bip.launch_angle.between(HRW_LO, HRW_HI)
    g = bip.groupby(["batter", "game_year"]).agg(
        n_bip=("is_pull", "size"), pull_rate=("is_pull", "mean"),
        pulled_air_rate=("pulled_air", "mean"),
        pulled_barrel_rate=("pulled_barrel", "mean"),
        hr_window_rate=("hr_window", "mean")).reset_index()
    return g.rename(columns={"game_year": "season"})


def shrink(g: pd.DataFrame) -> pd.DataFrame:
    for c in RATES:
        ok = g[c].notna()
        lg = np.average(g.loc[ok, c], weights=g.loc[ok, "n_bip"])
        w = g.n_bip / (g.n_bip + K_BIP)
        g[c + "_sh"] = lg + w * (g[c] - lg)      # rows with NaN rate stay NaN
    return g


if __name__ == "__main__":
    mine = my_rates()
    theirs = pd.read_parquet(DCV_DIR / "batter_season_damage.parquet")
    chk = mine.merge(theirs, on=["batter", "season"], suffixes=("", "_fw"))
    chk = chk[chk.n_bip >= 50]
    print("=== replication check vs framework (2023-25, >=50 BIP) ===")
    for c in ["pulled_air_rate", "pulled_barrel_rate", "hr_window_rate", "pull_rate"]:
        print(f"   {c:22s} r = {chk[c].corr(chk[c + '_fw']):.3f}")

    dcv = pd.read_parquet(DCV_DIR / "damage_conversion_plus.parquet")[
        ["batter", "season", "dcv_plus"]]
    m = shrink(mine).merge(dcv, on=["batter", "season"])
    m = m[m.n_bip >= 50].dropna(subset=[c + "_sh" for c in RATES] + ["dcv_plus"])
    X = np.column_stack([np.ones(len(m))] + [m[c + "_sh"] for c in RATES])
    beta, _, _, _ = np.linalg.lstsq(X, m.dcv_plus.values, rcond=None)
    pred = X @ beta
    ss = 1 - ((m.dcv_plus - pred) ** 2).sum() / ((m.dcv_plus - m.dcv_plus.mean()) ** 2).sum()
    print(f"\ncalibration dcv_plus ~ shrunk rates (2023-25): R^2 = {ss:.3f} (n={len(m)})")

    s26 = shrink(mine[mine.season == 2026].copy())
    s26 = s26[s26.n_bip >= 30].dropna(subset=[c + "_sh" for c in RATES])
    X26 = np.column_stack([np.ones(len(s26))] + [s26[c + "_sh"] for c in RATES])
    s26["dcv_plus"] = X26 @ beta
    w = s26.n_bip / (s26.n_bip + K_BIP)                    # extra low-sample pull to 100
    s26["dcv_plus"] = (100 + w * (s26.dcv_plus - 100)).round(1)

    out = pd.concat([
        dcv.merge(mine[["batter", "season", "n_bip"]], on=["batter", "season"], how="left")
           .assign(source="framework"),
        s26[["batter", "season", "dcv_plus", "n_bip"]].assign(source="calibrated_2026"),
    ], ignore_index=True)
    out.to_parquet(OUT, index=False)
    print(f"\nsaved {OUT}: {len(out)} rows "
          f"({dict(out.season.value_counts().sort_index())})")
    nm = theirs[["batter", "name"]].drop_duplicates("batter")
    top = s26.nlargest(6, "dcv_plus").merge(nm, on="batter", how="left")
    print("2026 top:", "; ".join(f"{r['name']} {r.dcv_plus:.0f}" for _, r in top.iterrows()))
