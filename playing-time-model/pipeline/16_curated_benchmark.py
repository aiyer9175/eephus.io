# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Module 16 — Curated-system benchmark on target 2025 (ATC + Depth Charts).

FG never archives ATC / Depth Charts (overwritten in-season; member API
500s on those type suffixes — verified with an authenticated session).
Wayback Machine captures of the LIVE api are the only preseason vintages:

  ATC 2025  capture 2025-03-07 — genuine preseason (Soto NYM 674 PA)
  DC  2025  capture 2024-12-02 — EARLY-winter vintage (Soto teamless 700 PA,
            predates his Dec 8 signing). Understates DC's true March skill;
            read its numbers with that handicap in mind.

No usable spring captures exist for 2023/2024, so this is a one-year,
five-system shootout on target 2025: Steamer, ZiPS, ATC, DC(Dec) vs our
F-pre+OD model and the blend.

DC's Dec-2024 payload predates xMLBAMID; joined via a FanGraphs-ID bridge
built from the ATC capture + archived steamer/zips pulls.

Output: reports/16_curated_benchmark.md
"""
import json
import time

import numpy as np
import pandas as pd
import requests
from sklearn.ensemble import HistGradientBoostingRegressor

import ptm_lib as L

OUT = "/Users/willcahoon/playing_time_model"
RAW = f"{OUT}/data/raw"

lines = ["# Module 16 — Curated Benchmark (target 2025: ATC + Depth Charts)", ""]


def log(s=""):
    lines.append(s)
    print(s)


# ---- FG-id -> MLBAM bridge (ATC capture + current API pulls carry both ids)
atc = pd.DataFrame(json.load(open(f"{RAW}/atc_2025_wayback.json")))
bridge = atc[["playerids", "xMLBAMID"]].dropna().drop_duplicates()
H = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
for t in ["steamer", "steamer_2025", "zips_2025"]:
    r = requests.get("https://www.fangraphs.com/api/projections",
                     params={"type": t, "stats": "bat", "pos": "all"},
                     headers=H, timeout=60)
    df = pd.DataFrame(r.json())
    bridge = pd.concat([bridge, df[["playerids", "xMLBAMID"]].dropna()])
    time.sleep(1)
bridge = (bridge[bridge.xMLBAMID > 0].drop_duplicates("playerids")
          .rename(columns={"xMLBAMID": "mlbam_id"}))
log(f"- FG-id bridge: {len(bridge)} ids")

dc = pd.DataFrame(json.load(open(f"{RAW}/dc_2025dec_wayback.json")))
dc = dc.merge(bridge, on="playerids", how="left")
log(f"- DC Dec-2024 rows mlbam-linked: {dc.mlbam_id.notna().mean():.1%} "
    f"of {len(dc)}")

atc_pa = (atc.rename(columns={"xMLBAMID": "mlbam_id", "PA": "pa_atc"})
          [["mlbam_id", "pa_atc"]])
dc_pa = dc.dropna(subset=["mlbam_id"]).astype({"mlbam_id": int}) \
          .rename(columns={"PA": "pa_dc"})[["mlbam_id", "pa_dc"]]

# ---- our model: rebuild the 14b frame (champ + tx + OD + steamer prior)
pairs, CHAMP = L.champion_pairs()
pairs["target_year"] = pairs.season + 1

txf = pd.read_parquet(f"{OUT}/data/processed/tx_features.parquet")
pairs = pairs.merge(txf, on=["mlbam_id", "target_year"], how="left")
TXALL = [c for c in txf.columns if c not in ("mlbam_id", "target_year")]
known = pairs.target_year >= 2004
pairs.loc[known, TXALL] = pairs.loc[known, TXALL].fillna(0)

od = pd.read_parquet(f"{OUT}/data/processed/od_features.parquet")
pairs = pairs.merge(od, on=["mlbam_id", "target_year"], how="left")
ODF = ["on_40man_od", "on_active_od", "od_pos_depth", "od_team_pos_players"]
cov = known & (pairs.target_year != 2020)
pairs.loc[cov, ["on_40man_od", "on_active_od"]] = (
    pairs.loc[cov, ["on_40man_od", "on_active_od"]].fillna(0))

pub = pd.read_parquet(f"{RAW}/public_projections.parquet")
st = (pub[pub.system == "steamer"]
      [["mlbam_id", "season", "pa_proj", "woba_proj", "g_proj"]]
      .rename(columns={"season": "target_year", "pa_proj": "pa_steamer",
                       "woba_steamer" if False else "woba_proj": "woba_steamer",
                       "g_proj": "g_steamer"}))
pairs = pairs.merge(st, on=["mlbam_id", "target_year"], how="left")
zp = (pub[pub.system == "zips"][["mlbam_id", "season", "pa_proj"]]
      .rename(columns={"season": "target_year", "pa_proj": "pa_zips"}))
pairs = pairs.merge(zp, on=["mlbam_id", "target_year"], how="left")

FPRE = (CHAMP + ["pa_steamer", "woba_steamer", "g_steamer"] + TXALL + ODF)
train, test = L.split(pairs)
m = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05,
                                  random_state=7)
m.fit(train[FPRE], train.pa_next)

t25 = test[test.target_year == 2025].copy()
t25["pa_ours"] = np.clip(m.predict(t25[FPRE]), 0, None)
t25 = t25.merge(atc_pa, on="mlbam_id", how="left")
t25 = t25.merge(dc_pa, on="mlbam_id", how="left")

SYS = ["pa_steamer", "pa_zips", "pa_atc", "pa_dc"]
log(f"\n- 2025 test universe: {len(t25)}; coverage "
    f"{ {s: f'{t25[s].notna().mean():.0%}' for s in SYS} }")

common = t25.dropna(subset=SYS)
log(f"\n## Five-system shootout, common universe (n={len(common)})")
rows = [L.evaluate("Ours (F-pre+OD)", common.pa_ours.values, common),
        L.evaluate("Steamer (preseason)", common.pa_steamer.values, common),
        L.evaluate("ZiPS (preseason)", common.pa_zips.values, common),
        L.evaluate("ATC (Mar 7 capture)", common.pa_atc.values, common),
        L.evaluate("DC (Dec 2 capture*)", common.pa_dc.values, common),
        L.evaluate("blend ours+Steamer", 0.5 * common.pa_ours.values
                   + 0.5 * common.pa_steamer.values, common),
        L.evaluate("blend ours+ATC", 0.5 * common.pa_ours.values
                   + 0.5 * common.pa_atc.values, common)]
log(pd.DataFrame(rows).to_string(index=False))
log("\n*DC capture is Dec 2, 2024 — pre-offseason-moves vintage; "
    "handicapped vs the others.")

big = t25[t25.pa_steamer.notna() & t25.pa_atc.notna()]
log(f"\n## Ours vs Steamer vs ATC (n={len(big)}, no DC/ZiPS constraint)")
rows = [L.evaluate("Ours", big.pa_ours.values, big),
        L.evaluate("Steamer", big.pa_steamer.values, big),
        L.evaluate("ATC", big.pa_atc.values, big),
        L.evaluate("blend ours+ATC", 0.5 * big.pa_ours.values
                   + 0.5 * big.pa_atc.values, big),
        L.evaluate("blend ours+ATC+Steamer", (big.pa_ours.values
                   + big.pa_atc.values + big.pa_steamer.values) / 3, big)]
log(pd.DataFrame(rows).to_string(index=False))

with open(f"{OUT}/reports/16_curated_benchmark.md", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\nreport written")
