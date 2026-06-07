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

st=sc.season_stats(); dec=sc.decision_by_season()
lb=pd.read_parquet("data/processed/leaderboard_season.parquet"); lb["yr"]=lb.season.astype(int)
sp=lb.groupby(["batter","yr"]).swing_plus.mean().reset_index()
m=st.merge(dec,on=["batter","yr"]).merge(sp,on=["batter","yr"])
m=m[m.pa>=250].dropna(subset=["ops","swing_plus","dec_tailored"])

# pitch-level tailoring (career): does he swing where his swing grades well? (the covariance term)
SW={"hit_into_play","foul","foul_tip","swinging_strike","swinging_strike_blocked"}
sg=pd.read_parquet("data/processed/swing_grades.parquet")
sg["zone"]=np.where(sg.plate_x<-0.3,0,np.where(sg.plate_x>0.3,2,1))*3+np.where(sg.plate_z<2.2,0,np.where(sg.plate_z>3.0,2,1))
raw=pd.concat([pd.read_parquet(f,columns=["batter","description","plate_x","plate_z"]) for f in glob.glob("data/raw/statcast_*.parquet")],ignore_index=True).dropna(subset=["plate_x","plate_z"])
raw["zone"]=np.where(raw.plate_x<-0.3,0,np.where(raw.plate_x>0.3,2,1))*3+np.where(raw.plate_z<2.2,0,np.where(raw.plate_z>3.0,2,1)); raw["sw"]=raw.description.isin(SW)
gz=sg.groupby(["batter","zone"]).swing_grade.mean().unstack(); rz=raw.groupby(["batter","zone"]).sw.mean().unstack(); nz=raw.groupby(["batter","zone"]).size().unstack()
tail={}
for b in gz.index.intersection(rz.index):
    g,r,n=gz.loc[b],rz.loc[b],nz.loc[b]; msk=g.notna()&r.notna()&(n>=25)
    if msk.sum()>=6: tail[b]=np.corrcoef(g[msk],r[msk])[0,1]
m["tailor"]=m.batter.map(pd.Series(tail))
m=m.dropna(subset=["tailor"])

nxt=m[["batter","yr","ops"]].rename(columns={"ops":"ops_next"}); nxt["yr"]=nxt.yr-1
mn=m.merge(nxt,on=["batter","yr"])
print(f"next-season pairs (with tailoring): {len(mn)}\n")
def cv(df,feats,tgt):
    d=df.dropna(subset=feats+[tgt]); 
    p=cross_val_predict(LinearRegression(),d[feats].values,d[tgt].values,cv=KFold(5,shuffle=True,random_state=0))
    return np.corrcoef(p,d[tgt])[0,1], r2_score(d[tgt],p)
def zsum(df,feats,tgt):  # fixed equal-weight sum of z-scores (the per-pitch unified proxy)
    d=df.dropna(subset=feats+[tgt]); Z=sum((d[f]-d[f].mean())/d[f].std() for f in feats)
    return np.corrcoef(Z,d[tgt])[0,1]
print("Predict NEXT-season OPS:")
print(f"  A. optimized combo  (SP + Dec, regression)     r {cv(mn,['swing_plus','dec_tailored'],'ops_next')[0]:.3f}")
print(f"  B. fixed sum        (z(SP)+z(Dec), 1:1)         r {zsum(mn,['swing_plus','dec_tailored'],'ops_next'):.3f}")
print(f"  C. combo + tailoring (per-pitch covariance)     r {cv(mn,['swing_plus','dec_tailored','tailor'],'ops_next')[0]:.3f}")
print(f"\n  R^2:  A {cv(mn,['swing_plus','dec_tailored'],'ops_next')[1]:.3f}   C {cv(mn,['swing_plus','dec_tailored','tailor'],'ops_next')[1]:.3f}   (does tailoring/covariance add?)")
print(f"  corr(tailoring, next OPS) raw = {mn.tailor.corr(mn.ops_next):+.3f}")
