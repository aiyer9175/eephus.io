# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""Compare our MLB Decision model to SEAGER's published correlation profile.
Builds the same table: same-season & next-season corr with ISO / BB% / OPS, plus
metric self-correlation (year-to-year)."""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, glob
import mlb_decision as md

HITS={"single":1,"double":2,"triple":3,"home_run":4}
BB={"walk","intent_walk"}; HBP={"hit_by_pitch"}; SF={"sac_fly","sac_fly_double_play"}
SAC={"sac_bunt","sacrifice_bunt_double_play"}
SW={"hit_into_play","foul","foul_tip","swinging_strike","swinging_strike_blocked"}

def season_stats():
    cols=["batter","events","description","plate_x","plate_z","sz_top","sz_bot","game_date"]
    raw=pd.concat([pd.read_parquet(f,columns=cols) for f in glob.glob("data/raw/statcast_*.parquet")],ignore_index=True)
    raw["yr"]=pd.to_datetime(raw.game_date).dt.year
    pa=raw[raw.events.notna()].copy()
    def agg(g):
        n=len(g); bb=g.events.isin(BB).sum(); hbp=g.events.isin(HBP).sum(); sf=g.events.isin(SF).sum(); sac=g.events.isin(SAC).sum()
        ab=n-bb-hbp-sf-sac
        b1=(g.events=="single").sum(); b2=(g.events=="double").sum(); b3=(g.events=="triple").sum(); hr=(g.events=="home_run").sum()
        h=b1+b2+b3+hr; tb=b1+2*b2+3*b3+4*hr
        avg=h/ab if ab else np.nan; slg=tb/ab if ab else np.nan; iso=slg-avg if ab else np.nan
        obp=(h+bb+hbp)/(ab+bb+hbp+sf) if (ab+bb+hbp+sf) else np.nan
        return pd.Series({"pa":n,"iso":iso,"bbpct":bb/n*100,"ops":(obp+slg) if pd.notna(obp) else np.nan})
    st=pa.groupby(["batter","yr"]).apply(agg).reset_index()
    # zone / chase
    sw=raw.dropna(subset=["plate_x","plate_z","sz_top","sz_bot"]).copy()
    sw["sw"]=sw.description.isin(SW)
    sw["inzone"]=(sw.plate_x.abs()<=0.83)&(sw.plate_z>=sw.sz_bot)&(sw.plate_z<=sw.sz_top)
    z=sw.groupby(["batter","yr"]).apply(lambda g: pd.Series({
        "zsw": g[g.inzone].sw.mean(), "chase": g[~g.inzone].sw.mean()})).reset_index()
    z["zminus_o"]=z.zsw-z.chase
    return st.merge(z,on=["batter","yr"])

def decision_by_season():
    agg,d=md.score(verbose=False)
    d["yr"]=d.half.str[:4].astype(int)
    g=d.groupby(["batter","yr"]).agg(rv_t=("drv_tailored","mean"),rv_g=("drv_generic","mean"),
        rv_d=("drv_damage","mean"),n=("drv_tailored","size")).reset_index()
    g=g[g.n>=400]
    g["dec_tailored"]=g.rv_t*100; g["dec_generic"]=g.rv_g*100; g["dec_damage"]=g.rv_d*100
    return g[["batter","yr","dec_tailored","dec_generic","dec_damage"]]

st=season_stats(); dec=decision_by_season()
m=st.merge(dec,on=["batter","yr"])
m=m[m.pa>=250].dropna(subset=["iso","bbpct","ops"])
metrics={"Decision+ (pure discipline)":"dec_tailored","Damage-aware Decision (zone)":"dec_damage",
         "Z-O (zone% - chase%)":"zminus_o","Chase%":"chase"}
# next-season pairs
nxt=m[["batter","yr","iso","bbpct","ops","dec_tailored","dec_generic","dec_damage","zminus_o","chase"]].copy(); nxt["yr"]=nxt.yr-1
mn=m.merge(nxt,on=["batter","yr"],suffixes=("","_next"))
print(f"same-season rows: {len(m)} | next-season pairs: {len(mn)}\n")
print(f"{'METRIC':34s} | {'SAME: ISO':>9} {'BB%':>6} {'OPS':>6} | {'NEXT: Self':>10} {'ISO':>6} {'BB%':>6} {'OPS':>6}")
print("-"*100)
for lab,col in metrics.items():
    iso=m[col].corr(m.iso); bb=m[col].corr(m.bbpct); ops=m[col].corr(m.ops)
    self_=mn[col].corr(mn[col+"_next"]); isoN=mn[col].corr(mn.iso_next); bbN=mn[col].corr(mn.bbpct_next); opsN=mn[col].corr(mn.ops_next)
    print(f"{lab:34s} | {iso:9.2f} {bb:6.2f} {ops:6.2f} | {self_:10.2f} {isoN:6.2f} {bbN:6.2f} {opsN:6.2f}")
print("\nSEAGER (published, for reference):")
print(f"{'SEAGER':34s} | {0.46:9.2f} {0.45:6.2f} {0.45:6.2f} | {0.66:10.2f} {0.41:6.2f} {0.29:6.2f} {0.34:6.2f}")
print(f"{'Z-O (published)':34s} | {0.25:9.2f} {0.46:6.2f} {0.26:6.2f} | {0.75:10.2f} {0.24:6.2f} {0.40:6.2f} {0.23:6.2f}")
print(f"{'Chase (published)':34s} | {-0.11:9.2f} {-0.79:6.2f} {-0.18:6.2f} | {0.82:10.2f} {-0.11:6.2f} {-0.63:6.2f} {-0.12:6.2f}")
