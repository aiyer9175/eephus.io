import json, statistics, random
import numpy as np
import positional_fit as pf

feeds=pf.Feeds()
obs_all=feeds.rates()
obs={k:{p:v for p,v in d.items() if v['inn']>=pf.MIN_PAIR_INN} for k,d in obs_all.items()}
obs={k:d for k,d in obs.items() if d}

# --- A: is the D used inside BOTH validations the SAME estimator as the shipped D?
mf={k:d for k,d in obs.items() if len(d)>=2}
mu={k:d for k,d in obs_all.items() if len(d)>=2}
bf=pf._solve_D(pf._pairs_from(mf)); bu=pf._solve_D(pf._pairs_from(mu))
print('=== A  shipped D is fit on innings>=100 pairs; both backtests refit on UNFILTERED pairs ===')
print(f'  n player-seasons: filtered {len(mf)}   unfiltered {len(mu)}')
print(f'  n pairs:          filtered {len(pf._pairs_from(mf))}   unfiltered {len(pf._pairs_from(mu))}')
print('  pos   D(filtered, shipped-style)   D(unfiltered, backtest-style)   diff')
for p in pf.OAA_POSITIONS:
    print(f'  {p:3s}      {bf[pf.IDX[p]]:+8.3f}                  {bu[pf.IDX[p]]:+8.3f}          {bu[pf.IDX[p]]-bf[pf.IDX[p]]:+7.3f}')

# --- B: does DH ever carry innings? can the label see a move to DH?
se=feeds.inn['seasons']
dh_inn=[v['DH']['inn'] for y in se for v in se[y].values() if 'DH' in v]
print(f'\n=== B  DH rows in fielding_innings: {len(dh_inn)}, max innings={max(dh_inn)}, nonzero={sum(1 for x in dh_inn if x>0)}')
# how many "regulars" are mostly-DH but get labelled by scrap fielding innings?
n_dh_heavy=0; ex=[]
for y in ('2024','2025'):
    for mid,byp in se[y].items():
        g_dh=(byp.get('DH') or {}).get('g',0)
        fld=sum(v['inn'] for p,v in byp.items() if p not in ('P','DH'))
        if g_dh>=60 and 0<fld<400:
            n_dh_heavy+=1
            if len(ex)<6: ex.append((feeds.names.get(mid,mid),y,g_dh,round(fld),pf.Feeds.primary_position(feeds,mid,int(y))))
print(f'  players with >=60 DH games and <400 fielding innings in 2024-25: {n_dh_heavy}')
print('  examples (name, season, DH games, fielding innings, label primary_position):')
for e in ex: print('   ',e)
print('  -> primary_position(exclude_dh=True) NEVER returns DH, so "moved to DH" -- the single')
print('     most common real demotion -- can never be a positive label in backtest().')
