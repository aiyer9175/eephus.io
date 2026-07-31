"""Re-run the total-value test restricted to CLEAN movers: >=70% of fielding innings
at the origin in t and >=70% at the destination in t+1. Removes the attenuation from
partial position changes."""
import json, statistics, random
import numpy as np
import positional_fit as pf
from collections import defaultdict
feeds=pf.Feeds(); pay=json.load(open('data/positional_fit.json')); f=pay['fit']
lad=f['ladder']['values']; D=f['difficulty']['values']
sig={k:v['signal_sd'] for k,v in f['signal'].items()}; kinn={k:v['k_inn'] for k,v in f['signal'].items()}
C=f['ladder']['inn_per_pa']*650/1000.0; obs=feeds.rates(); dh=feeds.defhist; RPW=9.7
def share(mid,y,p):
    b=feeds.innings(mid,y); t=sum(v['inn'] for q,v in b.items() if q!='P')
    return (b.get(p,{}).get('inn',0.0)/t) if t>0 else 0.0
def z_of(row):
    n=d=0.0
    for p,r in row.items():
        n+=r['inn']/kinn[p]*(r['rate']-D[p])/sig[p]; d+=r['inn']/kinn[p]
    return n/(1+d)
rows=[]
for y in range(2016,2026):
    for mid_s in feeds.inn['seasons'].get(str(y),{}):
        mid=int(mid_s)
        a=feeds.primary_position(mid,y); b=feeds.primary_position(mid,y+1)
        if a is None or b is None or a==b or a not in pf.OAA_POSITIONS or b not in pf.OAA_POSITIONS: continue
        k1,k2=f'{mid}:{y}',f'{mid}:{y+1}'
        if k1 not in dh or k2 not in dh or dh[k1]['pa']<300 or dh[k2]['pa']<300: continue
        if share(mid,y,a)<0.70 or share(mid,y+1,b)<0.70: continue
        r1=obs.get((mid,y))
        if not r1: continue
        zz=z_of(r1)
        def tot(k): return dh[k]['war_def']*RPW/dh[k]['pa']*650.0
        rows.append(dict(a=a,b=b,pred=(D[b]-D[a])*C+(lad[b]-lad[a])+(sig[b]-sig[a])*zz*C,
                         lad=lad[b]-lad[a],act=tot(k2)-tot(k1)))
print(f'=== CLEAN movers (>=70% share both sides, both seasons >=300 PA): n={len(rows)} ===')
def mae(rs,k): return statistics.mean(abs((rs[0][k]*0 if k is None else 0)+ (0 if k is None else r[k])-r['act']) for r in rs) if False else statistics.mean(abs((0.0 if k is None else r[k])-r['act']) for r in rs)
print(f'  MAE model {mae(rows,"pred"):.3f}   ladder-only {mae(rows,"lad"):.3f}   zero-change {mae(rows,None):.3f}')
rng=random.Random(3); n=len(rows); dz=[]
for _ in range(2000):
    pk=[rows[rng.randrange(n)] for _ in range(n)]; dz.append(mae(pk,None)-mae(pk,'pred'))
print(f'  model advantage over zero-change: {np.mean(dz):+.3f}  CI95 [{np.percentile(dz,2.5):+.3f}, {np.percentile(dz,97.5):+.3f}]')
g=defaultdict(list)
for r in rows: g[(r['a'],r['b'])].append(r)
print('  move      n    model pred    actual      CI95 of actual        verdict')
for (a,b),s in sorted(g.items(),key=lambda kv:-len(kv[1])):
    if len(s)<10: continue
    act=[r['act'] for r in s]
    bs=[statistics.mean([act[rng.randrange(len(act))] for _ in act]) for _ in range(3000)]
    lo,hi=np.percentile(bs,2.5),np.percentile(bs,97.5); pm=statistics.mean(r['pred'] for r in s)
    print(f'  {a}->{b:3s} {len(s):4d}   {pm:+8.2f}   {statistics.mean(act):+8.2f}   [{lo:+6.2f},{hi:+6.2f}]   {"ok" if lo<=pm<=hi else "MISS by %.1f runs"%(min(abs(pm-lo),abs(pm-hi)))}')
