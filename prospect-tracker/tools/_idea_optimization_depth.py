import json, collections, statistics
d=json.load(open('data/mlb_projections.json',encoding='utf-8'))
vets=d['vets']; pros=d['prospects']
print('vets w/ team', sum(1 for v in vets if v.get('team')), 'of', len(vets))
print('pos counter', collections.Counter(v.get('pos') for v in vets).most_common(20))
print('thru present', sum(1 for v in vets if v.get('thru')), 'aav present', sum(1 for v in vets if v.get('aav')))
# depth chart by team/pos for 2027
POSG={'C':'C','1B':'COR','3B':'COR','DH':'COR','LF':'COR','RF':'COR','OF':'COR',
      '2B':'MID','SS':'MID','CF':'MID','SP':'SP','RP':'RP','TWP':'SP'}
byt=collections.defaultdict(lambda: collections.defaultdict(list))
for v in vets:
    t=v.get('team'); p=POSG.get(v.get('pos'))
    if t and p and v.get('war'): byt[t][p].append((v['war'][0], v['name'], v.get('thru')))
SLOT={'C':1,'COR':4,'MID':3,'SP':5,'RP':6}
print(f"{'org':>4}", ''.join(f"{g:>16}" for g in SLOT))
rows=[]
for t in sorted(byt):
    line=[]
    for g,k in SLOT.items():
        arr=sorted(byt[t][g],reverse=True)
        marg = arr[k-1][0] if len(arr)>=k else 0.0   # WAR of the player displaced
        depth=len(arr)
        line.append(f"{marg:6.2f}/{depth:<3}")
        rows.append((g,marg))
    print(f"{t:>4}", ''.join(f"{x:>16}" for x in line))
print()
for g in SLOT:
    v=[m for gg,m in rows if gg==g]
    print(g,'displaced-WAR across 30 teams: min',round(min(v),2),'med',round(statistics.median(v),2),'max',round(max(v),2),'sd',round(statistics.pstdev(v),2))
