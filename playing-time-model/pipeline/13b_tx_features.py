# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Module 13b — Transaction Cost / Offseason Context features.

From the league-wide transaction log (2002-2026). Two information frames:

  OCT frame (champion): events known by Oct 1 of feature year t
    - n_opt_t, n_recall_t      option churn during season t
    - opt_seasons_career       distinct seasons with >=1 option (options burned)
    - des_career, out_career, clw_career   DFA'd / outrighted / claimed counts
  PRESEASON frame (stack): adds offseason events Oct 1 (t) -> Mar 25 (t+1)
    - off_traded, off_signed_fa, off_selected_40man, off_des_out_clw,
      off_released

Type-code map (verified Module 13a): OPT=Optioned, CU=Recalled, DES=Designated
for Assignment, DFA=Declared Free Agency (NOT designated), SE=Selected (40-man
add), OUT=Outrighted, CLW=Waiver claim, SFA/SGN=signings, TR=Trade, REL=Released.

Transactions start 2002 -> all tx features set NaN for target years < 2004
(career aggregates too left-truncated to trust).

Evaluation:
  rung F-oct:  champion + OCT features          (vs champion)
  rung F-pre:  stack + OCT + offseason features (vs stack, vs Steamer)

Output: reports/13_tx_features.md, data/processed/tx_features.parquet
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

import ptm_lib as L

OUT = "/Users/willcahoon/playing_time_model"

lines = ["# Module 13b — Transaction / Offseason Features", ""]


def log(s=""):
    lines.append(s)
    print(s)


tx = pd.read_parquet(f"{OUT}/data/raw/transactions.parquet")
tx = tx[tx.mlbam_id.notna()].copy()
tx["mlbam_id"] = tx.mlbam_id.astype(int)
tx["date"] = pd.to_datetime(tx.date)
tx["year"] = tx.date.dt.year

rows = []
for ty in range(2004, 2027):                      # target year
    t = ty - 1                                    # feature year
    oct_cut = pd.Timestamp(f"{t}-10-01")
    mar_cut = pd.Timestamp(f"{ty}-03-25")
    season = tx[(tx.date >= f"{t}-03-15") & (tx.date < oct_cut)]
    career = tx[tx.date < oct_cut]
    off = tx[(tx.date >= oct_cut) & (tx.date <= mar_cut)]

    f = pd.DataFrame(index=pd.Index(
        career.mlbam_id.unique(), name="mlbam_id"))
    cnt = lambda d, codes: (d[d.type_code.isin(codes)]
                            .groupby("mlbam_id").size())
    f["n_opt_t"] = cnt(season, ["OPT"])
    f["n_recall_t"] = cnt(season, ["CU"])
    f["opt_seasons_career"] = (career[career.type_code == "OPT"]
                               .groupby("mlbam_id").year.nunique())
    f["des_career"] = cnt(career, ["DES"])
    f["out_career"] = cnt(career, ["OUT"])
    f["clw_career"] = cnt(career, ["CLW"])
    f["off_traded"] = cnt(off, ["TR"])
    f["off_signed_fa"] = cnt(off, ["SFA", "SGN"])
    f["off_selected_40man"] = cnt(off, ["SE"])
    f["off_des_out_clw"] = cnt(off, ["DES", "OUT", "CLW"])
    f["off_released"] = cnt(off, ["REL", "DFA"])
    f = f.fillna(0).reset_index()
    f["target_year"] = ty
    rows.append(f)

txf = pd.concat(rows, ignore_index=True)
txf.to_parquet(f"{OUT}/data/processed/tx_features.parquet", index=False)
log(f"- tx features: {txf.shape}, target years 2004-2026")

OCT_F = ["n_opt_t", "n_recall_t", "opt_seasons_career", "des_career",
         "out_career", "clw_career"]
OFF_F = ["off_traded", "off_signed_fa", "off_selected_40man",
         "off_des_out_clw", "off_released"]

pairs, CHAMP = L.champion_pairs()
pairs["target_year"] = pairs.season + 1
pairs = pairs.merge(txf, on=["mlbam_id", "target_year"], how="left")
known = pairs.target_year >= 2004
pairs.loc[known, OCT_F + OFF_F] = pairs.loc[known, OCT_F + OFF_F].fillna(0)
log(f"- pairs with tx data: {known.mean():.0%} "
    f"(players w/o any career transaction before Oct -> 0)")

# steamer prior for the preseason frame
pub = pd.read_parquet(f"{OUT}/data/raw/public_projections.parquet")
st = (pub[pub.system == "steamer"]
      [["mlbam_id", "season", "pa_proj", "woba_proj", "g_proj"]]
      .rename(columns={"season": "target_year", "pa_proj": "pa_steamer",
                       "woba_proj": "woba_steamer", "g_proj": "g_steamer"}))
pairs = pairs.merge(st, on=["mlbam_id", "target_year"], how="left")
STACK = CHAMP + ["pa_steamer", "woba_steamer", "g_steamer"]

train, test = L.split(pairs)


def fit_pred(F):
    m = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05,
                                      random_state=7)
    m.fit(train[F], train.pa_next)
    return np.clip(m.predict(test[F]), 0, None)


test = test.copy()
preds = {
    "champion": fit_pred(CHAMP),
    "F-oct  champ+tx": fit_pred(CHAMP + OCT_F),
    "stack": fit_pred(STACK),
    "F-pre  stack+tx+off": fit_pred(STACK + OCT_F + OFF_F),
}

log("\n## OCT frame (full test universe)")
res = [L.evaluate(k, v, test) for k, v in preds.items()
       if k in ("champion", "F-oct  champ+tx")]
log(pd.DataFrame(res).to_string(index=False))

common = test.pa_steamer.notna()
tt = test[common]
log(f"\n## PRESEASON frame (common universe n={common.sum()})")
res = [L.evaluate("Steamer preseason", tt.pa_steamer.values, tt)]
for k in ("stack", "F-pre  stack+tx+off"):
    res.append(L.evaluate(k, preds[k][common.values], tt))
blend = 0.5 * preds["F-pre  stack+tx+off"][common.values] + 0.5 * tt.pa_steamer.values
res.append(L.evaluate("blend (F-pre + Steamer)/2", blend, tt))
log(pd.DataFrame(res).to_string(index=False))

log("\n## Segments (MAE: steamer | stack | F-pre)")
tt = tt.assign(pa_stack=preds["stack"][common.values],
               pa_fpre=preds["F-pre  stack+tx+off"][common.values])
for nm, mask in {"age<=25": tt.age <= 25, "pa_t<200": tt.pa_adj < 200,
                 "shuttle=1": tt.shuttle == 1,
                 "optioned in t (n_opt>0)": tt.n_opt_t > 0,
                 "off_traded": tt.off_traded > 0,
                 "off_des_out_clw": tt.off_des_out_clw > 0}.items():
    s = tt[mask]
    if len(s) < 20:
        log(f"- {nm}: n={len(s)}")
        continue
    a = L.evaluate("s", s.pa_steamer.values, s)
    b = L.evaluate("k", s.pa_stack.values, s)
    c = L.evaluate("f", s.pa_fpre.values, s)
    log(f"- {nm} (n={len(s)}): MAE {a['MAE']} | {b['MAE']} | {c['MAE']}   "
        f"rho {a['Spearman']} | {b['Spearman']} | {c['Spearman']}")

with open(f"{OUT}/reports/13_tx_features.md", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\nreport written")
