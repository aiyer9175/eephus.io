# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Module 6 — Prospect Pedigree+ (ladder rung E).

Do teams give extra opportunity to highly regarded prospects, beyond what
usage history + talent already predict?

Leakage control: for a target year y, only snapshots dated <= March 31 of y
and no older than 14 months are used (Pipeline lists drop late January, i.e.
preseason of y — legitimately known at prediction time).

Coverage caveat: tracker snapshots start 2021, so pedigree features exist
only for target years 2022+ (train pairs 2001-2021 carry NaN; GBM handles
NaN natively). Test years 2023-2025 are fully covered.

Features: fv_latest, top100_rank, is_top100, is_top10, org_rank,
          had_pedigree (any snapshot at all).

Output: reports/06_pedigree.md, data/processed/pedigree_features.parquet
"""
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

import ptm_lib as L

OUT = "/Users/willcahoon/playing_time_model"
GRADES = f"{OUT}/data/processed/grades_long.parquet"

lines = ["# Module 6 — Prospect Pedigree+ (Rung E)", ""]


def log(s=""):
    lines.append(s)
    print(s)


g = pd.read_parquet(GRADES)
g = g[g.mlbam_id.notna()].copy()
g["mlbam_id"] = g.mlbam_id.astype(int)
g["snapshot_date"] = pd.to_datetime(g.snapshot_date)

rows = []
for y in range(2022, 2026):
    cutoff = pd.Timestamp(f"{y}-03-31")
    floor = cutoff - pd.DateOffset(months=14)
    win = g[(g.snapshot_date <= cutoff) & (g.snapshot_date >= floor)]
    win = win.sort_values("snapshot_date")
    top = win[win.scope == "top100"].groupby("mlbam_id").last()
    org = win[win.scope == "org"].groupby("mlbam_id").last()
    fv = win[win.fv.notna()].groupby("mlbam_id").fv.last()
    ids = set(win.mlbam_id)
    f = pd.DataFrame(index=sorted(ids))
    f["top100_rank"] = top["rank"]
    f["org_rank"] = org["rank"]
    f["fv_latest"] = fv
    f["is_top100"] = f.top100_rank.notna().astype(int)
    f["is_top10"] = (f.top100_rank <= 10).astype(int)
    f["had_pedigree"] = 1
    f["target_year"] = y
    rows.append(f.reset_index(names="mlbam_id"))

ped = pd.concat(rows, ignore_index=True)
ped["season"] = ped.target_year - 1  # join on feature year
ped.to_parquet(f"{OUT}/data/processed/pedigree_features.parquet", index=False)
log(f"- pedigree rows: {len(ped)} across target years "
    f"{ped.target_year.min()}-{ped.target_year.max()}")

pairs = L.build_pairs()
pairs = pairs.merge(ped.drop(columns=["target_year"]),
                    on=["mlbam_id", "season"], how="left")
pairs["had_pedigree"] = pairs.had_pedigree.fillna(0)
pairs.loc[pairs.season + 1 < 2022, "had_pedigree"] = float("nan")  # no data era

NEW = ["fv_latest", "top100_rank", "org_rank", "is_top100", "is_top10",
       "had_pedigree"]
recent_test_cov = pairs[(pairs.season + 1).isin(L.TEST_YEARS)]
log(f"- test pairs with any pedigree: "
    f"{(recent_test_cov.had_pedigree == 1).mean():.1%} "
    f"(incumbent universe — most MLB regulars are post-prospect)")

train, test = L.split(pairs)
rows = []
models = {}
for name, F in [("B (benchmark)", L.FEATS_B), ("E + pedigree", L.FEATS_B + NEW)]:
    m = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05,
                                      random_state=7)
    m.fit(train[F], train.pa_next)
    rows.append(L.evaluate(name, m.predict(test[F]), test))
    models[name] = (m, F)

log("\n## Pooled holdout (targets 2023-2025)")
log(pd.DataFrame(rows).to_string(index=False))

mE, FE = models["E + pedigree"]
mB, FB = models["B (benchmark)"]
log("\n## Where pedigree should matter")
segs = {"age<=25": test.age <= 25,
        "rookie-ish (pa_l1 NaN/0)": test.pa_adj_l1.fillna(0) < 50,
        "had pedigree": test.had_pedigree == 1,
        "top100 at cutoff": test.is_top100 == 1}
for nm, mask in segs.items():
    tt = test[mask]
    if len(tt) < 20:
        log(f"- {nm}: n={len(tt)} too small")
        continue
    b = L.evaluate("b", mB.predict(tt[FB]), tt)
    e = L.evaluate("e", mE.predict(tt[FE]), tt)
    log(f"- {nm} (n={len(tt)}): MAE {b['MAE']} -> {e['MAE']}, "
        f"R2 {b['R2']} -> {e['R2']}, rho {b['Spearman']} -> {e['Spearman']}")

with open(f"{OUT}/reports/06_pedigree.md", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\nreport written")
