# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Expansion E29 — How much of the oracle ceiling does ACHIEVABLE OD role
resolution capture? (the build-decision test)

E28: oracle allocation (perfect realized usage ranks) MAE 59.6 vs champion
94.5 — huge ceiling, but auto (rank by model) captures none. The realistic
in-house build resolves OPENING-DAY roles (the depth chart), NOT mid-season
injuries/call-ups. So the achievable version ranks by the Opening-Day depth
chart and applies the same structural role-PA prior.

  team usage rank = order within team by (depth_rank asc, model pred desc)
    -> starters above backups (from the chart), model breaks within-tier ties
  apply training rank->PA prior (E28 engine)

Compares: champion / auto (model rank) / DEPTH-CHART rank (achievable) /
oracle (ceiling) / Steamer. The depth-chart row vs oracle = how much the
manual layer can realistically capture.

Output: research/E29_depthchart_alloc.md
"""
import sys

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor

PT = "/Users/willcahoon/playing_time_model"
EXP = f"{PT}/expansion"
sys.path.insert(0, f"{PT}/pipeline")
import ptm_lib as L  # noqa: E402

lines = ["# Expansion E29 — Depth-Chart Allocation: achievable vs ceiling", ""]


def log(s=""):
    lines.append(s)
    print(s)


# champion assembly (M02-21)
inc, CHAMP = L.champion_pairs()
inc["target_year"] = inc.season + 1
txf = pd.read_parquet(f"{PT}/data/processed/tx_features.parquet")
inc = inc.merge(txf, on=["mlbam_id", "target_year"], how="left")
TXALL = [c for c in txf.columns if c not in ("mlbam_id", "target_year")]
k = inc.target_year >= 2004
inc.loc[k, TXALL] = inc.loc[k, TXALL].fillna(0)
od = pd.read_parquet(f"{PT}/data/processed/od_features.parquet")
inc = inc.merge(od, on=["mlbam_id", "target_year"], how="left")
ODF = ["on_40man_od", "on_active_od", "od_pos_depth", "od_team_pos_players"]
kc = k & (inc.target_year != 2020)
inc.loc[kc, ["on_40man_od", "on_active_od"]] = inc.loc[kc, ["on_40man_od", "on_active_od"]].fillna(0)
ijf = pd.read_parquet(f"{PT}/data/processed/injury_features.parquet")
inc = inc.merge(ijf, on=["mlbam_id", "target_year"], how="left")
PANELF = ["il_stints_t", "il_days_t", "career_il_stints", "career_il_days"]
ki = inc.target_year >= 2016
inc.loc[ki, PANELF] = inc.loc[ki, PANELF].fillna(0)
sev = pd.read_parquet(f"{PT}/data/processed/injury_severity.parquet")
inc = inc.merge(sev, on=["mlbam_id", "target_year"], how="left")
SEVF = ["od_il_level", "od_region_exp_days"]
ros = pd.read_parquet(f"{PT}/data/raw/od_rosters.parquet")
ros = ros[ros.mlbam_id.notna()].astype({"mlbam_id": int})
ilr = (ros[ros.status.isin(["D7", "D10", "D15", "D60"])]
       [["mlbam_id", "target_year"]].drop_duplicates().assign(on_il_at_od=1))
inc = inc.merge(ilr, on=["mlbam_id", "target_year"], how="left")
inc.loc[k, "on_il_at_od"] = inc.loc[k, "on_il_at_od"].fillna(0)
inc.loc[k, SEVF] = inc.loc[k, SEVF].fillna(0)
F = CHAMP + TXALL + ODF + PANELF + ["on_il_at_od"] + SEVF
inc = inc.drop(columns=[c for c in ["team_id"] if c in inc.columns])
team = (ros[ros.roster_type == "active"][["mlbam_id", "target_year", "team_id"]]
        .drop_duplicates(["mlbam_id", "target_year"]))
inc = inc.merge(team, on=["mlbam_id", "target_year"], how="left")
dc = pd.read_parquet(f"{EXP}/data/processed/depth_rank.parquet")
inc = inc.merge(dc[["mlbam_id", "target_year", "depth_rank"]], on=["mlbam_id", "target_year"], how="left")

train = inc[inc.target_year <= 2022].copy()
test = inc[inc.target_year.isin([2023, 2024, 2025])].copy()
mdl = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05, random_state=7).fit(train[F].fillna(0), train.pa_next)
train["pred"] = np.clip(mdl.predict(train[F].fillna(0)), 0, None)
test["pred"] = np.clip(mdl.predict(test[F].fillna(0)), 0, None)

# structural rank->PA prior (training, realized usage rank within OD team)
tt = train.dropna(subset=["team_id"]).copy()
tt["rank"] = tt.groupby(["target_year", "team_id"]).pa_next.rank(method="first", ascending=False).astype(int)
maxrank = 18
prior = tt.groupby("rank").pa_next.mean().reindex(range(1, maxrank + 1)).ffill()


def alloc(df, sort_cols, ascending):
    d = df.dropna(subset=["team_id"]).copy()
    d = d.sort_values(["target_year", "team_id"] + sort_cols,
                      ascending=[True, True] + ascending)
    d["rk"] = (d.groupby(["target_year", "team_id"]).cumcount() + 1).clip(upper=maxrank)
    d["a"] = d.rk.map(prior).values
    out = pd.Series(df["pred"].values, index=df.index)
    out.loc[d.index] = d.a.values
    return out.values


# depth-chart rank: starters(1) above backups; missing chart -> 6 (deep); ties by pred
test["dr_fill"] = test.depth_rank.fillna(6)
test["auto"] = alloc(test, ["pred"], [False])
test["dcrank"] = alloc(test, ["dr_fill", "pred"], [True, False])
test["oracle"] = alloc(test, ["pa_next"], [False])
for col in ["auto", "dcrank", "oracle"]:
    test[f"bl_{col}"] = 0.5 * test.pred + 0.5 * test[col]

pub = pd.read_parquet(f"{PT}/data/raw/public_projections.parquet")
st = (pub[pub.system == "steamer"][["mlbam_id", "season", "pa_proj"]]
      .rename(columns={"season": "target_year", "pa_proj": "pa_steamer"}))
test = test.merge(st, on=["mlbam_id", "target_year"], how="left")
c = test[test.pa_steamer.notna()].copy(); y = c.pa_next.values
log(f"- test incumbents {len(c)}; on OD depth chart {c.depth_rank.notna().mean():.0%}\n")


def M(name, p):
    err = p - y; ss = ((y - y.mean()) ** 2).sum()
    return {"model": name, "R2": round(1 - (err ** 2).sum() / ss, 4),
            "MAE": round(float(np.abs(err).mean()), 1),
            "RMSE": round(float(np.sqrt((err ** 2).mean())), 1),
            "rho": round(float(spearmanr(p, y).statistic), 4)}


log("## Overall (incumbents, test 2023-25)")
log(pd.DataFrame([
    M("champion", c.pred.values),
    M("auto-alloc (model rank)", c.auto.values),
    M("DEPTH-CHART alloc (achievable)", c.dcrank.values),
    M("  blend champ+depthchart", c.bl_dcrank.values),
    M("ORACLE alloc (ceiling)", c.oracle.values),
    M("Steamer (yardstick)", c.pa_steamer.values)]).to_string(index=False))

log("\n## pred>=500 band — MAE")
s = c[c.pred >= 500]
for col, lab in [("pred", "champion"), ("auto", "auto"), ("dcrank", "depth-chart"),
                 ("bl_dcrank", "blend+depthchart"), ("oracle", "ORACLE"), ("pa_steamer", "Steamer")]:
    log(f"- {lab:18s} {np.abs(s[col]-s.pa_next).mean():.1f}")

# how much of the ceiling captured
ch = np.abs(c.pred - y).mean(); orc = np.abs(c.oracle - y).mean()
dcm = np.abs(c.dcrank - y).mean(); bdc = np.abs(c.bl_dcrank - y).mean()
best_dc = min(dcm, bdc)
log(f"\n## Ceiling capture (overall MAE): champion {ch:.1f} -> oracle {orc:.1f} "
    f"(ceiling {ch-orc:.1f} PA). Best achievable (depth-chart) {best_dc:.1f} "
    f"= {max(0,(ch-best_dc))/(ch-orc)*100:.0f}% of ceiling.")
log("- decision: if achievable capture is large AND beats Steamer (90.3) -> "
    "build the curated layer; if ~0 -> OD role knowledge doesn't help, skip.")

with open(f"{EXP}/research/E29_depthchart_alloc.md", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\nreport written")
