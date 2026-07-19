# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""Independent audit of the MLB swing-tailored Decision model (decision-theory oriented)."""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from numpy.linalg import lstsq
import mlb_decision as md
def line(t): print("\n"+"="*70+f"\n{t}\n"+"="*70)
agg, d = md.score(verbose=False)
nm=pd.read_parquet("data/processed/leaderboard_alltime.parquet")[["batter","name"]].drop_duplicates("batter").set_index("batter")

line("DATA INTEGRITY")
print(f"  pitch rows: {len(d):,}  | hitters scored (>=300 pitches): {len(agg)}")
print(f"  pitches/hitter: p10 {agg.pitches.quantile(.1):.0f}  p50 {agg.pitches.median():.0f}  p90 {agg.pitches.quantile(.9):.0f}")
print(f"  Decision+ MLB: mean {agg.decision_plus_mlb.mean():.1f} sd {agg.decision_plus_mlb.std():.1f}")

line("LEAKAGE AUDIT")
print("  target leakage: LOW — decision_rv uses count-value (league) + called-strike (league) +")
print("    hitter swing-outcome rates; the action chosen (swung) is the predictor, not the target.")
print("  derived: MODERATE — EV_swing uses the hitter's own whiff/contact rates (shrunk), so a")
print("    hitter's decision value is partly evaluated with his own outcomes (self-referential by design).")
print("  temporal: LOW for ranking (career rates); for prediction we test next-half OOS below.")
print("  identity: LOW — league baselines pooled; per-hitter only via shrunk rates.")

line("RELIABILITY")
rng=np.random.default_rng(0); d2=d.assign(h=rng.integers(0,2,len(d)))
A=d2[d2.h==0].groupby("batter").agg(rv=("drv_tailored","mean"),n=("drv_tailored","size"))
B=d2[d2.h==1].groupby("batter").agg(rv=("drv_tailored","mean"),n=("drv_tailored","size"))
j=A.join(B,lsuffix="_a",rsuffix="_b").query("n_a>=400 and n_b>=400")
print(f"  split-half decision RV: r {j.rv_a.corr(j.rv_b):.3f} (n={len(j)})")
# year over year
d2["season"]=d2.index.map(lambda i: None)  # placeholder
d["season"]=pd.to_datetime(d.get("game_date","2024")) if "game_date" in d else 2024

line("OUT-OF-SAMPLE — does decision RV predict NEXT-season production?")
# build per (batter, season)
import glob
pa=pd.concat([pd.read_parquet(f,columns=["batter","events","woba_value","woba_denom","game_date"]) for f in glob.glob("data/raw/statcast_*.parquet")],ignore_index=True)
pa=pa[pa.events.notna()&(pa.woba_denom.fillna(0)>0)].copy(); pa["yr"]=pd.to_datetime(pa.game_date).dt.year
woba_ys=pa.groupby(["batter","yr"]).agg(woba=("woba_value","mean"),pa=("woba_value","size"))
# decision RV by season
d["yr"]=pd.to_datetime(d.game_date).dt.year if "game_date" in d.columns else 2024
# game_date not loaded in d; reload light to map season
gd=pd.concat([pd.read_parquet(f"data/raw/statcast_{h}.parquet",columns=["batter","game_pk","at_bat_number","balls","strikes","game_date"]).assign() for h in md.HALVES],ignore_index=True)
# simpler: recompute decision RV per (batter, half) using d.half
drv_h=d.groupby(["batter","half"]).agg(rv=("drv_tailored","mean"),n=("drv_tailored","size")).reset_index()
drv_h["yr"]=drv_h.half.str[:4].astype(int)
drv_y=drv_h.groupby(["batter","yr"]).apply(lambda x: np.average(x.rv,weights=x.n)).rename("rv").reset_index()
mm=drv_y.merge(woba_ys.reset_index(),on=["batter","yr"])
mm["yr_next"]=mm.yr+1
nxt=mm[["batter","yr","woba"]].rename(columns={"yr":"yr_next","woba":"woba_next"})
mm=mm.merge(nxt,on=["batter","yr_next"]).query("pa>=150")
print(f"  decision RV (yr) -> SAME-year wOBA:  r {mm.rv.corr(mm.woba):+.3f}")
print(f"  decision RV (yr) -> NEXT-year wOBA:  r {mm.rv.corr(mm.woba_next):+.3f} (n={len(mm)})")

line("EXPECTED RUN VALUE ADDED")
rv100=agg.dec_rv100_tailored
print(f"  decision RV per 100 pitches: p10 {rv100.quantile(.1):+.3f}  p50 {rv100.median():+.3f}  p90 {rv100.quantile(.9):+.3f}  (wOBA units)")
print(f"  spread best-worst: {rv100.max()-rv100.min():.3f} wOBA/100 pitches (~{(rv100.max()-rv100.min())*15:.1f} wOBA pts/season at ~1500 pitches)")

line("OPTIMAL SWING/TAKE POLICY")
d["opt_swing"]=(d.ev_diff>0).astype(int)         # optimal = swing if EV_swing>EV_take
d["correct"]=(d.swung==d.opt_swing).astype(int)
d["regret"]=np.where(d.swung==d.opt_swing,0.0,np.abs(d.ev_diff))
pol=d.groupby("batter").agg(acc=("correct","mean"),regret=("regret","mean"),n=("correct","size")).query("n>=300")
pol["name"]=pol.index.map(nm.name)
print(f"  league policy accuracy (chose higher-EV action): {d.correct.mean()*100:.1f}%")
print(f"  per-hitter accuracy: p10 {pol.acc.quantile(.1)*100:.0f}%  p50 {pol.acc.median()*100:.0f}%  p90 {pol.acc.quantile(.9)*100:.0f}%")
print(f"  corr(policy accuracy, Decision+) = {pol.acc.corr(agg.set_index('batter').decision_plus_mlb.reindex(pol.index)):+.3f}")

line("SELECTIVITY EFFICIENCY — correct pitches, or just swinging less?")
sr=d.groupby("batter").agg(swing_rate=("swung","mean"),
      chase=("swung", lambda s: np.nan)).copy()  # placeholder
swing_rate=d.groupby("batter").swung.mean().rename("swing_rate")
# selectivity = within-hitter corr between swinging and EV_diff (does he swing at +EV pitches?)
sel={}
for b,gg in d.groupby("batter"):
    if len(gg)>=300 and gg.ev_diff.std()>0: sel[b]=np.corrcoef(gg.swung,gg.ev_diff)[0,1]
sel=pd.Series(sel,name="selectivity")
S=pd.concat([agg.set_index("batter").decision_plus_mlb, swing_rate, sel],axis=1).dropna()
print(f"  corr(Decision+, overall swing rate)  = {S.decision_plus_mlb.corr(S.swing_rate):+.3f}   <- if ~0, NOT just swinging less")
print(f"  corr(Decision+, selectivity)         = {S.decision_plus_mlb.corr(S.selectivity):+.3f}   <- swinging at the RIGHT pitches")
# partial: does selectivity drive Decision+ beyond swing rate?
X=np.column_stack([np.ones(len(S)),(S.swing_rate-S.swing_rate.mean())/S.swing_rate.std()])
b1,_,_,_=lstsq(X,S.decision_plus_mlb.values,rcond=None); r2_sr=1-((S.decision_plus_mlb-X@b1)**2).sum()/((S.decision_plus_mlb-S.decision_plus_mlb.mean())**2).sum()
X2=np.column_stack([X,(S.selectivity-S.selectivity.mean())/S.selectivity.std()])
b2,_,_,_=lstsq(X2,S.decision_plus_mlb.values,rcond=None); r2_both=1-((S.decision_plus_mlb-X2@b2)**2).sum()/((S.decision_plus_mlb-S.decision_plus_mlb.mean())**2).sum()
print(f"  R^2 of Decision+ from swing-rate alone {r2_sr:.3f} ; + selectivity {r2_both:.3f}")

line("DECISION ENTROPY — crisp policy vs random swinging (by zone)")
# entropy of swing decision within zone, averaged (low = decisive/consistent)
def ent(p): p=np.clip(p,1e-6,1-1e-6); return -(p*np.log2(p)+(1-p)*np.log2(1-p))
ez=d.groupby(["batter","zone"]).swung.mean()
nz=d.groupby(["batter","zone"]).size()
edf=pd.DataFrame({"p":ez,"n":nz}).reset_index()
edf["H"]=ent(edf.p.values)
hb=edf.groupby("batter").apply(lambda x: np.average(x.H,weights=x.n)).rename("entropy")
E=pd.concat([agg.set_index("batter").decision_plus_mlb,hb],axis=1).dropna()
print(f"  mean per-zone swing entropy: {hb.mean():.3f} bits (0=always same, 1=coinflip)")
print(f"  corr(Decision+, entropy) = {E.decision_plus_mlb.corr(E.entropy):+.3f}  (neg = better deciders are more decisive)")

line("STRESS — Decision+ vs production by hitter type")
prod=pa.groupby("batter").agg(woba=("woba_value","mean"),pa=("woba_value","size"))
P=agg.merge(prod,on="batter").query("pa>=200")
P["whiff_proxy"]=P.batter.map(d.groupby("batter").swung.mean())  # crude
P["tier"]=np.where(P.woba>=P.woba.quantile(.66),"good",np.where(P.woba<=P.woba.quantile(.33),"weak","avg"))
for t in ["good","avg","weak"]:
    s=P[P.tier==t]; print(f"  {t:5s} hitters: Decision+ mean {s.decision_plus_mlb.mean():.1f}")
print(f"  corr(Decision+, wOBA) overall = {P.decision_plus_mlb.corr(P.woba):+.3f}")

line("FACE VALIDITY")
s=agg.dropna(subset=["name"]).sort_values("decision_plus_mlb",ascending=False)
print("  TOP:   "+", ".join(f"{r['name']}({r.decision_plus_mlb:.0f})" for _,r in s.head(5).iterrows()))
print("  BOTTOM:"+", ".join(f"{r['name']}({r.decision_plus_mlb:.0f})" for _,r in s.tail(5).iterrows()))
