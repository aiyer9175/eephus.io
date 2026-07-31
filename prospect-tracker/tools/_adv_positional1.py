"""Does the model's predicted change in TOTAL defensive value match BRef's actual
change for players who really changed position? This is the claim the lane ships
(V = bat + FIELD(p) + LADDER(p)) and never validated end to end."""
import json, math, statistics, random
import numpy as np
import positional_fit as pf

feeds = pf.Feeds()
pay = json.load(open('data/positional_fit.json'))
f = pay['fit']
lad = f['ladder']['values']; D = f['difficulty']['values']
sig = {k: v['signal_sd'] for k, v in f['signal'].items()}
kinn = {k: v['k_inn'] for k, v in f['signal'].items()}
C = f['ladder']['inn_per_pa'] * 650.0 / 1000.0   # per-1000-inn -> per-650-PA
obs = feeds.rates()
dh = feeds.defhist

# estimate BRef runs-per-win implied by the file: war_def*RPW - runs_position should be
# the fielding-only runs. Try a grid and score correlation with Savant FRP.
best=None
for RPW in (9.0,9.5,9.7,10.0,10.3):
    xs,ys=[],[]
    for k,v in dh.items():
        m,y=k.split(':')
        if v['pa']<300: continue
        r=obs.get((int(m),int(y)))
        if not r: continue
        frp=sum(x['frp'] for x in r.values())
        xs.append(v['war_def']*RPW - v['runs_position']); ys.append(frp)
    c=float(np.corrcoef(xs,ys)[0,1])
    if best is None or c>best[1]: best=(RPW,c)
    print(f'  RPW={RPW}: corr(bref fielding runs, savant FRP) = {c:.4f}  n={len(xs)}')
RPW=best[0]; print('using RPW', RPW)

def bref_def650(k):
    v=dh[k]; return v['war_def']*RPW/v['pa']*650.0

def shrunk_z(row):
    num=den=0.0
    for p,rec in row.items():
        if sig[p]<=0 or kinn[p]<=0: continue
        num += rec['inn']/kinn[p] * (rec['rate']-D[p])/sig[p]; den += rec['inn']/kinn[p]
    return num/(1.0+den)

rows=[]
for y in range(2016,2026):
    for mid_s, byp in feeds.inn['seasons'].get(str(y),{}).items():
        mid=int(mid_s)
        a=feeds.primary_position(mid,y); b=feeds.primary_position(mid,y+1)
        if a is None or b is None or a==b: continue
        if a not in pf.OAA_POSITIONS or b not in pf.OAA_POSITIONS: continue
        k1,k2=f'{mid}:{y}',f'{mid}:{y+1}'
        if k1 not in dh or k2 not in dh: continue
        if dh[k1]['pa']<300 or dh[k2]['pa']<300: continue
        r1=obs.get((mid,y))
        if not r1: continue
        z=shrunk_z(r1)
        pred = (D[b]-D[a])*C + (lad[b]-lad[a]) + (sig[b]-sig[a])*z*C
        base = (D[b]-D[a])*C + (lad[b]-lad[a])          # avg-glove part
        ladonly = lad[b]-lad[a]
        act = bref_def650(k2)-bref_def650(k1)
        rows.append(dict(mid=mid,y=y,a=a,b=b,z=z,pred=pred,base=base,lad=ladonly,act=act))

print(f'\nn movers (both seasons >=300 PA, both positions OAA-covered) = {len(rows)}')
def mae(rs,k): return statistics.mean(abs(r[k]-r['act']) for r in rs)
for k,lbl in (('pred','model full'),('base','model avg-glove'),('lad','ladder only'),):
    print(f'  MAE {lbl:18s} {mae(rows,k):7.3f}   bias(pred-act) {statistics.mean(r[k]-r["act"] for r in rows):+7.3f}')
print(f'  MAE {"zero change":18s} {statistics.mean(abs(r["act"]) for r in rows):7.3f}')
print(f'  corr(pred, act) = {float(np.corrcoef([r["pred"] for r in rows],[r["act"] for r in rows])[0,1]):.4f}')
print(f'  corr(ladderonly, act) = {float(np.corrcoef([r["lad"] for r in rows],[r["act"] for r in rows])[0,1]):.4f}')

print('\nBY MOVE (n>=15): predicted vs actual change in TOTAL def runs per 650 PA')
from collections import defaultdict
g=defaultdict(list)
for r in rows: g[(r['a'],r['b'])].append(r)
rng=random.Random(5)
for (a,b),sub in sorted(g.items(), key=lambda kv:-len(kv[1])):
    if len(sub)<15: continue
    act=[r['act'] for r in sub]
    bs=[statistics.mean([act[rng.randrange(len(act))] for _ in act]) for _ in range(2000)]
    lo,hi=np.percentile(bs,2.5),np.percentile(bs,97.5)
    pm=statistics.mean(r['pred'] for r in sub)
    inside = lo<=pm<=hi
    print(f'  {a}->{b:3s} n={len(sub):3d}  pred {pm:+7.2f}  actual {statistics.mean(act):+7.2f} '
          f'CI[{lo:+6.2f},{hi:+6.2f}]  {"ok" if inside else "MISS"}')
