# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""eFV HIGH-END tail lab. Question (owner): can a tail fix improve eFV for the
best players (ex. Bobby Witt Jr.)?

The eFV rank gate is Spearman, which is INVARIANT to any monotone tail transform
- so a tail fix can only ever be a CALIBRATION (magnitude) change, not a rank
change. This harness measures, on the EXACT forward-chained leakage-clean
protocol data/xfv_eval.json uses (reusing efv_lab_runner's machinery):

  1. DIAGNOSIS - is the high end (true top FV tier + top predicted decile) over-
     or under-predicted vs realized first-6yr WAR? (mean residual, MAE, slope.)
  2. TAIL FIXES (all forward-chained: knee + factor fit on TRAIN, applied to
     TEST) - global linear calibration, tail-only expansion, tail-only
     compression, and a convex ramp (mirrors the FA mega-deal $/WAR tail idea).
  3. Each variant vs the shipped blend baseline on: high-end MAE + |bias|, AND
     the pooled / within-tier rank gate (must NOT regress).

SHIP RULE (honest, owner: "don't ship losses"): a variant ships ONLY if it
reduces high-end MAE AND |high-end bias| while pooled Spearman holds within
noise (>= baseline - 0.005) on BOTH sides. Otherwise it is a LOSS - reported,
never shipped.

Run:  python tools/xfv_tail_lab.py            # diagnosis + all variants, both sides
"""
from __future__ import annotations
import sys, json, math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import os; os.chdir(ROOT)

import efv_lab_runner as LAB
from efv_model import _fit_ols_fv, _pred_ols, blend_lambda, _feature_spec
from prospect_path import _spearman, _fit_ridge, _predict

SCORED_YEARS = LAB.SCORED_YEARS
HIGH_FV = 55.0          # "true top tier" cutoff (consensus FV >= 55)
TOP_Q = 0.85            # "top predicted" cutoff = 85th pct of predicted WAR


# ── forward-chained base predictions (the shipped blend) + per-fold train ─────
def _folds(side, target="censored"):
    tkey = {"censored": "target_censored", "resolved": "target_resolved", "war_per_year": "wpy"}[target]
    keys = _feature_spec(side)[0]
    rows = [r for r in LAB.data_for(side) if r.get(tkey) is not None]
    lam = blend_lambda(side)
    folds = []
    for yr in SCORED_YEARS:
        tr = [r for r in rows if r["decision_year"] < yr]
        te = [r for r in rows if r["decision_year"] == yr]
        if len(te) < 12 or len(tr) < 50:
            continue
        trf = [{"feats": r["feats"], "target": r[tkey], "weight": r["weight"], "fv": r["fv"]} for r in tr]
        ols = _fit_ols_fv([{"fv": r["fv"], "target": r[tkey]} for r in tr])
        ridge = _fit_ridge(trf, keys)
        if not (ols and ridge):
            continue

        def blend_of(r):
            rp = _predict(ridge, r["feats"])
            cw = max(0.0, _pred_ols(ols, r["fv"]))
            return (1 - lam) * cw + lam * rp

        train = [(blend_of(r), r[tkey], r["fv"]) for r in tr]
        test = [(blend_of(r), r[tkey], r["fv"], r["cohort"]) for r in te]
        folds.append({"train": train, "test": test})
    return folds


# ── tail-fix transforms: each returns a fn fit on TRAIN (pred,real) pairs ─────
def _fit_identity(train):
    return lambda p: p


def _fit_linear_cal(train):
    """Global per-fold OLS realized ~ a + b*pred (monotone -> preserves rank)."""
    ps = [p for p, _, _ in train]; os_ = [o for _, o, _ in train]
    n = len(ps); mp = sum(ps) / n; mo = sum(os_) / n
    var = sum((p - mp) ** 2 for p in ps)
    if var <= 0:
        return lambda p: p
    b = sum((p - mp) * (o - mo) for p, o in zip(ps, os_)) / var
    a = mo - b * mp
    b = max(0.0, b)            # keep monotone non-decreasing
    return lambda p: a + b * p


def _fit_tail_factor(train, knee_q, lo_g, hi_g):
    """Above the train knee K=quantile(pred,knee_q), match the mean realized:
    t(p) = p for p<=K else K + g*(p-K), g = (mean_real_above - K)/(mean_pred_above - K).
    g clamped to [lo_g, hi_g] (lo_g<1 compresses, hi_g>1 expands)."""
    ps = sorted(p for p, _, _ in train)
    if len(ps) < 20:
        return lambda p: p
    K = ps[min(len(ps) - 1, int(knee_q * len(ps)))]
    above = [(p, o) for p, o, _ in train if p > K]
    if len(above) < 8:
        return lambda p: p
    mp = sum(p for p, _ in above) / len(above)
    mo = sum(o for _, o in above) / len(above)
    denom = mp - K
    g = (mo - K) / denom if abs(denom) > 1e-6 else 1.0
    g = max(lo_g, min(hi_g, g))
    return lambda p: p if p <= K else K + g * (p - K)


VARIANTS = {
    "baseline":      _fit_identity,
    "linear_cal":    _fit_linear_cal,
    "tail_expand_q85": lambda tr: _fit_tail_factor(tr, 0.85, 1.0, 2.5),   # expansion-only
    "tail_shrink_q80": lambda tr: _fit_tail_factor(tr, 0.80, 0.3, 1.0),   # compression-only
    "tail_shrink_q70": lambda tr: _fit_tail_factor(tr, 0.70, 0.3, 1.0),
}


# ── metrics ───────────────────────────────────────────────────────────────
def _mae(pairs):
    return sum(abs(p - o) for p, o in pairs) / len(pairs) if pairs else None


def _calib_slope(pairs):
    n = len(pairs)
    if n < 8:
        return None
    mp = sum(p for p, _ in pairs) / n; mo = sum(o for _, o in pairs) / n
    var = sum((p - mp) ** 2 for p, _ in pairs)
    cov = sum((p - mp) * (o - mo) for p, o in pairs)
    return round(cov / var, 3) if var else None


def _high_end(pooled, by_pred_cut):
    """pooled = [(pred, real, fv)]. Returns metrics for FV>=HIGH_FV and top-pred."""
    fv_hi = [(p, o) for p, o, fv in pooled if fv >= HIGH_FV]
    top = [(p, o) for p, o, fv in pooled if p >= by_pred_cut]
    def block(pairs):
        if len(pairs) < 8:
            return {"n": len(pairs)}
        mp = sum(p for p, _ in pairs) / len(pairs)
        mo = sum(o for _, o in pairs) / len(pairs)
        return {"n": len(pairs), "mean_pred": round(mp, 2), "mean_real": round(mo, 2),
                "bias": round(mp - mo, 3), "mae": round(_mae(pairs), 3),
                "slope": _calib_slope(pairs)}
    return {"fv_ge_55": block(fv_hi), "top_pred": block(top)}


def evaluate(side, target="censored"):
    folds = _folds(side, target)
    # top-pred cutoff from ALL test preds (a fixed reporting cut, not used in fitting)
    all_test = [t for f in folds for t in f["test"]]
    preds_sorted = sorted(p for p, _, _, _ in all_test)
    cut = preds_sorted[min(len(preds_sorted) - 1, int(TOP_Q * len(preds_sorted)))]

    out = {}
    for name, fit in VARIANTS.items():
        pooled = []          # (t_pred, real, fv)
        per_tier = defaultdict(list)
        for f in folds:
            tfn = fit(f["train"])
            for p, o, fv, _ in f["test"]:
                tp = tfn(p)
                pooled.append((tp, o, fv))
                per_tier[round(fv / 5) * 5].append((tp, o))
        sp = _spearman([a for a, _, _ in pooled], [b for _, b, _ in pooled])
        wsum = wn = 0
        for tk, grp in per_tier.items():
            if len(grp) < 15:
                continue
            r = _spearman([a for a, _ in grp], [b for _, b in grp])
            if r is not None:
                wsum += r * len(grp); wn += len(grp)
        out[name] = {
            "n": len(pooled),
            "pooled_spearman": round(sp, 4) if sp is not None else None,
            "within_tier_wm": round(wsum / wn, 4) if wn else None,
            "overall_mae": round(_mae([(p, o) for p, o, _ in pooled]), 3),
            "overall_slope": _calib_slope([(p, o) for p, o, _ in pooled]),
            "high_end": _high_end(pooled, cut),
        }
    return out, round(cut, 2)


def _ship_decision(side_results):
    """A variant ships only if it cuts high-end MAE AND |bias| while holding the
    pooled rank gate (>= baseline - 0.005) on every side it is evaluated on."""
    decisions = {}
    names = [n for n in VARIANTS if n != "baseline"]
    for name in names:
        verdict = "LOSS"
        reasons = []
        ok = True
        for side, res in side_results.items():
            base = res["baseline"]; var = res[name]
            b_he = base["high_end"]["fv_ge_55"]; v_he = var["high_end"]["fv_ge_55"]
            if "mae" not in b_he or "mae" not in v_he:
                ok = False; reasons.append(f"{side}: high-end cohort too small"); continue
            rank_ok = (var["pooled_spearman"] is not None and base["pooled_spearman"] is not None
                       and var["pooled_spearman"] >= base["pooled_spearman"] - 0.005)
            mae_ok = v_he["mae"] < b_he["mae"]
            bias_ok = abs(v_he["bias"]) < abs(b_he["bias"])
            if not (rank_ok and mae_ok and bias_ok):
                ok = False
            reasons.append(f"{side}: rank {base['pooled_spearman']}->{var['pooled_spearman']} "
                           f"({'ok' if rank_ok else 'REGRESS'}); FV55+ MAE {b_he['mae']}->{v_he['mae']} "
                           f"({'better' if mae_ok else 'worse'}); |bias| {abs(b_he['bias'])}->{abs(v_he['bias'])} "
                           f"({'better' if bias_ok else 'worse'})")
        if ok:
            verdict = "SHIP"
        decisions[name] = {"verdict": verdict, "reasons": reasons}
    return decisions


if __name__ == "__main__":
    side_results = {}
    for side in ("hit", "pit"):
        res, cut = evaluate(side, "censored")
        side_results[side] = res
        print(f"\n========== {side.upper()}  (top-pred cut = {cut}, FV>=55 = top tier) ==========")
        for name, r in res.items():
            he55 = r["high_end"]["fv_ge_55"]; hetp = r["high_end"]["top_pred"]
            print(f"  {name:>16}: rho={r['pooled_spearman']} wm={r['within_tier_wm']} "
                  f"MAE={r['overall_mae']} slope={r['overall_slope']}")
            print(f"  {'':>16}    FV55+ (n={he55.get('n')}): pred={he55.get('mean_pred')} "
                  f"real={he55.get('mean_real')} bias={he55.get('bias')} MAE={he55.get('mae')} slope={he55.get('slope')}")
            print(f"  {'':>16}    topPred(n={hetp.get('n')}): pred={hetp.get('mean_pred')} "
                  f"real={hetp.get('mean_real')} bias={hetp.get('bias')} MAE={hetp.get('mae')}")
    print("\n========== SHIP DECISIONS ==========")
    for name, d in _ship_decision(side_results).items():
        print(f"  {name}: {d['verdict']}")
        for r in d["reasons"]:
            print(f"      {r}")
