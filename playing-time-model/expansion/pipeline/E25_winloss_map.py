# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Expansion E25 — Where the FINAL (Steamer-free) model wins vs Steamer / ZiPS.

Decision: the deployed system is fully owned (NO Steamer dependency). The final
model = full-population unified, Steamer-free (incumbent champion M02-21 +
prospect model E11). Steamer/ZiPS are external yardsticks only.

Maps win/loss across DEPLOYABLE segments (known at projection time — no
realized-PA conditioning, which is a selection artifact): player slice,
projected-PA band, age, MLB experience, Opening-Day roster status.
Metrics per segment: MAE + Spearman for ours / Steamer / ZiPS, winner flagged.

Output: research/E25_winloss_map.md, data/processed/winloss_segments.csv
"""
import sys

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

PT = "/Users/willcahoon/playing_time_model"
EXP = f"{PT}/expansion"

lines = ["# Expansion E25 — Final (Steamer-free) Model: Win/Loss Map", ""]


def log(s=""):
    lines.append(s)
    print(s)


full = pd.read_parquet(f"{EXP}/data/processed/full_population_proj.parquet")
pub = pd.read_parquet(f"{PT}/data/raw/public_projections.parquet")
zp = (pub[pub.system == "zips"][["mlbam_id", "season", "pa_proj"]]
      .rename(columns={"season": "target_year", "pa_proj": "pa_zips"}))
full = full.merge(zp, on=["mlbam_id", "target_year"], how="left")

# deployable attributes (known at prediction time = feature year t)
sp = pd.read_parquet(f"{PT}/data/processed/usage_spine.parquet")[["mlbam_id", "season", "pa", "age"]]
mlb = sp.sort_values("season")
mlb["career_pa_through_t"] = mlb.groupby("mlbam_id").pa.cumsum()
feat = mlb.rename(columns={"season": "fy"})
feat["target_year"] = feat.fy + 1
full = full.merge(feat[["mlbam_id", "target_year", "age", "career_pa_through_t"]],
                  on=["mlbam_id", "target_year"], how="left")
ros = pd.read_parquet(f"{PT}/data/raw/od_rosters.parquet")
ros = ros[ros.mlbam_id.notna()].astype({"mlbam_id": int})
act = (ros[ros.roster_type == "active"][["mlbam_id", "target_year"]]
       .drop_duplicates().assign(on_od=1))
full = full.merge(act, on=["mlbam_id", "target_year"], how="left")
full["on_od"] = full.on_od.fillna(0)

c = full.dropna(subset=["pred", "pa_steamer", "pa_zips"]).copy()
y_all = c.pa_next.values
log(f"- common universe (ours ∩ Steamer ∩ ZiPS): {len(c)} player-seasons, "
    f"targets 2023-25\n")


def row(label, mask):
    s = c[mask]
    if len(s) < 25:
        return None
    y = s.pa_next.values
    def mae(col): return float(np.abs(s[col] - y).mean())
    def rho(col): return float(spearmanr(s[col], y).statistic)
    om, sm, zm = mae("pred"), mae("pa_steamer"), mae("pa_zips")
    orh, srh = rho("pred"), rho("pa_steamer")
    win_mae = "OURS" if om <= sm else "steam"
    win_rho = "OURS" if orh >= srh else "steam"
    return {"segment": label, "n": len(s),
            "MAE_ours": round(om, 1), "MAE_steam": round(sm, 1), "MAE_zips": round(zm, 1),
            "rho_ours": round(orh, 3), "rho_steam": round(srh, 3),
            "MAE_win": win_mae, "rho_win": win_rho}


segs = []
segs.append(row("ALL", c.index == c.index))
segs.append(("slice", None))
segs.append(row("  incumbents", c.slice == "incumbent"))
segs.append(row("  prospects", c.slice == "prospect"))
segs.append(("projected-PA band (ours)", None))
for lo, hi, lab in [(0, 100, "  proj <100"), (100, 300, "  proj 100-300"),
                    (300, 500, "  proj 300-500"), (500, 9999, "  proj 500+")]:
    segs.append(row(lab, (c.pred >= lo) & (c.pred < hi)))
segs.append(("age", None))
for lo, hi, lab in [(0, 24, "  age <=23"), (24, 28, "  age 24-27"),
                    (28, 32, "  age 28-31"), (32, 99, "  age 32+")]:
    segs.append(row(lab, (c.age >= lo) & (c.age < hi)))
segs.append(("MLB experience (career PA thru t)", None))
for lo, hi, lab in [(0, 1, "  no MLB (debut yr)"), (1, 500, "  rookie <500"),
                    (500, 2000, "  established 500-2k"), (2000, 1e9, "  veteran 2k+")]:
    segs.append(row(lab, (c.career_pa_through_t.fillna(0) >= lo) & (c.career_pa_through_t.fillna(0) < hi)))
segs.append(("Opening-Day roster", None))
segs.append(row("  on OD active roster", c.on_od == 1))
segs.append(row("  NOT on OD roster", c.on_od == 0))

out = []
log(f"{'segment':34s}{'n':>5s}{'MAE ours':>9s}{'MAE stm':>8s}{'MAE zip':>8s}"
    f"{'rho ours':>9s}{'rho stm':>8s}  win(MAE/rho)")
for s in segs:
    if s is None:
        continue
    if isinstance(s, tuple):
        log(f"\n[{s[0]}]")
        continue
    out.append(s)
    log(f"{s['segment']:34s}{s['n']:5d}{s['MAE_ours']:9.1f}{s['MAE_steam']:8.1f}"
        f"{s['MAE_zips']:8.1f}{s['rho_ours']:9.3f}{s['rho_steam']:8.3f}  "
        f"{s['MAE_win']}/{s['rho_win']}")

pd.DataFrame(out).to_csv(f"{EXP}/data/processed/winloss_segments.csv", index=False)
log("\n## Summary")
om = np.abs(c.pred - y_all).mean(); sm = np.abs(c.pa_steamer - y_all).mean()
log(f"- overall MAE ours {om:.1f} vs Steamer {sm:.1f}; rho ours "
    f"{spearmanr(c.pred, y_all).statistic:.3f} vs Steamer "
    f"{spearmanr(c.pa_steamer, y_all).statistic:.3f}")
log("- ZiPS shown for MAE context (it over-projects PA; weak on this task).")

with open(f"{EXP}/research/E25_winloss_map.md", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\nreport written")
