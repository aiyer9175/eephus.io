# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Expansion E21 — FINAL MODEL benchmark vs Steamer + ZiPS.

The final Playing Time+ projection = full-population unified model (E20):
  incumbents -> champion (parent M02-21: usage+talent+minors+draft+tx+
                Opening-Day rosters+injury+severity)
  prospects  -> E11 model (minors perf+draft+40man+OD-roster+FV)
Steamer-free; blend = (ours + Steamer)/2.

Realized = actual MLB PA in the target season (0 if none). Targets 2023-25.
Reports full population + incumbent/prospect slices vs Steamer and ZiPS.

Output: research/E21_final_benchmark.md, data/processed/final_benchmark.csv
"""
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

PT = "/Users/willcahoon/playing_time_model"
EXP = f"{PT}/expansion"

lines = ["# Expansion E21 — FINAL MODEL vs Steamer + ZiPS", ""]


def log(s=""):
    lines.append(s)
    print(s)


full = pd.read_parquet(f"{EXP}/data/processed/full_population_proj.parquet")
pub = pd.read_parquet(f"{PT}/data/raw/public_projections.parquet")
zp = (pub[pub.system == "zips"][["mlbam_id", "season", "pa_proj"]]
      .rename(columns={"season": "target_year", "pa_proj": "pa_zips"}))
full = full.merge(zp, on=["mlbam_id", "target_year"], how="left")
full["blend"] = 0.5 * full.pred + 0.5 * full.pa_steamer


def M(name, pred, y):
    err = np.asarray(pred) - y
    ss = ((y - y.mean()) ** 2).sum()
    return {"system": name, "n": len(y),
            "R2": round(1 - (err ** 2).sum() / ss, 4),
            "MAE": round(float(np.abs(err).mean()), 1),
            "RMSE": round(float(np.sqrt((err ** 2).mean())), 1),
            "Spearman": round(float(spearmanr(pred, y).statistic), 4)}


def table(df, title):
    c = df.dropna(subset=["pred", "pa_steamer", "pa_zips"])
    y = c.pa_next.values
    rows = [M("Ours (final, Steamer-free)", c.pred.values, y),
            M("Steamer", c.pa_steamer.values, y),
            M("ZiPS", c.pa_zips.values, y),
            M("Blend (ours + Steamer)", c.blend.values, y)]
    log(f"\n## {title} (common universe n={len(c)})")
    log(pd.DataFrame(rows).to_string(index=False))
    return pd.DataFrame(rows).assign(slice=title)


log(f"- coverage: ours projects 100% of {len(full)} players; "
    f"Steamer {full.pa_steamer.notna().mean():.0%}, "
    f"ZiPS {full.pa_zips.notna().mean():.0%}")
allt = [table(full, "FULL POPULATION"),
        table(full[full.slice == "incumbent"], "Incumbents"),
        table(full[full.slice == "prospect"], "Prospects")]
pd.concat(allt).to_csv(f"{EXP}/data/processed/final_benchmark.csv", index=False)

log("\n## Notes")
log("- Targets 2023-2025 pooled; realized = actual MLB PA (0 if no MLB time).")
log("- Ours uses NO FanGraphs inputs; blend adds Steamer as a partner.")
log("- ZiPS PA is a rate-system allocation, not a playing-time model — its low")
log("  R2 (esp. on prospects) reflects that, and validates the harness.")
with open(f"{EXP}/research/E21_final_benchmark.md", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\nreport written")
