# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Module 21 — Injury severity / duration (the residual MAE channel).

Module 20 closed most of the Steamer MAE gap with IL *history*, but Steamer
still edged us on the on-IL-at-Opening-Day segment: it knows how LONG the
spring injury keeps a player out, we only knew he was hurt. This adds that
duration signal, leakage-clean.

Two complementary, timestamp-valid severity features:

  od_il_level    ordinal Opening-Day IL designation from OUR roster pull —
                 0 none / 1 D10 / 2 D15 / 3 D60. This is MLB's own duration
                 estimate (60-day IL = season-threatening). Module 20
                 collapsed it to binary; here we keep the ladder. Fully clean.

  od_region_exp_days   for OD-injured players, the WALK-FORWARD median
                 days_missed for their injury's body region. Region is known
                 at Opening Day (the injury is announced); the median is
                 computed ONLY from injury events in seasons < target year
                 (impact_windows_v2, raw). The player's OWN days_missed is
                 never used. Region attributed via the earliest season-Y
                 event (the OD placement cause). 0 for healthy players.

Why rebuild instead of using the handoff availability_median_days.csv: that
table is fit on the full window (incl. test seasons) — same leak class as
the rate-table columns dropped in Module 20.

Baseline = Module 20 champion (BASE + clean IL history). Reports the
on_il_at_od segment explicitly vs Steamer.

Output: data/processed/injury_severity.parquet, reports/21_injury_severity.md
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

import ptm_lib as L

OUT = "/Users/willcahoon/playing_time_model"
INJ = "/Users/willcahoon/injury_model/data/processed"

lines = ["# Module 21 — Injury Severity / Duration", ""]


def log(s=""):
    lines.append(s)
    print(s)


# ---------- raw injury events (region + days_missed, no within-season date)
iw = pd.read_parquet(f"{INJ}/impact_windows_v2.parquet")
iw = iw.rename(columns={"player_id": "mlbam_id"})
iw = iw[iw.body_region.notna() & (iw.non_injury_flag == 0)
        & (iw.protocol_suspect_flag == 0)]
# earliest event id within (player, season) ~ the OD-placement cause
iw["evnum"] = iw.injury_event_id.str.extract(r"-(\d+)$").astype(int)
first = iw.sort_values("evnum").groupby(["mlbam_id", "season"]).first().reset_index()

# spine-id sanity
sp_ids = set(pd.read_parquet(f"{OUT}/data/processed/usage_spine.parquet").mlbam_id)
log(f"- impact_windows player ids ∩ spine: "
    f"{len(set(iw.mlbam_id) & sp_ids)} (confirms MLBAM keying)")

# ---------- walk-forward region median days table
reg_rows = []
for y in range(2010, 2027):
    past = iw[(iw.season < y) & iw.days_missed.notna()]
    if len(past) < 200:
        continue
    med = past.groupby("body_region").days_missed.median()
    glob = past.days_missed.median()
    for region, d in med.items():
        reg_rows.append({"target_year": y, "body_region": region,
                         "region_med_days": d})
    reg_rows.append({"target_year": y, "body_region": "__global__",
                     "region_med_days": glob})
regtab = pd.DataFrame(reg_rows)
log(f"- walk-forward region tables built for target years "
    f"{regtab.target_year.min()}-{regtab.target_year.max()}")

# OD injury region for each (player, target_year): the season-Y first event
od_region = first[["mlbam_id", "season", "body_region"]].copy()
od_region["target_year"] = od_region.season
od_region = od_region.drop(columns="season")

# ---------- OD IL designation (ordinal) from our roster pull
ros = pd.read_parquet(f"{OUT}/data/raw/od_rosters.parquet")
ros = ros[ros.mlbam_id.notna()].astype({"mlbam_id": int})
LEVEL = {"D7": 1, "D10": 1, "D15": 2, "D60": 3}
ros["il_level"] = ros.status.map(LEVEL)
od_il = (ros.dropna(subset=["il_level"])
            .groupby(["mlbam_id", "target_year"]).il_level.max()
            .reset_index().rename(columns={"il_level": "od_il_level"}))
log(f"- OD IL designations: {od_il.od_il_level.value_counts().to_dict()} "
    "(1=D10,2=D15,3=D60)")

# ---------- assemble severity features
sev = od_il.merge(od_region, on=["mlbam_id", "target_year"], how="left")
sev = sev.merge(regtab, on=["target_year", "body_region"], how="left")
glob = regtab[regtab.body_region == "__global__"][["target_year",
                                                   "region_med_days"]]
glob = glob.rename(columns={"region_med_days": "glob_days"})
sev = sev.merge(glob, on="target_year", how="left")
# expected days: region median, else global; scaled by D-level escalation
sev["region_med_days"] = sev.region_med_days.fillna(sev.glob_days)
# D60 carries far longer than its region median suggests -> let level lift it
lvl_mult = {1: 1.0, 2: 1.4, 3: 3.0}
sev["od_region_exp_days"] = sev.region_med_days * sev.od_il_level.map(lvl_mult)
sev = sev[["mlbam_id", "target_year", "od_il_level", "od_region_exp_days"]]
sev.to_parquet(f"{OUT}/data/processed/injury_severity.parquet", index=False)
log(f"- severity features: {sev.shape}; region attributed to "
    f"{od_region.merge(od_il, on=['mlbam_id','target_year']).shape[0]}/"
    f"{len(od_il)} OD-injured")

# ---------- evaluation: rebuild Module 20 champion, add severity
panel = pd.read_parquet(f"{INJ}/risk_panel_yoy.parquet") \
          .rename(columns={"batter": "mlbam_id"}).sort_values(["mlbam_id", "season"])
panel["career_il_stints"] = panel.groupby("mlbam_id").stints.cumsum()
panel["career_il_days"] = panel.groupby("mlbam_id").days.cumsum()
inj = panel[["mlbam_id", "season", "stints", "days", "career_il_stints",
             "career_il_days"]].rename(columns={"stints": "il_stints_t",
                                                "days": "il_days_t"})
inj["target_year"] = inj.season + 1
inj = inj.drop(columns="season")

pairs, CHAMP = L.champion_pairs()
pairs["target_year"] = pairs.season + 1
txf = pd.read_parquet(f"{OUT}/data/processed/tx_features.parquet")
pairs = pairs.merge(txf, on=["mlbam_id", "target_year"], how="left")
TXALL = [c for c in txf.columns if c not in ("mlbam_id", "target_year")]
known = pairs.target_year >= 2004
pairs.loc[known, TXALL] = pairs.loc[known, TXALL].fillna(0)
od = pd.read_parquet(f"{OUT}/data/processed/od_features.parquet")
pairs = pairs.merge(od, on=["mlbam_id", "target_year"], how="left")
ODF = ["on_40man_od", "on_active_od", "od_pos_depth", "od_team_pos_players"]
cov = known & (pairs.target_year != 2020)
pairs.loc[cov, ["on_40man_od", "on_active_od"]] = (
    pairs.loc[cov, ["on_40man_od", "on_active_od"]].fillna(0))
pairs = pairs.merge(inj, on=["mlbam_id", "target_year"], how="left")
ros_il = (ros[ros.status.isin(["D7", "D10", "D15", "D60"])]
          [["mlbam_id", "target_year"]].drop_duplicates().assign(on_il_at_od=1))
pairs = pairs.merge(ros_il, on=["mlbam_id", "target_year"], how="left")
covI = pairs.target_year >= 2016
PANELF = ["il_stints_t", "il_days_t", "career_il_stints", "career_il_days"]
pairs.loc[covI, PANELF] = pairs.loc[covI, PANELF].fillna(0)
pairs.loc[known, "on_il_at_od"] = pairs.loc[known, "on_il_at_od"].fillna(0)
INJF = PANELF + ["on_il_at_od"]

pairs = pairs.merge(sev, on=["mlbam_id", "target_year"], how="left")
pairs.loc[known, "od_il_level"] = pairs.loc[known, "od_il_level"].fillna(0)
pairs.loc[known, "od_region_exp_days"] = (
    pairs.loc[known, "od_region_exp_days"].fillna(0))
SEVF = ["od_il_level", "od_region_exp_days"]

pub = pd.read_parquet(f"{OUT}/data/raw/public_projections.parquet")
st = (pub[pub.system == "steamer"][["mlbam_id", "season", "pa_proj"]]
      .rename(columns={"season": "target_year", "pa_proj": "pa_steamer"}))
pairs = pairs.merge(st, on=["mlbam_id", "target_year"], how="left")

CH20 = CHAMP + TXALL + ODF + INJF
train, test = L.split(pairs)


def run(F):
    m = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05,
                                      random_state=7)
    m.fit(train[F], train.pa_next)
    return np.clip(m.predict(test[F]), 0, None)


test = test.copy()
p20 = run(CH20)
p21 = run(CH20 + SEVF)
common = test.pa_steamer.notna()
tt = test[common]
log(f"\n## Steamer-free preseason frame, common universe (n={common.sum()})")
res = [L.evaluate("Steamer (reference)", tt.pa_steamer.values, tt),
       L.evaluate("Module 20 champion (IL history)", p20[common.values], tt),
       L.evaluate("21 + severity/duration  <-- new", p21[common.values], tt),
       L.evaluate("blend (21 + Steamer)",
                  0.5 * p21[common.values] + 0.5 * tt.pa_steamer.values, tt)]
log(pd.DataFrame(res).to_string(index=False))

log("\n## The target segment — on IL at Opening Day")
tt = tt.assign(p20=p20[common.values], p21=p21[common.values])
for nm, mask in {"on_il_at_od=1": tt.on_il_at_od == 1,
                 "  of which D60": tt.od_il_level == 3,
                 "  of which D10/D15": tt.od_il_level.isin([1, 2]),
                 "age>=32": tt.age >= 32,
                 "il_days_t>=30": tt.il_days_t >= 30}.items():
    s = tt[mask]
    if len(s) < 15:
        log(f"- {nm}: n={len(s)}")
        continue
    a = L.evaluate("s", s.pa_steamer.values, s)
    b = L.evaluate("b", s.p20.values, s)
    c = L.evaluate("c", s.p21.values, s)
    log(f"- {nm} (n={len(s)}): MAE steamer {a['MAE']} | m20 {b['MAE']} | "
        f"m21 {c['MAE']}   rho {a['Spearman']} | {b['Spearman']} | "
        f"{c['Spearman']}")

with open(f"{OUT}/reports/21_injury_severity.md", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\nreport written")
