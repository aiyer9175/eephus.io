"""ADVERSARIAL VERIFY part 2 -- the rank_war channel (read-only, nothing written).

The part-1 sim held rank_war FIXED. In production consensus_fv also enters
  (a) the blend's consensus OLS anchor leg, and
  (b) the ridge as the `fv` feature (the only individually resolvable feature).
So an fv shift moves the RANKING too. Quantify d(rank_war)/d(fv) under the real
production stack and re-rank the live board.
"""
import os, sys, json
os.environ.setdefault("OMP_NUM_THREADS","1"); os.environ.setdefault("OPENBLAS_NUM_THREADS","1")
from pathlib import Path
HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0,str(HERE))
import efv_model as em
from efv_dataset import matrix_path

for side in ("hit","pit"):
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    st = em.fit_production_stack(rows, side)
    lam = em.blend_lambda(side)
    keys = st["keys"]; ridge = st["ridge"]; a,b = st["a"], st["b"]; ols = st["ols"]
    i = keys.index("fv")
    coef = ridge["coef"][i]; sd = ridge["sd"][i]
    d_ridge = b * coef / sd                    # d(calibrated model leg)/d(fv)
    d_cons  = ols["b"] if isinstance(ols,dict) and "b" in ols else None
    print(f"\n=== {side} ===  lam={lam}  n_train={st['n']}  keys={len(keys)}")
    print(f"  ols anchor: {ols}")
    print(f"  ridge fv coef {coef:.4f} / sd {sd:.4f}; calib b={b:.4f}  -> d(model leg)/d(fv) = {d_ridge:.4f} WAR per FV pt")
    if d_cons is not None:
        tot = (1-lam)*d_cons + lam*d_ridge
        print(f"  d(cons leg)/d(fv) = {d_cons:.4f};  d(rank_war)/d(fv) = (1-{lam})*{d_cons:.4f} + {lam}*{d_ridge:.4f} = {tot:.4f} WAR/FV")
        print(f"  => a 1.808 FV shift moves rank_war by {abs(tot)*1.808:.3f} WAR")
