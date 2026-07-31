import sys, collections, random, math
sys.path.insert(0,'.')
import numpy as np, fa_sources, fa_cba
rows=[]
for y in range(2017,2027):
    thr=fa_cba.cbt_threshold(y)["threshold_usd"]
    for r in fa_sources.scrape_spotrac_tax(y):
        v=r.get("tax_payroll_usd")
        if v: rows.append((v-thr)/thr)
rows=np.array(rows)
W=0.02  # bin width in normalized units
lo,hi=-0.35,0.35
edges=np.arange(lo,hi+W,W)
cnt,_=np.histogram(rows,bins=edges)
mid=(edges[:-1]+edges[1:])/2
excl=(mid>=-0.06)&(mid<0.02)
def excess(cnt):
    X=np.vander(mid[~excl],5)
    b=np.linalg.lstsq(X,cnt[~excl],rcond=None)[0]
    cf=np.vander(mid,5)@b
    return (cnt[excl]-cf[excl]).sum()/max(cf[excl].mean(),1e-9), cf
b,cf=excess(cnt)
print(f"n={len(rows)} bins={len(cnt)} excess mass b={b:.2f} bin-widths")
for m,c,f in zip(mid,cnt,cf):
    if -0.2<=m<=0.2: print(f"{m*100:+6.1f}%  n={c:3d}  cf={f:5.1f} {'*' if (-0.06<=m<0.02) else ''}")
# bootstrap
bs=[]
rng=np.random.default_rng(7)
for _ in range(2000):
    s=rng.choice(rows,size=len(rows),replace=True)
    c,_=np.histogram(s,bins=edges)
    bs.append(excess(c)[0])
bs=np.array(bs)
print(f"bootstrap b mean {bs.mean():.2f} sd {bs.std():.2f} p(b<=0)={np.mean(bs<=0):.3f} CI95 [{np.percentile(bs,2.5):.2f},{np.percentile(bs,97.5):.2f}]")
