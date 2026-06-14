# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Module 5 — Defensive Flexibility+ (ladder rung D, run as an ablation).

The flexibility block (n_positions, premium_pos, dh_share, per-position
games/starts) was included in rung A from the start, so rung D is tested by
REMOVING it: B-minus-flex vs B. The delta is the block's incremental value.

Output: reports/05_def_flexibility.md
"""
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

import ptm_lib as L

OUT = "/Users/willcahoon/playing_time_model"
FLEX = ["n_positions", "premium_pos", "dh_share", "g_c_adj", "g_ss_adj",
        "g_cf_adj", "gs_dh_adj", "g_field_total_adj"]

lines = ["# Module 5 — Defensive Flexibility+ (Rung D ablation)", ""]


def log(s=""):
    lines.append(s)
    print(s)


pairs = L.build_pairs()
train, test = L.split(pairs)

rows = []
models = {}
for name, F in [("B minus flexibility", [f for f in L.FEATS_B if f not in FLEX]),
                ("B (with flexibility)", L.FEATS_B)]:
    m = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05,
                                      random_state=7)
    m.fit(train[F], train.pa_next)
    rows.append(L.evaluate(name, m.predict(test[F]), test))
    models[name] = (m, F)

log("## Pooled holdout (targets 2023-2025)")
log(pd.DataFrame(rows).to_string(index=False))

log("\n## Segments most likely to need flexibility")
m, F = models["B (with flexibility)"]
m0, F0 = models["B minus flexibility"]
segs = {"multi-pos (n_positions>=2)": test.n_positions >= 2,
        "single-pos": test.n_positions <= 1,
        "premium (C/SS/CF)": test.premium_pos == 1,
        "DH-heavy (dh_share>.3)": test.dh_share > 0.3,
        "age<=25": test.age <= 25}
for nm, mask in segs.items():
    tt = test[mask]
    with_ = L.evaluate("with", m.predict(tt[F]), tt)
    wout = L.evaluate("without", m0.predict(tt[F0]), tt)
    log(f"- {nm} (n={len(tt)}): MAE {wout['MAE']} -> {with_['MAE']}  "
        f"R2 {wout['R2']} -> {with_['R2']}")

with open(f"{OUT}/reports/05_def_flexibility.md", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\nreport written")
