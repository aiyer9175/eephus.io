"""The primary validation uses sig (signal_sd, k_inn) and feas fit on ALL seasons
2016-2026 inside a per-season forward-chained loop. Re-run it with sig refit
strictly on seasons <= t."""
import json, statistics, random
import numpy as np
import positional_fit as pf

feeds=pf.Feeds()
obs_all=feeds.rates()
obs={k:{p:v for p,v in d.items() if v['inn']>=pf.MIN_PAIR_INN} for k,d in obs_all.items()}
obs={k:d for k,d in obs.items() if d}
sig_full=pf.fit_signal(obs)
print('=== F  sig fit on ALL seasons vs sig fit as-of each fold ===')
print('  pos   signal_sd(full)  k_inn(full) | as-of 2018 | as-of 2021 | as-of 2024')
asof={}
for t in (2018,2021,2024):
    asof[t]=pf.fit_signal({k:d for k,d in obs.items() if k[1]<=t})
for p in pf.OAA_POSITIONS:
    print(f'  {p:3s}  {sig_full[p]["signal_sd"]:7.3f} {sig_full[p]["k_inn"]:8.0f}  |'
          + ''.join(f' {asof[t][p]["signal_sd"]:6.3f}/{asof[t][p]["k_inn"]:6.0f} |' for t in (2018,2021,2024)))

def run(asof_sig):
    rng=random.Random(61); rows=[]
    for t in range(2017,2026):
        sig = pf.fit_signal({k:d for k,d in obs.items() if k[1]<=t}) if asof_sig else sig_full
        train={k:v for k,v in obs_all.items() if k[1]<=t}
        multi={k:d for k,d in train.items() if len(d)>=2}
        if len(multi)<100: continue
        beta=pf._solve_D(pf._pairs_from(multi)); Dt={p:float(beta[pf.IDX[p]]) for p in pf.OAA_POSITIONS}
        for (mid,s),row in obs_all.items():
            if s!=t: continue
            nxt=obs_all.get((mid,t+1))
            if not nxt: continue
            src={p:v for p,v in row.items() if v['inn']>=200.0}
            if not src: continue
            for b,nv in nxt.items():
                if nv['inn']<200.0 or b in src: continue
                prior=sum(obs_all.get((mid,y),{}).get(b,{}).get('inn',0.0) for y in range(t-2,t+1))
                if prior>50.0: continue
                a=max(src,key=lambda p:src[p]['inn'])
                z,_=pf._shrunk_z(src,Dt,sig)
                rows.append({'actual':nv['rate'],'season':t,
                    'model':Dt[b]+sig[b]['signal_sd']*z,'carry_over':src[a]['rate'],
                    'league_avg':Dt[b],'z':z,'to':b,'Dt':Dt,'sig':sig})
    for t in sorted({r['season'] for r in rows}):
        sub=[r for r in rows if r['season']==t]; zs=[r['z'] for r in sub]; rng.shuffle(zs)
        for r,zz in zip(sub,zs): r['permuted']=r['Dt'][r['to']]+r['sig'][r['to']]['signal_sd']*zz
    def mae(rs,k): return statistics.mean(abs(r[k]-r['actual']) for r in rs)
    n=len(rows); out={'n':n,**{k:round(mae(rows,k),3) for k in ('model','carry_over','league_avg','permuted')}}
    for arm in ('carry_over','permuted','league_avg'):
        d=[]
        for _ in range(1000):
            pick=[rows[rng.randrange(n)] for _ in range(n)]
            d.append(mae(pick,arm)-mae(pick,'model'))
        out['adv_'+arm]=(round(float(np.mean(d)),3),[round(float(np.percentile(d,2.5)),3),round(float(np.percentile(d,97.5)),3)])
    return out

for lbl,flag in (('sig fit on ALL seasons (as shipped)',False),('sig refit as-of each fold',True)):
    r=run(flag)
    print(f'\n  {lbl}:  n={r["n"]}')
    print(f'    MAE model {r["model"]}  carry_over {r["carry_over"]}  league_avg {r["league_avg"]}  permuted {r["permuted"]}')
    for a in ('carry_over','permuted','league_avg'):
        m,ci=r['adv_'+a]; print(f'    advantage over {a:11s} {m:+.3f}  CI95 [{ci[0]:+.3f}, {ci[1]:+.3f}]  {"BEATS" if ci[0]>0 else "NULL"}')
