"""Feasibility probe: per-team FA knapsack LP with dual extraction (shadow prices)."""
import json, sqlite3, collections, sys
import numpy as np
from scipy.optimize import linprog

D=json.load(open('data/fa_class.json',encoding='utf-8'))
M=[m for m in D['members'] if m.get('warY1') is not None and m.get('projAav')]
print('members priced', len(M))

c=sqlite3.connect('prospects.db')
pay={}
for t,s,p in c.execute("select team,season,payload_json from fa_team_payroll where season=2027"):
    pay[t]=json.loads(p)
print('payroll rows 2027', len(pay), list(pay.items())[:1])

THR=244_000_000
def space(org):
    r=pay.get(org) or {}
    s=r.get('space_usd')
    if s is None:
        s=THR-(r.get('tax_payroll_usd') or r.get('total_payroll_usd') or 0)
    return float(s)

POSG={'SP':'SP','RP':'RP','C':'C','1B':'COR','3B':'COR','DH':'COR','LF':'COR','RF':'COR',
      '2B':'MID','SS':'MID','CF':'MID','OF':'COR','P':'SP'}
# Per-team LP:  max sum_i v_i x_i   s.t.  sum_i aav_i x_i <= space,  sum_{i in g} x_i <= slots_g,  0<=x<=1
SLOTS={'SP':2,'RP':3,'C':1,'COR':2,'MID':2}
orgs=sorted(pay)
res_rows=[]
for org in orgs:
    sp=space(org)
    if sp<=0: sp=5_000_000   # habitual-taxpayer floor placeholder
    v=[]; a=[]; g=[]
    for m in M:
        # value = marginal wins x $/WAR proxy, net of price -> surplus objective
        v.append(float(m.get('surplus') or 0))
        a.append(float(m['projAav']))
        g.append(POSG.get(m['pos'],'COR'))
    n=len(M)
    A=[a]; b=[sp]
    for grp in SLOTS:
        A.append([1.0 if gi==grp else 0.0 for gi in g]); b.append(float(SLOTS[grp]))
    r=linprog(c=[-x for x in v], A_ub=np.array(A), b_ub=np.array(b),
              bounds=[(0,1)]*n, method='highs')
    if not r.success: print(org,'FAIL',r.message); continue
    duals=-r.ineqlin.marginals   # >=0
    res_rows.append({'org':org,'space_musd':round(sp/1e6),'obj_musd':round(-r.fun/1e6,1),
                     'dual_payroll_per_musd':round(duals[0]*1e6,3),
                     **{f'dual_{k}':round(duals[1+i]/1e6,2) for i,k in enumerate(SLOTS)},
                     'nsel':round(float(sum(r.x)),1)})
import statistics
print(f"{'org':>4}{'space':>7}{'obj':>8}{'$/$':>7}", ''.join(f'{k:>7}' for k in SLOTS),f"{'nsel':>6}")
for rr in sorted(res_rows,key=lambda z:-z['dual_payroll_per_musd']):
    print(f"{rr['org']:>4}{rr['space_musd']:>7}{rr['obj_musd']:>8.1f}{rr['dual_payroll_per_musd']:>7.2f}",
          ''.join(f"{rr['dual_'+k]:>7.1f}" for k in SLOTS), f"{rr['nsel']:>6.1f}")
dp=[r['dual_payroll_per_musd'] for r in res_rows]
print('payroll shadow price: min',round(min(dp),3),'med',round(statistics.median(dp),3),'max',round(max(dp),3))
for k in SLOTS:
    v=[r['dual_'+k] for r in res_rows]
    print('slot dual',k,'min',round(min(v),2),'med',round(statistics.median(v),2),'max',round(max(v),2),'($M per extra slot)')
