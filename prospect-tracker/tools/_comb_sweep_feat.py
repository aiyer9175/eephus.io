# SCRATCH LAB (combinatorial-archetype lane, SWEEP sub-lane). READ-ONLY.
#
# The sweep's only recurring non-artifact candidate is tool_game_pwr = below average, which
# is NOT a shipped hitter feature (shipped: fv, obp_rel, k_rel, peak_k_rel, age_rel_level,
# n_milb_seasons, tool_hit, tool_speed, milb_missing, is_ifa, is_college, ops_rel, age,
# level_rank). A discrete stratum test on 40-95 rows is a low-power instrument; if that
# grade really carries unpriced information the FEATURE ADD is the powerful version of the
# same question, and it is the form item C asks about (does the stratum reduce to a smooth
# term). Run under docs/EFV_GATE_STANDARD.md: MDE95 = 0.017 pooled hit rho, 0.0149 block-rho,
# permuted-twin zero-information control, forward-chained folds, paired refit bootstrap.
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

import efv_model as E                                                   # noqa: E402
from _frontier_ablate import ridge_fit, ridge_pred, ols_fit, lincal, rho, _rankavg  # noqa: E402
from _comb_sweep import OUT, SEED, LAM, ORIGINS, load_rows              # noqa: E402

CAND = ["tool_game_pwr", "tool_raw_pwr", "tool_field", "tool_throw"]


def load(side="hit"):
    rows = load_rows(side)
    prep = E._prep(rows, "target_censored", side)
    keys = E._feature_spec(side)[0]
    X = np.array([[r["feats"].get(k, 0.0) for k in keys] for r in prep], dtype=float)
    y = np.array([r["target"] for r in prep], dtype=float)
    w = np.clip(np.array([float(r.get("weight", 1.0) or 0.0) for r in prep]), 1e-3, None)
    fv = np.array([r["fv"] for r in prep], dtype=float)
    dy = np.array([r["decision_year"] for r in prep], dtype=int)
    deb = np.array([r["kind"] == "debuted" for r in prep])
    keep = np.array([not (r["kind"] == "bust" and o.get("bust_recent"))
                     for r, o in zip(prep, rows)])
    names = list(keys)
    rng = np.random.default_rng(SEED)
    cols = []
    # candidate grades. Missing is imputed at the PRE-2020 observed mean and paired with an
    # explicit missing flag, so "has a grade at all" cannot masquerade as the grade itself.
    for k in CAND:
        v = np.array([np.nan if r.get(k) is None else float(r[k]) for r in rows])
        obs = ~np.isnan(v)
        pre = obs & (dy < min(ORIGINS))
        mu = float(v[pre].mean()) if pre.sum() > 30 else float(v[obs].mean())
        vv = np.where(obs, v, mu)
        cols.append((k, vv))
        cols.append((k + "_missing", (~obs).astype(float)))
    for k, v in cols:
        names.append(k)
        X = np.column_stack([X, v])
    # permuted twins (identical marginal, zero information)
    for k, v in cols:
        names.append("~perm~" + k)
        X = np.column_stack([X, v[rng.permutation(len(v))]])
    return dict(side=side, X=X, y=y, w=w, fv=fv, dy=dy, deb=deb, keep=keep,
                names=names, idx={k: i for i, k in enumerate(names)},
                base=[names.index(k) for k in keys])


def score(D, cols, sel=None, origins=ORIGINS):
    X, y, w, fv, dy, deb, keep = (D["X"], D["y"], D["w"], D["fv"], D["dy"],
                                  D["deb"], D["keep"])
    if sel is None:
        sel = np.arange(len(y))
    Xs, ys, ws, fvs, dys = X[sel][:, cols], y[sel], w[sel], fv[sel], dy[sel]
    debs, keeps = deb[sel], keep[sel]
    lam = LAM[D["side"]]
    B, P, T = [], [], []
    for yr in origins:
        tr = np.flatnonzero(keeps & (dys < yr))
        te = np.flatnonzero(debs & (dys == yr))
        if len(te) < 15 or len(tr) < 60:
            continue
        o = ols_fit(fvs[tr], ys[tr])
        rg = ridge_fit(Xs[tr], ys[tr], ws[tr])
        if o is None or rg is None:
            continue
        a, b = lincal(ridge_pred(rg, Xs[tr]), ys[tr])
        mod = np.maximum(-2.0, a + b * ridge_pred(rg, Xs[te]))
        cons = np.maximum(0.0, o[0] + o[1] * fvs[te])
        B.append(np.full(len(te), yr))
        P.append((1 - lam) * cons + lam * mod)
        T.append(ys[te])
    if not P:
        return None
    return np.concatenate(B), np.concatenate(P), np.concatenate(T)


def blockrho(B, P, T):
    def bn(v):
        o = np.empty(len(v))
        for b in np.unique(B):
            m = B == b
            o[m] = (_rankavg(v[m]) - 0.5) / m.sum()
        return o
    return rho(bn(P), bn(T))


def arm(D, extra):
    cols = list(D["base"]) + [D["idx"][k] for k in extra]
    r = score(D, cols)
    if r is None:
        return None
    B, P, T = r
    per = {int(b): round(rho(P[B == b], T[B == b]), 4) for b in np.unique(B)}
    return {"pooled_rho": rho(P, T), "block_rho": blockrho(B, P, T),
            "n_test": len(T), "per_fold": per}


def main():
    t0 = time.time()
    D = load("hit")
    base = arm(D, [])
    res = {"base": base, "arms": {}}
    print("BASE pooled rho %.4f  block rho %.4f  n=%d  folds %s"
          % (base["pooled_rho"], base["block_rho"], base["n_test"], base["per_fold"]))
    trials = ([([k, k + "_missing"], k) for k in CAND]
              + [(["~perm~" + k, k + "_missing"], "~perm~" + k) for k in CAND]
              + [([c for k in CAND for c in (k, k + "_missing")], "ALL4")])
    for cols, label in trials:
        a = arm(D, cols)
        d_p = a["pooled_rho"] - base["pooled_rho"]
        d_b = a["block_rho"] - base["block_rho"]
        nfold = sum(1 for k in a["per_fold"] if a["per_fold"][k] > base["per_fold"][k])
        res["arms"][label] = {**a, "d_pooled_rho": round(d_p, 4),
                              "d_block_rho": round(d_b, 4),
                              "folds_better": nfold, "folds": len(a["per_fold"])}
        print("  %-22s d_pooled %+.4f   d_block %+.4f   folds better %d/%d"
              % (label, d_p, d_b, nfold, len(a["per_fold"])))

    # paired refit bootstrap on the single best real candidate
    best = max(CAND, key=lambda k: abs(res["arms"][k]["d_pooled_rho"]))
    rng = np.random.default_rng(SEED + 5)
    n = len(D["y"])
    dp, db = [], []
    Bn = 400
    for _ in range(Bn):
        sel = rng.integers(0, n, n)
        r0 = score(D, list(D["base"]), sel)
        r1 = score(D, list(D["base"]) + [D["idx"][best], D["idx"][best + "_missing"]], sel)
        if r0 is None or r1 is None:
            continue
        dp.append(rho(r1[1], r1[2]) - rho(r0[1], r0[2]))
        db.append(blockrho(*r1) - blockrho(*r0))
    dp, db = np.array(dp), np.array(db)
    res["bootstrap"] = {"candidate": best, "B": len(dp),
                        "d_pooled_mean": round(float(dp.mean()), 4),
                        "d_pooled_ci95": [round(float(np.quantile(dp, .025)), 4),
                                          round(float(np.quantile(dp, .975)), 4)],
                        "p_improves": round(float((dp > 0).mean()), 3),
                        "d_block_mean": round(float(db.mean()), 4),
                        "d_block_ci95": [round(float(np.quantile(db, .025)), 4),
                                         round(float(np.quantile(db, .975)), 4)]}
    print("  paired refit bootstrap (%s, B=%d): d_pooled %+.4f ci %s  P(improves) %.3f"
          % (best, len(dp), res["bootstrap"]["d_pooled_mean"],
             res["bootstrap"]["d_pooled_ci95"], res["bootstrap"]["p_improves"]))
    print("                                     d_block  %+.4f ci %s"
          % (res["bootstrap"]["d_block_mean"], res["bootstrap"]["d_block_ci95"]))
    print("  GATE: MDE95 pooled 0.017 hit, block-rho 0.0149")
    (OUT / "feature_add_hit.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print("  %.1fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
