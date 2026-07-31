# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""ADVERSARIAL RE-DERIVATION 1: does the shrinkage lane's fold fit reproduce PRODUCTION?

Production (efv_model.fit_production_stack / oos_grades):
    pool  = full labeled pool minus recent busts   (debuted + busts)
    model = max(-2.0, a + b * ridge)               (linear output calibration)
    cons  = max(0.0, ols(fv))                      (ols ALSO fit on the full pool)
Shrinkage lab (tools/_prem_shrink_lab.py::_fit_fold):
    pool  = DEBUTED ONLY (busts carry target=None and are filtered)
    model = ridge                                  (NO calibration)
    cons  = max(0.0, ols(fv))                      (ols fit on DEBUTED ONLY)

fit_production_stack's own docstring records this exact pair of defects as the
E-LAMBDA parity bug repaired 2026-07-15.

Read-only. Prints only.
"""
from __future__ import annotations
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import os; os.chdir(ROOT)

import efv_model as XM
from prospect_path import _spearman, _fit_ridge, _predict
from efv_model import (_fit_ols_fv, _pred_ols, blend_lambda, _feature_spec,
                       _prep, _fit_linear_calibration)
from efv_dataset import matrix_path

SCORED = XM.SCORED_YEARS


def load(side):
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    full = [r for r in rows if not (r["kind"] == "bust" and r.get("bust_recent"))]
    data = _prep(full, "target_censored", side)
    by = {r["player_key"]: r for r in full}
    for d in data:
        src = by[d["player_key"]]
        m = src.get("milb") if isinstance(src.get("milb"), dict) else {}
        d["kind"] = src["kind"]
        d["served"] = bool(m.get("milb_level"))
        d["milb"] = m
    return data


def run(side, lam, style):
    keys = _feature_spec(side)[0]
    data = load(side)
    out = []
    for yr in SCORED:
        tr = [r for r in data if r["decision_year"] < yr]
        te = [r for r in data if r["decision_year"] == yr]
        if style == "lab":
            tr = [r for r in tr if r["kind"] == "debuted"]
        if len(te) < 15 or len(tr) < 60:
            continue
        ridge = _fit_ridge(tr, keys)
        ols = _fit_ols_fv(tr)
        if not (ridge and ols):
            continue
        if style == "prod":
            cal = _fit_linear_calibration([(_predict(ridge, r["feats"]), r["target"]) for r in tr])
            a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
        else:
            a, b = 0.0, 1.0
        for r in te:
            cw = max(0.0, _pred_ols(ols, r["fv"]))
            if style == "prod":
                mw = max(-2.0, a + b * _predict(ridge, r["feats"]))
            else:
                mw = _predict(ridge, r["feats"])
            out.append({"pk": r["player_key"], "yr": yr, "kind": r["kind"],
                        "b": (1 - lam) * cw + lam * mw, "cw": cw, "mw": mw,
                        "y": r["target"], "served": r["served"],
                        "fv": r["fv"],
                        "a": a, "bcal": b})
    return out


def rho_deb(rows):
    sel = [x for x in rows if x["kind"] == "debuted"]
    return _spearman([x["b"] for x in sel], [x["y"] for x in sel]), len(sel)


def main():
    for side in ("hit",):
        print("=" * 92)
        print("SIDE", side, " shipped lambda", blend_lambda(side))
        for style in ("lab", "prod"):
            r = run(side, blend_lambda(side), style)
            cw = [x["cw"] for x in r]; mw = [x["mw"] for x in r]
            rr, n = rho_deb(r)
            print(f"\n  style={style:5s}  n_test={len(r):4d}  n_debuted={n}")
            print(f"    cons leg  mean {sum(cw)/len(cw):7.3f}  min {min(cw):7.3f} max {max(cw):7.3f}")
            print(f"    model leg mean {sum(mw)/len(mw):7.3f}  min {min(mw):7.3f} max {max(mw):7.3f}")
            print(f"    output calibration per fold a/b: "
                  f"{sorted({(round(x['a'],4), round(x['bcal'],4)) for x in r})}")
            print(f"    rho (debuted OOS) = {rr:.4f}")
        print("\n  LAMBDA SWEEP, rho on debuted OOS rows:")
        print(f"    {'lam':>5s} {'lab':>9s} {'prod':>9s}")
        for lam in (0.0, 0.2, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0):
            a = rho_deb(run(side, lam, "lab"))[0]
            b = rho_deb(run(side, lam, "prod"))[0]
            print(f"    {lam:5.2f} {a:9.4f} {b:9.4f}")


if __name__ == "__main__":
    raise SystemExit(main())
