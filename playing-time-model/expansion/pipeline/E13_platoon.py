# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Expansion E13 — Platoon share + manager effect (Bucket 13 / Q7).

Platoon usage is the role signal MOST orthogonal to total PA: a platoon bat
can post 400 PA while almost never facing same-handed pitching. From E03
splits + handedness.

platoon_index = same_hand_PA/total_PA  -  league mean same_hand share for that
                handedness & season.  (negative = platoon-protected: faces
                LESS same-hand pitching than a typical hitter of that hand.)
Universe: PA >= 100 (role meaningful); switch hitters excluded (no handedness
platoon). Target = platoon_index next year.

Tests:
  1. reliability (year-over-year) — is platoon usage a stable role?
  2. projectability OOS + new-info-vs-PA (corr with projected PA).
  3. MANAGER EFFECT (Q7): residualize platoon_index from player features,
     attach next-year team's Opening-Day manager, test persistence + OOS lift
     — the leakage-safe test E10 said leadership deserves on a target NOT
     mediated by a single roster transaction.

Output: data/processed/platoon_index.parquet, research/E13_platoon.md
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

lines = ["# Expansion E13 — Platoon Share + Manager Effect", ""]


def log(s=""):
    lines.append(s)
    print(s)


# ---------- platoon index per player-season
pl = pd.read_parquet(f"{EXP}/data/raw/platoon_splits.parquet")
bs = pd.read_parquet(f"{EXP}/data/raw/bat_side.parquet")
w = (pl.pivot_table(index=["mlbam_id", "season"], columns="vs_hand",
                    values="pa", aggfunc="sum").reset_index()
       .rename(columns={"L": "pa_vL", "R": "pa_vR"}).fillna(0))
w["pa_tot"] = w.pa_vL + w.pa_vR
w = w.merge(bs, on="mlbam_id", how="left")
w = w[(w.pa_tot >= 100) & w.bat_side.isin(["L", "R"])].copy()
w["same_share"] = np.where(w.bat_side == "L", w.pa_vL, w.pa_vR) / w.pa_tot
base = (w.groupby(["bat_side", "season"]).same_share.transform("mean"))
w["platoon_index"] = w.same_share - base
w[["mlbam_id", "season", "bat_side", "pa_tot", "same_share",
   "platoon_index"]].to_parquet(f"{EXP}/data/processed/platoon_index.parquet",
                                index=False)
log(f"- platoon universe: {len(w)} player-seasons (PA>=100, L/R bats); "
    f"index sd {w.platoon_index.std():.3f}")

# ---------- pairs + next-year target
pairs, CHAMP = L.champion_pairs()
nx = w[["mlbam_id", "season", "platoon_index"]].copy()
nx["season"] = nx.season - 1
nx = nx.rename(columns={"platoon_index": "platoon_next"})
pairs = pairs.merge(nx, on=["mlbam_id", "season"], how="left")
pairs = pairs.merge(w[["mlbam_id", "season", "platoon_index", "bat_side"]],
                    on=["mlbam_id", "season"], how="left")
pairs["bat_L"] = (pairs.bat_side == "L").astype(float)
P = pairs.dropna(subset=["platoon_next"]).copy()

log(f"\n## 1. Reliability")
rel = P.dropna(subset=["platoon_index"])
log(f"- year-over-year platoon_index r = "
    f"{rel.platoon_index.corr(rel.platoon_next):.3f} (n={len(rel)}) "
    "-> platoon usage is a stable role" if
    rel.platoon_index.corr(rel.platoon_next) > 0.4 else
    f"- year-over-year r = {rel.platoon_index.corr(rel.platoon_next):.3f}")

train = P[P.season + 1 <= 2022]
test = P[(P.season + 1).isin([2023, 2024, 2025])].copy()
FEAT = CHAMP + ["bat_L", "platoon_index"]


def ev(name, pred, t):
    y = t.platoon_next.values
    err = pred - y
    ss = ((y - y.mean()) ** 2).sum()
    return (f"- {name}: R2 {1-(err**2).sum()/ss:.3f}  MAE {np.abs(err).mean():.3f}"
            f"  rho {spearmanr(pred, y).statistic:.3f}")


log("\n## 2. Projectability (target 2023-25) + new-info check")
reg = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05,
                                    random_state=7).fit(train[FEAT],
                                                        train.platoon_next)
pred = reg.predict(test[FEAT])
log(ev("model (champion + handedness + this-yr platoon)", pred, test))
log(ev("naive (this-yr platoon_index)", test.platoon_index.fillna(0).values, test))
pa_proj = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05,
                                        random_state=7).fit(train[CHAMP],
                                                            train.pa_next)
test["pa_hat"] = pa_proj.predict(test[CHAMP])
log(f"- corr(projected PA, platoon_next) = "
    f"{spearmanr(test.pa_hat, test.platoon_next).statistic:.3f}  "
    "(near 0 => platoon is genuinely NEW info beyond PA)")

# ---------- 3. manager effect (Q7)
log("\n## 3. Manager effect (Q7) — leakage-safe residual test")
ros = pd.read_parquet(f"{PT}/data/raw/od_rosters.parquet")
ros = ros[ros.mlbam_id.notna()].astype({"mlbam_id": int})
team = (ros[ros.roster_type == "active"][["mlbam_id", "target_year", "team_id"]]
        .drop_duplicates(["mlbam_id", "target_year"]))
mgr = pd.read_parquet(f"{EXP}/data/raw/managers.parquet") \
        .drop_duplicates(["team_id", "season"]) \
        .rename(columns={"season": "target_year"})
team = team.merge(mgr, on=["team_id", "target_year"], how="left")
P["target_year"] = P.season + 1
P = P.merge(team[["mlbam_id", "target_year", "manager_id"]],
            on=["mlbam_id", "target_year"], how="left")
# player-only OOF residual
P = P.sort_values("target_year").reset_index(drop=True)
P["resid"] = np.nan
for ty in sorted(P.target_year.unique()):
    tr = P[P.target_year < ty]
    if len(tr) < 400:
        continue
    m = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05,
                                      random_state=7).fit(tr[FEAT], tr.platoon_next)
    idx = P.index[P.target_year == ty]
    P.loc[idx, "resid"] = (P.loc[idx, "platoon_next"]
                           - m.predict(P.loc[idx, FEAT]))
ev2 = P.dropna(subset=["resid", "manager_id"])
mgr_agg = (ev2.groupby(["manager_id", "target_year"]).resid.agg(["size", "mean"])
              .reset_index())
mgr_agg = mgr_agg[mgr_agg["size"] >= 4]
# split-half across seasons
odd = ev2[ev2.target_year % 2 == 1].groupby("manager_id").resid.mean()
evn = ev2[ev2.target_year % 2 == 0].groupby("manager_id").resid.mean()
sh = pd.concat([odd.rename("o"), evn.rename("e")], axis=1).dropna()
gm = (mgr_agg["mean"] * mgr_agg["size"]).sum() / mgr_agg["size"].sum()
mm = (mgr_agg.assign(w=mgr_agg["mean"] * mgr_agg["size"]).groupby("manager_id")
             .apply(lambda d: d.w.sum() / d["size"].sum(), include_groups=False))
mn = mgr_agg.groupby("manager_id")["size"].sum()
between = ((mm - gm) ** 2 * mn).sum() / mgr_agg["size"].sum()
total = ((mgr_agg["mean"] - gm) ** 2 * mgr_agg["size"]).sum() / mgr_agg["size"].sum()
log(f"- manager residual split-half (odd vs even seasons): r = "
    f"{sh.o.corr(sh.e):.3f} (n={len(sh)} managers)")
log(f"- between-manager variance share of residual platoon usage: "
    f"{between/total:.1%}")

# OOS: does trailing manager residual improve platoon prediction?
rows = []
for ty in [y for y in sorted(P.target_year.unique()) if y >= 2019]:
    tr = P[P.target_year < ty].dropna(subset=["platoon_next"])
    te = P[P.target_year == ty].dropna(subset=["platoon_next"])
    if len(te) < 30:
        continue
    prior = ev2[(ev2.target_year < ty) & (ev2.target_year >= ty - 3)]
    mtrail = prior.groupby("manager_id").resid.mean().rename("mgr_trail")
    trX = tr.merge(mtrail, on="manager_id", how="left")
    teX = te.merge(mtrail, on="manager_id", how="left")
    trX["mgr_trail"] = trX.mgr_trail.fillna(0)
    teX["mgr_trail"] = teX.mgr_trail.fillna(0)
    b = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05,
                                      random_state=7).fit(trX[FEAT], trX.platoon_next)
    wm = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05,
                                       random_state=7).fit(trX[FEAT + ["mgr_trail"]],
                                                           trX.platoon_next)
    yb = teX.platoon_next.values
    rows.append({"year": ty,
                 "MAE_base": np.abs(b.predict(teX[FEAT]) - yb).mean(),
                 "MAE_mgr": np.abs(wm.predict(teX[FEAT + ["mgr_trail"]]) - yb).mean()})
r = pd.DataFrame(rows)
log(f"- OOS: trailing-manager platoon residual add -> MAE "
    f"{r.MAE_base.mean():.4f} -> {r.MAE_mgr.mean():.4f} "
    f"(Δ {r.MAE_mgr.mean()-r.MAE_base.mean():+.4f})")

log("\n## Verdict")
log("Platoon usage stable + new-info if reliability high & PA-corr ~0. "
    "Manager ships only if split-half persists AND OOS MAE improves.")

with open(f"{EXP}/research/E13_platoon.md", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\nreport written")
