# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV Pass 1 -- leakage-clean as-of feature matrix + KM-censored labels (HITTERS).

This is the training SUBSTRATE for the eFV flagship model. It assembles one row per
resolved/censored prospect with features built strictly as-of a pre-outcome decision
point, attaches a first-6-MLB-season bWAR label with censoring handling, and reproduces
the consensus-FV-only baseline that the model must match or beat. NO MODEL IS FIT HERE.

Design (per docs/xfv-phase1-plan.md, owner sign-off 2026-06-21):
  COHORT     HITTERS only. Debuted (debuts.json) debut years 2017-2023 + the bust pool
             (inactive.json, never reached MLB). Busts are real 0-WAR outcomes, kept in
             to avoid survivorship bias (the prospect_path / source_backtest house rule).
  VINTAGE    consensus FV strictly pre-outcome: the LATEST points[] entry dated before
             the debut date (debuted) or the player's final prospect point (bust). Uses
             consensus_fv_raw / consensus_fv_pre_shrinkage -- never the shrunk grade,
             never fv_close/fv_high (whole-history candlesticks that peek forward).
  FEATURES   prior backbone (consensus FV, per-source FG/MLB-Pipeline FV, n_sources),
             the hit-tool + tool vector, scout disagreement (fv_stddev/spread -- kept
             though the Phase-1 sweep showed ~0 outcome signal), translated production
             from the StatsAPI ladder (milb_history, final pre-decision MiLB season --
             season-specific norms are contemporaneous by construction = leakage-safe):
             age-rel-level, level rank, staleness, league-relative k/bb/iso; plus draft
             pick/bonus and pre-decision IL history. NO Statcast (no historical depth;
             Tier-2 overlay is a later pass).
  TARGET     first-6-MLB-season summed bWAR (career_war seasons debut..debut+5).
  CENSORING  KM-from-the-start (owner call): 2017-2020 debuts resolve fully (window ends
             <= 2025); 2021-2023 debuts are right-censored -- carried with a rate
             projection of the unobserved tail + an observed-fraction weight. Busts = 0.
             We emit BOTH the resolved-only and the censored-included targets so the
             baseline's sensitivity to the censoring assumption is measurable.
  BASELINE   consensus_fv_raw rank vs realized WAR (Spearman) -- THE bar. Reported for
             debuted-only, full-pool resolved, and KM-censored full pool.

Artifacts: data/xfv_hitter_matrix.json (the matrix) + data/xfv_dataset_report.json.
Run: python efv_dataset.py
"""

from __future__ import annotations

import json
import logging
import statistics
from datetime import date
from pathlib import Path

import milb_history as mh
import storage
from prospect_path import _spearman   # reuse the house hand-rolled rank corr

try:
    import efv_statcast_line as _xline   # S-XLINE AAA measurement upgrade (flag-gated)
except ImportError:                      # never let the optional layer break the build
    _xline = None

try:
    import efv_park_line as _parkline    # W2 PARK-LINE MiLB park neutralization (flag-gated)
except ImportError:                      # never let the optional layer break the build
    _parkline = None

log = logging.getLogger(__name__)

# --- E-STALE (2026-07-14): serve-time anchor-staleness decay -----------------
# ~7% of actively-scored players carry a consensus anchor (fv + tools) frozen at
# their LAST list appearance while stats/age move on. PREMISE CORRECTED by the
# audit (measured): ~16% of debuted TRAINING rows also carry >1y-stale anchors
# (26% of the 2017-2019 cohorts) - but ALL bust rows anchor at their final list
# point (staleness 0 by construction), so the stale-anchor configuration
# appears in training ONLY with debuted-survivor labels. The model structurally
# cannot learn the stale-anchor BUST discount (that is the correct
# justification for a serve-time decay, not zero train staleness). Ground truth (tools/
# efv_stale_anchor_lab.py -> data/xfv_stale_anchor_eval.json, held-out-validated
# 2021-fit / 2022-validate): dropped-from-lists players bust ~91% vs ~55% for
# same-band re-listed controls and realize ~FV20-23 against FV35-45 anchors;
# the age gradient is flat, so time-since-listing alone drives the schedule.
# These constants MUST match the committed eval artifact (test-pinned, the
# overseas-factors pattern). Applied to the MODEL's fv input + the blend's
# consensus leg for ACTIVE rows only; the DISPLAYED consensus stays raw.
STALE_ANCHOR_RAMP_START_MO = 18     # inside normal annual list cadence: no decay
STALE_ANCHOR_RAMP_FULL_MO = 30      # fully "dropped" per the 18mo-relist study
STALE_ANCHOR_TERMINAL = {35: 10.0, 40: 10.0, 45: 10.0}   # FV points at full ramp


def _stale_anchor_discount(asof_iso, fv_raw, today=None):
    """FV-point decay of the model anchor for a live row. 0 inside the ramp
    start, linear to the band terminal at the ramp end. Bands without ground
    truth (outside 35-45) are never decayed."""
    if not asof_iso or fv_raw is None:
        return 0.0
    try:
        asof = date.fromisoformat(str(asof_iso)[:10])
    except ValueError:
        return 0.0
    months = ((today or date.today()) - asof).days / 30.44
    if months <= STALE_ANCHOR_RAMP_START_MO:
        return 0.0
    band = int(round(float(fv_raw) / 5.0) * 5)
    term = STALE_ANCHOR_TERMINAL.get(band)
    if not term:
        return 0.0
    frac = min(1.0, (months - STALE_ANCHOR_RAMP_START_MO)
               / (STALE_ANCHOR_RAMP_FULL_MO - STALE_ANCHOR_RAMP_START_MO))
    return term * frac

DATA_DIR = Path(__file__).parent / "data"
MATRIX_PATH = DATA_DIR / "xfv_hitter_matrix.json"
REPORT_PATH = DATA_DIR / "xfv_dataset_report.json"

DEBUT_YEARS = tuple(range(2011, 2025))      # 2011-2024 (2011-2016 via the MLB Pipeline
#   backfill, now in debuts.json after the rebuild — captured directly, no augment needed)
RESOLVED_THROUGH = 2025                      # last fully-played season
TARGET_SEASONS = 6
CURRENT_SEASON = 2026
_LEVEL_RANK = {"DSL": 0, "CPX": 1, "A": 2, "A+": 3, "AA": 4, "AAA": 5}
# contemporaneous-ish typical age by level (leakage-free static prior for age-rel-level;
# the modeling pass refines this with frozen empirical level-season medians).
#
# C2 2026-07-30 - MEASURED AND NOT REPLACED (registered null, see
# docs/efv-2026-07-30/EFV_LANE_GATES.md and data/xfv_agepipe_eval.json).
# The empirical prospect-filtered DECIMAL medians were built for the first time
# (tools/_c_agenorms.py, 32,616 qualified prospect-season-level rows 2014-2026, the same
# >=50 PA / >=60 BF exposure gate _milb_features applies) and they are 0.10 to 1.86 yr
# OLDER than this table: DSL 18.10, CPX 19.58, A 21.45, A+ 22.77, AA 24.08, AAA 25.86.
# So the site ("young for AAA") and the model ("exactly neutral") really do tell opposite
# stories, and this table is the younger of the two. Swapping it in is nonetheless a NULL
# on every cut (forward-chained pooled rho over 8 splits: hit +0.0005, pit -0.0019 against
# MDE95 0.017 / 0.016; on SCORED_YEARS pit -0.0075; per-fold 5/8 positive both sides; and
# the pit side is NEGATIVE where it matters most), so under the gate standard it does not
# ship and the static prior stands. The measured table is published as the reconciliation
# reference for the DISPLAY tables (eta.EXPECTED_AGES, level_norms) rather than being
# forced into the model on sub-floor evidence. Do not swap it without a new gate.
_TYPICAL_LEVEL_AGE = {"DSL": 18.0, "CPX": 19.0, "A": 20.0, "A+": 21.0,
                      "AA": 22.5, "AAA": 24.0}
# C1 guard: the decimal season-midpoint age and the integer StatsAPI baseball age can
# only differ by less than one year by construction (the latter is the floor of the
# former), so a wider gap is a DATA CONFLICT -- a birth_date bound to the wrong player.
# Past this, keep the feed's own age. 1.05 leaves room for the 1dp rounding.
AGE_CONFLICT_MAX_YR = 1.05


def _resolve_season_age(row_age, birth_date, season):
    """C1 2026-07-30 (the owner's decimal-ages ask). The age the model reads for a
    MiLB season row: the DECIMAL season-midpoint age from birth_date, with the integer
    StatsAPI "baseball age" as the fallback. That is the REVERSE of the old precedence,
    where the decimal branch was gated behind `if age is None` and was therefore DEAD --
    measured, the model saw an integer age on 4,260 of 4,260 live rows.

    A CORRECTNESS change, not an accuracy claim, and the ship note says so. The StatsAPI
    baseball age is floor(age at June 30), so the floor loses a mean 0.52 yr and, worse,
    loses a DIFFERENT amount by birth month: a July-born player is flattered by up to
    0.91 yr against a June-born one at the same true age. It also manufactures a fake
    neutral -- an integer age meeting an integer level norm put 17.6% of live rows
    (752 of 4,260) at age_rel_level EXACTLY 0.0. The measured accuracy effect is a NULL on
    every cut and the zero-information control (integer age + a row-permuted fractional
    part) scores the same, so no rank gain is claimed: forward-chained pooled rho over 8
    splits moves hit +0.0003 / pit +0.0016 against MDE95 0.017 / 0.016, control
    +0.0005 / +0.0017. Ledger: data/xfv_agepipe_eval.json, tools/_c_agepipe_lab.py,
    docs/efv-2026-07-30/EFV_LANE_GATES.md.

    CONFLICT GUARD: the two ages can only differ by under a year by construction, so a
    larger gap means one of the two inputs is wrong -- almost always a birth_date bound to
    the wrong player by identity resolution (measured: 4 labeled-matrix rows, e.g. a
    luis_gonzalez carrying birth_date 2005-07-15 against a StatsAPI age of 23 in 2019, a
    9.0 yr gap; ZERO live rows). eFV must not start trusting a bad birth date over the
    feed's own age, so a gap past AGE_CONFLICT_MAX_YR keeps the StatsAPI integer.
    """
    age = _f(row_age)
    if not birth_date:
        return age
    try:
        b = date.fromisoformat(str(birth_date)[:10])
    except (TypeError, ValueError):
        return age
    dec_age = round((date(int(season), 6, 30) - b).days / 365.25, 1)
    if age is None or abs(dec_age - age) <= AGE_CONFLICT_MAX_YR:
        return dec_age
    return age

# age_rel_level bound. The HARD clip is a genuine asymmetry on the live board: measured
# 2026-07-30, 489 rows (123 hit / 366 pit) sit pinned at exactly +3.5 against FOUR at
# -3.5, so in practice the cap is protection for old-for-level org filler and almost
# never touches a young-for-level prospect. AGE_REL_SOFT replaces the clip with a
# tanh saturation over the SAME effective range (odd, monotone, derivative 1 at 0, so
# small age gaps are untouched and only the extremes bend, spreading the 489 pinned rows
# by severity instead of collapsing them onto one value).
# DEFAULT OFF: measured under the full gate as a NULL (forward-chained pooled rho over 8
# splits hit +0.0063 / pit +0.0014 against MDE95 0.017 / 0.016, and the hit number is one
# fold carrying +0.0426 with 4 of 8 folds negative). The gate standard does not license
# shipping a feature-shape change on sub-floor evidence, so the dial exists, is tested,
# and is off. data/xfv_agepipe_eval.json, docs/efv-2026-07-30/EFV_LANE_GATES.md.
AGE_REL_CAP = 3.5
AGE_REL_SOFT = False


def _age_rel_bound(x: float) -> float:
    """Bound age_rel_level to +/-AGE_REL_CAP: hard clip (shipped) or, with
    AGE_REL_SOFT, a same-range smooth saturation."""
    if AGE_REL_SOFT:
        import math
        return AGE_REL_CAP * math.tanh(x / AGE_REL_CAP)
    return max(-AGE_REL_CAP, min(AGE_REL_CAP, x))

_HIT_TOOLS = ("hit", "game_pwr", "raw_pwr", "speed", "field", "throw")
_PIT_TOOLS = ("fb", "sl", "cb", "ch", "cmd")


def matrix_path(side: str = "hit"):
    return DATA_DIR / ("xfv_pitcher_matrix.json" if side == "pit" else "xfv_hitter_matrix.json")


def live_matrix_path(side: str = "hit"):
    return DATA_DIR / ("xfv_live_pitcher_matrix.json" if side == "pit"
                       else "xfv_live_hitter_matrix.json")


def report_path(side: str = "hit"):
    return DATA_DIR / ("xfv_pitcher_dataset_report.json" if side == "pit"
                       else "xfv_dataset_report.json")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _rec_is_pitcher(rec):
    """True / False / None-unknown. AUDIT FIX 2026-07-14: trusting
    statline.is_pitcher==False routed ~20 real pitchers (nestor_cortes,
    zack_britton, michael_pineda, ...) into the HITTER cohort - their
    statline was a 0-AB batting-side fetch of a pitcher, and their real
    pitcher WAR labels then trained the hitter model against fully-imputed
    hitter features. A batting line with no AB/PA is uninformative; a
    record with no position either side-routes on real evidence or is
    dropped from the cohorts (None)."""
    sl = rec.get("statline") or {}
    if sl.get("is_pitcher") is True:
        return True
    informative_batting = False
    if sl.get("is_pitcher") is False:
        if (_f(sl.get("ab")) or 0) > 0 or (_f(sl.get("pa")) or 0) > 0:
            informative_batting = True
        # else: 0-AB batting-side fetch - fall through to position evidence
    pos = (rec.get("position") or "").upper()
    if any(p in pos for p in ("RHP", "LHP", "SP", "RP")) or pos == "P":
        return True
    if informative_batting:
        return False
    if not pos:
        return None          # no usable side evidence
    return False             # a real fielder position


def _side_match(rec, side: str) -> bool:
    isp = _rec_is_pitcher(rec)
    if isp is None:
        return False         # unknown side: excluded from BOTH cohorts
    return isp if side == "pit" else not isp


def _asof_point(rec, cutoff: str | None):
    """Latest points[] entry strictly before cutoff (debuted) or the final point
    (bust, cutoff=None). Returns the point dict or None."""
    pts = [p for p in (rec.get("points") or []) if p.get("snapshot_date")]
    if not pts:
        return None
    pts.sort(key=lambda p: p["snapshot_date"])
    if cutoff is None:
        return pts[-1]
    elig = [p for p in pts if p["snapshot_date"] < cutoff]
    return elig[-1] if elig else None


def _prior_features(rec, pt, side: str = "hit") -> dict:
    """Backbone prior + tools + disagreement, all as-of the decision point."""
    per = pt.get("per_source") or {}
    def src_fv(s):
        return _f((per.get(s) or {}).get("fv_published"))
    n_src = sum(1 for s, v in per.items()
                if s != "auto_detect" and _f(v.get("fv_published")) is not None)
    tools = pt.get("tools_consensus") or {}
    # As-of consensus-FV trajectory (momentum): net movement in consensus FV across
    # the player's snapshots up to AND INCLUDING the decision point. Leakage-free (only
    # points dated <= the decision date). A rising grade signals scouts catching up to
    # a breakout; orthogonal to the static FV level (the dominant feature).
    cutoff_date = pt.get("snapshot_date") or "9999"
    hist = sorted((p for p in (rec.get("points") or [])
                   if p.get("snapshot_date") and p["snapshot_date"] <= cutoff_date
                   and _f(p.get("consensus_fv_raw")) is not None),
                  key=lambda p: p["snapshot_date"])
    fv_trend = ((_f(hist[-1].get("consensus_fv_raw")) - _f(hist[0].get("consensus_fv_raw")))
                if len(hist) >= 2 else 0.0)
    out = {
        "consensus_fv_raw": _f(pt.get("consensus_fv_raw")),
        "consensus_fv_pre_shrinkage": _f(pt.get("consensus_fv_pre_shrinkage")),
        "fv_fangraphs": src_fv("fangraphs"),
        "fv_mlb_pipeline": src_fv("mlb_pipeline"),
        "n_sources": float(n_src),
        "fv_stddev": _f(pt.get("fv_stddev")),
        "fv_spread": _f(pt.get("fv_spread")),
        "fv_trend": fv_trend,
        "asof_date": pt.get("snapshot_date"),
    }
    for k in (_PIT_TOOLS if side == "pit" else _HIT_TOOLS):
        out[f"tool_{k}"] = _f(tools.get(k))
    return out


# Reliability shrink: a level-relative rate is shrunk toward 0 (league average) by its
# sample size, w = exposure / (exposure + K). A small-sample cup-of-coffee (e.g. a 3-PA
# AAA cameo with a fluky .98 OBP) collapses to ~0 instead of reading as elite; a full
# season is barely touched. Without this, cameos produced absurd grades (a 37-FV org bat
# read 53 eFV off a few AAA PA). K is roughly a quarter-season of exposure.
# A3 shrink loosen (owner-authorized 2026-07-24c, coordinated rebuild): reliability shrink
# K 100/80 -> 50/40 to trust MiLB rates more. Sweep found all 4 accuracy deltas non-negative
# (hit dSp +0.0005/dAUC +0.0008; pit dSp +0.0034/dAUC +0.0002), CI-neutral. This is a
# matrix-rebuild change: the lambda (A1) + alpha/weights (A2) were re-selected on the rebuilt
# matrix in the same coordinated pass. data/xfv_cap_sweep_eval.json.
_K_REL_PA = 50.0
_K_REL_BF = 40.0

# Static per-group level-median-ish priors, used ONLY when neither the
# contemporaneous nor the prior-season same-level norm exists (e.g. a brand-new
# season's DSL pitching norms have not been computed yet). Without a fallback,
# _season_rates subtracts 0, so a RAW rate masquerades as a level-relative edge --
# the exact bug that spiked new-season DSL arms (a 45% DSL K% read as a +45% edge).
_NORM_PRIOR = {
    "pitching": {"k_pct": 0.22, "bb_pct": 0.095, "era": 4.30},
    "hitting":  {"k_pct": 0.22, "bb_pct": 0.085, "iso": 0.135, "obp": 0.330, "ops": 0.715},
}


def _resolved_norms(season, level, group):
    """Contemporaneous same-level norms, falling back to the prior season's
    same-level norms, then to a static per-group prior -- NEVER an empty dict. A
    missing norm made _season_rates treat a raw rate as a level-relative edge,
    which is why un-normed DSL/complex arms spiked to the grade ceiling."""
    n = mh.league_norms(season, level, group, fetch=False) or {}
    if not n.get("k_pct"):
        n = mh.league_norms(season - 1, level, group, fetch=False) or {}
    if not n.get("k_pct"):
        n = dict(_NORM_PRIOR.get(group, {}))
    return n


def _season_rates(row, norms, side: str, shrink: bool = True):
    """Level-relative rate block + exposure (pa/bf) for one MiLB season, SAMPLE-SHRUNK.
    Side-specific: hitters k/bb/obp/iso vs level median; pitchers k/bb/era vs level median.
    Norms are season-and-level-specific (contemporaneous) so this is leakage-safe.

    shrink=False returns the RAW level-relative deviations with the reliability weight
    left OFF (w = 1). Only the B3 multi-level blend uses this, and it uses it because
    the shrink must be applied ONCE on the season's TOTAL exposure rather than once per
    level: weighting already-shrunk per-level rates would shrink twice and pull a
    full-season multi-level line toward the level mean harder than a single-level line
    of the same total size. Callers that take raw deviations own re-applying the weight.
    """
    if side == "pit":
        bf = _f(row.get("bf")) or 0.0
        so, bb, era = _f(row.get("so")), _f(row.get("bb")), _f(row.get("era"))
        w = (bf / (bf + _K_REL_BF) if bf else 0.0) if shrink else 1.0
        return {
            "k_rel": w * (((so / bf) - (norms.get("k_pct") or 0.0)) if so is not None and bf else 0.0),
            "bb_rel": w * (((bb / bf) - (norms.get("bb_pct") or 0.0)) if bb is not None and bf else 0.0),
            "era_rel": w * ((era - (norms.get("era") or 4.5)) if era is not None else 0.0),
            "exposure": bf, "rates_missing": 0.0 if bf else 1.0,
        }
    pa = _f(row.get("pa")) or 0.0
    so, bb = _f(row.get("so")), _f(row.get("bb"))
    slg, avg, obp, ops = _f(row.get("slg")), _f(row.get("avg")), _f(row.get("obp")), _f(row.get("ops"))
    iso = (slg - avg) if slg is not None and avg is not None else None
    w = (pa / (pa + _K_REL_PA) if pa else 0.0) if shrink else 1.0
    return {
        "k_rel": w * (((so / pa) - (norms.get("k_pct") or 0.0)) if so is not None and pa else 0.0),
        "bb_rel": w * (((bb / pa) - (norms.get("bb_pct") or 0.0)) if bb is not None and pa else 0.0),
        "iso_rel": w * ((iso - (norms.get("iso") or 0.0)) if iso is not None else 0.0),
        # Phase-1 sweep: peak-MiLB OBP is the strongest hitter edge BEYOND FV (+0.16
        # partial), under-priced by scouts. Not derivable from k/bb/iso (hits-on-base).
        "obp_rel": w * ((obp - (norms.get("obp") or 0.0)) if obp is not None and norms.get("obp") else 0.0),
        # RPS+ family: full OPS vs the level mean (the site's level-relative production
        # metric). Adds the batting-average / contact-quality component beyond OBP + ISO.
        "ops_rel": w * ((ops - (norms.get("ops") or 0.0)) if ops is not None and norms.get("ops") else 0.0),
        "exposure": pa, "rates_missing": 0.0 if pa else 1.0,
    }


# B3 multi-level blend (docs/efv-2026-07-30/B3_LEVEL_BLEND_GATE.md). DEFAULT OFF:
# flipping it rebuilds both matrices and moves the board, so it ships only on the
# pre-registered gate, and until then this module is byte-identical with it off.
#
# What it fixes: the level selection below walks DOWN from the highest level and stops
# at the first clearing the exposure floor, so exposure acts as a GATE and never as a
# WEIGHT. Measured on the 2026-07-30 live board, 151 of 701 multi-level hitters (22%)
# and 149 of 790 pitchers (19%) are scored on a level carrying LESS exposure than one
# being discarded, and ~100k plate appearances / batters faced are thrown away.
#
# The two arms are separate because they have very different blast radii. RATES blends
# the production signal, which is the accuracy claim. ANCHOR re-keys level_rank and
# age_rel_level onto the most-exposed level, which is a board-ordering change and is
# gated on its own.
LEVEL_BLEND_RATES = False
LEVEL_BLEND_ANCHOR_MOST_EXPOSED = False
# A level must clear this to join the blend at all, so a 3-PA cameo cannot drag a real
# season's rates. Deliberately far below the selection floor: the whole point is that
# a sub-floor level still carries information, it just should not dominate.
LEVEL_BLEND_MIN_EXPOSURE = 10.0


def _blend_level_rates(per_level: list[tuple[float, dict]], side: str) -> dict:
    """Exposure-weighted mean of RAW level-relative deviations, then ONE reliability
    shrink on the season's TOTAL exposure.

    per_level is [(exposure, raw_rates_dict)] with raw_rates_dict from
    _season_rates(..., shrink=False). Returns the same keys _season_rates returns, so
    the caller can drop it in where a single-level block would have gone.

    Shrinking once on the total is the whole design. Applying the per-level weight and
    then averaging would penalise a 200+150 PA split against a 350 PA single-level
    season of identical quality, which is the opposite of the defect being repaired.
    """
    keys = ("k_rel", "bb_rel", "era_rel") if side == "pit" \
        else ("k_rel", "bb_rel", "iso_rel", "obp_rel", "ops_rel")
    total = sum(e for e, _r in per_level)
    if total <= 0:
        return dict(per_level[0][1]) if per_level else {}
    out = {}
    for k in keys:
        out[k] = sum(e * (r.get(k) or 0.0) for e, r in per_level) / total
    w = total / (total + (_K_REL_BF if side == "pit" else _K_REL_PA))
    for k in keys:
        out[k] *= w
    out["exposure"] = total
    out["rates_missing"] = 0.0 if total else 1.0
    return out


def _consecutive_at_level(seasons: list[dict]) -> int:
    """How many consecutive seasons, counting back from the most recent, the player
    spent at the level he is currently on. `seasons` is newest-first.

    Consecutive rather than total on purpose: a player who was at AA in 2022, spent
    2023 at AAA, and is back at AA in 2024 is a different animal from one who has sat
    at AA for three straight years, and only the second is 'stalled'. Gaps in the
    season list (an injury year with no MiLB row) break the run, which is the
    conservative reading -- we did not observe him repeating.
    """
    if not seasons:
        return 0
    lvl = seasons[0].get("level")
    n, prev = 0, None
    for s in seasons:
        if s.get("level") != lvl:
            break
        yr = s.get("season")
        if prev is not None and prev - yr != 1:
            break            # a missing season is not an observed repeat
        n, prev = n + 1, yr
    return n


def _milb_features(mlbam, decision_year, birth_date, side: str = "hit",
                   annotate: bool = False, cutoff: str | None = None):
    """Translated production from the MiLB ladder strictly before the decision year
    (StatsAPI; season-and-level norms are contemporaneous = leakage-safe). Returns the
    FINAL pre-decision season's rates (the current-state read) PLUS multi-season PEAK
    production + season count (a fuller read than one snapshot -- a player who posted an
    elite K-BB% two levels ago carries that signal). Mirrors prospect_path._features +
    a clean age-rel-level.

    annotate=True (LIVE builds only) additionally surfaces the S-XLINE measurement
    annotation for the FINAL season row as base["xline_note"] (what the Statcast
    blend applied, efv_statcast_line.maybe_adjust_row). Display metadata only --
    efv_model._vec reads named feature keys, so the note never enters the model;
    training builds keep annotate=False so the labeled matrices stay byte-identical."""
    if not mlbam:
        return None
    group = "pitching" if side == "pit" else "hitting"
    minpa = 60 if side == "pit" else 50
    seasons = []
    # AS-OF REPAIR (2026-07-24, docs/EFV_FRONTIER_AUDIT.md). The loop must start at the
    # last MiLB season that had actually ENDED as of the decision date. `decision_year - 1`
    # is correct for DEBUTED rows (cutoff = the debut date) but wrong for BUSTS, whose
    # decision_year is last_list_year + 1 -- that admitted the SAME year as the final list
    # point. Measured on the shipped matrices: 582 bust rows (344 hit / 238 pit) did this,
    # 100% with a cutoff before October (33% / 25% before April, i.e. a season that had not
    # been played at all). Because a bust's label is 0 and the contaminating season is his
    # washout year, row timing became a label proxy: P(bust | milb_season == cutoff year)
    # was 95.6%. MiLB regular seasons end in September, so season Y is only readable once
    # the decision date is at/after Oct 1 of Y. min() keeps this STRICTLY subtractive -- it
    # can only remove leaked seasons, never add ones the old code did not already allow, so
    # every clean (debuted) row is byte-identical.
    first_season = decision_year - 1
    if cutoff:
        try:
            _cy, _cm = int(str(cutoff)[:4]), int(str(cutoff)[5:7])
            first_season = min(first_season, _cy if _cm >= 10 else _cy - 1)
        except (ValueError, IndexError):
            pass
    for season in range(first_season, 2013, -1):
        rows = [r for r in (mh.player_index(season, group).get(int(mlbam)) or [])
                if r.get("level") != "MLB"]
        if not rows:
            continue
        # PRIMARY level = the highest level where the player got meaningful exposure that
        # season (not a cup-of-coffee). Sets level_rank + age_rel_level so a cameo can't
        # make a 19-yo look like an established AAA bat. Rates come from this level too,
        # and are sample-shrunk on top.
        present = sorted({r.get("level") for r in rows if r.get("level") in _LEVEL_RANK},
                         key=lambda lv: -_LEVEL_RANK[lv])
        if not present:
            continue
        level, row = None, None
        for lv in present:
            lr = mh.level_row(rows, lv, group)
            exp = (_f(lr.get("bf")) if side == "pit" else _f(lr.get("pa"))) or 0.0
            if exp >= minpa:
                level, row = lv, lr
                break
        if level is None:
            # No level cleared the exposure threshold -> use the MOST-EXPOSED level (the
            # player's real home), NOT the highest. A cup-of-coffee at a high level (e.g. an
            # 18-yo's 3-PA AA cameo) must not set level_rank / age_rel_level as if he were
            # established there: those level features are NOT exposure-shrunk the way the rate
            # features are, so a cameo at a high level otherwise manufactures a huge
            # young-for-level + level-reached boost off zero real playing time.
            def _lv_exp(lv):
                lr = mh.level_row(rows, lv, group)
                return (_f(lr.get("bf")) if side == "pit" else _f(lr.get("pa"))) or 0.0
            level = max(present, key=_lv_exp)
            row = mh.level_row(rows, level, group)
        elif LEVEL_BLEND_ANCHOR_MOST_EXPOSED and len(present) > 1:
            # B3 ANCHOR arm: re-key the level features onto where the player actually
            # played most, not merely the highest rung he cleared the floor at. Gated
            # separately from the RATES arm because this is what moves board ORDER:
            # level_rank and age_rel_level are not exposure-shrunk, so a 51-PA A+ stint
            # currently sets them as if the player were established there.
            def _lv_exp2(lv):
                lr = mh.level_row(rows, lv, group)
                return (_f(lr.get("bf")) if side == "pit" else _f(lr.get("pa"))) or 0.0
            level = max(present, key=_lv_exp2)
            row = mh.level_row(rows, level, group)
        norms = _resolved_norms(season, level, group)
        # S-XLINE (docs/efv-2026-07-23/GATES.md): AAA 2023+ rows may get a Statcast
        # expected-stat blend before the level-relative conversion; uncovered rows
        # and disabled flags return the row object unchanged (byte-identical path).
        if _xline is not None:
            row = _xline.maybe_adjust_row(row, mlbam, season, level, side)
        # W2 PARK-LINE (docs/wills-2026-07-23/GATES.md): 2021+ seasons with a
        # dominant affiliate and a mapped venue factor may get a park
        # neutralization before the level-relative conversion; uncovered rows
        # and disabled flags return the row object unchanged (byte-identical).
        if _parkline is not None:
            row = _parkline.maybe_adjust_row(row, mlbam, season, level, side)
        rates = _season_rates(row, norms, side)
        # B3: blend the season's OTHER levels into the rate block. `level` (and so
        # level_rank / age_rel_level) stays where the selection put it unless the
        # ANCHOR arm is also on, so the two arms can be gated independently.
        if LEVEL_BLEND_RATES and len(present) > 1:
            per_level = []
            for lv in present:
                lr = mh.level_row(rows, lv, group)
                e = (_f(lr.get("bf")) if side == "pit" else _f(lr.get("pa"))) or 0.0
                if e < LEVEL_BLEND_MIN_EXPOSURE:
                    continue
                if _xline is not None:
                    lr = _xline.maybe_adjust_row(lr, mlbam, season, lv, side)
                if _parkline is not None:
                    lr = _parkline.maybe_adjust_row(lr, mlbam, season, lv, side)
                per_level.append(
                    (e, _season_rates(lr, _resolved_norms(season, lv, group), side,
                                      shrink=False)))
            if len(per_level) > 1:
                blended = _blend_level_rates(per_level, side)
                if annotate and rates.get("_xline_note"):
                    blended["_xline_note"] = rates["_xline_note"]
                rates = blended
        if annotate and row.get("_xline_note"):
            # S-XLINE annotation rides the season dict (local) so the final
            # season's note can surface on the returned base below.
            rates["_xline_note"] = row["_xline_note"]
        age = _resolve_season_age(row.get("age"), birth_date, season)
        rates.update({"season": season, "level": level,
                      "level_rank": float(_LEVEL_RANK[level]), "age": age})
        seasons.append(rates)
    if not seasons:
        return None

    final = seasons[0]                 # most recent (descending loop)
    level, age = final["level"], final["age"]
    # age-relative-to-level, bounded to +/-AGE_REL_CAP: the model term is linear, so an
    # extreme (a 19-yo cup-of-coffee in AAA -> -5) would over-extrapolate the
    # young-for-level boost.
    age_rel = (age - _TYPICAL_LEVEL_AGE[level]) if age is not None else None
    if age_rel is not None:
        age_rel = _age_rel_bound(age_rel)
    base = {
        "milb_season": final["season"], "milb_level": level,
        "level_rank": final["level_rank"],
        "stale": float(decision_year - 1 - final["season"]),
        "age": age if age is not None else 23.0,
        "age_missing": 1.0 if age is None else 0.0,
        "age_rel_level": age_rel if age_rel is not None else 0.0,
        "n_milb_seasons": float(len(seasons)),
        # E1 (docs/efv-2026-07-30/E1_REPEAT_LEVEL_GATE.md): consecutive seasons the
        # player has now spent at his CURRENT level, counting back from the most recent.
        # 1 = arrived this year. 3 = a third year on the same rung.
        #
        # This is NOT n_milb_seasons. That one counts total seasons anywhere and is a
        # declared suppressor precisely because, holding level_rank and age fixed, more
        # seasons means more seasons spent REACHING the level. This counts the stall
        # itself, which nothing in the feature set currently sees: only the final
        # season's rates enter, so a player repeating a level on the back of a collapse
        # reads exactly like a player who just arrived and is hitting well.
        # Always computed (a matrix key is free); it only enters the model when the
        # flag below is on.
        "seasons_at_level": float(_consecutive_at_level(seasons)),
    }
    keep = ("k_rel", "bb_rel", "era_rel", "rates_missing") if side == "pit" \
        else ("k_rel", "bb_rel", "iso_rel", "obp_rel", "ops_rel", "rates_missing")
    base.update({k: final[k] for k in keep})
    if annotate and final.get("_xline_note"):
        # Measurement note for the CURRENT (final) season only: what S-XLINE
        # applied to the line the grade actually reads. Annotation, not a factor.
        base["xline_note"] = final["_xline_note"]

    # Multi-season PEAK across exposure-qualified seasons (best sustained production,
    # not just the latest line). Direction = the productive extreme of each rate.
    minpa = 60 if side == "pit" else 50
    qual = [s for s in seasons if (s.get("exposure") or 0) >= minpa] or seasons
    if side == "pit":
        base["peak_k_rel"] = max(s["k_rel"] for s in qual)
        base["peak_bb_rel"] = min(s["bb_rel"] for s in qual)   # fewer walks = better
    else:
        base["peak_obp_rel"] = max(s["obp_rel"] for s in qual)
        base["peak_k_rel"] = min(s["k_rel"] for s in qual)     # fewer Ks = better
        base["peak_iso_rel"] = max(s["iso_rel"] for s in qual)
        base["peak_ops_rel"] = max(s["ops_rel"] for s in qual)
    # A2: production TRAJECTORY -- latest vs earliest level-relative production (the primary
    # rate per side). Positive = improving toward the decision point. Leakage-safe (all
    # pre-decision). 0 when only one season is on record.
    metric = "k_rel" if side == "pit" else "ops_rel"
    base["prod_trend"] = (final[metric] - seasons[-1][metric]) if len(seasons) >= 2 else 0.0
    return base


def _label_6yr(seasons: dict, debut_year: int):
    """(target_resolved, target_censored, censored_flag, weight, observed_seasons).
    seasons: {int year: war}."""
    window = [debut_year + i for i in range(TARGET_SEASONS)]
    observed = [y for y in window if y <= RESOLVED_THROUGH]
    obs_sum = round(sum(seasons.get(y, 0.0) for y in observed), 3)
    n_obs = len(observed)
    full_resolved = (debut_year + TARGET_SEASONS - 1) <= RESOLVED_THROUGH
    if full_resolved:
        return obs_sum, obs_sum, False, 1.0, n_obs
    # right-censored: project the unobserved tail at the observed per-season rate
    rate = obs_sum / n_obs if n_obs else 0.0
    n_missing = TARGET_SEASONS - n_obs
    censored_target = round(obs_sum + n_missing * rate, 3)
    weight = round(n_obs / TARGET_SEASONS, 3)
    return obs_sum, censored_target, True, weight, n_obs


# ---------------------------------------------------------------------------
# join sidecars (draft / bonus / injury) from the DB
# ---------------------------------------------------------------------------

def _load_sidecars(player_keys: set[str]):
    acq, il = {}, {}
    with storage.connect() as con:
        ph = ",".join("?" for _ in player_keys)
        pk = tuple(player_keys)
        for r in con.execute(
                f"SELECT player_key, method, pick_overall, bonus_usd, year FROM acquisitions "
                f"WHERE player_key IN ({ph})", pk):
            acq[r["player_key"]] = {"pick_overall": r["pick_overall"],
                                    "bonus_usd": r["bonus_usd"], "method": r["method"],
                                    "year": r["year"]}
        for r in con.execute(
                f"SELECT player_key, since FROM il_history WHERE player_key IN ({ph})", pk):
            il.setdefault(r["player_key"], []).append(r["since"])
    return acq, il


# Career-terminal transactions (AUDIT FIX 2026-07-15): a lifetime DEI ban or a
# retirement means the player plays NONE of the label window's unobserved
# seasons, so the censored extrapolation invents WAR they cannot earn
# (tucupita_marcano's lifetime gambling ban extrapolated a 2026 season he is
# barred from playing). Raw payloads are the ONLY source: stats.py
# derive_transactions drops DEI (unmapped) and maps RET to rule_5_return.
# NB bare "signed" is NOT activating - it substring-matches "assigned", and
# Marcano's post-ban winter-league assignment rows would falsely clear him.
_TERMINAL_ACTIVATING = ("selected the contract", "purchased the contract",
                        "recalled", "reinstated", "activated")


def _terminal_date(txs: list[dict]) -> str | None:
    """Date of the last career-terminal transaction (DEI ban / retirement)
    with NO later activating move. One-year bans (Saalfrank, Groome) are
    cleared by their later reinstate/activate/recall rows."""
    terminal, activating = [], []
    for tx in txs or []:
        d = tx.get("date") or ""
        if not d:
            continue
        code = (tx.get("type_code") or "").upper()
        desc = (tx.get("description") or "").lower()
        if code == "DEI" or (code == "RET" and "retired" in desc):
            terminal.append(d)
        elif any(a in desc for a in _TERMINAL_ACTIVATING):
            activating.append(d)
    if not terminal:
        return None
    term = max(terminal)
    return None if any(a > term for a in activating) else term


def _terminal_resolves(tdate) -> bool:
    """A terminal event fully resolves a censored window only when the player
    cannot have logged WAR the window has not observed yet: any event through
    RESOLVED_THROUGH, or a pre-season (on/before Apr 1) event in the first
    unresolved season. A mid-season CURRENT_SEASON retirement could strand
    real not-yet-resolved WAR, so those rows stay censored until the season
    resolves."""
    try:
        y = int(str(tdate)[:4])
    except (TypeError, ValueError):
        return False
    return y <= RESOLVED_THROUGH or (y == RESOLVED_THROUGH + 1
                                     and str(tdate)[5:10] <= "04-01")


def _load_terminal_dates(player_keys: set[str]) -> dict[str, str]:
    """{player_key: terminal_date} from the raw player_transactions payloads."""
    term = {}
    with storage.connect() as con:
        ph = ",".join("?" for _ in player_keys)
        for r in con.execute(
                f"SELECT player_key, payload_json FROM player_transactions "
                f"WHERE player_key IN ({ph})", tuple(player_keys)):
            try:
                txs = json.loads(r["payload_json"]) or []
            except ValueError:
                continue
            td = _terminal_date(txs)
            if td:
                term[r["player_key"]] = td
    return term


# --- F1 bust-loop guard (audit 2026-07-24): MLB exposure disqualifies a bust --
_MLB_EXPOSED_MEMO: set[int] | None = None


def _mlb_exposed_ids() -> set[int]:
    """mlbam ids carrying ANY MLB (sport-1) stat line in the local StatsAPI
    caches, 2014-present (fetch=False keeps this offline-safe; the caches are
    warmed by the pipeline). The bust pool must never contain these ids: an
    inactive.json record with debut_date=None but real MLB exposure
    (adolis_garcia 3,378 PA, kodai_senga 1,390 BF, ...) is an upstream
    debut-detector miss, not a never-MLB 0-WAR bust."""
    global _MLB_EXPOSED_MEMO
    if _MLB_EXPOSED_MEMO is None:
        ids: set[int] = set()
        for season in range(2014, CURRENT_SEASON + 1):
            for group in ("hitting", "pitching"):
                for r in mh.season_splits(1, season, group, fetch=False):
                    m = r.get("mlbam")
                    if m:
                        ids.add(int(m))
        _MLB_EXPOSED_MEMO = ids
    return _MLB_EXPOSED_MEMO


def _cohort_flags(method, year, birth_date) -> tuple[float, float]:
    """Acquisition-cohort indicators used as model features. is_ifa = signed as an
    international free agent; is_college = drafted out of college (age>=21 in the draft
    year, the leakage-free split the eFV sweep validated). HS draftees / unknown are (0,0).
    The ridge re-centers each cohort's intercept -> sharper CROSS-tier ordering (OOS gain:
    hit +0.024, pit cohort-interactions +0.011)."""
    is_ifa = 1.0 if method == "international_fa" else 0.0
    is_college = 0.0
    if method == "draft" and year and birth_date:
        try:
            if int(year) - int(str(birth_date)[:4]) >= 21:
                is_college = 1.0
        except (ValueError, TypeError):
            pass
    return is_ifa, is_college


def _injury_features(il_dates, cutoff: str | None):
    """IL stints recorded strictly before the decision date."""
    if not il_dates:
        return {"il_stints_pre": 0.0, "il_any_pre": 0.0}
    pre = [d for d in il_dates if d and (cutoff is None or d < cutoff)]
    return {"il_stints_pre": float(len(pre)), "il_any_pre": 1.0 if pre else 0.0}


# ---------------------------------------------------------------------------
# cohort
# ---------------------------------------------------------------------------

def build_matrix(side: str = "hit"):
    is_pit = side == "pit"
    debuts = json.loads((DATA_DIR / "debuts.json").read_text(encoding="utf-8"))
    inact = json.loads((DATA_DIR / "inactive.json").read_text(encoding="utf-8"))

    with storage.connect() as con:
        cw = {}
        for r in con.execute("SELECT player_key, payload_json FROM career_war"):
            try:
                seasons = (json.loads(r["payload_json"]) or {}).get("seasons") or {}
            except ValueError:
                continue
            cw[r["player_key"]] = {int(y): float(w) for y, w in seasons.items()}

    acct = {"debuted_seen": 0, "debuted_hitter": 0, "debuted_no_pre_fv": 0,
            "debuted_no_war": 0, "debuted_kept": 0,
            "bust_seen": 0, "bust_hitter": 0, "bust_no_fv": 0, "bust_kept": 0,
            "bust_recent_flagged": 0,
            "bust_mlb_exposure_rerouted": 0, "bust_mlb_exposure_dropped": 0}
    rows = []

    # --- debuted ---
    for rec in debuts:
        acct["debuted_seen"] += 1
        pk, dd, mlbam = rec.get("player_key"), rec.get("debut_date"), rec.get("mlbam_id")
        if not (pk and dd):
            continue
        dy = int(dd[:4])
        if dy not in DEBUT_YEARS or not _side_match(rec, side):
            continue
        acct["debuted_hitter"] += 1
        pt = _asof_point(rec, dd)
        if pt is None or _f(pt.get("consensus_fv_raw")) is None:
            acct["debuted_no_pre_fv"] += 1
            continue
        seasons = cw.get(pk)
        if not seasons:
            acct["debuted_no_war"] += 1
            continue
        # LABEL-INTEGRITY guards (audit 2026-07-14):
        # (a) veteran RE-appearance mislabeled as a debut: MLB WAR seasons
        #     strictly BEFORE the claimed debut year mean the "debut" is a
        #     journeyman resurfacing (rougned_odor "2023" with 2016+ WAR) -
        #     the 6yr window would attach a decline-tail label to a
        #     prospect-era anchor. 41+ provable rows. Drop.
        if min(seasons) < dy:
            acct["debuted_veteran_dropped"] = acct.get("debuted_veteran_dropped", 0) + 1
            continue
        # (b) postseason-only "debut" (kirilloff/mcclanahan 2020): no
        #     regular-season line in the debut year burns a 0-WAR window
        #     season - re-date a Sept/Oct debut to the first WAR season.
        #     A gap of MORE than one year is a data hole (e.g. the
        #     career_war sliding-window decay), not a postseason debut: drop.
        if min(seasons) == dy + 1 and dd[5:7] >= "09":
            dy = min(seasons)
            if dy not in DEBUT_YEARS:
                continue
        elif min(seasons) > dy:
            acct["debuted_war_gap_dropped"] = acct.get("debuted_war_gap_dropped", 0) + 1
            continue
        t_res, t_cens, cflag, w, n_obs = _label_6yr(seasons, dy)
        row = {"player_key": pk, "kind": "debuted", "debut_year": dy,
               "is_pitcher": is_pit, "cutoff": dd,
               "target_resolved": t_res, "target_censored": t_cens,
               "censored": cflag, "weight": w, "observed_seasons": n_obs,
               "mlbam_id": mlbam, "birth_date": rec.get("birth_date"),
               "position": rec.get("position")}
        row.update(_prior_features(rec, pt, side))
        row["milb"] = _milb_features(mlbam, dy, rec.get("birth_date"), side, cutoff=dd)
        # AUDIT FIX 2026-07-14: distinguish "no pro track record" from "data
        # cannot exist" - the StatsAPI cache floor is 2014 and the 2011-2015
        # backfills mostly lack mlbam ids, so 100% of 2011-2014 debut rows
        # fired milb_missing for availability reasons, diluting the
        # coefficient whose job is spotting imputed-zero production.
        # milb_unavailable rows stay NEUTRAL in efv_model._vec.
        if row["milb"] is None and (dy <= 2015 or not mlbam):
            row["milb_unavailable"] = True
        acct["debuted_kept"] += 1
        rows.append(row)

    # --- busts (never reached MLB) ---
    mlb_ids = _mlb_exposed_ids()
    debuted_keys = {r["player_key"] for r in rows}
    for rec in inact:
        acct["bust_seen"] += 1
        pk = rec.get("player_key")
        if not pk or rec.get("debut_date"):     # debut_date set => not a never-MLB bust
            continue
        if not _side_match(rec, side):
            continue
        acct["bust_hitter"] += 1
        # F1 bust-loop guard (audit 2026-07-24): a record whose mlbam id has
        # real MLB (sport-1) stat lines, or whose player_key already carries
        # career_war seasons, is NOT a never-MLB bust - the hardcoded 0.0
        # label below would train a full-weight bust label against an actual
        # MLB career (adolis_garcia: 3,378 MLB PA trained as a 0-WAR bust).
        # Honest repair: when career_war holds the player's real seasons and
        # the debut year is trainable, route through the debuted machinery
        # with the REAL first-6yr label (cutoff = Jan 1 of the debut year,
        # strictly pre-outcome; a debut cannot predate the first list point,
        # which screens career_war name collisions). Otherwise exclude from
        # training with an accounting counter - never a fabricated label.
        mlbam = rec.get("mlbam_id")
        cw_seasons = cw.get(pk)
        if (mlbam and int(mlbam) in mlb_ids) or cw_seasons:
            dy = min(cw_seasons) if cw_seasons else None
            first_list = min((p["snapshot_date"][:4]
                              for p in (rec.get("points") or [])
                              if p.get("snapshot_date")), default=None)
            if (dy is not None and dy in DEBUT_YEARS and pk not in debuted_keys
                    and first_list and first_list.isdigit()
                    and dy >= int(first_list)):
                cutoff = f"{dy}-01-01"    # true debut date unknown: anchor pre-debut-season
                rpt = _asof_point(rec, cutoff)
                if rpt is not None and _f(rpt.get("consensus_fv_raw")) is not None:
                    t_res, t_cens, cflag, w, n_obs = _label_6yr(cw_seasons, dy)
                    row = {"player_key": pk, "kind": "debuted", "debut_year": dy,
                           "is_pitcher": is_pit, "cutoff": cutoff,
                           "target_resolved": t_res, "target_censored": t_cens,
                           "censored": cflag, "weight": w, "observed_seasons": n_obs,
                           "mlbam_id": mlbam, "birth_date": rec.get("birth_date"),
                           "position": rec.get("position"),
                           "rerouted_from_bust": True}
                    row.update(_prior_features(rec, rpt, side))
                    row["milb"] = _milb_features(mlbam, dy, rec.get("birth_date"),
                                                side, cutoff=cutoff)
                    if row["milb"] is None and (dy <= 2015 or not mlbam):
                        row["milb_unavailable"] = True
                    acct["bust_mlb_exposure_rerouted"] += 1
                    debuted_keys.add(pk)
                    rows.append(row)
                    continue
            acct["bust_mlb_exposure_dropped"] += 1
            log.warning("bust_mlb_exposure: %s (mlbam %s) has MLB exposure - "
                        "excluded from the bust pool", pk, mlbam)
            continue
        pt = _asof_point(rec, None)
        if pt is None or _f(pt.get("consensus_fv_raw")) is None:
            acct["bust_no_fv"] += 1
            continue
        last_date = pt.get("snapshot_date") or ""
        recent = last_date[:4] >= "2024"     # may still be developing
        if recent:
            acct["bust_recent_flagged"] += 1
        cutoff = (last_date or None)
        row = {"player_key": pk, "kind": "bust", "debut_year": None,
               "is_pitcher": is_pit, "cutoff": cutoff,
               "target_resolved": 0.0, "target_censored": 0.0,
               "censored": False, "weight": 0.5 if recent else 1.0,
               "observed_seasons": TARGET_SEASONS, "bust_recent": recent,
               "mlbam_id": rec.get("mlbam_id"), "birth_date": rec.get("birth_date"),
               "position": rec.get("position")}
        row.update(_prior_features(rec, pt, side))
        dec_year = (int(last_date[:4]) + 1) if last_date[:4].isdigit() else CURRENT_SEASON
        row["milb"] = _milb_features(rec.get("mlbam_id"), dec_year,
                                     rec.get("birth_date"), side, cutoff=cutoff)
        # same availability distinction as the debuted loop
        if row["milb"] is None and (dec_year <= 2015 or not rec.get("mlbam_id")):
            row["milb_unavailable"] = True
        acct["bust_kept"] += 1
        rows.append(row)

    # sidecars
    acq, il = _load_sidecars({r["player_key"] for r in rows})
    term = _load_terminal_dates({r["player_key"] for r in rows})
    for r in rows:
        a = acq.get(r["player_key"]) or {}
        r["pick_overall"] = a.get("pick_overall")
        r["bonus_usd"] = a.get("bonus_usd")
        r["is_ifa"], r["is_college"] = _cohort_flags(a.get("method"), a.get("year"), r.get("birth_date"))
        r.update(_injury_features(il.get(r["player_key"]), r["cutoff"]))
        # AUDIT FIX 2026-07-15: consume career-terminal transactions. A banned
        # or retired player resolves at the observed sum with full weight
        # instead of extrapolating seasons they cannot play; a recent-bust
        # retiree is no longer "may still be developing".
        td = term.get(r["player_key"])
        if td:
            if r["kind"] == "debuted" and r["censored"] and _terminal_resolves(td):
                r["target_censored"] = r["target_resolved"]
                r["censored"] = False
                r["weight"] = 1.0
                r["observed_seasons"] = TARGET_SEASONS
                r["terminal_resolved"] = td
                acct["debuted_terminal_resolved"] = acct.get("debuted_terminal_resolved", 0) + 1
            elif r["kind"] == "bust" and r.get("bust_recent"):
                r["weight"] = 1.0
                r["bust_recent"] = False
                r["terminal_resolved"] = td
                acct["bust_recent_flagged"] -= 1
                acct["bust_terminal_resolved"] = acct.get("bust_terminal_resolved", 0) + 1

    return rows, acct


# ---------------------------------------------------------------------------
# live cohort -- the CURRENT active prospect board (no labels; for scoring)
# ---------------------------------------------------------------------------

def build_live_matrix(side: str = "hit"):
    """Feature rows for the CURRENT active prospect board so the trained model can
    score the players the site actually shows. Same as-of feature construction as
    build_matrix (the SAME _prior_features / _milb_features / sidecar helpers) but
    sourced from the live board (data/timeseries.json `players[]`), with the
    decision point = the latest snapshot (cutoff=None) and NO outcome label.

    Reads timeseries.json (the export output) so the eFV grades line up exactly with
    the consensus FV the site displays. Captures age + eta_years + the engine's
    consensus surplus so the scorer can price eFV vs consensus on identical timing.
    Run AFTER the site export (run_monthly / build_site) has written timeseries.json.
    """
    is_pit = side == "pit"
    ts_path = DATA_DIR / "timeseries.json"
    if not ts_path.exists():
        log.warning("timeseries.json absent -- run the site export first; live matrix empty")
        return [], {"live_seen": 0, "live_side": 0, "live_kept": 0, "live_no_fv": 0}

    payload = json.loads(ts_path.read_text(encoding="utf-8"))
    players = payload.get("players") or []
    acct = {"live_seen": 0, "live_side": 0, "live_kept": 0, "live_no_fv": 0}
    rows = []
    for rec in players:
        acct["live_seen"] += 1
        pk = rec.get("player_key")
        if not pk or not _side_match(rec, side):
            continue
        acct["live_side"] += 1
        pt = _asof_point(rec, None)        # latest snapshot = current grade
        if pt is None or _f(pt.get("consensus_fv_raw")) is None:
            acct["live_no_fv"] += 1
            continue
        surplus = rec.get("surplus") or {}
        il = rec.get("il_status") or {}
        hp = rec.get("health_profile") or {}
        row = {"player_key": pk, "kind": "active", "debut_year": None,
               "is_pitcher": is_pit, "cutoff": None,
               "mlbam_id": rec.get("mlbam_id"), "birth_date": rec.get("birth_date"),
               "position": rec.get("position"),
               "age_now": _f(rec.get("age")),
               "eta_years": _f(surplus.get("eta_years")),
               "consensus_surplus_mm": _f(surplus.get("value_mm")),
               # current injury signals (for the live injury penalty)
               "il_on": 1 if il.get("is_on_il") else 0,
               "il_type": il.get("type"),
               "il_days_12mo": _f(hp.get("il_days_12mo")) or 0.0,
               "il_stints_12mo": _f(hp.get("il_stints_12mo")) or 0.0,
               "is_post_tj": bool(hp.get("is_post_tj")),
               # Statcast+ (batted-ball quality / Stuff+) -- current-state only, upper-level;
               # a live overlay tilt (no historical depth to train on). 100 = average.
               "statcast_plus": _f(rec.get("statcast_plus"))}
        row.update(_prior_features(rec, pt, side))
        # E-STALE: decay the MODEL anchor for long-unlisted players (the Nathan
        # Hickey class: FV frozen at a 2024 list while stats/age are current).
        # fv_effective feeds _vec's fv feature + the scorer's consensus blend
        # leg; consensus_fv_raw is untouched so every DISPLAY of consensus
        # stays the true consensus.
        _disc = _stale_anchor_discount(row.get("asof_date"), row.get("consensus_fv_raw"))
        row["anchor_stale_discount"] = round(_disc, 2)
        row["fv_effective"] = round(row["consensus_fv_raw"] - _disc, 2) if _disc else row["consensus_fv_raw"]
        # LIVE scoring includes the CURRENT season (no leakage -- current production IS the
        # signal). decision_year = CURRENT_SEASON+1 so _milb_features' range starts at the
        # current year. (Training stays strictly pre-outcome.) Without this, a 2026 breakout
        # like Arias's .990 OPS was ignored and stale 2025 stats drove the grade.
        row["milb"] = _milb_features(rec.get("mlbam_id"), CURRENT_SEASON + 1,
                                     rec.get("birth_date"), side,
                                     annotate=True)   # S-XLINE note, live only
        rows.append(row)
        acct["live_kept"] += 1

    acq, il = _load_sidecars({r["player_key"] for r in rows})
    for r in rows:
        a = acq.get(r["player_key"]) or {}
        r["pick_overall"] = a.get("pick_overall")
        r["bonus_usd"] = a.get("bonus_usd")
        r["is_ifa"], r["is_college"] = _cohort_flags(a.get("method"), a.get("year"), r.get("birth_date"))
        r.update(_injury_features(il.get(r["player_key"]), None))
    return rows, acct


def build_live(persist: bool = True, side: str = "hit") -> dict:
    rows, acct = build_live_matrix(side)
    rep = {"generated_at": date.today().isoformat(),
           "scope": f"LIVE {'PITCHERS' if side == 'pit' else 'HITTERS'} (active board)",
           "accounting": acct, "n_rows": len(rows),
           "milb_coverage": _coverage(rows, "level_rank", sub="milb"),
           "mlbam_coverage": _coverage(rows, "mlbam_id")}
    if persist:
        live_matrix_path(side).write_text(json.dumps(rows, indent=0), encoding="utf-8")
        log.info("wrote %s (%d rows)", live_matrix_path(side), len(rows))
    return rep


# ---------------------------------------------------------------------------
# coverage + baseline
# ---------------------------------------------------------------------------

def _coverage(rows, field, sub=None):
    n = 0
    for r in rows:
        v = (r.get(sub) or {}).get(field) if sub else r.get(field)
        if v is not None:
            n += 1
    return n


def _baseline(rows, target_key, fv_key="consensus_fv_raw"):
    xs, ys = [], []
    for r in rows:
        fv, t = r.get(fv_key), r.get(target_key)
        if fv is not None and t is not None:
            xs.append(fv); ys.append(t)
    return {"n": len(xs), "spearman": _spearman(xs, ys) if len(xs) >= 8 else None}


def run(persist: bool = True, side: str = "hit") -> dict:
    rows, acct = build_matrix(side)
    debuted = [r for r in rows if r["kind"] == "debuted"]
    busts = [r for r in rows if r["kind"] == "bust"]
    resolved_debuted = [r for r in debuted if not r["censored"]]
    full_resolved = resolved_debuted + [b for b in busts if not b.get("bust_recent")]
    full_censored = debuted + [b for b in busts if not b.get("bust_recent")]

    feat_cov = {k: f"{_coverage(rows, k)}/{len(rows)}"
                for k in ("consensus_fv_raw", "fv_fangraphs", "fv_mlb_pipeline",
                          "fv_stddev", "tool_hit", "tool_game_pwr", "pick_overall",
                          "bonus_usd")}
    milb_cov = {k: f"{_coverage(rows, k, sub='milb')}/{len(rows)}"
                for k in ("level_rank", "age_rel_level", "k_rel",
                          "era_rel" if side == "pit" else "iso_rel")}

    baselines = {
        "debuted_only_resolved": _baseline(resolved_debuted, "target_resolved"),
        "full_pool_resolved": _baseline(full_resolved, "target_resolved"),
        "full_pool_km_censored": _baseline(full_censored, "target_censored"),
        "debuted_km_censored": _baseline(debuted, "target_censored"),
    }
    # WAR distribution sanity
    res_t = sorted(r["target_resolved"] for r in resolved_debuted)
    def pct(v, p):
        return round(v[int(p * (len(v) - 1))], 2) if v else None

    report = {
        "generated_at": date.today().isoformat(),
        "scope": (f"{'PITCHERS' if side == 'pit' else 'HITTERS'}; debut "
                  f"{DEBUT_YEARS[0]}-{DEBUT_YEARS[-1]} + never-MLB bust pool"),
        "target": f"first-{TARGET_SEASONS}-season summed bWAR; resolved<= {RESOLVED_THROUGH}",
        "no_model": True,
        "accounting": acct,
        "counts": {
            "rows_total": len(rows), "debuted": len(debuted), "busts": len(busts),
            "resolved_debuted": len(resolved_debuted),
            "censored_debuted": len(debuted) - len(resolved_debuted),
            "bust_recent_excluded_from_label": acct["bust_recent_flagged"],
        },
        "feature_coverage": feat_cov,
        "milb_feature_coverage": milb_cov,
        "war_distribution_resolved_debuted": {
            "n": len(res_t), "p10": pct(res_t, .10), "p50": pct(res_t, .50),
            "p90": pct(res_t, .90), "mean": round(statistics.mean(res_t), 2) if res_t else None,
            "max": round(max(res_t), 2) if res_t else None,
            "pct_under_0.5": round(sum(1 for v in res_t if v < 0.5) / len(res_t), 3) if res_t else None,
        },
        "baseline_consensus_fv_spearman": baselines,
        "baseline_note": ("THE bar. consensus_fv_raw rank vs realized first-6yr bWAR. "
                          "debuted-only ~ the 0.38 Phase-1 sweep figure; full-pool dilutes "
                          "with busts. Sensitivity = resolved vs KM-censored."),
    }
    if persist:
        mp, rp = matrix_path(side), report_path(side)
        mp.write_text(json.dumps(rows, indent=0), encoding="utf-8")
        rp.write_text(json.dumps(report, indent=1), encoding="utf-8")
        log.info("wrote %s (%d rows) + %s", mp, len(rows), rp)
    return report


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    _side = "pit" if "--pit" in sys.argv else "hit"
    rep = run(side=_side)
    print("accounting:", json.dumps(rep["accounting"]))
    print("counts:", json.dumps(rep["counts"]))
    print("feature coverage:", json.dumps(rep["feature_coverage"]))
    print("milb coverage:", json.dumps(rep["milb_feature_coverage"]))
    print("WAR dist (resolved debuted):", json.dumps(rep["war_distribution_resolved_debuted"]))
    print("BASELINE consensus-FV Spearman:")
    for k, v in rep["baseline_consensus_fv_spearman"].items():
        print(f"  {k:28s} n={v['n']:5d}  spearman={v['spearman']}")
