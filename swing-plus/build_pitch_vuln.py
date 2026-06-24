# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
build_pitch_vuln.py — per-hitter PITCH-TYPE VULNERABILITY profile (DESCRIPTIVE).

Game Theory+ research: RV-by-pitch-type is noise (YoY r ~0.1), but WHIFF-rate by
pitch type is a reliable trait (YoY r 0.48-0.66). It's mostly redundant with
overall whiff and has no forward/collapse signal (so NOT a projection input) —
but the per-pitch-type *profile* ("his hole is the slider") is real scouting /
matchup context, like the zone-coverage profile.

Per batter, pooled recent seasons, EB-shrunk whiff% vs league by pitch family:
  fastball (FF/SI/FC) · slider (SL/ST/SV) · curve (CU/KC/CS) · offspeed (CH/FS/FO)
  vuln = shrunk_whiff - league_whiff   (positive = whiffs more than league = a hole)
Output -> data/processed/pitch_vuln_profile.parquet
"""

import glob
import numpy as np
import pandas as pd
from pathlib import Path

PROC = Path(__file__).parent / "data" / "processed"
FAM = {"fb": {"FF", "SI", "FC"}, "sl": {"SL", "ST", "SV"},
       "cu": {"CU", "KC", "CS"}, "ch": {"CH", "FS", "FO", "SC"}}
WH = {"swinging_strike", "swinging_strike_blocked", "foul_tip"}
SW = WH | {"foul", "hit_into_play"}
K = 60   # EB shrink: ~60 swings to half-trust


def main():
    files = sorted(glob.glob(str(Path(__file__).parent / "data/raw/statcast_20*_H*.parquet")))
    # pool the most recent ~2 seasons for a stable current profile
    files = [f for f in files if any(y in f for y in ("2024", "2025", "2026"))]
    d = pd.concat([pd.read_parquet(f, columns=["batter", "pitch_type", "description"]) for f in files],
                  ignore_index=True).dropna(subset=["pitch_type"])
    d["fam"] = "x"
    for k, s in FAM.items():
        d.loc[d.pitch_type.isin(s), "fam"] = k
    d = d[d.fam != "x"]
    d["swing"] = d.description.isin(SW)
    d["whiff"] = d.description.isin(WH)
    sw = d[d.swing]

    lg = sw.groupby("fam")["whiff"].mean()            # league whiff per family
    g = sw.groupby(["batter", "fam"]).agg(wh=("whiff", "sum"), n=("whiff", "size")).reset_index()
    g["lg"] = g.fam.map(lg)
    g["whiff_shrunk"] = (g.wh + K * g.lg) / (g.n + K)
    g["vuln"] = (g.whiff_shrunk - g.lg).round(3)      # + = a hole
    g["whiff_shrunk"] = g.whiff_shrunk.round(3)

    out = g.pivot(index="batter", columns="fam", values=["whiff_shrunk", "vuln", "n"])
    out.columns = [f"{a}_{b}" for a, b in out.columns]
    out = out.reset_index()
    # biggest hole (only among families with >=40 swings)
    def hole(r):
        cand = {}
        for f in FAM:
            n = r.get(f"n_{f}"); v = r.get(f"vuln_{f}")
            if pd.notna(n) and n >= 40 and pd.notna(v):
                cand[f] = v
        return max(cand, key=cand.get) if cand else None
    out["worst_fam"] = out.apply(hole, axis=1)
    for f, v in lg.items():
        out[f"lg_{f}"] = round(float(v), 3)
    out.to_parquet(PROC / "pitch_vuln_profile.parquet", index=False)
    print(f"saved pitch_vuln_profile.parquet ({len(out)} hitters); league whiff by family: "
          + ", ".join(f"{k} {v:.2f}" for k, v in lg.items()))
    print(f"  worst-family distribution: {out['worst_fam'].value_counts().to_dict()}")


if __name__ == "__main__":
    main()
