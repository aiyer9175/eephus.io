# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""eFV improvement sweep (2026-07-18) -- five pre-registered arms.

Gates registered FIRST in docs/efv-2026-07-18/GATES.md (read it before editing
anything here; the vintage caveat there is binding). Arms:

  E-FWDCAL   forward-chained per-fold output calibration legs (eval measurement)
  E-RECENCY  recency-decay training weights (grid, fit-population change)
  E-IPCW     resolved-only + inverse-P(resolved) training weights (cap 5.0)
  E-STACK    forward-chained OOF simplex stacker over ridge/lgbm/comps (one attempt)
  E-HURDLE   full-pool two-stage P(contributor) x E[WAR|debut] head (+AUC)

Everything reuses the SHIPPED machinery (efv_model._prep/_vec/_fit_ridge/
_fit_ols_fv/_fit_lgbm_mono/_fit_comps) on the same forward-chained protocol as
data/xfv_eval.json, so a gain here is the same kind of gain the flagship gate
measures. No DB dependency: cohort flags ride the matrix rows; lambda is held at
the shipped live stamps (hit 0.70 / pit 0.61) so arm effects are unconfounded.

Run:  python tools/efv_improve_sweep_lab.py            # both sides, all arms
Artifact: data/xfv_improve_sweep_eval.json (committed win or lose).
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import os
os.chdir(ROOT)

import efv_model as XM
from efv_model import (_prep, _fit_ols_fv, _pred_ols, _feature_spec, _fit_lgbm_mono,
                       _pred_lgbm, _fit_comps, _pred_comps)
from prospect_path import _spearman, _fit_ridge, _predict, _fit_linear_calibration
from efv_dataset import matrix_path
from source_backtest import _auc

SCORED_YEARS = XM.SCORED_YEARS
# Shipped live lambda stamps (data/xfv.json meta as of 2026-07-15); held FIXED.
LAM = {"hit": 0.70, "pit": 0.61}
OUT_PATH = ROOT / "data" / "xfv_improve_sweep_eval.json"

VINTAGE = {
    "matrix": "restored from git 13d7728^ (2026-07-14 post-label-repair, pre-2024-fold-unlock)",
    "rows": {},   # filled at load
    "db": "degraded local; cohort flags read from matrix rows, no career_war/acquisitions joins",
    "lambda": "held fixed at shipped stamps hit 0.70 / pit 0.61",
    "caveat": "PRELIMINARY screen -- any pass requires re-gate at canonical matrix vintage before ship",
}


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------

_CACHE: dict = {}


def load(side: str):
    if side in _CACHE:
        return _CACHE[side]
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    deb = [r for r in rows if r["kind"] == "debuted"]
    full = [r for r in rows if not (r["kind"] == "bust" and r.get("bust_recent"))]
    out = {
        "deb_km": _prep(deb, "target_censored", side),
        "full_km": _prep(full, "target_censored", side),
    }
    VINTAGE["rows"][side] = {"matrix": len(rows), "debuted": len(deb), "full_pool": len(full)}
    _CACHE[side] = out
    return out


def _tier(fv):
    return round(fv / 5) * 5


def _era_fold(yr):
    return "2019-2021" if yr <= 2021 else "2022-2023"


# ---------------------------------------------------------------------------
# shared scoring: pooled + tier + era + per-year splits from (pred, target, fv, yr)
# ---------------------------------------------------------------------------

def splits(recs):
    if len(recs) < 30:
        return {"n": len(recs), "error": "too few rows"}
    sp = _spearman([r[0] for r in recs], [r[1] for r in recs])
    mae = sum(abs(r[0] - r[1]) for r in recs) / len(recs)
    byt = defaultdict(list)
    for p, t, fv, yr in recs:
        byt[_tier(fv)].append((p, t))
    wsum = wn = 0
    t45 = None
    per_tier = {}
    for tk, grp in sorted(byt.items()):
        if len(grp) < 15:
            continue
        r = _spearman([a for a, _ in grp], [b for _, b in grp])
        if r is None:
            continue
        per_tier[str(tk)] = {"n": len(grp), "rho": round(r, 4)}
        wsum += r * len(grp)
        wn += len(grp)
        if tk == 45:
            t45 = round(r, 4)
    bye = defaultdict(list)
    byy = defaultdict(list)
    for p, t, fv, yr in recs:
        bye[_era_fold(yr)].append((p, t))
        byy[yr].append((p, t))
    era = {}
    for k, g in bye.items():
        if len(g) >= 15:
            r = _spearman([a for a, _ in g], [b for _, b in g])
            if r is not None:
                era[k] = round(r, 4)
    per_year = {}
    for yr, g in sorted(byy.items()):
        if len(g) >= 12:
            r = _spearman([a for a, _ in g], [b for _, b in g])
            if r is not None:
                per_year[str(yr)] = round(r, 4)
    return {"n": len(recs), "spearman": round(sp, 4), "mae": round(mae, 3),
            "within_tier_wm": round(wsum / wn, 4) if wn else None, "t45": t45,
            "per_tier": per_tier, "era": era, "per_year": per_year}


# ---------------------------------------------------------------------------
# fold engine -- one place that walks the forward chain; arms plug in via hooks
# ---------------------------------------------------------------------------

def folds(data, side, *, weight_fn=None, train_filter=None, fwdcal=False,
          legs=("baseline", "ridge", "blend")):
    """Walk SCORED_YEARS. weight_fn(row, fold_year) -> weight multiplier (or None to
    drop the row from the FIT); train_filter(row) -> bool for the fit population.
    fwdcal=True adds per-fold train-fit linear calibration to ridge/blend legs.
    Returns {leg: [(pred, target, fv, yr)]}."""
    keys, mono = _feature_spec(side)
    lam = LAM[side]
    out = defaultdict(list)
    for yr in SCORED_YEARS:
        train = [r for r in data if r["decision_year"] < yr]
        test = [r for r in data if r["decision_year"] == yr]
        if len(test) < 15 or len(train) < 60:
            continue
        fit_pool = [r for r in train if (train_filter is None or train_filter(r))]
        if weight_fn is not None:
            fit_pool2 = []
            for r in fit_pool:
                m = weight_fn(r, yr)
                if m is None:
                    continue
                rr = dict(r)
                rr["weight"] = r["weight"] * m
                fit_pool2.append(rr)
            fit_pool = fit_pool2
        if len(fit_pool) < 60:
            continue
        ols = _fit_ols_fv(train)          # consensus bar always fits on the FULL train
        ridge = _fit_ridge(fit_pool, keys)
        if not (ols and ridge):
            continue
        cal = None
        if fwdcal:
            cal = _fit_linear_calibration(
                [(_predict(ridge, r["feats"]), r["target"]) for r in fit_pool])
        a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
        for r in test:
            t, fv = r["target"], r["fv"]
            cons = max(0.0, _pred_ols(ols, fv))
            rp = _predict(ridge, r["feats"])
            rp_c = a + b * rp if fwdcal else rp
            if "baseline" in legs:
                out["baseline"].append((cons, t, fv, yr))
            if "ridge" in legs:
                out["ridge"].append((rp_c, t, fv, yr))
            if "blend" in legs:
                out["blend"].append(((1 - lam) * cons + lam * rp_c, t, fv, yr))
    return out


# ---------------------------------------------------------------------------
# E-FWDCAL
# ---------------------------------------------------------------------------

def arm_fwdcal(side):
    data = load(side)["deb_km"]
    raw = folds(data, side)
    calib = folds(data, side, fwdcal=True)
    base = splits(raw["baseline"])
    res = {
        "baseline": base,
        "blend_raw": splits(raw["blend"]),
        "ridge_raw": splits(raw["ridge"]),
        "blend_fwdcal": splits(calib["blend"]),
        "ridge_fwdcal": splits(calib["ridge"]),
    }
    bf = res["blend_fwdcal"]
    gate = {
        "mae_beats_baseline": bf.get("mae") is not None and bf["mae"] < base["mae"],
        "rho_beats_baseline": (bf.get("spearman") or -9) > (base.get("spearman") or 9e9 * -1),
        "rho_within_tolerance_of_raw_blend":
            (bf.get("spearman") or -9) >= (res["blend_raw"].get("spearman") or -9) - 0.002,
    }
    gate["pass"] = all(gate.values())
    res["gate"] = gate
    return res


# ---------------------------------------------------------------------------
# identity noise floor (duplicate-feature arm)
# ---------------------------------------------------------------------------

def noise_floor(side):
    data = load(side)["deb_km"]
    base = splits(folds(data, side)["blend"])
    keys, mono = _feature_spec(side)
    lam = LAM[side]
    out = []
    for yr in SCORED_YEARS:
        train = [r for r in data if r["decision_year"] < yr]
        test = [r for r in data if r["decision_year"] == yr]
        if len(test) < 15 or len(train) < 60:
            continue
        tr2 = [{**r, "feats": {**r["feats"], "fv_dup": r["feats"]["fv"]}} for r in train]
        ols = _fit_ols_fv(train)
        ridge = _fit_ridge(tr2, keys + ["fv_dup"])
        if not (ols and ridge):
            continue
        for r in test:
            f2 = {**r["feats"], "fv_dup": r["feats"]["fv"]}
            cons = max(0.0, _pred_ols(ols, r["fv"]))
            out.append(((1 - lam) * cons + lam * _predict(ridge, f2),
                        r["target"], r["fv"], yr))
    ident = splits(out)
    floor = abs((ident.get("spearman") or 0) - (base.get("spearman") or 0))
    return {"identity_rho": ident.get("spearman"), "base_rho": base.get("spearman"),
            "floor": round(floor, 4)}


# ---------------------------------------------------------------------------
# E-RECENCY
# ---------------------------------------------------------------------------

def arm_recency(side, floor):
    data = load(side)["deb_km"]
    base = splits(folds(data, side)["blend"])
    grid = {}
    for decay in (0.95, 0.90, 0.85, 0.80):
        def wf(r, yr, d=decay):
            return d ** max(0, (yr - 1) - r["decision_year"])
        grid[str(decay)] = splits(folds(data, side, weight_fn=wf)["blend"])
    best_key = max(grid, key=lambda k: grid[k].get("spearman") or -9)
    best = grid[best_key]
    bar = max(0.005, 2 * floor)
    era_ok = all((best.get("era", {}).get(k, -9) >= base.get("era", {}).get(k, -9) - 0.010)
                 for k in base.get("era", {}))
    yrs_down = sum(1 for k, v in base.get("per_year", {}).items()
                   if best.get("per_year", {}).get(k, -9) < v)
    gate = {
        "pooled_gain": round((best.get("spearman") or 0) - (base.get("spearman") or 0), 4),
        "pooled_bar": bar,
        "pooled_ok": (best.get("spearman") or -9) >= (base.get("spearman") or 0) + bar,
        "wm_ok": (best.get("within_tier_wm") or -9) >= (base.get("within_tier_wm") or 0) - 0.003,
        "t45_ok": (best.get("t45") if best.get("t45") is not None else -9)
                  >= ((base.get("t45") or 0) - 0.003),
        "era_ok": era_ok,
        "per_year_ok": yrs_down <= 1,
    }
    gate["pass"] = all(v for k, v in gate.items() if k.endswith("_ok"))
    return {"baseline_blend": base, "grid": grid, "best_decay": best_key, "gate": gate}


# ---------------------------------------------------------------------------
# E-IPCW
# ---------------------------------------------------------------------------

def _fv_band(fv):
    return "lo" if fv <= 42.5 else ("mid" if fv < 55 else "hi")


def _yr_band(yr):
    return "<=2017" if yr <= 2017 else ("2018-19" if yr <= 2019 else
                                        ("2020-21" if yr <= 2021 else "2022+"))


def arm_ipcw(side, floor):
    data = load(side)["deb_km"]
    base = splits(folds(data, side)["blend"])
    # resolved = weight 1.0 rows (observed_seasons==6); censored rows carry weight<1
    CAP = 5.0

    def make_wf(train_rows):
        cells = defaultdict(lambda: [0, 0])
        for r in train_rows:
            c = (_yr_band(r["decision_year"]), _fv_band(r["fv"]))
            cells[c][1] += 1
            if r["weight"] >= 0.999:
                cells[c][0] += 1
        p = {c: (n_res / n if n else 1.0) for c, (n_res, n) in cells.items()}

        def wf(r, yr):
            if r["weight"] < 0.999:      # censored -> dropped under IPCW
                return None
            pr = p.get((_yr_band(r["decision_year"]), _fv_band(r["fv"])), 1.0)
            return min(CAP, 1.0 / max(pr, 1e-6)) / max(r["weight"], 1e-6)
        return wf

    # per-fold probabilities: recompute inside folds() via a closure keyed on fold year
    # folds() passes (row, fold_year); we rebuild the cell table lazily per fold year.
    tables = {}

    def wf(r, yr):
        if yr not in tables:
            train_rows = [x for x in data if x["decision_year"] < yr]
            tables[yr] = make_wf(train_rows)
        return tables[yr](r, yr)

    res = splits(folds(data, side, weight_fn=wf)["blend"])
    bar = max(0.005, 2 * floor)
    era_ok = all((res.get("era", {}).get(k, -9) >= base.get("era", {}).get(k, -9) - 0.010)
                 for k in base.get("era", {}))
    yrs_down = sum(1 for k, v in base.get("per_year", {}).items()
                   if res.get("per_year", {}).get(k, -9) < v)
    gate = {
        "pooled_gain": round((res.get("spearman") or 0) - (base.get("spearman") or 0), 4),
        "pooled_ok": (res.get("spearman") or -9) >= (base.get("spearman") or 0) + bar,
        "wm_ok": (res.get("within_tier_wm") or -9) >= (base.get("within_tier_wm") or 0) - 0.003,
        "t45_ok": (res.get("t45") if res.get("t45") is not None else -9)
                  >= ((base.get("t45") or 0) - 0.003),
        "era_ok": era_ok,
        "per_year_ok": yrs_down <= 1,
    }
    gate["pass"] = all(v for k, v in gate.items() if k.endswith("_ok"))
    return {"baseline_blend": base, "ipcw_blend": res, "cap": CAP, "gate": gate}


# ---------------------------------------------------------------------------
# E-STACK
# ---------------------------------------------------------------------------

def arm_stack(side):
    data = load(side)["deb_km"]
    keys, mono = _feature_spec(side)
    base = splits(folds(data, side)["blend"])
    recs = []
    for yr in SCORED_YEARS:
        train = [r for r in data if r["decision_year"] < yr]
        test = [r for r in data if r["decision_year"] == yr]
        if len(test) < 15 or len(train) < 60:
            continue
        # inner OOF over train years (forward-chained inside the fold)
        inner_years = sorted({r["decision_year"] for r in train})
        oof = []
        for iy in inner_years:
            itr = [r for r in train if r["decision_year"] < iy]
            ite = [r for r in train if r["decision_year"] == iy]
            if len(itr) < 60 or len(ite) < 10:
                continue
            ir = _fit_ridge(itr, keys)
            ig = _fit_lgbm_mono(itr, keys, mono)
            ic = _fit_comps(itr, keys)
            if not (ir and ig and ic):
                continue
            for r in ite:
                oof.append((_predict(ir, r["feats"]), _pred_lgbm(ig, r["feats"]),
                            _pred_comps(ic, r["feats"])[0], r["target"]))
        if len(oof) < 60:
            continue
        # coarse non-negative simplex grid, step 0.05, deterministic tie-break
        best_w, best_mae = (1.0, 0.0, 0.0), None
        steps = [i * 0.05 for i in range(21)]
        for w1 in steps:
            for w2 in steps:
                w3 = 1.0 - w1 - w2
                if w3 < -1e-9:
                    continue
                mae = sum(abs(w1 * a + w2 * b + max(0.0, w3) * c - t)
                          for a, b, c, t in oof) / len(oof)
                if best_mae is None or mae < best_mae - 1e-12:
                    best_mae, best_w = mae, (w1, w2, max(0.0, w3))
        fr = _fit_ridge(train, keys)
        fg = _fit_lgbm_mono(train, keys, mono)
        fc = _fit_comps(train, keys)
        ols = _fit_ols_fv(train)
        if not (fr and fg and fc and ols):
            continue
        lam = LAM[side]
        w1, w2, w3 = best_w
        for r in test:
            stacked = (w1 * _predict(fr, r["feats"]) + w2 * _pred_lgbm(fg, r["feats"])
                       + w3 * _pred_comps(fc, r["feats"])[0])
            cons = max(0.0, _pred_ols(ols, r["fv"]))
            recs.append(((1 - lam) * cons + lam * stacked, r["target"], r["fv"], yr))
    res = splits(recs)
    gate = {
        "pooled_gain": round((res.get("spearman") or 0) - (base.get("spearman") or 0), 4),
        "pooled_ok": (res.get("spearman") or -9) >= (base.get("spearman") or 0) + 0.0046,
        "wm_ok": (res.get("within_tier_wm") or -9) >= (base.get("within_tier_wm") or 0) - 0.0023,
        "t45_ok": (res.get("t45") if res.get("t45") is not None else -9)
                  >= ((base.get("t45") or 0) - 0.0023),
    }
    gate["pass"] = all(v for k, v in gate.items() if k.endswith("_ok"))
    return {"baseline_blend": base, "stack_blend": res, "gate": gate}


# ---------------------------------------------------------------------------
# E-HURDLE
# ---------------------------------------------------------------------------

def _fit_logistic(rows, keys, label_fn, l2=1.0, iters=25):
    import numpy as np
    X = np.array([[r["feats"].get(k, 0.0) for k in keys] for r in rows])
    y = np.array([1.0 if label_fn(r) else 0.0 for r in rows])
    w = np.array([float(r.get("weight", 1.0) or 1.0) for r in rows])
    mu, sd = X.mean(axis=0), X.std(axis=0)
    sd[sd == 0] = 1.0
    Xs = np.hstack([np.ones((len(rows), 1)), (X - mu) / sd])
    beta = np.zeros(Xs.shape[1])
    for _ in range(iters):
        z = Xs @ beta
        p = 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))
        g = Xs.T @ (w * (y - p)) - l2 * np.r_[0.0, beta[1:]]
        s = w * p * (1 - p) + 1e-9
        H = (Xs * s[:, None]).T @ Xs + l2 * np.eye(Xs.shape[1])
        H[0, 0] -= l2
        try:
            step = np.linalg.solve(H, g)
        except np.linalg.LinAlgError:
            break
        beta += step
        if float(np.abs(step).max()) < 1e-8:
            break
    return {"beta": beta, "mu": mu, "sd": sd, "keys": keys}


def _pred_logistic(m, feats):
    import numpy as np
    x = np.array([feats.get(k, 0.0) for k in m["keys"]])
    z = float(m["beta"][0] + ((x - m["mu"]) / m["sd"]) @ m["beta"][1:])
    return 1.0 / (1.0 + math.exp(-max(-30, min(30, z))))


def arm_hurdle(side):
    d = load(side)
    full = d["full_km"]
    keys, mono = _feature_spec(side)
    lam = LAM[side]
    CONTRIB = XM._CONTRIB_WAR
    recs = []   # (hurdle, blend, cons, target, fv, yr)
    for yr in SCORED_YEARS:
        train = [r for r in full if r["decision_year"] < yr]
        test = [r for r in full if r["decision_year"] == yr]
        if len(test) < 15 or len(train) < 60:
            continue
        deb_train = [r for r in train if r["kind"] == "debuted"]
        logit = _fit_logistic(train, keys, lambda r: r["target"] >= CONTRIB)
        ridge = _fit_ridge(deb_train, keys) if len(deb_train) >= 60 else None
        ols = _fit_ols_fv(train)
        if not (logit and ridge and ols):
            continue
        for r in test:
            p = _pred_logistic(logit, r["feats"])
            e = max(0.0, _predict(ridge, r["feats"]))
            cons = max(0.0, _pred_ols(ols, r["fv"]))
            blend = (1 - lam) * cons + lam * _predict(ridge, r["feats"])
            recs.append((p * e, blend, cons, r["target"], r["fv"], yr))
    if len(recs) < 30:
        return {"error": "too few rows", "n": len(recs)}
    hs = splits([(h, t, fv, yr) for h, _, _, t, fv, yr in recs])
    bs = splits([(b, t, fv, yr) for _, b, _, t, fv, yr in recs])
    cs = splits([(c, t, fv, yr) for _, _, c, t, fv, yr in recs])
    labels = [t >= CONTRIB for _, _, _, t, _, _ in recs]
    auc_h = _auc([h for h, *_ in recs], labels)
    auc_b = _auc([b for _, b, *_ in recs], labels)
    auc_c = _auc([c for _, _, c, *_ in recs], labels)
    gate = {
        "rho_vs_blend": round((hs.get("spearman") or 0) - (bs.get("spearman") or 0), 4),
        "rho_ok": (hs.get("spearman") or -9) >= (bs.get("spearman") or 0) + 0.005,
        "auc_gain_vs_blend": (round(auc_h - auc_b, 4)
                              if (auc_h is not None and auc_b is not None) else None),
        "auc_ok": (auc_h is not None and auc_b is not None and auc_h >= auc_b + 0.005),
        "beats_consensus_ok": (hs.get("spearman") or -9) > (cs.get("spearman") or -9),
    }
    gate["pass"] = all(v for k, v in gate.items() if k.endswith("_ok"))
    return {"full_pool": {"hurdle": hs, "blend": bs, "consensus": cs},
            "contributor_auc": {"hurdle": round(auc_h, 4) if auc_h is not None else None,
                                "blend": round(auc_b, 4) if auc_b is not None else None,
                                "consensus": round(auc_c, 4) if auc_c is not None else None},
            "gate": gate}


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    out = {"generated_at": date.today().isoformat(),
           "registration": "docs/efv-2026-07-18/GATES.md",
           "vintage": VINTAGE, "sides": {}}
    for side in ("hit", "pit"):
        load(side)
        nf = noise_floor(side)
        side_out = {"noise_floor": nf}
        print(f"[{side}] noise floor: {nf}")
        side_out["E_FWDCAL"] = arm_fwdcal(side)
        print(f"[{side}] E-FWDCAL gate: {side_out['E_FWDCAL']['gate']}")
        side_out["E_RECENCY"] = arm_recency(side, nf["floor"])
        print(f"[{side}] E-RECENCY gate: {side_out['E_RECENCY']['gate']}")
        side_out["E_IPCW"] = arm_ipcw(side, nf["floor"])
        print(f"[{side}] E-IPCW gate: {side_out['E_IPCW']['gate']}")
        side_out["E_STACK"] = arm_stack(side)
        print(f"[{side}] E-STACK gate: {side_out['E_STACK']['gate']}")
        side_out["E_HURDLE"] = arm_hurdle(side)
        print(f"[{side}] E-HURDLE gate: {side_out['E_HURDLE'].get('gate')}")
        out["sides"][side] = side_out
    OUT_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
