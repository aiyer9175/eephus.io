"""Score 2026 Contact+ via the framework's difficulty-contact model, calibrated to the
framework Contact+ scale (2024-25), low-sample shrunk. Updates bat_to_ball_plus.parquet 2026 rows."""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, glob, joblib
from sklearn.linear_model import LinearRegression
BM="/tmp/b2b/bat_to_ball_plus/models"
NUM=["plate_x","plate_z","release_speed","pfx_x","pfx_z","release_spin_rate","spin_axis","balls","strikes",
     "release_pos_x","release_pos_z","release_extension","arm_angle","effective_speed"]
CAT=["pitch_type","stand","p_throws"]; COMMON={"FF","SI","SL","CH","FC","ST","CU","FS","KC"}
SWING={"foul","foul_bunt","foul_tip","bunt_foul_tip","hit_into_play","missed_bunt","swinging_strike","swinging_strike_blocked"}
WHIFF={"swinging_strike","swinging_strike_blocked","missed_bunt"}
dc=joblib.load(f"{BM}/difficulty_contact.lgb.joblib")
cols=["batter","stand","p_throws","pitch_type","description","game_date"]+[c for c in NUM]
rows=[]
for f in sorted(glob.glob("data/raw/statcast_*.parquet")):
    d=pd.read_parquet(f,columns=[c for c in cols]); d["yr"]=pd.to_datetime(d.game_date).dt.year
    sw=d[d.description.isin(SWING)].copy()
    if not len(sw): continue
    for c in ["release_spin_rate","spin_axis","release_extension","arm_angle","release_pos_x","release_pos_z","effective_speed"]:
        sw[c]=sw[c].fillna(sw[c].median())
    sw["pitch_type"]=sw.pitch_type.astype(str).where(sw.pitch_type.astype(str).isin(COMMON),"other").astype("category")
    sw["stand"]=sw.stand.astype("category"); sw["p_throws"]=sw.p_throws.astype("category")
    sw["exp_contact"]=dc.predict(sw[NUM+CAT])
    sw["obs_contact"]=(~sw.description.isin(WHIFF)).astype(float)
    sw["resid"]=sw.obs_contact-sw.exp_contact
    rows.append(sw[["batter","yr","resid"]])
allsw=pd.concat(rows,ignore_index=True)
agg=allsw.groupby(["batter","yr"]).agg(n_sw=("resid","size"),resid=("resid","mean")).reset_index()
fw=pd.read_parquet("data/processed/bat_to_ball_plus.parquet")
cal=agg.merge(fw[["batter","season","contact_plus"]].rename(columns={"season":"yr"}),on=["batter","yr"]).query("yr in [2024,2025] and n_sw>=150").dropna()
lr=LinearRegression().fit(cal[["resid"]],cal.contact_plus)
print(f"Contact+ calibration R^2: {lr.score(cal[['resid']],cal.contact_plus):.3f} (n={len(cal)})")
a26=agg[agg.yr==2026].copy(); a26["pred"]=lr.predict(a26[["resid"]])
K=200; a26["contact_plus_new"]=(100+(a26.pred-100)*a26.n_sw/(a26.n_sw+K)).round(1)
print(f"2026 Contact+ scored: {len(a26)} (median swings {a26.n_sw.median():.0f}, shrunk K={K})")
# update 2026 rows in the parquet
fw=fw.merge(a26[["batter","contact_plus_new"]].assign(season=2026),on=["batter","season"],how="left")
fw.loc[fw.contact_plus_new.notna(),"contact_plus"]=fw.loc[fw.contact_plus_new.notna(),"contact_plus_new"]
fw=fw.drop(columns="contact_plus_new")
fw.to_parquet("data/processed/bat_to_ball_plus.parquet",index=False)
print("updated 2026 contact_plus; 2026 rows with contact_plus:", fw[(fw.season==2026)].contact_plus.notna().sum())
