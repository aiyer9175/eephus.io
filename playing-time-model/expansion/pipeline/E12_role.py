# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Expansion E12 — Role decomposition: full-time role + bench share.

Beyond total PA, the framework wants the ROLE: is the player a regular, a
bench/utility piece, a platoon bat? This module builds the two role targets
that carry information NOT already in projected PA, from the usage spine
(starts gs_total, games). Platoon share is added in E13 once E03 lands.

Incumbent universe (parent ptm_lib pairs), targets for season t+1:
  full_time_next   1 if gs_total_{t+1} >= 100 (~everyday starter), else 0
                   (0 also if no MLB next year) -> classifier
  bench_share_{t+1}= (games - gs_total)/games among players w/ games>=20 next yr
                   -> regression (high = sub/pinch role, low = pure starter)

For each: is it PROJECTABLE OOS, and does it beat the naive
"same-role-as-last-year" baseline? Split train target<=2022, test 2023-25.

Output: data/processed/role_targets.parquet, research/E12_role.md
"""
import sys

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import (HistGradientBoostingClassifier,
                              HistGradientBoostingRegressor)
from sklearn.metrics import brier_score_loss, roc_auc_score

PT = "/Users/willcahoon/playing_time_model"
EXP = f"{PT}/expansion"
sys.path.insert(0, f"{PT}/pipeline")
import ptm_lib as L  # noqa: E402

lines = ["# Expansion E12 — Role: full-time + bench share", ""]


def log(s=""):
    lines.append(s)
    print(s)


sp = pd.read_parquet(f"{PT}/data/processed/usage_spine.parquet")
role = sp[["mlbam_id", "season", "pa", "games", "gs_total"]].copy()
role["full_time"] = (role.gs_total >= 100).astype(int)
role["bench_share"] = np.where(role.games >= 20,
                               (role.games - role.gs_total) / role.games, np.nan)
role.to_parquet(f"{EXP}/data/processed/role_targets.parquet", index=False)

pairs, CHAMP = L.champion_pairs()
# next-year role
nx = role[["mlbam_id", "season", "full_time", "bench_share", "gs_total",
           "games"]].copy()
nx["season"] = nx.season - 1
nx = nx.rename(columns={"full_time": "full_time_next",
                        "bench_share": "bench_share_next",
                        "gs_total": "gs_next", "games": "games_next"})
pairs = pairs.merge(nx, on=["mlbam_id", "season"], how="left")
pairs["full_time_next"] = pairs.full_time_next.fillna(0)        # no MLB -> not FT
# this-year role for the naive baseline
pairs = pairs.merge(role[["mlbam_id", "season", "full_time", "bench_share"]],
                    on=["mlbam_id", "season"], how="left")

train = pairs[pairs.season + 1 <= 2022]
test = pairs[(pairs.season + 1).isin([2023, 2024, 2025])].copy()

# ---------- 1. full-time role probability ----------
log("## Full-time role probability  (P(>=100 starts next year))")
log(f"- base rate: train {train.full_time_next.mean():.3f}, "
    f"test {test.full_time_next.mean():.3f}")
clf = HistGradientBoostingClassifier(max_iter=400, learning_rate=0.05,
                                     random_state=7).fit(train[CHAMP],
                                                         train.full_time_next)
p = clf.predict_proba(test[CHAMP])[:, 1]
# naive: was full-time this year
naive = test.full_time.fillna(0).values
log(f"- model:  AUC {roc_auc_score(test.full_time_next, p):.4f}  "
    f"Brier {brier_score_loss(test.full_time_next, p):.4f}")
log(f"- naive (was FT this yr): AUC "
    f"{roc_auc_score(test.full_time_next, naive):.4f}  "
    f"Brier {brier_score_loss(test.full_time_next, naive):.4f}")

# ---------- 2. bench share (new info beyond PA?) ----------
log("\n## Bench share  ((games-starts)/games, players w/ >=20 games next yr)")
b_tr = train.dropna(subset=["bench_share_next"])
b_te = test.dropna(subset=["bench_share_next"]).copy()
# reliability: year-over-year of bench_share among those with both years
rel = pairs.dropna(subset=["bench_share", "bench_share_next"])
log(f"- year-over-year reliability (this yr vs next): r = "
    f"{rel.bench_share.corr(rel.bench_share_next):.3f} (n={len(rel)})")


def reg_eval(name, pred, t):
    y = t.bench_share_next.values
    err = pred - y
    ss = ((y - y.mean()) ** 2).sum()
    return (f"- {name}: R2 {1-(err**2).sum()/ss:.3f}  MAE {np.abs(err).mean():.3f}"
            f"  rho {spearmanr(pred, y).statistic:.3f}")


reg = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05,
                                    random_state=7).fit(b_tr[CHAMP],
                                                        b_tr.bench_share_next)
log(reg_eval("model (champion feats)", reg.predict(b_te[CHAMP]), b_te))
log(reg_eval("naive (this-yr bench share)", b_te.bench_share.values, b_te))

# does bench share add beyond PROJECTED pa? regress role on pa-rank check:
log("\n## Is bench share just inverse PA? (new-info check)")
pa_proj = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05,
                                        random_state=7).fit(train[CHAMP],
                                                            train.pa_next)
b_te["pa_hat"] = pa_proj.predict(b_te[CHAMP])
log(f"- corr(projected PA, actual bench_share_next) = "
    f"{spearmanr(b_te.pa_hat, b_te.bench_share_next).statistic:.3f} "
    "(high |corr| => largely redundant with PA)")

with open(f"{EXP}/research/E12_role.md", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\nreport written")
