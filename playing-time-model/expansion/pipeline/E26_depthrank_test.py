# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Expansion E26 — Does the depth-chart depth-rank feature close the gap?

Adds the FACTUAL, owned depth-chart signal (E07: Opening-Day depth rank at
position, 1 = projected starter) to the incumbent champion and tests whether it
closes the Steamer gap in our loss zone (young / borderline / competing-for-a-
job players). Unlike the allocator, this is real published role-resolution
info — the rookie-wins-the-job signal (e.g., Volpe = SS#1) we lacked.

Features: depth_rank (capped), is_starter (rank==1), is_backup (rank>=2),
has_dc. Champion = M02-21. Train<=2022, test 2023-25. Reports overall + loss-
zone segments vs Steamer (external yardstick only — not an input).

Output: research/E26_depthrank_test.md
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

lines = ["# Expansion E26 — Depth-Chart Depth-Rank Feature Test", ""]


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
CHAMP_F = CHAMP + TXALL + ODF + PANELF + ["on_il_at_od"] + SEVF

# depth-rank feature
dc = pd.read_parquet(f"{EXP}/data/processed/depth_rank.parquet")
inc = inc.merge(dc[["mlbam_id", "target_year", "depth_rank"]],
                on=["mlbam_id", "target_year"], how="left")
inc["has_dc"] = inc.depth_rank.notna().astype(int)
inc["is_starter"] = (inc.depth_rank == 1).astype(int)
inc["is_backup"] = (inc.depth_rank >= 2).astype(int)
inc["depth_rank_f"] = inc.depth_rank.fillna(9).clip(upper=9)
DC = ["depth_rank_f", "is_starter", "is_backup", "has_dc"]

# age + experience for segments
sp = pd.read_parquet(f"{PT}/data/processed/usage_spine.parquet")[["mlbam_id", "season", "pa", "age"]]
m2 = sp.sort_values("season"); m2["career_pa"] = m2.groupby("mlbam_id").pa.cumsum()
m2 = m2.rename(columns={"season": "fyr"}); m2["target_year"] = m2.fyr + 1
inc = inc.merge(m2[["mlbam_id", "target_year", "career_pa"]], on=["mlbam_id", "target_year"], how="left")

pub = pd.read_parquet(f"{PT}/data/raw/public_projections.parquet")
st = (pub[pub.system == "steamer"][["mlbam_id", "season", "pa_proj"]]
      .rename(columns={"season": "target_year", "pa_proj": "pa_steamer"}))
inc = inc.merge(st, on=["mlbam_id", "target_year"], how="left")

train = inc[inc.target_year <= 2022].copy()
test = inc[inc.target_year.isin([2023, 2024, 2025])].copy()
log(f"- test n={len(test)}; on a depth chart: {test.has_dc.mean():.0%}; "
    f"of those, starters: {(test[test.has_dc==1].is_starter).mean():.0%}")


def fit(F):
    m = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05,
                                      random_state=7).fit(train[F].fillna(0), train.pa_next)
    return np.clip(m.predict(test[F].fillna(0)), 0, None)


test["base"] = fit(CHAMP_F)
test["dcm"] = fit(CHAMP_F + DC)
c = test[test.pa_steamer.notna()].copy(); y = c.pa_next.values


def M(name, p, s=None):
    d = c if s is None else c[s]
    pp = p if s is None else p[s]
    yy = d.pa_next.values; err = pp - yy; ss = ((yy - yy.mean()) ** 2).sum()
    return {"model": name, "n": len(d), "R2": round(1 - (err**2).sum()/ss, 4),
            "MAE": round(float(np.abs(err).mean()), 1),
            "rho": round(float(spearmanr(pp, yy).statistic), 4)}


log("\n## Overall (incumbents, test 2023-25)")
log(pd.DataFrame([M("champion", c.base.values),
                  M("champion + depth-rank", c.dcm.values),
                  M("Steamer (yardstick)", c.pa_steamer.values)]).to_string(index=False))

log("\n## LOSS ZONE — does depth-rank close the gap toward Steamer? (MAE)")
log(f"{'segment':28s}{'n':>5s}{'champ':>8s}{'+DC':>8s}{'Steamer':>9s}")
segs = {"age<=23": c.age <= 23, "rookie <500 PA": c.career_pa.fillna(0) < 500,
        "proj-ish 100-500 (base)": (c.base >= 100) & (c.base < 500),
        "base pred 500+": c.base >= 500, "on OD roster": c.on_active_od == 1}
for nm, s in segs.items():
    d = c[s]
    if len(d) < 20:
        continue
    f = lambda col: float(np.abs(d[col] - d.pa_next).mean())
    log(f"{nm:28s}{len(d):5d}{f('base'):8.1f}{f('dcm'):8.1f}{f('pa_steamer'):9.1f}")

log("\n## rho on loss zone (ranking)")
for nm, s in segs.items():
    d = c[s]
    if len(d) < 20:
        continue
    r = lambda col: float(spearmanr(d[col], d.pa_next).statistic)
    log(f"- {nm} (n={len(d)}): champ {r('base'):.3f} | +DC {r('dcm'):.3f} | "
        f"Steamer {r('pa_steamer'):.3f}")

with open(f"{EXP}/research/E26_depthrank_test.md", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\nreport written")
