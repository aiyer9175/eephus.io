"""SCRATCH: can StatsAPI transactions date the FA signings corpus?"""
import json, sqlite3, collections, statistics, datetime
p=r'C:\Users\noah\AppData\Local\Temp\claude\c--Users-noah-baseball-projects-BaseballR\c6ce73e3-6700-473f-beea-01f160967961\scratchpad\tx25.json'
tx=json.load(open(p,encoding='utf-8'))['transactions']
sg={}
for t in tx:
    if 'Sign' not in (t.get('typeDesc') or ''): continue
    pid=(t.get('person') or {}).get('id')
    if pid and pid not in sg:
        sg[pid]={'date':t['date'],'desc':t.get('description',''),
                 'major': 'minor league' not in (t.get('description') or '').lower()}
print("dated FA signings 2024-10-25..2025-04-01:", len(sg), "major-league:", sum(1 for v in sg.values() if v['major']))
c=sqlite3.connect('prospects.db')
rows=[json.loads(r[0]) for r in c.execute("select payload_json from fa_signings where class_year=2025")]
mlb=[r for r in rows if r.get('mlb_deal') and r.get('mlbam_id')]
hit=[r for r in mlb if r['mlbam_id'] in sg]
print(f"class 2025 mlb deals w/ mlbam: {len(mlb)}  matched to a date: {len(hit)} ({len(hit)/len(mlb):.0%})")
for r in sorted(hit, key=lambda r:-r['guarantee_usd'])[:8]:
    print(f"  {sg[r['mlbam_id']]['date']}  ${r['guarantee_usd']/1e6:7.1f}M  {r['player_name']}")
d=[datetime.date.fromisoformat(sg[r['mlbam_id']]['date']) for r in hit]
print("date range", min(d), max(d))
big=[(datetime.date.fromisoformat(sg[r['mlbam_id']]['date']), r['guarantee_usd']) for r in hit]
early=[g for dt,g in big if dt<datetime.date(2025,1,1)]; late=[g for dt,g in big if dt>=datetime.date(2025,1,1)]
print(f"signed before Jan1 n={len(early)} median ${statistics.median(early)/1e6:.1f}M | after n={len(late)} median ${statistics.median(late)/1e6:.1f}M")

# --- crude quality-controlled check: does late signing predict lower price? ---
import math
import numpy as np
X=[];y=[];names=[]
for r in hit:
    led=r.get('ledger') or {}
    ey=led.get('elapsed_years') or 0
    if not ey or led.get('war_to_date') is None: continue
    wpy=led['war_to_date']/ey
    dt=(datetime.date.fromisoformat(sg[r['mlbam_id']]['date'])-datetime.date(2024,11,1)).days
    aav=r.get('aav_usd') or r['guarantee_usd']/max(r['years'],1)
    X.append([1.0,wpy,wpy*wpy,float(r['years']),dt/30.0]); y.append(math.log(aav)); names.append(r['player_name'])
X=np.asarray(X); y=np.asarray(y)
b,*_=np.linalg.lstsq(X,y,rcond=None)
res=y-X@b
se=math.sqrt(((res@res)/(len(y)-X.shape[1]))*np.linalg.inv(X.T@X)[4,4])
print(f"\nn={len(y)}  coef on months-since-Nov1 = {b[4]:+.3f} log-$ (se {se:.3f}, t {b[4]/se:+.2f})")
print(f"  => each month unsigned ~ {100*(math.exp(b[4])-1):+.1f}% AAV, controlling for realized WAR/yr, WAR^2, term")
