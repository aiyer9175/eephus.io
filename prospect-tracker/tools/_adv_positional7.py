"""fit_ladder normalises innings shares by tot=sum(exposure), but tot only equals
pa*inn_per_pa when the DH residual is positive. For 53.5% of rows it is clamped to 0
and tot=fielded, so the regressor is mis-scaled. Refit with the algebraically correct
regressor inn_p/(pa*inn_per_pa) and an explicit (possibly negative-free) DH column."""
import json, statistics
import numpy as np
import positional_fit as pf
feeds=pf.Feeds(); pay=json.load(open('data/positional_fit.json'))
ship=pay['fit']['ladder']['values']; ipp=pay['fit']['ladder']['inn_per_pa']
LP=pf.LADDER_POSITIONS
rows=[]
for k,v in feeds.defhist.items():
    m,y=k.split(':')
    if v['pa']<200 or not (2000<=int(y)<=2026): continue
    byp=feeds.innings(m,y)
    if not byp: continue
    ex={p:float((byp.get(p) or {}).get('inn',0.0)) for p in LP}
    fielded=sum(ex[p] for p in LP if p!='DH')
    denom=v['pa']*ipp
    ex['DH']=max(0.0,denom-fielded)
    if denom<=0: continue
    rows.append(([ex[p]/denom for p in LP], v['runs_position']/v['pa']*650.0))
X=np.array([r[0] for r in rows]); yv=np.array([r[1] for r in rows])
b,*_=np.linalg.lstsq(X,yv,rcond=None)
r2=1-((yv-X@b)**2).sum()/((yv-yv.mean())**2).sum()
print(f'n={len(rows)}  R2={r2:.4f}  (shipped R2 {pay["fit"]["ladder"]["r2"]})')
print('  pos   shipped   correct-denominator   diff')
for i,p in enumerate(LP):
    print(f'  {p:3s}  {ship[p]:+8.2f}      {b[i]:+8.2f}        {b[i]-ship[p]:+7.2f}')
# what it does to the shipped headline move
C=ipp*650/1000.0; D=pay['fit']['difficulty']['values']
for a,bb in (('LF','1B'),('RF','1B'),('CF','LF'),('SS','2B')):
    old=(D[bb]-D[a])*C+ship[bb]-ship[a]
    new=(D[bb]-D[a])*C+b[LP.index(bb)]-b[LP.index(a)]
    print(f'  net {a}->{bb} for an average glove: shipped {old:+.2f}  ->  {new:+.2f}')
