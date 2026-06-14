# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Expansion E28 — Curated PA allocation engine + ORACLE ceiling test.

Builds the in-house allocation layer that would fill the curated-playing-time
gap, and measures its ceiling so we know whether the manual build is worth it.

ENGINE: allocate a team's PA down its depth chart by USAGE RANK using a
structural role-PA prior learned from history (rank1 ~ everyday ~640, ...,
deep ranks ~ small). Ranks beyond the roster naturally absorb the ~15%
call-up "replacement pool" — so summing the roster's priors lands near the
real team total without forcing it (the fix to E24's failure).

THREE depth-chart sources for the SAME engine:
  champion      our model (baseline, no allocation)
  AUTO-alloc    rank by MODEL prediction        (deployable, no human)
  ORACLE-alloc  rank by REALIZED PA             (perfect role resolution =
                upper bound of human curation; LEAKAGE — ceiling only)
Blends of champion with auto / oracle also reported. Steamer = yardstick.

champion - oracle  = total ceiling of this approach
auto - oracle      = what correct human job-resolution buys (the manual layer)

Incumbents, ranks within OD-active team, train<=2022 priors, test 2023-25.
Output: research/E28_allocator_oracle.md
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

lines = ["# Expansion E28 — Allocation Engine + Oracle Ceiling", ""]


def log(s=""):
    lines.append(s)
    print(s)


# ---- champion assembly (M02-21) ----
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

# OD active team (drop spine team_id collision)
inc = inc.drop(columns=[c for c in ["team_id"] if c in inc.columns])
team = (ros[ros.roster_type == "active"][["mlbam_id", "target_year", "team_id"]]
        .drop_duplicates(["mlbam_id", "target_year"]))
inc = inc.merge(team, on=["mlbam_id", "target_year"], how="left")

train = inc[inc.target_year <= 2022].copy()
test = inc[inc.target_year.isin([2023, 2024, 2025])].copy()
mdl = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05, random_state=7).fit(train[F].fillna(0), train.pa_next)
train["pred"] = np.clip(mdl.predict(train[F].fillna(0)), 0, None)
test["pred"] = np.clip(mdl.predict(test[F].fillna(0)), 0, None)

# ---- structural role-PA prior by usage rank (training, within OD team) ----
def rank_by(df, col):
    return (df.dropna(subset=["team_id"])
              .assign(_r=df.dropna(subset=["team_id"])
                      .groupby(["target_year", "team_id"])[col]
                      .rank(method="first", ascending=False))
              ._r.astype(int))


tr_team = train.dropna(subset=["team_id"]).copy()
tr_team["rank"] = (tr_team.groupby(["target_year", "team_id"]).pa_next
                   .rank(method="first", ascending=False).astype(int))
prior = tr_team.groupby("rank").pa_next.mean()
maxrank = 18
prior = prior.reindex(range(1, maxrank + 1)).ffill()
log("- role-PA prior by usage rank (training): "
    + ", ".join(f"r{r}:{prior[r]:.0f}" for r in [1, 2, 3, 5, 8, 10, 13]))


def allocate(df, rank_col):
    d = df.dropna(subset=["team_id"]).copy()
    d["rk"] = (d.groupby(["target_year", "team_id"])[rank_col]
               .rank(method="first", ascending=False).astype(int).clip(upper=maxrank))
    d["alloc"] = d.rk.map(prior).values
    out = pd.Series(df["pred"].values, index=df.index)   # default = champion
    out.loc[d.index] = d.alloc.values
    return out.values


test["auto"] = allocate(test, "pred")          # deployable
test["oracle"] = allocate(test, "pa_next")     # ceiling (leakage)
test["blend_auto"] = 0.5 * test.pred + 0.5 * test.auto
test["blend_oracle"] = 0.5 * test.pred + 0.5 * test.oracle

pub = pd.read_parquet(f"{PT}/data/raw/public_projections.parquet")
st = (pub[pub.system == "steamer"][["mlbam_id", "season", "pa_proj"]]
      .rename(columns={"season": "target_year", "pa_proj": "pa_steamer"}))
test = test.merge(st, on=["mlbam_id", "target_year"], how="left")
c = test[test.pa_steamer.notna()].copy(); y = c.pa_next.values
log(f"- test incumbents {len(c)}; with OD team {c.team_id.notna().mean():.0%}\n")


def M(name, p):
    err = p - y; ss = ((y - y.mean()) ** 2).sum()
    return {"model": name, "R2": round(1 - (err ** 2).sum() / ss, 4),
            "MAE": round(float(np.abs(err).mean()), 1),
            "RMSE": round(float(np.sqrt((err ** 2).mean())), 1),
            "rho": round(float(spearmanr(p, y).statistic), 4)}


log("## Overall (incumbents, test 2023-25)")
log(pd.DataFrame([
    M("champion (baseline)", c.pred.values),
    M("AUTO-alloc (deployable)", c.auto.values),
    M("blend champ+auto", c.blend_auto.values),
    M("ORACLE-alloc (ceiling)", c.oracle.values),
    M("blend champ+oracle (ceiling)", c.blend_oracle.values),
    M("Steamer (yardstick)", c.pa_steamer.values)]).to_string(index=False))

log("\n## Projected-regular band pred>=500 (where the gap lives) — MAE")
s = c[c.pred >= 500]
for col, lab in [("pred", "champion"), ("auto", "auto"), ("blend_auto", "blend+auto"),
                 ("oracle", "ORACLE"), ("blend_oracle", "blend+ORACLE"), ("pa_steamer", "Steamer")]:
    log(f"- {lab:16s} {np.abs(s[col]-s.pa_next).mean():.1f}")

log("\n## Read")
log("- champion->ORACLE = total ceiling of curated allocation.")
log("- AUTO->ORACLE = value of correct human job-resolution (the manual layer).")
log("- if blend+ORACLE ~ champion, even perfect curation doesn't help -> don't build.")

with open(f"{EXP}/research/E28_allocator_oracle.md", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\nreport written")
