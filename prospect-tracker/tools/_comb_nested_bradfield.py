# scratch lab (lane: nested) -- the owner's stratum, priced under the full
# multiplicity correction and under nested CV.
#
# Owner's case: AAA, age >= 23.5, below-median ops_rel. In-sample it looks
# damning. The question this lane must answer is what survives once you account
# for the fact that it was found by looking.
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import _comb_nested as C            # noqa: E402
import _comb_nested_run as R        # noqa: E402


def main(arm="tr"):
    rows = R.get_rows(arm)
    n = len(rows)
    years = np.array([r["year"] for r in rows])
    w = np.array([r["weight"] for r in rows], float)
    resid = np.array([r["resid"] for r in rows], float)
    tgt = np.array([r["target"] for r in rows], float)
    tres = np.array([r["target_resolved"] if r["target_resolved"] is not None
                     else np.nan for r in rows], float)

    lr = np.array([(r.get("milb") or {}).get("level_rank") or 0.0 for r in rows], float)
    age = np.array([(r.get("milb") or {}).get("age") or 22.5 for r in rows], float)
    ops = np.array([(r.get("milb") or {}).get("ops_rel") or 0.0 for r in rows], float)
    print("level_rank values:", sorted(set(lr.tolist())))

    OW = (lr >= 3.5) & (age >= 23.5) & (ops < 0)
    print(f"\n=== OWNER STRATUM  (level_rank>=3.5 & age>=23.5 & ops_rel<0)  arm={arm} ===")
    print(f"n={int(OW.sum())}  of {n}")
    yc = C.block_center(resid, w, years)
    for nm, m in (("owner", OW),):
        r_in = yc[m]
        r_out = yc[~m]
        se = np.sqrt(r_in.var() / len(r_in) + r_out.var() / len(r_out))
        t = (r_in.mean() - r_out.mean()) / se
        v = tres[m]
        v = v[~np.isnan(v)]
        print(f"  block-centred OOF resid: in={r_in.mean():+.3f} out={r_out.mean():+.3f} "
              f"t={t:+.3f}")
        print(f"  realized first-6yr WAR: mean={v.mean():+.3f} median={np.median(v):+.3f} "
              f"bust(<=0.5)={np.mean(v <= 0.5):.3f}  n_resolved={len(v)}")

    # where does it rank in the pre-registered family, and what is its q-value?
    M, desc = R.fold_masks(rows, np.ones(n, bool), arm)
    Mf = M.astype(np.float32)
    t_all, m_in, m_out, n_in = C.score_all(Mf, yc, w)
    from math import erfc, sqrt
    p = np.array([erfc(abs(x) / sqrt(2)) for x in t_all])
    q = C.bh_q(p)
    # closest pre-registered relatives: any candidate using level_rank top bin + age top bin
    rel = [i for i, d in enumerate(desc)
           if any(x[0] == "level_rank" and x[1] == 3 for x in d)
           and any(x[0] == "age" and x[1] == 3 for x in d)]
    print(f"\n  pre-registered relatives (level_rank top bin AND age top bin): {len(rel)}")
    rel.sort(key=lambda i: -abs(t_all[i]))
    order = np.argsort(-np.abs(t_all))
    rank = {int(c): r for r, c in enumerate(order)}
    for i in rel[:8]:
        print(f"    rank {rank[i]+1:5d}/{len(desc)}  t={t_all[i]:+7.3f} q={q[i]:8.3g} "
              f"n={int(M[:,i].sum()):4d} dWAR={m_in[i]-m_out[i]:+6.3f}  {C.desc_str(desc[i])}")

    # nested: does conditioning on the owner stratum help out of fold?
    print("\n=== NESTED: owner stratum as a FIXED, pre-specified rule (no search) ===")
    pred = np.array([r["pred"] for r in rows], float)
    accp, acct, accy = [], [], []
    for Y in C.OUTER_YEARS:
        tr = years < Y
        te = years == Y
        if tr.sum() < 80 or te.sum() == 0:
            continue
        ytr = C.block_center(resid[tr], w[tr], years[tr])
        off = ytr[OW[tr]].mean() - ytr[~OW[tr]].mean() if OW[tr].sum() >= 5 else 0.0
        adj = np.where(OW[te], off, 0.0)
        accp.append(pred[te] + adj)
        acct.append(tgt[te])
        accy.append(pred[te])
        print(f"  Y={Y} train_n_owner={int(OW[tr].sum()):3d} offset={off:+.3f} WAR "
              f"test_n_owner={int(OW[te].sum()):3d}")
    p1 = np.concatenate(accp); tt = np.concatenate(acct); p0 = np.concatenate(accy)
    print(f"  pooled rho {C.spearman(p0, tt):.4f} -> {C.spearman(p1, tt):.4f}  "
          f"d_rho={C.spearman(p1, tt)-C.spearman(p0, tt):+.4f}   (MDE95 0.017)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "tr")
