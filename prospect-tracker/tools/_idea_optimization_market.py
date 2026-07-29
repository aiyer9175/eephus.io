"""Feasibility: assignment-market (Shapley-Shubik) equilibrium prices for the 2027 FA class.
Duals on the player-supply constraints = minimum competitive-equilibrium contract value."""
import json, math, collections, statistics
import numpy as np
from scipy.optimize import linprog

P=json.load(open('data/mlb_projections.json',encoding='utf-8'))
F=json.load(open('data/fa_class.json',encoding='utf-8'))
to={t['team']:t for t in P['team_outlook']}
DPW=F['dpw_usd']; DISC=0.09

POSG={'C':'C','1B':'COR','3B':'COR','DH':'COR','LF':'COR','RF':'COR','OF':'COR',
      '2B':'MID','SS':'MID','CF':'MID','SP':'SP','RP':'RP','TWP':'SP','P':'SP','H':'COR'}
SLOT={'C':2,'COR':5,'MID':4,'SP':5,'RP':7}   # roster slots per group

# depth chart -> displaced WAR at each team/group (the marginal slot)
byt=collections.defaultdict(lambda: collections.defaultdict(list))
for v in P['vets']:
    t=v.get('team'); g=POSG.get(v.get('pos'))
    if t and g and v.get('war'): byt[t][g].append(v['war'][0])
disp={}
for t in to:
    for g,k in SLOT.items():
        arr=sorted(byt[t][g],reverse=True)
        disp[(t,g)]=arr[k-1] if len(arr)>=k else 0.0

def lev(w,c=86.5,s=2.8):
    p=1/(1+math.exp(-(w-c)/s)); return 4*p*(1-p)

M=[m for m in F['members'] if m.get('warPath') and m.get('projGuar')]
orgs=sorted(to)
# willingness to pay: NPV of marginal wins x leverage-scaled $/WAR
def wtp(m,t):
    g=POSG.get(m['pos'],'COR')
    d=disp[(t,g)]
    L=lev(to[t]['wins'])
    yrs=m['warPath']
    val=0.0
    for j,w in enumerate(yrs):
        marg=max(0.0, w-d*(0.85**j))
        val += marg*DPW*(1.05**j)/((1+DISC)**j)
    return val*(0.55+0.9*L)     # leverage tilt: contenders pay more per win

n=len(M); T=len(orgs)
V=np.zeros((n,T))
for i,m in enumerate(M):
    for j,t in enumerate(orgs): V[i,j]=wtp(m,t)
print('players',n,'teams',T,'mean WTP $M',round(V.mean()/1e6,1),'max',round(V.max()/1e6,1))

# LP: max sum V_ij x_ij ; sum_j x_ij <= 1 (each player once); group slots per team
idx={}
cols=[]
for i in range(n):
    for j in range(T):
        idx[(i,j)]=len(cols); cols.append((i,j))
NC=len(cols)
obj=np.array([-V[i,j] for i,j in cols])
rowsA=[]; b=[]
for i in range(n):
    r=np.zeros(NC); 
    for j in range(T): r[idx[(i,j)]]=1.0
    rowsA.append(r); b.append(1.0)
grp=[POSG.get(m['pos'],'COR') for m in M]
OPEN={'C':1,'COR':2,'MID':2,'SP':2,'RP':3}   # how many open slots each team may fill from FA
for j in range(T):
    for g,k in OPEN.items():
        r=np.zeros(NC)
        for i in range(n):
            if grp[i]==g: r[idx[(i,j)]]=1.0
        rowsA.append(r); b.append(float(k))
A=np.array(rowsA); b=np.array(b)
res=linprog(obj,A_ub=A,b_ub=b,bounds=[(0,1)]*NC,method='highs')
print('LP status',res.status,res.message[:60],'obj $B',round(-res.fun/1e9,2))
duals=-res.ineqlin.marginals
p_player=duals[:n]          # competitive equilibrium price (rent to player)
u_team=duals[n:].reshape(T,len(OPEN))
matched=sum(1 for k,(i,j) in enumerate(cols) if res.x[k]>1e-6)
print('fractional/whole matches',matched, 'total mass',round(res.x.sum(),1))
# compare eq price to the market model's projGuar
rows=[]
for i,m in enumerate(M):
    if p_player[i]<=0: continue
    rows.append((m['name'],m['pos'],round(p_player[i]/1e6,1),round(m['projGuar']/1e6,1),
                 round(m['rational']/1e6,1) if m.get('rational') else None))
rows.sort(key=lambda z:-z[2])
print(f"\n{'player':>22}{'pos':>5}{'EQprice$M':>11}{'projGuar$M':>12}{'rational$M':>12}")
for r in rows[:20]: print(f"{r[0]:>22}{r[1]:>5}{r[2]:>11}{r[3]:>12}{str(r[4]):>12}")
print('\nn with positive eq price:',len(rows),'of',n)
from scipy.stats import spearmanr
a=[r[2] for r in rows]; bq=[r[3] for r in rows]
print('rho(eq_price, projGuar) =',round(spearmanr(a,bq).statistic,3))
print('median ratio eq/projGuar =',round(statistics.median([x/y for x,y in zip(a,bq) if y>0]),2))
