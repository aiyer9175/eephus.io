# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, glob
from sklearn.model_selection import KFold, cross_val_predict
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score
import seager_compare as sc
st=sc.season_stats()
raw=pd.concat([pd.read_parquet(f,columns=["batter","events","description","game_date"]) for f in glob.glob("data/raw/statcast_*.parquet")],ignore_index=True)
raw["yr"]=pd.to_datetime(raw.game_date).dt.year
pa=raw[raw.events.notna()]; kr=pa.assign(k=pa.events.isin(["strikeout","strikeout_double_play"])).groupby(["batter","yr"]).k.mean().rename("kpct").reset_index()
SW={"hit_into_play","foul","foul_tip","swinging_strike","swinging_strike_blocked"};WH={"swinging_strike","swinging_strike_blocked","foul_tip"}
sw=raw[raw.description.isin(SW)]; whr=sw.assign(w=sw.description.isin(WH)).groupby(["batter","yr"]).w.mean().rename("whiff").reset_index()
b2bp=pd.read_parquet("data/processed/bat_to_ball_plus.parquet")
b2b=b2bp[["batter","season","bat_to_ball_plus","contact_plus","dc_plus"]].rename(columns={"season":"yr","bat_to_ball_plus":"b2b","contact_plus":"contactp","dc_plus":"dcp"})
lb=pd.read_parquet("data/processed/leaderboard_season.parquet");lb["yr"]=lb.season.astype(int)
sp=lb.groupby(["batter","yr"]).swing_plus.mean().reset_index()
dec=sc.decision_by_season().rename(columns={"dec_tailored":"dec"})[["batter","yr","dec"]]
m=st.merge(kr,on=["batter","yr"]).merge(whr,on=["batter","yr"]).merge(b2b,on=["batter","yr"]).merge(sp,on=["batter","yr"]).merge(dec,on=["batter","yr"])
m=m[m.pa>=250].dropna(subset=["b2b","swing_plus","dec","ops"]); m["kpct"]*=100; m["whiff"]*=100
print(f"n={len(m)}")
print("\n=== CHARACTERIZE B2B+ (what is it?) ===")
for c,l in [("kpct","K%"),("whiff","whiff%"),("swing_plus","Swing+"),("dec","Decision+"),("iso","ISO"),("ops","OPS")]:
    print(f"  corr(B2B+, {l:8}) = {m.b2b.corr(m[c]):+.2f}   corr(contact_plus,{l:8})={m.contactp.corr(m[c]):+.2f}")
# Hitter+ : OPS-optimal 3-axis combo
z=lambda c:(m[c]-m[c].mean())/m[c].std()
m["zS"],m["zD"],m["zB"]=z("swing_plus"),z("dec"),z("b2b")
from numpy.linalg import lstsq
X=np.column_stack([np.ones(len(m)),m.zS,m.zD,m.zB]); b,_,_,_=lstsq(X,m.ops.values,rcond=None)
w=np.array([b[1],b[2],b[3]]); w=w/w.sum()
print(f"\nHitter+ OPS weights (normalized): Swing+ {w[0]:.2f}  Decision+ {w[1]:.2f}  B2B+ {w[2]:.2f}")
m["hitter_raw"]=b[1]*m.zS+b[2]*m.zD+b[3]*m.zB
nxt=m[["batter","yr","iso","bbpct","ops"]].copy();nxt["yr"]=nxt.yr-1
mn=m.merge(nxt,on=["batter","yr"],suffixes=("","_next"))
def cv(df,cols,tgt):
    d=df.dropna(subset=cols+[tgt]);p=cross_val_predict(LinearRegression(),d[cols].values,d[tgt].values,cv=KFold(5,shuffle=True,random_state=0));return np.corrcoef(p,d[tgt])[0,1]
print("\n=== Hitter+ (3 axes) vs SwingDecision+ (2 axes) vs SEAGER ===")
print(f"{'':26}{'SAME ISO':>9}{'BB%':>7}{'OPS':>7}{'| NEXT ISO':>11}{'BB%':>7}{'OPS':>7}")
for lab,cols in [("SwingDecision+ (2)",["swing_plus","dec"]),("Hitter+ (3 axes)",["swing_plus","dec","b2b"])]:
    s=[cv(m,cols,t) for t in ["iso","bbpct","ops"]]; n=[cv(mn,cols,t) for t in ["iso_next","bbpct_next","ops_next"]]
    print(f"{lab:26}{s[0]:>9.2f}{s[1]:>7.2f}{s[2]:>7.2f}{n[0]:>11.2f}{n[1]:>7.2f}{n[2]:>7.2f}")
print(f"{'SEAGER (published)':26}{0.46:>9.2f}{0.45:>7.2f}{0.45:>7.2f}{0.41:>11.2f}{0.29:>7.2f}{0.34:>7.2f}")
