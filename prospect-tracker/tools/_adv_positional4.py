import json, statistics
import positional_fit as pf
pay=json.load(open('data/positional_fit.json'))
feeds=pf.Feeds()
print('=== C  does the DH mislabel contaminate the SHIPPED lists? ===')
rows={r['mlbam']:r for r in pay['players']}
def fldinn(mid,ts):
    b=feeds.innings(mid,ts); return sum(v['inn'] for p,v in b.items() if p!='P')
def dhg(mid,ts):
    b=feeds.innings(mid,ts); return (b.get('DH') or {}).get('g',0)
ts=pay['target_season']
bad=[]
for lst in ('top_demotions','top_misplaced'):
    for r in pay[lst]:
        fi=fldinn(r['mlbam'],ts); dg=dhg(r['mlbam'],ts)
        if dg>=fi/9.0*0.5 and dg>=15:
            bad.append((lst,r['name'],r['current_pos'],round(fi),dg,r.get('demotion_pos'),r.get('demotion_gain')))
print(f'  headline rows whose DH games rival their fielding starts: {len(bad)}')
for b in bad[:12]: print('   ',b)

print('\n=== D  who is scored at all with almost no defensive exposure this season? ===')
thin=[r for r in pay['players'] if r.get('qualified') and not r['c_out_of_scope']
      and sum(r['innings'].values())<200]
print(f'  qualified rows with <200 fielding innings in {ts}: {len(thin)}')
print(f'  ...of which flagged_demotion: {sum(1 for r in thin if r["flagged_demotion"])}')
for r in sorted(thin,key=lambda r:-(r["demotion_gain"] or -99))[:8]:
    print(f'    {r["name"][:24]:24s} pos={r["current_pos"]} inn={sum(r["innings"].values()):6.1f} '
          f'pa={r["pa"]} dem={r["demotion_pos"]} gain={r["demotion_gain"]} flagged={r["flagged_demotion"]}')

print('\n=== E  composition of the shipped demotion list ===')
from collections import Counter
c=Counter((r['current_pos'],r['demotion_pos']) for r in pay['top_demotions'])
print(' ',dict(c))
lp=[r['demotion_gain_league_part'] for r in pay['top_demotions'] if r.get('demotion_gain_league_part') is not None]
pp=[r['demotion_gain_player_part'] for r in pay['top_demotions'] if r.get('demotion_gain_player_part') is not None]
print(f'  league-wide (unvalidated constant) part: mean {statistics.mean(lp):+.2f}  of total mean '
      f'{statistics.mean(r["demotion_gain"] for r in pay["top_demotions"]):+.2f}')
print(f'  player-specific part: mean {statistics.mean(pp):+.2f}')
print(f'  rows where the player part ALONE would clear the {pf.FLAG_MIN_GAIN}-run flag: '
      f'{sum(1 for x in pp if x>=pf.FLAG_MIN_GAIN)}/{len(pp)}')
