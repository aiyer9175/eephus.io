# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""S-XLINE-2 / S-XLINE-3 gate lab (pre-registered: docs/efv-2026-07-23/
GATES.md, sections "S-XLINE-2 gate registration" and "S-XLINE-3 gate
registration"). S-XLINE-2's V0 ran 2026-07-23 and STOPPED (rho 0.6365,
ledger data/xfv_statcast_line2_eval.json); S-XLINE-3 supersedes ONLY the V0
quantity (complete the contact-only feed estimate to full-xwOBA scale before
comparing) and re-freezes every other clause by reference. This lab now
executes the S-XLINE-3 registration exactly:

  V0'    stop gate: xwoba_est_full (frozen completion below) vs Savant full
         xwOBA on AAA 2026 both-source players (>= 25 tracked BBE feed-side,
         >= 100 PA Savant-side): Spearman >= 0.70 or STOP + ledger.
  M-A    PRIMARY: A-ball (sport 14) blend50 of the capped gap
         (xwoba_est_full - line wOBA proxy, cap +-0.050) into the actual
         line vs next-season wOBA z. lo95 > 0 ships the measurement clause.
  M-CPX  SECONDARY: same design at CPX (sport 16).
  AUX-1  hit p90 EV, level-relative, A-ball, vs next-season wOBA z.
  AUX-2  hit whiff/swing-miss (zone_metrics codes) at A vs next K% + wOBA z.
  AUX-3  pit fastball velo (feeds) at A vs next-season K% against.
  Selection-bias falsification for every arm run.

Seed 20260723, 2000 bootstrap reps, percentile CIs. Nothing ships from this
run; a M-A pass only licenses the default-OFF implementation + the S-XLINE
in-matrix clauses (registered separately).

FROZEN S-XLINE-3 completion formula (frozen in this header BEFORE V0' ran;
the ONLY change from S-XLINE-2). Inputs: the player's milb_history hitting
line at the level in question (lean fields: pa, ab, avg, obp, slg, so, bb,
hr - HBP/SF/IBB are NOT stored) plus the feed contact-only estimate
xw_con = contact_quality.xwoba_est (xwOBAcon scale, incl. the module's
profile adjustment). Linear weights are the codebase's canonical FanGraphs
family (hem_plus.py W_UBB/W_HBP/W_1B/W_2B/W_HR, mirroring fa_config
assembly.woba_weights) - the SAME constants woba_proxy() below already uses.
Event algebra (mirrors how Savant builds xwOBA: expected value on contact,
actual value on non-contact events):

    H    = avg * ab
    HBP' = max(0, obp*pa - H - bb)      reconstructed HBP; absorbs the OBP
                                        denominator error (SF/SH/CI), so it
                                        can overstate HBP by roughly the SF
                                        count; IDENTICAL treatment to
                                        woba_proxy(), so line-vs-line gaps
                                        cancel the error exactly
    BIP' = max(0, pa - bb - HBP' - so)  PA that ended on contact; includes
                                        SF (correct - Savant values SF
                                        batted balls by EV/LA) and SH (tiny
                                        overcount, bunts)
    xwoba_est_full = (0.69*bb + 0.72*HBP' + xw_con*BIP') / pa

Frozen edge handling:
  - IBB unavailable in the lean rows -> total BB at weight 0.69 and pa as
    the denominator (standard approximation; IBB are rare in the minors)
  - SF unavailable -> remains inside BIP' and pa (see above)
  - HBP unavailable -> reconstructed as above, floored at 0
  - rows with pa < 1, ab < 1, or missing avg/obp -> excluded (no estimate)
  - denominator = pa, the SAME denominator as woba_proxy(), so the M-A gap
    xwoba_est_full - woba_proxy reduces to (xw_con - wobacon_line)*BIP'/pa
    with the BB/HBP/K channels cancelling by construction; any constant
    xwOBAcon-scale offset in xw_con enters only through the slowly-varying
    contact share and is absorbed by within-pool z + rank statistics

All fetching goes through the production seams:
  statcast_metrics._game_logs      (gamelog path, per-player, cached)
  feed_cache.get_game_feed         (gamePk-shared cache, atomic, throttled)
  arkmetric_forward_eval.savant_rows (cached Savant minors CSVs, fetch=False)
  milb_history                     (outcome stat lines, cached)
Aggregation reuses statcast_metrics._finalize_contact (the module's own
contact-quality aggregate incl. its xwoba_est) and zone_metrics'
SWING_CODES / WHIFF_CODES.

S-XLINE-4 (registered in the same GATES.md file, section "S-XLINE-4 gate
registration"): incremental arms on the S-XLINE-3 AUX winners. Raw forward
correlation is not incremental value - the stat line already carries
ISO/K/BB into eFV - so each AUX signal is tested against the residual of a
cross-fitted ridge baseline (5-fold, folds by player) built on the
CURRENT-season stat-line inputs eFV consumes (hitters: wOBA-proxy z, K%,
BB%, ISO z, age-for-level; pitchers: K%a, BB%a, ERA z, age-for-level),
predicting the arm's outcome (hitters: next-season wOBA z; pitchers:
next-season K%a z). INC-1 p90 EV (lo95 > 0), INC-2 whiff share (negative vs
the wOBA residual; separately positive vs the next-K% residual), INC-3 FB
velo (lo95 > 0), plus the descriptive age-interaction report. All data is
the local S-XLINE-3 backfill (accumulators + cached feeds); zero fetches.

Commands (run from prospect-tracker/):
  python -m tools.efv_statcast_line2_lab v0        # S-XLINE-2 V0 (archived STOP)
  python -m tools.efv_statcast_line2_lab v0full    # S-XLINE-3 V0' STOP gate
  python -m tools.efv_statcast_line2_lab plan      # target sizing, no fetch
  python -m tools.efv_statcast_line2_lab backfill  # hours; resumable; V0'-gated
  python -m tools.efv_statcast_line2_lab arms      # frozen arms + artifact
  python -m tools.efv_statcast_line2_lab inc       # S-XLINE-4 incremental arms
"""
from __future__ import annotations

import json
import os
import pickle
import sys
import time
from datetime import date, datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
os.chdir(_ROOT)

import numpy as np

# ---------------------------------------------------------------- constants
SEED = 20260723
REPS = 2000
V0_RHO_BAR = 0.70
MIN_BBE = 25          # tracked BBE floor (registration)
MIN_PA = 150          # both legs (registration)
MIN_BF = 150          # pitcher analog of the 150 PA floor
MIN_SAVANT_PA = 100   # V0 Savant qualification (registration)
W_BLEND = 0.5         # same W as S-XLINE (registration)
GAP_LINE_CAP = 0.100  # S-XLINE-2 mirror cap (archived; V0 stopped that run)
GAP_FULL_CAP = 0.050  # S-XLINE-3 registered cap on (xwoba_est_full - wOBA)
MIN_POOL_N = 20       # a-priori hygiene floor for a z pool
MIN_PITCHES_SEEN = 100  # zone_metrics.PERCENTILE_MIN_PITCHES (AUX-2 qual)
MIN_FB = 50           # a-priori tracked-fastball floor (AUX-3 qual)
FB_CODES = {"FF", "FA", "FT", "SI"}
SEASONS = (2023, 2024, 2025)
LEVELS = ("A", "CPX")
PAST_TTL = 3650 * 86400   # past-season gamelog hydrates are immutable
LOG_WORKERS = 10
FEED_WORKERS = 12         # module discipline caps feed workers at 20
CHECKPOINT_EVERY = 200

SCRATCH = Path(os.environ.get(
    "SXLINE2_SCRATCH",
    r"C:\Users\noah\AppData\Local\Temp\claude\c--Users-noah-baseball-projects-BaseballR"
    r"\d5365103-d19e-492b-bc63-c7e79cfcebad\scratchpad"))
SCRATCH.mkdir(parents=True, exist_ok=True)
V0_PATH = SCRATCH / "sxline2_v0.json"
V0_3_PATH = SCRATCH / "sxline3_v0.json"
PROGRESS_PATH = SCRATCH / "sxline2_progress.json"
EVAL_PATH = _ROOT / "data" / "xfv_statcast_line2_eval.json"
EVAL3_PATH = _ROOT / "data" / "xfv_statcast_line3_eval.json"
EVAL4_PATH = _ROOT / "data" / "xfv_statcast_line4_eval.json"

# S-XLINE-4 baseline (registered): closed-form ridge, 5 folds by player.
# Lambda is an a-priori default on train-fold-standardized features (n in the
# hundreds, 4-5 features); it is NOT tuned against any arm result.
RIDGE_LAMBDA = 1.0
N_FOLDS = 5
HIT_FEATS = ("woba_proxy_z", "k_pct", "bb_pct", "iso_z", "age_for_level")
PIT_FEATS = ("k_pct_a", "bb_pct_a", "era_z", "age_for_level")

# wOBA proxy linear weights (FanGraphs-scale constants, fixed a priori;
# triples are folded into the doubles term because milb_history lines do not
# split 2B/3B - see woba_proxy() for the exact reconstruction).
WOBA_W_BB, WOBA_W_HBP, WOBA_W_1B, WOBA_W_2B, WOBA_W_HR = 0.69, 0.72, 0.89, 1.27, 2.10

REGISTRATION_ECHO = {
    "source": "docs/efv-2026-07-23/GATES.md :: 'S-XLINE-2 gate registration - 2026-07-23'",
    "seed": SEED, "bootstrap_reps": REPS,
    "clauses": {
        "V0": "feeds xwoba_est vs Savant xwOBA on AAA same-season overlap "
              f"(>= {MIN_BBE} BBE / >= {MIN_SAVANT_PA} PA): Spearman >= {V0_RHO_BAR} "
              "or STOP; report r, rho, bias, slope",
        "M-A": "PRIMARY: A-ball season pairs (Y in 2023-2025 -> Y+1, z within "
               f"destination pool, >= {MIN_PA} PA both legs, >= {MIN_BBE} tracked BBE "
               "in Y): blend50 of the xwoba_est-implied gap into the actual line "
               "must predict next-season wOBA better than the actual line; lo95 > 0",
        "M-CPX": "SECONDARY: same design at CPX; honest NULL closes it",
        "AUX-1": "hit p90 EV level-relative at A vs next-season wOBA z; lo95 > 0 or NULL",
        "AUX-2": "hit whiff/swing-miss (zone_metrics) at A vs next-season K% and wOBA z",
        "AUX-3": "pit fastball velo (feeds) at A vs next-season K% against",
        "selection_bias": "same-band covered vs uncovered next-season outcome gap + CI, "
                          "mandatory per arm; big gap => confounded, do not ship",
        "ship_rule": "V0 + M-A pass -> feeds-based gap source in efv_statcast_line, "
                     "W=0.5, caps .050/.050/.100, A/CPX 2023+, default-OFF flags, then "
                     "the S-XLINE in-matrix clauses before any flip; AUX passes inform "
                     "future registrations only",
    },
}

FROZEN_COMPLETION_FORMULA = {
    "quantity": "xwoba_est_full = (0.69*BB + 0.72*HBP' + xw_con*BIP') / PA",
    "weights_source": "hem_plus.py W_UBB/W_HBP (FanGraphs family, mirrors "
                      "fa_config assembly.woba_weights); identical constants "
                      "to this lab's woba_proxy()",
    "xw_con": "feed contact_quality.xwoba_est (contact-only, xwOBAcon scale, "
              "incl. the module's profile adjustment)",
    "event_algebra": {
        "H": "avg * ab",
        "HBP'": "max(0, obp*pa - H - bb) - reconstructed, absorbs the OBP "
                "denominator error (SF/SH/CI); identical to woba_proxy()",
        "BIP'": "max(0, pa - bb - HBP' - so) - contact-ending PA incl. SF "
                "(Savant values SF batted balls) and SH (tiny overcount)",
        "denominator": "pa (same as woba_proxy, so the M-A gap cancels the "
                       "BB/HBP/K channels by construction)",
    },
    "edge_handling": {
        "ibb": "not in milb_history lean rows -> total BB at 0.69",
        "sf": "not stored -> stays inside BIP' and pa",
        "hbp": "not stored -> reconstructed, floored at 0",
        "exclusions": "pa < 1, ab < 1, or missing avg/obp -> no estimate",
    },
    "frozen": "in the lab header BEFORE V0' ran (S-XLINE-3 registration)",
}

REGISTRATION_ECHO_3 = {
    "source": "docs/efv-2026-07-23/GATES.md :: 'S-XLINE-3 gate registration - "
              "2026-07-23 (pre-registered; supersedes S-XLINE-2's V0 quantity ONLY)'",
    "seed": SEED, "bootstrap_reps": REPS,
    "clauses": {
        "V0'": "xwoba_est_full (frozen completion) vs Savant FULL xwOBA on AAA "
               f"2026 both-source players (>= {MIN_BBE} tracked BBE feed-side / "
               f">= {MIN_SAVANT_PA} PA Savant-side): Spearman >= {V0_RHO_BAR} or "
               "STOP; report r, rho, bias, slope",
        "M-A": "PRIMARY: A-ball season pairs (Y in 2023-2025 -> Y+1, z within "
               f"destination pool, >= {MIN_PA} PA both legs, >= {MIN_BBE} tracked "
               f"BBE in Y): blend50 of the capped gap (xwoba_est_full - line wOBA "
               f"proxy, cap +-{GAP_FULL_CAP}) into the actual line must predict "
               "next-season wOBA better than the actual line; lo95 > 0",
        "M-CPX": "SECONDARY: same design at CPX; honest NULL closes it",
        "AUX-1": "hit p90 EV level-relative at A vs next-season wOBA z; lo95 > 0 or NULL",
        "AUX-2": "hit whiff/swing-miss (zone_metrics) at A vs next-season K% and wOBA z",
        "AUX-3": "pit fastball velo (feeds) at A vs next-season K% against",
        "selection_bias": "same-band covered vs uncovered next-season outcome gap + CI, "
                          "mandatory per arm; big gap => confounded, do not ship",
        "ship_rule": "V0' + M-A pass -> feeds-based gap source in efv_statcast_line, "
                     "W=0.5, caps .050/.050/.100, A/CPX 2023+, default-OFF flags, then "
                     "the S-XLINE in-matrix clauses (invariance, no-harm >= -0.003, "
                     "bounded pull, post-flip max served move <= 3 FV) before any "
                     "flip; AUX passes inform future registrations only",
    },
    "frozen_completion_formula": FROZEN_COMPLETION_FORMULA,
}


def _f(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=1) + "\n", encoding="utf-8")


# ------------------------------------------------------------- rank helpers
def _rankdata_avg(a: np.ndarray) -> np.ndarray:
    """Average-tie ranks (1-based), deterministic."""
    a = np.asarray(a, dtype=float)
    _, inv, cnt = np.unique(a, return_inverse=True, return_counts=True)
    csum = np.cumsum(cnt)
    start = csum - cnt
    avg = start + (cnt + 1) / 2.0
    return avg[inv]


def _pearson_np(x: np.ndarray, y: np.ndarray) -> float | None:
    if len(x) < 8:
        return None
    sx, sy = np.std(x), np.std(y)
    if sx == 0 or sy == 0:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def _spearman_np(x: np.ndarray, y: np.ndarray) -> float | None:
    if len(x) < 8:
        return None
    return _pearson_np(_rankdata_avg(x), _rankdata_avg(y))


def _boot_ci(stat_fn, n: int, reps: int = REPS, seed: int = SEED):
    """Percentile bootstrap over row indices. stat_fn(idx) -> float | None."""
    rng = np.random.default_rng(seed)
    stats = []
    for _ in range(reps):
        idx = rng.integers(0, n, size=n)
        s = stat_fn(idx)
        if s is not None:
            stats.append(s)
    if len(stats) < reps * 0.9:
        return None, None, None
    arr = np.asarray(stats)
    return (float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5)),
            float(np.mean(arr > 0)))


# ----------------------------------------------------------- wOBA proxy
def woba_proxy(row: dict) -> float | None:
    """wOBA proxy from a milb_history hitting line.

    Fields consumed: pa, ab, avg, obp, slg, bb, hr (so is NOT used here; it
    enters only through the contact share in the gap application).
    Reconstruction: H = avg*ab; TB = slg*ab; 2B' = max(0, TB - H - 3*HR)
    (triples folded into the doubles term); 1B = max(0, H - 2B' - HR);
    HBP' = max(0, obp*pa - H - BB) (absorbs the OBP-denominator error).
    proxy = (0.69*BB + 0.72*HBP' + 0.89*1B + 1.27*2B' + 2.10*HR) / pa.
    Constants fixed a priori; every player in a pool gets the identical
    treatment, and pool z-scoring absorbs any systematic level bias."""
    pa, ab = _f(row.get("pa")), _f(row.get("ab"))
    avg, obp, slg = _f(row.get("avg")), _f(row.get("obp")), _f(row.get("slg"))
    bb, hr = _f(row.get("bb")) or 0.0, _f(row.get("hr")) or 0.0
    if not pa or not ab or pa < 1 or ab < 1 or None in (avg, obp, slg):
        return None
    h = avg * ab
    tb = slg * ab
    d2 = max(0.0, tb - h - 3.0 * hr)
    b1 = max(0.0, h - d2 - hr)
    hbp = max(0.0, obp * pa - h - bb)
    num = (WOBA_W_BB * bb + WOBA_W_HBP * hbp + WOBA_W_1B * b1
           + WOBA_W_2B * d2 + WOBA_W_HR * hr)
    return num / pa


def xwoba_est_full(row: dict, xw_con: float | None) -> float | None:
    """FROZEN S-XLINE-3 completion of the contact-only feed estimate to
    full-xwOBA scale (exact algebra + edge handling in the module header,
    frozen BEFORE V0' ran). `row` is a milb_history hitting line; `xw_con`
    is the feed contact_quality.xwoba_est (xwOBAcon scale)."""
    pa, ab = _f(row.get("pa")), _f(row.get("ab"))
    avg, obp = _f(row.get("avg")), _f(row.get("obp"))
    bb = _f(row.get("bb")) or 0.0
    so = _f(row.get("so")) or 0.0
    if not pa or not ab or pa < 1 or ab < 1 or None in (avg, obp) or xw_con is None:
        return None
    h = avg * ab
    hbp = max(0.0, obp * pa - h - bb)
    bip = max(0.0, pa - bb - hbp - so)
    return (WOBA_W_BB * bb + WOBA_W_HBP * hbp + xw_con * bip) / pa


def hit_k_pct(row: dict) -> float | None:
    pa, so = _f(row.get("pa")), _f(row.get("so"))
    if not pa or pa < 1 or so is None:
        return None
    return so / pa


def pit_k_pct(row: dict) -> float | None:
    bf, so = _f(row.get("bf")), _f(row.get("so"))
    if not bf or bf < 1 or so is None:
        return None
    return so / bf


# ------------------------------------------------- destination outcome pools
def _dest_rows_hit(season: int) -> dict[int, dict]:
    """{mlbam: destination hitting row (max-PA row across the ladder)} with
    pa >= MIN_PA and a computable proxy."""
    import milb_history as mh
    out = {}
    for mid, rows in mh.player_index(season, "hitting").items():
        best = max(rows, key=lambda r: _f(r.get("pa")) or 0.0)
        pa = _f(best.get("pa")) or 0.0
        if pa < MIN_PA:
            continue
        w = woba_proxy(best)
        if w is None:
            continue
        out[mid] = {"level": best.get("level"), "pa": pa, "woba": w,
                    "k_pct": hit_k_pct(best)}
    return out


def _dest_rows_pit(season: int) -> dict[int, dict]:
    import milb_history as mh
    out = {}
    for mid, rows in mh.player_index(season, "pitching").items():
        best = max(rows, key=lambda r: _f(r.get("bf")) or 0.0)
        bf = _f(best.get("bf")) or 0.0
        if bf < MIN_BF:
            continue
        k = pit_k_pct(best)
        if k is None:
            continue
        out[mid] = {"level": best.get("level"), "bf": bf, "k_pct": k}
    return out


def _pool_z(values_by_group: dict, key: str):
    """Per-group mean/sd for z-scoring; groups under MIN_POOL_N are dropped."""
    stats = {}
    for g, rows in values_by_group.items():
        vals = np.asarray([r[key] for r in rows if r.get(key) is not None], float)
        if len(vals) >= MIN_POOL_N and np.std(vals) > 0:
            stats[g] = (float(np.mean(vals)), float(np.std(vals)))
    return stats


def _dest_z_maps(season: int, group: str):
    """({mlbam: outcome-z dict}, pool sizes) for one destination season.
    z within (destination level, season) pool of players whose OWN
    max-exposure row sits at that level (>= exposure floor)."""
    if group == "hitting":
        dest = _dest_rows_hit(season)
        keys = ("woba", "k_pct")
    else:
        dest = _dest_rows_pit(season)
        keys = ("k_pct",)
    by_level: dict[str, list[dict]] = {}
    for mid, r in dest.items():
        by_level.setdefault(r["level"], []).append(r)
    zmaps: dict[int, dict] = {}
    stats = {k: _pool_z(by_level, k) for k in keys}
    for mid, r in dest.items():
        lv = r["level"]
        zr = {"level": lv}
        ok = False
        for k in keys:
            st = stats[k].get(lv)
            if st and r.get(k) is not None:
                zr[f"{k}_z"] = (r[k] - st[0]) / st[1]
                ok = True
        if ok:
            zmaps[mid] = zr
    pool_sizes = {lv: len(rows) for lv, rows in by_level.items()}
    return zmaps, pool_sizes


# ------------------------------------------------------------ level targets
def _level_targets_hit(season: int, level: str) -> dict[int, dict]:
    """{mlbam: A/CPX-level hitting row} with pa >= MIN_PA."""
    import milb_history as mh
    out = {}
    for mid, rows in mh.player_index(season, "hitting").items():
        row = mh.level_row(rows, level, "hitting")
        if row is None:
            continue
        if (_f(row.get("pa")) or 0.0) >= MIN_PA and woba_proxy(row) is not None:
            out[mid] = row
    return out


def _level_pitchers(season: int, level: str) -> dict[int, dict]:
    import milb_history as mh
    out = {}
    for mid, rows in mh.player_index(season, "pitching").items():
        row = mh.level_row(rows, level, "pitching")
        if row is None:
            continue
        if (_f(row.get("bf")) or 0.0) >= MIN_BF and pit_k_pct(row) is not None:
            out[mid] = row
    return out


# ------------------------------------------------------------------ V0 gate
def _v0_diagnostics(feeds: dict, sav_full: dict, matched: list[int]) -> dict:
    """DESCRIPTIVE ONLY - ledger context, the gate stat is untouched.
    Answers: is the sub-0.70 agreement sampling noise (would rise with BBE),
    a profile-adjustment artifact, or the structural K/BB channel that a
    contact-only estimate cannot carry against full xwOBA?"""
    x = np.asarray([feeds[m]["xwoba_est"] for m in matched], float)
    raw = np.asarray([feeds[m]["xwoba_raw"] for m in matched], float)
    bbe = np.asarray([feeds[m]["bbe"] for m in matched], float)
    y = np.asarray([sav_full[m]["xwoba"] for m in matched], float)
    diag: dict = {"note": "descriptive ledger diagnostics; the registered gate "
                          "statistic is the >= 25 BBE Spearman above"}
    for floor in (40, 75, 100):
        sel = bbe >= floor
        r = _spearman_np(x[sel], y[sel])
        diag[f"rho_bbe_ge_{floor}"] = {"n": int(sel.sum()),
                                       "rho": round(r, 4) if r is not None else None}
    r = _spearman_np(raw, y)
    diag["rho_raw_pre_adjustment"] = round(r, 4) if r is not None else None
    xsl_pairs = [(feeds[m]["xwoba_est"], sav_full[m]["xslg"]) for m in matched
                 if sav_full[m].get("xslg") is not None]
    if xsl_pairs:
        a, b_ = map(np.asarray, zip(*xsl_pairs))
        r = _spearman_np(a, b_)
        diag["rho_vs_savant_xslg"] = round(r, 4) if r is not None else None
    res = x - y
    for chan, sign in (("k_percent", 1.0), ("bb_percent", -1.0)):
        vals = np.asarray([sav_full[m].get(chan) if sav_full[m].get(chan) is not None
                           else np.nan for m in matched], float)
        ok = ~np.isnan(vals)
        r = _spearman_np(res[ok], sign * vals[ok])
        diag[f"rho_residual_vs_savant_{chan}"] = round(r, 4) if r is not None else None
    diag["reading"] = (
        "agreement does NOT rise with more BBE (structural, not noise); the "
        "feed estimate clears 0.70 against the contact-flavored Savant xSLG; "
        "the residual vs full xwOBA loads on Savant K% and BB% - i.e. the "
        "failure is the contact-only-vs-full-xwOBA quantity mismatch, not a "
        "broken EV/LA surface. A future registration would need a like-for-"
        "like V0 quantity (K/BB-completed reconstruction or xSLG-family gap) "
        "re-registered BEFORE any re-run; nothing proceeds in this one.")
    return diag


def _v0_feed_side() -> dict[int, dict]:
    """Stored 2026 AAA feed level-splits with >= MIN_BBE tracked BBE (the
    exact V0-2 feed-side population)."""
    import storage
    feeds: dict[int, dict] = {}
    with storage.connect() as con:
        rows = con.execute(
            "SELECT player_key, payload_json FROM statcast_metrics WHERE season = 2026"
        ).fetchall()
    for r in rows:
        p = json.loads(r["payload_json"])
        if p.get("is_pitcher") or not p.get("mlbam_id"):
            continue
        for ls in p.get("level_splits") or []:
            if ls.get("level") != "AAA":
                continue
            cq = ls.get("contact_quality") or {}
            bbe = cq.get("batted_balls") or 0
            xw = _f(cq.get("xwoba_est"))
            if bbe >= MIN_BBE and xw is not None:
                adj = _f(cq.get("xwobacon_adjustment")) or 0.0
                feeds[int(p["mlbam_id"])] = {"xwoba_est": xw, "bbe": int(bbe),
                                             "xwoba_raw": xw - adj}
    return feeds


def _v0_savant_side() -> dict[int, dict]:
    """Cached Savant minors batter rows, >= MIN_SAVANT_PA (the exact V0-2
    Savant-side population)."""
    import arkmetric_forward_eval as af
    sav: dict[int, dict] = {}
    for r in af.savant_rows(2026, "batter", fetch=False):
        mid, pa, xw = _f(r.get("player_id")), _f(r.get("pa")) or 0.0, _f(r.get("xwoba"))
        if mid is not None and pa >= MIN_SAVANT_PA and xw is not None:
            sav[int(mid)] = {"xwoba": xw, "xslg": _f(r.get("xslg")),
                             "k_percent": _f(r.get("k_percent")),
                             "bb_percent": _f(r.get("bb_percent"))}
    return sav


def cmd_v0() -> dict:
    """Clause V0 STOP gate: stored AAA 2026 feed aggregates vs Savant xwOBA.

    2025 leg: skipped. Stored statcast_metrics rows exist for 2026 only and
    the cached feed set does not cover AAA 2025; adding it would be a
    ~2,200-feed AAA backfill, which the registration only allows 'without a
    huge fetch'. Documented, not fetched."""
    feeds = _v0_feed_side()
    sav = _v0_savant_side()
    matched = sorted(set(feeds) & set(sav))
    x = np.asarray([feeds[m]["xwoba_est"] for m in matched], float)   # feeds
    y = np.asarray([sav[m]["xwoba"] for m in matched], float)         # Savant
    n = len(matched)
    rho = _spearman_np(x, y)
    r_p = _pearson_np(x, y)
    bias = float(np.mean(x - y)) if n else None
    slope = intercept = None
    if n >= 8 and np.var(x) > 0:
        slope = float(np.cov(x, y, bias=True)[0, 1] / np.var(x))
        intercept = float(np.mean(y) - slope * np.mean(x))

    verdict = "PASS" if (rho is not None and rho >= V0_RHO_BAR) else "STOP"
    out = {
        "clause": "V0", "season": 2026, "level": "AAA",
        "n_feed_side": len(feeds), "n_savant_side": len(sav), "n_matched": n,
        "spearman": round(rho, 4) if rho is not None else None,
        "pearson": round(r_p, 4) if r_p is not None else None,
        "mean_bias_feed_minus_savant": round(bias, 4) if bias is not None else None,
        "ols_slope_savant_on_feed": round(slope, 4) if slope is not None else None,
        "ols_intercept": round(intercept, 4) if intercept is not None else None,
        "bar": V0_RHO_BAR, "verdict": verdict,
        "note": ("feeds xwoba_est is the module's contact-only estimate (xwOBAcon "
                 "scale, incl. its profile adjustment); Savant xwoba is full xwOBA "
                 "(includes K/BB), so a level bias is expected and reported; the "
                 "registered gate is the rank agreement (Spearman)"),
        "v0_2025_leg": "skipped - stored rows are 2026-only; AAA 2025 would be a "
                       "~2,200-feed backfill (registration: only 'without a huge fetch')",
        "diagnostics_descriptive": _v0_diagnostics(feeds, sav, matched) if n >= 8 else None,
        "ts": _now(),
    }
    _write_json(V0_PATH, out)
    print(f"[V0] n={n} rho={out['spearman']} r={out['pearson']} "
          f"bias={out['mean_bias_feed_minus_savant']} slope={out['ols_slope_savant_on_feed']} "
          f"-> {verdict}", flush=True)
    if verdict == "STOP":
        artifact = {
            "generated_at": date.today().isoformat(),
            "experiment": "S-XLINE-2 (docs/efv-2026-07-23/GATES.md)",
            "tool": "tools/efv_statcast_line2_lab.py",
            "registration_echo": REGISTRATION_ECHO,
            "v0": out,
            "not_run_per_v0_stop": {
                "backfill": "A (sport 14) + CPX (sport 16) hitter feeds 2023-2025 "
                            "NOT fetched (registered scope, gated behind V0)",
                "arms": ["M-A (primary)", "M-CPX (secondary)", "AUX-1 p90 EV",
                         "AUX-2 whiff", "AUX-3 pit FB velo",
                         "selection-bias falsification"],
            },
            "keep_alive": (
                "revival requires a NEW pre-registered V0 on a like-for-like "
                "quantity: either (a) complete the feeds estimate to full-xwOBA "
                "scale with the stat line's K/BB before comparing, or (b) gate "
                "on an xSLG-family agreement (measured 0.714 here, descriptive). "
                "The EV/LA surface itself looks usable; the registered proxy "
                "quantity was the wrong yardstick. No arm may be run under THIS "
                "registration."),
            "verdict": "V0 STOP - in-house feeds xwoba_est proxy below the 0.70 "
                       "rank-agreement bar vs Savant xwOBA; no backfill run, arms "
                       "not executed. This artifact is the V0 loss ledger.",
        }
        _write_json(EVAL_PATH, artifact)
        print(f"[V0] STOP ledger written to {EVAL_PATH}", flush=True)
    return out


def cmd_v0_full() -> dict:
    """S-XLINE-3 clause V0' STOP gate: the FROZEN completion xwoba_est_full
    (header formula) vs Savant FULL xwOBA on the same AAA 2026 both-source
    population as V0-2, additionally joined to the player's milb_history AAA
    2026 stat line for the actual BB/HBP'/SO/PA accounting. Spearman >= 0.70
    or STOP + ledger. The checkpoint is written IMMEDIATELY after the gate
    statistic, then re-written with descriptive diagnostics."""
    import milb_history as mh

    feeds = _v0_feed_side()
    sav = _v0_savant_side()
    matched2 = sorted(set(feeds) & set(sav))       # the V0-2 population

    lines: dict[int, dict] = {}
    for mid in matched2:
        rows = mh.player_index(2026, "hitting").get(mid)
        if not rows:
            continue
        row = mh.level_row(rows, "AAA", "hitting")
        if row is not None:
            lines[mid] = row

    full: dict[int, float] = {}
    for mid in matched2:
        row = lines.get(mid)
        if row is None:
            continue
        est = xwoba_est_full(row, feeds[mid]["xwoba_est"])
        if est is not None:
            full[mid] = est
    matched = sorted(full)

    x = np.asarray([full[m] for m in matched], float)          # completed est
    y = np.asarray([sav[m]["xwoba"] for m in matched], float)  # Savant full
    n = len(matched)
    rho = _spearman_np(x, y)
    r_p = _pearson_np(x, y)
    bias = float(np.mean(x - y)) if n else None
    slope = intercept = None
    if n >= 8 and np.var(x) > 0:
        slope = float(np.cov(x, y, bias=True)[0, 1] / np.var(x))
        intercept = float(np.mean(y) - slope * np.mean(x))

    verdict = "PASS" if (rho is not None and rho >= V0_RHO_BAR) else "STOP"
    out = {
        "clause": "V0' (S-XLINE-3)", "season": 2026, "level": "AAA",
        "n_feed_side": len(feeds), "n_savant_side": len(sav),
        "n_matched_feed_savant": len(matched2),
        "n_lost_at_stat_line_join": len(matched2) - n,
        "n_matched": n,
        "spearman": round(rho, 4) if rho is not None else None,
        "pearson": round(r_p, 4) if r_p is not None else None,
        "mean_bias_full_est_minus_savant": round(bias, 4) if bias is not None else None,
        "ols_slope_savant_on_full_est": round(slope, 4) if slope is not None else None,
        "ols_intercept": round(intercept, 4) if intercept is not None else None,
        "bar": V0_RHO_BAR, "verdict": verdict,
        "frozen_completion_formula": FROZEN_COMPLETION_FORMULA,
        "note": ("xwoba_est_full completes the contact-only feed estimate to "
                 "full-xwOBA scale with the AAA stat line's actual BB/HBP'/SO "
                 "accounting (header formula, frozen before this ran); the "
                 "registered gate is the rank agreement (Spearman) vs Savant "
                 "full xwOBA on the V0-2 population"),
        "ts": _now(),
    }
    _write_json(V0_3_PATH, out)   # checkpoint IMMEDIATELY, before diagnostics
    print(f"[V0'] n={n} rho={out['spearman']} r={out['pearson']} "
          f"bias={out['mean_bias_full_est_minus_savant']} "
          f"slope={out['ols_slope_savant_on_full_est']} -> {verdict}", flush=True)

    if n >= 8:
        diag: dict = {"note": "descriptive ledger diagnostics; the registered "
                              "gate statistic is the >= 25 BBE Spearman above"}
        bbe = np.asarray([feeds[m]["bbe"] for m in matched], float)
        for floor in (40, 75, 100):
            sel = bbe >= floor
            r_ = _spearman_np(x[sel], y[sel])
            diag[f"rho_bbe_ge_{floor}"] = {"n": int(sel.sum()),
                                           "rho": round(r_, 4) if r_ is not None else None}
        con = np.asarray([feeds[m]["xwoba_est"] for m in matched], float)
        r_ = _spearman_np(con, y)
        diag["rho_contact_only_same_subset"] = round(r_, 4) if r_ is not None else None
        res = x - y
        for chan in ("k_percent", "bb_percent"):
            vals = np.asarray([sav[m].get(chan) if sav[m].get(chan) is not None
                               else np.nan for m in matched], float)
            ok = ~np.isnan(vals)
            r_ = _spearman_np(res[ok], vals[ok])
            diag[f"rho_residual_vs_savant_{chan}"] = round(r_, 4) if r_ is not None else None
        # sanity on the stat-line join: the line's own K%/BB% vs Savant's
        line_k = np.asarray([(hit_k_pct(lines[m]) if hit_k_pct(lines[m]) is not None
                              else np.nan) for m in matched], float)
        sav_k = np.asarray([sav[m].get("k_percent") if sav[m].get("k_percent") is not None
                            else np.nan for m in matched], float)
        ok = ~np.isnan(line_k) & ~np.isnan(sav_k)
        r_ = _spearman_np(line_k[ok], sav_k[ok])
        diag["rho_line_k_vs_savant_k"] = round(r_, 4) if r_ is not None else None
        out["diagnostics_descriptive"] = diag
        _write_json(V0_3_PATH, out)

    if verdict == "STOP":
        artifact = {
            "generated_at": date.today().isoformat(),
            "experiment": "S-XLINE-3 (docs/efv-2026-07-23/GATES.md)",
            "tool": "tools/efv_statcast_line2_lab.py",
            "registration_echo": REGISTRATION_ECHO_3,
            "v0_full": out,
            "not_run_per_v0_stop": {
                "backfill": "A (sport 14) + CPX (sport 16) hitter feeds 2023-2025 "
                            "NOT fetched (registered scope, gated behind V0')",
                "arms": ["M-A (primary)", "M-CPX (secondary)", "AUX-1 p90 EV",
                         "AUX-2 whiff", "AUX-3 pit FB velo",
                         "selection-bias falsification"],
            },
            "verdict": "V0' STOP - the K/BB-completed feed estimate remains "
                       "below the 0.70 rank-agreement bar vs Savant full xwOBA; "
                       "no backfill run, arms not executed. This artifact is "
                       "the V0' loss ledger.",
        }
        _write_json(EVAL3_PATH, artifact)
        print(f"[V0'] STOP ledger written to {EVAL3_PATH}", flush=True)
    return out


# --------------------------------------------------------------- plan sizing
def cmd_plan() -> None:
    for season in SEASONS:
        for level in LEVELS:
            th = _level_targets_hit(season, level)
            tp = _level_pitchers(season, level)
            print(f"[plan] {level} {season}: hitter targets >= {MIN_PA} PA: {len(th)}; "
                  f"pitchers >= {MIN_BF} BF: {len(tp)}", flush=True)


# ------------------------------------------------------------------ backfill
def _acc_path(level: str, season: int) -> Path:
    return SCRATCH / f"sxline2_acc_{level}_{season}.pkl"


def _pks_path(level: str, season: int) -> Path:
    return SCRATCH / f"sxline2_pks_{level}_{season}.json"


def _load_acc(level: str, season: int) -> dict:
    p = _acc_path(level, season)
    if p.exists():
        try:
            with p.open("rb") as fh:
                return pickle.load(fh)
        except Exception:
            pass
    return {"level": level, "season": season, "done_pks": set(),
            "bat": {}, "pit": {}, "feed_errors": 0, "feeds_fresh": 0,
            "feeds_with_contact": 0}


def _save_acc(acc: dict) -> None:
    p = _acc_path(acc["level"], acc["season"])
    tmp = p.with_suffix(".pkl.tmp")
    with tmp.open("wb") as fh:
        pickle.dump(acc, fh, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, p)


def _update_progress(key: str, entry: dict) -> None:
    prog = {}
    if PROGRESS_PATH.exists():
        try:
            prog = json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
        except Exception:
            prog = {}
    entry["ts"] = _now()
    prog[key] = entry
    _write_json(PROGRESS_PATH, prog)


def _collect_pks(level: str, season: int, targets: dict[int, dict]) -> dict:
    """Collect {gamePk: date} at `level` via the module's gamelog path."""
    import concurrent.futures
    import statcast_metrics as sm
    p = _pks_path(level, season)
    if p.exists():
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if d.get("pks"):
                return d
        except Exception:
            pass
    t0 = time.monotonic()
    pks: dict[str, str] = {}
    players_with_logs = 0
    ttl = PAST_TTL if season < date.today().year else 86400

    def _logs(mid):
        try:
            return mid, sm._game_logs(int(mid), season, is_pitcher=False,
                                      ttl_seconds=ttl)
        except Exception:
            return mid, []

    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=LOG_WORKERS) as ex:
        for mid, logs in ex.map(_logs, sorted(targets)):
            hit_level = False
            for split in logs:
                if split.get("_level") != level:
                    continue
                gpk = int((split.get("game") or {}).get("gamePk") or 0)
                if not gpk:
                    continue
                hit_level = True
                if str(gpk) not in pks and split.get("date"):
                    pks[str(gpk)] = split.get("date")
            if hit_level:
                players_with_logs += 1
            done += 1
            if done % 100 == 0 or done == len(targets):
                print(f"[logs {level} {season}] {done}/{len(targets)} players, "
                      f"{len(pks)} unique games, {time.monotonic()-t0:.0f}s", flush=True)
    out = {"level": level, "season": season, "n_targets": len(targets),
           "players_with_level_logs": players_with_logs, "pks": pks,
           "elapsed_s": round(time.monotonic() - t0, 1)}
    _write_json(p, out)
    return out


def _classify_bip(hit_type) -> str:
    t = str(hit_type or "").strip().lower().replace(" ", "_")
    if t == "single":
        return "single"
    if t == "double":
        return "double"
    if t == "triple":
        return "triple"
    if t in ("home_run", "homerun"):
        return "hr"
    return "out"


def _extract_feed(data: dict, game_pk: int, targets: set[int], acc: dict) -> None:
    """One pass over a cached feed: batter contact rows + swing/whiff counts
    (target hitters only) and per-pitcher fastball velo. Field extraction
    mirrors statcast_metrics.fetch_statcast_metrics_for_player exactly."""
    import statcast_metrics as sm
    import zone_metrics as zm
    game_data = data.get("gameData") or {}
    game_date = (game_data.get("datetime") or {}).get("officialDate")
    any_contact = False
    for play in (data.get("liveData") or {}).get("plays", {}).get("allPlays", []):
        matchup = play.get("matchup") or {}
        batter = int((matchup.get("batter") or {}).get("id") or 0)
        pitcher = int((matchup.get("pitcher") or {}).get("id") or 0)
        result = play.get("result") or {}
        is_target = batter in targets
        b = None
        if is_target:
            b = acc["bat"].setdefault(batter, {"rows": [], "pitches": 0,
                                               "swings": 0, "whiffs": 0})
        for event in play.get("playEvents", []):
            if not event.get("isPitch"):
                continue
            details = event.get("details") or {}
            code = details.get("code") or ""
            if b is not None:
                b["pitches"] += 1
                if code in zm.SWING_CODES:
                    b["swings"] += 1
                    if code in zm.WHIFF_CODES:
                        b["whiffs"] += 1
            if pitcher:
                pitch_data = event.get("pitchData") or {}
                velo = sm._safe_float(pitch_data.get("startSpeed"))
                ptype = (details.get("type") or {}).get("code")
                if velo is not None and ptype in FB_CODES:
                    p = acc["pit"].setdefault(pitcher, {"fb_sum": 0.0, "fb_n": 0,
                                                        "fb_max": 0.0})
                    p["fb_sum"] += velo
                    p["fb_n"] += 1
                    p["fb_max"] = max(p["fb_max"], velo)
            if b is None:
                continue
            hit_data = event.get("hitData") or {}
            launch_speed = sm._safe_float(hit_data.get("launchSpeed"))
            if launch_speed is None:
                continue
            coords = hit_data.get("coordinates") or {}
            hit_type = (details.get("eventType") or details.get("event")
                        or result.get("eventType") or result.get("event"))
            b["rows"].append({
                "game_pk": game_pk,
                "date": game_date,
                "launch_speed": launch_speed,
                "launch_angle": sm._safe_float(hit_data.get("launchAngle")),
                "total_distance": sm._safe_float(hit_data.get("totalDistance")),
                "coord_x": sm._safe_float(coords.get("coordX")),
                "coord_y": sm._safe_float(coords.get("coordY")),
                "hit_type": hit_type,
                "bb_type": (hit_data.get("trajectory") or "").title().replace("_", ""),
                "batter_side": (matchup.get("batSide") or {}).get("code"),
            })
            any_contact = True
    if any_contact:
        acc["feeds_with_contact"] += 1


def cmd_backfill() -> None:
    import concurrent.futures
    import feed_cache as fc

    if not V0_3_PATH.exists():
        print("V0' checkpoint missing - run `v0full` first (S-XLINE-3 STOP gate).",
              flush=True)
        sys.exit(2)
    v0 = json.loads(V0_3_PATH.read_text(encoding="utf-8"))
    if v0.get("verdict") != "PASS":
        print("V0' verdict is not PASS - backfill refused per registration.", flush=True)
        sys.exit(2)

    for season in SEASONS:
        for level in LEVELS:
            key = f"{level}_{season}"
            targets = _level_targets_hit(season, level)
            pkinfo = _collect_pks(level, season, targets)
            pks = {int(k): v for k, v in pkinfo["pks"].items()}
            acc = _load_acc(level, season)
            todo = sorted(pk for pk in pks if pk not in acc["done_pks"])
            print(f"[backfill {key}] targets={len(targets)} games={len(pks)} "
                  f"done={len(acc['done_pks'])} todo={len(todo)}", flush=True)
            if not todo:
                _update_progress(key, {
                    "targets": len(targets), "pks_total": len(pks),
                    "pks_done": len(acc["done_pks"]),
                    "feeds_fresh": acc["feeds_fresh"],
                    "players_with_data": len(acc["bat"]),
                    "status": "complete"})
                continue
            tset = set(targets)
            t0 = time.monotonic()
            since_ckpt = 0

            def _fetch(gpk):
                fresh = not (fc.CACHE_DIR / f"{gpk}.json").exists()
                try:
                    return gpk, fc.get_game_feed(gpk, game_date=pks.get(gpk)), fresh, None
                except Exception as e:  # noqa: BLE001
                    return gpk, None, fresh, str(e)

            CHUNK = 400
            for ci in range(0, len(todo), CHUNK):
                chunk = todo[ci:ci + CHUNK]
                with concurrent.futures.ThreadPoolExecutor(max_workers=FEED_WORKERS) as ex:
                    for gpk, data, fresh, err in ex.map(_fetch, chunk):
                        if fresh:
                            acc["feeds_fresh"] += 1
                        if err is not None or data is None:
                            acc["feed_errors"] += 1
                        else:
                            _extract_feed(data, gpk, tset, acc)
                        acc["done_pks"].add(gpk)
                        since_ckpt += 1
                        if since_ckpt >= CHECKPOINT_EVERY:
                            since_ckpt = 0
                            _save_acc(acc)
                            elapsed = time.monotonic() - t0
                            done_n = len(acc["done_pks"])
                            rate = max(1e-6, (done_n - (len(pks) - len(todo))) / elapsed)
                            eta = (len(pks) - done_n) / rate
                            _update_progress(key, {
                                "targets": len(targets), "pks_total": len(pks),
                                "pks_done": done_n, "feeds_fresh": acc["feeds_fresh"],
                                "feed_errors": acc["feed_errors"],
                                "players_with_data": len(acc["bat"]),
                                "elapsed_s": round(elapsed, 1),
                                "eta_s": round(eta, 1), "status": "running"})
                            print(f"[backfill {key}] {done_n}/{len(pks)} feeds "
                                  f"({acc['feeds_fresh']} fresh, {acc['feed_errors']} err, "
                                  f"{len(acc['bat'])} players w/ data, {elapsed:.0f}s, "
                                  f"eta {eta:.0f}s)", flush=True)
            _save_acc(acc)
            _update_progress(key, {
                "targets": len(targets), "pks_total": len(pks),
                "pks_done": len(acc["done_pks"]), "feeds_fresh": acc["feeds_fresh"],
                "feed_errors": acc["feed_errors"],
                "players_with_data": len(acc["bat"]),
                "elapsed_s": round(time.monotonic() - t0, 1), "status": "complete"})
            print(f"[backfill {key}] COMPLETE: {len(acc['done_pks'])} feeds, "
                  f"{len(acc['bat'])} players with contact/pitch-seen data", flush=True)
    print("[backfill] all level-seasons complete", flush=True)


# ------------------------------------------------------------- aggregates
def _hitter_aggregates(level: str, season: int) -> dict[int, dict]:
    """Per-player aggregates from the backfill accumulator, using the
    module's own _finalize_contact. Gap components are computed on the
    identical (ev AND la present) row set so the KNN-model scale cancels."""
    import statcast_metrics as sm
    acc = _load_acc(level, season)
    out = {}
    for mid, b in acc["bat"].items():
        rows = b["rows"]
        cq = sm._finalize_contact(rows, is_pitcher=False) if rows else {}
        evla = [r for r in rows
                if sm._safe_float(r.get("launch_speed")) is not None
                and sm._safe_float(r.get("launch_angle")) is not None]
        wobacon_act = None
        if evla:
            wobacon_act = float(np.mean([
                sm._BIP_WOBA_WEIGHTS[_classify_bip(r.get("hit_type"))] for r in evla]))
        out[mid] = {
            "bbe": int(cq.get("batted_balls") or 0),
            "n_gap": len(evla),
            "xwoba_est": _f(cq.get("xwoba_est")),
            "p90_ev": _f(cq.get("p90_ev")),
            "wobacon_act": wobacon_act,
            "pitches": b["pitches"], "swings": b["swings"], "whiffs": b["whiffs"],
        }
    return out


def _pitcher_aggregates(level: str, season: int) -> dict[int, dict]:
    acc = _load_acc(level, season)
    return {mid: {"fb_velo": p["fb_sum"] / p["fb_n"], "fb_n": p["fb_n"],
                  "fb_max": p["fb_max"]}
            for mid, p in acc["pit"].items() if p["fb_n"] > 0}


# ------------------------------------------------------------------- arms
def _season_z(values: dict[int, float]) -> dict[int, float]:
    """z within the given map (one season pool)."""
    arr = np.asarray(list(values.values()), float)
    if len(arr) < MIN_POOL_N or np.std(arr) == 0:
        return {}
    m, s = float(np.mean(arr)), float(np.std(arr))
    return {k: (v - m) / s for k, v in values.items()}


def _selection_bias(universe: list[dict], seed: int) -> dict:
    """Registered falsification: within current-line bands (per-season
    quintiles of the predictor z among the eligible universe), covered vs
    uncovered next-season outcome gap, covered-count-weighted, bootstrap CI.
    Band assignments are fixed from the full sample; bootstrap resamples
    players. Flag 'confounded' when the CI excludes 0."""
    if not universe:
        return {"n_universe": 0, "note": "empty universe"}
    by_season: dict[int, list[dict]] = {}
    for u in universe:
        by_season.setdefault(u["season"], []).append(u)
    for rows in by_season.values():
        zs = np.asarray([r["line_z"] for r in rows], float)
        qs = np.quantile(zs, [0.2, 0.4, 0.6, 0.8]) if len(zs) >= MIN_POOL_N else None
        for r in rows:
            r["band"] = int(np.searchsorted(qs, r["line_z"])) if qs is not None else 0

    cov = np.asarray([u["covered"] for u in universe], bool)
    outz = np.asarray([u["out_z"] for u in universe], float)
    band = np.asarray([f"{u['season']}_{u['band']}" for u in universe])

    def _gap(idx) -> float | None:
        c, o, bnd = cov[idx], outz[idx], band[idx]
        num = den = 0.0
        for bl in np.unique(bnd):
            sel = bnd == bl
            csel, usel = sel & c, sel & ~c
            nc, nu = int(csel.sum()), int(usel.sum())
            if nc == 0 or nu == 0:
                continue
            num += nc * (float(o[csel].mean()) - float(o[usel].mean()))
            den += nc
        return num / den if den > 0 else None

    full = _gap(np.arange(len(universe)))
    lo, hi, _p = _boot_ci(_gap, len(universe), seed=seed)
    flagged = (full is not None and lo is not None and (lo > 0 or hi < 0))
    return {
        "n_universe": len(universe), "n_covered": int(cov.sum()),
        "n_uncovered": int((~cov).sum()),
        "gap_covered_minus_uncovered_z": round(full, 4) if full is not None else None,
        "ci95": [round(lo, 4), round(hi, 4)] if lo is not None else None,
        "confounded_flag": bool(flagged),
        "design": "per-season quintile bands of the current-line z among the "
                  "stat-line-eligible universe; covered-count-weighted mean of "
                  "within-band outcome-z gaps; percentile bootstrap, "
                  f"{REPS} reps",
    }


def _measurement_arm(level: str, dest_maps: dict[int, tuple], report: dict) -> dict:
    """M-A / M-CPX under the S-XLINE-3 registration: blend50 of the capped
    gap (xwoba_est_full - line wOBA proxy, cap +-GAP_FULL_CAP) into the
    actual line vs next-season wOBA z. Coverage = >= MIN_BBE tracked BBE with
    a feed xwoba_est (the S-XLINE-2 wobacon_act/n_gap requirements are gone -
    the gap's actual-contact side now comes from the stat line itself).
    Returns the arm block for the artifact."""
    pairs = []          # covered pairs for the rho comparison
    universe = []       # selection-bias universe (no BBE requirement)
    accounting = {}
    for season in SEASONS:
        targets = _level_targets_hit(season, level)
        aggs = _hitter_aggregates(level, season)
        dest_z, _sizes = dest_maps[season + 1]
        proxies = {mid: woba_proxy(row) for mid, row in targets.items()}
        proxies = {k: v for k, v in proxies.items() if v is not None}
        arr = np.asarray(list(proxies.values()), float)
        if len(arr) < MIN_POOL_N or np.std(arr) == 0:
            continue
        pool_mean, pool_sd = float(np.mean(arr)), float(np.std(arr))
        n_cov = n_pairs = bbe_total = 0
        for mid, row in targets.items():
            if mid not in proxies:
                continue
            a = aggs.get(mid)
            est_full = (xwoba_est_full(row, a["xwoba_est"])
                        if a and a["xwoba_est"] is not None else None)
            covered = bool(a and a["bbe"] >= MIN_BBE and est_full is not None)
            if covered:
                n_cov += 1
                bbe_total += a["bbe"]
            d = dest_z.get(mid)
            if d is None or d.get("woba_z") is None:
                continue
            z_off = (proxies[mid] - pool_mean) / pool_sd
            universe.append({"season": season, "line_z": z_off,
                             "out_z": d["woba_z"], "covered": covered})
            if not covered:
                continue
            gap_full = est_full - proxies[mid]
            gap_line = max(-GAP_FULL_CAP, min(GAP_FULL_CAP, gap_full))
            z_on = z_off + W_BLEND * gap_line / pool_sd
            pairs.append({"season": season, "z_off": z_off, "z_on": z_on,
                          "out_z": d["woba_z"], "gap_full": gap_full,
                          "gap_line": gap_line, "p90_ev": a["p90_ev"]})
            n_pairs += 1
        accounting[str(season)] = {"targets": len(targets), "covered": n_cov,
                                   "pairs_both_legs": n_pairs,
                                   "covered_bbe_total": bbe_total}

    block = {"level": level, "per_season": accounting, "n_pairs": len(pairs)}
    if len(pairs) < MIN_POOL_N:
        block["verdict"] = "UNTRAINABLE"
        block["note"] = f"only {len(pairs)} covered season pairs"
        return block
    z_off = np.asarray([p["z_off"] for p in pairs], float)
    z_on = np.asarray([p["z_on"] for p in pairs], float)
    out_z = np.asarray([p["out_z"] for p in pairs], float)
    rho_off = _spearman_np(z_off, out_z)
    rho_on = _spearman_np(z_on, out_z)

    def _delta(idx):
        a = _spearman_np(z_on[idx], out_z[idx])
        b = _spearman_np(z_off[idx], out_z[idx])
        return None if a is None or b is None else a - b

    lo, hi, p_gt0 = _boot_ci(_delta, len(pairs))
    gaps = np.asarray([p["gap_line"] for p in pairs], float)
    block.update({
        "rho_actual_line": round(rho_off, 4),
        "rho_blend50": round(rho_on, 4),
        "delta_rho": round(rho_on - rho_off, 4),
        "ci95": [round(lo, 4), round(hi, 4)] if lo is not None else None,
        "p_gt0": round(p_gt0, 4) if p_gt0 is not None else None,
        "gap_line_stats": {"mean": round(float(gaps.mean()), 4),
                           "sd": round(float(gaps.std()), 4),
                           "max_abs": round(float(np.abs(gaps).max()), 4),
                           "capped_at": GAP_FULL_CAP},
        "verdict": ("PASS" if (lo is not None and lo > 0) else
                    ("NULL" if lo is not None else "UNTRAINABLE")),
    })
    report[f"selection_bias_{level}"] = _selection_bias(universe, seed=SEED)
    return block


def _aux1(dest_maps: dict) -> dict:
    """AUX-1: p90 EV level-relative at A vs next-season wOBA z."""
    xs, ys = [], []
    for season in SEASONS:
        aggs = _hitter_aggregates("A", season)
        targets = _level_targets_hit(season, "A")
        dest_z, _ = dest_maps[season + 1]
        vals = {mid: a["p90_ev"] for mid, a in aggs.items()
                if mid in targets and a["bbe"] >= MIN_BBE and a["p90_ev"] is not None}
        z = _season_z(vals)
        for mid, v in z.items():
            d = dest_z.get(mid)
            if d and d.get("woba_z") is not None:
                xs.append(v)
                ys.append(d["woba_z"])
    x, y = np.asarray(xs, float), np.asarray(ys, float)
    if len(x) < MIN_POOL_N:
        return {"n": len(x), "verdict": "UNTRAINABLE"}
    rho = _spearman_np(x, y)
    lo, hi, p = _boot_ci(lambda i: _spearman_np(x[i], y[i]), len(x))
    return {"n": len(x), "rho": round(rho, 4),
            "ci95": [round(lo, 4), round(hi, 4)] if lo is not None else None,
            "p_gt0": round(p, 4) if p is not None else None,
            "verdict": "PASS" if (lo is not None and lo > 0) else "NULL",
            "note": "z of p90_ev within (A, season) covered pool vs next-season "
                    "wOBA z; AAA early-window read was ANTI-correlated, this is "
                    "the registered honest test at the younger level"}


def _aux2(dest_maps: dict, report: dict) -> dict:
    """AUX-2: whiff share (zone_metrics codes) at A vs next K% z and wOBA z."""
    rows = []
    universe = []
    for season in SEASONS:
        aggs = _hitter_aggregates("A", season)
        targets = _level_targets_hit(season, "A")
        dest_z, _ = dest_maps[season + 1]
        proxies = {mid: woba_proxy(r) for mid, r in targets.items()}
        proxies = {k: v for k, v in proxies.items() if v is not None}
        pz = _season_z(proxies)
        vals = {}
        for mid in targets:
            a = aggs.get(mid)
            if a and a["pitches"] >= MIN_PITCHES_SEEN and a["swings"] > 0:
                vals[mid] = a["whiffs"] / a["swings"]
        z = _season_z(vals)
        for mid in targets:
            d = dest_z.get(mid)
            if d is None or mid not in pz:
                continue
            covered = mid in z
            if d.get("woba_z") is not None:
                universe.append({"season": season, "line_z": pz[mid],
                                 "out_z": d["woba_z"], "covered": covered})
            if covered and d.get("k_pct_z") is not None and d.get("woba_z") is not None:
                rows.append({"whiff_z": z[mid], "k_z": d["k_pct_z"],
                             "woba_z": d["woba_z"]})
    if len(rows) < MIN_POOL_N:
        return {"n": len(rows), "verdict": "UNTRAINABLE",
                "note": "A-level swing/whiff coverage insufficient"}
    wz = np.asarray([r["whiff_z"] for r in rows], float)
    kz = np.asarray([r["k_z"] for r in rows], float)
    oz = np.asarray([r["woba_z"] for r in rows], float)
    rho_k = _spearman_np(wz, kz)
    lo_k, hi_k, p_k = _boot_ci(lambda i: _spearman_np(wz[i], kz[i]), len(rows),
                               seed=SEED)
    rho_w = _spearman_np(wz, oz)
    lo_w, hi_w, p_w = _boot_ci(lambda i: _spearman_np(wz[i], oz[i]), len(rows),
                               seed=SEED)
    report["selection_bias_AUX2"] = _selection_bias(universe, seed=SEED)
    return {
        "n": len(rows),
        "vs_next_k_pct": {"rho": round(rho_k, 4),
                          "ci95": [round(lo_k, 4), round(hi_k, 4)],
                          "expected_direction": "positive",
                          "pass_direction": bool(lo_k is not None and lo_k > 0)},
        "vs_next_woba": {"rho": round(rho_w, 4),
                         "ci95": [round(lo_w, 4), round(hi_w, 4)],
                         "expected_direction": "negative",
                         "pass_direction": bool(hi_w is not None and hi_w < 0)},
        "verdict": ("PASS" if (lo_k is not None and lo_k > 0) else "NULL"),
        "note": "whiff share = WHIFF_CODES/SWING_CODES over all pitches seen "
                f"(>= {MIN_PITCHES_SEEN} pitches, zone_metrics qualification); "
                "call codes need no tracking hardware so coverage is near-full; "
                "registered gate direction is vs next-season K%",
    }


def _aux3(report: dict) -> dict:
    """AUX-3: pitcher fastball velo at A vs next-season K%-against z."""
    xs, ys = [], []
    universe = []
    dest_pit = {}
    for season in SEASONS:
        dest_pit[season + 1] = _dest_z_maps(season + 1, "pitching")
    for season in SEASONS:
        paggs = _pitcher_aggregates("A", season)
        pitchers = _level_pitchers(season, "A")
        dest_z, _ = dest_pit[season + 1]
        kmap = {mid: pit_k_pct(r) for mid, r in pitchers.items()}
        kmap = {k: v for k, v in kmap.items() if v is not None}
        kz_cur = _season_z(kmap)
        vals = {mid: a["fb_velo"] for mid, a in paggs.items()
                if mid in pitchers and a["fb_n"] >= MIN_FB}
        z = _season_z(vals)
        for mid in pitchers:
            d = dest_z.get(mid)
            if d is None or d.get("k_pct_z") is None or mid not in kz_cur:
                continue
            covered = mid in z
            universe.append({"season": season, "line_z": kz_cur[mid],
                             "out_z": d["k_pct_z"], "covered": covered})
            if covered:
                xs.append(z[mid])
                ys.append(d["k_pct_z"])
    x, y = np.asarray(xs, float), np.asarray(ys, float)
    if len(x) < MIN_POOL_N:
        return {"n": len(x), "verdict": "UNTRAINABLE",
                "note": "A-level tracked fastball coverage insufficient "
                        f"(>= {MIN_FB} tracked FB); pitch tracking exists only "
                        "at instrumented A parks"}
    rho = _spearman_np(x, y)
    lo, hi, p = _boot_ci(lambda i: _spearman_np(x[i], y[i]), len(x))
    report["selection_bias_AUX3"] = _selection_bias(universe, seed=SEED)
    return {"n": len(x), "rho": round(rho, 4),
            "ci95": [round(lo, 4), round(hi, 4)] if lo is not None else None,
            "p_gt0": round(p, 4) if p is not None else None,
            "verdict": "PASS" if (lo is not None and lo > 0) else "NULL",
            "note": f"avg FB velo (codes {sorted(FB_CODES)}), >= {MIN_FB} tracked "
                    "FB, z within (A, season) covered pool vs next-season "
                    "K%-against z (max-BF destination row, >= 150 BF both legs); "
                    "pitcher rows came free from the hitter-cohort feed set "
                    "(same games), so no extra fetch was needed"}


def _backfill_accounting() -> dict:
    out = {}
    for season in SEASONS:
        for level in LEVELS:
            acc = _load_acc(level, season)
            aggs = _hitter_aggregates(level, season)
            covered = [a for a in aggs.values() if a["bbe"] >= MIN_BBE]
            pk = {}
            p = _pks_path(level, season)
            if p.exists():
                try:
                    pk = json.loads(p.read_text(encoding="utf-8"))
                except Exception:
                    pk = {}
            out[f"{level}_{season}"] = {
                "hitter_targets": pk.get("n_targets"),
                "unique_games": len(pk.get("pks") or {}),
                "feeds_processed": len(acc["done_pks"]),
                "feeds_fetched_fresh": acc["feeds_fresh"],
                "feed_errors": acc["feed_errors"],
                "feeds_with_contact": acc["feeds_with_contact"],
                "players_with_any_feed_rows": len(acc["bat"]),
                "players_25plus_bbe": len(covered),
                "bbe_total_25plus": int(sum(a["bbe"] for a in covered)),
                "pitchers_with_fb_rows": len(acc["pit"]),
            }
    return out


PROPOSED_DIFF = """PROPOSED (NOT APPLIED) efv_statcast_line extension - only if M-A PASS:
  1. New feeds-based gap index beside _gap_index (source: S-XLINE-3 backfill
     aggregates for A/CPX 2023+, >= 25 tracked BBE):
       @lru_cache(maxsize=16)
       def _feed_gap_index(season: int) -> dict:
           # {mlbam: {"gap_full": clamp(xwoba_est_full - woba_line, +-0.050),
           #          "level": "A"|"CPX"}}
           # xwoba_est_full = the FROZEN S-XLINE-3 completion (lab header):
           #   (0.69*BB + 0.72*HBP' + xw_con*BIP') / PA from the milb_history
           #   level row + the feed contact estimate; woba_line = the same
           #   row's woba_proxy (identical weights, so K/BB channels cancel)
           # applied onto the line: d = W * gap_full (W = 0.5), split with
           # the SAME caps as S-XLINE:
           #   avg += clamp(d * 0.35, +-0.050); obp += clamp(d * 0.35, +-0.050)
           #   slg += clamp(d * 0.65, +-0.100); ops = obp' + slg'
  2. maybe_adjust_row: extend the level gate from `level != "AAA"` to
     `level not in ("AAA", "A", "CPX")`; AAA keeps the Savant source, A/CPX
     use _feed_gap_index behind NEW default-OFF flags
     XLINE_FEEDS_HIT_DEFAULT = False / EEPHUS_XLINE_FEEDS_HIT.
  3. In-matrix clause plan (same as S-XLINE, registered): clause 1 uncovered
     -row invariance OFF vs ON; clause 2 no-harm delta >= -0.003 on the
     debuted-KM pooled OOS Spearman; clause 3 bounded pull (< 0.5 rate scale)
     + post-flip max served grade move <= 3 FV among covered actives.
     Flip only on full pass; otherwise the eval artifact is the ledger."""


def cmd_arms() -> None:
    if not V0_3_PATH.exists():
        print("V0' checkpoint missing - run `v0full` first.", flush=True)
        sys.exit(2)
    v0 = json.loads(V0_3_PATH.read_text(encoding="utf-8"))
    if v0.get("verdict") != "PASS":
        print("V0' is not PASS - arms refused per registration.", flush=True)
        sys.exit(2)

    print("[arms] building destination outcome pools...", flush=True)
    dest_maps = {y: _dest_z_maps(y, "hitting") for y in (2024, 2025, 2026)}

    report: dict = {}
    print("[arms] M-A (primary)...", flush=True)
    m_a = _measurement_arm("A", dest_maps, report)
    print(f"[arms] M-A: n={m_a.get('n_pairs')} delta={m_a.get('delta_rho')} "
          f"ci={m_a.get('ci95')} -> {m_a.get('verdict')}", flush=True)
    print("[arms] M-CPX (secondary)...", flush=True)
    m_cpx = _measurement_arm("CPX", dest_maps, report)
    print(f"[arms] M-CPX: n={m_cpx.get('n_pairs')} delta={m_cpx.get('delta_rho')} "
          f"ci={m_cpx.get('ci95')} -> {m_cpx.get('verdict')}", flush=True)
    print("[arms] AUX-1...", flush=True)
    aux1 = _aux1(dest_maps)
    print(f"[arms] AUX-1: n={aux1.get('n')} rho={aux1.get('rho')} "
          f"ci={aux1.get('ci95')} -> {aux1.get('verdict')}", flush=True)
    print("[arms] AUX-2...", flush=True)
    aux2 = _aux2(dest_maps, report)
    print(f"[arms] AUX-2: n={aux2.get('n')} -> {aux2.get('verdict')}", flush=True)
    print("[arms] AUX-3...", flush=True)
    aux3 = _aux3(report)
    print(f"[arms] AUX-3: n={aux3.get('n')} rho={aux3.get('rho')} "
          f"ci={aux3.get('ci95')} -> {aux3.get('verdict')}", flush=True)

    artifact = {
        "generated_at": date.today().isoformat(),
        "experiment": "S-XLINE-3 (docs/efv-2026-07-23/GATES.md)",
        "tool": "tools/efv_statcast_line2_lab.py",
        "registration_echo": REGISTRATION_ECHO_3,
        "v0_full": v0,
        "backfill_accounting": _backfill_accounting(),
        "conventions": {
            "outcome": "next-season wOBA proxy (see woba_proxy docstring: pa, ab, "
                       "avg, obp, slg, bb, hr; triples folded into doubles; HBP "
                       "reconstructed from OBP), z within the destination "
                       "(max-exposure level, season) pool, >= 150 PA both legs; "
                       "2025->2026 outcome leg is 2026 season-to-date",
            "gap": "gap_full = xwoba_est_full (FROZEN header completion of the "
                   "feed contact estimate with the level row's actual BB/HBP'/SO "
                   "accounting) minus the same row's woba_proxy (identical "
                   "linear weights, so the BB/HBP/K channels cancel exactly); "
                   f"gap_line = clamp(gap_full, +-{GAP_FULL_CAP}); "
                   "blend = line proxy + 0.5 * gap_line (z with the pool's own "
                   "mean/sd, mirroring efv_statcast_line's additive hitter form)",
            "bootstrap": f"percentile, {REPS} reps, seed {SEED}, paired for the "
                         "M arms (delta rho), plain for AUX rho",
        },
        "arms": {"M_A_primary": m_a, "M_CPX_secondary": m_cpx,
                 "AUX_1_p90ev": aux1, "AUX_2_whiff": aux2, "AUX_3_fb_velo": aux3},
        "selection_bias": {k: v for k, v in report.items()},
        "caveats": [
            "A-level batted-ball tracking is park-dependent (FSL Hawk-Eye parks "
            "dominate coverage); the selection-bias falsification is the "
            "registered guard for exactly this",
            "CPX registered as likely underpowered; an honest NULL closes it "
            "without touching the A-ball verdict",
            "2026 destination lines are season-to-date (partial season)",
            "feeds xwoba_est is contact-only and carries the module's profile "
            "adjustment; V0' validated the rank agreement of its K/BB-completed "
            "form vs Savant full xwOBA (the S-XLINE-3 amendment)",
            "any constant xwOBAcon-scale offset in the feed estimate enters the "
            "gap only through the slowly-varying contact share; within-pool z + "
            "rank statistics absorb it (V0' bias/slope recorded)",
        ],
        "nothing_ships_from_this_run": True,
    }
    if m_a.get("verdict") == "PASS":
        artifact["proposed_next_step"] = PROPOSED_DIFF
    verdicts = {k: v.get("verdict") for k, v in artifact["arms"].items()}
    artifact["verdicts"] = verdicts
    _write_json(EVAL3_PATH, artifact)
    print(f"[arms] wrote {EVAL3_PATH}", flush=True)
    print(f"[arms] verdicts: {verdicts}", flush=True)


# ------------------------------------------------------- S-XLINE-4 (inc)
REGISTRATION_ECHO_4 = {
    "source": "docs/efv-2026-07-23/GATES.md :: 'S-XLINE-4 gate registration - "
              "2026-07-23 (pre-registered; incremental arms on the AUX winners)'",
    "seed": SEED, "bootstrap_reps": REPS,
    "clauses": {
        "baseline": "per arm: cross-fitted ridge (5-fold, by player) on the "
                    "CURRENT-season stat-line inputs eFV consumes (hitters: "
                    "wOBA-proxy z, K%, BB%, ISO z, age-for-level; pitchers: "
                    "K%a, BB%a, ERA z, age-for-level), predicting the arm's "
                    "outcome (hitters: next-season wOBA z; pitchers: "
                    "next-season K%a z)",
        "INC-1": "AUX-1 p90 EV z vs the hitter baseline residual; lo95 > 0 proceeds",
        "INC-2": "AUX-2 whiff share vs the hitter baseline residual (sign: "
                 "negative helps wOBA; and separately vs the next-K% residual, "
                 "sign positive)",
        "INC-3": "AUX-3 FB velo vs the pitcher baseline residual; lo95 > 0 proceeds",
        "age_interaction": "descriptive, not verdict-bearing: incremental rho "
                           "by age-for-level half (younger vs older), each arm",
        "ship_rule": "an INC pass makes the signal ELIGIBLE for a bounded live "
                     "overlay on A/CPX prospects (magnitude bounded so no served "
                     "grade moves more than 2 FV, default-OFF flag, post-flip "
                     "check vs a fresh baseline snapshot with the 2-FV ceiling, "
                     "registry row provisional, chip copy in the eFV explainer); "
                     "INC fail = recorded NULL, signal stays display-only",
    },
}


def _ridge_crossfit(X: np.ndarray, y: np.ndarray, groups: np.ndarray):
    """Out-of-fold predictions from a closed-form ridge; folds assigned by
    PLAYER (a player's multiple season-pairs share a fold, so no player sits
    on both sides of a split). Deterministic: rng permutation seed 20260723
    of the sorted unique player ids. Features standardized on the train fold
    only; intercept via train-fold centering."""
    rng = np.random.default_rng(SEED)
    uids = np.unique(groups)
    perm = rng.permutation(len(uids))
    fold_of = {uid: int(perm[i] % N_FOLDS) for i, uid in enumerate(uids)}
    fold = np.asarray([fold_of[g] for g in groups])
    yhat = np.full(len(y), np.nan)
    for f in range(N_FOLDS):
        tr, te = fold != f, fold == f
        if te.sum() == 0 or tr.sum() < 8:
            continue
        mu, sd = X[tr].mean(axis=0), X[tr].std(axis=0)
        sd = np.where(sd == 0, 1.0, sd)
        xtr, xte = (X[tr] - mu) / sd, (X[te] - mu) / sd
        ym = float(y[tr].mean())
        a = xtr.T @ xtr + RIDGE_LAMBDA * np.eye(X.shape[1])
        beta = np.linalg.solve(a, xtr.T @ (y[tr] - ym))
        yhat[te] = ym + xte @ beta
    return yhat


def _hit_dataset(dest_maps: dict) -> tuple[list[dict], dict]:
    """Stat-line-eligible A-ball season pairs with the registered hitter
    feature vector and both outcome targets. The baseline trains on the FULL
    eligible universe (covered or not) - the strongest stat-line baseline,
    which biases AGAINST a false INC pass; residuals stay out-of-fold for
    every row by the player-fold construction."""
    rows: list[dict] = []
    skipped = {"no_outcome_row": 0, "feature_incomplete": 0}
    for season in SEASONS:
        targets = _level_targets_hit(season, "A")
        dest_z, _ = dest_maps[season + 1]
        proxies, isos = {}, {}
        for mid, row in targets.items():
            w = woba_proxy(row)
            slg, avg = _f(row.get("slg")), _f(row.get("avg"))
            if w is not None and slg is not None and avg is not None:
                proxies[mid] = w
                isos[mid] = slg - avg
        pz, iz = _season_z(proxies), _season_z(isos)
        for mid, row in targets.items():
            d = dest_z.get(mid)
            if d is None:
                skipped["no_outcome_row"] += 1
                continue
            k = hit_k_pct(row)
            bb, pa, age = _f(row.get("bb")), _f(row.get("pa")), _f(row.get("age"))
            if (mid not in pz or mid not in iz or k is None or bb is None
                    or not pa or age is None):
                skipped["feature_incomplete"] += 1
                continue
            rows.append({"mid": mid, "season": season, "age": age,
                         "x": [pz[mid], k, bb / pa, iz[mid], age],
                         "out_woba_z": d.get("woba_z"),
                         "out_k_z": d.get("k_pct_z")})
    return rows, skipped


def _pit_dataset() -> tuple[list[dict], dict]:
    rows: list[dict] = []
    skipped = {"no_outcome_row": 0, "feature_incomplete": 0}
    for season in SEASONS:
        pitchers = _level_pitchers(season, "A")
        dest_z, _ = _dest_z_maps(season + 1, "pitching")
        eras = {mid: _f(r.get("era")) for mid, r in pitchers.items()}
        ez = _season_z({k: v for k, v in eras.items() if v is not None})
        for mid, row in pitchers.items():
            d = dest_z.get(mid)
            if d is None or d.get("k_pct_z") is None:
                skipped["no_outcome_row"] += 1
                continue
            k = pit_k_pct(row)
            bb, bf, age = _f(row.get("bb")), _f(row.get("bf")), _f(row.get("age"))
            if mid not in ez or k is None or bb is None or not bf or age is None:
                skipped["feature_incomplete"] += 1
                continue
            rows.append({"mid": mid, "season": season, "age": age,
                         "x": [k, bb / bf, ez[mid], age],
                         "out_k_z": d["k_pct_z"]})
    return rows, skipped


def _fit_baseline(rows: list[dict], out_key: str, feats: tuple):
    """Cross-fitted baseline on the rows carrying `out_key`. Returns
    ({(mid, season): residual}, diagnostics, {(mid, season): age})."""
    sel = [r for r in rows if r.get(out_key) is not None]
    X = np.asarray([r["x"] for r in sel], float)
    y = np.asarray([r[out_key] for r in sel], float)
    g = np.asarray([r["mid"] for r in sel])
    yhat = _ridge_crossfit(X, y, g)
    ok = ~np.isnan(yhat)
    resid = {(r["mid"], r["season"]): float(y[i] - yhat[i])
             for i, r in enumerate(sel) if ok[i]}
    ages = {(r["mid"], r["season"]): r["age"] for r in sel}
    rho = _spearman_np(yhat[ok], y[ok])
    diag = {"n": int(ok.sum()), "outcome": out_key, "features": list(feats),
            "ridge_lambda": RIDGE_LAMBDA, "folds": N_FOLDS,
            "fold_scheme": f"player-id folds, rng permutation seed {SEED}",
            "oof_spearman_vs_outcome": round(rho, 4) if rho is not None else None,
            "training_universe": "FULL stat-line-eligible A-ball pair universe "
                                 "(covered and uncovered), the strongest "
                                 "stat-line baseline"}
    return resid, diag, ages


def _signal_maps_hit() -> tuple[dict, dict]:
    """Per-season signal z maps, constructed EXACTLY like the S-XLINE-3 AUX
    arms: p90 EV z within the (A, season) covered pool (>= MIN_BBE BBE);
    whiff share z within the (A, season) qualified pool (>= 100 pitches)."""
    p90, whiff = {}, {}
    for season in SEASONS:
        aggs = _hitter_aggregates("A", season)
        targets = _level_targets_hit(season, "A")
        v1 = {mid: a["p90_ev"] for mid, a in aggs.items()
              if mid in targets and a["bbe"] >= MIN_BBE and a["p90_ev"] is not None}
        p90[season] = _season_z(v1)
        v2 = {mid: a["whiffs"] / a["swings"] for mid, a in aggs.items()
              if mid in targets and a["pitches"] >= MIN_PITCHES_SEEN
              and a["swings"] > 0}
        whiff[season] = _season_z(v2)
    return p90, whiff


def _signal_map_pit() -> dict:
    velo = {}
    for season in SEASONS:
        paggs = _pitcher_aggregates("A", season)
        pitchers = _level_pitchers(season, "A")
        vals = {mid: a["fb_velo"] for mid, a in paggs.items()
                if mid in pitchers and a["fb_n"] >= MIN_FB}
        velo[season] = _season_z(vals)
    return velo


def _inc_test(resid: dict, signal_maps: dict, ages: dict,
              expected_sign: str) -> tuple[dict, dict | None]:
    """One registered INC arm: Spearman(signal z, baseline residual) on the
    signal-covered rows; percentile bootstrap of rows (residuals held fixed
    from the single cross-fit - the cross-fit is the leakage guard). Also
    returns the descriptive age-interaction block (median age-for-level
    split; younger = age <= median)."""
    xs, ys, ag = [], [], []
    for key, res in resid.items():
        z = signal_maps.get(key[1], {}).get(key[0])
        if z is None:
            continue
        xs.append(z)
        ys.append(res)
        ag.append(ages[key])
    x, y, a = (np.asarray(v, float) for v in (xs, ys, ag))
    n = len(x)
    if n < MIN_POOL_N:
        return {"n": n, "verdict": "UNTRAINABLE"}, None
    rho = _spearman_np(x, y)
    lo, hi, p = _boot_ci(lambda i: _spearman_np(x[i], y[i]), n)
    if expected_sign == "positive":
        passed, bar = (lo is not None and lo > 0), "lo95 > 0"
    else:
        passed, bar = (hi is not None and hi < 0), "hi95 < 0"
    block = {"n": n, "rho": round(rho, 4) if rho is not None else None,
             "ci95": [round(lo, 4), round(hi, 4)] if lo is not None else None,
             "p_gt0": round(p, 4) if p is not None else None,
             "expected_sign": expected_sign, "bar": bar, "pass": bool(passed)}
    med = float(np.median(a))
    young = a <= med
    r_y = _spearman_np(x[young], y[young])
    r_o = _spearman_np(x[~young], y[~young])
    age_blk = {"median_age_for_level": med,
               "younger_le_median": {"n": int(young.sum()),
                                     "rho": round(r_y, 4) if r_y is not None else None},
               "older_gt_median": {"n": int((~young).sum()),
                                   "rho": round(r_o, 4) if r_o is not None else None},
               "note": "descriptive, not verdict-bearing (registered); rho = "
                       "Spearman(signal z, baseline residual) within the half"}
    return block, age_blk


def cmd_inc() -> None:
    """S-XLINE-4: incremental arms on the S-XLINE-3 AUX winners. Requires
    the S-XLINE-3 artifact (AUX passes recorded) + the local backfill
    accumulators; zero fetches (past-season milb_history is cache-final and
    the 2026 destination leg was cache-warmed by the arms run)."""
    if not EVAL3_PATH.exists():
        print("S-XLINE-3 artifact missing - run `arms` first.", flush=True)
        sys.exit(2)
    eval3 = json.loads(EVAL3_PATH.read_text(encoding="utf-8"))
    aux_verdicts = {k: v for k, v in (eval3.get("verdicts") or {}).items()
                    if k.startswith("AUX")}
    if not any(v == "PASS" for v in aux_verdicts.values()):
        print("no AUX pass recorded in the S-XLINE-3 artifact - nothing to test.",
              flush=True)
        sys.exit(2)

    print("[inc] building destination outcome pools + datasets...", flush=True)
    dest_maps = {y: _dest_z_maps(y, "hitting") for y in (2024, 2025, 2026)}
    hit_rows, hit_skip = _hit_dataset(dest_maps)
    pit_rows, pit_skip = _pit_dataset()
    print(f"[inc] hitter universe {len(hit_rows)} pairs (skipped {hit_skip}), "
          f"pitcher universe {len(pit_rows)} pairs (skipped {pit_skip})", flush=True)

    resid_w, base_w, ages_w = _fit_baseline(hit_rows, "out_woba_z", HIT_FEATS)
    resid_k, base_k, ages_k = _fit_baseline(hit_rows, "out_k_z", HIT_FEATS)
    resid_p, base_p, ages_p = _fit_baseline(pit_rows, "out_k_z", PIT_FEATS)
    print(f"[inc] baselines: hit-wOBA n={base_w['n']} "
          f"rho={base_w['oof_spearman_vs_outcome']}; hit-K n={base_k['n']} "
          f"rho={base_k['oof_spearman_vs_outcome']}; pit-K n={base_p['n']} "
          f"rho={base_p['oof_spearman_vs_outcome']}", flush=True)

    p90_maps, whiff_maps = _signal_maps_hit()
    velo_maps = _signal_map_pit()

    inc1, age1 = _inc_test(resid_w, p90_maps, ages_w, "positive")
    print(f"[inc] INC-1 p90ev: n={inc1.get('n')} rho={inc1.get('rho')} "
          f"ci={inc1.get('ci95')} pass={inc1.get('pass')}", flush=True)
    inc2_w, age2_w = _inc_test(resid_w, whiff_maps, ages_w, "negative")
    inc2_k, age2_k = _inc_test(resid_k, whiff_maps, ages_k, "positive")
    print(f"[inc] INC-2 whiff vs wOBA-resid: rho={inc2_w.get('rho')} "
          f"ci={inc2_w.get('ci95')} pass={inc2_w.get('pass')}; vs K-resid: "
          f"rho={inc2_k.get('rho')} ci={inc2_k.get('ci95')} "
          f"pass={inc2_k.get('pass')}", flush=True)
    inc3, age3 = _inc_test(resid_p, velo_maps, ages_p, "positive")
    print(f"[inc] INC-3 fb velo: n={inc3.get('n')} rho={inc3.get('rho')} "
          f"ci={inc3.get('ci95')} pass={inc3.get('pass')}", flush=True)

    inc1["verdict"] = ("PASS" if inc1.get("pass") else
                       inc1.get("verdict", "NULL"))
    inc3["verdict"] = ("PASS" if inc3.get("pass") else
                       inc3.get("verdict", "NULL"))
    inc2_channels = []
    if inc2_w.get("pass"):
        inc2_channels.append("woba_residual")
    if inc2_k.get("pass"):
        inc2_channels.append("k_residual")
    inc2 = {"vs_woba_residual": inc2_w, "vs_k_residual": inc2_k,
            "eligible_channels": inc2_channels,
            "verdict": "PASS" if inc2_channels else (
                "UNTRAINABLE" if inc2_w.get("verdict") == "UNTRAINABLE"
                else "NULL"),
            "verdict_rule": "the registration lists two directional channels "
                            "(negative vs the wOBA residual; positive vs the "
                            "next-K% residual); the arm PASSES if a channel "
                            "clears its bar, and overlay eligibility extends "
                            "only to the channel(s) that cleared"}

    verdicts = {"INC_1_p90ev": inc1["verdict"], "INC_2_whiff": inc2["verdict"],
                "INC_3_fb_velo": inc3["verdict"]}
    eligible = []
    if inc1["verdict"] == "PASS":
        eligible.append("p90_ev (hitters, next-wOBA channel)")
    for ch in inc2_channels:
        eligible.append(f"whiff_share (hitters, {ch} channel)")
    if inc3["verdict"] == "PASS":
        eligible.append("fb_velo (pitchers, next-K%a channel)")

    artifact = {
        "generated_at": date.today().isoformat(),
        "experiment": "S-XLINE-4 (docs/efv-2026-07-23/GATES.md)",
        "tool": "tools/efv_statcast_line2_lab.py (inc command)",
        "registration_echo": REGISTRATION_ECHO_4,
        "upstream": {
            "s_xline3_artifact": "data/xfv_statcast_line3_eval.json",
            "aux_verdicts": aux_verdicts,
            "selection_bias_carryover": "the S-XLINE-3 selection-bias "
                "falsifications on these exact covered pools were clean "
                "(no confounded flags); INC re-uses those pools",
        },
        "datasets": {
            "hitter_pairs": {"n": len(hit_rows), "skipped": hit_skip},
            "pitcher_pairs": {"n": len(pit_rows), "skipped": pit_skip},
            "note": "A-ball 2023-2025 -> Y+1, >= 150 PA / >= 150 BF both legs, "
                    "outcome z within the destination (max-exposure level, "
                    "season) pool; 2025->2026 outcome leg is 2026 season-to-date",
        },
        "baselines": {"hit_next_woba_z": base_w, "hit_next_k_z": base_k,
                      "pit_next_k_z": base_p},
        "arms": {"INC_1_p90ev": inc1, "INC_2_whiff": inc2,
                 "INC_3_fb_velo": inc3},
        "age_interaction": {
            "INC_1_p90ev": age1,
            "INC_2_whiff_vs_woba_residual": age2_w,
            "INC_2_whiff_vs_k_residual": age2_k,
            "INC_3_fb_velo": age3,
        },
        "conventions": {
            "signals": "identical per-season z construction to the S-XLINE-3 "
                       "AUX arms (p90 EV: >= 25 BBE covered pool; whiff share: "
                       ">= 100 pitches seen; FB velo: >= 50 tracked FB)",
            "incremental_statistic": "Spearman(signal z, out-of-fold baseline "
                                     "residual) on the signal-covered rows",
            "bootstrap": f"percentile, {REPS} reps, seed {SEED}, resampling "
                         "rows with residuals held fixed from the single "
                         "cross-fit (the player-fold cross-fit is the leakage "
                         "guard)",
            "age_for_level": "StatsAPI seasonal age on the A-ball row; every "
                             "row in a pool is at the same level, so age IS "
                             "age-for-level within the pool",
        },
        "caveats": [
            "the baseline trains on the FULL stat-line-eligible universe, not "
            "just covered rows - the strongest stat-line baseline, biasing "
            "against a false INC pass",
            "A-level batted-ball/pitch tracking is park-dependent for INC-1/"
            "INC-3 (S-XLINE-3 selection-bias reads were clean on these pools)",
            "2026 destination lines are season-to-date (partial season)",
            "ridge lambda 1.0 is an a-priori default on standardized features, "
            "not tuned against any arm result",
        ],
        "verdicts": verdicts,
        "overlay_eligible_signals": eligible,
        "next_step_if_pass": "bounded live overlay on A/CPX prospects per the "
                             "registered ship rule (2-FV ceiling, default-OFF "
                             "flag, post-flip check, registry row provisional, "
                             "chip copy); an in-matrix feature ship stays "
                             "impossible until A-ball-covered cohorts resolve",
        "nothing_ships_from_this_run": True,
    }
    _write_json(EVAL4_PATH, artifact)
    print(f"[inc] wrote {EVAL4_PATH}", flush=True)
    print(f"[inc] verdicts: {verdicts}", flush=True)
    print(f"[inc] overlay-eligible: {eligible}", flush=True)


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "v0full"
    if cmd == "v0":
        cmd_v0()
    elif cmd == "v0full":
        cmd_v0_full()
    elif cmd == "plan":
        cmd_plan()
    elif cmd == "backfill":
        cmd_backfill()
    elif cmd == "arms":
        cmd_arms()
    elif cmd == "inc":
        cmd_inc()
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
