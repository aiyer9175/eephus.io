# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Expansion E22 — Where we lose to Steamer + can an in-house estimator replace it.

Part A (diagnosis): incumbent champion vs Steamer, signed error (bias) and MAE
by realized-PA band — is the gap a specific band? bias or noise?

Part B (own-Steamer): Module 17 showed the blend's value is ESTIMATOR
DIVERSITY, not Steamer per se. Build methodologically-different in-house PA
estimators and test whether blending two of OURS recovers the Steamer-blend
gain — removing the external dependency:
  champ   GBM squared-error (current; good ranking, noisier magnitude)
  pois    GBM Poisson loss   (count-calibrated magnitude — the 'our Steamer')
  enet    ElasticNet on standardized feats (smooth linear, decorrelated method)
Blends: champ+pois, champ+enet, champ+pois+enet  vs  champ+Steamer.

Incumbent universe, train<=2022, test 2023-25.
Output: research/E22_own_steamer.md
"""
import sys

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import ElasticNet
from sklearn.preprocessing import StandardScaler

PT = "/Users/willcahoon/playing_time_model"
EXP = f"{PT}/expansion"
sys.path.insert(0, f"{PT}/pipeline")
import ptm_lib as L  # noqa: E402

lines = ["# Expansion E22 — Where we lose to Steamer + own-Steamer blend", ""]


def log(s=""):
    lines.append(s)
    print(s)


# champion assembly (parent M02-21)
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

pub = pd.read_parquet(f"{PT}/data/raw/public_projections.parquet")
st = (pub[pub.system == "steamer"][["mlbam_id", "season", "pa_proj"]]
      .rename(columns={"season": "target_year", "pa_proj": "pa_steamer"}))
inc = inc.merge(st, on=["mlbam_id", "target_year"], how="left")

train = inc[inc.target_year <= 2022].copy()
test = inc[inc.target_year.isin([2023, 2024, 2025])].copy()
Xtr, Xte = train[F].fillna(0), test[F].fillna(0)

# estimators
champ = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05,
                                      random_state=7).fit(Xtr, train.pa_next)
pois = HistGradientBoostingRegressor(loss="poisson", max_iter=400,
                                     learning_rate=0.05, random_state=7).fit(Xtr, train.pa_next)
sc = StandardScaler().fit(Xtr)
enet = ElasticNet(alpha=1.0, l1_ratio=0.3, max_iter=5000).fit(sc.transform(Xtr), train.pa_next)
test["champ"] = np.clip(champ.predict(Xte), 0, None)
test["pois"] = np.clip(pois.predict(Xte), 0, None)
test["enet"] = np.clip(enet.predict(sc.transform(Xte)), 0, None)
test = test[test.pa_steamer.notna()].copy()
y = test.pa_next.values


def m(name, p):
    err = p - y; ss = ((y - y.mean()) ** 2).sum()
    return {"model": name, "R2": round(1 - (err ** 2).sum() / ss, 4),
            "MAE": round(float(np.abs(err).mean()), 1),
            "RMSE": round(float(np.sqrt((err ** 2).mean())), 1),
            "rho": round(float(spearmanr(p, y).statistic), 4)}


# ---- Part A: where we lose
log("## A. Where we lose — signed error (bias) & MAE by realized-PA band")
log(f"{'band':12s}{'n':>5s}{'ours bias':>11s}{'steam bias':>12s}"
    f"{'ours MAE':>10s}{'steam MAE':>11s}")
bands = [(0, 0), (1, 99), (100, 299), (300, 499), (500, 800)]
for lo, hi in bands:
    s = test[(test.pa_next >= lo) & (test.pa_next <= hi)]
    if not len(s):
        continue
    ob = (s.champ - s.pa_next).mean(); sb = (s.pa_steamer - s.pa_next).mean()
    om = (s.champ - s.pa_next).abs().mean(); sm = (s.pa_steamer - s.pa_next).abs().mean()
    log(f"{f'{lo}-{hi}':12s}{len(s):5d}{ob:+11.1f}{sb:+12.1f}{om:10.1f}{sm:11.1f}")
# error correlation (diversity check)
log(f"\n- error corr(ours, Steamer) = "
    f"{np.corrcoef(test.champ - y, test.pa_steamer - y)[0,1]:.3f} "
    f"| corr(ours, pois) = {np.corrcoef(test.champ - y, test.pois - y)[0,1]:.3f} "
    f"| corr(ours, enet) = {np.corrcoef(test.champ - y, test.enet - y)[0,1]:.3f}")

# ---- Part B: own-Steamer blends
log("\n## B. Can an in-house estimator replace Steamer in the blend?")
rows = [m("champ (current)", test.champ.values),
        m("pois (in-house)", test.pois.values),
        m("enet (in-house)", test.enet.values),
        m("Steamer", test.pa_steamer.values),
        m("blend champ+Steamer (external)", 0.5 * test.champ + 0.5 * test.pa_steamer),
        m("blend champ+pois (in-house)", 0.5 * test.champ + 0.5 * test.pois),
        m("blend champ+enet (in-house)", 0.5 * test.champ + 0.5 * test.enet),
        m("blend champ+pois+enet (in-house)",
          (test.champ + test.pois + test.enet) / 3)]
log(pd.DataFrame(rows).to_string(index=False))

with open(f"{EXP}/research/E22_own_steamer.md", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\nreport written")
