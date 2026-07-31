"""SCRATCH: can we get a usable bidder-count from the served fit matrix?"""
import json, math, statistics, collections
d=json.load(open('data/fa_class.json'))
mem=d['members']; tf=d['teamFits']
byp=collections.defaultdict(dict)
for org,rows in tf.items():
    for r in rows: byp[r['i']][org]=r['fit']
print("players with fit rows:", len(byp), "of", len(mem))
print("orgs per player:", collections.Counter(len(v) for v in byp.values()).most_common(5))
def neff(fits, tau):
    mx=max(fits)
    w=[math.exp((f-mx)/tau) for f in fits]
    s=sum(w); p=[x/s for x in w]
    return 1.0/sum(x*x for x in p)
for tau in (0.02,0.05,0.10):
    vals=[]
    for i,v in byp.items():
        f=list(v.values())
        if len(f)>=20: vals.append((neff(f,tau), mem[i]['name'], mem[i].get('pos'), mem[i].get('projAav')))
    ns=[x[0] for x in vals]
    print(f"tau={tau}: n={len(ns)} Neff mean {statistics.mean(ns):.1f} sd {statistics.pstdev(ns):.1f} min {min(ns):.1f} max {max(ns):.1f}")
    vals.sort()
    print("  thinnest:", [(n.split()[-1],p,round(x,1)) for x,n,p,_ in vals[:5]])
    print("  thickest:", [(n.split()[-1],p,round(x,1)) for x,n,p,_ in vals[-5:]])
# by position group
tau=0.05
g=collections.defaultdict(list)
for i,v in byp.items():
    f=list(v.values())
    if len(f)>=20: g[mem[i].get('pos')].append(neff(f,tau))
for pos,v in sorted(g.items(), key=lambda kv:-len(kv[1]))[:12]:
    print(f"  {pos:6s} n={len(v):3d} Neff {statistics.mean(v):.1f}")
