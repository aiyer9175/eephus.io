# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""Score 2026 Bat-to-Ball+ (B2B+ = damage-conversion) using the framework's opportunity
models, calibrated to the framework's existing B2B+ scale. Low-sample shrunk (2026 = H1 only)."""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, glob, joblib
from sklearn.linear_model import LinearRegression
BMODELS = "/tmp/b2b/bat_to_ball_plus/models"
NUM = ["plate_x","plate_z","release_speed","pfx_x","pfx_z","release_spin_rate","spin_axis","balls","strikes",
       "release_pos_x","release_pos_z","release_extension","arm_angle","effective_speed"]
CAT = ["pitch_type","stand","p_throws"]
COMMON_PT = {"FF","SI","SL","CH","FC","ST","CU","FS","KC"}
opp = {t: joblib.load(f"{BMODELS}/opportunity_{t}_v2.lgb.joblib") for t in ["ev","xwobacon","barrel","squared_up"]}

def score_resid(df):
    df = df.copy()
    for c in ["release_spin_rate","spin_axis","release_extension","arm_angle","release_pos_x","release_pos_z","effective_speed"]:
        df[c] = df[c].fillna(df[c].median())
    df["pitch_type"] = df["pitch_type"].astype(str).where(df["pitch_type"].astype(str).isin(COMMON_PT), "other").astype("category")
    df["stand"] = df["stand"].astype("category"); df["p_throws"] = df["p_throws"].astype("category")
    X = df[NUM+CAT]
    df["o_ev"] = opp["ev"].predict(X); df["o_xw"] = opp["xwobacon"].predict(X)
    df["o_ba"] = opp["barrel"].predict(X); df["o_su"] = opp["squared_up"].predict(X)
    df["barrel"] = (df.launch_speed_angle == 6).astype(float)
    df["su"] = (df.launch_speed / (1.23*df.bat_speed + 0.2116*df.release_speed) >= 0.80).astype(float)
    df["r_ev"] = df.launch_speed - df.o_ev
    df["r_xw"] = df.estimated_woba_using_speedangle - df.o_xw
    df["r_ba"] = df.barrel - df.o_ba
    df["r_su"] = df.su - df.o_su
    return df

cols = ["batter","stand","p_throws","pitch_type","description","type","launch_speed","launch_angle",
        "launch_speed_angle","estimated_woba_using_speedangle","bat_speed","game_date"]+[c for c in NUM if c not in ("balls","strikes")]+["balls","strikes"]
rows=[]
for f in sorted(glob.glob("data/raw/statcast_*.parquet")):
    d = pd.read_parquet(f, columns=[c for c in cols if c])
    d["yr"] = pd.to_datetime(d.game_date).dt.year
    bip = d[(d.description=="hit_into_play") & d.launch_speed.notna() & d.estimated_woba_using_speedangle.notna() & d.bat_speed.notna()]
    if len(bip): rows.append(score_resid(bip))
bip = pd.concat(rows, ignore_index=True)
agg = bip.groupby(["batter","yr"]).agg(n_bip=("r_ev","size"), r_ev=("r_ev","mean"), r_xw=("r_xw","mean"),
        r_ba=("r_ba","mean"), r_su=("r_su","mean")).reset_index()
# calibrate to framework B2B+ on 2024+2025 (full seasons in our data)
fw = pd.read_parquet("data/processed/bat_to_ball_plus.parquet")[["batter","season","bat_to_ball_plus","n_bip"]].rename(columns={"season":"yr"})
cal = agg.merge(fw[["batter","yr","bat_to_ball_plus"]], on=["batter","yr"]).query("yr in [2024,2025] and n_bip>=80").dropna()
feats=["r_ev","r_xw","r_ba","r_su"]
lr = LinearRegression().fit(cal[feats], cal.bat_to_ball_plus)
print(f"calibration R^2 (residuals -> framework B2B+): {lr.score(cal[feats], cal.bat_to_ball_plus):.3f} (n={len(cal)})")
# predict 2026 + low-sample shrink toward 100
a26 = agg[agg.yr==2026].copy()
a26["pred"] = lr.predict(a26[feats])
K=120
a26["bat_to_ball_plus"] = (100 + (a26.pred-100)*a26.n_bip/(a26.n_bip+K)).round(1)
a26["season"]=2026
print(f"2026 hitters scored: {len(a26)} (median BIP {a26.n_bip.median():.0f}); shrunk toward 100 (K={K})")
# append to framework parquet (add contact/dc placeholders = NaN; B2B+ is the headline)
full = pd.read_parquet("data/processed/bat_to_ball_plus.parquet")
new = a26[["batter","season","n_bip","bat_to_ball_plus"]].copy()
for c in ["contact_plus","dc_plus"]:
    if c in full.columns: new[c]=np.nan
full26 = pd.concat([full[full.season!=2026], new], ignore_index=True)
full26.to_parquet("data/processed/bat_to_ball_plus.parquet", index=False)
print("appended 2026 to bat_to_ball_plus.parquet; total rows", len(full26))
print(a26.sort_values("bat_to_ball_plus",ascending=False).head(6)[["batter","n_bip","bat_to_ball_plus"]].to_string(index=False))
