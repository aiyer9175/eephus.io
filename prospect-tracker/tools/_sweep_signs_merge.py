"""MERGE arm of the `signs` lane: does replacing a collinear PAIR with a single
combined column restore the declared direction, and does it cost anything?

Same gate as tools/_sweep_signs.drop_gate: 11 forward-chained time splits, paired
bootstrap resampling TRAIN AND TEST with a refit per draw, a zero-information control
(both member columns row-permuted, structure preserved), and a permutation null band.

Combination is the mean of the two STANDARDIZED members (the pair is on different raw
scales - `age` is in years, `age_rel_level` in years-vs-level), which is the only
scale-free way to make one column out of two.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import efv_model as M                                   # noqa: E402
import _sweep_signs as S                                # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "data" / "xfv_sign_merge_gate.json"
PAIRS = [("hit", "k_rel", "peak_k_rel"), ("pit", "k_rel", "peak_k_rel"),
         ("pit", "age", "age_rel_level"), ("hit", "age", "age_rel_level")]


def _merged(X, i, j):
    """X with columns i,j replaced by one column = mean of their z-scores."""
    z = np.column_stack([(X[:, c] - X[:, c].mean()) / (X[:, c].std() or 1.0) for c in (i, j)])
    keep = [c for c in range(X.shape[1]) if c not in (i, j)]
    return np.column_stack([X[:, keep], z.mean(axis=1)]), keep


def merge_gate(side, a, b, boot=1000, perm=500):
    keys, mono = M._feature_spec(side)
    data = S.load(side)
    X, y, w, yr, fv = S.arrays(data, keys)
    lam = M.blend_lambda(side)
    i, j = keys.index(a), keys.index(b)

    rho_base, pf_base = S._fwd_pooled_rho(X, y, w, yr, list(range(len(keys))), lam, fv)
    Xm, keep = _merged(X, i, j)
    cols_m = list(range(Xm.shape[1]))
    rho_m, pf_m = S._fwd_pooled_rho(Xm, y, w, yr, cols_m, lam, fv)

    # fitted sign of the merged column, served pool + every informative fold
    m_full = S.ridge_np(Xm, y, w)
    w_merged_full = float(m_full["w"][-1])
    fold_w = []
    for Y in S.FOLDS:
        tr = yr < Y
        if tr.sum() < 60 or Xm[tr, -1].std() <= 0:
            continue
        mm = S.ridge_np(Xm[tr], y[tr], w[tr])
        fold_w.append(float(mm["w"][-1]))

    rng = np.random.default_rng(S.SEED)
    deltas = []
    n = len(y)
    for _ in range(boot):
        idx = rng.integers(0, n, n)
        r1, _ = S._fwd_pooled_rho(X[idx], y[idx], w[idx], yr[idx], list(range(len(keys))), lam, fv[idx])
        Xb, _k = _merged(X[idx], i, j)
        r2, _ = S._fwd_pooled_rho(Xb, y[idx], w[idx], yr[idx], list(range(Xb.shape[1])), lam, fv[idx])
        if r1 is not None and r2 is not None:
            deltas.append(r2 - r1)
    deltas = np.array(deltas)

    ctrl = []
    for _ in range(150):
        Xp = X.copy()
        Xp[:, i] = X[rng.permutation(n), i]
        Xp[:, j] = X[rng.permutation(n), j]
        r, _ = S._fwd_pooled_rho(Xp, y, w, yr, list(range(len(keys))), lam, fv)
        if r is not None:
            ctrl.append(r - rho_base)
    ctrl = np.array(ctrl)

    nulls = []
    for _ in range(perm):
        yp = y.copy()
        for Y in set(yr.tolist()):
            msk = yr == Y
            yp[msk] = y[msk][rng.permutation(int(msk.sum()))]
        r1, _ = S._fwd_pooled_rho(X, yp, w, yr, list(range(len(keys))), lam, fv)
        r2, _ = S._fwd_pooled_rho(Xm, yp, w, yr, cols_m, lam, fv)
        if r1 is not None and r2 is not None:
            nulls.append(r2 - r1)
    nulls = np.array(nulls)

    mde = 0.016 if side == "pit" else 0.017
    d = float(rho_m - rho_base)
    decl = dict(zip(keys, mono))
    return {
        "side": side, "pair": [a, b], "declared": [decl[a], decl[b]], "lambda": lam,
        "served_w_members": [round(float(S.ridge_np(X, y, w)["w"][i]), 4),
                             round(float(S.ridge_np(X, y, w)["w"][j]), 4)],
        "merged_w_served": round(w_merged_full, 4),
        "merged_w_folds": [round(v, 4) for v in fold_w],
        "merged_folds_positive": sum(1 for v in fold_w if v > 0), "merged_folds_n": len(fold_w),
        "rho_base": round(float(rho_base), 4), "rho_merged": round(float(rho_m), 4),
        "delta_merge_minus_base": round(d, 5),
        "mde95": mde, "x_of_floor": round(abs(d) / mde, 3),
        "per_fold_delta": {k: round(pf_m[k] - pf_base[k], 4) for k in pf_base if k in pf_m},
        "boot": {"n": int(len(deltas)), "mean": round(float(deltas.mean()), 5),
                 "ci95": [round(float(np.percentile(deltas, 2.5)), 5),
                          round(float(np.percentile(deltas, 97.5)), 5)],
                 "p_merge_helps": round(float((deltas > 0).mean()), 4)},
        "zero_info_control": {"n": int(len(ctrl)), "mean": round(float(ctrl.mean()), 5),
                              "band": [round(float(np.percentile(ctrl, 2.5)), 5),
                                       round(float(np.percentile(ctrl, 97.5)), 5)]},
        "permutation_null": {"n": int(len(nulls)),
                             "band95": [round(float(np.percentile(nulls, 2.5)), 5),
                                        round(float(np.percentile(nulls, 97.5)), 5)],
                             "p_two_sided": round(float((np.abs(nulls) >= abs(d)).mean()), 4)},
    }


if __name__ == "__main__":
    out = {}
    for side, a, b in PAIRS:
        r = merge_gate(side, a, b)
        out[f"{side}:{a}+{b}"] = r
        print(f"{side} {a}+{b}: merged_w={r['merged_w_served']:+.4f} "
              f"folds+={r['merged_folds_positive']}/{r['merged_folds_n']} "
              f"delta={r['delta_merge_minus_base']:+.5f} ({r['x_of_floor']}x floor) "
              f"ci95={r['boot']['ci95']} ctrl={r['zero_info_control']['mean']:+.5f}")
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("wrote", OUT)
