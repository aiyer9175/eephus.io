"""Find the exact n=66 stratum the mechanism lane used, then test the scale basis."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import efv_model as em

M = json.load(open('data/xfv_hitter_matrix.json'))
X = json.load(open('data/xfv.json'))['by_player']
rows = []
for r in M:
    try: d = em._vec(r, 'hit')
    except Exception: continue
    rows.append((r, d))

def build(resolved_only, agemin, need_xfv=True):
    out = []
    for r, d in rows:
        if resolved_only and not r.get('target_resolved'): continue
        if d.get('level_rank') != 5.0: continue
        a = d.get('age')
        if a is None or a < agemin: continue
        o = d.get('ops_rel')
        if o is None or o >= 0: continue
        x = X.get(r['player_key'])
        if need_xfv and (not x or x.get('xfv_grade') is None or x.get('consensus_fv') is None):
            continue
        out.append((r, d, x))
    return out

for res in (True, False):
    for agemin in (23.5,):
        s = build(res, agemin)
        if not s: continue
        n = len(s)
        mc = sum(x['consensus_fv'] for _,_,x in s)/n
        mg = sum(x['xfv_grade'] for _,_,x in s)/n
        mr = sum(x['xfv_grade_realized'] for _,_,x in s)/n
        print('resolved_only=%s n=%d  mean_cons %.4f  mean SERVED grade %.4f (prem %.4f)  mean PRE-scale %.4f (prem %.4f)'
              % (res, n, mc, mg, mg-mc, mr, mr-mc))

print()
print('=== THE SWING, ON EACH BASIS ===')
b = X['enrique_bradfield_jr']
for res in (True, False):
    s = build(res, 23.5)
    n=len(s)
    mc = sum(x['consensus_fv'] for _,_,x in s)/n
    mg = sum(x['xfv_grade'] for _,_,x in s)/n
    mr = sum(x['xfv_grade_realized'] for _,_,x in s)/n
    print('resolved_only=%s n=%d' % (res, n))
    print('   MIXED  (Brad PRE-scale  vs stratum SERVED): %.3f' % ((b['xfv_grade_realized']-b['consensus_fv']) - (mg-mc)))
    print('   consistent SERVED                         : %.3f' % ((b['xfv_grade']-b['consensus_fv']) - (mg-mc)))
    print('   consistent PRE-scale                      : %.3f' % ((b['xfv_grade_realized']-b['consensus_fv']) - (mr-mc)))
