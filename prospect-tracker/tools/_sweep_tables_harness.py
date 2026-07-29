"""Lane TABLES: full-gate harness for a _TYPICAL_LEVEL_AGE re-derivation.

READ-ONLY. Recomputes milb.age_rel_level in-memory from (age, milb_level) with a
candidate level-age table, then runs the production forward-chained protocol.
Does not touch efv_dataset.py / efv_model.py.
"""
import sys, pathlib, json, math, random, statistics as st
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import numpy as np
import efv_model as em
from efv_dataset import matrix_path
from prospect_path import _fit_ridge, _predict, _spearman

HAND = {"DSL":18.0,"CPX":19.0,"A":20.0,"A+":21.0,"AA":22.5,"AAA":24.0}
LV = ["DSL","CPX","A","A+","AA","AAA"]
RANK = {l:i for i,l in enumerate(LV)}

def load(side):
    return json.loads(matrix_path(side).read_text(encoding="utf-8"))

def apply_table(rows, tbl, permute_seed=None):
    """Return deep-ish copies of rows with milb.age_rel_level recomputed."""
    out=[]
    vals=[]
    for r in rows:
        m = r.get("milb")
        r2 = dict(r)
        if m:
            m2 = dict(m)
            lv, ag = m2.get("milb_level"), m2.get("age")
            if lv in tbl and ag is not None:
                v = max(-3.5, min(3.5, float(ag) - tbl[lv]))
                m2["age_rel_level"] = v
            r2["milb"]=m2
            vals.append(m2.get("age_rel_level"))
        out.append(r2)
    if permute_seed is not None:
        rnd = random.Random(permute_seed)
        idxs=[i for i,r in enumerate(out) if r.get("milb")]
        pool=[out[i]["milb"]["age_rel_level"] for i in idxs]
        rnd.shuffle(pool)
        for i,v in zip(idxs,pool):
            out[i]["milb"] = dict(out[i]["milb"]); out[i]["milb"]["age_rel_level"]=v
    return out

def verify_hand(side):
    rows = load(side)
    bad=0; n=0
    for r in rows:
        m=r.get("milb") or {}
        lv,ag = m.get("milb_level"), m.get("age")
        if lv in HAND and ag is not None and not m.get("age_missing"):
            n+=1
            want=max(-3.5,min(3.5,float(ag)-HAND[lv]))
            if abs(want-float(m["age_rel_level"]))>1e-9: bad+=1
    return n,bad

# ---- scoring ------------------------------------------------------------
def score_pairs(pairs):
    if len(pairs)<8: return None
    return _spearman([p for p,_ in pairs],[t for _,t in pairs])

def fwd_folds(data, years, keys, lam):
    """forward-chained; returns {year: [(blend,target,player_key,fv)]}"""
    out={}
    for yr in years:
        tr=[r for r in data if r["decision_year"]<yr]
        te=[r for r in data if r["decision_year"]==yr]
        if len(te)<15 or len(tr)<60: continue
        ols=em._fit_ols_fv(tr); ridge=_fit_ridge(tr,keys)
        if not (ols and ridge): continue
        rec=[]
        for r in te:
            cons=max(0.0, em._pred_ols(ols,r["fv"]))
            blend=(1-lam)*cons+lam*_predict(ridge,r["feats"])
            rec.append((blend,r["target"],r["player_key"],r["fv"],cons))
        out[yr]=rec
    return out

def pooled_rho(folds):
    p=[(a,b) for yr in folds for a,b,_,_,_ in folds[yr]]
    return score_pairs(p), len(p)

def block_rho(folds):
    """(year) block-normalized pooled spearman: rank within fold, then pool."""
    xs,ys=[],[]
    for yr,rec in folds.items():
        n=len(rec)
        if n<8: continue
        def rk(vals):
            order=sorted(range(n), key=lambda i: vals[i]); r=[0.0]*n
            i=0
            while i<n:
                j=i
                while j+1<n and vals[order[j+1]]==vals[order[i]]: j+=1
                avg=(i+j)/2.0
                for k in range(i,j+1): r[order[k]]=avg
                i=j+1
            return [(v/(n-1) if n>1 else 0.5) for v in r]
        xs += rk([a for a,_,_,_,_ in rec]); ys += rk([b for _,b,_,_,_ in rec])
    return _spearman(xs,ys), len(xs)

def auc(scores, labels):
    pairs=sorted(zip(scores,labels))
    n=len(pairs); ranks=[0.0]*n; i=0
    while i<n:
        j=i
        while j+1<n and pairs[j+1][0]==pairs[i][0]: j+=1
        avg=(i+j)/2.0+1
        for k in range(i,j+1): ranks[k]=avg
        i=j+1
    npos=sum(1 for _,l in pairs if l); nneg=n-npos
    if npos==0 or nneg==0: return None
    s=sum(r for r,(_,l) in zip(ranks,pairs) if l)
    return (s - npos*(npos+1)/2)/(npos*nneg)

def t45(folds, lo=42.5, hi=47.5):
    p=[(a,b) for yr in folds for a,b,_,fv,_ in folds[yr] if lo<=fv<hi]
    return score_pairs(p), len(p)

def run_side(side, tbl, years=None, seed_perm=None):
    keys,_m = em._feature_spec(side)
    rows = apply_table(load(side), tbl, permute_seed=seed_perm)
    data = em._prep([r for r in rows if bool(r.get("is_pitcher"))==(side=="pit")
                     and not (r.get("kind")=="bust" and r.get("bust_recent"))],
                    "target_censored", side)
    lam = em.blend_lambda(side)
    years = years or em.SCORED_YEARS
    folds = fwd_folds(data, years, keys, lam)
    pr,npr = pooled_rho(folds); br,nbr = block_rho(folds); t,nt = t45(folds)
    sc=[a for yr in folds for a,_,_,_,_ in folds[yr]]
    lb=[b>=3.0 for yr in folds for _,b,_,_,_ in folds[yr]]
    return {"pooled_rho":pr,"n":npr,"block_rho":br,"t45":t,"n_t45":nt,
            "auc_contrib":auc(sc,lb),"lam":lam,"folds":folds}

if __name__=="__main__":
    for side in ("hit","pit"):
        n,bad = verify_hand(side)
        print(f"[verify] {side}: {n} rows with level+age; mismatches vs stored age_rel_level = {bad}")
