# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV for UNGRADED prospects -- a production-only leading indicator for the players the
scouting sources have NOT graded yet (the DSL/CPX/A breakout bats + arms the prospect
cycle is behind on, plus the org-depth fillers).

THE PROBLEM the flagship eFV model can't touch: it is anchored on consensus FV (the
dominant feature) and ABSTAINS on players with no source grade. But ~6,300 players on
40-man org rosters have real MiLB production and zero source FV -- and among them are
the genuine sleepers (a 18-yo posting an elite line in the DSL) that eFV could flag a
cycle ahead of the sources.

THE MODEL (deliberately separate, NOT the flagship): a dedicated NO-FV ridge -- the same
production substrate (level-relative k/bb/obp/iso vs contemporaneous norms, age-for-level,
multi-season peaks, track record) the flagship uses, but WITHOUT the consensus-FV anchor,
re-fit so the production features carry the full WAR signal instead of a partial effect.
Imputing a constant FV into the shipped model was tested and FAILS (the FV weight is so
dominant that production-only predictions floor at the -2 WAR clamp; degenerate). The
no-FV fit is the fix.

  VALIDATION (forward-chained on the labeled matrix, low-minors DSL/CPX/A cohort -- the
  target population; data/xfv_ungraded_eval.json):
    HITTERS  keep level_rank: low-minors age<=21 Spearman vs realized WAR ~0.22, all-levels
             ~0.31 -- nearly matching the 0.26 consensus FV gets on graded low-minors bats,
             for players who have NO consensus at all. A real coverage + discovery win.
    PITCHERS drop level_rank (it HURTS the low-minors read -- it rewards quad-A org arms
             reaching AAA): low-minors Spearman jumps 0.09 -> 0.24. The K-rate signal (a DSL
             arm missing bats) is the genuine lead; conservative by design (weak signal).

  GRADE MAP: a conventional, CAPPED, ABSOLUTE linear map war_pred -> FV (NOT a cohort
  quantile map -- a weak year must not inflate the top). Calibrated so the cohort matches
  both the owner's spec and conventional FV semantics: MOST land 20-30 (org filler), only
  genuine production breakouts reach 35-43, and a hard cap (43 hit / 40 pit) keeps any
  un-scouted player from masquerading as a real prospect (a true 45+ would have been
  graded). Heavy reliability shrinkage (inherited from _season_rates) keeps small-sample
  DSL lines from spiking.

These grades are PROVISIONAL and explicitly flagged (xfv_ungraded + xfv_provisional) so
every surface can show them as the production-only leading indicator they are, distinct
from the source-anchored flagship grade.

Artifact: data/xfv_ungraded.json (by_player + by_mlbam). Run: python efv_ungraded.py
"""
from __future__ import annotations

import json
import logging
import statistics
from datetime import date, timedelta
from pathlib import Path

import value_framework as vf
import efv_factor_groups as _fgroups
# DELIBERATELY prospect_path's pair, not efv_model's. ARM A2 (neutral imputation for
# rows with no MiLB block) is about the FLAGSHIP ridge's treatment of that block; this
# is a different model on a different feature set (_NOFV_HIT / _NOFV_PIT, no fv anchor)
# fitted on production-bearing rows only, so a milb_unavailable row is out of its pool
# by construction and the imputation has nothing to act on. Repointing would be a no-op
# that implied the arm was measured here. See the arms-lane handoff, 2026-09-04.
from prospect_path import _fit_ridge, _predict, _fit_linear_calibration, _spearman
from efv_model import _vec
from efv_dataset import matrix_path, _milb_features, _f, CURRENT_SEASON

log = logging.getLogger(__name__)
DATA_DIR = Path(__file__).parent / "data"
OUT_PATH = DATA_DIR / "xfv_ungraded.json"
EVAL_PATH = DATA_DIR / "xfv_ungraded_eval.json"
_BUCKETS = ("bust", "bench", "regular", "good", "star")

# No-FV production feature sets (see module docstring + data/xfv_ungraded_eval.json).
# Hitters KEEP level_rank (reaching a high level is predictive); pitchers DROP it (it
# rewards quad-A org arms and HURTS the low-minors discovery the model exists for).
_NOFV_HIT = ["obp_rel", "ops_rel", "k_rel", "peak_k_rel", "peak_obp_rel",
             "iso_rel", "age_rel_level", "level_rank", "n_milb_seasons"]
_NOFV_PIT = ["k_rel", "peak_k_rel", "bb_rel", "era_rel", "x_era_k",
             "age_rel_level", "n_milb_seasons"]

# Declared monotone direction per provisional key (sign audit 2026-07-25). These sets
# used to be bare key lists, so nothing stated what any of them was supposed to do and
# the audit had to inherit the flagship declaration, which is how peak_obp_rel /
# iso_rel / era_rel shipped with no stated intent at all and n_milb_seasons shipped
# claiming +1 while fitting -1.0063. 0 = NO DIRECTIONAL CLAIM. Pinned by
# test_efv_sign_declarations.py; audit function in efv_sign_audit.audit_provisional.
_NOFV_MONO = {
    "obp_rel": +1, "peak_obp_rel": +1, "ops_rel": +1, "iso_rel": +1,
    "bb_rel": -1, "era_rel": -1, "x_era_k": +1,
    "age_rel_level": -1, "level_rank": +1,
    # n_milb_seasons: fitted -1.0063 (hit) / -0.1643 (pit) against the flagship's
    # inherited +1, and the marginal is -0.0075 on the provisional pool, so the
    # "track record" reading is not true even unconditionally here. Conditional on
    # level_rank + age_rel_level it prices seasons USED to reach the level.
    "n_milb_seasons": 0,
}

# Conventional grade map with a SOFT ceiling: grade = BASE + SLOPE*war_pred, floored at
# FLOOR, then compressed above KNEE toward CEIL: g' = KNEE + (CEIL-KNEE)*(1-exp(-(g-KNEE)/SOFT)).
# Spec-calibrated (owner: "low, 20-30 for most, breakouts higher") + validated to match
# conventional FV semantics on the real roster cohort (hitters median ~23 / 77% <=30;
# pitchers median ~24 / 87% <=30). WHY SOFT, not a HARD CAP (cap test, 2026-06-23):
#   HITTERS  uncapped grade carries REAL forward-chained signal above 43 (realized 6yr WAR
#            bins: [43,48) mean 3.43, [48+) mean 6.10; Spearman 0.29 among grade>=40), so a
#            hard cap at 43 DISCARDS signal -- the genuine young-for-level breakouts (an 18-yo
#            holding AA) deserve mid-to-high-40s. KNEE 43 / CEIL 49 lets them through while
#            bounding the extreme (an un-scouted player still can't claim top-prospect status
#            without scout corroboration; ungraded-selection risk caps the magnitude).
#   PITCHERS signal above 40 is NOISE (Spearman 0.077; bins flat) -- the top uncapped arms are
#            small-sample high-K complex-ball spikes. KNEE 38 / CEIL 42 compresses hard.
# Soft (not hard) so ORDER is preserved above the knee -- it matters now that these grades fold
# into the flagship board rank + farm composite.
_GRADE_MAP = {
    "hit": {"BASE": 27.0, "SLOPE": 3.8, "FLOOR": 20.0, "KNEE": 43.0, "CEIL": 49.0, "SOFT": 4.0},
    # Pitcher ceiling de-rated (KNEE 38->34, CEIL 42->38): the module's own cap test
    # found the un-scouted low-level pitcher signal above ~40 is NOISE (small-sample
    # high-K complex/DSL spikes), so a provisional arm should top out at an org-depth
    # grade, not a fringe-regular 42. Order-preserving soft ceiling -> the provisional
    # rank eval is unchanged; xfv.json is untouched (this path writes only xfv_ungraded).
    "pit": {"BASE": 25.0, "SLOPE": 4.5, "FLOOR": 20.0, "KNEE": 34.0, "CEIL": 38.0, "SOFT": 2.5},
}

# C1 DE-CAP (true-to-model; owner: "same for provisional grades"). When True, the
# war_pred -> FV grade map DROPS the soft ceiling (the KNEE/CEIL/SOFT exponential
# compression above the knee) so a provisional grade reflects the model's raw,
# UNCOMPRESSED war->FV linear map at the top: g = max(FLOOR, BASE + SLOPE*war_pred),
# no upper compression (FLOOR stays -- it is the 20-80 scale minimum, a domain guard,
# not top compression). A Primera-class breakout then grades to its true model value
# instead of piling at the ceiling. The soft ceiling is ORDER-PRESERVING (strictly
# monotone in war above the knee, identity below), and the low-minors OOS harness
# (evaluate() / data/xfv_ungraded_eval.json) scores _war(), NOT _grade() -- so this
# flip is Spearman-INVARIANT by construction; the only effect is de-compression of the
# served grade distribution. Default OFF; the Wave-F consolidator flips to True on ship.
# PROVISIONAL CAP RESTORED 2026-07-25 (owner call, docs/EFV_FRONTIER_AUDIT.md follow-up).
# The C1 de-cap (2026-07-24b) turned the soft ceiling off for BOTH the graded and the
# provisional paths on a true-to-model argument: do not compress the raw war->FV map.
# That argument still holds for the GRADED path, where the grade rests on a real scouting
# anchor plus a pro track record. It does not hold here. A provisional grade is fit on a
# source-ungraded player with as little as _MIN_EXPO_PA=80 plate appearances, and the
# measured outcome is that DSL bats carrying these grades realize ~0 WAR about 85% of the
# time while the served card printed p_bust 0.201. Uncapped, an 87-PA DSL line produced a
# 53 (deployed) / 43.5 (current tree) grade, above the CEIL49 the graded path uses as its
# own asymptote. The KNEE/CEIL/SOFT map is ORDER-PRESERVING (see _grade), so restoring it
# bounds magnitude on thin samples WITHOUT flattening the ranking that makes a breakout
# visible - which is the correct treatment for a small-sample estimate.
# Scope: this constant is local to efv_ungraded, so the graded-path de-cap is untouched.
UNCAPPED_GRADE = False

# Sample floor: a provisional grade needs a real exposure sample. The rate features
# are exposure-shrunk, but level_rank + age_rel_level are NOT, so a 1-PA / 1.2-IP
# cameo at a high level otherwise mints a mid-30s grade off level + age alone. Below
# the floor we cap the grade at org-filler (a cameo is not a prospect signal).
_MIN_EXPO_BF = 90.0     # min batters faced for a pitcher provisional grade
_MIN_EXPO_PA = 80.0     # min plate appearances for a hitter provisional grade
_SUBFLOOR_GRADE = 30.0  # org-filler cap for sub-floor lines

# Default ETA (years to MLB) by level, for the surplus seam -- ungraded low-minors players
# are years away. Surplus at FV 20-35 is near $0 regardless; this only shapes the band.
_LEVEL_ETA = {"DSL": 6.0, "CPX": 5.0, "A": 4.5, "A+": 3.5, "AA": 2.5, "AAA": 1.5}


# ---------------------------------------------------------------------------
# THIN-SAMPLE p_bust CONDITIONAL (2026-07-25, owner-authorized)
# ---------------------------------------------------------------------------
# WHAT CHANGED. efv_score.py states that p_bucket / p_bust are "the validated
# star/bust odds" and are "NEVER touched". That invariant now reads: NEVER
# touched EXCEPT by this thin-sample conditional, which replaces p_bust (and
# renormalizes p_bucket to stay consistent with it) on PROVISIONAL rows only.
# Nothing on the graded flagship path changes; see the amended notes in
# efv_score.py.
#
# WHY. p_bust arrives from vf.sv_distribution -> vf.p_bucket_given_fv, keyed on
# the GRADE alone. That curve is fitted on the Clemens published-list population:
# source-graded prospects with a real pro track record. A provisional grade is
# fitted on a source-UNGRADED player off as little as _MIN_EXPO_PA = 80 plate
# appearances, so the card inherited odds that were never calibrated for it. The
# served result was a 17-year-old with an 87-PA DSL line printing P(bust) 51%
# (and 20% on the pre-cap deployed build).
#
# WHAT WAS MEASURED (tools/pbust_thin/, artifact data/xfv_thin_pbust_eval.json).
# A historical cohort was rebuilt to match the SERVED population exactly:
# source-ungraded as of the cohort season, never MLB-exposed at or before it,
# primary-level exposure at or above the served grade floor, primary level on the
# DSL..AAA ladder. Cohort seasons 2015-2018 (four independent time splits; 8 to
# 11 seasons of outcome, and 97.8% of eventual DSL/CPX debuts occur within 8).
# n = 19,812 player-seasons. Every row is re-scored through THIS module's own
# grade map. Label: bust = first-6-MLB-season summed bWAR < 3.0, i.e. the
# Clemens bucket-0 band of < 0.5 WAR/season over the 6-season control window.
# Never reaching MLB is a bust with certainty and needs no WAR join.
#
# THE HISTORICAL HIT RATE, with n (this is the number the served card was
# missing). Among ungraded DSL bats carrying a provisional grade of 35 or better,
# 88.1% never produced a non-bust MLB career (n = 87 for that exact cell; the
# DSL cell as a whole is n = 2,236 at 99.2%). Ungraded DSL arms at grade 35+:
# 99.0%, n = 314. Pooled at grade 35+: hitters 88.1% observed against 71.5%
# served (n = 778), pitchers 94.0% against 80.9% (n = 745).
#
# GATES (docs/EFV_GATE_STANDARD.md; B = 400 paired bootstrap draws that resample
# the TRAIN matrix AND the TEST cohort and REFIT the provisional ridge on every
# draw, so the grade column carries its own sampling variability):
#   G1 defect  empirical minus served, grade >= 35: hit +0.169 CI95 [0.128,
#              0.204], pit +0.130 CI95 [0.094, 0.150]. Positive on all 8
#              (side x cohort-year) cells.
#   G2 ship    leave-one-cohort-year-out log loss, incumbent minus this head
#              +0.0179 CI95 [0.0123, 0.0249], P(>0) = 1.000. Brier 0.0364 ->
#              0.0329.
#   G3 controls  the covariate-free CONSTANT head (the ablation that killed
#              BUCKET-AGE-HEAD) loses by 0.0164 CI95 [0.0133, 0.0193]; a pure
#              population offset is a measured NULL against the incumbent
#              (+0.0015 CI95 [-0.0046, 0.0079], P = 0.695), so none of the gain
#              is population recalibration. Row-permuted GRADE twin loses by
#              0.0103 [0.0079, 0.0129]; row-permuted LEVEL twin by 0.0081
#              [0.0060, 0.0103].
#   G4 null    label-permutation null on (constant minus head) p95 = -0.00007
#              against an observed 0.0164.
#   G5 monotone  b < 0 on both sides, so p_bust is nonincreasing in the grade
#              inside every level. Levels are CATEGORICAL on purpose: the
#              realized level-to-bust relation is NOT monotone (ungraded AAA is
#              org filler and busts more than ungraded AA), so a linear
#              level_rank term is misspecified exactly where it moves served
#              numbers most. That variant was fitted, beat the incumbent, and
#              was REJECTED for this reason.
#
# LABEL BASIS. Rows that reached MLB but carry no career_war row are unknown.
# The fit calls an unknown row a bust only when its first-6-MLB-season playing
# time is under 300 PA / batters faced. That is validated, not assumed: of the
# 1,144 cohort rows with a KNOWN first-6-year WAR, 0 of the 487 under 300 PA/BF
# reached 3.0 WAR (highest was 1.58, and it is still 0 of 639 at a 500
# threshold). The remaining unknowns stay labelled NON-bust even though 63.9% of
# the KNOWN rows above 300 PA/BF are busts, so the fitted curve is a LOWER bound
# on the real bust rate. Every gate above also passes under the two bracketing
# labelings (all unknowns non-bust, all unknowns bust).
#
# SCOPE AND LIMITS.
#  * Serves p_bust and p_bucket only. Surplus DOLLARS stay on the engine's own
#    grade-anchored path: vf.expected_surplus_usd applies a separate sub-FV-40
#    dollar anchor that does not decompose as a bucket mixture, so the exact
#    "scale the non-bust mass" identity does not carry through it, and a dollar
#    change was neither gated nor authorized here. The odds and the dollars
#    therefore sit on different bases at this seam, the same documented split
#    _reprice_surplus_on_display already makes on the flagship path.
#  * The cohort's feature history is floored at 2014 by the MiLB cache, so early
#    cohort rows see at most 1 to 2 prior seasons. That matters for the
#    n_milb_seasons feature at the UPPER levels; the DSL/CPX population the
#    defect lives in is 17 to 19 year olds with 1 to 2 pro seasons anyway.
#  * Residual: the hitter 45+ band is still under-called out of fold (0.743
#    against 0.813 observed, n = 107). The served provisional map tops out at
#    CEIL 49 and the live artifact's maximum is 44.9, so that band is nearly
#    empty in production. Not repaired here.
#  * A row whose level does not resolve to the ladder keeps the incumbent
#    p_bust and is flagged p_bust_low_confidence rather than fed a made-up
#    number.
THIN_PBUST_ENABLED = True          # env override EEPHUS_THIN_PBUST "1"/"0"
# logit p_bust = a + b*(grade - 30) + level_offset      (DSL is the reference cell)
_THIN_PBUST_HEAD = {
    "hit": {"a": 4.251112, "b": -0.148750,
            "level": {"DSL": 0.0, "CPX": -0.929576, "A": -1.182609,
                      "A+": -1.659829, "AA": -1.502044, "AAA": -0.246737}},
    "pit": {"a": 5.083222, "b": -0.169809,
            "level": {"DSL": 0.0, "CPX": -1.372043, "A": -2.116888,
                      "A+": -2.594148, "AA": -3.266335, "AAA": -2.662682}},
}
# Served clamp. The ceiling is 0.99 for two reasons, both conservative: the card
# rounds to whole percent, so anything at or above 0.995 would print "P(bust)
# 100%" and claim a certainty no model has; and 0.99 sits BELOW the measured DSL
# cell rate (0.992 hit / 0.992 pit, n = 2,236 / 2,167), so the clamp can only
# make a served row look SAFER than the cohort was. It binds on the low-grade
# DSL/CPX tail, where the fitted head reaches 0.999.
_THIN_PBUST_CLAMP = (0.02, 0.99)
_THIN_PBUST_FIT = {
    "cohort_seasons": [2015, 2016, 2017, 2018], "n": 19812,
    "label": "first-6-MLB-season bWAR < 3.0 (Clemens bucket 0)",
    "eval": "data/xfv_thin_pbust_eval.json", "lab": "tools/pbust_thin/",
}


def _thin_pbust_enabled() -> bool:
    import os
    env = os.environ.get("EEPHUS_THIN_PBUST")
    if env is not None:
        return env.strip() == "1"
    return THIN_PBUST_ENABLED


def thin_sample_p_bust(grade, side: str, level) -> float | None:
    """P(bust) for a THIN-SAMPLE provisional row, from the population-conditional
    head fitted on the served population's own realized outcomes (see the block
    above). Returns None when the flag is off, the grade is unusable, or the level
    does not resolve to the DSL..AAA ladder; the caller then keeps the incumbent
    grade-only odds and flags the row low-confidence rather than inventing one."""
    if not _thin_pbust_enabled() or grade is None:
        return None
    h = _THIN_PBUST_HEAD.get(side)
    if not h:
        return None
    off = h["level"].get(level)
    if off is None:
        return None
    try:
        g = float(grade)
    except (TypeError, ValueError):
        return None
    import math
    z = max(-30.0, min(30.0, h["a"] + h["b"] * (g - 30.0) + off))
    p = 1.0 / (1.0 + math.exp(-z))
    lo, hi = _THIN_PBUST_CLAMP
    return min(hi, max(lo, p))


def _apply_thin_pbust(p_bucket: dict | None, p_old, p_new: float):
    """Fold `p_new` into the served odds. The bust mass becomes p_new and the
    NON-bust buckets are rescaled by (1 - p_new) / (1 - p_old), which preserves the
    incumbent's relative shape across bench/regular/good/star (that shape was NOT
    measured here and must not be invented) while keeping p_bucket['bust'] and
    p_bust identical on the card. Returns the rebuilt p_bucket, or the original
    when the incumbent leaves no non-bust mass to rescale."""
    if not p_bucket or p_old is None:
        return p_bucket
    rem = 1.0 - float(p_old)
    if rem <= 1e-9:
        return p_bucket
    f = (1.0 - p_new) / rem
    out = {}
    for k, v in p_bucket.items():
        out[k] = round(p_new, 3) if k == "bust" else round(float(v) * f, 3)
    # Absorb the 3dp rounding residual into the largest NON-bust bucket so the
    # served vector still sums to 1.000 (rescaling then rounding otherwise loosens
    # the sum from the incumbent's 0.001 to 0.002). bust stays exactly p_new.
    nb = [k for k in out if k != "bust"]
    if nb:
        big = max(nb, key=lambda k: out[k])
        out[big] = round(out[big] + (1.0 - sum(out.values())), 3)
    return out

_FACTOR_LABELS = {
    "obp_rel": "On-base vs level", "ops_rel": "OPS vs level", "k_rel": "Contact (K%) vs level",
    "bb_rel": "Walk rate vs level", "iso_rel": "Power (ISO) vs level", "era_rel": "ERA vs level",
    "age_rel_level": "Age for level", "level_rank": "Level reached", "x_era_k": "Run prevention x K",
    "peak_k_rel": "Peak K rate", "peak_obp_rel": "Peak on-base",
    # see efv_score._FACTOR_LABELS: the provisional weight is -1.0063 (hit) /
    # -0.1643 (pit), so "Track record" rendered UP on 619 of 969 hitter and 615 of
    # 983 pitcher cards precisely BECAUSE those players have little track record.
    # Mean magnitude 1.300 on hitters (third-largest driver in that model).
    "n_milb_seasons": "Seasons used to reach level",
}

_PIT_POS = ("P", "RHP", "LHP", "SP", "RP", "SIRP", "MIRP")


def _is_pitcher_pos(pos) -> bool:
    return (pos or "").upper() in _PIT_POS


def _prep(rows, side: str):
    """Labeled rows -> {feats, target} for the no-FV fit (reuses the flagship _vec, which
    already emits every production feature; we just train on a subset of keys)."""
    out = []
    for r in rows:
        t = r.get("target_censored")
        if t is None:
            continue
        out.append({
            "player_key": r["player_key"], "feats": _vec(r, side), "target": float(t),
            "weight": float(r.get("weight", 1.0)),
            "decision_year": (int(r["debut_year"]) if r["kind"] == "debuted"
                              else (int((r.get("cutoff") or "2026")[:4]) + 1
                                    if (r.get("cutoff") or "")[:4].isdigit() else 2026)),
            "milb": r.get("milb") or {},
        })
    return out


def _keys(side: str):
    return _NOFV_PIT if side == "pit" else _NOFV_HIT


def fit_nofv(side: str):
    """Fit the no-FV production ridge + linear scale calibration on the full labeled matrix.
    Returns (ridge, a, b) where war = max(-2, a + b*ridge(feats))."""
    is_pit = side == "pit"
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    # AUDIT FIX 2026-07-14: this is the PRODUCTION-ONLY model - training it on
    # rows with NO production block (features imputed to raw 0.0, previously a
    # MAJORITY of the pool) taught it "all-zero features -> bust" instead of
    # production->outcome, and the live model never sees such rows (its gate
    # requires a milb block). Fit on production-bearing rows only; recent
    # busts stay excluded (their window is still open).
    data = _prep([r for r in rows
                  if bool(r.get("is_pitcher")) == is_pit and r.get("milb")
                  and not (r.get("kind") == "bust" and r.get("bust_recent"))], side)
    ridge = _fit_ridge(data, _keys(side))
    raw = {r["player_key"]: _predict(ridge, r["feats"]) for r in data}
    cal = _fit_linear_calibration([(raw[r["player_key"]], r["target"]) for r in data])
    a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
    return ridge, a, b


# Out-of-support guard: the no-FV ridge is a linear model, so a live feature far
# outside the training envelope extrapolates without bound. Un-scouted tiny-sample
# DSL/complex lines routinely present standardized features at z = +5..+40 (a
# catastrophic-outing era_rel, a 2.8% K% k_rel), which the shared _predict weights
# straight through -- e.g. x_era_k contributing +6.9 WAR off a 1.2-IP blowup. Clip
# each standardized feature to +/-_Z_CLIP before weighting. This is LOCAL to the
# provisional path (writes only xfv_ungraded.json; xfv.json is byte-identical) and
# preserves the low-minors OOS rank (validated: clip 6 leaves Spearman flat).
_Z_CLIP = 6.0


def _predict_clipped(model: dict, feats: dict, clip: float = _Z_CLIP) -> float:
    z = 0.0
    for k, m, s, w in zip(model["keys"], model["mu"], model["sd"], model["w"]):
        zc = (feats.get(k, 0.0) - m) / (s or 1.0)
        zc = max(-clip, min(clip, zc))
        z += w * zc
    return z + model["b"]


def _war(ridge, a, b, feats) -> float:
    return max(-2.0, a + b * _predict_clipped(ridge, feats))


def _grade(war: float, side: str) -> float:
    """war_pred -> provisional FV. Default: linear below the KNEE, soft-compressed toward CEIL
    above it (order-preserving, so breakouts stay ranked while the magnitude is bounded).
    With UNCAPPED_GRADE True (C1 de-cap): the raw uncompressed linear map, no soft ceiling."""
    import math
    m = _GRADE_MAP[side]
    g = max(m["FLOOR"], m["BASE"] + m["SLOPE"] * war)
    if not UNCAPPED_GRADE:
        knee, ceil, soft = m["KNEE"], m["CEIL"], m["SOFT"]
        if g > knee:
            g = knee + (ceil - knee) * (1.0 - math.exp(-(g - knee) / soft))
    return round(g, 1)


def _display_statline(mlbam, milb_block, side: str, org: str | None):
    """A frontend-shaped statline (the final pre-decision MiLB season line that drove the
    grade) so a provisional player's board row + detail page can show the production behind
    the grade. Best-effort: reads the warm milb_history cache (no network)."""
    import milb_history as mh
    season = milb_block.get("milb_season")
    level = milb_block.get("milb_level")
    if not (season and level and mlbam):
        return None
    group = "pitching" if side == "pit" else "hitting"
    try:
        rows = mh.player_index(int(season), group, fetch=False).get(int(mlbam)) or []
        row = mh.level_row(rows, level, group)
    except Exception:
        return None
    if not row:
        return None
    def fl(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    out = {"mlbam_id": mlbam, "level": level, "level_label": row.get("league"),
           "season": int(season), "is_prior_season": int(season) < CURRENT_SEASON, "org": org}
    if side == "pit":
        bf, ip, so, bb = fl(row.get("bf")), fl(row.get("ip")), fl(row.get("so")), fl(row.get("bb"))
        out.update({
            "is_pitcher": True, "ip": row.get("ip"), "era": row.get("era"), "games": row.get("g"),
            "tbf": int(bf) if bf else None,
            "k_pct": round(so / bf * 100, 1) if (so is not None and bf) else None,
            "bb_pct": round(bb / bf * 100, 1) if (bb is not None and bf) else None,
            "k_per_9": round(so / ip * 9, 2) if (so is not None and ip) else None,
            "bb_per_9": round(bb / ip * 9, 2) if (bb is not None and ip) else None,
        })
    else:
        pa, so, bb = fl(row.get("pa")), fl(row.get("so")), fl(row.get("bb"))
        slg, avg = fl(row.get("slg")), fl(row.get("avg"))
        out.update({
            "is_pitcher": False, "ab": row.get("ab"), "avg": row.get("avg"), "obp": row.get("obp"),
            "slg": row.get("slg"), "ops": row.get("ops"), "hr": row.get("hr"),
            "pa": int(pa) if pa else None,
            "k_pct": round(so / pa * 100, 1) if (so is not None and pa) else None,
            "bb_pct": round(bb / pa * 100, 1) if (bb is not None and pa) else None,
            "iso": round(slg - avg, 3) if (slg is not None and avg is not None) else None,
        })
    return out


def _career_row(r, side: str, org: str | None):
    """One season-and-level MiLB stat row in the site's career_stats shape (the detail-page
    stats table reads career_stats)."""
    def fl(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    base = {"season": r.get("season"), "level": r.get("level"), "level_label": r.get("league"),
            "org": org, "is_pitcher": side == "pit"}
    if side == "pit":
        bf, ip, so, bb = fl(r.get("bf")), fl(r.get("ip")), fl(r.get("so")), fl(r.get("bb"))
        base.update({
            "games": r.get("g"), "era": r.get("era"), "ip": r.get("ip"),
            "tbf": int(bf) if bf else None,
            "k_per_9": round(so / ip * 9, 2) if (so is not None and ip) else None,
            "bb_per_9": round(bb / ip * 9, 2) if (bb is not None and ip) else None,
            "k_pct": round(so / bf * 100, 1) if (so is not None and bf) else None,
            "bb_pct": round(bb / bf * 100, 1) if (bb is not None and bf) else None,
        })
    else:
        pa, so, bb = fl(r.get("pa")), fl(r.get("so")), fl(r.get("bb"))
        slg, avg = fl(r.get("slg")), fl(r.get("avg"))
        base.update({
            "games": None, "ab": r.get("ab"), "avg": r.get("avg"), "obp": r.get("obp"),
            "slg": r.get("slg"), "ops": r.get("ops"), "hr": r.get("hr"),
            "iso": round(slg - avg, 3) if (slg is not None and avg is not None) else None,
            "k_pct": round(so / pa * 100, 1) if (so is not None and pa) else None,
            "bb_pct": round(bb / pa * 100, 1) if (bb is not None and pa) else None,
        })
    return base


def _career_stats(mlbam, side: str, org: str | None, max_seasons: int = 5):
    """Multi-season MiLB stat rows (one per season-and-level) for the provisional player's
    detail-page stats table -- the production behind the grade. Best-effort, warm cache only."""
    import milb_history as mh
    group = "pitching" if side == "pit" else "hitting"
    out = []
    for season in range(CURRENT_SEASON, CURRENT_SEASON - max_seasons, -1):
        try:
            rows = mh.player_index(int(season), group, fetch=False).get(int(mlbam)) or []
        except Exception:
            continue
        for r in rows:
            lvl = r.get("level")
            if not lvl or lvl == "MLB":
                continue
            out.append(_career_row(r, side, org))
    # newest first, higher level first within a season (matches the site's ordering)
    _ord = {"AAA": 5, "AA": 4, "A+": 3, "A": 2, "CPX": 1, "DSL": 0}
    out.sort(key=lambda x: (-(x.get("season") or 0), -_ord.get(x.get("level"), -1)))
    return out


def _factors(ridge, feats, top: int = 3, side: str = "hit") -> list:
    """The largest standardized production contributions (WAR units), for the explainer.

    COLLINEAR-GROUP FIX 2026-07-25 (same defect as efv_score._factors, same shared
    rule): k_rel/peak_k_rel and obp_rel/peak_obp_rel are the same statistic over two
    windows (live r = +0.76 / +0.58) and both pairs ship in this provisional set, so
    the explainer sums each declared group into ONE factor before the magnitude floor
    and the top-N cut. A group is therefore shown or hidden whole and its direction is
    the NET direction, instead of one half of a cancelling pair reaching the card.
    DISPLAY ONLY: the provisional grade, WAR and surplus are untouched."""
    contribs = []
    for k, mu, sd, w in zip(ridge["keys"], ridge["mu"], ridge["sd"], ridge["w"]):
        zc = max(-_Z_CLIP, min(_Z_CLIP, (feats.get(k, 0.0) - mu) / (sd or 1.0)))   # match _war's clip
        contribs.append((k, w * zc))
    return _fgroups.collapse(contribs, side, lambda k: _FACTOR_LABELS.get(k, k),
                             min_mag=0.05, top=top)


def evaluate(persist: bool = True) -> dict:
    """Forward-chained rank validation vs realized WAR on the low-minors target cohort
    (the governance artifact -- proves the no-FV production model carries OOS signal where
    there is no consensus FV). Mirrors the flagship eval protocol."""
    out = {"generated_at": __import__("datetime").date.today().isoformat(),
           "model": "eFV ungraded (no-FV production ridge)", "by_side": {}}
    for side in ("hit", "pit"):
        is_pit = side == "pit"
        rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
        # AUDIT FIX 2026-07-14: evaluate on the same production-bearing pool
        # the live model can actually see - the old all-rows pool inflated
        # the advertised Spearman with no-production rows (42% of test rows)
        # whose all-zero features the fit had memorized as busts.
        data = _prep([r for r in rows
                      if bool(r.get("is_pitcher")) == is_pit and r.get("milb")
                      and not (r.get("kind") == "bust" and r.get("bust_recent"))], side)
        keys = _keys(side)
        res = {}
        for label, levels, max_age in (("low_minors_age_le21", {"DSL", "CPX", "A"}, 21),
                                       ("all_levels", None, None)):
            P, T = [], []
            for yr in (2019, 2020, 2021, 2022, 2023):
                tr = [r for r in data if r["decision_year"] < yr]
                te = [r for r in data if r["decision_year"] == yr]
                if len(tr) < 60 or len(te) < 15:
                    continue
                rg = _fit_ridge(tr, keys)
                cal = _fit_linear_calibration([(_predict(rg, r["feats"]), r["target"]) for r in tr])
                a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
                for r in te:
                    m = r["milb"]
                    lvl = m.get("milb_level")
                    age = m.get("age")
                    if (levels is None or lvl in levels) and (max_age is None or age is None or age <= max_age):
                        P.append(_war(rg, a, b, r["feats"]))
                        T.append(r["target"])
            res[label] = {"n": len(P), "spearman_vs_realized_war": _spearman(P, T) if len(P) >= 8 else None}
        out["by_side"][side] = {"features": keys, "cohorts": res}
    out["note"] = ("Production-only (no consensus FV) ranks realized WAR among un-graded-analog "
                   "low-minors players; this is the signal the provisional ungraded grade rests on. "
                   "Hitters ~0.22 low-minors / ~0.31 all-levels; pitchers ~0.24 low-minors (level_rank "
                   "dropped). These are PROVISIONAL leading-indicator grades, not the flagship.")
    if persist:
        EVAL_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
        log.info("wrote %s", EVAL_PATH)
    return out


def flagship_owns(roster_player: dict) -> bool:
    """Does the FLAGSHIP eFV board own this roster row, or does the provisional path?

    THE PARTITION, stated once (2026-07-30). `fv_raw` on a rosters_by_org.json row is
    the latest consensus point's `consensus_fv_raw` (run_monthly stamps it from the
    timeseries, and it is None whenever the player has no consensus point at all).
    `consensus.compute_consensus_point` returns None unless the player has at least one
    explicit FV or one non-org-list rank. So:

        has a scout grade  ->  consensus point  ->  fv_raw set  ->  FLAGSHIP board
        no scout grade     ->  no point         ->  fv_raw None ->  PROVISIONAL pool

    The two are complements, so every rostered non-MLB player with usable MiLB
    production lands in exactly one of them. That is a general rule and it predates
    this note; it is named here because it was not obvious enough to survive being
    tested.

    WHY IT IS NAMED NOW. Removing `baseballamerica_statcast_by_age`'s fabricated FV 40
    dropped seven players off the served board (`braylon_whitaker`, `easton_shelton`,
    `jacob_friend`, `jake_cunningham`, `jose_meza`, `mason_guerra`,
    `michael_martinez`): that snapshot was their ONLY row in the database, so with no
    FV they produce no consensus point. They did not fall through a hole. The
    fabricated grade had been holding them on the WRONG side of this partition, and
    with it gone they route here, which is where a player with a track record and no
    scout grade belongs. Nothing had to change for that to happen; what was missing
    was a test saying so. See docs/efv-2026-07-30/POSITION_ROLE_GATE.md 3.2 and
    ORPHAN_ROUTING.md.

    THE CONSTANT WAS BLOCKING ITS OWN REPLACEMENT (fixed 2026-08-05). The invariant
    above assumes fv_raw is set only by a published opinion. It is not.
    `consensus.compute_consensus_point` folds CONSTANT_ANCHOR_SOURCES
    (performance_ingest / auto_detect) back in as a LAST RESORT so players nobody
    has graded do not vanish from the board, and that produces a real consensus
    point carrying a fabricated FV. So a player with NO scout grade got fv_raw set,
    read as "flagship-owned", and was routed away from this model, which exists to
    grade exactly him. Measured: 2,632 of the 2,720 constant-only players were
    excluded that way, every one of them at fv_raw exactly 35.0, while this model
    scored only 70 of them (and those 70 only because their identity join failed,
    which happened to leave fv_raw None). run_monthly now stamps fv_synthetic_only
    on the roster row and this gate honors it, which restores the invariant the
    docstring above always claimed. Same defect class the paragraph below describes
    for the retired baseballamerica_statcast_by_age FV 40; that one was removed at
    the source, this one cannot be, because the constant is load-bearing for board
    coverage.
    """
    rp = roster_player or {}
    if rp.get("fv_synthetic_only"):
        return False
    return rp.get("fv_raw") is not None


def build(persist: bool = True) -> dict:
    """Score every UNGRADED roster player (data/rosters_by_org.json: fv_raw is None) that has
    real MiLB production, on the no-FV production model + capped grade map. Writes
    data/xfv_ungraded.json = {by_player, by_mlbam, meta}. Run AFTER the site export
    (rosters_by_org.json must exist)."""
    rost_path = DATA_DIR / "rosters_by_org.json"
    if not rost_path.exists():
        log.warning("rosters_by_org.json absent -- run the site export first; ungraded eFV empty")
        return {"players": 0}
    rosters = json.loads(rost_path.read_text(encoding="utf-8"))
    fits = {s: fit_nofv(s) for s in ("hit", "pit")}

    by_player, by_mlbam = {}, {}
    counts = {"hit": 0, "pit": 0, "no_production": 0, "no_mlbam": 0}
    pb_counts = {"thin_conditional": 0, "incumbent_low_confidence": 0}
    for org, levels in rosters.items():
        for level, players in (levels or {}).items():
            if level == "MLB" or not isinstance(players, list):
                continue
            for p in players:
                if flagship_owns(p):        # already source-graded -> flagship owns it
                    continue
                mid = p.get("mlbam_id")
                if not mid:
                    counts["no_mlbam"] += 1
                    continue
                side = "pit" if _is_pitcher_pos(p.get("position")) else "hit"
                m = _milb_features(mid, CURRENT_SEASON + 1, None, side)
                if not m or m.get("k_rel") is None:        # no usable MiLB production
                    counts["no_production"] += 1
                    continue
                ridge, a, b = fits[side]
                feats = _vec({"consensus_fv_raw": _GRADE_MAP[side]["BASE"],
                              "position": p.get("position"), "milb": m}, side)
                war = _war(ridge, a, b, feats)
                grade = _grade(war, side)
                pos = p.get("position")
                age = _f(p.get("age"))
                eta = _LEVEL_ETA.get(level, 4.0)
                is_pit = side == "pit"
                pk = p.get("player_key") or f"mlbam_{mid}"
                statline = _display_statline(mid, m, side, p.get("team_name"))
                # SAMPLE FLOOR: cap a sub-floor cameo at org-filler BEFORE it prices surplus,
                # so a 1-PA/1.2-IP line can't ride level+age into a prospect grade.
                _expo = ((statline or {}).get("tbf") if is_pit else (statline or {}).get("pa")) or 0
                # AUDIT FIX 2026-07-14: only apply the cameo sub-floor when the
                # display statline actually resolved - a cold/missing cache
                # season returns statline=None, and treating that unknown
                # exposure as 0 crushed real prospects to org-filler grades.
                if statline is not None and _expo < (_MIN_EXPO_BF if is_pit else _MIN_EXPO_PA):
                    grade = min(grade, _SUBFLOOR_GRADE)
                surplus = vf.expected_surplus_usd(grade, is_pit, pos, age=age, eta_years=eta)
                dist = vf.sv_distribution(grade, is_pit, pos, age=age, eta_years=eta) or {}
                pcts = dist.get("percentiles") or {}
                probs = vf.p_bucket_given_fv(grade, is_pit) or []
                # THIN-SAMPLE CONDITIONAL (see the block above _LEVEL_ETA). The head
                # is keyed on the PRIMARY-level line the grade actually read (the
                # statline), not the roster assignment, so the served row matches
                # the fit population row for row; the roster level is the fallback.
                _pb_level = (statline or {}).get("level") or level
                _pb_old = dist.get("p_bust")
                _pb_new = thin_sample_p_bust(grade, side, _pb_level)
                _pb_basis, _pb_lowconf = "incumbent", False
                if _pb_new is not None and _pb_old is not None:
                    probs_d = {k: pv for k, pv in zip(_BUCKETS, probs)} if probs else None
                    probs_d = _apply_thin_pbust(probs_d, _pb_old, _pb_new)
                    probs = [probs_d[b_] for b_ in _BUCKETS] if probs_d else probs
                    dist = {**dist, "p_bust": _pb_new}
                    _pb_basis = "thin_sample_conditional"
                    pb_counts["thin_conditional"] += 1
                elif not _thin_pbust_enabled():
                    # Feature off: the row is the plain incumbent baseline, which is
                    # the documented pre-2026-07-25 behavior, NOT a low-confidence row.
                    pb_counts["incumbent_flag_off"] = pb_counts.get("incumbent_flag_off", 0) + 1
                else:
                    _pb_lowconf = True
                    pb_counts["incumbent_low_confidence"] += 1
                career_stats = _career_stats(mid, side, p.get("team_name"))
                # eFV TRAJECTORY: the provisional grade as-of each MiLB season (re-score
                # production through that season only) so the detail page can plot an
                # eFV-over-time chart for a prospect the sources have never graded.
                xfv_hist = []
                _min_expo = _MIN_EXPO_BF if is_pit else _MIN_EXPO_PA
                for _S in sorted({r.get("season") for r in (career_stats or []) if r.get("season")}):
                    _ms = _milb_features(mid, int(_S) + 1, None, side)
                    if not _ms or _ms.get("k_rel") is None:
                        continue
                    _ws = _war(ridge, a, b, _vec({"consensus_fv_raw": _GRADE_MAP[side]["BASE"],
                                                  "position": p.get("position"), "milb": _ms}, side))
                    _xg = _grade(_ws, side)
                    # Same sample floor as the headline grade (398-400), applied to THIS point's
                    # own primary-level line -- the exposure _milb_features keyed its as-of
                    # statline on -- NOT cumulative career PA/BF. Mirroring the headline exactly:
                    # a season whose primary line is a sub-floor cameo floors that point, so a
                    # player with a big early season then a tiny recent cameo floors the cameo
                    # point just as the card headline floors it (cumulative would leave it above).
                    _stat_S = _display_statline(mid, _ms, side, p.get("team_name"))
                    _expo_S = ((_stat_S or {}).get("tbf") if is_pit else (_stat_S or {}).get("pa")) or 0
                    # Same unresolved-statline guard as the headline (AUDIT FIX
                    # 2026-07-14): a None statline is UNKNOWN exposure, not 0.
                    if _stat_S is not None and _expo_S < _min_expo:
                        _xg = min(_xg, _SUBFLOOR_GRADE)
                    xfv_hist.append({"d": f"{int(_S)}-07-01", "x": _xg})
                # Approximate birth_date from the roster age so the detail-page stats table can
                # show age-vs-level (no extra fetch; ~+/- a few months, fine for display).
                birth_date = None
                if age is not None:
                    try:
                        birth_date = (date.today() - timedelta(days=age * 365.25)).isoformat()
                    except Exception:
                        birth_date = None
                def _mm(v):
                    return round(float(v), 1) if v is not None else None
                entry = {
                    "player_key": pk, "mlbam_id": mid, "name": p.get("fullName"),
                    "player_name": p.get("fullName"), "birth_date": birth_date,
                    "side": "P" if is_pit else "H", "org": org, "level": level,
                    "position": pos, "age": age,
                    "statline": statline,
                    "career_stats": career_stats or None,
                    "xfv_history": xfv_hist if len(xfv_hist) >= 2 else None,
                    "xfv_grade": grade, "xfv_war_6yr": round(war, 2),
                    "consensus_fv": None,                     # ungraded -> no source FV
                    "surplus_mm": round(surplus / 1e6, 1) if surplus else None,
                    "p_bucket": {k: round(pv, 3) for k, pv in zip(_BUCKETS, probs)} if probs else None,
                    "dist": {"p10_mm": _mm(pcts.get("p10")), "p25_mm": _mm(pcts.get("p25")),
                             "p50_mm": _mm(pcts.get("p50")), "p75_mm": _mm(pcts.get("p75")),
                             "p90_mm": _mm(pcts.get("p90")), "mean_mm": _mm(dist.get("mean")),
                             "p_bust": round(dist["p_bust"], 3) if dist.get("p_bust") is not None else None},
                    "band_p10_mm": _mm(pcts.get("p10")),
                    "band_p90_mm": _mm(pcts.get("p90")),
                    "p_bust": round(dist["p_bust"], 3) if dist.get("p_bust") is not None else None,
                    "p_bust_basis": _pb_basis,
                    "factors": _factors(ridge, feats, side=side),
                    "xfv_ungraded": True, "xfv_provisional": True,
                }
                if _pb_lowconf:
                    # No fabricated number: the row kept the grade-only incumbent
                    # odds because its level did not resolve to the measured ladder.
                    entry["p_bust_low_confidence"] = True
                by_player[pk] = entry
                by_mlbam[str(mid)] = grade
                counts[side] += 1

    grades = [e["xfv_grade"] for e in by_player.values()]
    grades.sort()
    def q(pp):
        return grades[min(len(grades) - 1, int(pp * (len(grades) - 1)))] if grades else None
    meta = {
        "generated_at": __import__("datetime").date.today().isoformat(),
        "n_players": len(by_player), "counts": counts,
        "grade_dist": {"median": round(statistics.median(grades), 1) if grades else None,
                       "p75": q(0.75), "p90": q(0.90), "p99": q(0.99), "max": max(grades) if grades else None,
                       "share_le_30": round(sum(1 for g in grades if g <= 30) / len(grades), 3) if grades else None,
                       "n_breakout_ge35": sum(1 for g in grades if g >= 35)},
        "grade_map": _GRADE_MAP, "eval": "data/xfv_ungraded_eval.json", "status": "provisional",
        "p_bust_basis": {"enabled": _thin_pbust_enabled(), "counts": pb_counts,
                         "head": _THIN_PBUST_HEAD if _thin_pbust_enabled() else None,
                         "fit": _THIN_PBUST_FIT,
                         "note": ("p_bust / p_bucket on provisional rows come from the "
                                  "thin-sample conditional fitted on this population's own "
                                  "realized outcomes, not the graded-population grade curve. "
                                  "Surplus dollars stay on the engine's grade-anchored path.")},
        "note": ("Production-only leading indicator for source-UNGRADED roster players. "
                 "Conventional capped FV map; most 20-30, breakouts to the cap. NOT the flagship eFV."),
    }
    out = {"meta": meta, "by_player": by_player, "by_mlbam": by_mlbam}
    if persist:
        OUT_PATH.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
        log.info("wrote %s (%d ungraded players: %d hit / %d pit)",
                 OUT_PATH, len(by_player), counts["hit"], counts["pit"])
    return meta


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if "--eval" in sys.argv:
        rep = evaluate()
        for side, blk in rep["by_side"].items():
            print(f"\n=== {side} (no-FV production model) ===")
            for c, v in blk["cohorts"].items():
                print(f"  {c:22s} n={v['n']:5d} Spearman vs realized WAR = {v['spearman_vs_realized_war']}")
    else:
        meta = build()
        print("ungraded eFV:", meta["n_players"], "players", json.dumps(meta["counts"]))
        print("grade dist:", json.dumps(meta["grade_dist"]))
