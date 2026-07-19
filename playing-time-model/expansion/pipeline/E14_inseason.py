# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Expansion E14 — In-season rest-of-season (ROS) PA updating.

At a midseason cutoff (May 31 / Jun 30), project each player's REMAINING PA
(cutoff -> season end). This is the high-value in-season product: once the
season starts, the preseason number goes stale (trades, injuries, demotions,
breakouts have happened). The question: does an in-season model that uses
what ACTUALLY happened beat the stale preseason projection?

Universe: players with any PA-to-date at the cutoff (they're active).
Target: ROS_PA = full_season_PA (spine) - PA_to_date.

Baselines vs model:
  B1 preseason-prorated   preseason proj x (1 - league fraction-elapsed)
  B2 naive pace           PA_to_date x (PA-remaining-fraction / elapsed-frac)
  M  in-season GBM        PA_to_date, G_to_date, AB_to_date, pace, preseason
                          proj, age, cutoff -> ROS_PA
Split: train seasons <= 2022, test 2023-25, both cutoffs pooled (cutoff is a
feature). Preseason proj = our full-population projection (E20).

Output: research/E14_inseason.md
"""
import sys

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor

PT = "/Users/willcahoon/playing_time_model"
EXP = f"{PT}/expansion"
sys.path.insert(0, f"{PT}/pipeline")

lines = ["# Expansion E14 — In-Season Rest-of-Season PA Updating", ""]


def log(s=""):
    lines.append(s)
    print(s)


asof = pd.read_parquet(f"{EXP}/data/raw/asof_hitting.parquet")
sp = pd.read_parquet(f"{PT}/data/processed/usage_spine.parquet")[
    ["mlbam_id", "season", "pa", "age"]].rename(columns={"pa": "pa_full"})
df = asof.merge(sp, on=["mlbam_id", "season"], how="left")
df = df[df.pa_td.fillna(0) > 0].dropna(subset=["pa_full"]).copy()
df["ros_pa"] = (df.pa_full - df.pa_td).clip(lower=0)

# league fraction-elapsed per (season, cutoff): total PA-to-date / total full PA
frac = (df.groupby(["season", "cutoff"])
          .apply(lambda d: d.pa_td.sum() / d.pa_full.sum(), include_groups=False)
          .rename("f_elapsed").reset_index())
df = df.merge(frac, on=["season", "cutoff"], how="left")
df["pace_ros"] = df.pa_td * (1 - df.f_elapsed) / df.f_elapsed   # B2

# preseason projection from E20 full-population
proj = pd.read_parquet(f"{EXP}/data/processed/full_population_proj.parquet")
proj = proj.rename(columns={"target_year": "season", "pred": "preseason_proj"})
df = df.merge(proj[["mlbam_id", "season", "preseason_proj"]],
              on=["mlbam_id", "season"], how="left")
# players without a preseason proj (mid-season debuts etc.): fall back to pace
df["preseason_proj"] = df.preseason_proj.fillna(df.pa_td / df.f_elapsed)
df["pre_ros"] = (df.preseason_proj * (1 - df.f_elapsed)).clip(lower=0)  # B1

df["cut_num"] = (df.cutoff == "06-30").astype(int)
FEAT = ["pa_td", "ab_td", "g_td", "f_elapsed", "pace_ros", "preseason_proj",
        "pre_ros", "age", "cut_num"]

train = df[df.season <= 2022]
test = df[df.season.isin([2023, 2024, 2025])].copy()
log(f"- universe: {len(df)} player-cutoff rows; train {len(train)}, "
    f"test {len(test)} (cutoffs May31+Jun30 pooled)")
log(f"- league fraction-elapsed: May31 ~{frac[frac.cutoff=='05-31'].f_elapsed.mean():.2f}, "
    f"Jun30 ~{frac[frac.cutoff=='06-30'].f_elapsed.mean():.2f}")

m = HistGradientBoostingRegressor(max_iter=500, learning_rate=0.05,
                                  random_state=7).fit(train[FEAT], train.ros_pa)
test["m_ros"] = np.clip(m.predict(test[FEAT]), 0, None)


def ev(name, pred):
    y = test.ros_pa.values
    err = pred - y
    ss = ((y - y.mean()) ** 2).sum()
    return {"model": name, "R2": round(1 - (err ** 2).sum() / ss, 4),
            "MAE": round(float(np.abs(err).mean()), 1),
            "RMSE": round(float(np.sqrt((err ** 2).mean())), 1),
            "rho": round(float(spearmanr(pred, y).statistic), 4)}


log("\n## Rest-of-season PA: in-season model vs stale-preseason baselines")
log(pd.DataFrame([
    ev("B1 preseason-prorated", test.pre_ros.values),
    ev("B2 naive pace", test.pace_ros.values),
    ev("M  in-season model", test.m_ros.values),
]).to_string(index=False))

log("\n## By cutoff (in-season model)")
for cut, lab in [("05-31", "May 31 (~1/3 in)"), ("06-30", "Jun 30 (~1/2 in)")]:
    s = test[test.cutoff == cut]
    err = s.m_ros.values - s.ros_pa.values
    b1 = s.pre_ros.values - s.ros_pa.values
    log(f"- {lab} (n={len(s)}): model MAE {np.abs(err).mean():.1f} vs "
        f"preseason-prorated MAE {np.abs(b1).mean():.1f}  "
        f"(rho {spearmanr(s.m_ros, s.ros_pa).statistic:.3f})")

log("\n## Read")
log("- B1 = the stale preseason projection prorated for time left (what you'd")
log("  use without updating). If M beats B1, in-season updating adds value.")
log("- gains should grow from May->Jun as more in-season info accrues.")

with open(f"{EXP}/research/E14_inseason.md", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\nreport written")
