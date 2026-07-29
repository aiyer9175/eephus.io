"""Lane TABLES: the ZERO-DEFAULT milb-block imputes in efv_model._vec.
~52% of training rows carry no milb block; they are imputed at raw 0.0
(level_rank 0 == DSL, n_milb_seasons 0, age_rel_level 0 == 'typical for level')
and, because milb_unavailable forces milb_missing to 0.0, are NOT flagged."""
import sys, pathlib, json, random, statistics as st
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import numpy as np
import efv_model as em, _sweep_tables_harness as H
from efv_dataset import matrix_path, live_matrix_path
from _sweep_tables_gate import metrics

MILB_KEYS_HIT=["age_rel_level","age","level_rank","k_rel","bb_rel","n_milb_seasons",
               "obp_rel","ops_rel","peak_k_rel","peak_obp_rel","peak_iso_rel","peak_ops_rel",
               "iso_rel","prod_trend"]
MILB_KEYS_PIT=["age_rel_level","age","level_rank","k_rel","bb_rel","n_milb_seasons",
               "era_rel","peak_k_rel","peak_bb_rel","x_era_k","prod_trend"]

def rows(side,live=False):
    return json.loads((live_matrix_path(side) if live else matrix_path(side)).read_text(encoding="utf-8"))

def bootci(v,B=3000,seed=4):
    rnd=random.Random(seed);n=len(v)
    s=sorted(sum(v[rnd.randrange(n)] for _ in range(n))/n for _ in range(B))
    return round(s[int(.025*B)],3), round(s[int(.975*B)],3)

print("="*80)
for side in ("hit","pit"):
    keys,_=em._feature_spec(side)
    tr=[r for r in rows(side) if bool(r.get("is_pitcher"))==(side=="pit")
        and not (r.get("kind")=="bust" and r.get("bust_recent"))]
    li=[r for r in rows(side,True) if r.get("milb")]
    have=[r for r in tr if r.get("milb")]; miss=[r for r in tr if not r.get("milb")]
    flagged=sum(1 for r in miss if not r.get("milb_unavailable"))
    print(f"\n### side={side}  fit pool n={len(tr)}: milb-bearing {len(have)} ({len(have)/len(tr)*100:.1f}%), "
          f"milb-LESS {len(miss)} ({len(miss)/len(tr)*100:.1f}%) of which only {flagged} carry milb_missing=1")
    print(f"    LIVE scored pool is {len(li)}/{len(rows(side,True))} = 100% milb-bearing (run_live abstains otherwise)")
    print(f"  {'feature':16s} {'impute':>8} {'obs mean(milb-bearing)':>24} {'CI95':>18} {'shift in fit-pool SD':>21} {'in _FEATURES?':>14}")
    for k in (MILB_KEYS_HIT if side=="hit" else MILB_KEYS_PIT):
        vh=[em._vec(r,side)[k] for r in have]
        vall=[em._vec(r,side)[k] for r in tr]
        imp=em._vec({"kind":"bust","player_key":"x"},side)[k]
        sd=st.pstdev(vall) or 1.0
        print(f"  {k:16s} {imp:8.3f} {st.mean(vh):24.3f} {str(bootci(vh)):>18} {(imp-st.mean(vh))/sd:+21.3f} "
              f"{'YES' if k in keys else 'no':>14}")

print("\n"+"="*80)
print("GATE: re-impute the milb block at the OBSERVED milb-bearing means (the _TOOL_IMPUTE remedy)")
def prep_imp(side, use_means, perm=None):
    keys,_=em._feature_spec(side)
    tr=[r for r in rows(side) if bool(r.get("is_pitcher"))==(side=="pit")
        and not (r.get("kind")=="bust" and r.get("bust_recent"))]
    have=[r for r in tr if r.get("milb")]
    mk=MILB_KEYS_HIT if side=="hit" else MILB_KEYS_PIT
    means={k: st.mean([em._vec(r,side)[k] for r in have]) for k in mk}
    data=em._prep(tr,"target_censored",side)
    hasm={r["player_key"] for r in tr if r.get("milb")}
    if use_means:
        for d in data:
            if d["player_key"] not in hasm:
                for k in mk: d["feats"][k]=means[k]
    if perm is not None:
        rnd=random.Random(perm)
        for d in data:
            if d["player_key"] not in hasm:
                for k in mk: d["feats"][k]=means[k]+rnd.gauss(0,0)  # identical marginal, no info
    return data
for side in ("hit","pit"):
    keys,_=em._feature_spec(side); lam=em.blend_lambda(side)
    b=prep_imp(side,False); c=prep_imp(side,True)
    m0=metrics(b,keys,lam,em.SCORED_YEARS); m1=metrics(c,keys,lam,em.SCORED_YEARS)
    print(f"\n {side}: HAND zero-imputes pooled {m0['pooled']:.4f} block {m0['block']:.4f} auc {m0['auc']:.4f} t45 {m0['t45']:.4f}")
    print(f"      mean-imputes  d_pooled {m1['pooled']-m0['pooled']:+.4f}  d_block {m1['block']-m0['block']:+.4f} "
          f"d_auc {m1['auc']-m0['auc']:+.4f}  d_t45 {m1['t45']-m0['t45']:+.4f}")
    n=len(b); rnd=random.Random(7); bb=[]
    for _ in range(400):
        idx=[rnd.randrange(n) for _ in range(n)]
        a=metrics(b,keys,lam,em.SCORED_YEARS,idx); d=metrics(c,keys,lam,em.SCORED_YEARS,idx)
        if a and d: bb.append(d["pooled"]-a["pooled"])
    bb.sort(); print(f"      paired bootstrap B=400 (train+test, refit): d_pooled CI95 "
                     f"({bb[int(.025*len(bb))]:+.4f},{bb[int(.975*len(bb))]:+.4f}) P(>0)={sum(1 for x in bb if x>0)/len(bb):.3f}")
    yrs=tuple(range(2017,2025))
    m0a=metrics(b,keys,lam,yrs); m1a=metrics(c,keys,lam,yrs)
    pf=[m1a["per_fold"][y]-m0a["per_fold"][y] for y in m0a["per_fold"]]
    print(f"      time splits n={len(pf)}: mean {st.mean(pf):+.4f} n_pos {sum(1 for x in pf if x>0)}/{len(pf)} {[round(x,4) for x in pf]}")
