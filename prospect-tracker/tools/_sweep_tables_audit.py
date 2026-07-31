"""Lane TABLES: re-derivation / verification of the remaining hand-set constants."""
import sys, pathlib, json, math, statistics as st, random
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import efv_model as em, efv_ungraded as eu, _sweep_tables_harness as H
from efv_dataset import matrix_path, live_matrix_path
LV=["DSL","CPX","A","A+","AA","AAA"]

def rows(side, live=False):
    return json.loads((live_matrix_path(side) if live else matrix_path(side)).read_text(encoding="utf-8"))

def boot_mean(v,B=3000,seed=3):
    rnd=random.Random(seed); n=len(v)
    s=sorted(sum(v[rnd.randrange(n)] for _ in range(n))/n for _ in range(B))
    return round(s[int(.025*B)],2), round(s[int(.975*B)],2)

print("="*78); print("1. _TOOL_IMPUTE  (claim: 'the measured train means')")
for side,tools in (("hit",("tool_hit","tool_speed","tool_game_pwr","tool_field","tool_raw_pwr","tool_throw")),
                   ("pit",("tool_fb","tool_cmd","tool_sl","tool_ch","tool_cb"))):
    tr=rows(side); li=rows(side,True)
    for t in tools:
        vt=[float(r[t]) for r in tr if r.get(t) is not None]
        vl=[float(r[t]) for r in li if r.get(t) is not None]
        cur = em._TOOL_IMPUTE.get(t, 45.0)
        ci=boot_mean(vt) if vt else None
        print(f"  {side} {t:14s} shipped_impute {cur:5.1f} | TRAIN mean {st.mean(vt):6.2f} CI{ci} n={len(vt)} "
              f"(miss {100*(1-len(vt)/len(tr)):5.1f}%) | LIVE mean {st.mean(vl):6.2f} n={len(vl)} (miss {100*(1-len(vl)/len(li)):5.1f}%)")

print("="*78); print("2. _N_MILB_SEASONS_CAP = 8.0  (claim: 'training max = 8 on both sides')")
for side in ("hit","pit"):
    tr=[float((r.get('milb') or {}).get('n_milb_seasons') or 0) for r in rows(side) if r.get('milb')]
    li=[float((r.get('milb') or {}).get('n_milb_seasons') or 0) for r in rows(side,True) if r.get('milb')]
    print(f"  {side}: TRAIN max {max(tr):.0f} p99 {sorted(tr)[int(.99*len(tr))]:.0f} | LIVE max {max(li):.0f} "
          f"share ABOVE cap {100*sum(1 for v in li if v>8)/len(li):5.2f}% (n={len(li)})")

print("="*78); print("3. _SHAPE_IMPUTE 38.9 / _DEPTH_IMPUTE 1.6 (claim: observed debuted-pool means)")
sh,dp=[],[]
for r in rows("pit"):
    obs=[float(v) for v in (r.get("tool_fb"),r.get("tool_sl"),r.get("tool_cb"),r.get("tool_ch")) if v is not None]
    if not obs: continue
    depth=sum(1 for v in obs if v>=55.0)
    ds={0:5.0,1:15.0,2:45.0,3:80.0}.get(depth,100.0)
    rc=r.get("tool_cmd"); cs=50.0 if rc is None else max(0.0,min(100.0,(float(rc)-40.0)/20.0*100.0))
    sh.append(round(0.60*ds+0.40*cs,1)); dp.append(float(depth))
print(f"  observed pit-pool (tool-bearing n={len(sh)}): starter_shape mean {st.mean(sh):.2f} CI{boot_mean(sh)} ; "
      f"arsenal_depth mean {st.mean(dp):.3f} CI{boot_mean(dp)}")

print("="*78); print("4. age imputes: efv_dataset base 23.0 vs efv_model._vec 22.5 (+ age_missing wiring)")
for side in ("hit","pit"):
    for lab,rs in (("TRAIN",rows(side)),("LIVE",rows(side,True))):
        wm=[r for r in rs if r.get("milb")]
        am=[r for r in wm if (r["milb"] or {}).get("age_missing")]
        ages=[float(r["milb"]["age"]) for r in wm if r["milb"].get("age") is not None]
        print(f"  {side} {lab}: rows with milb {len(wm)}, age_missing==1 -> {len(am)} "
              f"(dataset already substituted 23.0 into milb.age, so _vec's age_missing reads 0.0 and 22.5 is never used); "
              f"observed milb age mean {st.mean(ages):.2f} CI{boot_mean(ages)}")

print("="*78); print("5. _LEVEL_RANK 0..5 -- is the ladder equally spaced in OUTCOME? (positional-ladder precedent)")
import numpy as np
for side in ("hit","pit"):
    tr=[r for r in rows(side) if r.get("milb") and r.get("target_censored") is not None
        and not (r.get("kind")=="bust" and r.get("bust_recent"))]
    print(f"  {side}: n={len(tr)}")
    base=None
    for lv in LV:
        sub=[r for r in tr if r["milb"].get("milb_level")==lv]
        if len(sub)<25: print(f"    {lv:>4} n={len(sub):4d} (sparse)"); continue
        w=[float(r.get("weight",1.0)) for r in sub]; y=[float(r["target_censored"]) for r in sub]
        mw=sum(a*b for a,b in zip(w,y))/sum(w)
        pc=sum(b for a,b in zip(w,[1.0 if v>=3.0 else 0.0 for y_ in [y] for v in y_])*1 for a,b in [(0,0)]) if False else None
        pc=sum(a for a,v in zip(w,y) if v>=3.0)/sum(w)
        print(f"    {lv:>4} n={len(sub):4d} rank={LV.index(lv)} weighted mean 6yr WAR {mw:6.3f}  P(WAR>=3) {pc:5.3f}")

print("="*78); print("6. _GRADE_MAP BASE/SLOPE (provisional war->FV) re-derived from the labeled pool")
import numpy as np
for side in ("hit","pit"):
    gm=eu._GRADE_MAP[side]
    tr=[r for r in rows(side) if r.get("milb") and r.get("target_censored") is not None
        and not (r.get("kind")=="bust" and r.get("bust_recent")) and r.get("consensus_fv_raw") is not None]
    x=np.array([float(r["target_censored"]) for r in tr]); y=np.array([float(r["consensus_fv_raw"]) for r in tr])
    w=np.array([float(r.get("weight",1.0)) for r in tr])
    A=np.vstack([np.ones_like(x),x]).T
    W=np.diag(w); coef=np.linalg.solve(A.T@W@A, A.T@W@y)
    print(f"  {side}: shipped BASE {gm['BASE']:.1f} SLOPE {gm['SLOPE']:.1f} FLOOR {gm['FLOOR']} KNEE {gm['KNEE']} CEIL {gm['CEIL']} SOFT {gm['SOFT']}")
    print(f"       weighted OLS  FV ~ a + b*first6yrWAR  on n={len(tr)}: a={coef[0]:.2f}  b={coef[1]:.3f}")
    for q in (0.5,0.75,0.9,0.95,0.99):
        print(f"         realized WAR p{int(q*100)} = {np.quantile(x,q):.2f} -> shipped grade {eu._grade(float(np.quantile(x,q)),side):.1f}")

print("="*78); print("7. _MIN_EXPO_PA 80 / _MIN_EXPO_BF 90 vs the exposure distribution actually seen")
for side,key,floor in (("hit","pa",eu._MIN_EXPO_PA),("pit","bf",eu._MIN_EXPO_BF)):
    li=[r for r in rows(side,True) if r.get("milb")]
    print(f"  {side}: floor={floor} (exposure not stored on the live matrix rows; see _milb_features minpa "
          f"{'50' if side=='hit' else '60'} used to pick the PRIMARY level -- two different, unrelated hand floors "
          f"for the same concept)")

print("="*78); print("8. _LEVEL_ETA (provisional surplus seam) vs realized time-to-MLB")
import storage
deb=json.loads((pathlib.Path(__file__).parent.parent/"data"/"debuts.json").read_text(encoding="utf-8"))
print(f"  shipped: {eu._LEVEL_ETA}")
print("  (realized years-from-level-to-debut needs the milb ladder join; reported qualitatively below)")
