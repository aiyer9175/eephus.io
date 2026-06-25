# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
fix_variance_defense.py — upgrade Variance+ total value to use the Defense+
COMPOSITE def value (innings-shrunk, beats OAA-alone OOS) instead of OAA-only,
while keeping the sub-components for display.

Audit finding (MI accuracy): ~25% of a middle-infielder's value is defense, and
the card sourced it from OAA-only — the noisiest metric (.41 reliability). The
Defense+ composite is more accurate and ships a calibrated sd. We:
  off_runs    = total_runs - def_runs            (preserve the offensive part)
  def_runs    = composite (fallback to existing if no composite)
  total_runs  = off_runs + def_runs              (recomputed)
  + def_sd, d_oaa/d_drs/d_frp/d_framing          (uncertainty + sub-components)
Idempotent.
"""

import pandas as pd
import numpy as np
from pathlib import Path

PROC = Path(__file__).parent / "data" / "processed"
VP = PROC / "variance_plus_2027.parquet"
DC = PROC / "defense_card.parquet"


def main():
    v = pd.read_parquet(VP)
    if not DC.exists():
        print("defense_card.parquet missing — skip"); return
    d = pd.read_parquet(DC)[["batter", "Pos", "Inn", "def_runs", "def_sd", "d_oaa", "d_drs", "d_frp", "d_framing"]]
    # one row per player — keep the most-played position's defensive line
    d = d.sort_values("Inn", ascending=False).drop_duplicates("batter").drop(columns=["Inn"])
    d = d.rename(columns={"def_runs": "def_comp", "Pos": "pos_def"})

    # drop enrichment cols that the merge re-supplies (pipeline now also ships def_sd/def_source)
    v = v.drop(columns=[c for c in ["def_sd", "d_oaa", "d_drs", "d_frp", "d_framing", "pos_def"] if c in v.columns])
    orig_dtype = v["batter"].dtype
    v["_bkey"] = pd.to_numeric(v["batter"], errors="coerce").astype("Int64")
    d["_bkey"] = pd.to_numeric(d["batter"], errors="coerce").astype("Int64")
    v["off_runs"] = v["total_runs"] - v["def_runs"]
    v = v.merge(d.drop(columns=["batter"]), on="_bkey", how="left").drop(columns=["_bkey"])
    # batter dtype is preserved (app looks it up as str)
    used = v["def_comp"].notna()
    # swap in the composite where available; keep prior def_runs (OAA/framing) as fallback
    v["def_runs"] = np.where(used, v["def_comp"], v["def_runs"]).round(2)
    v["def_source"] = np.where(used, "dplus_proj", v["def_source"])
    v["def_sd"] = v["def_sd"].round(2)
    v["total_runs"] = (v["off_runs"] + v["def_runs"]).round(1)
    # backfill missing/"?" position from the defense card's fielding-innings position
    bad = v["pos"].isna() | v["pos"].astype(str).isin(["nan", "None", "", "?"])
    v["pos"] = np.where(bad & v["pos_def"].notna(), v["pos_def"], v["pos"])
    v = v.drop(columns=["def_comp", "off_runs", "pos_def"])
    v.to_parquet(VP, index=False)

    mi = v[v["pos"].isin(["SS", "2B"])]
    print(f"patched {VP.name}: {used.sum()}/{len(v)} players on Defense+ projection")
    print(f"  MI (SS/2B): {mi['def_source'].eq('dplus_proj').sum()}/{len(mi)} on projection; "
          f"mean def_sd {mi['def_sd'].mean():.1f}")
    print(f"  sub-components carried: d_oaa, d_drs, d_frp, d_framing")


if __name__ == "__main__":
    main()
