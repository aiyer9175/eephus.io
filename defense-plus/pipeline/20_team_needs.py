# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
Defense+ — team-need / up-spectrum moves (the Betts/Rafaela-at-SS question).

Up-spectrum moves (an established player covering a MORE premium position than his own)
are driven by org holes we can't observe. Can we predict anything? Hypothesis: we can't
predict the org NEED, but athleticism + versatility GATE who is even eligible to be asked
(you move Betts/Rafaela to SS, never a slow 1B). Test whether sprint speed + versatility
characterize/forecast up-movers -> a 'capacity/optionality' flag, not a need predictor.
"""
import os, warnings
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score
from sklearn.metrics import roc_auc_score
warnings.filterwarnings("ignore"); pd.set_option("display.width", 200)

HOME = os.path.expanduser("~")
RANK = {"C": 8, "SS": 7, "CF": 6, "2B": 5, "3B": 4, "RF": 3, "LF": 2, "1B": 1, "DH": 0}
POS = list(RANK)
u = pd.read_parquet(os.path.join(HOME, "playing_time_model/data/processed/usage_spine.parquet"))
for p in POS:
    if f"g_{p.lower()}" not in u.columns: u[f"g_{p.lower()}"] = 0
gcol = {p: f"g_{p.lower()}" for p in POS}

# career primary (most career starts) + spectrum rank
for p in POS:
    if f"gs_{p.lower()}" not in u.columns: u[f"gs_{p.lower()}"] = 0
gs = [f"gs_{p.lower()}" for p in POS]
car = u.groupby("mlbam_id")[gs].sum()
car["career_gs"] = car[gs].max(axis=1)
car["primary"] = car[gs].idxmax(axis=1).str.replace("gs_", "").str.upper()
car["prim_rank"] = car["primary"].map(RANK)
# versatility = # positions with >=10 career games
gcar = u.groupby("mlbam_id")[[gcol[p] for p in POS]].sum()
car["versatility"] = (gcar >= 10).sum(axis=1)
prim = car[["primary", "career_gs", "prim_rank", "versatility"]]

# per season: most-premium position played >=10 games
seas = u.copy()
seas["top_rank"] = seas.apply(lambda r: max([RANK[p] for p in POS if r.get(gcol[p], 0) >= 10] or [0]), axis=1)
seas["top_pos"] = seas.apply(lambda r: max([(RANK[p], p) for p in POS if r.get(gcol[p], 0) >= 10] or [(0, "DH")])[1], axis=1)
seas = seas.merge(prim, on="mlbam_id", how="left")
# up-move = played a position MORE premium than career primary, while ESTABLISHED (career>=200 GS)
seas["up_move"] = ((seas["top_rank"] > seas["prim_rank"]) & (seas["career_gs"] >= 200)).astype(int)

# sprint speed (2023-25 mean) + age
sp = []
for y in [2023, 2024, 2025]:
    d = pd.read_csv(os.path.join(HOME, f"contact_plus/data/external/savant_sprint/sprint_speed_{y}.csv"))
    idc = [c for c in d.columns if c.lower() in ("player_id", "id")][0]
    spc = [c for c in d.columns if "sprint" in c.lower() and "speed" in c.lower()][0]
    sp.append(d[[idc, spc]].rename(columns={idc: "mlbam_id", spc: "sprint"}))
SP = pd.concat(sp).groupby("mlbam_id")["sprint"].mean().reset_index()
dm = pd.read_parquet(os.path.join(HOME, "projection_engine/data/deep_mlb.parquet"))[["batter", "season", "age"]]
seas = seas.merge(dm.rename(columns={"batter": "mlbam_id"}), on=["mlbam_id", "season"], how="left")
seas = seas.merge(SP, on="mlbam_id", how="left")

# player-level: did they EVER make an up-move (established)? characterize
pl = seas.groupby("mlbam_id").agg(ever_up=("up_move", "max"), versatility=("versatility", "first"),
                                  primary=("primary", "first"), career_gs=("career_gs", "first"),
                                  sprint=("sprint", "first")).reset_index()
pl = pl[(pl.career_gs >= 200) & pl.primary.isin(POS)]
print(f"established players (career>=200 GS): {len(pl)} | ever made up-spectrum move: {pl.ever_up.mean()*100:.0f}%\n")
print("=== up-movers vs not (characteristics) ===")
print(f"{'group':12}{'n':>6}{'versatility':>12}{'sprint(ft/s)':>14}")
for lab, g in [("up-movers", pl[pl.ever_up == 1]), ("non-movers", pl[pl.ever_up == 0])]:
    print(f"  {lab:12}{len(g):>6}{g.versatility.mean():>12.1f}{g.sprint.mean():>14.1f}")

# specific: emergency-SS (non-SS primary who played >=10 G SS while established)
emerg = seas[(seas.up_move == 1) & (seas.gs_ss.notna()) & (seas["g_ss"] >= 10) & (seas.primary != "SS")]
es_ids = emerg.mlbam_id.unique()
es = pl[pl.mlbam_id.isin(es_ids)].merge(SP, on="mlbam_id", how="left", suffixes=("", "_y"))
spr_all = pl.sprint.dropna()
print(f"\n=== emergency-SS (non-SS primary, >=10 G at SS while established): {len(es_ids)} players ===")
if len(es):
    print(f"  mean sprint {es.sprint.mean():.1f} ft/s (league regular mean {spr_all.mean():.1f}) | "
          f"mean versatility {es.versatility.mean():.1f} (vs {pl.versatility.mean():.1f})")
    pct = (spr_all < es.sprint.mean()).mean() * 100
    print(f"  -> emergency-SS sprint is ~{pct:.0f}th pct of regulars (athleticism GATES eligibility)")

# predictability: P(ever up-move) ~ sprint + versatility + prim_rank (CV AUC)
d = pl.dropna(subset=["sprint", "versatility"]).copy()
d["prim_rank"] = d.primary.map(RANK)
X = d[["sprint", "versatility", "prim_rank"]].values; y = d["ever_up"].values
auc = cross_val_score(LogisticRegression(max_iter=1000), X, y, cv=5, scoring="roc_auc").mean()
print(f"\n=== predictability of up-moves: 5-fold CV AUC = {auc:.3f} ===")
m = LogisticRegression(max_iter=1000).fit(X, y)
print(f"  coefs: sprint {m.coef_[0][0]:+.2f}, versatility {m.coef_[0][1]:+.2f}, prim_rank {m.coef_[0][2]:+.2f}")
print("  -> we can flag CAPACITY (who's eligible) but not the org NEED (timing).")
pl.to_csv(os.path.join(HOME, "defense_plus/reports/20_team_needs.csv"), index=False)
print("\nwrote reports/20_team_needs.csv")
