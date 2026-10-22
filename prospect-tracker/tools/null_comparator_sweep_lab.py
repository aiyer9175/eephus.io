# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Null comparator sweep (registration: docs/NULL_COMPARATOR_SWEEP.md).

Why it exists. On 2026-10-15 the positional ladder v2 passed its registered rule
(it beat v1) and an all-zero ladder then tied it: a rule that compares a candidate
only against the incumbent can pass a flat candidate when the loss rewards
shrinkage. This lab carries the census of every model_registry row whose verdict
is validated, plus every provisional row with a served comparative claim, and runs
the registered null comparators ONCE on the stored eval frame of the rows that
lacked one.

Runs (each defined in the registration, section 7):
  S1  fa_projection_marcel: Gate 1 WAR frame (fa_backtest.run_projection_gate,
      persist=False), nulls ZERO and POPULATION-MEAN constant.
  S2  fa_war_paths_decay + mlb_projections_vets: the proj_eval row-matched frame
      (bases 2017, 2018, 2019, 2021), nulls ZERO and the Gate 1 5/4/3 WAR carry
      held flat over the five horizons.
  S3  draft_slot_curve: the artifact's own 2015-18 first-8 holdout, nulls FLAT
      (the fit years' pooled mean) and ZERO.

Every cell carries two instrument checks (a planted-better arm the lab must
see as better and a planted-worse arm it must see as worse); a cell whose check
fails is VOID. Nothing here writes a served file: the lab writes
data/null_comparator_sweep.json (deploy-excluded, rendered nowhere) and
docs/null-comparator-sweep/RESULTS.md, and every projection cache it touches is
redirected to a private copy (--cache-dir), never the shared .cache.

Usage:
  python tools/null_comparator_sweep_lab.py --dry-run --out-dir <scratch>
  python tools/null_comparator_sweep_lab.py --run --cache-dir <scratch cache>
A second --run refuses once data/null_comparator_sweep.json records one.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
import tempfile
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

DATA_DIR = ROOT / "data"
OUT_JSON = DATA_DIR / "null_comparator_sweep.json"
RESULTS_MD = ROOT / "docs" / "null-comparator-sweep" / "RESULTS.md"
REGISTRATION = "docs/NULL_COMPARATOR_SWEEP.md"
SEED = 20261022
REPS = 2000
S2_BASES = (2017, 2018, 2019, 2021)

# ---------------------------------------------------------------------------
# The census (registration section 5 and 6). One tuple per row in scope:
# (model_id, verdict at registration, served, comparator the gate used,
#  null status, planted-recovery check, action, note)
# null status: PRESENT (a zero, naive, permuted or claimed-against comparator
#   was in the gate), ANALYTIC (the null value is known by construction, e.g. an
#   AUC of 0.5 or a rank correlation of 0), MISSING, or NA (no comparative claim).
# action: COVERED, RUN:S1/S2/S3, DEFERRED, NA.
# ---------------------------------------------------------------------------
CENSUS = [
    # ---- validated ----
    ("ba_source_classification", "validated", False, "the hardcoded insufficient-history list", "NA", False, "NA",
     "a data derivation (row counts), no predictive claim"),
    ("c3_proj_trans_recal", "validated", True, "the clamped band", "NA", False, "NA",
     "a clamp audit judged on monotone invariance; no accuracy claim"),
    ("consensus_contamination", "validated", False, "zero-information control", "PRESENT", False, "NA",
     "a measurement; the leak claim already failed its control"),
    ("consensus_coverage_shrinkage", "validated", False, "permuted-coverage control", "PRESENT", False, "NA",
     "a null result"),
    ("consensus_fv", "validated", True, "best single source on the same rows, argmax redrawn per draw", "PRESENT", False, "COVERED",
     "claims to beat the sources it blends; AUC null 0.5 is analytic (served AUC 0.767)"),
    ("consensus_org_rank_split", "validated", True, "the label-only guard", "NA", False, "NA",
     "a correctness repair; zero rows of the grade move"),
    ("consensus_rank", "validated", False, "rank permuted within cell", "PRESENT", False, "NA",
     "a measurement with a permutation null"),
    ("consensus_recency_decay", "validated", False, "permuted publication dates", "PRESENT", False, "NA",
     "a null result"),
    ("draft_slot_curve", "validated", True, "the hand-set step table only", "MISSING", False, "RUN:S3",
     "no flat or zero curve was scored on the 2015-18 holdout"),
    ("efv_scoreboard", "validated", True, "consensus FV on identical rows", "PRESENT", False, "COVERED",
     "the comparator is the consensus it is read against"),
    ("eta", "validated", True, "naive level-to-years table", "PRESENT", False, "COVERED",
     "naive table is the null"),
    ("eta_fg_blend", "validated", True, "CH40 champion", "MISSING", False, "DEFERRED",
     "FanGraphs ETA alone was registered as NOT scored on the look frame (a source score over 2025-26 debut rows); owner question"),
    ("fa_dpw_series", "validated", True, "fitted trend and trend plus CBT", "PRESENT", False, "COVERED",
     "the winner IS the naive flat carry"),
    ("fa_market", "validated", True, "nearest-comps median, trend inflated", "PRESENT", False, "COVERED",
     "comps median is the naive null"),
    ("fa_projection_marcel", "validated", True, "5/4/3 carry-forward of actual WAR", "PRESENT", False, "RUN:S1",
     "carry-forward is present; a zero or constant prediction was never scored, and MAE on an absent-as-zero label rewards shrinkage"),
    ("fa_war_paths_decay", "validated", True, "marcel_decay_v2 champion", "MISSING", False, "RUN:S2",
     "challenger vs champion only; no zero or carry path on the horizon frame"),
    ("fv_to_war_anchors", "validated", True, "public primer table", "MISSING", False, "DEFERRED",
     "any null needs an FV-cell realized WAR mean: docs/PROSPECT_ANCHOR_GATE.md"),
    ("hem_plus_3yr", "validated", True, "single-season HEM+ on the same set", "PRESENT", False, "COVERED",
     "single-season HEM+ is the naive carry of the same metric"),
    ("dem_plus", "validated", True, "fielding pct, innings, raw rate; permuted twin", "PRESENT", False, "COVERED",
     "ties its raw parent, disclosed"),
    ("mlb_projections_vets", "validated", True, "inherits Gate 1 and the horizon eval", "MISSING", False, "RUN:S2",
     "row-matched claim h1 0.5846 vs 0.5988 has no zero or carry path"),
    ("phem_marcel_lite", "validated", True, "1yr HEM+, flat 3yr, textbook Marcel", "PRESENT", False, "COVERED",
     "1yr HEM+ is the naive carry"),
    ("plus_metric_recal", "validated", True, "clamped display", "NA", False, "NA",
     "a clamp audit judged on invariance"),
    ("positional_ladder", "validated", True, "folklore table, level-corrected; zero-information control; H0 shape simulation", "PRESENT", True, "COVERED",
     "control at -5.02 runs; the consumer-level predictive gate is already a NULL"),
    ("proj_def_prior", "validated", True, "the model without the feature", "PRESENT", False, "COVERED",
     "an ablation: the zero-adjustment null"),
    ("prospect_surplus", "validated", True, "identity calibration", "PRESENT", False, "DEFERRED",
     "re-measure waits for the Prospect Anchor look (row note); its frame is the surplus backtest, never run here"),
    ("pwoba_blend_regate", "validated", True, "incumbent pWOBA, xwOBA alone", "PRESENT", False, "COVERED",
     "xwOBA(Y) alone is a naive carry"),
    ("rem_plus", "validated", True, "ERA, raw FIP, raw WPA", "PRESENT", False, "COVERED",
     "ERA is the naive carry"),
    ("savant_sprint", "validated", True, "r = 0 (no range read)", "PRESENT", False, "COVERED",
     "Fisher CI lower bound vs zero"),
    ("sc_plus_component_diagnostic", "validated", False, "n/a", "NA", False, "NA", "a measurement"),
    ("sem_plus", "validated", True, "ERA, raw FIP", "PRESENT", False, "COVERED", "ERA is the naive carry"),
    ("source_cohort_accuracy", "validated", True, "equal weight, random-cohort control", "PRESENT", False, "NA",
     "a null result; no weight ships"),
    ("source_track_record", "validated", True, "n/a", "NA", False, "NA", "a measurement"),
    ("surplus_decomposition_v6", "validated", False, "zero-information constant board, permuted truth", "PRESENT", False, "NA",
     "a measurement"),
    ("surplus_sensitivity_diagnostic", "validated", False, "n/a", "NA", False, "NA", "an invariance measurement"),
    ("war_cohort_diagnostic", "validated", False, "n/a", "NA", False, "NA", "a measurement"),
    ("xfv_bughunt2", "validated", False, "n/a", "NA", False, "NA", "an audit"),
    ("xfv_dist_calibration", "validated", False, "n/a", "NA", False, "NA", "a measurement"),
    ("xfv_dist_recalibration", "validated", False, "permuted-tier twin, zero-information constant", "PRESENT", False, "NA",
     "a no-ship; the constant reproduced 152.7 percent of the gain"),
    ("xfv_label_censoring", "validated", False, "n/a", "NA", False, "NA", "a measurement"),
    ("xfv_label_replacement", "validated", False, "level twin, permuted share profile", "PRESENT", False, "NA",
     "a null result"),
    ("xfv_lambda_adjudication", "validated", False, "null E (frozen stamps)", "PRESENT", False, "COVERED",
     "lab artifact"),
    ("xfv_lambda_reselect", "validated", True, "lambda grid from 0.5 (no consensus-alone arm)", "MISSING", False, "DEFERRED",
     "scored years 2020-2023 overlap the reserved list-vintage frame R-LV; consensus-vs-eFV v1 is a tie in xfv_hitter and xfv_headtohead_frame"),
    ("xfv_level_rank_fringe", "validated", False, "the lean set without the feature", "PRESENT", False, "COVERED",
     "ablation null; never re-run (its t45 cell is a consensus-FV stratum)"),
    ("xfv_odds_calibration_slope", "validated", True, "incumbent curve and a constant base rate", "PRESENT", False, "COVERED",
     "beats the constant, CI clear of zero"),
    ("xfv_ops_rel_fringe", "validated", False, "the lean set without the feature", "PRESENT", False, "COVERED",
     "ablation null; never re-run (consensus-FV stratum)"),
    ("xfv_rank_objective", "validated", False, "permuted-weight control", "PRESENT", False, "NA", "a null result"),
    ("xfv_stale_anchor", "validated", True, "the raw anchor served as fresh (zero decay)", "PRESENT", False, "DEFERRED",
     "zero adjustment is present; a time-flat discount null needs bust rates by FV band (PROSPECT_ANCHOR_GATE)"),
    ("xhem_plus", "validated", True, "actual wOBA forward rho", "PRESENT", False, "COVERED",
     "actual wOBA(Y) is the naive carry"),
    ("xfv_side_calibration", "validated", False, "the other side within band", "NA", False, "NA",
     "an audit; FV-band realized means, never re-run"),
    ("xfv_headtohead_frame", "validated", True, "consensus FV on identical rows", "PRESENT", False, "COVERED",
     "the served copy is a tie"),
    ("xfv_ewar_label_epoch", "validated", False, "zero-information twin, permutation null", "PRESENT", False, "NA",
     "a measurement"),
    ("hof_induction_ledger", "validated", False, "the unrepaired ledger", "NA", False, "NA", "a repair"),
    ("hof_public_bakeoff", "validated", True, "JAWS reference and the resampled public argmax", "PRESENT", False, "COVERED",
     "the served comparison is a loss, said as a loss"),
    ("efv_matrix", "validated", True, "PROSPX consensus on identical rows", "PRESENT", False, "COVERED",
     "comparator is the consensus"),
    ("fa_destination", "validated", False, "random, payroll, permuted control L_perm", "PRESENT", False, "COVERED",
     "not served"),
    # ---- provisional rows with a served comparative claim ----
    ("arb_award", "provisional", True, "MDE95 floor and a zero-information control", "PRESENT", False, "COVERED", ""),
    ("betting_game_prob", "provisional", True, "home-field constant, flat 0.500", "PRESENT", False, "COVERED", ""),
    ("college_translation", "provisional", True, "predict-the-Single-A-mean", "PRESENT", False, "COVERED", ""),
    ("college_translation_scorecard", "provisional", True, "predict-the-Single-A-mean", "PRESENT", False, "COVERED", ""),
    ("control_window_salary_path", "provisional", True, "no price (surplus 0)", "PRESENT", False, "COVERED", ""),
    ("draft_consensus_weight", "provisional", True, "best single source, equal weight", "PRESENT", False, "COVERED",
     "the edge is within noise, said so"),
    ("eta_hazard_lite", "provisional", True, "the incumbent path (zero adjustment)", "PRESENT", False, "COVERED", ""),
    ("farm_grades", "provisional", True, "prospect-count ranking", "PRESENT", False, "COVERED", ""),
    ("fwdhem_plus", "provisional", True, "xwOBA alone", "PRESENT", False, "COVERED", ""),
    ("btblend_plus", "provisional", True, "the served xHEM+ Blend; xwOBA alone", "PRESENT", False, "COVERED", ""),
    ("dem_plus_3yr", "provisional", True, "single-season DEM+", "PRESENT", False, "COVERED", ""),
    ("rem_plus_3yr", "provisional", True, "single-season REM+", "PRESENT", False, "COVERED", ""),
    ("sem_plus_3yr", "provisional", True, "single-season SEM+", "PRESENT", False, "COVERED", ""),
    ("leverage_consistency", "provisional", True, "a fixed bar (rho 0.30) above zero", "PRESENT", False, "COVERED", ""),
    ("mlb_projections_prospects", "provisional", True, "three stat-line challengers", "ANALYTIC", False, "COVERED",
     "a rank claim; a constant has rank correlation 0"),
    ("mlb_projections_prospects_statline", "provisional", True, "B0 league-average rookie line", "PRESENT", False, "COVERED", ""),
    ("overseas_translation", "provisional", True, "published primer factors", "MISSING", False, "DEFERRED",
     "n 3 KBO hitters; no null can be powered"),
    ("proj_components", "provisional", True, "naive three-season rate", "PRESENT", False, "COVERED", ""),
    ("spotlights_movement", "provisional", True, "random matched controls", "PRESENT", False, "COVERED", ""),
    ("statcast_alevel_display", "provisional", True, "the stat line alone", "PRESENT", False, "COVERED", ""),
    ("stuff_plus_aaa", "provisional", True, "r = 0", "ANALYTIC", False, "COVERED", ""),
    ("statcast_plus", "provisional", True, "publish-the-r", "ANALYTIC", False, "COVERED", ""),
    ("team_win_projections", "provisional", True, "prior-season wins carry-forward", "PRESENT", False, "COVERED", ""),
    ("etool_ehit", "provisional", True, "the consensus tool grade", "PRESENT", False, "COVERED", ""),
    ("etool_epow", "provisional", True, "the consensus tool grade", "PRESENT", False, "COVERED", ""),
    ("etool_esel", "provisional", True, "the consensus tool grade", "PRESENT", False, "COVERED", ""),
    ("etool_ebat", "provisional", True, "the consensus tool grade", "PRESENT", False, "COVERED", ""),
    ("etool_efb", "provisional", True, "the consensus tool grade", "PRESENT", False, "COVERED", ""),
    ("etool_ecmd", "provisional", True, "the consensus tool grade", "PRESENT", False, "COVERED", ""),
    ("trade_machine_surplus", "provisional", True, "consensus FV ordering", "PRESENT", False, "COVERED", ""),
    ("fantasy_combined_rank", "provisional", True, "vintage consensus FV rank", "PRESENT", False, "COVERED",
     "loses to consensus, said so"),
    ("mock_draft", "provisional", True, "the raw consensus board", "PRESENT", False, "COVERED", ""),
    ("grpo_prospect", "provisional", True, "zero-information shuffle, FV-only control", "PRESENT", False, "COVERED", ""),
    ("scores_mlb_wp", "provisional", True, "home-win base rate", "PRESENT", False, "COVERED", ""),
    ("rpw_fit", "provisional", True, "FanGraphs closed form", "PRESENT", False, "COVERED", ""),
    ("milb_fielding_runs", "provisional", True, "zero, fielder shuffle, within-position permutation", "PRESENT", True, "COVERED",
     "the reference design: null plus planted recovery"),
    ("efv_v2", "provisional", True, "PROSPX consensus and eFV v1", "PRESENT", True, "COVERED", "served as a tie"),
    ("xfv_thin_pbust", "provisional", True, "grade-only curve, constant, permuted grade and level", "PRESENT", False, "COVERED", ""),
    ("xfv_tools", "provisional", True, "consensus tool grade alone", "PRESENT", False, "COVERED", ""),
    ("xfv_ungraded", "provisional", True, "rank vs zero; constant first-grade MAE", "PRESENT", False, "COVERED",
     "loses the level to a constant, said so"),
    ("provisional_first_grade", "provisional", True, "per-set constant, level-rank and younger nulls", "PRESENT", False, "COVERED", ""),
    ("provisional_v2", "provisional", True, "level-rank and younger nulls, constant", "PRESENT", False, "COVERED", ""),
    ("ifa_step_prior", "provisional", True, "difference vs zero", "PRESENT", False, "COVERED", ""),
    ("xfv_statcast_line", "provisional", True, "unadjusted AAA lines", "PRESENT", False, "COVERED", ""),
    ("xfv_odds_grade_basis", "provisional", True, "the re-key and a constant", "PRESENT", False, "COVERED",
     "loses to the constant, said so"),
    ("fa_team_fit", "provisional", True, "random, payroll-only, behavior-only", "PRESENT", False, "COVERED", ""),
    ("fv_outcome_pooled_grade", "provisional", True, "the side-neutral inversion", "MISSING", False, "DEFERRED",
     "an FV-to-outcome curve: PROSPECT_ANCHOR_GATE"),
]

# Stored numbers the reproduction checks compare against (quoted, never refit).
STORED = {
    "S1": {"artifact": "data/fa_gate1_eval.json", "label": "ewar_v2",
           "war_mae_model": 0.5156555204307136, "war_mae_base": 0.6242164570411276, "n": 20721},
    "S2": {"artifact": "data/proj_horizon_eval.json", "block": "rowmatch_champion_vs_challenger",
           "label": "pre-epoch (2026-08-19)",
           "champion_mae": {1: 0.5988, 2: 0.5188, 3: 0.4635, 4: 0.3957, 5: 0.3692},
           "challenger_mae": {1: 0.5846, 2: 0.4917, 3: 0.4356, 4: 0.3758, 5: 0.3586}, "n": 8053},
    "S3": {"artifact": "data/draft_slot_curve.json", "label": "fwar",
           "holdout_mae_fitted_first8": 2.73},
}


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
def _verdict(lo: float | None, hi: float | None) -> str:
    """delta = loss(null) - loss(model). BEATS: the model beats the null."""
    if lo is None or hi is None:
        return "UNSCORED"
    if lo > 0:
        return "BEATS"
    if hi < 0:
        return "LOSES"
    return "TIES"


def cluster_delta(keys, loss_a, loss_b, seed: int, reps: int = REPS) -> dict:
    """Mean(loss_a) - mean(loss_b) with a cluster bootstrap (resample cluster
    keys with replacement; a drawn cluster brings all its rows)."""
    import numpy as np
    if len(keys) == 0:
        return {"n": 0, "point": None, "lo95": None, "hi95": None}
    loss_a = np.asarray(loss_a, dtype=float)
    loss_b = np.asarray(loss_b, dtype=float)
    _, inv = np.unique(np.asarray([str(k) for k in keys]), return_inverse=True)
    k = int(inv.max()) + 1
    sa = np.bincount(inv, weights=loss_a, minlength=k)
    sb = np.bincount(inv, weights=loss_b, minlength=k)
    cnt = np.bincount(inv, minlength=k).astype(float)
    rng = np.random.default_rng(seed)
    draws = np.empty(reps)
    for r in range(reps):
        c = np.bincount(rng.integers(0, k, k), minlength=k).astype(float)
        tot = (c * cnt).sum()
        draws[r] = ((c * sa).sum() - (c * sb).sum()) / tot
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return {"n": int(len(keys)), "clusters": k,
            "point": round(float(loss_a.mean() - loss_b.mean()), 5),
            "lo95": round(float(lo), 5), "hi95": round(float(hi), 5)}


def _mae_cell(keys, pred_model, act, nulls: dict, seed: int) -> dict:
    """One MAE cell: model vs each null, plus the two instrument checks."""
    import numpy as np
    act = np.asarray(act, dtype=float)
    pm = np.asarray(pred_model, dtype=float)
    out = {"n": int(len(act)), "mae_model": round(float(np.abs(pm - act).mean()), 4) if len(act) else None,
           "nulls": {}}
    if not len(act):
        out["instrument"] = {"verdict": "UNSCORED"}
        return out
    em = np.abs(pm - act)
    for name, pn in nulls.items():
        en = np.abs(np.asarray(pn, dtype=float) - act)
        d = cluster_delta(keys, en, em, seed)
        d["mae_null"] = round(float(en.mean()), 4)
        d["verdict"] = _verdict(d["lo95"], d["hi95"])
        out["nulls"][name] = d
    # instrument: planted-better (half way to the truth) must beat the model;
    # planted-worse (model plus residual-scale noise, seeded) must lose to it.
    rng = np.random.default_rng(seed + 7)
    better = 0.5 * pm + 0.5 * act
    worse = pm + rng.normal(0.0, float(np.std(act - pm)) or 1.0, len(pm))
    chk_b = cluster_delta(keys, em, np.abs(better - act), seed + 1)
    chk_w = cluster_delta(keys, np.abs(worse - act), em, seed + 2)
    ok = (_verdict(chk_b["lo95"], chk_b["hi95"]) == "BEATS"
          and _verdict(chk_w["lo95"], chk_w["hi95"]) == "BEATS")
    out["instrument"] = {"planted_better": chk_b, "planted_worse": chk_w,
                         "verdict": "PASS" if ok else "VOID"}
    return out


# ---------------------------------------------------------------------------
# Cache isolation: the projection modules write disk caches; a lab must never
# write the shared .cache (a junction other worktrees read).
# ---------------------------------------------------------------------------
def isolate_caches(cache_dir: Path) -> dict:
    import glob
    import fa_projection as fp
    src = Path(fp.CACHE_DIR)
    cache_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for pat in ("fa_corpus.pkl", "xstats.pkl", "fa_fits_*.pkl",
                "proj_ml_frame_*fwar*.pkl", "proj_ml_pit_*fwar*.joblib"):
        for f in glob.glob(str(src / pat)):
            dst = cache_dir / Path(f).name
            if not dst.exists():
                shutil.copy2(f, dst)
                copied += 1
    fp.CACHE_DIR = cache_dir
    fp.CORPUS_CACHE = cache_dir / "fa_corpus.pkl"
    fp._XSTATS_CACHE = cache_dir / "xstats.pkl"
    return {"cache_dir": str(cache_dir), "files_copied": copied, "source": str(src)}


# ---------------------------------------------------------------------------
# S1: Gate 1 WAR frame
# ---------------------------------------------------------------------------
def run_s1(seed: int) -> dict:
    import fa_backtest as fb
    import fa_projection as fp
    t0 = time.time()
    fb.GATE1_COLLECT = []
    try:
        summary = fb.run_projection_gate(persist=False, reexport=False)
        rows = list(fb.GATE1_COLLECT)
    finally:
        fb.GATE1_COLLECT = None
    corpus = fp.build_corpus()
    last_war = {}
    for side in ("hit", "pit"):
        for r in corpus[side]:
            if r.get("mlbam"):
                last_war[(side, r["mlbam"], r["season"])] = r.get("war")
    by_t = defaultdict(list)
    for (t, side, m, _p, _a) in rows:
        by_t[t].append(last_war.get((side, m, t - 1)) or 0.0)
    const = {t: sum(v) / len(v) for t, v in by_t.items()}
    cells = {}
    for cell, keep in (("pooled", lambda s: True), ("hit", lambda s: s == "hit"),
                       ("pit", lambda s: s == "pit")):
        sub = [r for r in rows if keep(r[1])]
        cells[cell] = _mae_cell([r[2] for r in sub], [r[3] for r in sub], [r[4] for r in sub],
                                {"ZERO": [0.0] * len(sub),
                                 "POP_MEAN": [const[r[0]] for r in sub]}, seed)
    pw = summary["pooled"]["war"]
    return {
        "frame": "fa_backtest.run_projection_gate(persist=False) WAR pool, targets "
                 f"{summary.get('targets')}, absent target season = 0 for every arm",
        "label": summary.get("war_provider"), "label_shape": summary.get("label_shape"),
        "reproduction": {"stored": STORED["S1"],
                         "now": {"war_mae_model": pw["mae_model"], "war_mae_base": pw["mae_base"], "n": pw["n"]},
                         "note": "the stored artifact is on the retired eWAR v2 label; the frame definition is "
                                 "reproduced on the current training label and every arm is scored on identical rows"},
        "population_mean_constants": {str(t): round(v, 4) for t, v in sorted(const.items())},
        "primary_cell": "pooled", "cells": cells, "seconds": round(time.time() - t0, 1),
    }


# ---------------------------------------------------------------------------
# S2: proj_eval row-matched horizon frame
# ---------------------------------------------------------------------------
def _carry_543(hist: list[dict], base: int) -> float:
    wn = wd = 0.0
    for h in hist:
        w = {1: 5.0, 2: 4.0, 3: 3.0}.get(base - h["season"])
        if w and h.get("war") is not None:
            wn += w * h["war"]
            wd += w
    return wn / wd if wd else 0.0


def run_s2(seed: int, bases=S2_BASES) -> dict:
    import fa_projection as fp
    import proj_eval as pe
    import proj_ml
    t0 = time.time()
    corpus = fp.build_corpus()
    league, by_player, war_actual = pe._assemble(corpus)
    rows = []          # (base, side, mlbam, h, champ, chal, carry, act)
    n_matched = 0
    for B in bases:
        curves, war_map = fp.fitted_models(corpus, B - 1, aging="v2")
        bundle = proj_ml.train_cached(corpus, B - 1, quantiles=proj_ml.QUANTILES)
        for side in ("hit", "pit"):
            for mlbam, seasons in by_player[side].items():
                hist = [seasons[t] for t in (B - 1, B - 2, B - 3) if t in seasons]
                if not hist:
                    continue
                age = proj_ml.age_from_history(hist, B)
                if age is None:
                    continue
                champ = pe.default_predict_fn(hist, side, B, age, curves, war_map, league)
                if champ is None:
                    continue
                feats = proj_ml.build_features(hist, side, B, age, curves, war_map, league, champ=champ)
                chal = proj_ml.predict_path(bundle, feats, side) if feats is not None else None
                if chal is None:
                    continue
                n_matched += 1
                carry = _carry_543(hist, B)
                for h in range(1, 6):
                    target = B + h - 1
                    if target > corpus["last"] - 1:
                        continue
                    rows.append((B, side, mlbam, h, champ["war_by_year"][h - 1],
                                 chal["war_by_year"][h - 1], carry,
                                 war_actual.get((mlbam, target), 0.0)))
    cells = {}
    for model_name, idx in (("challenger_proj_lgbm", 5), ("champion_decay", 4)):
        cells[model_name] = {}
        for cell in ("h1", "h2", "h3", "h4", "h5", "pooled_h1_h5"):
            sub = rows if cell.startswith("pooled") else [r for r in rows if r[3] == int(cell[1])]
            cells[model_name][cell] = _mae_cell(
                [r[2] for r in sub], [r[idx] for r in sub], [r[7] for r in sub],
                {"ZERO": [0.0] * len(sub), "CARRY_543_FLAT": [r[6] for r in sub]}, seed)
    now = {h: {"n": cells["champion_decay"][f"h{h}"]["n"],
               "champion_mae": cells["champion_decay"][f"h{h}"]["mae_model"],
               "challenger_mae": cells["challenger_proj_lgbm"][f"h{h}"]["mae_model"]}
           for h in range(1, 6)}
    return {
        "frame": f"proj_eval row-matched frame, bases {list(bases)}, horizons 1-5, label seasons <= "
                 f"{corpus['last'] - 1}, absent target season = 0 for every arm",
        "label": corpus.get("war_provider"), "label_shape": corpus.get("label_shape"),
        "n_players_matched": n_matched,
        "reproduction": {"stored": STORED["S2"], "now": now,
                         "note": "the stored block predates the 2026-09-18 two-way label repair and the "
                                 "fWAR epoch; both models are re-scored on identical rows in this run"},
        "primary_cell": "h1", "cells": cells, "seconds": round(time.time() - t0, 1),
    }


# ---------------------------------------------------------------------------
# S3: draft slot curve holdout
# ---------------------------------------------------------------------------
def _bucket_metric(rows_by_bucket: dict, preds: dict) -> float:
    errs = [abs(preds[b] - (sum(v) / len(v))) for b, v in rows_by_bucket.items() if v and b in preds]
    return sum(errs) / len(errs)


def run_s3(seed: int) -> dict:
    import numpy as np
    import war_source
    import fit_draft_slot_curve as f
    t0 = time.time()
    picks_by_year = {y: f.draft_picks(y) for y in f.DRAFT_YEARS}
    last_drafted = {}
    for y, picks in picks_by_year.items():
        for p in picks:
            last_drafted[p["mlbam"]] = max(last_drafted.get(p["mlbam"], 0), y)
    wars = f.war_by_player(war_source.DEFAULT_PROVIDER)
    fit_rows, hold = [], []
    for y, picks in picks_by_year.items():
        for p in picks:
            if p["pick"] > f.MAX_PICK or last_drafted[p["mlbam"]] > y:
                continue
            seasons = wars.get(p["mlbam"]) or {}
            if y in f.CAREER_FIT_YEARS:
                fit_rows.append((p["pick"], f._window_war(seasons, 8)))
            else:
                hold.append((p["pick"], f._window_war(seasons, 8), p["mlbam"]))
    curve = f.fit_curve(fit_rows)
    curve_b = f._curve_bucket_means(curve)
    flat = sum(w for _, w in fit_rows) / len(fit_rows)
    buckets = sorted(curve_b)
    preds = {"CURVE": dict(curve_b), "FLAT": {b: flat for b in buckets}, "ZERO": {b: 0.0 for b in buckets}}
    order = list(buckets)
    preds["PLANTED_WORSE"] = {b: curve_b[order[len(order) - 1 - i]] for i, b in enumerate(order)}
    by_b = defaultdict(list)
    for pick, w, _m in hold:
        by_b[f._bucket_of(pick)].append(w)
    realized = {b: sum(v) / len(v) for b, v in by_b.items()}
    preds["PLANTED_BETTER"] = {b: 0.5 * curve_b[b] + 0.5 * realized.get(b, curve_b[b]) for b in buckets}

    def pick_pred(name, pick):
        if name == "CURVE":
            return curve.get(pick, curve_b[f._bucket_of(pick)])
        return preds[name][f._bucket_of(pick)]

    point = {k: _bucket_metric(by_b, v) for k, v in preds.items()}
    mse = {k: float(np.mean([(pick_pred(k, p) - w) ** 2 for p, w, _ in hold]))
           for k in ("CURVE", "FLAT", "ZERO")}
    rng = np.random.default_rng(seed)
    draws = defaultdict(list)
    draws_mse = defaultdict(list)
    arr = {b: np.asarray(v) for b, v in by_b.items()}
    hold_by_b = defaultdict(list)
    for p, w, _ in hold:
        hold_by_b[f._bucket_of(p)].append((p, w))
    for _ in range(REPS):
        sample = {}
        sq = defaultdict(float)
        n_tot = 0
        for b, v in arr.items():
            idx = rng.integers(0, len(v), len(v))
            sample[b] = list(v[idx])
            rows_b = [hold_by_b[b][i] for i in idx]
            n_tot += len(rows_b)
            for k in ("CURVE", "FLAT", "ZERO"):
                sq[k] += sum((pick_pred(k, p) - w) ** 2 for p, w in rows_b)
        m = {k: _bucket_metric(sample, v) for k, v in preds.items()}
        for k in ("FLAT", "ZERO", "PLANTED_WORSE"):
            draws[k].append(m[k] - m["CURVE"])
        draws["PLANTED_BETTER"].append(m["CURVE"] - m["PLANTED_BETTER"])
        for k in ("FLAT", "ZERO"):
            draws_mse[k].append((sq[k] - sq["CURVE"]) / n_tot)

    def ci(v):
        lo, hi = np.percentile(v, [2.5, 97.5])
        return round(float(lo), 4), round(float(hi), 4)

    nulls = {}
    for k in ("FLAT", "ZERO"):
        lo, hi = ci(draws[k])
        lo2, hi2 = ci(draws_mse[k])
        nulls[k] = {"metric_null": round(point[k], 4), "point": round(point[k] - point["CURVE"], 4),
                    "lo95": lo, "hi95": hi, "verdict": _verdict(lo, hi),
                    "secondary_mse_null": round(mse[k], 4),
                    "secondary_mse_delta": round(mse[k] - mse["CURVE"], 4),
                    "secondary_lo95": lo2, "secondary_hi95": hi2,
                    "secondary_verdict": _verdict(lo2, hi2)}
    lb, hb = ci(draws["PLANTED_BETTER"])
    lw, hw = ci(draws["PLANTED_WORSE"])
    inst_ok = _verdict(lb, hb) == "BEATS" and _verdict(lw, hw) == "BEATS"
    return {
        "frame": "tools/fit_draft_slot_curve.py: first-8 curve fit on 2005-14 picks 1-500, scored on the "
                 "2015-18 holdout; metric = the artifact's holdout_mae (unweighted mean over buckets of "
                 "|bucket prediction - realized bucket mean|); bootstrap stratified by bucket",
        "label": war_source.DEFAULT_PROVIDER,
        "n_fit": len(fit_rows), "n_holdout": len(hold), "flat_constant": round(flat, 4),
        "reproduction": {"stored": STORED["S3"], "now": {"holdout_mae_fitted_first8": round(point["CURVE"], 3)},
                         "reproduces": round(point["CURVE"], 2) == STORED["S3"]["holdout_mae_fitted_first8"]},
        "primary_cell": "holdout_bucket_mae",
        "cells": {"holdout_bucket_mae": {"n": len(hold), "metric_model": round(point["CURVE"], 4),
                                         "secondary_mse_model": round(mse["CURVE"], 4), "nulls": nulls,
                                         "instrument": {"planted_better": {"lo95": lb, "hi95": hb},
                                                        "planted_worse": {"lo95": lw, "hi95": hw},
                                                        "verdict": "PASS" if inst_ok else "VOID"}}},
        "disclosed_confound": "the holdout is right-censored (a 2018 pick debuting 2022 has 4 observed "
                              "seasons by 2025) and every window holds 2020, so its level reads low; "
                              "the artifact names it a diagnostic, not the ship criterion",
        "seconds": round(time.time() - t0, 1),
    }


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------
RUN_ROWS = {"S1": ["fa_projection_marcel"], "S2": ["fa_war_paths_decay", "mlb_projections_vets"],
            "S3": ["draft_slot_curve"]}


def row_findings(runs: dict) -> list[dict]:
    """Per row: the primary cell's verdict against every null. A row whose
    primary cell TIES or LOSES any null goes to the owner question."""
    out = []
    for sid, rows in RUN_ROWS.items():
        run = runs.get(sid)
        if not run or "error" in run:
            for mid in rows:
                out.append({"model_id": mid, "run": sid, "status": "NOT RUN",
                            "detail": (run or {}).get("error", "not run")})
            continue
        prim = run["primary_cell"]
        for mid in rows:
            if sid == "S2":
                cell = run["cells"]["challenger_proj_lgbm"][prim]
            else:
                cell = run["cells"][prim]
            inst = cell["instrument"]["verdict"]
            verdicts = {k: v["verdict"] for k, v in cell["nulls"].items()}
            if inst != "PASS":
                status = "VOID"
            elif any(v in ("TIES", "LOSES") for v in verdicts.values()):
                status = "TIES_OR_LOSES_NULL"
            else:
                status = "BEATS_EVERY_NULL"
            out.append({"model_id": mid, "run": sid, "primary_cell": prim,
                        "verdicts": verdicts, "instrument": inst, "status": status})
    return out


def census_rows(registry: dict) -> list[dict]:
    reg = {m["model_id"]: m for m in registry["models"]}
    out = []
    for (mid, verdict, served, comparator, null_status, planted, action, note) in CENSUS:
        r = reg.get(mid)
        out.append({"model_id": mid, "verdict_at_registration": verdict,
                    "verdict_now": r["verdict"] if r else None,
                    "served": served, "comparator": comparator, "null_status": null_status,
                    "planted_recovery": planted, "action": action, "note": note})
    return out


def census_counts(rows: list[dict]) -> dict:
    c = defaultdict(int)
    for r in rows:
        c[f"{r['verdict_at_registration']}:{r['null_status']}"] += 1
        c[f"action:{r['action'].split(':')[0]}"] += 1
        if r["planted_recovery"]:
            c["planted_recovery_yes"] += 1
    return dict(sorted(c.items()))


def _fmt_cell(name: str, cell: dict) -> list[str]:
    lines = [f"- {name}: n {cell['n']}, model {cell.get('mae_model', cell.get('metric_model'))}; "
             f"instrument {cell['instrument']['verdict']}"]
    for k, v in cell["nulls"].items():
        nv = v.get("mae_null", v.get("metric_null"))
        lines.append(f"  - {k}: null {nv}, delta (null minus model) {v['point']:+.4f}, "
                     f"CI95 {v['lo95']:+.4f} to {v['hi95']:+.4f}: {v['verdict']}")
        if "secondary_mse_delta" in v:
            lines.append(f"    - secondary per-pick MSE: null {v['secondary_mse_null']}, delta "
                         f"{v['secondary_mse_delta']:+.4f}, CI95 {v['secondary_lo95']:+.4f} to "
                         f"{v['secondary_hi95']:+.4f}: {v['secondary_verdict']}")
    return lines


def write_results_md(payload: dict, path: Path) -> None:
    L = ["# Null comparator sweep: results", "",
         f"Registration: `{REGISTRATION}`. Lab: `tools/null_comparator_sweep_lab.py`. "
         f"Artifact: `data/null_comparator_sweep.json`. Run at {payload['generated_at']} "
         f"({'DRY RUN on fixtures' if payload.get('dry_run') else 'the one registered run'}).", "",
         "delta = loss(null) minus loss(model): positive means the model beats the null. "
         "BEATS: CI95 above zero. TIES: CI95 contains zero. LOSES: CI95 below zero. "
         "A cell whose planted-better or planted-worse instrument check fails is VOID.", "",
         "## Census", ""]
    for k, v in payload["census_counts"].items():
        L.append(f"- {k}: {v}")
    L += ["", "## Runs", ""]
    for sid, run in payload["runs"].items():
        L.append(f"### {sid}")
        L.append("")
        if "error" in run:
            L.append(f"ERROR: {run['error']}")
            L.append("")
            continue
        L.append(f"Frame: {run['frame']}. Label: {run.get('label')}.")
        L.append("")
        L.append(f"Reproduction: {json.dumps(run['reproduction'].get('now'))}; stored "
                 f"{json.dumps({k: v for k, v in run['reproduction']['stored'].items() if k != 'artifact'})}.")
        L.append("")
        if sid == "S2":
            for model_name, cells in run["cells"].items():
                L.append(f"{model_name}:")
                for cname, cell in cells.items():
                    L += _fmt_cell(cname, cell)
                L.append("")
        else:
            for cname, cell in run["cells"].items():
                L += _fmt_cell(cname, cell)
            L.append("")
            if run.get("disclosed_confound"):
                L.append(f"Disclosed confound: {run['disclosed_confound']}.")
                L.append("")
    L += ["## Row findings", ""]
    for f_ in payload["row_findings"]:
        L.append(f"- {f_['model_id']} ({f_['run']}): {f_['status']}"
                 + (f"; {json.dumps(f_.get('verdicts'))}" if f_.get("verdicts") else ""))
    L.append("")
    text = "\r\n".join(L) + "\r\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _fixture_runs(seed: int) -> dict:
    """Synthetic rows (with an empty cell) that exercise the reporting path."""
    import numpy as np
    rng = np.random.default_rng(seed)
    keys = [f"p{i % 50}" for i in range(400)]
    act = rng.normal(0.5, 1.0, 400)
    pm = act + rng.normal(0, 0.6, 400)
    cell = _mae_cell(keys, pm, act, {"ZERO": [0.0] * 400, "POP_MEAN": [0.5] * 400}, seed)
    empty = _mae_cell([], [], [], {"ZERO": []}, seed)
    s1 = {"frame": "fixture", "label": None, "reproduction": {"stored": STORED["S1"], "now": None},
          "primary_cell": "pooled", "cells": {"pooled": cell, "hit": empty}}
    s2 = {"frame": "fixture", "label": None, "reproduction": {"stored": STORED["S2"], "now": None},
          "primary_cell": "h1", "cells": {"challenger_proj_lgbm": {"h1": cell}, "champion_decay": {"h1": cell}}}
    return {"S1": s1, "S2": s2, "S3": {"error": "fixture: not built"}}


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--run", action="store_true")
    ap.add_argument("--out-dir", type=Path, default=None, help="dry-run output directory")
    ap.add_argument("--cache-dir", type=Path, default=None)
    a = ap.parse_args()
    registry = json.loads((DATA_DIR / "model_registry.json").read_text(encoding="utf-8"))
    census = census_rows(registry)
    payload = {"generated_at": _utc(), "registration": REGISTRATION, "seed": SEED, "bootstrap_reps": REPS,
               "dry_run": bool(a.dry_run), "census": census, "census_counts": census_counts(census)}
    if a.dry_run:
        out_dir = a.out_dir or Path(tempfile.mkdtemp())
        out_dir.mkdir(parents=True, exist_ok=True)
        payload["runs"] = _fixture_runs(SEED)
        payload["row_findings"] = row_findings(payload["runs"])
        (out_dir / "null_comparator_sweep.dryrun.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")
        write_results_md(payload, out_dir / "RESULTS.dryrun.md")
        print("dry run written to", out_dir)
        return 0
    if OUT_JSON.exists():
        prev = json.loads(OUT_JSON.read_text(encoding="utf-8"))
        if prev.get("runs") and not prev.get("dry_run"):
            print("REFUSED: data/null_comparator_sweep.json already records the one registered run")
            return 2
    iso = isolate_caches(a.cache_dir or Path(tempfile.mkdtemp(prefix="ncs_cache_")))
    payload["cache_isolation"] = iso
    print("cache isolation:", json.dumps(iso), flush=True)
    runs = {}
    for sid, fn in (("S3", run_s3), ("S1", run_s1), ("S2", run_s2)):
        print(f"--- {sid} start {_utc()}", flush=True)
        try:
            runs[sid] = fn(SEED)
        except Exception as e:  # noqa: BLE001 - recorded, never rerun
            import traceback
            traceback.print_exc()
            runs[sid] = {"error": f"{type(e).__name__}: {e}"}
        print(f"--- {sid} done {_utc()}: {json.dumps(runs[sid].get('reproduction', runs[sid]))[:600]}", flush=True)
    payload["runs"] = runs
    payload["row_findings"] = row_findings(runs)
    OUT_JSON.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    write_results_md(payload, RESULTS_MD)
    for f_ in payload["row_findings"]:
        print("ROW", json.dumps(f_))
    print("wrote", OUT_JSON, "and", RESULTS_MD)
    return 0


if __name__ == "__main__":
    sys.exit(main())
