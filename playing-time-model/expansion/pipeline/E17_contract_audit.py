# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Expansion E17 — Contract value audit (the E15 exception test).

Contract is the one candidate plausibly NOT mediated by usage history (a fresh
FA deal is a forward commitment not yet reflected in past playing time). Tests
whether contract features add to the incumbent champion for PA projection.

Contract data (E06) exists only for target years 2023-2025, so the usual
train<=2022 split is impossible (feature absent in training -> unlearnable,
the FV-for-incumbents trap). Instead: LEAVE-ONE-YEAR-OUT CV across 2023/24/25
(train two, test the held-out one, rotate, pool) so contract is present in
both train and test. Reported pooled and on contract-covered players only.

Output: research/E17_contract_audit.md
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

lines = ["# Expansion E17 — Contract Value Audit (E15 exception test)", ""]


def log(s=""):
    lines.append(s)
    print(s)


# ---------- champion assembly (parent M02-21), as in E15 ----------
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
CHAMP_F = CHAMP + TXALL + ODF + PANELF + ["on_il_at_od"] + SEVF

# ---------- contract block ----------
con = pd.read_parquet(f"{EXP}/data/processed/contract_features.parquet")
CON = ["log_cur_salary", "log_total_guar", "years_remaining_guar",
       "walk_year", "is_arb", "guaranteed_multiyr"]
inc = inc.merge(con, on=["mlbam_id", "target_year"], how="left")
inc["has_contract"] = inc[CON].notna().any(axis=1).astype(int)
# absent contract record in a covered year ~ pre-arb/min: fill 0 (+ has_contract flag)
covyears = sorted(con.target_year.unique())
m = inc.target_year.isin(covyears)
inc.loc[m, CON] = inc.loc[m, CON].fillna(0)
CON = CON + ["has_contract"]

uni = inc[inc.target_year.isin(covyears)].copy()
log(f"- contract-covered target years: {covyears}; incumbent rows {len(uni)}; "
    f"with a contract record {uni.has_contract.mean():.0%}")


def loyo(F):
    """leave-one-year-out CV over covered years; return pooled preds."""
    pred = pd.Series(np.nan, index=uni.index)
    for ty in covyears:
        tr = uni[uni.target_year != ty]
        te_idx = uni.index[uni.target_year == ty]
        mdl = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05,
                                            random_state=7).fit(tr[F], tr.pa_next)
        pred.loc[te_idx] = np.clip(mdl.predict(uni.loc[te_idx, F]), 0, None)
    return pred


def ev(name, pred, mask=None):
    s = uni if mask is None else uni[mask]
    p = pred if mask is None else pred[mask]
    y = s.pa_next.values
    err = p.values - y
    ss = ((y - y.mean()) ** 2).sum()
    return {"model": name, "n": len(y),
            "R2": round(1 - (err ** 2).sum() / ss, 4),
            "MAE": round(float(np.abs(err).mean()), 1),
            "RMSE": round(float(np.sqrt((err ** 2).mean())), 1),
            "rho": round(float(spearmanr(p, y).statistic), 4)}


p_base = loyo(CHAMP_F)
p_con = loyo(CHAMP_F + CON)
log("\n## Leave-one-year-out CV (2023/24/25), all covered incumbents")
log(pd.DataFrame([ev("champion", p_base), ev("champion + contract", p_con)]).to_string(index=False))

# fair test on players WITH a real contract record (multiyear / FA types)
mc = uni.has_contract == 1
log(f"\n## Players WITH a contract record (n={int(mc.sum())})")
log(pd.DataFrame([ev("champion", p_base, mc), ev("champion + contract", p_con, mc)]).to_string(index=False))

# the hypothesis segment: recently-signed FA / big guarantees (forward commitment)
mfa = uni.guaranteed_multiyr == 1
log(f"\n## Multiyear-guaranteed players (the 'plays through slumps' segment, n={int(mfa.sum())})")
log(pd.DataFrame([ev("champion", p_base, mfa), ev("champion + contract", p_con, mfa)]).to_string(index=False))

log("\n## Verdict")
log("Contract ships only if it improves OOS here — this is the one feature not")
log("mediated by usage history, so it's the real test of the E15 ceiling.")

with open(f"{EXP}/research/E17_contract_audit.md", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\nreport written")
