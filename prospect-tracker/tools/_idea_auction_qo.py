"""SCRATCH: heterogeneous QO tax -> does the low-tax bidder win more often?"""
import sys, json, sqlite3, math, collections, statistics
sys.path.insert(0,'.')
import numpy as np, fa_sources
payor={}
for y in range(2016,2027):
    try:
        for r in fa_sources.scrape_spotrac_tax(y):
            s=(r.get('payor_status_raw') or '').lower()
            payor[(r['team'],y)] = 0 if (not s or 'non' in s) else 1
    except Exception as e: print(y,e)
print("payor cells:", len(payor), "payor share:", round(np.mean(list(payor.values())),3))
c=sqlite3.connect('prospects.db')
rows=[json.loads(r[0]) for r in c.execute("select payload_json from fa_signings")]
d=[]
for r in rows:
    if not r.get('mlb_deal') or not r.get('to_team'): continue
    p=payor.get((r['to_team'], r['class_year']-1))
    if p is None: continue
    d.append({'qo':1 if r.get('qo') else 0,'payor':p,'g':r['guarantee_usd'],'y':r['class_year']})
print("matched signings:", len(d), "qo:", sum(x['qo'] for x in d))
# logit: payor ~ qo + log guarantee + winter FE
ys=sorted({x['y'] for x in d})
X=[];Y=[]
for x in d:
    fe=[1.0 if x['y']==t else 0.0 for t in ys[1:]]
    X.append([1.0, x['qo'], math.log(x['g']/1e6)]+fe); Y.append(x['payor'])
X=np.asarray(X); Y=np.asarray(Y)
from sklearn.linear_model import LogisticRegression
m=LogisticRegression(C=1e6,max_iter=2000).fit(X[:,1:],Y)
co=m.coef_[0]
print(f"logit coef on QO (payor as outcome, controls log$ + winter FE): {co[0]:+.3f}  OR={math.exp(co[0]):.2f}")
# bootstrap
bs=[]
rng=np.random.default_rng(3)
for _ in range(400):
    idx=rng.integers(0,len(Y),len(Y))
    try:
        mm=LogisticRegression(C=1e6,max_iter=1000).fit(X[idx,1:],Y[idx]); bs.append(mm.coef_[0][0])
    except Exception: pass
bs=np.array(bs); print(f"  bootstrap mean {bs.mean():+.3f} sd {bs.std():.3f} P(<0)={np.mean(bs<0):.3f}")
# raw table by guarantee bucket
for lo,hi,lab in ((0,10,'<10M'),(10,50,'10-50M'),(50,1e9,'>=50M')):
    g=[x for x in d if lo<=x['g']/1e6<hi]
    q=[x for x in g if x['qo']]; nq=[x for x in g if not x['qo']]
    if q: print(f"  {lab:8s} QO n={len(q):3d} payor-share {np.mean([x['payor'] for x in q]):.2f} | nonQO n={len(nq):4d} payor-share {np.mean([x['payor'] for x in nq]):.2f}")
