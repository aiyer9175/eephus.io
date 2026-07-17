# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
build_defense_projection.py — multi-year, aging-aware NEXT-SEASON defensive
projection (Marcel-style for defense), replacing the latest-single-season card.

For each player, projected fielding runs for TARGET_YEAR:
  1. composite per-season def runs (reliability-weighted OAA/DRS/FRP, innings-shrunk)
  2. Marcel weights over the last 3 seasons (6/3/1, recency-weighted)
  3. regress to position mean by total reliability (sum innings)
  4. AGE-ADJUST: shift along the position aging curve from weighted-mean age to
     the player's TARGET_YEAR age (curve = cumulative run value vs age)
  5. uncertainty grows with fewer seasons / less innings / age extrapolation

Output -> ~/swing_plus/data/processed/defense_card.parquet (same schema + proj cols)
"""

import glob
import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).parent
DST = Path.home() / "swing_plus" / "data" / "processed" / "defense_card.parquet"
TARGET_YEAR = 2027
N0 = 400.0                      # innings half-reliability
MARCEL_W = {0: 6.0, 1: 3.0, 2: 1.0}   # season lag -> weight
SYS = ["OAA", "DRS", "FRP"]


def main():
    files = glob.glob(str(ROOT / "data/raw/fg_field_full_20*.csv"))
    d = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    d = d[d["Inn"] >= 50].rename(columns={"xMLBAMID": "batter"}).copy()
    d["batter"] = pd.to_numeric(d["batter"], errors="coerce").astype("Int64")

    # primary position per player-season + composite per-season def runs (z-blend -> runs)
    drs_sd = d.groupby("Pos")["DRS"].std()
    rows = []
    for (pos, seas), g in d.groupby(["Pos", "Season"]):
        z = pd.DataFrame({s: (g[s] - g[s].mean()) / g[s].std() for s in SYS if g[s].std() > 0})
        gg = g.assign(dz=z.mean(axis=1))
        gg["rel"] = gg["Inn"] / (gg["Inn"] + N0)
        gg["def_runs_season"] = gg["dz"] * drs_sd.get(pos, 8) * gg["rel"]
        rows.append(gg[["batter", "Season", "Pos", "Inn", "rel", "def_runs_season",
                        "OAA", "DRS", "FRP", "CFraming"]])
    p = pd.concat(rows).dropna(subset=["batter"])
    # historical per-season composite panel (for downstream models, e.g. Variance+ jobloss)
    panel = p.rename(columns={"Season": "season", "def_runs_season": "def_season"})[["batter", "season", "Pos", "Inn", "def_season"]].copy()
    panel["def_season"] = panel["def_season"].round(2)
    panel.to_parquet(Path.home() / "swing_plus/data/processed/def_panel.parquet", index=False)
    # keep each player's primary position by total innings
    prim = p.groupby(["batter", "Pos"])["Inn"].sum().reset_index().sort_values("Inn", ascending=False)
    prim = prim.drop_duplicates("batter").set_index("batter")["Pos"]

    # aging curve (cumulative run value vs age, per position)
    ac = pd.read_csv(ROOT / "reports" / "11_position_aging_curves.csv").set_index("age")

    # ages: infer from latest season age if available; fg has no age -> use a roster/age source
    ages = d.dropna(subset=["batter"])
    # no age column in fg_field_full; approximate target age from career span is not possible here,
    # so pull age from the variance card (has age) as the age anchor.
    vp = pd.read_parquet(Path.home() / "swing_plus/data/processed/variance_plus_2027.parquet")
    vp_age = vp.assign(batter=pd.to_numeric(vp["batter"], errors="coerce").astype("Int64")).set_index("batter")["age"]

    out = []
    for bid, g in p.groupby("batter"):
        g = g.sort_values("Season")
        recent = g[g["Season"] >= 2025 - 2]              # last 3 seasons
        if recent.empty:
            recent = g.tail(1)
        lag = (2025 - recent["Season"]).clip(0, 2)
        w = lag.map(MARCEL_W).values * recent["rel"].values
        if w.sum() == 0:
            continue
        base = np.average(recent["def_runs_season"].values, weights=w)
        pos = prim.get(bid, recent["Pos"].iloc[-1])
        rel_tot = recent["rel"].sum() / (recent["rel"].sum() + 1.0)   # multi-yr reliability
        proj = base * (0.6 + 0.4 * rel_tot)              # mild regress-to-mean (0) by reliability

        # age adjustment along the position curve: shift from the weighted-mean
        # season's age all the way to the TARGET_YEAR age (≈2-3 yrs for a 3-yr base)
        age_tgt = vp_age.get(bid, np.nan)
        d_age = np.nan
        if pos in ac.columns and not np.isnan(age_tgt):
            s_bar = np.average(recent["Season"].values, weights=w)      # weighted-mean season
            age_bar = age_tgt - (TARGET_YEAR - s_bar)                   # age at that base
            a0, a1 = int(round(age_bar)), int(round(age_tgt))
            a0, a1 = max(a0, ac.index.min()), min(a1, ac.index.max())
            if a0 in ac.index and a1 in ac.index and pd.notna(ac.loc[a0, pos]) and pd.notna(ac.loc[a1, pos]):
                d_age = ac.loc[a1, pos] - ac.loc[a0, pos]               # cumulative-curve delta over the gap

        # BACKTEST (n=1680, 2021-25): the multi-year blend beats single-season
        # (Spearman .44 vs .36) but the 1-yr aging term slightly HURTS (.42) —
        # mean-reversion dominates at a 1-yr horizon. So the headline def_runs is
        # the BLEND; age_adj is stored for the multi-year fan (2028+) where aging
        # compounds, not added to the 1-yr value.
        sub = recent.iloc[-1]
        nyr = recent["Season"].nunique()
        DRIFT = 1.7   # backtest: def_sd as a forecast interval needs +1.7 for 80% coverage
        sd = np.sqrt((np.sqrt(1 - rel_tot) * drs_sd.get(pos, 8) + (1.5 if nyr == 1 else 0.0)) ** 2 + DRIFT ** 2)
        out.append({"batter": int(bid), "Pos": pos, "Inn": int(recent["Inn"].sum()),
                    "def_runs": round(float(proj), 2), "def_sd": round(float(sd), 2),
                    "n_seasons": int(nyr), "age_adj": (round(float(d_age), 2) if not np.isnan(d_age) else None),
                    "d_oaa": round(float(sub["OAA"]), 1) if pd.notna(sub["OAA"]) else None,
                    "d_drs": round(float(sub["DRS"]), 1) if pd.notna(sub["DRS"]) else None,
                    "d_frp": round(float(sub["FRP"]), 1) if pd.notna(sub["FRP"]) else None,
                    "d_framing": round(float(sub["CFraming"]), 1) if pd.notna(sub["CFraming"]) else None,
                    "def_source": "dplus_proj"})
    card = pd.DataFrame(out)
    card.to_parquet(DST, index=False)
    print(f"saved {DST} ({len(card)} players) — multi-year aging-aware projection for {TARGET_YEAR}")
    print(f"  mean n_seasons {card.n_seasons.mean():.1f}; def_runs [{card.def_runs.min():.1f},{card.def_runs.max():.1f}]; mean def_sd {card.def_sd.mean():.1f}")
    mi = card[card.Pos.isin(["SS", "2B"])]
    print(f"  MI: n={len(mi)}, mean age_adj {mi['age_adj'].mean():.2f}, mean def_sd {mi['def_sd'].mean():.1f}")


if __name__ == "__main__":
    main()
