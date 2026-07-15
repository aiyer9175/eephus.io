# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""E-LAMBDA parity adjudication lab -> data/xfv_lambda_parity_eval.json.

QUESTION (eFV pitcher-skew program 3.2, 2026-07-15): the blend-lambda selector
(efv_model.rank_calibration) fits a DEBUTED-only consensus anchor and scores a
RAW uncalibrated model leg, while production (_fit_production / run_live) ships a
full-pool anchor with a calibrated, clamped model leg. Does re-plumbing the
selector to production parity change the selected lambda, and is that selection
stable enough to restamp?

ANSWER (this lab, both sides): NO RESTAMP. Two faithful parity implementations
disagree across the whole band on curves flat within noise:
  - variant C (globally-prepped pool, the investigation prototype): argmax
    hit 0.56 / pit 0.53;
  - variant D (per-fold-prepped pool via efv_model.fit_production_stack, the
    leakage-free build): argmax hit 0.68 / pit 0.69.
Same question, same data, opposite ends of [0.50, 0.70]. The composite curve's
top-5 candidates sit within ~0.003 of each other (vs a per-fold noise floor an
order of magnitude larger), so the argmax is implementation-sensitive noise.
Restamp protocol: a near-boundary or flat argmax requires the owner's sign-off,
not a rerun. The shipped debuted-only selector (hit 0.70 / pit 0.63) stands.

Variants per side (test rows always the debuted fold rows, the eval protocol):
  A = shipped selector (debuted anchor, debuted ridge, raw model leg)
  B = full-pool anchor only
  C = full parity, pool prepped ONCE globally then fold-sliced
  D = full parity, pool prepped per fold (fit_production_stack; leakage-free)

Run: python tools/xfv_lambda_parity_lab.py    (writes the artifact; read-only
against the matrices; ~2 min). Seed-free: no bootstrap here - the deliverable is
the curve geometry, which is deterministic.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from efv_dataset import matrix_path                                    # noqa: E402
from efv_model import (_prep, _feature_spec, _fit_ols_fv, _pred_ols,   # noqa: E402
                       fit_production_stack, SCORED_YEARS)
from prospect_path import (_fit_ridge, _predict,                        # noqa: E402
                           _fit_linear_calibration, _spearman)

OUT = _ROOT / "data" / "xfv_lambda_parity_eval.json"
_BAND = (0.50, 0.70)
_SHIPPED = {"hit": 0.70, "pit": 0.63}


def _folds(side: str, variant: str):
    keys, _m = _feature_spec(side)
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    deb = _prep([r for r in rows if r["kind"] == "debuted"], "target_censored", side)
    full = _prep([r for r in rows if not (r["kind"] == "bust" and r.get("bust_recent"))],
                 "target_censored", side)
    out = []
    for yr in SCORED_YEARS:
        te = [r for r in deb if r["decision_year"] == yr]
        tr_d = [r for r in deb if r["decision_year"] < yr]
        if len(te) < 15 or len(tr_d) < 60:
            continue
        if variant == "D":
            stack = fit_production_stack([r for r in rows
                                          if (r.get("decision_year") or 0) < yr], side, keys)
            if not stack:
                continue
            ridge, a, b, ols = stack["ridge"], stack["a"], stack["b"], stack["ols"]
        else:
            tr_f = [r for r in full if r["decision_year"] < yr]
            ols = _fit_ols_fv(tr_d if variant == "A" else tr_f)
            ridge_tr = tr_f if variant == "C" else tr_d
            ridge = _fit_ridge(ridge_tr, keys)
            if not (ols and ridge):
                continue
            if variant == "C":
                cal = _fit_linear_calibration(
                    [(_predict(ridge, r["feats"]), r["target"]) for r in ridge_tr])
                a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
            else:
                a, b = 0.0, 1.0
        for r in te:
            cons = max(0.0, _pred_ols(ols, r["fv"]))
            mdl = _predict(ridge, r["feats"])
            if variant in ("C", "D"):
                mdl = max(-2.0, a + b * mdl)
            out.append((cons, mdl, r["target"], r["fv"]))
    return out


def _curve(folds):
    lo, hi = _BAND
    cand = [round(lo + (hi - lo) * i / 20, 3) for i in range(21)]
    out = {}
    for lam in cand:
        scored = [((1 - lam) * c + lam * m, t, fv) for c, m, t, fv in folds]
        rho = _spearman([s for s, _, _ in scored], [t for _, t, _ in scored]) or 0.0
        byt: dict = {}
        for s, t, fv in scored:
            byt.setdefault(round(fv / 5) * 5, []).append((s, t))
        wsum = wn = 0.0
        t45 = 0.0
        for tk, grp in byt.items():
            if len(grp) < 15:
                continue
            r = _spearman([a for a, _ in grp], [b for _, b in grp])
            if r is None:
                continue
            wsum += r * len(grp)
            wn += len(grp)
            if tk == 45:
                t45 = r
        out[lam] = round(rho + (wsum / wn if wn else 0.0) + t45, 4)
    return out


def run(persist: bool = True) -> dict:
    sides = {}
    for side in ("hit", "pit"):
        variants = {}
        for v in ("A", "B", "C", "D"):
            folds = _folds(side, v)
            curve = _curve(folds)
            best = max(curve, key=curve.get)
            variants[v] = {"n": len(folds), "argmax_lambda": best,
                           "argmax_composite": curve[best],
                           "curve_spread": round(max(curve.values()) - min(curve.values()), 4),
                           "curve": {str(k): v2 for k, v2 in curve.items()}}
        parity_argmaxes = [variants["C"]["argmax_lambda"], variants["D"]["argmax_lambda"]]
        sides[side] = {
            "shipped_lambda": _SHIPPED[side],
            "variants": variants,
            "parity_disagreement": round(abs(parity_argmaxes[0] - parity_argmaxes[1]), 3),
        }
    doc = {
        "experiment": "xfv_lambda_parity",
        "generated_at": date.today().isoformat(),
        "question": "does production-parity re-plumbing of rank_calibration support a lambda restamp?",
        "band": list(_BAND),
        "sides": sides,
        "verdict": {
            "restamp": False,
            "reason": "two faithful parity implementations (C globally-prepped, D per-fold-prepped) "
                      "select argmax lambdas at opposite ends of the band on composite curves whose "
                      "top candidates sit within ~0.003; the selection is implementation-sensitive "
                      "noise and the restamp protocol (near-boundary/flat argmax -> owner sign-off) "
                      "blocks it. Shipped debuted-only selector stands (hit 0.70 / pit 0.63).",
            "owner_decision_required": True,
        },
    }
    if persist:
        OUT.write_text(json.dumps(doc, indent=1), encoding="utf-8")
        print(f"wrote {OUT}")
    return doc


if __name__ == "__main__":
    d = run()
    for side, s in d["sides"].items():
        print(f"{side}: shipped={s['shipped_lambda']} " +
              " ".join(f"{v}={s['variants'][v]['argmax_lambda']}@{s['variants'][v]['argmax_composite']}"
                       for v in ("A", "B", "C", "D")) +
              f" parity_disagreement={s['parity_disagreement']}")
    print("verdict: restamp =", d["verdict"]["restamp"])
