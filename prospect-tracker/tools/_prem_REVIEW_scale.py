"""REVIEW LAB: which grade scale is each lane's 'premium' computed on?
Reproduces the n=66 stratum and recomputes the 12.15 FV swing on BOTH scales."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import efv_model as em

M = json.load(open('data/xfv_hitter_matrix.json'))
X = json.load(open('data/xfv.json'))['by_player']

print('_FEATURES_HIT =', em._FEATURES_HIT)

rows = []
for r in M:
    try:
        d = em._vec(r, 'hit')
    except Exception as e:
        continue
    rows.append((r, d))
print('vectorized', len(rows))

names = em._FEATURES_HIT
def get(d, k):
    return d.get(k)

# stratum: AAA (level_rank 5), age >= 23.5, ops_rel < 0, RESOLVED
strat = []
for r, d in rows:
    if not r.get('target_resolved'):
        continue
    if get(d,'level_rank') != 5.0:
        continue
    if get(d,'age') is None or get(d,'age') < 23.5:
        continue
    if get(d,'ops_rel') is None or get(d,'ops_rel') >= 0:
        continue
    key = r['player_key']
    x = X.get(key)
    if not x: continue
    if x.get('xfv_grade') is None or x.get('consensus_fv') is None: continue
    strat.append((key, x))

print()
print('STRATUM n =', len(strat))
if strat:
    gs  = [x['xfv_grade'] for _,x in strat]
    grs = [x['xfv_grade_realized'] for _,x in strat if x.get('xfv_grade_realized') is not None]
    cs  = [x['consensus_fv'] for _,x in strat]
    chips = [x['xfv_minus_consensus'] for _,x in strat if x.get('xfv_minus_consensus') is not None]
    n=len(strat)
    print('  mean consensus_fv        %.4f' % (sum(cs)/n))
    print('  mean xfv_grade (SERVED)  %.4f' % (sum(gs)/n))
    print('  mean xfv_grade_realized  %.4f  (n=%d)' % (sum(grs)/len(grs), len(grs)))
    print('  mean premium on SERVED   %.4f' % (sum(g-c for g,c in zip(gs,cs))/n))
    print('  mean premium PRE-scale   %.4f' % (sum(chips)/len(chips)))

b = X['enrique_bradfield_jr']
print()
print('BRADFIELD')
print('  served xfv_grade %.4f   pre-scale realized %.4f   consensus %.4f'
      % (b['xfv_grade'], b['xfv_grade_realized'], b['consensus_fv']))
print('  premium SERVED    %.4f' % (b['xfv_grade']-b['consensus_fv']))
print('  premium PRE-scale %.4f' % (b['xfv_grade_realized']-b['consensus_fv']))
