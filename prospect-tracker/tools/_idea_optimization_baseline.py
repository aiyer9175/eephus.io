import json, math, statistics
from scipy.stats import spearmanr
d=json.load(open('data/mlb_projections.json',encoding='utf-8'))
to={t['team']:t for t in d['team_outlook']}
# fa_fit-style: 47.7 + sum(max(0,war)) over CONTRACTED players (team-attached vets)
cw={}
for v in d['vets']:
    t=v.get('team')
    if t and v.get('war'): cw[t]=cw.get(t,0.0)+max(0.0,v['war'][0])
def lev(w, shift=12.0, c=86.5, s=2.8):
    p=1/(1+math.exp(-(w+shift-c)/s)); return 4*p*(1-p)
rows=[]
for t in sorted(cw):
    fa_base=47.7+cw[t]
    fa_lev=lev(fa_base)
    proj_lev=lev(to[t]['wins'], shift=0.0)
    rows.append((t, round(fa_base,1), round(fa_base+12,1), round(to[t]['wins'],1), round(fa_lev,3), round(proj_lev,3)))
print(f"{'org':>4}{'faBase':>8}{'fa+12':>8}{'projW':>8}{'faLev':>8}{'projLev':>9}{'diffW':>7}")
for r in sorted(rows,key=lambda z:-z[5]):
    print(f"{r[0]:>4}{r[1]:>8.1f}{r[2]:>8.1f}{r[3]:>8.1f}{r[4]:>8.3f}{r[5]:>9.3f}{r[2]-r[3]:>7.1f}")
fw=[r[2] for r in rows]; pw=[r[3] for r in rows]
fl=[r[4] for r in rows]; pl=[r[5] for r in rows]
print()
print('wins: rho(fa_shifted, proj)=',round(spearmanr(fw,pw).statistic,3))
print('leverage: rho=',round(spearmanr(fl,pl).statistic,3))
print('fa wins sd',round(statistics.pstdev(fw),2),'proj wins sd',round(statistics.pstdev(pw),2))
print('fa lev range',round(min(fl),3),round(max(fl),3),'| proj lev range',round(min(pl),3),round(max(pl),3))
err=[abs(a-b) for a,b in zip(fw,pw)]
print('mean |wins error| of fa baseline vs published projections:',round(statistics.mean(err),2),'max',round(max(err),1))
# rank churn
import numpy as np
fr={t:i for i,t in enumerate(sorted(rows,key=lambda z:-z[4]))}
pr={t:i for i,t in enumerate(sorted(rows,key=lambda z:-z[5]))}
mv=[abs(fr[r]-pr[r]) for r in rows]
print('mean |rank move| in leverage ordering:',round(statistics.mean(mv),1),'max',max(mv))
