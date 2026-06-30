# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""eFV experiment runner -- shared, deterministic, forward-chained compute for the
eFV improvement sweep. Reuses the SHIPPED model machinery (xfv_model._vec / _fit_ridge /
_fit_ols_fv / blend), so a 'gain' here is a real out-of-sample, leakage-clean gain on the
same protocol data/xfv_eval.json uses.

A variant is a dict:
  {"id": str, "side": "hit"|"pit",
   "features": [{"name": str, "expr": str}],   # expr over feats dict `f` (+ g,thr,math,max,min,abs)
   "lam": {"band": [lo,hi], "dip": float} | null,   # tier-aware trust (lower model weight in band)
   "target": "censored"|"resolved"|"war_per_year",
   "cohort": null|"ifa"|"college"|"hs"|"draft"}     # restrict the EVAL pool to one cohort

Run:  python tools/xfv_lab_runner.py SPECS.json OUT.json
Each result carries pooled-OOS Spearman + within-FV-tier (esp 45) + era split + per-cohort
+ per-year stability, vs the shipped-feature baseline for that side/target/cohort.
"""
from __future__ import annotations
import sys, json, math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import os; os.chdir(ROOT)

import storage
import xfv_model as XM
from prospect_path import _spearman, _fit_ridge, _predict
from xfv_model import _prep, _fit_ols_fv, _pred_ols, blend_lambda, _feature_spec, _decision_year, _vec
from xfv_dataset import matrix_path

SCORED_YEARS = XM.SCORED_YEARS
TARGET_SEASONS = 6


def _g(f, k): return float(f.get(k, 0.0) or 0.0)
def _thr(v, t): return 1.0 if v >= t else 0.0
_NS = {"g": _g, "thr": _thr, "math": math, "max": max, "min": min, "abs": abs}


def _load_acq():
    acq = {}
    with storage.connect() as con:
        for r in con.execute("SELECT player_key, method, year FROM acquisitions"):
            acq[r["player_key"]] = {"method": r["method"], "year": r["year"]}
    return acq


def _load_career_war():
    cw = {}
    with storage.connect() as con:
        for r in con.execute("SELECT player_key, payload_json FROM career_war"):
            try:
                seasons = (json.loads(r["payload_json"]) or {}).get("seasons") or {}
            except ValueError:
                continue
            vals = [float(v) for v in seasons.values()]
            if vals:
                cw[r["player_key"]] = (sum(vals), len(vals))
    return cw


def _cohort_of(pk, row, acq):
    a = acq.get(pk) or {}
    m = a.get("method")
    if m == "international_fa":
        return "ifa"
    if m == "draft":
        bd = row.get("birth_date"); yr = a.get("year")
        if bd and yr:
            try:
                age = int(yr) - int(str(bd)[:4])
                return "college" if age >= 21 else "hs"
            except (ValueError, TypeError):
                return "draft"
        return "draft"
    return "other"


def load_side(side):
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    deb = [r for r in rows if r["kind"] == "debuted"]
    acq, cw = _load_acq(), _load_career_war()
    out = []
    for r in deb:
        if r.get("target_censored") is None or r.get("consensus_fv_raw") is None:
            continue
        feats = _vec(r, side)
        pk = r["player_key"]
        coh = _cohort_of(pk, r, acq)
        feats["is_ifa"] = 1.0 if coh == "ifa" else 0.0
        feats["is_college"] = 1.0 if coh == "college" else 0.0
        feats["is_hs"] = 1.0 if coh == "hs" else 0.0
        c = cw.get(pk)
        wpy = (c[0] / c[1]) if (c and c[1]) else None
        out.append({
            "player_key": pk, "decision_year": _decision_year(r), "feats": feats,
            "fv": float(r["consensus_fv_raw"]), "weight": float(r.get("weight", 1.0)),
            "target_censored": float(r["target_censored"]),
            "target_resolved": float(r.get("target_resolved") if r.get("target_resolved") is not None else r["target_censored"]),
            "wpy": wpy, "cohort": coh, "censored": bool(r.get("censored")),
        })
    return out


_CACHE = {}
def data_for(side):
    if side not in _CACHE:
        _CACHE[side] = load_side(side)
    return _CACHE[side]


def _add_feats(feats, specs):
    if not specs:
        return feats
    f = dict(feats)
    for s in specs:
        try:
            f[s["name"]] = float(eval(s["expr"], {"__builtins__": {}}, {**_NS, "f": feats}))
        except Exception:
            f[s["name"]] = 0.0
    return f


def _tier(fv): return round(fv / 5) * 5


def _era(yr): return "<=2018" if yr <= 2018 else ("2019-2021" if yr <= 2021 else "2022-2023")


def run_variant(v):
    side = v.get("side", "hit")
    target = v.get("target", "censored")
    tkey = {"censored": "target_censored", "resolved": "target_resolved", "war_per_year": "wpy"}[target]
    specs = v.get("features") or []
    extra_keys = [s["name"] for s in specs]
    lam_cfg = v.get("lam")
    cohort = v.get("cohort")
    keys = _feature_spec(side)[0] + extra_keys

    rows = [r for r in data_for(side) if r.get(tkey) is not None]
    if cohort:
        rows = [r for r in rows if r["cohort"] == cohort]
    base_lam = blend_lambda(side)

    def lam_of(fv):
        if not lam_cfg:
            return base_lam
        lo, hi = lam_cfg["band"]
        return base_lam * (1 - lam_cfg["dip"]) if (lo <= fv < hi) else base_lam

    pooled, per_year = [], defaultdict(list)
    for yr in SCORED_YEARS:
        tr = [r for r in rows if r["decision_year"] < yr]
        te = [r for r in rows if r["decision_year"] == yr]
        if len(te) < 12 or len(tr) < 50:
            continue
        trf = [{"feats": _add_feats(r["feats"], specs), "target": r[tkey], "weight": r["weight"], "fv": r["fv"]} for r in tr]
        olst = [{"fv": r["fv"], "target": r[tkey]} for r in tr]
        ols = _fit_ols_fv(olst)
        ridge = _fit_ridge(trf, keys)
        if not (ols and ridge):
            continue
        for r in te:
            rp = _predict(ridge, _add_feats(r["feats"], specs))
            cw = max(0.0, _pred_ols(ols, r["fv"]))
            blend = (1 - lam_of(r["fv"])) * cw + lam_of(r["fv"]) * rp
            pooled.append((blend, r[tkey], r["fv"], r["cohort"]))
            per_year[yr].append((blend, r[tkey]))

    if len(pooled) < 30:
        return {"id": v.get("id"), "n": len(pooled), "spearman": None, "error": "too few rows"}

    sp = _spearman([a for a, _, _, _ in pooled], [b for _, b, _, _ in pooled])
    # within-tier
    byt = defaultdict(list)
    for pr, t, fv, _ in pooled:
        byt[_tier(fv)].append((pr, t))
    wsum = wn = 0; t45 = None
    per_tier = {}
    for tk, grp in byt.items():
        if len(grp) < 15:
            continue
        r = _spearman([a for a, _ in grp], [b for _, b in grp])
        if r is None:
            continue
        per_tier[tk] = {"n": len(grp), "rho": round(r, 4)}
        wsum += r * len(grp); wn += len(grp)
        if tk == 45:
            t45 = round(r, 4)
    # era
    bye = defaultdict(list)
    for yr, prs in per_year.items():
        bye[_era(yr)].extend(prs)
    era = {k: round(_spearman([a for a, _ in g], [b for _, b in g]), 4)
           for k, g in bye.items() if len(g) >= 15 and _spearman([a for a, _ in g], [b for _, b in g]) is not None}
    # per-cohort
    byc = defaultdict(list)
    for pr, t, fv, c in pooled:
        byc[c].append((pr, t))
    coh = {k: {"n": len(g), "rho": round(_spearman([a for a, _ in g], [b for _, b in g]), 4)}
           for k, g in byc.items() if len(g) >= 25 and _spearman([a for a, _ in g], [b for _, b in g]) is not None}
    # per-year stability (sign + values)
    pyr = {yr: round(_spearman([a for a, _ in g], [b for _, b in g]), 4)
           for yr, g in per_year.items() if len(g) >= 12 and _spearman([a for a, _ in g], [b for _, b in g]) is not None}

    return {"id": v.get("id"), "side": side, "target": target, "cohort": cohort,
            "n": len(pooled), "spearman": round(sp, 4),
            "within_tier_wm": round(wsum / wn, 4) if wn else None,
            "t45": t45, "per_tier": per_tier, "era": era, "per_cohort": coh, "per_year": pyr}


def baseline(side="hit", target="censored", cohort=None):
    return run_variant({"id": f"BASELINE:{side}:{target}:{cohort}", "side": side, "target": target, "cohort": cohort})


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        specs = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        results = [run_variant(v) for v in specs]
        Path(sys.argv[2]).write_text(json.dumps(results, indent=1), encoding="utf-8")
        print(f"wrote {sys.argv[2]} ({len(results)} variants)")
    else:
        # smoke test
        for side in ("hit", "pit"):
            b = baseline(side)
            print(f"BASELINE {side}: rho={b['spearman']} t45={b['t45']} wm={b['within_tier_wm']} "
                  f"era={b['era']} cohorts={ {k:v['rho'] for k,v in (b['per_cohort'] or {}).items()} }")
