# SCRATCH LAB (combinatorial-archetype lane, SWEEP sub-lane). READ-ONLY w.r.t. shipped code.
# NOTE: tools/_comb_nested.py belongs to a different lane. This file is the nested-CV
# driver for tools/_comb_sweep.py and shares its pre-registered family.
#
# STEP 4: NESTED CROSS-VALIDATION ON THE SEARCH PROCEDURE.
#
# The question that answers the owner is not "which archetype is best". It is "IS THE
# ARCHETYPE-SEARCH PROCEDURE WORTH ANYTHING OUT OF SAMPLE". So: leave one decision-year
# out, run the ENTIRE pre-registered sweep on the remaining years, select what the search
# likes best there, and score that selection on the untouched year. Repeat for every year.
#
#   inner_sel_abs_t     what a naive sweep would publish
#   outer_effect        the same archetype on the held-out year, SIGNED so positive means
#                       the inner finding replicated
#   d_mae / d_rho       what happens to the shipped model on the held-out year if the
#                       inner-estimated offset is actually applied
#
# A zero-information control (random strata, IDENTICAL marginal sizes) runs the identical
# procedure, so the nested lift has something to be judged against.
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from _comb_sweep import OUT, SEED, MIN_N, ORIGINS, prepare, welch_t    # noqa: E402


def _spearman(a, b):
    def rk(v):
        o = np.argsort(v, kind="mergesort")
        r = np.empty(len(v), float)
        r[o] = np.arange(1, len(v) + 1, dtype=float)
        s = v[o]
        i = 0
        while i < len(s):
            j = i
            while j + 1 < len(s) and s[j + 1] == s[i]:
                j += 1
            if j > i:
                r[o[i:j + 1]] = (i + j) / 2.0 + 1
            i = j + 1
        return r
    x, y = rk(np.asarray(a, float)), rk(np.asarray(b, float))
    x = x - x.mean()
    y = y - y.mean()
    d = np.sqrt((x * x).sum() * (y * y).sum())
    return float((x * y).sum() / d) if d > 0 else float("nan")


def run(side="hit", pop="TRACK", arm="R_cal", topk=(1, 5), seed=SEED):
    D, art, strata0, idx, M0, R, N, keepj, pred = prepare(side, pop)
    strata = [s for s, k in zip(strata0, keepj) if k]
    M = M0[:, keepj]
    dy, y, p, r = D["dy"][idx], D["y"][idx], pred[idx], R[arm]
    rng = np.random.default_rng(seed)

    nsz = M.sum(axis=0).astype(int)
    Mc = np.zeros_like(M)
    for j in range(len(strata)):
        Mc[rng.choice(N, size=nsz[j], replace=False), j] = 1.0

    years = [yv for yv in ORIGINS if (dy == yv).sum() >= 25]
    rows = {"real": [], "ctrl": []}
    for tag, MM in (("real", M), ("ctrl", Mc)):
        for yv in years:
            out = dy == yv
            inn = ~out
            Mi, Mo = MM[inn], MM[out]
            ok = (Mi.sum(axis=0) >= MIN_N) & (Mo.sum(axis=0) >= 8)
            if ok.sum() == 0:
                continue
            ti, m1i, m2i, ni, sei = welch_t(Mi, r[inn])
            score = np.where(ok, np.abs(ti), -np.inf)
            order = np.argsort(-score)
            rec = {"year": int(yv), "n_out": int(out.sum()), "n_cand": int(ok.sum())}
            for k in topk:
                sel = order[:k]
                off = (m1i - m2i)[sel]
                eff_out, pcorr = [], p[out].copy()
                for jj, o in zip(sel, off):
                    mo = Mo[:, jj] > 0
                    if mo.sum() >= 3 and (~mo).sum() >= 3:
                        eff_out.append(float(np.sign(o) * (r[out][mo].mean()
                                                           - r[out][~mo].mean())))
                    pcorr[mo] += o
                rec["k%d_sel_t" % k] = float(score[sel].max())
                rec["k%d_sel_eff" % k] = float(off[0])
                rec["k%d_out_eff" % k] = float(np.mean(eff_out)) if eff_out else None
                rec["k%d_d_mae" % k] = float(np.abs(y[out] - pcorr).mean()
                                             - np.abs(y[out] - p[out]).mean())
                rec["k%d_d_rho" % k] = float(_spearman(pcorr, y[out])
                                             - _spearman(p[out], y[out]))
                if k == 1:
                    rec["k1_id"] = (strata[sel[0]]["id"] if tag == "real"
                                    else "ctrl#%d" % sel[0])
            rows[tag].append(rec)

    def agg(rs, k):
        oe = np.array([x["k%d_out_eff" % k] for x in rs
                       if x["k%d_out_eff" % k] is not None])
        dm = np.array([x["k%d_d_mae" % k] for x in rs])
        dr = np.array([x["k%d_d_rho" % k] for x in rs])
        st = np.array([x["k%d_sel_t" % k] for x in rs])
        se = np.array([abs(x["k%d_sel_eff" % k]) for x in rs])

        def ci(v):
            if len(v) < 2:
                return [None, None]
            s = v.std(ddof=1) / np.sqrt(len(v))
            return [round(float(v.mean() - 1.96 * s), 4),
                    round(float(v.mean() + 1.96 * s), 4)]
        return {"folds": len(rs),
                "inner_sel_abs_t_mean": round(float(st.mean()), 3),
                "inner_sel_abs_effect_mean": round(float(se.mean()), 4),
                "outer_effect_mean": round(float(oe.mean()), 4) if len(oe) else None,
                "outer_effect_ci95": ci(oe),
                "outer_effect_pos_folds": int((oe > 0).sum()), "outer_folds": len(oe),
                "shrinkage_ratio": (round(float(oe.mean() / se.mean()), 3)
                                    if len(oe) and se.mean() else None),
                "d_mae_mean": round(float(dm.mean()), 4), "d_mae_ci95": ci(dm),
                "d_rho_mean": round(float(dr.mean()), 4), "d_rho_ci95": ci(dr)}

    res = {"side": side, "pop": pop, "arm": arm, "n_rows": int(N),
           "n_hypotheses": len(strata), "years": years,
           "real": {"k%d" % k: agg(rows["real"], k) for k in topk},
           "ctrl": {"k%d" % k: agg(rows["ctrl"], k) for k in topk},
           "per_fold": rows}
    fp = OUT / ("nested_%s_%s_%s.json" % (side, pop, arm))
    fp.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print("[%s/%s/%s] N=%d K=%d folds=%d" % (side, pop, arm, N, len(strata), len(years)))
    for k in topk:
        a, c = res["real"]["k%d" % k], res["ctrl"]["k%d" % k]
        print("  k=%d REAL inner|t| %.2f inner|eff| %+.3f -> OUTER %s ci %s (%d/%d +) "
              "shrink %s" % (k, a["inner_sel_abs_t_mean"], a["inner_sel_abs_effect_mean"],
                             a["outer_effect_mean"], a["outer_effect_ci95"],
                             a["outer_effect_pos_folds"], a["outer_folds"],
                             a["shrinkage_ratio"]))
        print("       d_MAE %+.4f ci %s   d_rho %+.4f ci %s"
              % (a["d_mae_mean"], a["d_mae_ci95"], a["d_rho_mean"], a["d_rho_ci95"]))
        print("  k=%d CTRL inner|t| %.2f inner|eff| %+.3f -> OUTER %s ci %s (%d/%d +)"
              % (k, c["inner_sel_abs_t_mean"], c["inner_sel_abs_effect_mean"],
                 c["outer_effect_mean"], c["outer_effect_ci95"],
                 c["outer_effect_pos_folds"], c["outer_folds"]))
    print("  selected per fold:", [x["k1_id"] for x in rows["real"]])
    return res


if __name__ == "__main__":
    t0 = time.time()
    run(sys.argv[1] if len(sys.argv) > 1 else "hit",
        sys.argv[2] if len(sys.argv) > 2 else "TRACK",
        sys.argv[3] if len(sys.argv) > 3 else "R_cal")
    print("  %.1fs" % (time.time() - t0))
