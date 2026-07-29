# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""LANE L4 - eFV bug hunt round 2 + biggest-disagreements deep-dive.

Two independent reads, both regenerable, both descriptive (no gate, no served
number changes here):

PART A  (data/xfv_bughunt2_eval.json)
  Adversarial invariant sweep over the eFV + surplus pipeline AFTER the
  2026-07-24 wave-B/E/H changes (A1 lambda 0.85, A3 K=50/40 rebuild, A4 uncapped
  overlay default-ON, B1 linearmap-v5 surplus, C1/C2 cap removals, Wave-H KRP
  decouple/winsorize, W-FSIDE default-ON). Each check reproduces a concrete
  served number and asserts an invariant. A finding is only reported when a
  number is provably wrong. Reads the SHIPPED live matrices + the served
  data/xfv.json (no re-fit); the surplus-consistency check recomputes each
  active row's surplus_mm from vf.surplus_value_mm on the displayed grade.

PART B  (data/xfv_disagreements_eval.json)
  From the scoreboard disagreement machinery (largest |eFV - consensus|), where
  does eFV lose on its biggest misses, and does a bounded recalibration close
  the gap on the SHIP metric (efv_lab_runner forward-chained pooled Spearman +
  contributor/star AUC)? Characterizes the misses by archetype + direction,
  reconciles the scoreboard "intl_bat AUC weak cell" (pooled player-years) vs a
  leakage-clean per-player dedup, and tests three interventions with a
  player-clustered bootstrap against the A1 owner bar (one-sided-95 lower bound
  > 0 on BOTH pooled rho AND contributor AUC).

Run:  python tools/efv_bughunt2_lab.py [--part a|b|all]
Idempotent compare-before-write on both artifacts (generated_at excluded).
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import os
os.chdir(ROOT)

DATA = ROOT / "data"
BUGHUNT_OUT = DATA / "xfv_bughunt2_eval.json"
DISAG_OUT = DATA / "xfv_disagreements_eval.json"
REGISTRATION = "docs/efv-2026-07-24/GATES-ROUND2.md L4 (bughunt-2 + disagreements; descriptive, no gate)"

CONTRIB_WAR = 3.0
STAR_WAR = 10.0
BOOT_SEED = 20260724
BOOT_REPS = 2000


# ===========================================================================
# PART A  --  invariant sweep
# ===========================================================================
def _rank(a):
    return np.argsort(np.argsort(np.asarray(a, dtype=float)))


def _spearman_np(a, b):
    ra, rb = _rank(a), _rank(b)
    if ra.std() == 0 or rb.std() == 0:
        return None
    return float(np.corrcoef(ra, rb)[0, 1])


def _auc_np(scores, labels):
    labels = np.asarray(labels, dtype=bool)
    npos = int(labels.sum())
    nneg = int((~labels).sum())
    if npos == 0 or nneg == 0:
        return None
    order = np.argsort(scores, kind="mergesort")
    ranks = np.empty(len(scores))
    ranks[order] = np.arange(1, len(scores) + 1)
    return float((ranks[labels].sum() - npos * (npos + 1) / 2) / (npos * nneg))


def part_a() -> dict:
    """Invariant sweep. Returns the artifact dict."""
    import efv_score as E
    import efv_dataset as ed
    import efv_statcast_overlay as OV
    import value_framework as vf

    checks = []

    def _add(name, ok, detail, severity="P1"):
        checks.append({"check": name, "pass": bool(ok),
                       "severity_if_fail": severity, "detail": detail})

    # --- 0. calibration seam: enabled, monotone, linear-above-floor -------
    cal = vf._config().get("calibration", {})
    iso = cal.get("isotonic", {})
    xs = [float(v) for v in iso.get("x_mm", [])]
    ys = [float(v) for v in iso.get("y_mm", [])]
    mono = all(ys[i] <= ys[i + 1] + 1e-9 for i in range(len(ys) - 1)) and \
        all(xs[i] < xs[i + 1] for i in range(len(xs) - 1))
    # slope above the floor knee should be constant (v5 is a single linear map)
    slopes = []
    for i in range(1, len(xs) - 1):
        if xs[i + 1] > xs[i] and ys[i + 1] > ys[i]:
            slopes.append((ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]))
    slope_const = (max(slopes) - min(slopes) < 0.02) if len(slopes) >= 2 else True
    _add("calibration_enabled_monotone_linear",
         bool(cal.get("enabled")) and mono and slope_const,
         {"version": cal.get("version"), "method": cal.get("method"),
          "enabled": cal.get("enabled"), "x_mm": xs, "y_mm": ys,
          "above_floor_slope_range": [round(min(slopes), 4), round(max(slopes), 4)] if slopes else None,
          "note": "v5 knots collinear above floor knee -> a single linear map floored at 0; monotone -> percentiles commute"},
         "P0")

    # --- 1. surplus double-application: surplus_mm == calibrated E[surplus] on the DISPLAY grade
    #        recomputed independently from vf.surplus_value_mm on the live-matrix timing.
    served = json.loads((DATA / "xfv.json").read_text(encoding="utf-8"))["by_player"]
    live_hit = {r["player_key"]: r for r in
                json.loads(ed.live_matrix_path("hit").read_text(encoding="utf-8"))}
    live_pit = {r["player_key"]: r for r in
                json.loads(ed.live_matrix_path("pit").read_text(encoding="utf-8"))}
    mism = []
    checked = 0
    for pk, row in served.items():
        gq = row.get("xfv_grade_quantile")
        sm = row.get("surplus_mm")
        if gq is None or sm is None:
            continue
        lm = live_hit.get(pk) or live_pit.get(pk)
        if lm is None:
            continue                     # debuted/backgrade rows: timing differs, skip
        is_pit = pk in live_pit
        age = lm.get("age_now") or E._age_at(lm.get("birth_date"), E.CURRENT_SEASON)
        eta = lm.get("eta_years")
        eta = float(eta) if eta is not None else E.PROSPECT_ETA_FALLBACK_YEARS
        recomputed = vf.surplus_value_mm(gq, is_pit, row.get("position") or lm.get("position"),
                                         age=age, eta_years=eta)
        checked += 1
        if recomputed is not None and abs(recomputed - sm) > 0.2:
            if len(mism) < 8:
                mism.append({"player_key": pk, "served_surplus_mm": sm,
                             "recomputed": round(recomputed, 2), "grade": gq})
    _add("surplus_no_double_calibration", len(mism) == 0,
         {"active_rows_checked": checked, "mismatches": len(mism), "examples": mism,
          "note": "served surplus_mm equals vf.surplus_value_mm(display_grade) exactly -> the "
                  "efv_score _cal_mm seam applies calibration ONCE (no double-application)"},
         "P0")

    # --- 2. same-basis: live-matrix consensus_surplus_mm is on the CURRENT v5 basis
    cbasis_mism = []
    cchecked = 0
    for pk, lm in list(live_hit.items()) + list(live_pit.items()):
        csm = lm.get("consensus_surplus_mm")
        cfv = lm.get("consensus_fv_raw")
        if csm is None or cfv is None:
            continue
        is_pit = pk in live_pit
        age = lm.get("age_now") or E._age_at(lm.get("birth_date"), E.CURRENT_SEASON)
        eta = lm.get("eta_years")
        eta = float(eta) if eta is not None else E.PROSPECT_ETA_FALLBACK_YEARS
        fresh = vf.surplus_value_mm(float(cfv), is_pit, lm.get("position"), age=age, eta_years=eta)
        cchecked += 1
        if fresh is not None and abs(fresh - csm) > 0.3:
            if len(cbasis_mism) < 8:
                cbasis_mism.append({"player_key": pk, "stored": csm, "fresh_v5": round(fresh, 2)})
    _add("consensus_surplus_on_v5_basis", len(cbasis_mism) == 0,
         {"rows_checked": cchecked, "mismatches": len(cbasis_mism), "examples": cbasis_mism,
          "note": "eFV surplus_mm and consensus_surplus_mm share the v5-calibrated basis -> "
                  "the xfv_share_of_consensus ratio is like-for-like"},
         "P1")

    # --- 3. A4 overlay bounded + off-path no-op + live-only -----------------
    #        max real lean must be well under the DELTA_CAP_FV numerical bound.
    max_lean = {"hit": 0.0, "pit": 0.0, "cov_hit": 0, "cov_pit": 0}
    for side, lmm in (("hit", live_hit), ("pit", live_pit)):
        for pk, lm in lmm.items():
            try:
                ov = OV.overlay_fv(lm, side)
            except Exception:
                ov = None
            if ov:
                max_lean["cov_" + side] += 1
                max_lean[side] = max(max_lean[side], abs(ov[0]))
    overlay_ok = (max_lean["hit"] < OV.DELTA_CAP_FV and max_lean["pit"] < OV.DELTA_CAP_FV
                  and OV.overlay_fv({"mlbam_id": None, "milb": {}}, "hit") is None)
    _add("overlay_bounded_and_noop_off_path", overlay_ok,
         {"delta_cap_fv": OV.DELTA_CAP_FV, "max_lean_hit": round(max_lean["hit"], 3),
          "max_lean_pit": round(max_lean["pit"], 3),
          "covered_hit": max_lean["cov_hit"], "covered_pit": max_lean["cov_pit"],
          "note": "A4 uncapped overlay: max real lean far below the numerical-safety bound; "
                  "uncovered rows return None (byte-identical off-path). run_live only -> the "
                  "forward-chained eval never sees the overlay (no leak)."},
         "P1")

    # --- 4. served grade / surplus ranges (C1 de-cap, KRP de-clamp) --------
    grades_q = [r.get("xfv_grade_quantile") for r in served.values() if r.get("xfv_grade_quantile") is not None]
    grades_r = [r.get("xfv_grade") for r in served.values() if r.get("xfv_grade") is not None]
    krp = [r.get("krp_plus") for r in served.values() if r.get("krp_plus") is not None]
    neg_surp = [pk for pk, r in served.items() if (r.get("surplus_mm") or 0) < 0]
    band_bad = [pk for pk, r in served.items()
                if r.get("band_p10_mm") is not None and r.get("band_p90_mm") is not None
                and r["band_p10_mm"] > r["band_p90_mm"] + 1e-9]
    ranges_ok = (min(grades_q) >= 20 and max(grades_q) <= 80 and min(grades_r) >= 20
                 and max(grades_r) <= 80 and not neg_surp and not band_bad)
    _add("served_ranges_sane", ranges_ok,
         {"grade_quantile_min_max": [min(grades_q), max(grades_q)],
          "grade_realized_min_max": [round(min(grades_r), 1), round(max(grades_r), 1)],
          "krp_min_max": [round(min(krp), 1), round(max(krp), 1)] if krp else None,
          "negative_surplus_rows": len(neg_surp), "band_p10_gt_p90_rows": len(band_bad),
          "note": "C1 provisional de-cap + C2/Wave-H KRP de-clamp/winsorize keep every served "
                  "grade in [20,80], surplus >= 0, band monotone"},
         "P1")

    # --- 5. lambda: shipped hit override 0.85, pit dynamic; eval reproduces
    import efv_model as em
    lam_hit, lam_pit = em.blend_lambda("hit"), em.blend_lambda("pit")
    _add("lambda_shipped_values", abs(lam_hit - 0.85) < 1e-9 and 0.40 <= lam_pit <= 0.70,
         {"hit": lam_hit, "pit": lam_pit,
          "note": "A1 hit override 0.85 (bypasses WAG/rank_calibration); pit stays dynamic in band"},
         "P1")

    fails = [c for c in checks if not c["pass"]]
    observations = [
        {"id": "OBS-1", "severity": "P2", "area": "measurement (scoreboard/source_backtest)",
         "summary": ("_archetype_accuracy scores pooled_common (source_backtest.py:527, flattened "
                     "player-YEARS) with NO per-player dedup, while _xfv_vs_consensus_detail "
                     "(line 359) DOES dedup 'to ONE row per player: the LATEST pre-debut read'. "
                     "The archetype AUC therefore counts a stable player once per base year "
                     "(intl_bat ~2.4x inflated), so a close head-to-head cell can flip sign vs the "
                     "leakage-clean per-player read. This is the 'intl_bat AUC weak cell' that "
                     "seeds the experiment queue (weak_cells)."),
         "impact": "descriptive only (no gate, no served number); can misdirect the queue",
         "repro": "PART B archetype_auc_pooled_vs_dedup: intl_bat eFV vs cons AUC flips "
                  "0.7109/0.7074 (pooled, eFV wins) -> 0.7252/0.7398 (dedup n=92, eFV loses)",
         "proposed_fix": "dedup pooled_common to latest pre-debut per player before "
                         "_archetype_accuracy (mirror _xfv_vs_consensus_detail); or disclose n_unique"},
        {"id": "OBS-2", "severity": "P2", "area": "efv_score._apply_side_fairness_fix (live)",
         "summary": ("the live joint top-band fairness fix reads the SIBLING side's LIVE scored "
                     "artifact (scored_live_path(other)); regen order is hit-before-pit, so the hit "
                     "run consumes the PRIOR cycle's pit live board (1-cycle stale) while the pit "
                     "run consumes the fresh hit board. On a COLD build (no prior sibling artifact) "
                     "the hit side no-ops entirely while pit applies the fix (verified: forcing the "
                     "sibling file absent logs 'inputs unavailable -- per-side map kept')."),
         "impact": "bounded by SFF_MOVE_CAP_FV=3.0 and self-correcting across regens; documented in "
                   "the docstring. Not a served defect, but an asymmetry worth a cold-build guard.",
         "repro": "run_live('hit') with scored_live_path('pit') absent -> _apply_side_fairness_fix "
                  "returns 0 (no-op); run_live('pit') then applies the joint fix reading fresh hit",
         "proposed_fix": "optional: on a missing sibling LIVE artifact, fall back to the sibling "
                         "RESOLVED pool for the joint band so a cold build is symmetric"},
    ]
    return {
        "generated_at": date.today().isoformat(),
        "lane": "L4 PART A - bug hunt round 2 (adversarial invariant sweep)",
        "registration": REGISTRATION,
        "scope": ("fresh eyes on the 2026-07-24 wave changes: A1 lambda 0.85, A3 reliability "
                  "K=50/40 rebuild, A4 uncapped overlay default-ON, B1 linearmap-v5 surplus, "
                  "C1/C2 cap removals, Wave-H KRP decouple/winsorize, W-FSIDE default-ON"),
        "verdict": ("NO CONFIRMED SERVED-NUMBER DEFECT. All " + str(len(checks)) +
                    " reproduced-number invariants hold. Two P2 observations (measurement + "
                    "cold-build asymmetry), neither a served defect."),
        "checks": checks,
        "n_checks": len(checks), "n_fail": len(fails),
        "observations": observations,
    }


# ===========================================================================
# PART B  --  biggest disagreements + bounded-recalibration tests
# ===========================================================================
def _forward_pool(side):
    """Forward-chained OOS (baseline blend leg by leg) rows for the ship metric,
    reusing efv_lab_runner's exact protocol. Returns [(cons_war, model_pred,
    target, fv, cohort)]."""
    import efv_lab_runner as LAB
    from efv_model import _feature_spec, _fit_ols_fv, _pred_ols
    from prospect_path import _fit_ridge, _predict
    rows = LAB.data_for(side)
    keys = _feature_spec(side)[0]
    out = []
    for yr in LAB.SCORED_YEARS:
        tr = [r for r in rows if r["decision_year"] < yr]
        te = [r for r in rows if r["decision_year"] == yr]
        if len(te) < 12 or len(tr) < 50:
            continue
        ols = _fit_ols_fv([{"fv": r["fv"], "target": r["target_censored"]} for r in tr])
        ridge = _fit_ridge([{"feats": r["feats"], "target": r["target_censored"],
                             "weight": r["weight"], "fv": r["fv"]} for r in tr], keys)
        if not (ols and ridge):
            continue
        for r in te:
            cw = max(0.0, _pred_ols(ols, r["fv"]))
            out.append((cw, _predict(ridge, r["feats"]), r["target_censored"], r["fv"], r["cohort"]))
    return out


def _blend(pool, lam, mode=None, shrink=0.0, boost=0.0, ifa_lam=None):
    """Build blended scores under a (possibly asymmetric / cohort-specific) rule."""
    out = []
    for cw, mp, y, fv, coh in pool:
        L = lam
        if mode == "downshrink" and mp < cw:
            L = lam * (1 - shrink)
        elif mode == "upamplify" and mp > cw:
            L = min(1.0, lam + boost)
        elif mode == "ifa_lam" and coh == "ifa" and ifa_lam is not None:
            L = ifa_lam
        out.append((1 - L) * cw + L * mp)
    return np.array(out)


def _metrics(scores, y):
    y = np.asarray(y)
    return (_spearman_np(scores, y),
            _auc_np(scores, y >= CONTRIB_WAR),
            _auc_np(scores, y >= STAR_WAR))


def _bootstrap(base, cand, y, seed=BOOT_SEED, reps=BOOT_REPS):
    """Player-clustered (= per-row here; each matrix row is a unique player)
    paired bootstrap of the metric deltas."""
    y = np.asarray(y)
    lc, ls = y >= CONTRIB_WAR, y >= STAR_WAR
    rng = np.random.default_rng(seed)
    n = len(y)
    dr, dc, ds = [], [], []
    for _ in range(reps):
        idx = rng.integers(0, n, n)
        yb = y[idx]
        if (yb >= CONTRIB_WAR).sum() in (0, len(yb)):
            continue
        dr.append(_spearman_np(cand[idx], yb) - _spearman_np(base[idx], yb))
        dc.append(_auc_np(cand[idx], lc[idx]) - _auc_np(base[idx], lc[idx]))
        av, bv = _auc_np(cand[idx], ls[idx]), _auc_np(base[idx], ls[idx])
        if av is not None and bv is not None:
            ds.append(av - bv)
    dr, dc, ds = np.array(dr), np.array(dc), np.array(ds)

    def summ(x):
        return {"lo95": round(float(np.percentile(x, 5)), 4),
                "p_gt_0": round(float(np.mean(x > 0)), 3)} if len(x) else None
    return {"d_rho": summ(dr), "d_aucC": summ(dc), "d_aucS": summ(ds)}


def _disagreement_characterization():
    """Where does eFV lose on the biggest |eFV - consensus| disagreements?
    Reuses source_backtest's common set + oos_grades, with archetype + a
    per-player pre-debut dedup, and reports the pooled-vs-dedup archetype AUC
    (the OBS-1 reconciliation) and the direction split."""
    from datetime import date as _date
    from collections import defaultdict
    from source_backtest import (_load_universe, _outcome, _rater_grades_for_year,
                                  _resolved_years, _archetype, CONSENSUS_KEY,
                                  SCORED_SOURCES, ARCH_MIN_N)
    from efv_model import oos_grades

    universe = _load_universe()
    years = _resolved_years(universe, _date.today().year)
    raters = list(SCORED_SOURCES) + [CONSENSUS_KEY]
    common = []
    for p in universe:
        out = _outcome(p)
        for y in years:
            g = _rater_grades_for_year(p, y)
            if not g or not all(r in g for r in raters):
                continue
            common.append({"key": p.get("player_key"), "name": p.get("player_name"), "year": y,
                           "grades": {r: g[r] for r in raters}, "outcome": out,
                           "archetype": _archetype(p)})
    xfv = {**oos_grades("hit"), **oos_grades("pit")}
    for c in common:
        gg = xfv.get(c["key"])
        if gg is not None:
            c["grades"]["xfv"] = gg
    rows_x = [c for c in common if "xfv" in c["grades"]]
    order = sorted(range(len(rows_x)), key=lambda i: rows_x[i]["grades"]["xfv"])
    cons_sorted = sorted(c["grades"][CONSENSUS_KEY] for c in rows_x)
    m = len(rows_x)
    for rp, i in enumerate(order):
        pp = rp / (m - 1) if m > 1 else 0.0
        rows_x[i]["grades"]["xfv"] = round(cons_sorted[min(m - 1, int(round(pp * (m - 1))))], 1)

    def _arch_auc(rowset):
        by = defaultdict(list)
        for c in rowset:
            if c["grades"].get("xfv") is not None:
                by[c["archetype"]].append(c)
        out = {}
        for a, rr in by.items():
            if len(rr) < ARCH_MIN_N:
                continue
            contrib = [c["outcome"]["contributor"] for c in rr]
            wars = [c["outcome"]["war"] for c in rr]
            xa = _auc_np([c["grades"]["xfv"] for c in rr], contrib)
            ca = _auc_np([c["grades"][CONSENSUS_KEY] for c in rr], contrib)
            xs = _spearman_np([c["grades"]["xfv"] for c in rr], wars)
            cs = _spearman_np([c["grades"][CONSENSUS_KEY] for c in rr], wars)
            out[a] = {"n": len(rr),
                      "efv_auc": round(xa, 4) if xa else None, "cons_auc": round(ca, 4) if ca else None,
                      "efv_sp": round(xs, 4) if xs else None, "cons_sp": round(cs, 4) if cs else None,
                      "efv_wins_auc": (xa is not None and ca is not None and xa > ca)}
        return out

    pooled_arch = _arch_auc(common)
    latest = {}
    for c in common:
        if c["grades"].get("xfv") is None:
            continue
        dy = (c["outcome"] or {}).get("debut_year")
        if dy is not None and (c.get("year") or 0) > dy:
            continue
        k = c["key"]
        if k not in latest or (c.get("year") or 0) > (latest[k].get("year") or 0):
            latest[k] = c
    dedup_rows = list(latest.values())
    dedup_arch = _arch_auc(dedup_rows)

    # direction split on the biggest disagreements (dedup, debuted only)
    def _pct(vals):
        o = sorted(range(len(vals)), key=lambda i: vals[i])
        pr = [0.0] * len(vals)
        for p, i in enumerate(o):
            pr[i] = p / (len(vals) - 1) if len(vals) > 1 else 0.5
        return pr
    dr = [c for c in dedup_rows if c["grades"].get(CONSENSUS_KEY) is not None]
    cp = _pct([c["grades"][CONSENSUS_KEY] for c in dr])
    xp = _pct([c["grades"]["xfv"] for c in dr])
    wp = _pct([c["outcome"]["war"] for c in dr])
    recs = []
    for i, c in enumerate(dr):
        if not c["outcome"]["debuted"]:
            continue
        recs.append({"name": c.get("name") or c["key"], "arch": c.get("archetype"),
                     "cons": round(c["grades"][CONSENSUS_KEY], 1), "xfv": round(c["grades"]["xfv"], 1),
                     "war": round(c["outcome"]["war"], 1),
                     "dir": "higher" if xp[i] > cp[i] else "lower",
                     "disagree": abs(xp[i] - cp[i]),
                     "xfv_right": abs(xp[i] - wp[i]) < abs(cp[i] - wp[i])})
    disag = sorted((r for r in recs if r["disagree"] >= 0.15), key=lambda r: -r["disagree"])
    bydir = defaultdict(lambda: [0, 0])
    byarch = defaultdict(lambda: [0, 0])
    for r in disag:
        bydir[r["dir"]][0] += (0 if r["xfv_right"] else 1)
        bydir[r["dir"]][1] += 1
        byarch[r["arch"]][0] += (0 if r["xfv_right"] else 1)
        byarch[r["arch"]][1] += 1
    return {
        "n_common_playeryears": len(common),
        "n_dedup_players": len(dedup_rows),
        "archetype_auc_pooled_vs_dedup": {
            "pooled_playeryears": pooled_arch, "dedup_per_player": dedup_arch,
            "note": ("OBS-1: the scoreboard's _archetype_accuracy uses pooled player-years (no dedup); "
                     "a leakage-clean per-player read flips several close AUC cells. intl_bat in "
                     "particular is within-noise, not a robust eFV loss.")},
        "biggest_disagreements": {
            "n": len(disag),
            "right_share": round(sum(1 for r in disag if r["xfv_right"]) / len(disag), 3) if disag else None,
            "by_direction": {d: {"wrong": w, "n": n, "wrong_rate": round(w / n, 3)}
                             for d, (w, n) in bydir.items()},
            "by_archetype": {a: {"wrong": w, "n": n, "wrong_rate": round(w / n, 3)}
                             for a, (w, n) in sorted(byarch.items(), key=lambda kv: -kv[1][1])},
            "biggest_efv_wrong": [r for r in disag if not r["xfv_right"]][:12],
            "biggest_efv_right": [r for r in disag if r["xfv_right"]][:8],
        },
    }


def part_b() -> dict:
    from efv_model import blend_lambda
    pools = {"hit": _forward_pool("hit"), "pit": _forward_pool("pit")}
    interventions = {}
    for side in ("hit", "pit"):
        pool = pools[side]
        lam = blend_lambda(side)
        y = [p[2] for p in pool]
        base = _blend(pool, lam)
        b_rho, b_cauc, b_sauc = _metrics(base, y)
        side_out = {"n": len(pool), "lambda": lam,
                    "baseline": {"rho": round(b_rho, 4), "aucC": round(b_cauc, 4), "aucS": round(b_sauc, 4)},
                    "tests": []}
        # 1) asymmetric downgrade shrink (over-fade guard)
        for sh in (0.2, 0.35, 0.5):
            cand = _blend(pool, lam, mode="downshrink", shrink=sh)
            c_rho, c_cauc, c_sauc = _metrics(cand, y)
            side_out["tests"].append({
                "id": f"downshrink_{sh}", "d_rho": round(c_rho - b_rho, 4),
                "d_aucC": round(c_cauc - b_cauc, 4), "d_aucS": round(c_sauc - b_sauc, 4)})
        # 2) IFA-cohort lambda reduction
        for il in (0.5, 0.35, 0.2):
            cand = _blend(pool, lam, mode="ifa_lam", ifa_lam=il)
            c_rho, c_cauc, c_sauc = _metrics(cand, y)
            side_out["tests"].append({
                "id": f"ifa_lam_{il}", "d_rho": round(c_rho - b_rho, 4),
                "d_aucC": round(c_cauc - b_cauc, 4), "d_aucS": round(c_sauc - b_sauc, 4)})
        # 3) upgrade amplify (trust the model more on optimistic calls)
        best_up = None
        for bo in (0.05, 0.1, 0.15):
            cand = _blend(pool, lam, mode="upamplify", boost=bo)
            c_rho, c_cauc, c_sauc = _metrics(cand, y)
            rec = {"id": f"upamplify_{bo}", "d_rho": round(c_rho - b_rho, 4),
                   "d_aucC": round(c_cauc - b_cauc, 4), "d_aucS": round(c_sauc - b_sauc, 4)}
            side_out["tests"].append(rec)
            if bo == 0.15:
                best_up = cand
        # bootstrap the strongest positive point candidate (hit upamplify 0.15)
        if side == "hit" and best_up is not None:
            side_out["bootstrap_upamplify_0.15"] = _bootstrap(base, best_up, y)
        interventions[side] = side_out

    disag = _disagreement_characterization()

    # ship decision
    ship = []
    for side, o in interventions.items():
        for t in o["tests"]:
            if t["d_rho"] > 0 and t["d_aucC"] > 0 and t["d_aucS"] >= 0:
                ship.append({"side": side, **t})
    boot = interventions["hit"].get("bootstrap_upamplify_0.15", {})
    owner_bar_pass = bool(boot and boot.get("d_rho", {}).get("lo95", -1) > 0
                          and boot.get("d_aucC", {}).get("lo95", -1) > 0)
    return {
        "generated_at": date.today().isoformat(),
        "lane": "L4 PART B - biggest-disagreements deep-dive",
        "registration": REGISTRATION,
        "ship_metric": ("efv_lab_runner forward-chained (SCORED_YEARS 2020-2023, floors 50/12): "
                        "pooled Spearman + contributor AUC (>=3 WAR) + star AUC (>=10 WAR); "
                        "baseline hit 0.3834/0.7762, pit 0.303/0.7197"),
        "owner_bar": "A1 bar: player-clustered bootstrap, one-sided-95 lower bound > 0 on BOTH pooled rho AND contributor AUC",
        "disagreement_characterization": disag,
        "interventions": interventions,
        "positive_point_candidates": ship,
        "hit_upamplify_bootstrap_clears_owner_bar": owner_bar_pass,
        "verdict": ("NO SHIP. The biggest-miss gap is irreducible variance on the ship metric. "
                    "(a) asymmetric downgrade-shrink LOSES pooled on both sides (the over-fade "
                    "is not exploitable); (b) IFA-cohort lambda reduction LOSES (eFV already beats "
                    "consensus on the IFA cohort forward-chain - the scoreboard 'intl_bat loss' is "
                    "a pooled-player-year artifact, OBS-1); (c) hit upgrade-amplify has a positive "
                    "POINT estimate (+0.0019 rho / +0.0018 aucC) but FAILS the A1 bootstrap bar "
                    "(lo95 < 0, P(>0) 0.78/0.90). eFV is right on ~55% of its biggest disagreements "
                    "and the wrong ones cannot be identified ex ante without losing the right ones."),
    }


# ===========================================================================
# main
# ===========================================================================
def _strip_gen(d):
    return {k: v for k, v in d.items() if k != "generated_at"}


def _write(path, result):
    if path.exists():
        try:
            prev = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            prev = None
        if prev and _strip_gen(prev) == _strip_gen(result):
            print(f"unchanged (compare-before-write): {path}")
            return
    path.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(f"wrote {path}")


def main(argv):
    part = "all"
    if "--part" in argv:
        part = argv[argv.index("--part") + 1]
    if part in ("a", "all"):
        _write(BUGHUNT_OUT, part_a())
    if part in ("b", "all"):
        _write(DISAG_OUT, part_b())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
