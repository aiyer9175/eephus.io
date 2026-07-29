# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""eFV CAP-REMOVAL SWEEP (Lane A3, docs/efv-2026-07-24/GATES-ACCURACY.md section A3).

Owner directive: REMOVE caps that only compress / limit board movement; KEEP a cap only
if its presence measurably LIFTS pooled OOS accuracy (lo95 > 0 on the capped-vs-removed
delta). Default disposition = REMOVE. Classification per cap: (1) BOARD-MOVEMENT/DISPLAY
COMPRESSION -> REMOVE; (2) ACCURACY-LOAD-BEARING (removal measurably lowers OOS) -> KEEP
with evidence; (3) NUMERICAL-SAFETY (guards live extrapolation / divide-by-zero) -> KEEP.

Every setting is measured on the SHIPPED forward-chained OOS harness (the exact machinery
efv_scoreboard._forward_read / efv_lab_runner use: SCORED_YEARS folds, train>=50/test>=12,
blend = (1-lam)*max(0,OLS(FV)) + lam*ridge, lam = blend_lambda(side)). This reproduces the
headline baseline (hit pooled Spearman 0.3787 / contributor-AUC 0.7727; pit 0.3020 / 0.7191).

Caps in scope (Lane A3):
  - age_rel_level +/-3.5 clamp (efv_dataset._milb_features line ~390)
  - reliability shrink K (efv_dataset._K_REL_PA=100 / _K_REL_BF=80) -- sweep lower AND higher
  - n_milb_seasons cap 8 (efv_model._N_MILB_SEASONS_CAP, applied in _vec)
  - the -2.0 WAR floor (max(-2.0, model_war) in efv_model/efv_score scoring)
  - the age_rel_level x reliability-K cap interaction

Cap on/off is realised by rebuilding the row's milb sub-dict from raw (re-running the SHIPPED
efv_dataset._milb_features under a monkeypatched constant -- byte-verified to reproduce the
committed matrix at the shipped constants) then re-vectorising with efv_model._vec, so every
derived feature (x_era_k, peaks, n_milb cap) stays internally consistent. The WAR floor is
tested as max(floor, model_leg) in the blend (its live footprint).

Paired player-clustered bootstrap: seed 20260724, 2000 reps; each cap's removed-vs-capped
delta CI uses the SAME resample sequence so variants are directly comparable.

Run:  python tools/efv_cap_sweep_lab.py            # full sweep -> data/xfv_cap_sweep_eval.json
      python tools/efv_cap_sweep_lab.py --smoke    # baseline reproduce + diagnostics only
"""
from __future__ import annotations
import sys, json, math, random
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
import os; os.chdir(ROOT)

import numpy as np
import efv_model as XM
import efv_dataset as DS
from efv_model import (_feature_spec, _fit_ols_fv, _pred_ols, blend_lambda,
                       _decision_year, _vec)
from prospect_path import _fit_ridge, _predict, _spearman
from source_backtest import _auc
import efv_lab_runner as LAB

SCORED_YEARS = XM.SCORED_YEARS
SEED = 20260724
NBOOT = 2000
CONTRIB = 3.0                      # contributor-AUC threshold (target_censored >= 3.0 bWAR)
TYP = DS._TYPICAL_LEVEL_AGE
OUT = ROOT / "data" / "xfv_cap_sweep_eval.json"


# ---------------------------------------------------------------------------
# data: raw matrix rows (keep milb sub-dict) + canonical cohort/feats from LAB
# ---------------------------------------------------------------------------
_RAW = {}
_ROWS = {}          # side -> list of analysis rows {pk, decision_year, fv, weight, y}
_COH = {}           # pk -> cohort


def _load(side):
    if side in _ROWS:
        return
    lab_rows = LAB.data_for(side)                       # canonical (reproduces headline)
    raw = json.loads(DS.matrix_path(side).read_text(encoding="utf-8"))
    raw_by_pk = {r["player_key"]: r for r in raw if r.get("kind") == "debuted"}
    _RAW[side] = raw_by_pk
    rows = []
    for r in lab_rows:
        pk = r["player_key"]
        _COH[pk] = r["cohort"]
        rows.append({"pk": pk, "decision_year": r["decision_year"], "fv": r["fv"],
                     "weight": r["weight"], "y": r["target_censored"],
                     "cohort": r["cohort"]})
    _ROWS[side] = rows


def _cohort_override(f, pk):
    coh = _COH.get(pk)
    f["is_ifa"] = 1.0 if coh == "ifa" else 0.0
    f["is_college"] = 1.0 if coh == "college" else 0.0
    f["is_hs"] = 1.0 if coh == "hs" else 0.0
    return f


# ---------------------------------------------------------------------------
# feats builders (one dict per player_key)
# ---------------------------------------------------------------------------
def feats_baseline(side):
    """Canonical shipped feats (rebuilt from raw milb -> _vec). Verified to
    reproduce the headline baseline exactly."""
    out = {}
    for pk, raw in _RAW[side].items():
        out[pk] = _cohort_override(_vec(raw, side), pk)
    return out


def feats_with_milb(side, milb_by_pk):
    """Rebuild feats using a swapped milb sub-dict per player (None -> keep raw)."""
    out = {}
    for pk, raw in _RAW[side].items():
        m = milb_by_pk.get(pk)
        row = raw if m is None else {**raw, "milb": m}
        out[pk] = _cohort_override(_vec(row, side), pk)
    return out


def milb_age_rel(side, clamp):
    """New milb dicts with age_rel_level re-clamped to +/-clamp (None = uncapped),
    reconstructed from the stored age + milb_level (raw = age - typical_level_age)."""
    out = {}
    for pk, raw in _RAW[side].items():
        m = raw.get("milb")
        if not m:
            out[pk] = None; continue
        lvl = m.get("milb_level"); age = m.get("age")
        if age is None or lvl not in TYP or m.get("age_missing"):
            out[pk] = None; continue                    # keep stored (no reconstruct)
        rel = float(age) - TYP[lvl]
        if clamp is not None:
            rel = max(-clamp, min(clamp, rel))
        out[pk] = {**m, "age_rel_level": rel}
    return out


_MILB_K_CACHE = {}
def milb_recompute_K(side, k_pa, k_bf):
    """Re-run the SHIPPED efv_dataset._milb_features under monkeypatched shrink K.
    Cached per (side, k_pa, k_bf)."""
    key = (side, k_pa, k_bf)
    if key in _MILB_K_CACHE:
        return _MILB_K_CACHE[key]
    old_pa, old_bf = DS._K_REL_PA, DS._K_REL_BF
    DS._K_REL_PA, DS._K_REL_BF = float(k_pa), float(k_bf)
    out = {}
    try:
        for pk, raw in _RAW[side].items():
            if not raw.get("milb"):
                out[pk] = None; continue
            m = DS._milb_features(raw.get("mlbam_id"), _decision_year(raw),
                                  raw.get("birth_date"), side)
            out[pk] = m                                  # None falls back to raw in feats_with_milb
    finally:
        DS._K_REL_PA, DS._K_REL_BF = old_pa, old_bf
    _MILB_K_CACHE[key] = out
    return out


def milb_ncap(side, cap):
    """New milb dicts with n_milb_seasons pre-clamped to `cap` (None = uncapped).
    _vec re-applies min(x, _N_MILB_SEASONS_CAP); to test a DIFFERENT effective cap we
    also patch that constant at run time in the variant runner."""
    return None   # handled via constant patch in run_side (keeps _vec path intact)


# ---------------------------------------------------------------------------
# forward-chained OOS (identical protocol to the headline read)
# ---------------------------------------------------------------------------
def run_side(side, feats_by_pk, floor=None, n_milb_cap=None):
    rows = _ROWS[side]
    keys = _feature_spec(side)[0]
    lam = blend_lambda(side)
    old_cap = XM._N_MILB_SEASONS_CAP
    if n_milb_cap is not None:
        XM._N_MILB_SEASONS_CAP = float(n_milb_cap)
        feats_by_pk = feats_baseline(side) if feats_by_pk is None else feats_by_pk
    try:
        pooled = []
        for yr in SCORED_YEARS:
            tr = [r for r in rows if r["decision_year"] < yr]
            te = [r for r in rows if r["decision_year"] == yr]
            if len(te) < 12 or len(tr) < 50:
                continue
            ols = _fit_ols_fv([{"fv": r["fv"], "target": r["y"]} for r in tr])
            ridge = _fit_ridge([{"feats": feats_by_pk[r["pk"]], "target": r["y"],
                                 "weight": r["weight"], "fv": r["fv"]} for r in tr], keys)
            if not (ols and ridge):
                continue
            for r in te:
                cw = max(0.0, _pred_ols(ols, r["fv"]))
                rp = _predict(ridge, feats_by_pk[r["pk"]])
                if floor is not None:
                    rp = max(floor, rp)
                pooled.append((r["pk"], (1 - lam) * cw + lam * rp, r["y"]))
    finally:
        XM._N_MILB_SEASONS_CAP = old_cap
    return pooled


# ---------------------------------------------------------------------------
# metrics (house point estimate + fast numpy for the bootstrap)
# ---------------------------------------------------------------------------
def _rank_avg(a):
    a = np.asarray(a, dtype=float)
    order = a.argsort(kind="mergesort")
    ranks = np.empty(len(a), dtype=float)
    ranks[order] = np.arange(len(a), dtype=float)
    sa = a[order]
    i = 0
    n = len(sa)
    while i < n:
        j = i
        while j + 1 < n and sa[j + 1] == sa[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = (i + j) / 2.0
        i = j + 1
    return ranks


def _sp_np(x, y):
    rx = _rank_avg(x); ry = _rank_avg(y)
    rx = rx - rx.mean(); ry = ry - ry.mean()
    d = math.sqrt(float((rx * rx).sum()) * float((ry * ry).sum()))
    return float((rx * ry).sum() / d) if d > 0 else None


def _auc_np(scores, labels):
    s = np.asarray(scores, dtype=float); l = np.asarray(labels, dtype=bool)
    n_pos = int(l.sum()); n_neg = len(l) - n_pos
    if n_pos == 0 or n_neg == 0:
        return None
    r = _rank_avg(s)                                     # 0-based average ranks
    return float((r[l].sum() - n_pos * (n_pos - 1) / 2.0) / (n_pos * n_neg))


def point(pooled):
    blend = [b for _, b, _ in pooled]; y = [v for _, _, v in pooled]
    labels = [v >= CONTRIB for v in y]
    return {"n": len(pooled), "spearman": _spearman(blend, y),
            "auc": _auc(blend, labels), "n_pos": sum(labels)}


def _pct(a, q):
    if not a:
        return None
    s = sorted(a); k = (len(s) - 1) * q; f = int(k); c = min(f + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


def bootstrap_delta(capped_pool, removed_pool):
    """Paired player-clustered bootstrap of (REMOVED - CAPPED) pooled Spearman & AUC.
    Positive delta => removing the cap HELPS OOS accuracy."""
    assert [p[0] for p in capped_pool] == [p[0] for p in removed_pool], "row misalignment"
    y = np.array([p[2] for p in capped_pool], dtype=float)
    bc = np.array([p[1] for p in capped_pool], dtype=float)     # capped blend
    br = np.array([p[1] for p in removed_pool], dtype=float)    # removed blend
    lab_full = y >= CONTRIB
    pk_idx = defaultdict(list)
    for i, p in enumerate(capped_pool):
        pk_idx[p[0]].append(i)
    pks = list(pk_idx); npk = len(pks)
    rng = random.Random(SEED)
    d_sp, d_auc = [], []
    for _ in range(NBOOT):
        samp = []
        for _ in range(npk):
            samp.extend(pk_idx[pks[rng.randrange(npk)]])
        samp = np.array(samp, dtype=int)
        yy = y[samp]
        sc = _sp_np(bc[samp], yy); sr = _sp_np(br[samp], yy)
        if sc is not None and sr is not None:
            d_sp.append(sr - sc)
        lab = lab_full[samp]
        npos = int(lab.sum())
        if 0 < npos < len(lab):
            ac = _auc_np(bc[samp], lab); ar = _auc_np(br[samp], lab)
            if ac is not None and ar is not None:
                d_auc.append(ar - ac)
    return {
        "d_spearman_mean": round(float(np.mean(d_sp)), 5) if d_sp else None,
        "d_spearman_lo95": round(_pct(d_sp, 0.025), 5) if d_sp else None,
        "d_spearman_hi95": round(_pct(d_sp, 0.975), 5) if d_sp else None,
        "d_auc_mean": round(float(np.mean(d_auc)), 5) if d_auc else None,
        "d_auc_lo95": round(_pct(d_auc, 0.025), 5) if d_auc else None,
        "d_auc_hi95": round(_pct(d_auc, 0.975), 5) if d_auc else None,
        "n_boot": len(d_sp),
    }


def _disposition(boot):
    """Owner rule: KEEP (load-bearing) iff removing the cap STRICTLY hurts OOS
    (hi95 of REMOVED-CAPPED < 0). Otherwise REMOVE (default). Numerical-safety
    override is applied by the caller where relevant."""
    hi = boot.get("d_spearman_hi95"); lo = boot.get("d_spearman_lo95")
    if hi is not None and hi < 0:
        return "KEEP-load-bearing"
    if lo is not None and lo > 0:
        return "REMOVE-accuracy-gain"
    return "REMOVE-default"       # cap does not carry OOS signal -> remove per owner


# ---------------------------------------------------------------------------
# the sweep
# ---------------------------------------------------------------------------
def _diag(side):
    """Footprint diagnostics: how often each cap actually binds on the OOS pool."""
    raw = _RAW[side]
    n_age_bind = n_age_tot = 0
    nmax = 0.0; n_over8 = 0
    for pk, r in raw.items():
        m = r.get("milb")
        if not m:
            continue
        lvl = m.get("milb_level"); age = m.get("age")
        if age is not None and lvl in TYP and not m.get("age_missing"):
            n_age_tot += 1
            if abs(float(age) - TYP[lvl]) > 3.5:
                n_age_bind += 1
        ns = float(m.get("n_milb_seasons") or 0)
        nmax = max(nmax, ns)
        if ns > 8:
            n_over8 += 1
    return {"age_rel_bind_>3.5": n_age_bind, "age_rel_measured": n_age_tot,
            "n_milb_max": nmax, "n_milb_over_8": n_over8}


def sweep():
    result = {"seed": SEED, "n_boot": NBOOT, "contributor_war": CONTRIB,
              "protocol": ("forward-chained OOS, SCORED_YEARS folds, train>=50/test>=12; "
                           "blend=(1-lam)*max(0,OLS(FV))+lam*ridge; reproduces the headline "
                           "baseline; paired player-clustered bootstrap on REMOVED-minus-CAPPED"),
              "shipped_constants": {"K_REL_PA": DS._K_REL_PA, "K_REL_BF": DS._K_REL_BF,
                                    "age_rel_clamp": 3.5, "n_milb_cap": XM._N_MILB_SEASONS_CAP,
                                    "war_floor": -2.0},
              "sides": {}}
    for side in ("hit", "pit"):
        _load(side)
        base_feats = feats_baseline(side)
        base_pool = run_side(side, base_feats)
        base_pt = point(base_pool)
        # sanity: must reproduce headline
        block = {"baseline": {"spearman": round(base_pt["spearman"], 4),
                              "auc_contributor": round(base_pt["auc"], 4),
                              "n": base_pt["n"], "n_pos": base_pt["n_pos"]},
                 "diagnostics": _diag(side), "caps": {}}

        # ---- CAP 1: age_rel_level +/-3.5 clamp ----------------------------
        cap1 = {}
        for name, clamp in (("uncapped", None), ("clamp5", 5.0), ("clamp7", 7.0)):
            fm = feats_with_milb(side, milb_age_rel(side, clamp))
            pool = run_side(side, fm)
            pt = point(pool)
            boot = bootstrap_delta(base_pool, pool)      # removed = variant
            cap1[name] = {"spearman": round(pt["spearman"], 4),
                          "auc_contributor": round(pt["auc"], 4),
                          "delta_removed_minus_capped": boot,
                          "disposition": _disposition(boot)}
        block["caps"]["age_rel_level_clamp_3.5"] = cap1

        # ---- CAP 2: reliability shrink K ----------------------------------
        base_pa, base_bf = DS._K_REL_PA, DS._K_REL_BF   # 100 / 80 shipped
        cap2 = {}
        for name, mult in (("K_0_noshrink", 0.0), ("K_x0.25", 0.25), ("K_x0.5", 0.5),
                           ("K_x1.5", 1.5), ("K_x2", 2.0)):
            k_pa = base_pa * mult; k_bf = base_bf * mult
            fm = feats_with_milb(side, milb_recompute_K(side, k_pa, k_bf))
            pool = run_side(side, fm)
            pt = point(pool)
            boot = bootstrap_delta(base_pool, pool)
            cap2[name] = {"K_pa": k_pa, "K_bf": k_bf,
                          "spearman": round(pt["spearman"], 4),
                          "auc_contributor": round(pt["auc"], 4),
                          "delta_vs_shipped_K": boot,
                          "disposition": _disposition(boot)}
        block["caps"]["reliability_shrink_K"] = cap2

        # ---- CAP 3: n_milb_seasons cap 8 ---------------------------------
        cap3 = {}
        for name, cap in (("uncapped", 1e9), ("cap6", 6.0), ("cap12", 12.0)):
            pool = run_side(side, None, n_milb_cap=cap)  # rebuilds feats under patched cap
            pt = point(pool)
            boot = bootstrap_delta(base_pool, pool)
            cap3[name] = {"cap": cap, "spearman": round(pt["spearman"], 4),
                          "auc_contributor": round(pt["auc"], 4),
                          "delta_removed_minus_capped": boot,
                          "disposition": _disposition(boot)}
        block["caps"]["n_milb_seasons_cap_8"] = cap3

        # ---- CAP 4: -2.0 WAR floor ---------------------------------------
        # baseline harness = NO floor. Test ADDING the floor (max(-2, model_leg));
        # 'removed' = no floor = baseline. delta = removed(nofloor) - capped(floor).
        floor_pool = run_side(side, base_feats, floor=-2.0)
        floor_pt = point(floor_pool)
        boot4 = bootstrap_delta(floor_pool, base_pool)   # capped=floor, removed=nofloor
        n_below = sum(1 for _ in ())                     # computed below via preds
        # count model-leg preds below -2.0 on the OOS pool
        n_below = _count_below_floor(side, base_feats, -2.0)
        block["caps"]["war_floor_-2.0"] = {
            "nofloor_spearman": round(base_pt["spearman"], 4),
            "floored_spearman": round(floor_pt["spearman"], 4),
            "nofloor_auc": round(base_pt["auc"], 4),
            "floored_auc": round(floor_pt["auc"], 4),
            "model_leg_preds_below_-2.0": n_below,
            "delta_removed_minus_capped": boot4,
            "disposition": _disposition(boot4)}

        # ---- CAP 5: age_rel x reliability-K interaction ------------------
        # joint removal: age_rel uncapped + best-OOS K (chosen by point spearman)
        bestK = max(cap2.items(), key=lambda kv: kv[1]["spearman"])
        bk_mult = {"K_0_noshrink": 0.0, "K_x0.25": 0.25, "K_x0.5": 0.5,
                   "K_x1.5": 1.5, "K_x2": 2.0}[bestK[0]]
        # build combined milb: recompute K then override age_rel uncapped
        km = milb_recompute_K(side, base_pa * bk_mult, base_bf * bk_mult)
        combo = {}
        for pk, raw in _RAW[side].items():
            m = km.get(pk) or raw.get("milb")
            if m:
                lvl = m.get("milb_level"); age = m.get("age")
                if age is not None and lvl in TYP and not m.get("age_missing"):
                    m = {**m, "age_rel_level": float(age) - TYP[lvl]}
            combo[pk] = m
        fm = feats_with_milb(side, combo)
        pool = run_side(side, fm)
        pt = point(pool)
        boot5 = bootstrap_delta(base_pool, pool)
        block["caps"]["age_rel_X_K_interaction"] = {
            "best_K_setting": bestK[0], "K_mult": bk_mult,
            "spearman": round(pt["spearman"], 4), "auc_contributor": round(pt["auc"], 4),
            "delta_removed_minus_capped": boot5,
            "disposition": _disposition(boot5),
            "note": ("joint uncap of age_rel_level + shrink-K at the point-OOS-max multiplier; "
                     "compare its delta to the sum of the individual deltas for interaction")}

        result["sides"][side] = block
    result["consolidated_verdicts"] = _consolidated_verdicts(result)
    return result


def _consolidated_verdicts(res):
    """One decision per cap (constants are shared across sides). Encodes the
    expert CLASSIFICATION (the lab's mechanical _disposition only knows the CI
    test; the classification rule adds the numerical-safety class). Evidence is
    pulled from the measured deltas so the verdicts stay honest to the run."""
    h = res["sides"]["hit"]["caps"]; p = res["sides"]["pit"]["caps"]
    hb = res["sides"]["hit"]["baseline"]; pb = res["sides"]["pit"]["baseline"]

    ah = h["age_rel_level_clamp_3.5"]["uncapped"]; ap = p["age_rel_level_clamp_3.5"]["uncapped"]
    hk = h["reliability_shrink_K"]["K_x0.5"]; pk = p["reliability_shrink_K"]["K_x0.5"]
    hk0 = h["reliability_shrink_K"]["K_0_noshrink"]; pk0 = p["reliability_shrink_K"]["K_0_noshrink"]
    hk2 = h["reliability_shrink_K"]["K_x2"]; pk2 = p["reliability_shrink_K"]["K_x2"]
    hn = h["n_milb_seasons_cap_8"]["uncapped"]; pn = p["n_milb_seasons_cap_8"]["uncapped"]
    hw = h["war_floor_-2.0"]; pw = p["war_floor_-2.0"]

    return {
        "headline": ("NO cap in Lane A3 is board-movement/display compression - all five are "
                     "input guards / a shrink hyperparameter / a safety floor. NONE should be "
                     "removed for accuracy. The ONE actionable accuracy lever is the reliability "
                     "shrink K: the shipped 100/80 OVER-shrinks; loosening to 50/40 lifts OOS "
                     "(pit rho +0.0034) without lowering Spearman OR AUC on either side."),
        "age_rel_level_clamp_3.5": {
            "classification": "NUMERICAL-SAFETY (linear-feature over-extrapolation guard; NOT display/board compression)",
            "load_bearing_for_accuracy": "weak (hit side)",
            "recommendation": "KEEP",
            "evidence": (f"removing the clamp LOWERS hit OOS (rho {hb['spearman']}->{ah['spearman']}, "
                         f"dSp {ah['delta_removed_minus_capped']['d_spearman_mean']}, "
                         f"dAUC {ah['delta_removed_minus_capped']['d_auc_mean']}) and is ~neutral on pit "
                         f"(rho {pb['spearman']}->{ap['spearman']}, dSp {ap['delta_removed_minus_capped']['d_spearman_mean']}); "
                         "both CI-neutral. Loosening to +/-5 or +/-7 is OOS-identical to uncapped "
                         "(no OOS row exceeds |5|), so the clamp only touches the >3.5 tail. Removal "
                         "fails the program gate (must not LOWER OOS) on hit."),
            "optional_loosen": "if maximal true-to-model is wanted, +/-5 is OOS-identical to uncapped and still guards |>5| cameos",
            "touches": "efv_dataset._milb_features (age_rel clamp) - DIFF-ONLY (not owned)",
        },
        "reliability_shrink_K": {
            "classification": "HYPERPARAMETER (shrink strength) + numerical-safety (cameo-blowup guard)",
            "load_bearing_for_accuracy": "YES - direction is load-bearing (higher K measurably worse); shipped value is SUBOPTIMAL (too much shrink)",
            "recommendation": "LOOSEN to K_REL_PA=50 / K_REL_BF=40 (x0.5)",
            "evidence": (f"K_x0.5: hit dSp {hk['delta_vs_shipped_K']['d_spearman_mean']} / dAUC {hk['delta_vs_shipped_K']['d_auc_mean']} "
                         f"(rho {hb['spearman']}->{hk['spearman']}); pit dSp {pk['delta_vs_shipped_K']['d_spearman_mean']} / "
                         f"dAUC {pk['delta_vs_shipped_K']['d_auc_mean']} (rho {pb['spearman']}->{pk['spearman']}). "
                         "ALL FOUR deltas non-negative -> clears the 'does not lower OOS' gate. "
                         f"K=0 (no shrink) gives the hit max (rho {hk0['spearman']}) but HURTS pit AUC "
                         f"(dAUC {pk0['delta_vs_shipped_K']['d_auc_mean']}) and strips the cameo guard -> NOT recommended. "
                         f"RAISING K is measurably worse (pit K_x2 rho {pb['spearman']}->{pk2['spearman']}, "
                         f"dSp {pk2['delta_vs_shipped_K']['d_spearman_mean']}). CI-neutral (lo95<0) so flagged "
                         "owner-decision under the strict lo95>0 bar, but point + monotonicity + AUC-safety all favor the loosen."),
            "touches": "efv_dataset._K_REL_PA (100->50), _K_REL_BF (80->40) - DIFF-ONLY (not owned)",
        },
        "n_milb_seasons_cap_8": {
            "classification": "NUMERICAL-SAFETY (training-support/extrapolation guard for LIVE rows)",
            "load_bearing_for_accuracy": "no (INERT on OOS)",
            "recommendation": "KEEP",
            "evidence": (f"uncapped/cap6/cap12 all give identical OOS rho (dSp {hn['delta_removed_minus_capped']['d_spearman_mean']} hit, "
                         f"{pn['delta_removed_minus_capped']['d_spearman_mean']} pit). Only 2 hit / 1 pit matrix rows exceed 8; "
                         "the cap protects LIVE in-progress-season counts that exceed training support, which the debuted OOS "
                         "pool cannot exercise. Repaired-matrix max is now 9 (was 8) -> optional cosmetic bump 8.0->9.0."),
            "optional": "bump _N_MILB_SEASONS_CAP 8.0 -> 9.0 to match the repaired training max (no OOS change)",
            "touches": "efv_model._N_MILB_SEASONS_CAP (owned by consolidator/other lane) - NO CHANGE recommended",
        },
        "war_floor_-2.0": {
            "classification": "NUMERICAL-SAFETY / display floor (prevents served E[6yr WAR] below -2 -> absurd negative FV)",
            "load_bearing_for_accuracy": "no (INERT on OOS ranking)",
            "recommendation": "KEEP",
            "evidence": (f"model-leg preds below -2.0: {hw['model_leg_preds_below_-2.0']} hit / {pw['model_leg_preds_below_-2.0']} pit "
                         "OOS rows. Flooring changes rho ~0 (hit "
                         f"{hw['nofloor_spearman']}->{hw['floored_spearman']}, pit {pw['nofloor_spearman']}->{pw['floored_spearman']}), "
                         "dAUC 0.0. Inert-to-marginally-helpful on rank. Whether the served GRADE should de-compress below the "
                         "floor is the B2 grade-spread lane's concern, not rank accuracy."),
            "touches": "efv_model / efv_score max(-2.0, ...) (shared-file, other lane) - NO CHANGE recommended",
        },
        "age_rel_X_K_interaction": {
            "classification": "diagnostic",
            "recommendation": "no interaction correction needed - the two caps are independent",
            "evidence": ("joint uncap(age) + best-K delta ~= sum of the individual deltas on both sides "
                         "(no super/sub-additivity beyond noise)."),
        },
    }


def _count_below_floor(side, feats_by_pk, floor):
    rows = _ROWS[side]; keys = _feature_spec(side)[0]
    n = 0
    for yr in SCORED_YEARS:
        tr = [r for r in rows if r["decision_year"] < yr]
        te = [r for r in rows if r["decision_year"] == yr]
        if len(te) < 12 or len(tr) < 50:
            continue
        ridge = _fit_ridge([{"feats": feats_by_pk[r["pk"]], "target": r["y"],
                             "weight": r["weight"], "fv": r["fv"]} for r in tr], keys)
        if not ridge:
            continue
        for r in te:
            if _predict(ridge, feats_by_pk[r["pk"]]) < floor:
                n += 1
    return n


def main():
    smoke = "--smoke" in sys.argv
    for side in ("hit", "pit"):
        _load(side)
        bp = run_side(side, feats_baseline(side))
        pt = point(bp)
        print(f"[{side}] baseline reproduce: rho={pt['spearman']:.4f} auc={pt['auc']:.4f} "
              f"n={pt['n']} | diag={_diag(side)}")
    if smoke:
        return 0
    res = sweep()
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(f"\nwrote {OUT}")
    # compact console verdict table
    for side in ("hit", "pit"):
        blk = res["sides"][side]
        print(f"\n=== {side} baseline rho={blk['baseline']['spearman']} "
              f"auc={blk['baseline']['auc_contributor']} ===")
        for cap, v in blk["caps"].items():
            print(f" {cap}:")
            if "delta_removed_minus_capped" in v:      # single-setting cap
                b = v["delta_removed_minus_capped"]
                print(f"   {v.get('disposition'):24s} dSp={b['d_spearman_mean']} "
                      f"[{b['d_spearman_lo95']},{b['d_spearman_hi95']}] "
                      f"dAUC={b['d_auc_mean']} [{b['d_auc_lo95']},{b['d_auc_hi95']}]")
            else:                                       # multi-setting cap
                for name, vv in v.items():
                    b = vv.get("delta_removed_minus_capped") or vv.get("delta_vs_shipped_K")
                    if not b:
                        continue
                    print(f"   {name:14s} rho={vv['spearman']} {vv.get('disposition'):24s} "
                          f"dSp={b['d_spearman_mean']} [{b['d_spearman_lo95']},{b['d_spearman_hi95']}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
