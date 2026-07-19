# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Module 11 — Public benchmark: champion vs preseason Steamer / ZiPS PA.

Compares champion (rung E2: usage + talent + minors usage + draft pedigree)
against the archived PRESEASON Steamer and ZiPS PA projections for target
years 2023-2025, on identical player sets (our incumbent test universe ∩
each system's coverage). Realized PA = pa_next (0 if no MLB PA).

Fairness notes reported alongside results:
  * Public systems embed known winter injury news; this model excludes
    medical information BY DESIGN (separate model later) — advantage them.
  * Steamer/ZiPS PA are not depth-chart-curated (FG Depth Charts is, but
    its archive is member-only) — the strongest public PA comp is missing.
  * Universe = players with MLB PA in year t (our ladder universe). Public
    systems also project debutants; not compared here.

Output: reports/11_public_benchmark.md
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

import ptm_lib as L

OUT = "/Users/willcahoon/playing_time_model"
PUB = f"{OUT}/data/raw/public_projections.parquet"
DRAFT = f"{OUT}/data/raw/draft_history.parquet"
DEEP_MIN = "/Users/willcahoon/projection_engine/data/deep_minors.parquet"

lines = ["# Module 11 — Public Benchmark (Steamer / ZiPS preseason PA)", ""]


def log(s=""):
    lines.append(s)
    print(s)


# --- champion features (rung E2, as in Module 9) ---
mn = pd.read_parquet(DEEP_MIN)
aaa = (mn[mn.sport == 11].groupby(["batter", "season"])
       .agg(pa_aaa=("pa", "sum"), woba_aaa=("woba", "mean")).reset_index())
allm = mn.groupby(["batter", "season"]).pa.sum().rename("pa_milb").reset_index()
mfeat = allm.merge(aaa, on=["batter", "season"], how="left") \
            .rename(columns={"batter": "mlbam_id"})

pairs = L.build_pairs()
pairs = pairs.merge(mfeat, on=["mlbam_id", "season"], how="left")
pre = pairs.season < 2008
pairs.loc[~pre, ["pa_milb", "pa_aaa"]] = (
    pairs.loc[~pre, ["pa_milb", "pa_aaa"]].fillna(0))
pairs["pa_aaa_adj"] = pairs.pa_aaa * pairs.scale
pairs["pa_milb_adj"] = pairs.pa_milb * pairs.scale
pairs["mlb_share"] = pairs.pa / (pairs.pa + pairs.pa_milb).replace(0, np.nan)
pairs["shuttle"] = ((pairs.pa > 0) & (pairs.pa_milb >= 50)).astype(float)
pairs.loc[pre, "shuttle"] = np.nan

dr = pd.read_parquet(DRAFT)
pairs = pairs.merge(dr[["mlbam_id", "draft_year", "overall_pick",
                        "signing_bonus"]], on="mlbam_id", how="left")
pairs["drafted"] = pairs.draft_year.notna().astype(int)
pairs["years_since_draft"] = pairs.season - pairs.draft_year
pairs["log_bonus"] = np.log1p(pairs.signing_bonus)
pairs["top10_pick"] = (pairs.overall_pick <= 10).astype(int)
pairs["first_rounder"] = (pairs.overall_pick <= 30).astype(int)

CHAMP = (L.FEATS_B
         + ["pa_aaa_adj", "pa_milb_adj", "woba_aaa", "mlb_share", "shuttle"]
         + ["overall_pick", "log_bonus", "drafted", "years_since_draft",
            "top10_pick", "first_rounder"])

train, test = L.split(pairs)
m = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05,
                                  random_state=7)
m.fit(train[CHAMP], train.pa_next)
test = test.copy()
test["pa_champ"] = np.clip(m.predict(test[CHAMP]), 0, None)
test["target_year"] = test.season + 1

# --- public systems ---
pub = pd.read_parquet(PUB)
pub = pub[pub.season.isin([2023, 2024, 2025])]
wide = pub.pivot_table(index=["mlbam_id", "season"], columns="system",
                       values="pa_proj").reset_index()
wide = wide.rename(columns={"season": "target_year",
                            "steamer": "pa_steamer", "zips": "pa_zips"})
test = test.merge(wide, on=["mlbam_id", "target_year"], how="left")

log(f"- test universe: {len(test)} player-seasons (targets 2023-2025)")
log(f"- Steamer coverage of universe: {test.pa_steamer.notna().mean():.1%}, "
    f"ZiPS: {test.pa_zips.notna().mean():.1%}")


def table(mask, label):
    tt = test[mask].copy()
    log(f"\n## {label} (n={len(tt)})")
    rows = [L.evaluate("Champion (E2 GBM)", tt.pa_champ.values, tt)]
    if tt.pa_steamer.notna().all():
        rows.append(L.evaluate("Steamer preseason", tt.pa_steamer.values, tt))
    if tt.pa_zips.notna().all():
        rows.append(L.evaluate("ZiPS preseason", tt.pa_zips.values, tt))
    rows.append(L.evaluate("Persistence pa_t", tt.pa_adj.values, tt))
    log(pd.DataFrame(rows).to_string(index=False))
    return tt


# head-to-head on common coverage
common = test.pa_steamer.notna() & test.pa_zips.notna()
tt = table(common, "Common universe (champion ∩ Steamer ∩ ZiPS)")

table(test.pa_steamer.notna(), "Champion vs Steamer (full Steamer overlap)")

log("\n## Segments (common universe)")
for nm, mask in {"age<=25": tt.age <= 25,
                 "pa_t<200": tt.pa_adj < 200,
                 "pa_t>=400": tt.pa_adj >= 400,
                 "by year 2023": tt.target_year == 2023,
                 "by year 2024": tt.target_year == 2024,
                 "by year 2025": tt.target_year == 2025}.items():
    s = tt[mask]
    c = L.evaluate("c", s.pa_champ.values, s)
    st = L.evaluate("s", s.pa_steamer.values, s)
    z = L.evaluate("z", s.pa_zips.values, s)
    log(f"- {nm} (n={len(s)}): MAE champ {c['MAE']} | steamer {st['MAE']} | "
        f"zips {z['MAE']}   rho {c['Spearman']} | {st['Spearman']} | "
        f"{z['Spearman']}")

log("\n## Caveats")
log("- Public systems embed winter injury knowledge; this model excludes "
    "medical info by design (separate model planned). Advantage: them.")
log("- FG Depth Charts (curated PA, strongest public comp) archive is "
    "member-only; not compared. Steamer/ZiPS PA are model-allocated.")
log("- Incumbent universe only (MLB PA in year t); debutants excluded.")

with open(f"{OUT}/reports/11_public_benchmark.md", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\nreport written")
