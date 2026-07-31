"""Lane TABLES: served-side impact of a _TYPICAL_LEVEL_AGE swap. READ-ONLY,
writes nothing; reproduces efv_score.run_live's rank_war leg in-memory."""
import sys, pathlib, json, statistics as st
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import efv_model as em, _sweep_tables_harness as H
from efv_dataset import matrix_path, live_matrix_path
from prospect_path import _predict

D=json.load(open(pathlib.Path(__file__).parent/"_sweep_tables_derived.json"))
CANDS={"EMP_TRAIN":D["train"],"EMP_LIVE":D["live"]}
LV=["DSL","CPX","A","A+","AA","AAA"]

def served(side, tbl):
    keys,_=em._feature_spec(side)
    tr=H.apply_table(json.loads(matrix_path(side).read_text(encoding="utf-8")),tbl)
    stack=em.fit_production_stack(tr,side,keys)
    ridge,a,b,ols=stack["ridge"],stack["a"],stack["b"],stack["ols"]
    lam=em.blend_lambda(side)
    live=H.apply_table(json.loads(live_matrix_path(side).read_text(encoding="utf-8")),tbl)
    out={}
    for r in live:
        try: cons_fv=float(r.get("consensus_fv_raw"))
        except (TypeError,ValueError): continue
        if not r.get("milb"): continue
        f=em._vec(r,side)
        war=max(-2.0,a+b*_predict(ridge,f))
        anchor=r.get("fv_effective"); anchor=float(anchor) if anchor is not None else cons_fv
        cons_war=max(0.0,em._pred_ols(ols,anchor))
        out[r["player_key"]]={"rank_war":(1-lam)*cons_war+lam*war,
                              "age_rel":f["age_rel_level"],"lvl":(r["milb"] or {}).get("milb_level"),
                              "w_agerel":dict(zip(ridge["keys"],ridge["w"])).get("age_rel_level"),
                              "mu":dict(zip(ridge["keys"],ridge["mu"])).get("age_rel_level"),
                              "sd":dict(zip(ridge["keys"],ridge["sd"])).get("age_rel_level")}
    return out

for side in ("hit","pit"):
    base=served(side,H.HAND)
    ks=list(base)
    r0={k:i for i,k in enumerate(sorted(ks,key=lambda k:-base[k]["rank_war"]))}
    any_k=ks[0]
    print(f"\n===== side={side} live scored n={len(ks)} =====")
    print(f"  HAND ridge age_rel_level: w={base[any_k]['w_agerel']:+.4f} mu={base[any_k]['mu']:+.4f} sd={base[any_k]['sd']:.4f}")
    for nm,tbl in CANDS.items():
        cur=served(side,tbl)
        r1={k:i for i,k in enumerate(sorted(ks,key=lambda k:-cur[k]["rank_war"]))}
        mv=[abs(r1[k]-r0[k]) for k in ks]
        dar=[cur[k]["age_rel"]-base[k]["age_rel"] for k in ks]
        big=sum(1 for v in dar if abs(v)>=0.5)
        print(f"  -- {nm}: w={cur[any_k]['w_agerel']:+.4f} mu={cur[any_k]['mu']:+.4f} sd={cur[any_k]['sd']:.4f}")
        print(f"     age_rel_level moved >=0.50 for {big}/{len(ks)} ({big/len(ks)*100:.1f}%); mean |move| {st.mean([abs(v) for v in dar]):.3f}")
        print(f"     board-rank movement: median {st.median(mv):.0f} slots, p90 {sorted(mv)[int(.9*len(mv))]:.0f}, max {max(mv)}")
        for lv in LV:
            sub=[k for k in ks if base[k]["lvl"]==lv]
            if len(sub)<20: continue
            print(f"       {lv:>4} n={len(sub):4d} mean d_age_rel {st.mean([cur[k]['age_rel']-base[k]['age_rel'] for k in sub]):+6.3f}"
                  f"  median rank move {st.median([r1[k]-r0[k] for k in sub]):+7.1f}")
        for pk in ("enrique_bradfield_jr",):
            if pk in base:
                print(f"     [{pk}] age_rel {base[pk]['age_rel']:+.2f} -> {cur[pk]['age_rel']:+.2f} ; "
                      f"rank_war {base[pk]['rank_war']:.3f} -> {cur[pk]['rank_war']:.3f} ; "
                      f"board slot {r0[pk]+1} -> {r1[pk]+1}")
