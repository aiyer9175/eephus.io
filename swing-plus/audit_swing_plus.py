# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""Independent audit of the Swing+ model. Prints a structured quantitative report."""
import warnings; warnings.filterwarnings("ignore")
import json, numpy as np, pandas as pd, glob
from numpy.linalg import lstsq
from scipy.stats import spearmanr  # noqa
HALVES = ["2023_H2","2024_H1","2024_H2","2025_H1","2025_H2","2026_H1"]
SW={"hit_into_play","foul","foul_tip","swinging_strike","swinging_strike_blocked"}
WH={"swinging_strike","swinging_strike_blocked","foul_tip"}
def line(t): print("\n"+"="*70+f"\n{t}\n"+"="*70)

# ---- build per (batter, half) truth from raw ----
cols=["batter","stand","description","launch_speed","launch_angle","launch_speed_angle",
      "estimated_woba_using_speedangle","game_date"]
raw=pd.concat([pd.read_parquet(f"data/raw/statcast_{h}.parquet",columns=cols).assign(half=h) for h in HALVES],ignore_index=True)
raw["swing"]=raw.description.isin(SW); raw["whiff"]=raw.description.isin(WH)
bip=raw[(raw.description=="hit_into_play")&raw.launch_speed.notna()].copy()
bip["barrel"]=(bip.launch_speed_angle==6).astype(float)
def ev90(x): return np.percentile(x,90) if len(x)>=10 else np.nan
g=bip.groupby(["batter","half"]).agg(ev=("launch_speed","mean"),ev90=("launch_speed",ev90),
    barrel=("barrel","mean"),xwobacon=("estimated_woba_using_speedangle","mean"),nbip=("launch_speed","size"))
sw=raw.groupby(["batter","half"]).agg(nsw=("swing","sum"),whiff=("whiff","mean"))
truth=g.join(sw).reset_index()
lb=pd.read_parquet("data/processed/leaderboard_half.parquet")
keep=["batter","half","swing_plus","swing_plus_raw","reliability","n_swings","bat_speed_mean",
      "pred_xwobacon","pred_avg_ev90","pred_barrel_pct","obs_xwobacon" if "obs_xwobacon" in lb else "obs_barrel_pct"]
m=truth.merge(lb[[c for c in keep if c in lb.columns]],on=["batter","half"],how="inner")
m["season"]=m.half.str[:4].astype(int)

line("DATA INTEGRITY")
print(f"  raw pitch rows: {len(raw):,}  | BIP rows: {len(bip):,}")
print(f"  player-halves (>=1 BIP): {len(truth):,}  | unique players: {truth.batter.nunique()}")
print(f"  date range: {raw.game_date.min()} -> {raw.game_date.max()}  ({len(HALVES)} halves)")
print(f"  merged player-halves with Swing+: {len(m):,}")
print(f"  n_swings distribution: p10 {m.n_swings.quantile(.1):.0f}  p50 {m.n_swings.median():.0f}  p90 {m.n_swings.quantile(.9):.0f}")
print(f"  missingness: ev90 {truth.ev90.isna().mean()*100:.1f}%  xwobacon {truth.xwobacon.isna().mean()*100:.1f}%")

line("GROUND-TRUTH AUDIT — Swing+(raw) concurrent corr with candidate targets")
mm=m.dropna(subset=["ev","ev90","barrel","xwobacon","swing_plus_raw"])
for t in ["ev","ev90","barrel","xwobacon"]:
    r=mm.swing_plus_raw.corr(mm[t]); rho=mm.swing_plus_raw.corr(mm[t],method="spearman")
    print(f"  {t:9s}: Pearson {r:+.3f}  Spearman {rho:+.3f}  R^2 {r*r:.3f}")
# target reliability (signal vs noise of each target itself)
rng=np.random.default_rng(0); bip["h2"]=rng.integers(0,2,len(bip))
print("  -- target self-reliability (split-half, >=40 BIP/half) [higher=less noise] --")
for t,fn in [("ev","mean"),("ev90",ev90),("barrel","mean"),("xwobacon","mean")]:
    a=bip[bip.h2==0].groupby("batter").agg(v=("launch_speed" if t in("ev","ev90") else ("barrel" if t=="barrel" else "estimated_woba_using_speedangle"),fn),n=("launch_speed","size"))
    b=bip[bip.h2==1].groupby("batter").agg(v=("launch_speed" if t in("ev","ev90") else ("barrel" if t=="barrel" else "estimated_woba_using_speedangle"),fn),n=("launch_speed","size"))
    j=a.join(b,lsuffix="_a",rsuffix="_b").query("n_a>=40 and n_b>=40")
    print(f"     {t:9s} r={j.v_a.corr(j.v_b):.3f}")

line("DESCRIPTIVE ACCURACY — model predictions vs observed (concurrent)")
for pred,obs in [("pred_xwobacon","xwobacon"),("pred_avg_ev90","ev90"),("pred_barrel_pct","barrel")]:
    if pred not in m: continue
    d=m.dropna(subset=[pred,obs]).copy()
    o=d[obs].values; p=d[pred].values
    if obs=="barrel": p=p/100 if p.mean()>1 else p
    r=np.corrcoef(p,o)[0,1]; rmse=np.sqrt(((p-o)**2).mean()); mae=np.abs(p-o).mean()
    slope=np.polyfit(p,o,1)[0]
    print(f"  {pred:16s}->{obs:9s}: Pearson {r:+.3f} R^2 {r*r:.3f} RMSE {rmse:.3f} MAE {mae:.3f} calib-slope {slope:.2f}")

line("OUT-OF-SAMPLE — predict NEXT-half observed from THIS-half model")
order={h:i for i,h in enumerate(HALVES)}; m["hi"]=m.half.map(order)
nxt=m[["batter","hi","ev90","xwobacon"]].copy(); nxt["hi"]=nxt["hi"]-1
m2=m.merge(nxt,on=["batter","hi"],suffixes=("","_next")).dropna(subset=["swing_plus_raw","xwobacon_next","ev90_next"])
for tgt in ["xwobacon_next","ev90_next"]:
    r=m2.swing_plus_raw.corr(m2[tgt]); print(f"  Swing+ -> {tgt:14s}: r {r:+.3f} R^2 {r*r:.3f} (n={len(m2)})")
# season-held-out: train scale on early seasons, test 2025-26 (Swing+ is fixed, so just report split corr)
te=m2[m2.season>=2025]
print(f"  (held-out 2025-26 only) Swing+ -> next xwOBAcon r {te.swing_plus_raw.corr(te.xwobacon_next):+.3f} (n={len(te)})")

line("INCREMENTAL VALUE — predict NEXT-half xwOBAcon (GroupKFold by batter)")
from sklearn.model_selection import GroupKFold, cross_val_predict
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score
d=m2.dropna(subset=["ev90","bat_speed_mean","barrel","ev","swing_plus_raw","xwobacon_next"]).copy()
grp=d.batter.values; y=d.xwobacon_next.values
def cvr2(cols):
    X=d[cols].values
    p=cross_val_predict(LinearRegression(),X,y,cv=GroupKFold(5),groups=grp)
    return r2_score(y,p)
base=cvr2(["ev90"]); b2=cvr2(["ev90","bat_speed_mean"]); b3=cvr2(["ev90","bat_speed_mean","barrel","ev"]); b4=cvr2(["ev90","bat_speed_mean","barrel","ev","swing_plus_raw"])
print(f"  EV90                         R^2 {base:.3f}")
print(f"  + Bat speed                  R^2 {b2:.3f}  (Δ {b2-base:+.3f})")
print(f"  + public (barrel,EV)         R^2 {b3:.3f}  (Δ {b3-b2:+.3f})")
print(f"  + Swing+                     R^2 {b4:.3f}  (Δ {b4-b3:+.3f})")

line("RELIABILITY")
piv=m.pivot_table(index="batter",columns="hi",values="swing_plus_raw")
def lagr(k):
    xs,ys=[],[]
    for h in range(6):
        if h+k<=5 and h in piv.columns and h+k in piv.columns:
            j=piv[[h,h+k]].dropna(); xs+=list(j[h]); ys+=list(j[h+k])
    return np.corrcoef(xs,ys)[0,1],len(xs)
for k in [1,2,4]:
    r,n=lagr(k); print(f"  lag {k} half ({k*0.5:.1f} yr): r {r:.3f} (n={n})")
# split-half within-half reliability vs n
print("  -- reliability vs sample (half-to-half by n_swings tercile) --")
m2b=m.merge(m[["batter","hi","swing_plus_raw"]].assign(hi=lambda x:x.hi-1),on=["batter","hi"],suffixes=("","_n")).dropna(subset=["swing_plus_raw_n"])
for lab,lo,hi in [("low",0,200),("mid",200,400),("high",400,9999)]:
    s=m2b[(m2b.n_swings>=lo)&(m2b.n_swings<hi)]
    if len(s)>30: print(f"     n_sw {lab:4s}: r {s.swing_plus_raw.corr(s.swing_plus_raw_n):.3f} (n={len(s)})")

line("CALIBRATION — pred_xwobacon buckets vs observed")
d=m.dropna(subset=["pred_xwobacon","xwobacon"]); d["b"]=pd.qcut(d.pred_xwobacon,8,labels=False,duplicates="drop")
cal=d.groupby("b").agg(pred=("pred_xwobacon","mean"),obs=("xwobacon","mean"),n=("xwobacon","size"))
for _,r in cal.iterrows(): print(f"  pred {r.pred:.3f} -> obs {r.obs:.3f}  (Δ {r.obs-r.pred:+.3f}, n={int(r.n)})")

line("RESIDUALS — persistent over/under performers (obs - pred xwOBAcon)")
d=m.dropna(subset=["pred_xwobacon","xwobacon"]).copy(); d["resid"]=d.xwobacon-d.pred_xwobacon
pr=d.groupby("batter").agg(resid=("resid","mean"),n=("resid","size"),whiff=("whiff","mean")).query("n>=3")
nm=pd.read_parquet("data/processed/leaderboard_alltime.parquet")[["batter","name"]].drop_duplicates("batter").set_index("batter")
pr["name"]=pr.index.map(nm.name)
print("  consistent OVER-performers (obs>pred):")
for _,r in pr.sort_values("resid",ascending=False).head(5).iterrows(): print(f"     {r['name']:20s} +{r.resid:.3f}  whiff {r.whiff*100:.0f}%")
print("  consistent UNDER-performers:")
for _,r in pr.sort_values("resid").head(5).iterrows(): print(f"     {r['name']:20s} {r.resid:.3f}  whiff {r.whiff*100:.0f}%")
print(f"  corr(residual, whiff%) = {pr.resid.corr(pr.whiff):+.3f}  (if strongly +/-, residual ~ bat-to-ball)")

line("STRESS / GENERALIZATION — Swing+ -> next xwOBAcon by subgroup")
d=m2.dropna(subset=["swing_plus_raw","xwobacon_next","ev90","whiff"]).copy()
d["type"]=np.where(d.ev90>=d.ev90.quantile(.66),"power",np.where(d.ev90<=d.ev90.quantile(.33),"contact","balanced"))
for sub in ["power","balanced","contact"]:
    s=d[d.type==sub]; print(f"  {sub:9s}: r {s.swing_plus_raw.corr(s.xwobacon_next):+.3f} (n={len(s)})")
for st in ["L","R"]:
    s=d[d.stand==st] if "stand" in d else d.iloc[0:0]
    if len(s)>30: print(f"  stand {st}: r {s.swing_plus_raw.corr(s.xwobacon_next):+.3f} (n={len(s)})")

line("BAYESIAN SHRINKAGE — raw vs shrunk predicting next-half xwOBAcon")
d=m2.dropna(subset=["swing_plus_raw","swing_plus","xwobacon_next"])
print(f"  raw Swing+   -> next xwOBAcon r {d.swing_plus_raw.corr(d.xwobacon_next):+.3f}")
print(f"  shrunk Swing+-> next xwOBAcon r {d.swing_plus.corr(d.xwobacon_next):+.3f}")
EOF_GUARD = True
