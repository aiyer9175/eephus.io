# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""AGE-VS-LEVEL AS A WEIGHT ON PRODUCTION, not as a flat feature (owner ask, 2026-09-04).

> "Instead of having a flat eFV driver weighting age for level, can we instead test and
> possibly implement age-vs-level-weighting into eFV statistical production drivers?"

Today `age_rel_level` enters the ridge ADDITIVELY, in parallel with the production rates
(`obp_rel`, `ops_rel`, `k_rel`, `peak_k_rel` on the hitter side; `k_rel`, `bb_rel`,
`peak_k_rel`, `x_era_k` on the pitcher side). An additive term can only say "young for the
level is good"; it cannot say "the same OBP means MORE from a 19-year-old in AA than from a
24-year-old in AA". Saying that requires an INTERACTION, and this lab measures whether the
interaction buys anything the additive pair does not already give.

Four arm shapes, each gated the same way:

  PRODUCT     age_rel_level * P, one column per production key P
  SPLIT       P gated on young-for-level and P gated on old-for-level as two columns, which
              lets the production slope differ by age band instead of assuming one slope
  LEVEL       level_rank * P, the other half of the same idea: a line at AA should not
              count the same as the identical line at A
  JOINT       every PRODUCT column at once, because the family may be jointly informative
              while no single column clears on its own

and then the one the ask is literally about:

  REPLACE     drop the flat `age_rel_level` column and add the PRODUCT columns in its
              place. This is "instead of a flat driver", tested as stated rather than as
              an addition on top.

CONTROLS. The permutation null for an interaction arm permutes the AGE vector across rows
inside each decision year, which destroys the age-production pairing while preserving both
marginals exactly. That is the right null here: an interaction that survives a shuffled age
column was never an interaction, it was the production term getting a second chance. Holm
runs across the whole family because this is a search. Floors are E_cond on the same paired
bootstrap the standard uses, and the estimator is imported from efv_mde_lab so the
arithmetic matches the shipped floors bit for bit.

Run:
    python tools/efv_age_interaction_lab.py
    python tools/efv_age_interaction_lab.py --side hit --b-perm 100
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import efv_model as E                       # noqa: E402  READ ONLY

sys.path.insert(0, str(ROOT / "tools"))
import efv_mde_lab as M                     # noqa: E402

OUT_PATH = ROOT / "data" / "xfv_age_interaction_eval.json"
SEED = 20260807
SIDES = ("hit", "pit")

PROD_KEYS = {
    "hit": ("obp_rel", "ops_rel", "k_rel", "peak_k_rel"),
    "pit": ("k_rel", "bb_rel", "peak_k_rel", "x_era_k"),
}
AGE_KEY = "age_rel_level"
LEVEL_KEY = "level_rank"
YOUNG_CUT = -0.5      # years below the level's typical age
OLD_CUT = 0.5


def load(side: str) -> dict:
    D = M.load_side(side)
    D["col"] = {k: i for i, k in enumerate(D["keys"])}
    return D


def _z(v: np.ndarray) -> np.ndarray:
    s = v.std()
    return (v - v.mean()) / s if s > 0 else v * 0.0


def arms(D: dict, side: str, age: np.ndarray | None = None) -> dict[str, np.ndarray]:
    """{arm name: extra columns (n, k)}. `age` overrides the age vector for the null."""
    col = D["col"]
    X = D["X"]
    a = X[:, col[AGE_KEY]] if age is None else age
    out: dict[str, np.ndarray] = {}
    prods = [k for k in PROD_KEYS[side] if k in col]
    az = _z(a)
    for k in prods:
        p = X[:, col[k]]
        out[f"product__{k}"] = _z(az * _z(p)).reshape(-1, 1)
        young = (a <= YOUNG_CUT).astype(float)
        old = (a >= OLD_CUT).astype(float)
        out[f"split__{k}"] = np.column_stack([_z(young * _z(p)), _z(old * _z(p))])
        if LEVEL_KEY in col:
            out[f"level__{k}"] = _z(_z(X[:, col[LEVEL_KEY]]) * _z(p)).reshape(-1, 1)
    if prods:
        out["joint__all_products"] = np.column_stack(
            [_z(az * _z(X[:, col[k]])) for k in prods])
    return out


def chain(D, extra=None, drop=None, sel=None, years=None):
    """The shipped forward chain, with optional extra columns and one dropped column."""
    years = tuple(E.SCORED_YEARS) if years is None else tuple(years)
    lam = D["lam"]
    if sel is None:
        sel = np.arange(D["n"])
    X = D["X"]
    if drop is not None:
        X = np.delete(X, drop, axis=1)
    if extra is not None:
        X = np.column_stack([X, extra])
    X, y, w, fv, dy = X[sel], D["y"][sel], D["w"][sel], D["fv"][sel], D["dy"][sel]
    YR, C, B, T, W = [], [], [], [], []
    for yr in years:
        tr = np.flatnonzero(dy < yr)
        te = np.flatnonzero(dy == yr)
        if len(te) < 15 or len(tr) < 60:
            continue
        o = M.ols_fit(fv[tr], y[tr])
        rg = M.ridge_fit(X[tr], y[tr], w[tr])
        if o is None or rg is None:
            continue
        cons = np.maximum(0.0, o[0] + o[1] * fv[te])
        mod = M.ridge_pred(rg, X[te])
        YR.append(np.full(len(te), yr))
        C.append(cons)
        B.append((1 - lam) * cons + lam * mod)
        T.append(y[te])
        W.append(w[te])
    if not B:
        return None
    return tuple(np.concatenate(a) for a in (YR, C, B, T, W))


def margin(parts, sel=None):
    if parts is None:
        return None
    _yr, cons, blend, tgt, w = parts
    if sel is not None:
        cons, blend, tgt, w = cons[sel], blend[sel], tgt[sel], w[sel]
    return float(M.wrho(blend, tgt, w)) - float(M.wrho(cons, tgt, w))


def permute_age_within_year(a: np.ndarray, dy: np.ndarray, rng) -> np.ndarray:
    """Shuffle the age vector inside each decision year: destroys the age-production
    pairing, preserves the marginal age distribution and the cohort structure."""
    out = a.copy()
    for yr in np.unique(dy):
        idx = np.flatnonzero(dy == yr)
        out[idx] = a[idx][rng.permutation(len(idx))]
    return out


def holm(p: dict[str, float]) -> dict[str, float]:
    items = sorted(p.items(), key=lambda kv: kv[1])
    m, out, run = len(items), {}, 0.0
    for i, (k, v) in enumerate(items):
        run = max(run, min(1.0, (m - i) * v))
        out[k] = round(run, 5)
    return out


def run(side: str, b_cond: int, b_perm: int) -> dict:
    D = load(side)
    base_parts = chain(D)
    base = margin(base_parts)
    n_te = len(base_parts[3])
    rng = np.random.default_rng(SEED)
    A = arms(D, side)
    results, pvals = [], {}
    t0 = time.time()

    # the REPLACE arm is built here because it also drops a column
    replace_cols = A.get("joint__all_products")
    todo = list(A.items())
    if replace_cols is not None and AGE_KEY in D["col"]:
        todo.append(("replace__age_rel_level_by_products", replace_cols))

    for i, (name, extra) in enumerate(todo):
        drop = D["col"][AGE_KEY] if name.startswith("replace__") else None
        parts = chain(D, extra=extra, drop=drop)
        m = margin(parts)
        if m is None:
            results.append({"name": name, "skipped": "no fold survived"})
            continue
        delta = m - base
        cond = []
        for _ in range(b_cond):
            s = rng.integers(0, n_te, n_te)
            a_, b_ = margin(parts, s), margin(base_parts, s)
            if a_ is not None and b_ is not None:
                cond.append(a_ - b_)
        cond = np.array([v for v in cond if np.isfinite(v)], dtype=float)
        null = []
        for j in range(b_perm):
            r2 = np.random.default_rng(SEED + 104729 * (i + 1) + j)
            a_perm = permute_age_within_year(D["X"][:, D["col"][AGE_KEY]], D["dy"], r2)
            A2 = arms(D, side, age=a_perm)
            e2 = (A2.get("joint__all_products") if name.startswith("replace__")
                  else A2.get(name))
            if e2 is None:
                continue
            mm = margin(chain(D, extra=e2, drop=drop))
            if mm is not None:
                null.append(mm - base)
        null = np.array(null, dtype=float)
        p = float((np.abs(null) >= abs(delta)).mean()) if len(null) else 1.0
        pvals[name] = p
        folds = {}
        for yr in E.SCORED_YEARS:
            a_ = margin(chain(D, extra=extra, drop=drop, years=(yr,)))
            b_ = margin(chain(D, years=(yr,)))
            if a_ is not None and b_ is not None:
                folds[str(yr)] = round(a_ - b_, 5)
        floor = 1.96 * float(cond.std(ddof=1)) if len(cond) > 1 else None
        results.append({
            "name": name, "n_extra_cols": int(np.asarray(extra).shape[1]),
            "drops_flat_age": bool(drop is not None),
            "margin_base": round(base, 5), "margin_with": round(m, 5),
            "delta": round(delta, 5),
            "E_cond_ci95": ([round(float(np.percentile(cond, 2.5)), 5),
                             round(float(np.percentile(cond, 97.5)), 5)] if len(cond) else None),
            "E_cond_floor_mde95": round(floor, 5) if floor else None,
            "clears_own_floor": bool(floor and abs(delta) >= floor),
            "permutation_p": round(p, 4), "permutation_B": int(len(null)),
            "folds_positive": sum(1 for v in folds.values() if v > 0),
            "folds_total": len(folds), "per_fold_delta": folds,
        })
        print(f"  [{i+1}/{len(todo)}] {name:38} delta {delta:+.5f} p={p:.3f} "
              f"{time.time()-t0:.0f}s", flush=True)
    adj = holm(pvals)
    for r in results:
        if r.get("name") in adj:
            r["holm_p"] = adj[r["name"]]
            r["SHIPPABLE"] = bool(r.get("clears_own_floor") and adj[r["name"]] < 0.05
                                  and r.get("delta", 0) > 0)
    return {"side": side, "n_rows": D["n"], "baseline_margin": round(base, 5),
            "family_size": len(pvals), "results": results}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--side", choices=["hit", "pit", "both"], default="both")
    ap.add_argument("--b-cond", type=int, default=1000)
    ap.add_argument("--b-perm", type=int, default=200)
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()
    sides = SIDES if a.side == "both" else (a.side,)
    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "produced_by": "tools/efv_age_interaction_lab.py",
        "asked_by": ("owner, 2026-09-04: age-vs-level as a WEIGHT on the production "
                     "drivers instead of a flat additive feature"),
        "label_basis": "eWAR v2 (the 2026-09-04 label epoch)",
        "arms": {
            "product": "age_rel_level * P, one column per production key",
            "split": "P gated young-for-level and P gated old-for-level, two columns",
            "level": "level_rank * P, the level half of the same idea",
            "joint": "every product column at once",
            "replace": "drop the flat age_rel_level and add the product columns instead",
        },
        "null": ("the age vector is permuted WITHIN each decision year, destroying the "
                 "age-production pairing while preserving both marginals"),
        "young_cut": YOUNG_CUT, "old_cut": OLD_CUT, "seed": SEED,
        "sides": {},
    }
    for side in sides:
        print(f"=== {side}", flush=True)
        out["sides"][side] = run(side, a.b_cond, a.b_perm)
    if not a.no_write:
        OUT_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print("wrote", OUT_PATH)
    for side, blk in out["sides"].items():
        ship = [r["name"] for r in blk["results"] if r.get("SHIPPABLE")]
        print(f"{side}: baseline {blk['baseline_margin']}, SHIPPABLE {ship or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
