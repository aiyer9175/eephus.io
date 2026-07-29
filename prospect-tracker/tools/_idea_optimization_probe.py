import collections, json, statistics, sys
sys.path.insert(0,'.')
import spotrac
from spotrac import _SPOTRAC_TEAM_SLUGS
slug2org={s:c for c,s in _SPOTRAC_TEAM_SLUGS.items()}
rows=spotrac.scrape_all_spotrac_contracts()
comm=collections.defaultdict(lambda: collections.defaultdict(int))
npl=collections.defaultdict(lambda: collections.Counter())
for r in rows:
    org=slug2org.get(r['team_slug'])
    for y,s in (r['salary_by_year'] or {}).items():
        comm[org][int(y)]+=int(s); npl[org][int(y)]+=1
years=sorted({y for o in comm for y in comm[o]})
print('years',years)
print(f"{'org':>4}", ' '.join(f'{y:>7}' for y in years[:8]))
for o in sorted(comm):
    print(f"{o:>4}", ' '.join(f"{comm[o].get(y,0)/1e6:7.0f}" for y in years[:8]))
print()
print('n contracted players by year:')
for y in years[:8]:
    v=[npl[o].get(y,0) for o in comm]
    print(y,'total',sum(v),'mean/team',round(statistics.mean(v),1),'min',min(v),'max',max(v))
# spread of 2028+ commitments
for y in [2027,2028,2029,2030]:
    v=sorted((comm[o].get(y,0)/1e6) for o in comm)
    print(y,'min',round(v[0]),'med',round(statistics.median(v)),'max',round(v[-1]),'sd',round(statistics.pstdev(v)))
