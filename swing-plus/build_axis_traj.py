# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
build_axis_traj.py — rolling trajectories for B2B+, Contact+, and DCV+ with
driver decomposition, analogous to trajectories.parquet for Swing+.

Rolling windows: 80 BIPs (B2B+/DCV+), 100 swings (Contact+).
Driver decomposition uses the calibration linear model exactly:
  contribution_i = shrink_weight * coef_i * rolling_mean(residual_i)
  sum of contributions = (axis_score - 100)

Output: data/processed/axis_traj.parquet
Columns:
  batter, season, game_date
  b2b, b_ev, b_xw, b_ba, b_su   — B2B+ rolling score + 4 EV/quality/barrel/sq-up drivers
  con, c_zone, c_chase           — Contact+ rolling score + in-zone / out-of-zone split
  dcv, d_pa, d_pb, d_hw, d_pr   — DCV+ rolling score + pull-air/pull-barrel/HR-window/pull drivers
"""

import warnings; warnings.filterwarnings("ignore")
import glob, joblib
import numpy as np, pandas as pd
from pathlib import Path
from sklearn.linear_model import LinearRegression

MODELS = Path("/Users/willcahoon/bat_to_ball_plus/models")
OUT    = Path("data/processed/axis_traj.parquet")
PROC   = Path("data/processed")

NUM = ["plate_x","plate_z","release_speed","pfx_x","pfx_z","release_spin_rate","spin_axis",
       "balls","strikes","release_pos_x","release_pos_z","release_extension","arm_angle","effective_speed"]
CAT = ["pitch_type","stand","p_throws"]
COMMON_PT   = {"FF","SI","SL","CH","FC","ST","CU","FS","KC"}
SWING_DESCS = {"foul","foul_bunt","foul_tip","bunt_foul_tip","hit_into_play",
               "missed_bunt","swinging_strike","swinging_strike_blocked"}
WHIFF_DESCS = {"swinging_strike","swinging_strike_blocked","missed_bunt"}
PULL_CUT, HRW_LO, HRW_HI = 15.0, 20.0, 35.0
WIN_B2B, WIN_CON, WIN_DCV = 80, 100, 80
MIN_B2B, MIN_CON, MIN_DCV = 40, 50, 40

# ── Load opportunity / difficulty models ──────────────────────────────────────
print("Loading models...")
opp = {t: joblib.load(MODELS / f"opportunity_{t}_v2.lgb.joblib")
       for t in ["ev","xwobacon","barrel","squared_up"]}
dc = joblib.load(MODELS / "difficulty_contact.lgb.joblib")
print("  OK")

# ── Load raw Statcast data ────────────────────────────────────────────────────
print("Loading raw Statcast...")
BIP_COLS = (["batter","stand","p_throws","pitch_type","description","type","bb_type",
             "launch_speed","estimated_woba_using_speedangle","launch_speed_angle",
             "bat_speed","game_date","hc_x","hc_y","launch_angle"] + NUM)
SW_COLS  = (["batter","stand","p_throws","pitch_type","description","bat_speed","game_date"]
            + NUM)
ALL_COLS = list(dict.fromkeys(BIP_COLS + SW_COLS))

raw_frames = []
for f in sorted(glob.glob("data/raw/statcast_*.parquet")):
    yr = Path(f).stem.replace("statcast_", "")[:4]   # e.g. "2026"
    d  = pd.read_parquet(f, columns=[c for c in ALL_COLS if c])
    d["season"] = int(yr)
    raw_frames.append(d)
raw = pd.concat(raw_frames, ignore_index=True)
raw["game_date"] = pd.to_datetime(raw["game_date"])
print(f"  {len(raw):,} pitches across {raw['season'].nunique()} seasons")


def prep(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in ["release_spin_rate","spin_axis","release_extension","arm_angle",
              "release_pos_x","release_pos_z","effective_speed"]:
        df[c] = df[c].fillna(df[c].median())
    df["pitch_type"] = (df["pitch_type"].astype(str)
                        .where(df["pitch_type"].astype(str).isin(COMMON_PT), "other")
                        .astype("category"))
    df["stand"]    = df["stand"].astype("category")
    df["p_throws"] = df["p_throws"].astype("category")
    return df


# ── B2B+: score each BIP ──────────────────────────────────────────────────────
print("Scoring BIPs for B2B+...")
bip = raw[(raw["description"] == "hit_into_play") &
          raw["launch_speed"].notna() &
          raw["estimated_woba_using_speedangle"].notna() &
          raw["bat_speed"].notna()].copy()
bip = prep(bip)
X   = bip[NUM + CAT]
bip["o_ev"] = opp["ev"].predict(X)
bip["o_xw"] = opp["xwobacon"].predict(X)
bip["o_ba"] = opp["barrel"].predict(X)
bip["o_su"] = opp["squared_up"].predict(X)
bip["act_barrel"] = (bip["launch_speed_angle"] == 6).astype(float)
bip["act_su"] = (bip["launch_speed"] /
                 (1.23 * bip["bat_speed"] + 0.2116 * bip["release_speed"]) >= 0.80).astype(float)
bip["r_ev"] = bip["launch_speed"] - bip["o_ev"]
bip["r_xw"] = bip["estimated_woba_using_speedangle"] - bip["o_xw"]
bip["r_ba"] = bip["act_barrel"] - bip["o_ba"]
bip["r_su"] = bip["act_su"]    - bip["o_su"]
print(f"  {len(bip):,} BIPs")

# Calibrate on 2024-2025 season means
fw_b2b = pd.read_parquet(PROC / "bat_to_ball_plus.parquet")[["batter","season","bat_to_ball_plus"]]
agg_b2b = (bip.groupby(["batter","season"])
           .agg(n_bip=("r_ev","size"), r_ev=("r_ev","mean"), r_xw=("r_xw","mean"),
                r_ba=("r_ba","mean"), r_su=("r_su","mean")).reset_index())
cal_b2b = (agg_b2b[agg_b2b["season"].isin([2024,2025])]
           .merge(fw_b2b[fw_b2b["season"].isin([2024,2025])], on=["batter","season"])
           .query("n_bip >= 80").dropna(subset=["bat_to_ball_plus"]))
F_B2B = ["r_ev","r_xw","r_ba","r_su"]
lr_b2b = LinearRegression().fit(cal_b2b[F_B2B], cal_b2b["bat_to_ball_plus"])
print(f"  B2B+ calibration R²={lr_b2b.score(cal_b2b[F_B2B], cal_b2b['bat_to_ball_plus']):.3f}")

# ── Contact+: score each swing ────────────────────────────────────────────────
print("Scoring swings for Contact+...")
sw = raw[raw["description"].isin(SWING_DESCS) & raw["bat_speed"].notna()].copy()
sw = prep(sw)
sw["exp_con"] = dc.predict(sw[NUM + CAT])
sw["obs_con"] = (~sw["description"].isin(WHIFF_DESCS)).astype(float)
sw["r_con"]   = sw["obs_con"] - sw["exp_con"]
sw["in_zone"] = sw["plate_x"].abs().le(0.83) & sw["plate_z"].between(1.5, 3.5)
print(f"  {len(sw):,} swings")

fw_con = pd.read_parquet(PROC / "bat_to_ball_plus.parquet")[["batter","season","contact_plus"]]
agg_con = (sw.groupby(["batter","season"])
           .agg(n_sw=("r_con","size"), r_con=("r_con","mean")).reset_index())
cal_con = (agg_con[agg_con["season"].isin([2024,2025])]
           .merge(fw_con[fw_con["season"].isin([2024,2025])], on=["batter","season"])
           .query("n_sw >= 150").dropna(subset=["contact_plus"]))
lr_con = LinearRegression().fit(cal_con[["r_con"]], cal_con["contact_plus"])
print(f"  Contact+ calibration R²={lr_con.score(cal_con[['r_con']], cal_con['contact_plus']):.3f}")

# ── DCV+: score each BIP ──────────────────────────────────────────────────────
print("Scoring BIPs for DCV+...")
dcv = raw[(raw["type"] == "X") & raw["bb_type"].notna() &
          raw["hc_x"].notna() & raw["hc_y"].notna()].copy()
ang = np.degrees(np.arctan((dcv["hc_x"] - 125.42) / (198.27 - dcv["hc_y"])))
dcv["spray_deg"]     = np.where(dcv["stand"] == "L", ang, -ang)
dcv["is_pull"]       = dcv["spray_deg"] > PULL_CUT
air                  = dcv["bb_type"].isin(["line_drive","fly_ball"])
dcv["pulled_air"]    = (dcv["is_pull"] & air).astype(float)
dcv["pulled_barrel"] = (dcv["is_pull"] & (dcv["launch_speed_angle"] == 6)).astype(float)
dcv["hr_window"]     = dcv["launch_angle"].between(HRW_LO, HRW_HI).astype(float)
dcv["pull_rate"]     = dcv["is_pull"].astype(float)
print(f"  {len(dcv):,} BIPs")

fw_dcv = pd.read_parquet(PROC / "dcv_plus.parquet")[["batter","season","dcv_plus"]]
fw_dcv["season"] = fw_dcv["season"].astype(int)
agg_dcv = (dcv.groupby(["batter","season"])
           .agg(n_bip=("is_pull","size"), pulled_air=("pulled_air","mean"),
                pulled_barrel=("pulled_barrel","mean"), hr_window=("hr_window","mean"),
                pull_rate=("pull_rate","mean")).reset_index())
cal_dcv = (agg_dcv[agg_dcv["season"].isin([2023,2024,2025])]
           .merge(fw_dcv[fw_dcv["season"].isin([2023,2024,2025])], on=["batter","season"])
           .query("n_bip >= 50").dropna(subset=["dcv_plus"]))
F_DCV = ["pulled_air","pulled_barrel","hr_window","pull_rate"]
lr_dcv = LinearRegression().fit(cal_dcv[F_DCV], cal_dcv["dcv_plus"])
print(f"  DCV+ calibration R²={lr_dcv.score(cal_dcv[F_DCV], cal_dcv['dcv_plus']):.3f}")

# ── Rolling trajectory builder ────────────────────────────────────────────────
print("\nBuilding rolling trajectories...")

def _roll(df, batter, season, feat_cols, lr, win, min_pts, extra_fn=None):
    g = df[(df["batter"] == batter) & (df["season"] == season)].sort_values("game_date")
    if len(g) < min_pts:
        return []
    k = win
    pts, by_date = [], {}
    for i in range(min_pts, len(g) + 1):
        w_g = g.iloc[max(0, i - win):i]
        n   = len(w_g)
        means = {f: float(w_g[f].mean()) for f in feat_cols}
        raw   = float(lr.intercept_) + sum(float(lr.coef_[j]) * means[f]
                                           for j, f in enumerate(feat_cols))
        wt    = n / (n + k)
        score = 100.0 + wt * (raw - 100.0)
        contribs = {f: round(wt * float(lr.coef_[j]) * means[f], 3)
                    for j, f in enumerate(feat_cols)}
        rec = {"date": w_g["game_date"].iloc[-1].strftime("%Y-%m-%d"),
               "v": round(score, 1), **contribs}
        if extra_fn:
            rec.update(extra_fn(w_g, wt, lr))
        by_date[rec["date"]] = rec
    return list(by_date.values())


def con_extra(w_g, wt, lr):
    coef = float(lr.coef_[0])
    n_z  = int(w_g["in_zone"].sum());  n_c = int((~w_g["in_zone"]).sum())
    n    = len(w_g)
    r_z  = float(w_g.loc[w_g["in_zone"],  "r_con"].mean()) if n_z else 0.0
    r_c  = float(w_g.loc[~w_g["in_zone"], "r_con"].mean()) if n_c else 0.0
    return {"c_zone":  round(wt * coef * r_z * n_z / n, 3),
            "c_chase": round(wt * coef * r_c * n_c / n, 3)}


batters_seasons = sorted(set(
    tuple(r) for r in bip[["batter","season"]].drop_duplicates().values.tolist()
) | set(
    tuple(r) for r in sw[["batter","season"]].drop_duplicates().values.tolist()
) | set(
    tuple(r) for r in dcv[["batter","season"]].drop_duplicates().values.tolist()
))
print(f"  {len(batters_seasons):,} batter-season combos")

all_rows = []
for idx, (bat, sea) in enumerate(batters_seasons):
    if idx % 500 == 0:
        print(f"  {idx}/{len(batters_seasons)}...")

    b2b_pts = _roll(bip, bat, sea, F_B2B, lr_b2b, WIN_B2B, MIN_B2B)
    con_pts  = _roll(sw,  bat, sea, ["r_con"], lr_con, WIN_CON, MIN_CON, con_extra)
    dcv_pts  = _roll(dcv, bat, sea, F_DCV,  lr_dcv, WIN_DCV, MIN_DCV)

    b2b_map = {p["date"]: p for p in b2b_pts}
    con_map  = {p["date"]: p for p in con_pts}
    dcv_map  = {p["date"]: p for p in dcv_pts}
    dates    = sorted(set(b2b_map) | set(con_map) | set(dcv_map))

    for d in dates:
        row: dict = {"batter": bat, "season": sea, "game_date": d}
        if d in b2b_map:
            p = b2b_map[d]
            row.update({"b2b": p["v"], "b_ev": p.get("r_ev"), "b_xw": p.get("r_xw"),
                        "b_ba": p.get("r_ba"), "b_su": p.get("r_su")})
        if d in con_map:
            p = con_map[d]
            row.update({"con": p["v"], "c_zone": p.get("c_zone"), "c_chase": p.get("c_chase")})
        if d in dcv_map:
            p = dcv_map[d]
            row.update({"dcv": p["v"], "d_pa": p.get("pulled_air"),
                        "d_pb": p.get("pulled_barrel"), "d_hw": p.get("hr_window"),
                        "d_pr": p.get("pull_rate")})
        all_rows.append(row)

out = pd.DataFrame(all_rows)
out.to_parquet(OUT, index=False)
print(f"\nSaved {OUT.name}: {len(out):,} rows, {out['batter'].nunique()} players")

# Quick sanity: Rafaela B2B+ and Contact+ rolling
r = out[out["batter"] == 678882].dropna(subset=["b2b"])
if len(r):
    print(f"Rafaela B2B+ rolling: n={len(r)}, latest={r.iloc[-1]['b2b']:.1f}")
r = out[out["batter"] == 678882].dropna(subset=["con"])
if len(r):
    print(f"Rafaela Contact+ rolling: n={len(r)}, latest={r.iloc[-1]['con']:.1f}")
