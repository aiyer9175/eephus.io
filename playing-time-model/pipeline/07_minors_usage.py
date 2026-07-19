# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Module 7 — Minors usage / shuttle features (ladder rung F').

A player splitting the season between MLB and AAA is the optionable-fringe
signature: it proxies transaction cost (has options, gets shuttled) and
replacement role without needing historical 40-man reconstruction. Dense
coverage 2008+ from deep_minors, timestamp-valid (year-t info only).

Features (year t):
  pa_aaa_adj      AAA PA, era-scaled        (sport 11)
  pa_milb_adj     all minors PA, era-scaled
  woba_aaa        AAA wOBA
  mlb_share       MLB PA / (MLB + minors PA)
  shuttle         1 if MLB PA>0 and minors PA>=50

Output: reports/07_minors_usage.md
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

import ptm_lib as L

OUT = "/Users/willcahoon/playing_time_model"
DEEP_MIN = "/Users/willcahoon/projection_engine/data/deep_minors.parquet"

lines = ["# Module 7 — Minors Usage / Shuttle (Rung F')", ""]


def log(s=""):
    lines.append(s)
    print(s)


mn = pd.read_parquet(DEEP_MIN)
aaa = (mn[mn.sport == 11].groupby(["batter", "season"])
       .agg(pa_aaa=("pa", "sum"),
            woba_aaa=("woba", lambda s: np.average(
                s, weights=mn.loc[s.index, "pa"]) if s.notna().any() else np.nan))
       .reset_index())
allm = (mn.groupby(["batter", "season"]).pa.sum()
        .rename("pa_milb").reset_index())
mfeat = allm.merge(aaa, on=["batter", "season"], how="left")
mfeat = mfeat.rename(columns={"batter": "mlbam_id"})

pairs = L.build_pairs()
pairs = pairs.merge(mfeat, on=["mlbam_id", "season"], how="left")
# deep_minors starts 2008; before that minors data simply doesn't exist
pre = pairs.season < 2008
pairs.loc[~pre, ["pa_milb", "pa_aaa"]] = (
    pairs.loc[~pre, ["pa_milb", "pa_aaa"]].fillna(0))
pairs["pa_aaa_adj"] = pairs.pa_aaa * pairs.scale
pairs["pa_milb_adj"] = pairs.pa_milb * pairs.scale
pairs["mlb_share"] = pairs.pa / (pairs.pa + pairs.pa_milb).replace(0, np.nan)
pairs["shuttle"] = ((pairs.pa > 0) & (pairs.pa_milb >= 50)).astype(float)
pairs.loc[pre, "shuttle"] = np.nan

NEW = ["pa_aaa_adj", "pa_milb_adj", "woba_aaa", "mlb_share", "shuttle"]
cov = pairs.loc[~pre, "pa_milb"].ge(1).mean()
log(f"- pairs with any minors PA in feature year (2008+): {cov:.1%}")

train, test = L.split(pairs)
rows, models = [], {}
for name, F in [("B (benchmark)", L.FEATS_B), ("F' + minors usage", L.FEATS_B + NEW)]:
    m = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05,
                                      random_state=7)
    m.fit(train[F], train.pa_next)
    rows.append(L.evaluate(name, m.predict(test[F]), test))
    models[name] = (m, F)

log("\n## Pooled holdout (targets 2023-2025)")
log(pd.DataFrame(rows).to_string(index=False))

mF, FF = models["F' + minors usage"]
mB, FB = models["B (benchmark)"]
log("\n## Segments")
segs = {"pa_t<200": test.pa_adj < 200, "age<=25": test.age <= 25,
        "shuttle=1": test.shuttle == 1, "pa_t>=400": test.pa_adj >= 400}
for nm, mask in segs.items():
    tt = test[mask]
    b = L.evaluate("b", mB.predict(tt[FB]), tt)
    f_ = L.evaluate("f", mF.predict(tt[FF]), tt)
    log(f"- {nm} (n={len(tt)}): MAE {b['MAE']} -> {f_['MAE']}, "
        f"R2 {b['R2']} -> {f_['R2']}, rho {b['Spearman']} -> {f_['Spearman']}")

with open(f"{OUT}/reports/07_minors_usage.md", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\nreport written")
