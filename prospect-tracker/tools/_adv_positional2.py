import json, math, statistics, random
import numpy as np
import positional_fit as pf
from collections import defaultdict

feeds=pf.Feeds(); pay=json.load(open('data/positional_fit.json')); f=pay['fit']
lad=f['ladder']['values']; D=f['difficulty']['values']
sig={k:v['signal_sd'] for k,v in f['signal'].items()}; kinn={k:v['k_inn'] for k,v in f['signal'].items()}
C=f['ladder']['inn_per_pa']*650.0/1000.0
obs=feeds.rates(); dh=feeds.defhist; RPW=9.7

# --- Q1: is Savant FRP position-centered? (if yes, D is a SELECTION term, not difficulty)
print('=== Q1  mean Savant FRP rate per 1000 inn, by position (inn>=300) ===')
for p in pf.OAA_POSITIONS:
    v=[d[p]['rate'] for d in obs.values() if p in d and d[p]['inn']>=300]
    w=[d[p]['inn'] for d in obs.values() if p in d and d[p]['inn']>=300]
    print(f'  {p:3s} n={len(v):4d} mean {statistics.mean(v):+6.3f}  inn-wtd {sum(a*b for a,b in zip(v,w))/sum(w):+6.3f}   D={D[p]:+6.3f}')
print('  -> if means are ~0 at every position, OAA is position-centered and D measures')
print('     WHO PLAYS THERE (selection), which is exactly what the ladder already prices.')

# --- Q2: BRef fielding-only change vs Savant rate change, for the same movers
def shrunk_z(row):
    num=den=0.0
    for p,rec in row.items():
        if sig[p]<=0: continue
        num+=rec['inn']/kinn[p]*(rec['rate']-D[p])/sig[p]; den+=rec['inn']/kinn[p]
    return num/(1.0+den)
rows=[]
for y in range(2016,2026):
    for mid_s in feeds.inn['seasons'].get(str(y),{}):
        mid=int(mid_s)
        a=feeds.primary_position(mid,y); b=feeds.primary_position(mid,y+1)
        if a is None or b is None or a==b: continue
        if a not in pf.OAA_POSITIONS or b not in pf.OAA_POSITIONS: continue
        k1,k2=f'{mid}:{y}',f'{mid}:{y+1}'
        if k1 not in dh or k2 not in dh or dh[k1]['pa']<300 or dh[k2]['pa']<300: continue
        r1,r2=obs.get((mid,y)),obs.get((mid,y+1))
        if not r1 or not r2 or a not in r1 or b not in r2: continue
        if r1[a]['inn']<200 or r2[b]['inn']<200: continue
        z=shrunk_z(r1)
        def bf(k): return (dh[k]['war_def']*RPW-dh[k]['runs_position'])/dh[k]['pa']*650.0
        def lp(k): return dh[k]['runs_position']/dh[k]['pa']*650.0
        rows.append(dict(mid=mid,y=y,a=a,b=b,z=z,
            d_bref_field=bf(k2)-bf(k1),
            d_bref_lad=lp(k2)-lp(k1),
            d_bref_tot=(bf(k2)+lp(k2))-(bf(k1)+lp(k1)),
            d_savant=(r2[b]['rate']-r1[a]['rate'])*C,
            pred=(D[b]-D[a])*C+(lad[b]-lad[a])+(sig[b]-sig[a])*z*C,
            pred_field=(D[b]-D[a])*C+(sig[b]-sig[a])*z*C,
            pred_lad=lad[b]-lad[a]))
print(f'\n=== Q2  n={len(rows)} movers. Does the FIELDING side move to offset the ladder? ===')
print('  move      n   dLADDER(bref)  dFIELD(bref)   dFIELD(savant)  model dFIELD')
g=defaultdict(list)
for r in rows: g[(r['a'],r['b'])].append(r)
for (a,b),s in sorted(g.items(),key=lambda kv:-len(kv[1])):
    if len(s)<12: continue
    print(f'  {a}->{b:3s} {len(s):4d}   {statistics.mean(r["d_bref_lad"] for r in s):+8.2f}      '
          f'{statistics.mean(r["d_bref_field"] for r in s):+8.2f}       '
          f'{statistics.mean(r["d_savant"] for r in s):+8.2f}      '
          f'{statistics.mean(r["pred_field"] for r in s):+8.2f}')

# --- Q3 paired bootstrap: model vs zero-change on BRef TOTAL
print('\n=== Q3  paired bootstrap, target = actual change in BRef TOTAL def runs/650PA ===')
rng=random.Random(9); n=len(rows)
def mae(rs,k): return statistics.mean(abs((r[k] if k else 0.0)-r['d_bref_tot']) for r in rs)
base={'model':'pred','ladder_only':'pred_lad','zero':None}
pt={k:mae(rows,v) for k,v in base.items()}
print('  point MAE:', {k:round(v,3) for k,v in pt.items()})
d_zero=[];d_lad=[]
for _ in range(2000):
    pick=[rows[rng.randrange(n)] for _ in range(n)]
    m=mae(pick,'pred'); d_zero.append(mae(pick,None)-m); d_lad.append(mae(pick,'pred_lad')-m)
for lbl,v in (('model advantage over ZERO-CHANGE',d_zero),('model advantage over LADDER-ONLY',d_lad)):
    print(f'  {lbl:36s} mean {np.mean(v):+7.3f}  CI95 [{np.percentile(v,2.5):+7.3f}, {np.percentile(v,97.5):+7.3f}]')
