"""Endogenous replacement level: WAR of the marginal FA who clears the market at each position."""
import json, collections, statistics
F=json.load(open('data/fa_class.json',encoding='utf-8'))
P=json.load(open('data/mlb_projections.json',encoding='utf-8'))
POSG={'C':'C','1B':'COR','3B':'COR','DH':'COR','LF':'COR','RF':'COR','OF':'COR',
      '2B':'MID','SS':'MID','CF':'MID','SP':'SP','RP':'RP','TWP':'SP','P':'SP','H':'COR'}
SLOT={'C':2,'COR':6,'MID':4,'SP':5,'RP':8}
# demand: league-wide open slots at each group entering 2027 (slots minus contracted bodies)
byt=collections.defaultdict(lambda: collections.Counter())
for v in P['vets']:
    t=v.get('team'); g=POSG.get(v.get('pos'))
    if t and g: byt[t][g]+=1
open_slots=collections.Counter()
for t in byt:
    for g,k in SLOT.items(): open_slots[g]+=max(0, k-byt[t][g])
# supply: FA class WAR by group, weighted by enterProb
sup=collections.defaultdict(list)
for m in F['members']:
    g=POSG.get(m['pos'],'COR')
    if m.get('warY1') is not None: sup[g].append((m['warY1'], m.get('enterProb',1.0), m['name']))
print(f"{'grp':>5}{'openSlots':>11}{'FAsupply':>10}{'effSupply':>11}{'endogRepl':>11}{'top3':>40}")
for g in SLOT:
    arr=sorted(sup[g],reverse=True)
    eff=sum(p for _,p,_ in arr)
    k=open_slots[g]
    # walk down the supply curve in expected-body units until demand k is met
    cum=0.0; marg=None
    for w,p,nm in arr:
        cum+=p
        if cum>=k: marg=w; break
    if marg is None: marg=arr[-1][0] if arr else 0.0
    top=', '.join(f'{nm.split()[-1]} {w:.1f}' for w,_,nm in arr[:3])
    print(f"{g:>5}{k:>11}{len(arr):>10}{eff:>11.1f}{marg:>11.2f}   {top:>37}")
print()
print('Interpretation: endogRepl = WAR of the last FA needed to fill league demand at that group.')
print('A signing at group g is worth (war_i - endogRepl_g), NOT (war_i - 0).')
for g in SLOT:
    arr=sorted(sup[g],reverse=True)
    print(g,'FA supply WAR quantiles', [round(statistics.quantiles([w for w,_,_ in arr],n=4)[i],2) for i in range(3)] if len(arr)>3 else 'thin')
