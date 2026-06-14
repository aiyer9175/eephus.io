# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Module 18 — Engine-talent backfill (own-system talent layer).

Replaces the trailing-raw-rate talent block with OUR projection engine's
backbone, regenerated WALK-FORWARD so it is leakage-clean for every ladder
year (the shipped backbone_scores.parquet was fit on transitions sourced
2000-2022, i.e. including transitions INTO 2023 — in-sample for our 2023
test fold; unusable as-is).

Construction (reuses projection_engine's own panel code — no external data):
  panel        = engine's build_panel(): features through season t only
  for target year y in 2004..2026:
      fit ridge per target on transitions with SOURCE season <= y-2
      (target season <= y-1, strictly before y), PA>=200 both sides
      predict rows with season == y-1 -> projection FOR season y
      prediction = rel_pred + league mean of source season

Then ablation in the Steamer-free preseason frame (champ+tx+OD):
  BASE   trailing-rate talent (current champion)
  +ENG   trailing + engine projections
  SWAP   engine projections replace trailing rates

Output: data/processed/engine_talent.parquet, reports/18_engine_talent.md
"""
import sys
from importlib import import_module
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge

import ptm_lib as L

OUT = "/Users/willcahoon/playing_time_model"
ENG = Path.home() / "projection_engine"
sys.path.insert(0, str(ENG / "pipeline"))
B5 = import_module("05_backbone")

TARGETS = B5.TARGETS
lines = ["# Module 18 — Engine-Talent Backfill (walk-forward backbone)", ""]


def log(s=""):
    lines.append(s)
    print(s)


# ---------- 1. panel (engine's own construction, walk-forward features)
log("- building engine panel (features through season t only)...")
panel = B5.prep(B5.build_panel())
lg = pd.read_parquet(ENG / "data" / "league_means.parquet")
lgm = lg[lg.sport == 1].set_index("season")

# transitions for training (target = next season's rel rates)
M = pd.read_parquet(ENG / "data" / "deep_mlb.parquet")
nxt = B5.league_join(M, lg, 1)
for t in TARGETS:
    nxt[f"{t}_relT"] = nxt[t] - nxt[f"{t}_lg"]
nxt = nxt[["batter", "season", "pa"] + [f"{t}_relT" for t in TARGETS]].copy()
nxt["season"] -= 1
nxt = nxt.rename(columns={"pa": "pa_T"})
pr = panel.merge(nxt, on=["batter", "season"])
pr = pr[(pr.pa >= 200) & (pr.pa_T >= 200) & pr.age.notna()]

# ---------- 2. walk-forward refits
rows = []
for y in range(2004, 2027):                      # projection FOR season y
    tr = pr[pr.season <= y - 2]                  # targets <= y-1, before y
    score = panel[panel.season == y - 1].copy()
    if len(tr) < 800 or score.empty:
        continue
    out = score[["batter"]].copy()
    out["target_year"] = y
    for t in TARGETS:
        cols = B5.feats(t)
        q = tr[tr[cols + [f"{t}_relT"]].notna().all(axis=1)]
        mu, sd = q[cols].mean(), q[cols].std().replace(0, 1)
        m = Ridge(alpha=1.0).fit((q[cols] - mu) / sd, q[f"{t}_relT"])
        ok = score[cols].notna().all(axis=1)
        out.loc[ok.values, f"eng_{t}"] = (
            m.predict((score.loc[ok, cols] - mu) / sd)
            + score.loc[ok, "season"].map(lgm[t]).values)
    rows.append(out)
    if y % 5 == 0 or y >= 2023:
        print(f"  {y}: train transitions {len(tr)}, scored {len(out)}", flush=True)

eng = pd.concat(rows, ignore_index=True).rename(columns={"batter": "mlbam_id"})
eng.to_parquet(f"{OUT}/data/processed/engine_talent.parquet", index=False)
log(f"- engine_talent: {eng.shape}, target years "
    f"{eng.target_year.min()}-{eng.target_year.max()}")

# ---------- 3. ablation in the Steamer-free preseason frame
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

pairs = pairs.merge(eng, on=["mlbam_id", "target_year"], how="left")
ENGF = [f"eng_{t}" for t in ["woba", "k_pct", "bb_pct", "iso", "obp", "avg"]]
log(f"- engine coverage on pairs (2004+ targets): "
    f"{pairs.loc[known, 'eng_woba'].notna().mean():.1%}")

TRAIL = ["woba", "woba_marcel", "woba_l1", "obp", "iso", "k_pct", "bb_pct"]
BASE = CHAMP + TXALL + ODF
PLUS = BASE + ENGF
SWAP = [f for f in BASE if f not in TRAIL] + ENGF

train, test = L.split(pairs)


def run(F):
    m = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05,
                                      random_state=7)
    m.fit(train[F], train.pa_next)
    return np.clip(m.predict(test[F]), 0, None)


test = test.copy()
preds = {"BASE trailing talent": run(BASE),
         "+ENG (trailing + engine)": run(PLUS),
         "SWAP (engine only)": run(SWAP)}

log(f"\n## Steamer-free preseason frame (test n={len(test)}, targets 2023-25)")
res = [L.evaluate(k, v, test) for k, v in preds.items()]
log(pd.DataFrame(res).to_string(index=False))

log("\n## Segments (MAE: BASE | +ENG | SWAP)")
segs = {"age<=25": test.age <= 25, "pa_t<200": test.pa_adj < 200,
        "pa_t>=400": test.pa_adj >= 400, "rookie-ish": test.pa_adj_l1.fillna(0) < 50}
for nm, mask in segs.items():
    s = test[mask]
    vals = [L.evaluate("x", preds[k][mask.values], s)["MAE"] for k in preds]
    rhos = [L.evaluate("x", preds[k][mask.values], s)["Spearman"] for k in preds]
    log(f"- {nm} (n={len(s)}): MAE {vals[0]} | {vals[1]} | {vals[2]}   "
        f"rho {rhos[0]} | {rhos[1]} | {rhos[2]}")

with open(f"{OUT}/reports/18_engine_talent.md", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\nreport written")
