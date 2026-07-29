import json, statistics
import numpy as np
import positional_fit as pf
feeds=pf.Feeds()
pay=json.load(open('data/positional_fit.json')); f=pay['fit']
ipp=f['ladder']['inn_per_pa']
over=0; tot=0; big=0
for k,v in feeds.defhist.items():
    m,y=k.split(':')
    if v['pa']<200 or not (2000<=int(y)<=2026): continue
    byp=feeds.innings(m,y)
    if not byp: continue
    fielded=sum(float((byp.get(p) or {}).get('inn',0.0)) for p in pf.LADDER_POSITIONS if p!='DH')
    tot+=1
    if fielded> v['pa']*ipp:
        over+=1
        if fielded > v['pa']*ipp*1.15: big+=1
print(f'=== G  ladder-fit rows where fielded innings EXCEED pa*inn_per_pa (DH clamped to 0) ===')
print(f'  {over}/{tot} rows ({100*over/tot:.1f}%), of which >15% over: {big}')
print('  For those rows the innings SHARES no longer scale to the pa-normalised target,')
print('  so the regression absorbs a per-row exposure error into the rungs.')

print('\n=== H  pitcher innings are excluded from `fielded` but NOT from the DH residual ===')
tw=[k for k,v in feeds.defhist.items() if v['pa']>=200 and (feeds.innings(*k.split(":")).get("P") or {}).get("inn",0)>50]
print(f'  two-way rows (>50 P innings, >=200 PA) in the ladder fit: {len(tw)}')
for k in tw[:5]:
    m,y=k.split(':'); b=feeds.innings(m,y)
    pi=b['P']['inn']; fl=sum(v['inn'] for p,v in b.items() if p not in ('P','DH'))
    print(f'    {feeds.names.get(m,m)} {y}: P inn={pi:.0f} fielded={fl:.0f} pa={feeds.defhist[k]["pa"]:.0f}'
          f' -> DH residual={max(0,feeds.defhist[k]["pa"]*ipp-fl):.0f} (P innings counted as DH)')

print('\n=== I  None / zero-division paths ===')
sig=f['signal']
print('  positions with fallback signal_sd (=4.0) or k_inn (=1200):',
      [p for p in pf.OAA_POSITIONS if sig[p].get('obs_sd') is None])
z=[r for r in pay['players'] if r['glove_z_se'] is not None]
print(f'  glove_z_se range: {min(r["glove_z_se"] for r in z):.3f} .. {max(r["glove_z_se"] for r in z):.3f}')
print(f'  rows with current_pos None: {sum(1 for r in pay["players"] if r["current_pos"] is None)}')
print(f'  rows with gain_se None but gain not None: '
      f'{sum(1 for r in pay["players"] if r["gain_se"] is None and r["gain_runs_per_650"] is not None)}')
