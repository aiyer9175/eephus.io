# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Expansion E15 — Incremental value audit of new candidate features.

Tests four candidate blocks against the current incumbent champion
(parent Modules 02-21), each individually (champion + block) and cumulatively,
OOS on PA target 2023-2025. Ships a block only if it improves the champion.

  DEF      defensive quality — Savant OAA + FRV (year t), has_oaa flag
           (the framework's Defensive Floor+; Module 5 only tested position
           COUNT, never defensive QUALITY)
  OPT      out-of-options / options-remaining, reconstructed from the
           transaction log (distinct OPT seasons -> options burned). A player
           out of options can't be freely demoted -> sticks -> more PA.
  SPEED    Savant sprint_speed (year t) — late-game/sub value -> games
  POSLIFE  discrete primary position (lets the GBM learn position x age
           lifecycle beyond the position-games already in the champion)

Split: train target<=2022, test 2023-25. Champion = full M20/21 stack.

Output: research/E15_value_audit.md
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

lines = ["# Expansion E15 — Incremental Value Audit (new features)", ""]


def log(s=""):
    lines.append(s)
    print(s)


# ---------- champion assembly (parent M02-21) ----------
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
il = (ros[ros.status.isin(["D7", "D10", "D15", "D60"])]
      [["mlbam_id", "target_year"]].drop_duplicates().assign(on_il_at_od=1))
inc = inc.merge(il, on=["mlbam_id", "target_year"], how="left")
inc.loc[k, "on_il_at_od"] = inc.loc[k, "on_il_at_od"].fillna(0)
inc.loc[k, SEVF] = inc.loc[k, SEVF].fillna(0)
CHAMP_F = CHAMP + TXALL + ODF + PANELF + ["on_il_at_od"] + SEVF

# ---------- candidate blocks ----------
# DEF + SPEED (Savant; year t -> attach on feature year = season)
oaa = pd.read_parquet(f"{EXP}/data/raw/savant_oaa.parquet")
inc = inc.merge(oaa, on=["mlbam_id", "season"], how="left")
inc["has_oaa"] = inc.oaa.notna().astype(int)        # 0 = no defensive innings (DH/bench)
DEF = ["oaa", "frv", "has_oaa"]
spd = pd.read_parquet(f"{EXP}/data/raw/sprint_speed.parquet")
inc = inc.merge(spd, on=["mlbam_id", "season"], how="left")
SPEED = ["sprint_speed"]

# OPT (reconstruct options burned from transaction log)
tx = pd.read_parquet(f"{PT}/data/raw/transactions.parquet")
tx = tx[tx.mlbam_id.notna()].astype({"mlbam_id": int})
tx["date"] = pd.to_datetime(tx.date); tx["yr"] = tx.date.dt.year
optyrs = (tx[tx.type_code == "OPT"].groupby(["mlbam_id", "yr"]).size()
          .reset_index()[["mlbam_id", "yr"]])
rows = []
for mid, g in optyrs.groupby("mlbam_id"):
    ys = sorted(g.yr)
    for ty in range(2004, 2027):
        used = sum(1 for y in ys if y < ty)        # option years burned before t+1
        rows.append((mid, ty, used))
optdf = pd.DataFrame(rows, columns=["mlbam_id", "target_year", "opt_used"])
inc = inc.merge(optdf, on=["mlbam_id", "target_year"], how="left")
inc["opt_used"] = inc.opt_used.fillna(0)
inc["options_remaining"] = (3 - inc.opt_used).clip(lower=0)
inc["out_of_options"] = ((inc.opt_used >= 3) & (inc.on_40man_od == 1)).astype(int)
OPT = ["opt_used", "options_remaining", "out_of_options"]

# POSLIFE (discrete primary position code)
posmap = {p: i for i, p in enumerate(
    ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH", "P", "PH"])}
inc["pos_code"] = inc.primary_pos.map(posmap).fillna(-1)
POSLIFE = ["pos_code"]

train = inc[inc.target_year <= 2022]
test = inc[inc.target_year.isin([2023, 2024, 2025])].copy()


def run(F, t=test, tr=train):
    m = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05,
                                      random_state=7).fit(tr[F], tr.pa_next)
    p = np.clip(m.predict(t[F]), 0, None)
    y = t.pa_next.values
    err = p - y
    ss = ((y - y.mean()) ** 2).sum()
    return {"R2": round(1 - (err ** 2).sum() / ss, 4),
            "MAE": round(float(np.abs(err).mean()), 1),
            "RMSE": round(float(np.sqrt((err ** 2).mean())), 1),
            "rho": round(float(spearmanr(p, y).statistic), 4)}


log(f"- DEF coverage: {test.has_oaa.mean():.0%} have OAA; SPEED coverage: "
    f"{test.sprint_speed.notna().mean():.0%}; out-of-options rate: "
    f"{test.out_of_options.mean():.1%}")

log("\n## Individual blocks vs champion (test 2023-25)")
base = run(CHAMP_F)
log(f"{'champion':30s} {base}")
blocks = {"+DEF (OAA/FRV)": DEF, "+OPT (out-of-options)": OPT,
          "+SPEED (sprint)": SPEED, "+POSLIFE (position)": POSLIFE}
results = {"champion": base}
for name, blk in blocks.items():
    r = run(CHAMP_F + blk)
    results[name] = r
    d = {kk: round(r[kk] - base[kk], 4) for kk in ["R2", "MAE", "RMSE", "rho"]}
    log(f"{name:30s} {r}   Δ {d}")

# cumulative: add winners (R2 improves) in order
log("\n## Cumulative (adding blocks that individually helped R2)")
keep, cur = [], list(CHAMP_F)
for name, blk in blocks.items():
    if results[name]["R2"] > base["R2"]:
        keep += blk
        r = run(CHAMP_F + keep)
        log(f"champion + {' '.join(k for k in keep):.0s}{name:24s} -> {r}")
log(f"\n- blocks kept (individually R2-positive): "
    f"{[n for n in blocks if results[n]['R2'] > base['R2']]}")

with open(f"{EXP}/research/E15_value_audit.md", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\nreport written")
