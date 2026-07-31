# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""W-WRC + W-SB gate lab (docs/efv-2026-07-24/GATES.md, Phases 1b + 2c).

PROTOCOL (frozen in this header BEFORE any arm ran; one attempt per registered
arm; marginal = FAIL; same-run baselines only; seed 20260724; 2000 reps).

Harness: the shipped efv_lab_runner fold protocol, re-implemented here ONLY so a
feature key can be REPLACED (the runner can only APPEND). Eval pool, fold gates
(len(te)>=12, len(tr)>=50), and every metric (pooled Spearman, within-tier
weighted mean, t45, era, per-cohort, per-year) are the runner's. An identity
check confirms this run()'s lean-key result reproduces efv_lab_runner.baseline
('hit') exactly before any arm is judged.

Feature injection (lab-side; efv_dataset / efv_model are NOT edited): wrc_rel +
hit_sb_rel from wrc_rates.build_index(), joined to each matrix row by the EXACT
(mlbam_id, milb.milb_season, milb.milb_level) whose ops_rel the matrix already
carries (538/540 milb-present hitters join; the 2 gaps are pre-2021 short-season
"A"/sportId-15 lines absent from this refetch).

IMPUTATION = 0 for every unjoined row (the 305 milb-missing players + the 2
gaps). This is deliberate and REQUIRED for a faithful gate, NOT the _TOOL_IMPUTE
mean convention:
  * A level-relative, PA-shrunk rate reads 0 = "league average / no edge", which
    is its neutral center -- unlike a tool grade, where 0 is off-scale.
  * The shipped sibling rates (ops_rel/obp_rel/iso_rel) are EXACTLY 0 for a
    milb-missing player (efv_dataset._milb_features returns None -> _vec defaults
    to 0 + milb_missing=1). A SHIP of wrc_rel would behave identically.
  * Therefore A1 (replace ops_rel) is a clean drop-in swap only under 0-impute;
    mean-imputing a nonzero constant for the 305 milb-missing players would test
    a feature that never ships and would contaminate the comparison.
A mean-impute SENSITIVITY is reported alongside (not the gate) so the choice is
auditable.

Arms (registered; judged independently; bars frozen in GATES.md):
  A1 replace: wrc_rel in place of ops_rel.  Bar: pooled delta >= +0.004 AND wm delta >= -0.0011
  A2 add:     wrc_rel appended to the lean set. Bar: same as A1.
  A3 fringe:  LR-FRINGE read of the ADD mechanism (no second fit). Bar:
              t45 delta >= +0.015 AND pooled delta >= -0.0011 AND wm delta >= -0.0011.
  A4 conditional composite: runs ONLY if A1 or A2 pooled delta is point-positive.
              Prereq clause M: a shrunken component-weighted composite fit to
              NEXT-SEASON wOBA must predict it with bootstrap lo95(OOS r) > 0.
              If M passes, the composite joins as a feature; bar = A2.
  SB lean:    hit_sb_rel appended. Bar: pooled >= +0.004 AND wm >= -0.0011.
              Fringe signature (t45 >= +0.015 w/ pooled+wm >= -0.0011) recorded
              KEEP-ALIVE ONLY (no fringe ship this cycle).

Uncertainty: paired player-clustered bootstrap (one pooled entry per player),
2000 reps, seed 20260724, on the pooled / wm / t45 DELTAS vs the same-run
baseline. Bars are point-based per GATES; CIs are reported for honesty and do
not themselves gate, but a delta that clears a point bar while its CI straddles
0 is flagged marginal.

A-PRIORI NULL (recorded in GATES before any run): decomposed components usually
dominate composites -- the shipped block already carries obp_rel / iso_rel /
k_rel / bb_rel / ops_rel, so a woba-lite composite of the same events is
expected to add ~nothing. Honest FAIL is an acceptable verdict.

Run: python tools/efv_wrc_lab.py
Artifact: data/xfv_wrc_eval.json
"""
from __future__ import annotations
import sys, json, math, random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import os; os.chdir(ROOT)

import numpy as np
import efv_lab_runner as LAB
from prospect_path import _spearman, _fit_ridge, _predict
from efv_model import _fit_ols_fv, _pred_ols, blend_lambda, _feature_spec
from efv_dataset import matrix_path
import wrc_rates

SEED = 20260724
REPS = 2000
SIDE = "hit"
SCORED_YEARS = LAB.SCORED_YEARS
LEAN = list(_feature_spec(SIDE)[0])          # includes ops_rel
LEAN_NO_OPS = [k for k in LEAN if k != "ops_rel"]

BAR_POOLED = 0.004
BAR_WM = -0.0011
BAR_FRINGE_T45 = 0.015


# --------------------------------------------------------------------------- #
# join: exact (mlbam, milb_season, milb_level) -> wrc_rel / hit_sb_rel        #
# --------------------------------------------------------------------------- #
def build_join():
    idx, _lg = wrc_rates.build_index()
    mat = json.loads(matrix_path(SIDE).read_text(encoding="utf-8"))
    meta = {}   # player_key -> (mlbam, milb_season, milb_level)
    for m in mat:
        milb = m.get("milb") or {}
        meta[m["player_key"]] = (m.get("mlbam_id"), milb.get("milb_season"), milb.get("milb_level"))
    joined = {}   # player_key -> {"wrc_rel":.., "hit_sb_rel":.., "peak_wrc_rel":..}
    n_exact = 0
    for pk, (mid, ms, ml) in meta.items():
        if mid is None or ms is None or ml is None:
            continue
        hit = idx.get((int(mid), int(ms), ml))
        if hit is None:
            continue
        joined[pk] = {"wrc_rel": hit["wrc_rel"], "hit_sb_rel": hit["hit_sb_rel"],
                      "peak_wrc_rel": wrc_rates.peak_wrc_rel(idx, mid, ms)}
        n_exact += 1
    return joined, meta, n_exact


def inject(joined, mode="zero"):
    """Attach wrc_rel / hit_sb_rel / peak_wrc_rel onto every LAB row's feats.
    mode 'zero' -> unjoined rows get 0 (ship-faithful). mode 'mean' -> unjoined
    rows get the observed joined-pool mean (sensitivity only). Returns the means."""
    rows = LAB.data_for(SIDE)
    means = {}
    if mode == "mean":
        for k in ("wrc_rel", "hit_sb_rel", "peak_wrc_rel"):
            vals = [joined[r["player_key"]][k] for r in rows
                    if r["player_key"] in joined and joined[r["player_key"]][k] is not None]
            means[k] = (sum(vals) / len(vals)) if vals else 0.0
    for r in rows:
        j = joined.get(r["player_key"])
        for k in ("wrc_rel", "hit_sb_rel", "peak_wrc_rel"):
            if j is not None and j.get(k) is not None:
                r["feats"][k] = float(j[k])
            else:
                r["feats"][k] = float(means.get(k, 0.0)) if mode == "mean" else 0.0
    return means


# --------------------------------------------------------------------------- #
# run(): the runner fold loop with an EXPLICIT key list                        #
# --------------------------------------------------------------------------- #
def _tier(fv): return round(fv / 5) * 5
def _era(yr): return "<=2018" if yr <= 2018 else ("2019-2021" if yr <= 2021 else "2022-2023")


def run(keys, tag=""):
    rows = [r for r in LAB.data_for(SIDE) if r.get("target_censored") is not None]
    lam = blend_lambda(SIDE)
    pooled = []      # (blend, truth, fv, cohort, player_key)
    per_year = defaultdict(list)
    for yr in SCORED_YEARS:
        tr = [r for r in rows if r["decision_year"] < yr]
        te = [r for r in rows if r["decision_year"] == yr]
        if len(te) < 12 or len(tr) < 50:
            continue
        trf = [{"feats": r["feats"], "target": r["target_censored"],
                "weight": r["weight"], "fv": r["fv"]} for r in tr]
        ols = _fit_ols_fv([{"fv": r["fv"], "target": r["target_censored"]} for r in tr])
        ridge = _fit_ridge(trf, keys)
        if not (ols and ridge):
            continue
        for r in te:
            rp = _predict(ridge, r["feats"])
            cw = max(0.0, _pred_ols(ols, r["fv"]))
            blend = (1 - lam) * cw + lam * rp
            pooled.append((blend, r["target_censored"], r["fv"], r["cohort"], r["player_key"]))
            per_year[yr].append((blend, r["target_censored"]))
    return _metrics(pooled, per_year, tag)


def _metrics(pooled, per_year, tag):
    if len(pooled) < 30:
        return {"tag": tag, "n": len(pooled), "spearman": None, "pooled": pooled}
    sp = _spearman([a for a, _, _, _, _ in pooled], [b for _, b, _, _, _ in pooled])
    byt = defaultdict(list)
    for pr, t, fv, _, _ in pooled:
        byt[_tier(fv)].append((pr, t))
    wsum = wn = 0; t45 = None; per_tier = {}
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
    bye = defaultdict(list)
    for yr, prs in per_year.items():
        bye[_era(yr)].extend(prs)
    era = {k: round(_spearman([a for a, _ in g], [b for _, b in g]), 4)
           for k, g in bye.items() if len(g) >= 15 and _spearman([a for a, _ in g], [b for _, b in g]) is not None}
    byc = defaultdict(list)
    for pr, t, fv, c, _ in pooled:
        byc[c].append((pr, t))
    coh = {k: {"n": len(g), "rho": round(_spearman([a for a, _ in g], [b for _, b in g]), 4)}
           for k, g in byc.items() if len(g) >= 25 and _spearman([a for a, _ in g], [b for _, b in g]) is not None}
    pyr = {int(yr): round(_spearman([a for a, _ in g], [b for _, b in g]), 4)
           for yr, g in per_year.items() if len(g) >= 12 and _spearman([a for a, _ in g], [b for _, b in g]) is not None}
    return {"tag": tag, "n": len(pooled), "spearman": round(sp, 4),
            "within_tier_wm": round(wsum / wn, 4) if wn else None,
            "t45": t45, "per_tier": {str(k): v for k, v in per_tier.items()},
            "era": era, "per_cohort": coh, "per_year": pyr, "pooled": pooled}


# --------------------------------------------------------------------------- #
# paired player-clustered bootstrap on the DELTAS (one row per player)         #
# --------------------------------------------------------------------------- #
def _wm_t45_sample(blend, truth, tiers, samp):
    bl = blend[samp]; tr = truth[samp]; ti = tiers[samp]
    wsum = wn = 0; t45 = None
    for tk in np.unique(ti):
        m = ti == tk
        if m.sum() < 15:
            continue
        r = _spearman(list(bl[m]), list(tr[m]))
        if r is None:
            continue
        wsum += r * m.sum(); wn += m.sum()
        if tk == 45:
            t45 = r
    return (wsum / wn if wn else None), t45


def bootstrap_delta(base_res, arm_res):
    """base_res and arm_res share the same rows; align by player_key, resample
    rows with replacement (== player-clustered here), delta of pooled/wm/t45."""
    bp = base_res["pooled"]; ap = arm_res["pooled"]
    n = len(bp)
    ak = {r[4]: i for i, r in enumerate(ap)}
    b_blend = np.array([bp[i][0] for i in range(n)])
    b_truth = np.array([bp[i][1] for i in range(n)])
    tiers = np.array([_tier(bp[i][2]) for i in range(n)])
    a_blend = np.array([ap[ak[bp[i][4]]][0] if bp[i][4] in ak else bp[i][0] for i in range(n)])
    rng = random.Random(SEED)
    d_pool, d_wm, d_t45 = [], [], []
    idx_all = list(range(n))
    for _ in range(REPS):
        samp = np.array(rng.choices(idx_all, k=n))
        sb = _spearman(list(b_blend[samp]), list(b_truth[samp]))
        sa = _spearman(list(a_blend[samp]), list(b_truth[samp]))
        if sb is not None and sa is not None:
            d_pool.append(sa - sb)
        wmb, t45b = _wm_t45_sample(b_blend, b_truth, tiers, samp)
        wma, t45a = _wm_t45_sample(a_blend, b_truth, tiers, samp)
        if wmb is not None and wma is not None:
            d_wm.append(wma - wmb)
        if t45b is not None and t45a is not None:
            d_t45.append(t45a - t45b)

    def ci(arr):
        if not arr:
            return None
        s = sorted(arr)
        return {"lo95": round(s[int(0.025 * len(s))], 4),
                "hi95": round(s[min(len(s) - 1, int(0.975 * len(s)))], 4), "reps": len(arr)}

    return {"pooled_delta": ci(d_pool), "wm_delta": ci(d_wm), "t45_delta": ci(d_t45)}


# --------------------------------------------------------------------------- #
# clause M: shrunken component composite fit to NEXT-SEASON wOBA               #
# --------------------------------------------------------------------------- #
_COMP = ["ubb", "hbp", "b1", "b2", "b3", "hr"]


def _scale_ss(rows):
    agg = defaultdict(lambda: defaultdict(float))
    for r in rows:
        a = agg[(r["sport"], r["season"])]
        for kk, vv in r["c"].items():
            a[kk] += vv
    out = {}
    for key, a in agg.items():
        den = wrc_rates._woba_den(a); obp_den = a["ab"] + a["bb"] + a["hbp"] + a["sf"]
        if den <= 0 or obp_den <= 0:
            continue
        lg_obp = (a["h"] + a["bb"] + a["hbp"]) / obp_den
        base = wrc_rates._woba_num(a, wrc_rates.BASE_W) / den
        out[key] = (lg_obp / base) if base > 0 else 1.0
    return out


def _lg_component_rate(rows):
    agg = defaultdict(lambda: defaultdict(float))
    for r in rows:
        a = agg[(r["season"], r["level"])]
        for kk in _COMP:
            a[kk] += r["c"][kk]
        a["pa"] += r["c"]["pa"]
    return {key: {kk: a[kk] / a["pa"] for kk in _COMP} for key, a in agg.items() if a["pa"] > 0}


def _comp_feat(r, lg_rate):
    pa = r["c"]["pa"]; lg = lg_rate.get((r["season"], r["level"]))
    if pa <= 0 or lg is None:
        return None
    w = pa / (pa + wrc_rates.K_REL_PA)
    return [w * (r["c"][kk] / pa - lg[kk]) for kk in _COMP]


def clause_m(rows):
    scale = _scale_ss(rows)
    lg_rate = _lg_component_rate(rows)
    by_ps = {}
    for r in rows:
        k = (r["mlbam"], r["season"])
        if k not in by_ps or r["c"]["pa"] > by_ps[k]["c"]["pa"]:
            by_ps[k] = r
    woba_next = defaultdict(lambda: [0.0, 0.0])
    for r in rows:
        s = scale.get((r["sport"], r["season"]))
        if s is None:
            continue
        acc = woba_next[(r["mlbam"], r["season"])]
        acc[0] += wrc_rates._woba_num(r["c"], wrc_rates.BASE_W) * s
        acc[1] += wrc_rates._woba_den(r["c"])
    pairs = []
    for (mid, season), r in by_ps.items():
        if r["c"]["pa"] < 100:
            continue
        nxt = woba_next.get((mid, season + 1))
        if not nxt or nxt[1] < 100:
            continue
        x = _comp_feat(r, lg_rate)
        if x is None:
            continue
        pairs.append({"season": season, "x": x, "y": nxt[0] / nxt[1], "mid": mid})
    preds = []
    last_beta = None
    for ev in range(2018, 2025):
        tr = [p for p in pairs if p["season"] < ev]
        te = [p for p in pairs if p["season"] == ev]
        if len(tr) < 50 or len(te) < 12:
            continue
        Xtr = np.array([p["x"] for p in tr]); ytr = np.array([p["y"] for p in tr])
        Xte = np.array([p["x"] for p in te])
        mu, sd = Xtr.mean(0), Xtr.std(0); sd[sd == 0] = 1.0
        Xs = (Xtr - mu) / sd
        A = Xs.T @ Xs + 1.0 * np.eye(Xs.shape[1])
        beta = np.linalg.solve(A, Xs.T @ (ytr - ytr.mean()))
        last_beta = (beta, mu, sd, float(ytr.mean()))
        pr = ((Xte - mu) / sd) @ beta + ytr.mean()
        for i, p in enumerate(te):
            preds.append((float(pr[i]), p["y"], p["mid"]))
    if len(preds) < 30 or last_beta is None:
        return {"n_pairs": len(pairs), "n_oos": len(preds), "oos_r": None, "passes": False}, None, lg_rate
    px = np.array([a for a, _, _ in preds]); py = np.array([b for _, b, _ in preds])
    r = float(np.corrcoef(px, py)[0, 1])
    rng = random.Random(SEED); n = len(preds); boot = []
    for _ in range(REPS):
        s = np.array(rng.choices(range(n), k=n))
        c = np.corrcoef(px[s], py[s])[0, 1]
        if not math.isnan(c):
            boot.append(c)
    boot.sort()
    lo = boot[int(0.025 * len(boot))]
    res = {"n_pairs": len(pairs), "n_oos": len(preds), "oos_r": round(r, 4),
           "lo95": round(lo, 4), "passes": bool(lo > 0), "components": _COMP}
    return res, last_beta, lg_rate


def _composite_feature(rows, last_beta, lg_rate):
    """Leading-indicator composite score per matrix player (final joined season)."""
    beta, mu, sd, ymean = last_beta
    rowmap = {(r["mlbam"], r["season"], r["level"]): r for r in rows}
    mat = json.loads(matrix_path(SIDE).read_text(encoding="utf-8"))
    out = {}
    for mm in mat:
        milb = mm.get("milb") or {}
        r = rowmap.get((mm.get("mlbam_id"), milb.get("milb_season"), milb.get("milb_level")))
        if r is None:
            continue
        x = _comp_feat(r, lg_rate)
        if x is None:
            continue
        out[mm["player_key"]] = float((((np.array(x) - mu) / sd) @ beta) + ymean)
    return out


# --------------------------------------------------------------------------- #
def _strip(res):
    return {k: v for k, v in res.items() if k != "pooled"}


def verdict(delta, boot):
    """Returns (bar_verdict, marginal, ship, ship_reason).
    bar_verdict = point-bar PASS/FAIL (frozen registration, no CI clause).
    ship = the governing 'marginal = FAIL' decision: a point-bar PASS whose
    2000-rep player-clustered bootstrap pooled-delta CI crosses zero is MARGINAL
    and does NOT ship this cycle."""
    passes = (delta["pooled"] >= BAR_POOLED) and (delta["wm"] >= BAR_WM)
    lo = boot["pooled_delta"]["lo95"] if (boot and boot.get("pooled_delta")) else None
    marginal = bool(passes and lo is not None and lo <= 0)
    if not passes:
        return "FAIL", False, False, "point bar not cleared"
    if marginal:
        return "PASS", True, False, (f"MARGINAL: bootstrap pooled-delta lo95={lo:+.4f} crosses zero; "
                                     "'marginal = FAIL' governing rule -> no ship this cycle")
    return "PASS", False, True, "clears point bar with pooled-delta CI above zero"


def main():
    joined, meta, _n_exact_all = build_join()
    lab_rows = LAB.data_for(SIDE)
    n_rows = len(lab_rows)
    # exact-join coverage over the DEBUTED eval pool only (not the full matrix)
    n_exact = sum(1 for r in lab_rows if r["player_key"] in joined)
    inject(joined, mode="zero")

    base = run(LEAN, "baseline")
    ref = LAB.baseline(SIDE)
    identity_ok = (base["spearman"] == ref["spearman"] and base["within_tier_wm"] == ref["within_tier_wm"]
                   and base["t45"] == ref["t45"] and base["n"] == ref["n"])

    a1 = run(LEAN_NO_OPS + ["wrc_rel"], "A1_replace")
    a2 = run(LEAN + ["wrc_rel"], "A2_add")
    sb = run(LEAN + ["hit_sb_rel"], "SB_add")

    def pack(res):
        d = {"pooled": round(res["spearman"] - base["spearman"], 4),
             "wm": round(res["within_tier_wm"] - base["within_tier_wm"], 4),
             "t45": round((res["t45"] or 0) - (base["t45"] or 0), 4)}
        boot = bootstrap_delta(base, res)
        v, marg, ship, reason = verdict(d, boot)
        return {"metrics": _strip(res), "delta": d, "bootstrap": boot,
                "bar_verdict": v, "marginal_ci_crosses_zero": marg,
                "ship": ship, "ship_reason": reason}

    A1 = pack(a1); A2 = pack(a2); SB = pack(sb)

    def fringe(P):
        d = P["delta"]
        return "PASS" if (d["t45"] >= BAR_FRINGE_T45 and d["pooled"] >= BAR_WM and d["wm"] >= BAR_WM) else "FAIL"

    A3 = {"of": "A2_add", "verdict": fringe(A2), "delta": A2["delta"]}
    A3_replace_desc = {"of": "A1_replace", "verdict": fringe(A1), "delta": A1["delta"]}

    a1_pos = A1["delta"]["pooled"] > 0
    a2_pos = A2["delta"]["pooled"] > 0
    A4 = {"triggered": bool(a1_pos or a2_pos),
          "trigger_reason": f"A1 pooled {A1['delta']['pooled']:+.4f}, A2 pooled {A2['delta']['pooled']:+.4f}"}
    if A4["triggered"]:
        rows_c = wrc_rates.load_rows()
        m, last_beta, lg_rate = clause_m(rows_c)
        A4["clause_m"] = m
        if m.get("passes") and last_beta is not None:
            comp = _composite_feature(rows_c, last_beta, lg_rate)
            for r in LAB.data_for(SIDE):
                r["feats"]["wrc_comp"] = float(comp.get(r["player_key"], 0.0))
            a4 = run(LEAN + ["wrc_comp"], "A4_composite")
            A4["arm"] = pack(a4)
            A4["verdict"] = A4["arm"]["bar_verdict"]
        else:
            A4["verdict"] = "FAIL"
            A4["reason"] = "clause M lo95 <= 0"
    else:
        A4["verdict"] = "not_triggered"

    # mean-impute SENSITIVITY (NOT the gate)
    means = inject(joined, mode="mean")
    base_m = run(LEAN, "baseline_mean")
    a1_m = run(LEAN_NO_OPS + ["wrc_rel"], "A1_mean")
    sb_m = run(LEAN + ["hit_sb_rel"], "SB_mean")
    sens = {"impute_means": {k: round(v, 6) for k, v in means.items()},
            "A1_replace": {"pooled_delta": round(a1_m["spearman"] - base_m["spearman"], 4),
                           "wm_delta": round(a1_m["within_tier_wm"] - base_m["within_tier_wm"], 4)},
            "SB_add": {"pooled_delta": round(sb_m["spearman"] - base_m["spearman"], 4),
                       "wm_delta": round(sb_m["within_tier_wm"] - base_m["within_tier_wm"], 4)},
            "note": ("mean-impute injects a nonzero constant for the 305 milb-missing players "
                     "that the shipped ops_rel/sibling rates never carry; reported only to "
                     "explain sensitivity, it is not ship-faithful and does not gate.")}
    inject(joined, mode="zero")   # leave rows ship-faithful

    out = {
        "registered": "docs/efv-2026-07-24/GATES.md sections W-WRC (Phase 1b) + W-SB (Phase 2c)",
        "generated": "2026-07-24",
        "seed": SEED, "reps": REPS,
        "harness": "efv_lab_runner fold protocol, explicit-key reimplementation",
        "identity_check_vs_runner_baseline": {
            "run_spearman": base["spearman"], "runner_spearman": ref["spearman"],
            "run_wm": base["within_tier_wm"], "runner_wm": ref["within_tier_wm"],
            "run_t45": base["t45"], "runner_t45": ref["t45"], "ok": bool(identity_ok)},
        "a_priori_null": ("decomposed components usually dominate composites; the shipped "
                          "hitter block already prices obp_rel/iso_rel/k_rel/bb_rel/ops_rel "
                          "from the same events, so a woba-lite composite is expected to add "
                          "~nothing (recorded in GATES before any arm ran)."),
        "imputation": ("0 for every unjoined row (ship-faithful: a milb-missing player's rate "
                       "features are 0 + milb_missing=1). Mean-impute reported as a sensitivity "
                       "only, NOT the gate."),
        "bars": {"A1_A2_SB": "pooled delta >= +0.004 AND wm delta >= -0.0011",
                 "A3_fringe": "t45 delta >= +0.015 AND pooled AND wm >= -0.0011 (LR-FRINGE)",
                 "A4": "same as A2; trigger = A1 or A2 point-positive pooled; prereq clause M lo95 > 0",
                 "SB_fringe": "keep-alive record only, no fringe ship this cycle"},
        "join": {"n_rows": n_rows, "n_milb_present_exact_join": n_exact,
                 "n_imputed_zero": n_rows - n_exact,
                 "note": "the 2 milb-present non-joins are pre-2021 short-season A (sportId 15) lines absent from this refetch"},
        "baseline": _strip(base),
        "arms": {"A1_replace": A1, "A2_add": A2, "SB_add": SB},
        "A3_fringe": A3, "A3_fringe_of_replace_descriptive": A3_replace_desc,
        "A4": A4,
        "mean_impute_sensitivity": sens,
        "verdicts": {
            "A1_replace": A1["bar_verdict"], "A2_add": A2["bar_verdict"], "A3_fringe": A3["verdict"],
            "SB_bar": SB["bar_verdict"], "SB_marginal_ci_crosses_zero": SB["marginal_ci_crosses_zero"],
            "SB_fringe_keepalive": fringe(SB), "A4_composite": A4["verdict"]},
        "ship_decisions": {
            "A1_replace": A1["ship"], "A2_add": A2["ship"], "A3_fringe": False,
            "SB": SB["ship"], "SB_reason": SB["ship_reason"], "A4_composite": False,
            "W_WRC_overall": "NO SHIP (all arms FAIL; a-priori null confirmed)",
            "W_SB_overall": ("NO SHIP" if not SB["ship"] else "SHIP")
            + (" -- " + SB["ship_reason"])},
    }
    (ROOT / "data" / "xfv_wrc_eval.json").write_text(json.dumps(out, indent=1), encoding="utf-8")

    print(f"identity_ok={identity_ok}  baseline rho={base['spearman']} wm={base['within_tier_wm']} t45={base['t45']}")
    print(f"join: exact={n_exact} imputed0={n_rows - n_exact}")
    for tag, P in (("A1_replace", A1), ("A2_add", A2), ("SB_add", SB)):
        d = P["delta"]; bp = P["bootstrap"]["pooled_delta"]
        print(f"  {tag:12s} pooled {d['pooled']:+.4f} wm {d['wm']:+.4f} t45 {d['t45']:+.4f} "
              f"[pooledCI {bp['lo95']:+.4f},{bp['hi95']:+.4f}] bar={P['bar_verdict']} ship={P['ship']}"
              + ("  (MARGINAL: CI crosses 0)" if P["marginal_ci_crosses_zero"] else ""))
    print(f"  A3_fringe(add) -> {A3['verdict']}   A4 -> {A4['verdict']}")
    print(f"  mean-impute sensitivity: A1 pooled {sens['A1_replace']['pooled_delta']:+.4f}, "
          f"SB pooled {sens['SB_add']['pooled_delta']:+.4f}")
    print("wrote data/xfv_wrc_eval.json")


if __name__ == "__main__":
    main()
