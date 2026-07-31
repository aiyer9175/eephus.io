# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""SWEEP LANE calibration -- OOS dispersion of the served WAR prediction.

xfv_war_6yr (efv_score: xfv_war = a + b*ridge, the model leg) is the number that
realized_implied_fv inverts into xfv_grade, which in turn feeds p_bucket / p_bust.
If realized ~ a + b*pred has b < 1 out of fold, that prediction is OVER-DISPERSED
and every level statement read off it is stretched at both ends.

Same gate machinery: paired bootstrap (train AND test resampled, refit per draw),
zero-information control (row-permuted prediction), permutation null (row-permuted
outcome), 5 forward-chained time splits.
"""
from __future__ import annotations
import json, random, statistics, sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("_sweep_calib_gate", str(HERE / "_sweep_calib_gate.py"))
G = _ilu.module_from_spec(_spec); _spec.loader.exec_module(G)
import efv_model as M                      # noqa: E402
from prospect_path import _fit_ridge, _predict, _fit_linear_calibration  # noqa: E402

B = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
ART = ROOT / "data" / "xfv_pred_dispersion_eval.json"


def legs(data, side, keys, folds=G.FOLDS, perm_pred=False, perm_war=False, rng=None):
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
        pool = [{"xfv_war": max(-2.0, a + b * _predict(ridge, r["feats"])),
                 "cons_war": max(0.0, M._pred_ols(ols, r["fv"])),
                 "war": r["target"], "has_milb": r["has_milb"]} for r in te]
        if perm_pred:
            v = [p["xfv_war"] for p in pool]; rng.shuffle(v)
            for p, x in zip(pool, v):
                p["xfv_war"] = x
        if perm_war:
            v = [p["war"] for p in pool]; rng.shuffle(v)
            for p, x in zip(pool, v):
                p["war"] = x
        out.extend(pool)
    return out


def slope(rows, key):
    if len(rows) < 20:
        return None
    xs = [r[key] for r in rows]; ys = [r["war"] for r in rows]
    mx, my = statistics.mean(xs), statistics.mean(ys)
    den = sum((x - mx) ** 2 for x in xs)
    return (sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den) if den else None


def stat(rows):
    lm = [r for r in rows if r["has_milb"]]
    return {"slope_xfv_war": slope(rows, "xfv_war"),
            "slope_cons_war": slope(rows, "cons_war"),
            "lm_slope_xfv_war": slope(lm, "xfv_war"),
            "lm_slope_cons_war": slope(lm, "cons_war"), "n": len(rows), "lm_n": len(lm)}


def main():
    data = {s: G.load_side(s) for s in ("hit", "pit")}
    keys = {s: M._feature_spec(s)[0] for s in ("hit", "pit")}
    point = {s: stat(legs(data[s], s, keys[s])) for s in ("hit", "pit")}
    per_fold = {s: {str(y): stat(legs(data[s], s, keys[s], folds=(y,))) for y in G.FOLDS}
                for s in ("hit", "pit")}
    rng = random.Random(G.SEED); npr = np.random.RandomState(G.SEED)
    dr = {s: defaultdict(list) for s in ("hit", "pit")}
    ct = {s: defaultdict(list) for s in ("hit", "pit")}
    pn = {s: defaultdict(list) for s in ("hit", "pit")}
    for it in range(B):
        for s in ("hit", "pit"):
            d = data[s]
            boot = [d[i] for i in npr.randint(0, len(d), len(d))]
            for tgt, kw in ((dr, {}), (ct, {"perm_pred": True, "rng": rng}),
                            (pn, {"perm_war": True, "rng": rng})):
                for k, v in stat(legs(boot, s, keys[s], **kw)).items():
                    tgt[s][k].append(v)
        if (it + 1) % 200 == 0:
            print(f"  {it+1}/{B}", flush=True)
    art = {"generated_at": __import__("datetime").date.today().isoformat(),
           "lane": "calibration -- OOS dispersion of xfv_war_6yr",
           "statistic": "OLS slope of realized first-6yr WAR on the OOS prediction; "
                        "1.0 == calibrated in level, < 1.0 == over-dispersed",
           "folds": list(G.FOLDS), "bootstrap": {"B": B, "seed": G.SEED},
           "point": point, "per_fold": per_fold,
           "boot_ci95": {s: {k: G._ci(v) for k, v in dr[s].items()} for s in ("hit", "pit")},
           "zero_info_control_permuted_prediction_ci95":
               {s: {k: G._ci(v) for k, v in ct[s].items()} for s in ("hit", "pit")},
           "permutation_null_permuted_outcome_ci95":
               {s: {k: G._ci(v) for k, v in pn[s].items()} for s in ("hit", "pit")}}
    ART.write_text(json.dumps(art, indent=1), encoding="utf-8")
    print("wrote", ART)


if __name__ == "__main__":
    main()
