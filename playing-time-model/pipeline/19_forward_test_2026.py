# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Module 19 — Registered forward test vs FanGraphs Depth Charts, season 2026.

The past comparison vs true-preseason DC is unsettleable (FG never archives
it; only a Dec-2024 vintage existed for 2025). For 2026, Wayback has genuine
preseason captures: DC 2026-02-26, ATC 2026-01-31. This module FREEZES a
five-way table now and defers scoring to season end:

  pa_ours      champion (Steamer-free: usage+talent+minors+draft+tx+OD),
               trained on all targets <= 2025, scored on feature-year 2025
  pa_dc        FG Depth Charts, Feb 26 2026 capture (their PT model)
  pa_atc       ATC, Jan 31 2026 capture
  pa_steamer / pa_zips   steamer_2026 / zips_2026 archive types if served

Provisional scoreboard (PARTIAL season through yesterday, ~40%): Spearman
vs 2026 PA-to-date only — levels not comparable mid-season. Final scoring:
after the season (rerun 01 pull, then this module with --score).

Output: data/processed/forward_test_2026.parquet,
        reports/19_forward_test_2026.md
"""
import json
import sys
import time

import numpy as np
import pandas as pd
import requests
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor

import ptm_lib as L

OUT = "/Users/willcahoon/playing_time_model"
RAW = f"{OUT}/data/raw"

lines = ["# Module 19 — Registered Forward Test: 2026 vs FG Depth Charts", ""]


def log(s=""):
    lines.append(s)
    print(s)


# ---- our frozen 2026 projection (feature year 2025 -> target 2026)
sp = L.prepare_spine()
pairs = L.build_pairs(sp)
pairs = L.add_draft(L.add_minors(pairs)) if False else pairs  # built below via champion_pairs pattern

# train pairs with full champion features
train = L.add_draft(L.add_minors(L.build_pairs(sp)))
CHAMP = L.FEATS_B + L.MINORS_F + L.DRAFT_F
train["target_year"] = train.season + 1

# scoring frame: feature year 2025
score = sp[sp.season == 2025].copy()
score = L.add_draft(L.add_minors(score))
score["target_year"] = 2026

txf = pd.read_parquet(f"{OUT}/data/processed/tx_features.parquet")
od = pd.read_parquet(f"{OUT}/data/processed/od_features.parquet")
TXALL = [c for c in txf.columns if c not in ("mlbam_id", "target_year")]
ODF = ["on_40man_od", "on_active_od", "od_pos_depth", "od_team_pos_players"]
for df_ in (train, score):
    df_.drop(columns=[c for c in TXALL + ODF if c in df_], inplace=True,
             errors="ignore")
train = train.merge(txf, on=["mlbam_id", "target_year"], how="left")
score = score.merge(txf, on=["mlbam_id", "target_year"], how="left")
train = train.merge(od, on=["mlbam_id", "target_year"], how="left")
score = score.merge(od, on=["mlbam_id", "target_year"], how="left")
for df_ in (train, score):
    k = df_.target_year >= 2004
    df_.loc[k, TXALL] = df_.loc[k, TXALL].fillna(0)
    k2 = k & (df_.target_year != 2020)
    df_.loc[k2, ["on_40man_od", "on_active_od"]] = (
        df_.loc[k2, ["on_40man_od", "on_active_od"]].fillna(0))

BASE = CHAMP + TXALL + ODF
train = train.dropna(subset=["age"])
score = score.dropna(subset=["age"])
m = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05,
                                  random_state=7)
m.fit(train[BASE], train.pa_next)
score["pa_ours"] = np.clip(m.predict(score[BASE]), 0, None)
log(f"- trained on {len(train)} pairs (targets <=2025); scored "
    f"{len(score)} incumbents for 2026")

# ---- public preseason vintages
frozen = score[["mlbam_id", "player_name", "primary_pos", "age",
                "pa_ours"]].copy()
for name, col in [("dc_2026", "pa_dc"), ("atc_2026", "pa_atc")]:
    d = pd.DataFrame(json.load(open(f"{RAW}/{name}_wayback.json")))
    d = d.rename(columns={"xMLBAMID": "mlbam_id", "PA": col})
    frozen = frozen.merge(d[["mlbam_id", col]], on="mlbam_id", how="left")

H = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
for t, col in [("steamer_2026", "pa_steamer"), ("zips_2026", "pa_zips")]:
    r = requests.get("https://www.fangraphs.com/api/projections",
                     params={"type": t, "stats": "bat", "pos": "all"},
                     headers=H, timeout=60)
    if r.status_code == 200:
        d = pd.DataFrame(r.json()).rename(
            columns={"xMLBAMID": "mlbam_id", "PA": col})
        d = d[d.mlbam_id > 0].drop_duplicates("mlbam_id")
        frozen = frozen.merge(d[["mlbam_id", col]], on="mlbam_id", how="left")
        log(f"- {t} archive served: {d.shape[0]} rows")
    else:
        frozen[col] = np.nan
        log(f"- {t} archive NOT served ({r.status_code}) — frozen without it")
    time.sleep(1)

frozen["frozen_at"] = "2026-06-12"
frozen.to_parquet(f"{OUT}/data/processed/forward_test_2026.parquet",
                  index=False)
SYS = ["pa_ours", "pa_dc", "pa_atc", "pa_steamer", "pa_zips"]
log(f"- frozen table saved: {frozen.shape}; coverage "
    f"{ {s: f'{frozen[s].notna().mean():.0%}' for s in SYS} }")

# ---- provisional scoreboard: Spearman vs PA-to-date (partial season)
cur = sp[sp.season == 2026][["mlbam_id", "pa"]].rename(
    columns={"pa": "pa_2026_todate"})
prov = frozen.merge(cur, on="mlbam_id", how="left")
prov["pa_2026_todate"] = prov.pa_2026_todate.fillna(0)
common = prov.dropna(subset=["pa_dc", "pa_atc"])
log(f"\n## PROVISIONAL scoreboard — Spearman vs 2026 PA through 6/11 "
    f"(~40% of season; levels not comparable, ranks only; n={len(common)})")
for s in SYS:
    sub = common.dropna(subset=[s])
    if len(sub) < 100:
        log(f"- {s}: insufficient coverage")
        continue
    rho = spearmanr(sub[s], sub.pa_2026_todate).statistic
    log(f"- {s}: rho {rho:.4f} (n={len(sub)})")
log("\nFinal scoring after the 2026 season: rerun pipeline/01 pull, then "
    "join realized PA to forward_test_2026.parquet and score all systems "
    "on R2/RMSE/MAE/Spearman. Universe = incumbents (MLB PA in 2025); "
    "our model excludes injury info BY DESIGN — DC/ATC embed spring "
    "injury news; note this when reading MAE.")

with open(f"{OUT}/reports/19_forward_test_2026.md", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\nreport written")
