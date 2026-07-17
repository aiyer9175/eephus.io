# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Expansion E30 — In-season IL status in the rest-of-season (ROS) updater.

The owned, dated IL feed (transaction log: placements/activations/transfers
with 15/60-day type) reconstructs an on-IL timeline as of ANY date. The E14
ROS updater currently has NO injury status; a player on the 60-day IL at the
cutoff has near-zero rest-of-season PA, which pace/preseason can't see.

As-of-cutoff IL features (timestamp-valid: known at the in-season cutoff):
  currently_on_il    on the IL as of the cutoff date
  on_60day_il        the active stint is a 60-day IL (season-threatening)
  il_days_to_date    days on the IL this season through the cutoff
  n_il_stints_td     IL stints this season through the cutoff

Tests E14 baseline (champion ROS GBM) vs + IL features, vs naive pace, overall
and on the currently-injured segment. Cutoffs May 31 / Jun 30, seasons
2017-2025 (E04 data), test 2023-25.

Output: research/E30_inseason_injury.md
"""
import re

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor

PT = "/Users/willcahoon/playing_time_model"
EXP = f"{PT}/expansion"

lines = ["# Expansion E30 — In-Season IL Status in the ROS Updater", ""]


def log(s=""):
    lines.append(s)
    print(s)


# ---------- reconstruct IL-stint timeline from transactions ----------
tx = pd.read_parquet(f"{PT}/data/raw/transactions.parquet")
tx = tx[tx.mlbam_id.notna()].copy()
tx["mlbam_id"] = tx.mlbam_id.astype(int)
tx["date"] = pd.to_datetime(tx.date)
d = tx.description.fillna("")
tx["is_place"] = d.str.contains(r"placed.*(disabled|injured) list", case=False, regex=True)
tx["is_activ"] = d.str.contains(r"activated.*(disabled|injured) list", case=False, regex=True)
tx["is_to60"] = d.str.contains(r"transferred.*60", case=False, regex=True)
tx["il_type"] = d.str.extract(r"(\d+)-day")[0].astype("float")
ev = tx[tx.is_place | tx.is_activ | tx.is_to60][
    ["mlbam_id", "date", "is_place", "is_activ", "is_to60", "il_type"]].sort_values(["mlbam_id", "date"])

SEASON_END = "-10-15"
stints = []
for mid, g in ev.groupby("mlbam_id"):
    on = False; start = None; typ = 0
    for _, r in g.iterrows():
        if r.is_place:
            if not on:
                on, start, typ = True, r.date, (r.il_type or 10)
            else:
                typ = max(typ, r.il_type or typ)
        elif r.is_to60 and on:
            typ = 60
        elif r.is_activ and on:
            stints.append((mid, start, r.date, typ)); on = False
    if on:
        stints.append((mid, start, pd.Timestamp(f"{start.year}{SEASON_END}"), typ))
st = pd.DataFrame(stints, columns=["mlbam_id", "start", "end", "il_type"])
st["season"] = st.start.dt.year
log(f"- reconstructed {len(st)} IL stints (2002-2026); "
    f"60-day share {(st.il_type >= 60).mean():.0%}")


def il_feats(mid, season, cutoff):
    s = st[(st.mlbam_id == mid) & (st.season == season)]
    sstart = pd.Timestamp(f"{season}-03-15")
    cur = on60 = days = n = 0
    for _, r in s.iterrows():
        if r.start <= cutoff:
            n += 1
            ovl = (min(r.end, cutoff) - max(r.start, sstart)).days
            days += max(0, ovl)
            if r.start <= cutoff < r.end:
                cur = 1
                if r.il_type >= 60:
                    on60 = 1
    return cur, on60, days, n


# ---------- ROS frame (mirror E14) ----------
asof = pd.read_parquet(f"{EXP}/data/raw/asof_hitting.parquet")
sp = pd.read_parquet(f"{PT}/data/processed/usage_spine.parquet")[["mlbam_id", "season", "pa", "age"]].rename(columns={"pa": "pa_full"})
df = asof.merge(sp, on=["mlbam_id", "season"], how="left")
df = df[df.pa_td.fillna(0) > 0].dropna(subset=["pa_full"]).copy()
df["ros_pa"] = (df.pa_full - df.pa_td).clip(lower=0)
frac = (df.groupby(["season", "cutoff"]).apply(lambda d: d.pa_td.sum() / d.pa_full.sum(), include_groups=False)
          .rename("f_elapsed").reset_index())
df = df.merge(frac, on=["season", "cutoff"], how="left")
df["pace_ros"] = df.pa_td * (1 - df.f_elapsed) / df.f_elapsed
proj = pd.read_parquet(f"{EXP}/data/processed/full_population_proj.parquet").rename(columns={"target_year": "season", "pred": "preseason_proj"})
df = df.merge(proj[["mlbam_id", "season", "preseason_proj"]], on=["mlbam_id", "season"], how="left")
df["preseason_proj"] = df.preseason_proj.fillna(df.pa_td / df.f_elapsed)
df["pre_ros"] = (df.preseason_proj * (1 - df.f_elapsed)).clip(lower=0)
df["cut_num"] = (df.cutoff == "06-30").astype(int)
df["cutoff_date"] = pd.to_datetime(df.season.astype(str) + "-" + df.cutoff)

# attach IL features
feats = df.apply(lambda r: il_feats(r.mlbam_id, r.season, r.cutoff_date), axis=1, result_type="expand")
feats.columns = ["currently_on_il", "on_60day_il", "il_days_to_date", "n_il_stints_td"]
df = pd.concat([df, feats], axis=1)
log(f"- ROS rows {len(df)}; currently-on-IL at cutoff {df.currently_on_il.mean():.1%}, "
    f"on 60-day {df.on_60day_il.mean():.1%}")

BASE = ["pa_td", "ab_td", "g_td", "f_elapsed", "pace_ros", "preseason_proj", "pre_ros", "age", "cut_num"]
IL = ["currently_on_il", "on_60day_il", "il_days_to_date", "n_il_stints_td"]
train = df[df.season <= 2022]; test = df[df.season.isin([2023, 2024, 2025])].copy()


def fit(F):
    m = HistGradientBoostingRegressor(max_iter=500, learning_rate=0.05, random_state=7).fit(train[F], train.ros_pa)
    return np.clip(m.predict(test[F]), 0, None)


test["m_base"] = fit(BASE)
test["m_il"] = fit(BASE + IL)
y = test.ros_pa.values


def M(name, p):
    err = p - y; ss = ((y - y.mean()) ** 2).sum()
    return {"model": name, "R2": round(1 - (err ** 2).sum() / ss, 4),
            "MAE": round(float(np.abs(err).mean()), 1),
            "RMSE": round(float(np.sqrt((err ** 2).mean())), 1),
            "rho": round(float(spearmanr(p, y).statistic), 4)}


log("\n## Rest-of-season PA (test 2023-25)")
log(pd.DataFrame([M("naive pace", test.pace_ros.values),
                  M("E14 base GBM", test.m_base.values),
                  M("E14 + in-season IL", test.m_il.values)]).to_string(index=False))

log("\n## Currently-on-IL-at-cutoff segment (where it should bite)")
for seg, mask in [("currently on IL", test.currently_on_il == 1),
                  ("on 60-day IL", test.on_60day_il == 1),
                  ("healthy at cutoff", test.currently_on_il == 0)]:
    s = test[mask]
    if len(s) < 15:
        log(f"- {seg}: n={len(s)} too small"); continue
    b = np.abs(s.m_base - s.ros_pa).mean(); i = np.abs(s.m_il - s.ros_pa).mean()
    pc = np.abs(s.pace_ros - s.ros_pa).mean()
    log(f"- {seg} (n={len(s)}): MAE base {b:.1f} -> +IL {i:.1f} | pace {pc:.1f}")

with open(f"{EXP}/research/E30_inseason_injury.md", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\nreport written")
