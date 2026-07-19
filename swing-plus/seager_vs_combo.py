# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from sklearn.model_selection import KFold, cross_val_predict
from sklearn.linear_model import LinearRegression
import seager_compare as sc

st=sc.season_stats()                       # ISO, BB%, OPS, Z-O, chase per (batter,yr)
dec=sc.decision_by_season()                # dec_tailored per (batter,yr)
lb=pd.read_parquet("data/processed/leaderboard_season.parquet")
lb["yr"]=lb.season.astype(int)
sp=lb.groupby(["batter","yr"]).swing_plus.mean().reset_index()  # Swing+ per season
m=st.merge(dec,on=["batter","yr"]).merge(sp,on=["batter","yr"])
m=m[m.pa>=250].dropna(subset=["iso","bbpct","ops","swing_plus","dec_tailored"])
# next-season
nxt=m[["batter","yr","iso","bbpct","ops"]].copy(); nxt["yr"]=nxt.yr-1
mn=m.merge(nxt,on=["batter","yr"],suffixes=("","_next"))
print(f"same-season rows {len(m)} | next-season pairs {len(mn)}\n")
def combo(df,feats,tgt):
    d=df.dropna(subset=feats+[tgt]); 
    p=cross_val_predict(LinearRegression(),d[feats].values,d[tgt].values,cv=KFold(5,shuffle=True,random_state=0))
    return np.corrcoef(p,d[tgt].values)[0,1]
print(f"{'':28s}{'ISO':>8}{'BB%':>8}{'OPS':>8}")
print("-"*52)
print(f"{'Swing+ alone':28s}{m.swing_plus.corr(m.iso):8.2f}{m.swing_plus.corr(m.bbpct):8.2f}{m.swing_plus.corr(m.ops):8.2f}")
print(f"{'Decision+ alone':28s}{m.dec_tailored.corr(m.iso):8.2f}{m.dec_tailored.corr(m.bbpct):8.2f}{m.dec_tailored.corr(m.ops):8.2f}")
print(f"{'Swing+ x Decision+ (combo)':28s}{combo(m,['swing_plus','dec_tailored'],'iso'):8.2f}{combo(m,['swing_plus','dec_tailored'],'bbpct'):8.2f}{combo(m,['swing_plus','dec_tailored'],'ops'):8.2f}")
print(f"{'SEAGER (published)':28s}{0.46:8.2f}{0.45:8.2f}{0.45:8.2f}")
print("\nNEXT SEASON:")
print(f"{'':28s}{'ISO':>8}{'BB%':>8}{'OPS':>8}")
print("-"*52)
print(f"{'Swing+ alone':28s}{mn.swing_plus.corr(mn.iso_next):8.2f}{mn.swing_plus.corr(mn.bbpct_next):8.2f}{mn.swing_plus.corr(mn.ops_next):8.2f}")
print(f"{'Decision+ alone':28s}{mn.dec_tailored.corr(mn.iso_next):8.2f}{mn.dec_tailored.corr(mn.bbpct_next):8.2f}{mn.dec_tailored.corr(mn.ops_next):8.2f}")
print(f"{'Swing+ x Decision+ (combo)':28s}{combo(mn,['swing_plus','dec_tailored'],'iso_next'):8.2f}{combo(mn,['swing_plus','dec_tailored'],'bbpct_next'):8.2f}{combo(mn,['swing_plus','dec_tailored'],'ops_next'):8.2f}")
print(f"{'SEAGER (published)':28s}{0.41:8.2f}{0.29:8.2f}{0.34:8.2f}")
