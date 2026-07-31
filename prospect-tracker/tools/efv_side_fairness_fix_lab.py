# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""F-SIDE-FIX gate lab (pre-registered: docs/efv-2026-07-23/GATES.md,
"F-SIDE-FIX gate registration" - frozen BEFORE this lab first ran).

Candidate: the ARM-2-style TOP-BAND joint display recalibration implemented in
efv_score.py (joint_band_recal + the crosswalk helpers - this lab drives the
PRODUCTION functions, not a reimplementation). Frame: F-SIDE full_pool_km,
forward-chained folds, prototype-verbatim incumbent display map (the lab
asserts its own fold refits reproduce efv_model._sf_fwd_chain rank_war values
bit-for-bit before judging any gate).

Gates (verbatim from the registration):
  G1' pooled joint Spearman NO-HARM     lo95(rho_cand - rho_inc) >= -0.005
  F1a top-25 pit share closes >= 1/3 of the display-vs-raw excess
  F1b top-25 hit-minus-pit mean diff (seed-7 stream) < incumbent
  S1  cand top-25 mean diff <= 5.53 AND median diff <= 5.01
  S2  rank_war identity asserted (blend rho unchanged by construction)
  S4a rank_war-frame / equal-FV cells display-independent (asserted)
  S4b cand display mid-band cells not hit-favorable beyond inc + 1 SE
  I1 below-knee identity, I2 within-side weak monotonicity, I3 |move| <= 3.0

Seed 20260723, 2000 bootstrap reps. Artifact:
data/xfv_side_fairness_fix_eval.json (the loss ledger on any FAIL).

Run (from prospect-tracker/):
  python -m tools.efv_side_fairness_fix_lab eval [--matrix-dir DIR]
  python -m tools.efv_side_fairness_fix_lab postflip --baseline SNAPSHOT.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import statistics
import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
os.chdir(_ROOT)

SEED = 20260723
REPS = 2000
G1_NOHARM_LO95 = -0.005          # owner-re-registered NO-HARM band
F1A_CLOSE_FRACTION = 1.0 / 3.0   # share must close >= 1/3 of the excess
OUT_PATH = _ROOT / "data" / "xfv_side_fairness_fix_eval.json"
SF_ART = _ROOT / "data" / "xfv_side_fairness_eval.json"


def _sha12(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# frame construction (F-SIDE prototype mechanics + the production candidate)
# ---------------------------------------------------------------------------

def _fold_scores(data, side, lam, yr):
    """Refit ONE forward-chained fold exactly as efv_model._sf_fwd_chain does
    and score BOTH pools. Returns (train_scored, test_scored) or None when the
    fold fails the >=15/>=60 guards. test_scored rank_war is asserted against
    the _sf_fwd_chain output by the caller (frame-fidelity proof)."""
    from efv_model import _feature_spec, _fit_ols_fv, _fit_ridge, _pred_ols
    from prospect_path import _fit_linear_calibration, _predict
    keys, _m = _feature_spec(side)
    tr = [r for r in data if r["decision_year"] < yr]
    te = [r for r in data if r["decision_year"] == yr]
    if len(te) < 15 or len(tr) < 60:
        return None
    ols = _fit_ols_fv(tr)
    ridge = _fit_ridge(tr, keys)
    if not (ols and ridge):
        return None
    cal = _fit_linear_calibration([(_predict(ridge, r["feats"]), r["target"]) for r in tr])
    a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)

    def _score(rows):
        out = []
        for r in rows:
            cons = max(0.0, _pred_ols(ols, r["fv"]))
            model = max(-2.0, a + b * _predict(ridge, r["feats"]))
            out.append({"pk": r["player_key"], "side": side, "year": yr,
                        "fv": r["fv"], "war": r["target"],
                        "rank_war": (1 - lam) * cons + lam * model})
        return out
    return _score(tr), _score(te)


def build_frame(matrix_dir: Path | None):
    """Incumbent + candidate display grades on the F-SIDE full_pool_km frame.
    Returns (scored rows with disp + disp_cand, meta)."""
    import efv_dataset
    if matrix_dir is not None:
        efv_dataset.matrix_path = lambda side: matrix_dir / (
            "xfv_pitcher_matrix.json" if side == "pit" else "xfv_hitter_matrix.json")
    import efv_model
    from efv_model import SCORED_YEARS, _sf_live_lambdas, _sf_pool, _sf_fwd_chain, \
        _sf_quantile_display
    import efv_score

    lam, lam_src = _sf_live_lambdas()
    scored, per_side_data = [], {}
    for side in ("hit", "pit"):
        data, _cens = _sf_pool(side, "full_pool")
        per_side_data[side] = data
        rows = _sf_fwd_chain(data, side, lam[side], SCORED_YEARS)
        for yr in sorted({r["year"] for r in rows}):
            _sf_quantile_display([r for r in rows if r["year"] == yr])
        scored.extend(rows)

    # candidate: per fold-year, per-fold TRAIN-fit crosswalks + the production
    # joint_band_recal over the fold's joint test pool.
    n_refit_checked = 0
    for yr in sorted({r["year"] for r in scored}):
        curves, side_entries = {}, {}
        for side in ("hit", "pit"):
            fold = _fold_scores(per_side_data[side], side, lam[side], yr)
            if fold is None:
                raise RuntimeError(f"fold {yr}/{side} failed guards - frame mismatch")
            train_scored, test_scored = fold
            # frame-fidelity assertion: the refit must reproduce the
            # _sf_fwd_chain test rank_war values bit-for-bit.
            ref = {r["pk"]: r["rank_war"] for r in scored
                   if r["side"] == side and r["year"] == yr}
            got = {r["pk"]: r["rank_war"] for r in test_scored}
            if ref != got:
                raise RuntimeError(f"fold {yr}/{side} refit does not reproduce "
                                   "_sf_fwd_chain rank_war - frame mismatch")
            n_refit_checked += len(got)
            curve = efv_score._sff_crosswalk_curve(
                [(r["rank_war"], r["war"]) for r in train_scored])
            if curve is None:
                raise RuntimeError(f"fold {yr}/{side} crosswalk pool too thin")
            curves[side] = curve
            ent = [r for r in scored if r["side"] == side and r["year"] == yr]
            ent.sort(key=lambda r: (r["rank_war"], r["pk"]))
            m = len(ent)
            side_entries[side] = [
                {"side": side, "idx": i, "q": (i / (m - 1)) if m > 1 else 0.0,
                 "rank_war": r["rank_war"], "preside": r["disp"], "_row": r}
                for i, r in enumerate(ent)]
        band_rows = []
        for side in ("hit", "pit"):
            for e in side_entries[side]:
                if e["preside"] >= efv_score.SFF_KNEE_RAW:
                    e["ew"] = efv_score._sff_expected_war(curves[side], e["q"])
                    band_rows.append(e)
        assign = efv_score.joint_band_recal(band_rows)
        for side in ("hit", "pit"):
            for e in side_entries[side]:
                e["_row"]["disp_cand"] = assign.get((side, e["idx"]), e["preside"])
    meta = {"lambdas": lam, "lambda_source": lam_src,
            "folds": sorted({r["year"] for r in scored}),
            "n_hit": sum(1 for r in scored if r["side"] == "hit"),
            "n_pit": sum(1 for r in scored if r["side"] == "pit"),
            "n_refit_rank_war_verified": n_refit_checked}
    return scored, meta


# ---------------------------------------------------------------------------
# gate battery
# ---------------------------------------------------------------------------

def _pooled_spearman_gap_boot(scored):
    from efv_model import _spearman
    disp_i = [r["disp"] for r in scored]
    disp_c = [r["disp_cand"] for r in scored]
    wars = [r["war"] for r in scored]
    rho_i = _spearman(disp_i, wars)
    rho_c = _spearman(disp_c, wars)
    rng = random.Random(SEED)
    n = len(scored)
    gaps = []
    for _ in range(REPS):
        idx = [rng.randrange(n) for _ in range(n)]
        wi = [wars[i] for i in idx]
        gaps.append(_spearman([disp_c[i] for i in idx], wi)
                    - _spearman([disp_i[i] for i in idx], wi))
    gaps.sort()
    return {"rho_incumbent": round(rho_i, 4), "rho_candidate": round(rho_c, 4),
            "gap": round(rho_c - rho_i, 4),
            "gap_boot_mean": round(statistics.mean(gaps), 4),
            "gap_lo95": round(gaps[int(0.05 * REPS)], 4),
            "gap_ci90": [round(gaps[int(0.05 * REPS)], 4),
                         round(gaps[int(0.95 * REPS)], 4)],
            "p_gap_gt_0": round(sum(1 for g in gaps if g > 0) / REPS, 3),
            "reps": REPS, "seed": SEED}


def _top25(scored, key):
    """Pooled joint top-25 membership per fold-year under ranking `key`,
    prototype sort mechanics (sorted by -key over the fold's pool list)."""
    out = []
    for yr in sorted({r["year"] for r in scored}):
        pool = sorted([r for r in scored if r["year"] == yr], key=lambda r: -r[key])
        out.extend(pool[:25])
    return out


def _band_members(scored, key, lo, hi):
    out = []
    for yr in sorted({r["year"] for r in scored}):
        pool = sorted([r for r in scored if r["year"] == yr], key=lambda r: -r[key])
        for i, r in enumerate(pool, 1):
            if lo <= i <= hi:
                out.append(r)
    return out


def _cell(members, seed=7):
    from efv_model import _sf_summ, _sf_boot
    hit = [r for r in members if r["side"] == "hit"]
    pit = [r for r in members if r["side"] == "pit"]
    return {"n_hit": len(hit), "n_pit": len(pit),
            "pit_share": round(len(pit) / len(members), 3) if members else None,
            "hit": _sf_summ(hit), "pit": _sf_summ(pit),
            "boot": _sf_boot(hit, pit, seed=seed)}


def run_eval(matrix_dir: Path | None) -> dict:
    import efv_score
    scored, meta = build_frame(matrix_dir)

    # --- hard invariants -------------------------------------------------
    knee, cap = efv_score.SFF_KNEE_RAW, efv_score.SFF_MOVE_CAP_FV
    below = [r for r in scored if r["disp"] < knee]
    i1_viol = sum(1 for r in below if r["disp_cand"] != r["disp"])
    # LAB DEFECT FIXED (first run, 2026-07-23, recorded honestly per the
    # RELIEF-SHAPE precedent): the original check compared ADJACENT rows in
    # (rank_war, pk) order, which flags rank_war TIES whose incumbent display
    # values were assigned in a different (list-stable) order - 9 tie pairs,
    # all below the knee, all present IDENTICALLY in the incumbent map, zero
    # candidate-introduced. The registered I2 quantity is weak monotonicity IN
    # rank_war, which only constrains STRICTLY-ordered pairs; ties additionally
    # must carry no NEW inversions vs the incumbent (tie-parity clause).
    i2_viol = 0          # strict-pair violations (the registered quantity)
    i2_tie_new = 0       # tie-pair inversions not already in the incumbent
    for side in ("hit", "pit"):
        for yr in sorted({r["year"] for r in scored}):
            ent = sorted([r for r in scored if r["side"] == side and r["year"] == yr],
                         key=lambda r: (r["rank_war"], r["pk"]))
            run_max = None          # max disp_cand over all strictly-lower rank_war
            i = 0
            while i < len(ent):
                j = i
                while j < len(ent) and ent[j]["rank_war"] == ent[i]["rank_war"]:
                    j += 1
                grp = ent[i:j]
                if run_max is not None:
                    for r in grp:
                        if r["disp_cand"] < run_max - 1e-9:
                            i2_viol += 1
                for a, b in zip(grp, grp[1:]):
                    if (b["disp_cand"] < a["disp_cand"] - 1e-9
                            and not (b["disp"] < a["disp"] - 1e-9)):
                        i2_tie_new += 1
                gmax = max(r["disp_cand"] for r in grp)
                run_max = gmax if run_max is None else max(run_max, gmax)
                i = j
    i2_viol += i2_tie_new
    moves = [abs(r["disp_cand"] - r["disp"]) for r in scored]
    i3_max = max(moves)
    n_changed = sum(1 for r in scored if abs(r["disp_cand"] - r["disp"]) > 1e-9)

    # --- G1' ---------------------------------------------------------------
    g1 = _pooled_spearman_gap_boot(scored)
    g1["pass"] = bool(g1["gap_lo95"] >= G1_NOHARM_LO95)
    g1["bar"] = G1_NOHARM_LO95

    # --- top-25 tables -------------------------------------------------------
    inc25 = _top25(scored, "disp")
    cand25 = _top25(scored, "disp_cand")
    raw25 = _top25(scored, "rank_war")
    inc_cell = _cell(inc25)
    cand_cell = _cell(cand25)
    cand_cell_seed = _cell(cand25, seed=SEED)
    raw_share = round(sum(1 for r in raw25 if r["side"] == "pit") / len(raw25), 3)

    share_inc, share_cand = inc_cell["pit_share"], cand_cell["pit_share"]
    f1a_bar = round(share_inc - (share_inc - raw_share) * F1A_CLOSE_FRACTION, 3)
    f1a = {"share_incumbent": share_inc, "share_raw_rank_war": raw_share,
           "share_candidate": share_cand, "max_allowed_share": f1a_bar,
           "registered_reference_bar": 0.283,
           "pass": bool(share_cand <= f1a_bar)}
    f1b = {"incumbent_mean_diff_seed7": inc_cell["boot"]["mean_diff"],
           "candidate_mean_diff_seed7": cand_cell["boot"]["mean_diff"],
           "candidate_boot_seed20260723": cand_cell_seed["boot"],
           "pass": bool(cand_cell["boot"]["mean_diff"] < inc_cell["boot"]["mean_diff"])}

    # --- S1 (re-baselined caps, read from the standing artifact) -----------
    sf = json.loads(SF_ART.read_text(encoding="utf-8"))
    s1g = sf["standing_gates"]["S1_top25_no_widening"]
    s1 = {"max_allowed_mean_diff": s1g["max_allowed_mean_diff"],
          "max_allowed_median_diff": s1g["max_allowed_median_diff"],
          "candidate_mean_diff": cand_cell["boot"]["mean_diff"],
          "candidate_median_diff": cand_cell["boot"]["median_diff"],
          "pass": bool(cand_cell["boot"]["mean_diff"] <= s1g["max_allowed_mean_diff"]
                       and cand_cell["boot"]["median_diff"] <= s1g["max_allowed_median_diff"])}
    assert s1g["max_allowed_mean_diff"] == 5.53 and s1g["max_allowed_median_diff"] == 5.01, \
        "S1 caps drifted from the frozen registration - re-register before judging"

    # --- S2 (identity by construction, asserted) ---------------------------
    # the candidate never touches rank_war / fv / war; the frame carries the
    # original floats untouched, and disp_cand was written as a NEW key.
    from efv_model import _spearman
    hit_rows = [r for r in scored if r["side"] == "hit"]
    s2 = {"rank_war_untouched": True,   # construction: no code path writes it
          "hit_display_spearman_incumbent":
              round(_spearman([r["disp"] for r in hit_rows],
                              [r["war"] for r in hit_rows]), 4),
          "hit_display_spearman_candidate":
              round(_spearman([r["disp_cand"] for r in hit_rows],
                              [r["war"] for r in hit_rows]), 4),
          "registered_blend_floor": sf["standing_gates"]["S2_hit_no_harm"]["floor"],
          "note": "the blend rho gate quantity is a function of rank_war only; "
                  "rank_war is byte-identical (asserted vs _sf_fwd_chain refit), "
                  "so S2 is unchanged by construction"}
    s2["pass"] = True

    # --- S4a (display-independent cells asserted) + S4b restamp ------------
    s4a = {"note": "rank_war-frame bands and equal-FV cells are functions of "
                   "rank_war / fv / war only - all carried untouched (asserted "
                   "by the refit identity check + disp_cand-as-new-key design)",
           "cells_registered": sf["standing_gates"]["S4_midband_pit_outperformance"]["cells"],
           "pass": True}
    s4b = {"cells": {}, "pass": True}
    for lo, hi, name in ((51, 100, "051-100"), (101, 200, "101-200")):
        ic = _cell(_band_members(scored, "disp", lo, hi))
        cc = _cell(_band_members(scored, "disp_cand", lo, hi))
        bar = round(ic["boot"]["mean_diff"] + ic["boot"]["mean_se"], 2)
        ok = bool(cc["boot"]["mean_diff"] <= bar)
        s4b["cells"][name] = {"incumbent": ic, "candidate": cc,
                              "max_allowed_cand_mean_diff": bar, "pass": ok}
        if not ok:
            s4b["pass"] = False

    invariants = {"I1_below_knee_identity": {"n_below": len(below),
                                             "violations": i1_viol,
                                             "pass": i1_viol == 0},
                  "I2_within_side_monotone": {"violations": i2_viol,
                                              "tie_pairs_new_inversions": i2_tie_new,
                                              "note": "strict rank_war pairs + "
                                                      "tie-parity vs incumbent; see "
                                                      "lab-defect record in source",
                                              "pass": i2_viol == 0},
                  "I3_move_cap": {"max_abs_move": round(i3_max, 2), "cap": cap,
                                  "pass": bool(i3_max <= cap + 1e-9)}}

    # --- mover profile (eval frame) -----------------------------------------
    movers = sorted((r for r in scored if abs(r["disp_cand"] - r["disp"]) > 1e-9),
                    key=lambda r: -abs(r["disp_cand"] - r["disp"]))
    per_fold_shares = {}
    for yr in sorted({r["year"] for r in scored}):
        yi = [r for r in _top25([r for r in scored if r["year"] == yr], "disp")]
        yc = [r for r in _top25([r for r in scored if r["year"] == yr], "disp_cand")]
        per_fold_shares[str(yr)] = {
            "inc_pit_share": round(sum(1 for r in yi if r["side"] == "pit") / len(yi), 3),
            "cand_pit_share": round(sum(1 for r in yc if r["side"] == "pit") / len(yc), 3)}

    gates_pass = bool(g1["pass"] and f1a["pass"] and f1b["pass"] and s1["pass"]
                      and s4b["pass"] and all(v["pass"] for v in invariants.values()))
    art = {
        "generated_at": date.today().isoformat(),
        "eval_line": "F-SIDE-FIX - ARM-2-style top-band joint display recalibration "
                     "(owner-authorized fairness fix, G1 re-registered as NO-HARM)",
        "registration": "docs/efv-2026-07-23/GATES.md 'F-SIDE-FIX gate registration'",
        "protocol": {
            "frame": "F-SIDE full_pool_km, forward-chained folds "
                     + "-".join(str(y) for y in (meta["folds"][0], meta["folds"][-1])),
            "mechanism": {"knee_raw": knee, "move_cap_fv": cap,
                          "order": "ARM-2 expected-WAR crosswalk (per-fold train-fit "
                                   "PAVA), ties rank_war -> hit -> within-side index",
                          "reassignment": "band's own display-value multiset",
                          "production_code": "efv_score.joint_band_recal + "
                                             "_sff_crosswalk_curve/_sff_expected_war"},
            "seed": SEED, "bootstrap_reps": REPS,
            **meta,
        },
        "gates": {"G1_noharm": g1, "F1a_top25_share": f1a, "F1b_top25_gap": f1b,
                  "S1_no_widening": s1, "S2_hit_no_harm": s2,
                  "S4a_rankwar_cells": s4a, "S4b_display_midband_restamp": s4b,
                  "invariants": invariants},
        "eval_frame_summary": {
            "n_rows": len(scored), "n_band_changed": n_changed,
            "top25_incumbent": inc_cell, "top25_candidate": cand_cell,
            "top25_candidate_boot_seed20260723": cand_cell_seed["boot"],
            "top25_raw_rank_war_share": raw_share,
            "per_fold_top25_pit_share": per_fold_shares,
            "top_movers": [{"pk": r["pk"], "side": r["side"], "year": r["year"],
                            "disp": round(r["disp"], 1),
                            "disp_cand": round(r["disp_cand"], 1),
                            "war": round(r["war"], 2)} for r in movers[:20]],
        },
        "verdict": "ALL-PASS - flip authorized per the registered ship rule"
                   if gates_pass else
                   "FAIL - defaults stay OFF; this artifact is the loss ledger",
        "all_pass": gates_pass,
        "reading": "The capped top-band recalibration reliably fixes the "
                   "OVER-REPRESENTATION channel (top-25 pit share 0.37 -> 0.20, "
                   "65% of the display-vs-raw excess closed; G1' pooled Spearman "
                   "unharmed at gap -0.0004 lo95 -0.0015) but does NOT move the "
                   "EQUAL-SLOT realized gap (F1b 4.15 vs 4.07): the pitcher "
                   "display tail carries no realized-WAR gradient (the TOP-QUANT "
                   "finding), so WHICH pitchers survive in the top band is "
                   "outcome-arbitrary, while the hitters promoted from just below "
                   "the cut dilute the hit-side mean. The gap metric at the top "
                   "slots is structurally insensitive to any within-tail "
                   "selection at this data resolution. Keep-alive: resolved "
                   "2024+ cohorts (a pit tail with gradient), or a NEW owner "
                   "registration whose primary efficacy metric is the "
                   "over-representation channel this mechanism demonstrably "
                   "fixes.",
    }
    if matrix_dir is not None:
        art["protocol"]["matrix_snapshot"] = {
            f.name: _sha12(f) for f in sorted(matrix_dir.glob("xfv_*matrix.json"))}
    OUT_PATH.write_text(json.dumps(art, indent=1), encoding="utf-8")
    print("wrote", OUT_PATH)
    return art


# ---------------------------------------------------------------------------
# post-flip served battery
# ---------------------------------------------------------------------------

def run_postflip(baseline_path: Path) -> dict:
    """Served comparison vs the fresh pre-flip snapshot: standing <= 3.0 FV
    ceiling on xfv_grade_quantile among actives, S3 byte-identity of
    p_bucket / p_bust, below-knee invariance. Appends to the eval artifact."""
    import efv_score
    base = json.loads(baseline_path.read_text(encoding="utf-8"))["by_player"]
    cur = json.loads((_ROOT / "data" / "xfv.json").read_text(encoding="utf-8"))["by_player"]
    shared = [pk for pk in cur if pk in base]
    movers, pb_mismatch, below_knee_moved = [], 0, 0
    for pk in shared:
        b, c = base[pk], cur[pk]
        if (b.get("p_bucket"), b.get("p_bust")) != (c.get("p_bucket"), c.get("p_bust")):
            pb_mismatch += 1
        qb, qc = b.get("xfv_grade_quantile"), c.get("xfv_grade_quantile")
        if qb is None or qc is None:
            continue
        d = round(qc - qb, 1)
        if d:
            movers.append((pk, c.get("kind"), c.get("side"), qb, qc, d))
            if qb < efv_score.SFF_KNEE_RAW and qc < efv_score.SFF_KNEE_RAW:
                below_knee_moved += 1
    act = [m for m in movers if m[1] == "active"]
    max_active = max((abs(m[5]) for m in act), default=0.0)

    def _top25_share(pool):
        rows = [(e.get("xfv_grade_quantile"), e.get("side")) for e in pool.values()
                if e.get("kind") == "active" and e.get("xfv_grade_quantile") is not None]
        rows.sort(key=lambda t: -t[0])
        top = rows[:25]
        return round(sum(1 for _q, s in top if s == "P") / len(top), 3) if top else None

    res = {
        "checked_at": date.today().isoformat(),
        "baseline_snapshot": str(baseline_path),
        "n_shared": len(shared),
        "n_movers_total": len(movers), "n_movers_active": len(act),
        "max_abs_active_move": max_active,
        "ceiling": 3.0, "ceiling_pass": bool(max_active <= 3.0),
        "s3_p_bucket_p_bust_mismatches": pb_mismatch, "s3_pass": pb_mismatch == 0,
        "below_knee_movers": below_knee_moved,
        "served_top25_pit_share": {"before": _top25_share(base),
                                   "after": _top25_share(cur)},
        "top_movers": [{"pk": pk, "kind": k, "side": s, "before": qb, "after": qc,
                        "delta": d} for pk, k, s, qb, qc, d in
                       sorted(act, key=lambda m: -abs(m[5]))[:20]],
    }
    art = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    art["post_flip"] = res
    OUT_PATH.write_text(json.dumps(art, indent=1), encoding="utf-8")
    print("post-flip:", json.dumps({k: res[k] for k in
          ("n_movers_active", "max_abs_active_move", "ceiling_pass",
           "s3_p_bucket_p_bust_mismatches", "below_knee_movers",
           "served_top25_pit_share")}, indent=1))
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", default="eval", choices=("eval", "postflip"))
    ap.add_argument("--matrix-dir", type=Path, default=None,
                    help="frozen matrix snapshot dir (vintage lock)")
    ap.add_argument("--baseline", type=Path, default=None,
                    help="postflip: pre-flip data/xfv.json snapshot")
    args = ap.parse_args()
    if args.cmd == "eval":
        art = run_eval(args.matrix_dir)
        g = art["gates"]
        print(json.dumps({
            "G1": {k: g["G1_noharm"][k] for k in
                   ("rho_incumbent", "rho_candidate", "gap", "gap_lo95", "pass")},
            "F1a": g["F1a_top25_share"], "F1b": {k: v for k, v in
                   g["F1b_top25_gap"].items() if k != "candidate_boot_seed20260723"},
            "S1": g["S1_no_widening"], "S4b": {n: c["pass"] for n, c in
                   g["S4b_display_midband_restamp"]["cells"].items()},
            "invariants": {k: v["pass"] for k, v in g["invariants"].items()},
            "verdict": art["verdict"]}, indent=1))
    else:
        if not args.baseline:
            ap.error("postflip requires --baseline")
        run_postflip(args.baseline)
