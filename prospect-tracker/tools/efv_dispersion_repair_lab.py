# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""C-1: fit and gate the rank-preserving level correction for Defect A.

Pre-registration: docs/efv-2026-08-13/DISPERSION_REPAIR_GATE.md, which copies its
three PASS conditions from the 2026-07-29 pre-registration rather than inventing
new ones.

The defect: `xfv_war_6yr` is over-dispersed out of fold, OLS slope of realized on
predicted 0.654 hit / 0.587 pit against a calibrated 1.0. The served value is
`clamp(-2, a + b*ridge)` where (a, b) are fitted on that fold's TRAINING rows, and
an in-sample calibration does not transfer: out of fold the predictions spread
wider than the outcomes.

The repair is an affine, strictly increasing map fitted LEAVE-ONE-FOLD-OUT, so no
row contributes to the correction applied to it. A global in-sample refit would
report slope 1.0 by construction and prove nothing.

Reuses `tools/_sweep_calib_shrink.py`'s pool construction verbatim so the parity
check against the registered numbers is meaningful.

Usage:
    python tools/efv_dispersion_repair_lab.py [B]      # default 2000
"""
from __future__ import annotations

import importlib.util as _ilu
import json
import random
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

_spec = _ilu.spec_from_file_location("_sweep_calib_gate", str(HERE / "_sweep_calib_gate.py"))
G = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(G)

import efv_model as M                                                      # noqa: E402
from prospect_path import _fit_ridge, _predict, _fit_linear_calibration    # noqa: E402

SIDES = ("hit", "pit")
FLOOR = -2.0
ART = ROOT / "data" / "xfv_dispersion_repair_eval.json"

#: The registered uncorrected slopes this lane must reproduce before it is
#: allowed to report a corrected one (data/xfv_pred_dispersion_eval.json,
#: 2026-07-25). Tolerance is loose because the corpus moves between vintages;
#: the check is that we are measuring the same quantity, not the same day.
PARITY = {"hit": 0.6540, "pit": 0.5868}
PARITY_TOL = 0.12


def _pool(data, keys, folds, perm_pred=False, perm_war=False, rng=None):
    """`_sweep_calib_shrink.legs`, plus the PRE-clamp value and the fold id.

    The pre-clamp value matters: clamp(-2, .) is flat below the floor, so rows
    pinned there are TIED, and a correction that lifts them off the floor breaks
    those ties. Carrying both lets the lane attribute any Spearman movement to
    the clamp rather than to the affine map, which is rank-preserving.
    """
    out = []
    for yr in folds:
        tr = [r for r in data if r["decision_year"] < yr]
        te = [r for r in data if r["decision_year"] == yr]
        if len(te) < 15 or len(tr) < 60:
            continue
        ols = M._fit_ols_fv(tr)
        ridge = _fit_ridge(tr, keys)
        if not (ols and ridge):
            continue
        cal = _fit_linear_calibration([(_predict(ridge, r["feats"]), r["target"]) for r in tr])
        a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
        rows = []
        for r in te:
            raw = a + b * _predict(ridge, r["feats"])
            rows.append({"fold": yr, "raw": raw, "xfv_war": max(FLOOR, raw),
                         "war": r["target"], "has_milb": r["has_milb"]})
        if perm_pred:
            v = [p["raw"] for p in rows]
            rng.shuffle(v)
            for p, x in zip(rows, v):
                p["raw"] = x
                p["xfv_war"] = max(FLOOR, x)
        if perm_war:
            v = [p["war"] for p in rows]
            rng.shuffle(v)
            for p, x in zip(rows, v):
                p["war"] = x
        out.extend(rows)
    return out


def _slope(xs, ys):
    if len(xs) < 20:
        return None
    mx, my = statistics.mean(xs), statistics.mean(ys)
    den = sum((x - mx) ** 2 for x in xs)
    return (sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den) if den else None


def _fit_affine(rows):
    """OLS of realized on predicted. Returns (a, b) mapping pred -> corrected."""
    xs = [r["raw"] for r in rows]
    ys = [r["war"] for r in rows]
    b = _slope(xs, ys)
    if b is None or b <= 0:
        return None
    a = statistics.mean(ys) - b * statistics.mean(xs)
    return a, b


def _apply_loo(rows):
    """Leave-one-fold-out affine correction. Returns rows with `corr` added."""
    folds = sorted({r["fold"] for r in rows})
    coefs = {}
    for f in folds:
        other = [r for r in rows if r["fold"] != f]
        ab = _fit_affine(other)
        if ab is None:
            return None, None
        coefs[f] = ab
    for r in rows:
        a, b = coefs[r["fold"]]
        r["corr"] = max(FLOOR, a + b * r["raw"])
        r["corr_unclamped"] = a + b * r["raw"]
    return rows, coefs


def _spearman(xs, ys):
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        rr = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                rr[order[k]] = avg
            i = j + 1
        return rr
    rx, ry = rank(xs), rank(ys)
    return _slope(rx, ry) and np.corrcoef(rx, ry)[0, 1]


def _mae(xs, ys):
    return float(np.mean([abs(x - y) for x, y in zip(xs, ys)]))


def _stat(rows):
    """Everything the gate needs from one pool."""
    if not rows or "corr" not in rows[0]:
        return {}
    war = [r["war"] for r in rows]
    pre = [r["xfv_war"] for r in rows]
    post = [r["corr"] for r in rows]
    n = len(rows)
    # tail = top decile of REALIZED war, the cell E2b and the 2026-06-25
    # recalibration both blew out
    cut = float(np.percentile(war, 90))
    tail = [i for i in range(n) if war[i] >= cut]
    return {
        "n": n,
        "slope_pre": _slope(pre, war),
        "slope_post": _slope(post, war),
        "spearman_pre": float(_spearman(pre, war)),
        "spearman_post": float(_spearman(post, war)),
        "mae_pre": _mae(pre, war),
        "mae_post": _mae(post, war),
        "tail_mae_pre": _mae([pre[i] for i in tail], [war[i] for i in tail]),
        "tail_mae_post": _mae([post[i] for i in tail], [war[i] for i in tail]),
        "tail_n": len(tail),
        "neg_pre": sum(1 for v in pre if v < 0),
        "neg_post": sum(1 for v in post if v < 0),
        "at_floor_pre": sum(1 for v in pre if v <= FLOOR + 1e-9),
        "at_floor_post": sum(1 for v in post if v <= FLOOR + 1e-9),
    }


def run(B: int = 2000, write: bool = True):
    data = {s: G.load_side(s) for s in SIDES}
    keys = {s: M._feature_spec(s)[0] for s in SIDES}

    point, coefs_out, parity = {}, {}, {}
    for s in SIDES:
        rows = _pool(data[s], keys[s], G.FOLDS)
        raw_slope = _slope([r["xfv_war"] for r in rows], [r["war"] for r in rows])
        parity[s] = {
            "registered": PARITY[s],
            "reproduced": round(raw_slope, 4) if raw_slope else None,
            "within_tol": bool(raw_slope is not None
                               and abs(raw_slope - PARITY[s]) <= PARITY_TOL),
            "tol": PARITY_TOL,
        }
        rows, coefs = _apply_loo(rows)
        if rows is None:
            raise SystemExit(f"ABORT: non-increasing correction on {s}")
        coefs_out[s] = {str(k): {"a": round(v[0], 5), "b": round(v[1], 5)}
                        for k, v in coefs.items()}
        if any(v[1] <= 0 for v in coefs.values()):
            raise SystemExit(f"ABORT: b_c <= 0 on {s}")
        point[s] = _stat(rows)

    if not all(parity[s]["within_tol"] for s in SIDES):
        raise SystemExit(f"ABORT: parity failed {parity}")

    rng = random.Random(G.SEED)
    npr = np.random.RandomState(G.SEED)
    draws = {s: defaultdict(list) for s in SIDES}
    zinfo = {s: defaultdict(list) for s in SIDES}
    pnull = {s: defaultdict(list) for s in SIDES}
    t0 = time.time()
    for it in range(B):
        for s in SIDES:
            d = data[s]
            boot = [d[i] for i in npr.randint(0, len(d), len(d))]
            for tgt, kw in ((draws, {}),
                            (zinfo, {"perm_pred": True, "rng": rng}),
                            (pnull, {"perm_war": True, "rng": rng})):
                rows = _pool(boot, keys[s], G.FOLDS, **kw)
                rows, _c = _apply_loo(rows)
                if rows is None:
                    continue
                for k, v in _stat(rows).items():
                    if v is not None:
                        tgt[s][k].append(v)
        if (it + 1) % 100 == 0:
            print(f"  {it+1}/{B}  {time.time()-t0:.0f}s", flush=True)

    def ci(vals):
        return G._ci(vals) if vals else None

    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "produced_by": "tools/efv_dispersion_repair_lab.py",
        "pre_registration": "docs/efv-2026-08-13/DISPERSION_REPAIR_GATE.md",
        "lane": "C-1 -- rank-preserving level correction of xfv_war_6yr (Defect A)",
        "correction": ("affine, strictly increasing, fitted LEAVE-ONE-FOLD-OUT so no row "
                       "contributes to the correction applied to it"),
        "folds": list(G.FOLDS),
        "bootstrap": {"B": B, "seed": G.SEED},
        "parity": parity,
        "loo_coefficients": coefs_out,
        "point": point,
        "boot_ci95": {s: {k: ci(v) for k, v in draws[s].items()} for s in SIDES},
        "zero_info_permuted_prediction_ci95": {s: {k: ci(v) for k, v in zinfo[s].items()}
                                               for s in SIDES},
        "permutation_null_permuted_outcome_ci95": {s: {k: ci(v) for k, v in pnull[s].items()}
                                                   for s in SIDES},
        "elapsed_s": round(time.time() - t0, 1),
    }

    # Adjudicate against the three pre-registered clauses.
    verdict = {}
    for s in SIDES:
        p = point[s]
        sl_ci = out["boot_ci95"][s].get("slope_post") or [None, None]
        c1 = bool(sl_ci[0] is not None and sl_ci[0] <= 1.0 <= sl_ci[1])
        d_rho = p["spearman_post"] - p["spearman_pre"]
        floor_rho = 0.0206 if s == "hit" else 0.0212
        c2 = bool(abs(d_rho) < floor_rho)
        c3 = bool(p["neg_post"] < p["neg_pre"] and p["at_floor_post"] < p["at_floor_pre"])
        tail_ok = bool(p["tail_mae_post"] <= p["tail_mae_pre"])
        verdict[s] = {
            "c1_slope_ci_covers_1": c1, "slope_post_ci95": sl_ci,
            "c2_spearman_unchanged_within_floor": c2,
            "d_spearman": round(d_rho, 5), "rho_floor": floor_rho,
            "c3_floor_no_longer_binds": c3,
            "added_clause_tail_mae_not_worse": tail_ok,
            "PASS": bool(c1 and c2 and c3 and tail_ok),
        }
    out["verdict"] = verdict
    out["overall"] = ("SHIP" if all(v["PASS"] for v in verdict.values())
                      else "SPLIT" if any(v["PASS"] for v in verdict.values())
                      else "NO_SHIP")

    if write:
        ART.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print("wrote", ART)
    print(json.dumps({k: out[k] for k in
                      ("parity", "point", "verdict", "overall")}, indent=1, default=str))
    return out


if __name__ == "__main__":
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 2000)
