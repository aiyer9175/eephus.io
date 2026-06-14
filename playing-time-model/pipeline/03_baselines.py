# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Module 3 — Validation ladder, rungs A and B.

Universe: MLB incumbents (any MLB PA in year t). Target: PA in year t+1
(0 if the player records no MLB PA — demotion/retirement/release all count
as 0; injuries are NOT excluded yet, per framework this model is role-based
and the medical model comes later).

Rungs:
  A0  persistence        pa_{t+1} = pa_t                  (floor)
  A   historical usage   GBM on PA/G/GS history + age + position structure
  B   + talent           A + current+trailing performance (wOBA/OBP/ISO/K/BB)

Era handling: counting features are scaled to a 162-game-equivalent using the
league-season PA total (fixes 2020 and the in-progress 2026 feature year).
Target years 2020 and 2026 are excluded.

Split: forward chaining. Train = target years 2001-2022 (excl 2020),
test = target years 2023, 2024, 2025.

Output: reports/03_baselines.md
"""
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor

SPINE = "/Users/willcahoon/playing_time_model/data/processed/usage_spine.parquet"
OUT = "/Users/willcahoon/playing_time_model"

lines = ["# Module 3 — Validation Ladder: Rungs A0 / A / B", ""]


def log(s=""):
    lines.append(s)
    print(s)


sp = pd.read_parquet(SPINE)

# 162-game-equivalent scaling per season
season_pa = sp.groupby("season").pa.sum()
full = season_pa[(season_pa.index >= 2000) & (season_pa.index <= 2019)].median()
scale = (full / season_pa).rename("scale")
sp = sp.merge(scale, left_on="season", right_index=True)

COUNT = ["pa", "games", "gs_total", "g_field_total", "g_c", "g_ss", "g_cf",
         "gs_dh"]
for c in COUNT:
    sp[f"{c}_adj"] = sp[c] * sp.scale

key = ["mlbam_id", "season"]
feat_now = [f"{c}_adj" for c in COUNT] + ["n_positions", "premium_pos",
                                          "dh_share", "age"]
talent_now = ["woba", "obp", "iso", "k_pct", "bb_pct"]

base = sp[key + feat_now + talent_now + ["pa"]].copy()

# lags
for lag, suf in [(1, "_l1"), (2, "_l2")]:
    lagged = sp[key + ["pa_adj", "gs_total_adj", "woba"]].copy()
    lagged["season"] = lagged.season + lag
    lagged = lagged.rename(columns={c: c + suf for c in
                                    ["pa_adj", "gs_total_adj", "woba"]})
    base = base.merge(lagged, on=key, how="left")

# marcel-style weighted trailing wOBA (5/4/3 on t, t-1, t-2)
w = (5 * base.woba.fillna(0) * base.pa_adj
     + 4 * base.woba_l1.fillna(0) * base.pa_adj_l1.fillna(0)
     + 3 * base.woba_l2.fillna(0) * base.pa_adj_l2.fillna(0))
d = (5 * base.pa_adj + 4 * base.pa_adj_l1.fillna(0)
     + 3 * base.pa_adj_l2.fillna(0))
base["woba_marcel"] = (w / d.replace(0, np.nan)).fillna(base.woba)

# target: next-season PA, 0 if absent
nxt = sp[key + ["pa"]].rename(columns={"pa": "pa_next"})
nxt["season"] = nxt.season - 1
base = base.merge(nxt, on=key, how="left")
base["pa_next"] = base.pa_next.fillna(0)

# feature years 2019/2020 dropped (COVID target/feature), 2025+ dropped
# (2026 target season in progress)
pairs = base[~base.season.isin([2019, 2020, 2025, 2026])].copy()
pairs = pairs.dropna(subset=["age"])
log(f"- prediction pairs: {len(pairs)} (feature years "
    f"{pairs.season.min()}-{pairs.season.max()}, targets exclude 2020/2026)")

FEATS_A = ["pa_adj", "pa_adj_l1", "pa_adj_l2", "games_adj", "gs_total_adj",
           "gs_total_adj_l1", "g_field_total_adj", "g_c_adj", "g_ss_adj",
           "g_cf_adj", "gs_dh_adj", "n_positions", "premium_pos", "dh_share",
           "age"]
FEATS_B = FEATS_A + ["woba", "woba_marcel", "woba_l1", "obp", "iso",
                     "k_pct", "bb_pct"]

train = pairs[pairs.season + 1 <= 2022]
test = pairs[(pairs.season + 1).isin([2023, 2024, 2025])]
log(f"- train pairs: {len(train)}, test pairs: {len(test)} "
    f"(targets 2023-2025)\n")


def evaluate(name, preds, t=test):
    y = t.pa_next.values
    err = preds - y
    r2 = 1 - (err ** 2).sum() / ((y - y.mean()) ** 2).sum()
    res = {"model": name, "R2": round(r2, 4),
           "RMSE": round(float(np.sqrt((err ** 2).mean())), 1),
           "MAE": round(float(np.abs(err).mean()), 1),
           "Spearman": round(float(spearmanr(preds, y).statistic), 4)}
    return res


rows = []
# A0 persistence (use raw pa_t, not adjusted — predicting a full season)
rows.append(evaluate("A0 persistence (pa_t)", test.pa_adj.values))

mA = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05,
                                   random_state=7)
mA.fit(train[FEATS_A], train.pa_next)
rows.append(evaluate("A  usage history GBM", mA.predict(test[FEATS_A])))

mB = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05,
                                   random_state=7)
mB.fit(train[FEATS_B], train.pa_next)
predB = mB.predict(test[FEATS_B])
rows.append(evaluate("B  + talent GBM", predB))

res = pd.DataFrame(rows)
log("## Pooled holdout (targets 2023-2025)")
log(res.to_string(index=False))

log("\n## By target year (Model B)")
for yr in [2023, 2024, 2025]:
    tt = test[test.season + 1 == yr]
    r = evaluate(f"B @ {yr}", mB.predict(tt[FEATS_B]), tt)
    log(str(r))

log("\n## By segment (Model B, pooled)")
segs = {"age<=25": test.age <= 25, "age 26-31": test.age.between(26, 31),
        "age>=32": test.age >= 32, "pa_t<200": test.pa_adj < 200,
        "pa_t>=400": test.pa_adj >= 400}
for nm, mask in segs.items():
    tt = test[mask]
    r = evaluate(f"B {nm} (n={len(tt)})", mB.predict(tt[FEATS_B]), tt)
    log(str(r))

with open(f"{OUT}/reports/03_baselines.md", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\nreport written")
