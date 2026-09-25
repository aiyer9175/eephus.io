# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""
MLB ETA projection.

Produces a rough "what year will this prospect reach the majors?" estimate
using four signals we already have in the DB:

  1. Current level  — the baseline travel time to MLB (AAA ≈ 0.5 yr, etc.)
  2. Performance    — ERA/OPS relative to level-typical values; dominating a
                      level pulls the ETA in, struggling pushes it out
  3. Age-for-level  — old for level → fast-tracked; young → may slow down
  4. FV grade       — scouts' overall assessment; high-grade prospects get
                      more organisational urgency behind their development

The "level-typical" age and performance baselines are EMPIRICAL — computed
at export time by `level_norms.compute_level_norms` over the most recent
two seasons of `career_stats`. This sharpens the "young for level" signal
considerably: empirical AAA median age is ~25.8, not the 24.0 the old
hardcoded baseline assumed, so a 22-year-old at AAA gets a stronger
fast-track bonus than before. Static fallbacks below are used only when
the caller didn't pass empirical norms or when a level has too few
samples.

These adjustments are intentionally coarse ±0.25/0.5 yr nudges on top of
the base travel time, then rounded to the nearest calendar year. The
result is a heuristic, not a model trained on historical debut timelines.

Confidence levels:
  high   — current level + performance stats + age available
  medium — current level + age OR current level + stats (one signal missing)
  low    — level only, or fell back to age/FV estimation with no level
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import date


# ── Base years remaining by current level ──────────────────────────────────
# v39 — FIRST MEASURED RECALIBRATION (model-audit Phase 4b, WS-8;
# eta_backtest.py → data/eta_eval.json). Bases are now the Kaplan-Meier
# MEDIAN years-to-debut per level over the 2018-2023 vintage cohorts
# (n=7,205 listings): debuts are events, still-active non-debuted
# players censor at observed follow-up, washed-out players stay in the
# risk set forever (known never-debuts) — so these are NOT survivor
# medians; the bust mass drags them honestly slower. Forward-chained
# verdict vs the old v18/v38 hand-set table on identical debuted rows:
# MAE 1.448 vs 1.993, within-1y 0.571 vs 0.405 (n=2,778). Disclosed
# trade: overdue censored-actives 803→904 of 2,345.
# DSL keeps the hand-set 7.5 — its debut curve never crosses 50%
# (cure fraction dominates; only 2 of 124 vintage-listed DSL prospects
# debuted in-window), so the KM median is undefined there.
# v18 spacing rationale (level dominates the ±adjustments) still holds:
# the AAA→A gap is 3.0y and the floor logic scales with the base.
#
# RE-GATED 2026-08-04 and HELD. The nightly eta_backtest rerun moved the
# artifact's full-window KM table underneath this table at two cells:
# A+ 3.0→3.25 and CPX 4.25→4.5. Both are ROUNDING-BOUNDARY crossings, not
# a change of belief: the raw (unrounded) KM medians are A+ 3.19 against a
# 3.125 quantization boundary and CPX 4.40 against a 4.375 boundary, i.e.
# CPX crossed by 0.025 yr (about 9 days). The drift comes from cohort
# accounting, not from new debuts: censored_active went 2,171→2,315 while
# debuted moved only 4,138→4,143, so fresh still-active non-debuted rows
# entered the risk set and pushed the survival curve later.
#
# The refit was scored against the SAME criterion the v39 ship was decided
# on (forward-chained, live estimate_eta path, identical rows; debuted MAE
# and within-1y must BOTH beat the incumbent). It loses both legs:
#
#   table                    MAE     within-1y   bias     overdue
#   incumbent v39 (this)     1.440   0.579       +1.088   345
#   KM refit full-window     1.490   0.561       +1.161   331
#   only A+ 3.0→3.25         1.481   0.563       +1.139   332
#   only CPX 4.25→4.5        1.448   0.576       +1.110   344
#   v38 frozen (legacy)      1.940   0.426       +1.746   242
#   (n=3,454 debuted / 958 censored-active on identical rows)
#
# Paired bootstrap on the refit: dMAE +0.0495, CI95 [+0.0408, +0.0585];
# dWithin-1y -0.0185, CI95 [-0.0237, -0.0136]; P(refit better)=0.000 on
# both. Of the 253 debuted rows the refit moves, 212 get WORSE and 41 get
# better. Each disputed cell loses on its own, so this is not a joint
# artifact. The overdue guardrail is NOT what refuses it: the refit pulls
# ETAs LATER, so overdue FALLS (345 to 331). It is refused on accuracy.
#
# The direction is the whole story: the shipped heuristic already runs
# systematically LATE (bias +1.09 here; LEVEL_BIAS_ADJ below exists to
# shave 0.5y off in production). A refit that pushes two level bases a
# further quarter-year out is moving away from the residual, not toward
# it. For reference, the forward-chained per-vintage KM tables mostly keep
# A+ at 3.0 and want A at 3.5 (EARLIER than the shipped 3.75). The fit's
# own out-of-sample preference is earlier, which the full-window refit's
# rounding inverts.
#
# Declined blast radius: adopting the refit would have moved 7.79% of
# scoreable cohort rows (335 of 4,301) one year LATER, concentrated
# entirely in the two disputed levels (A+ 241/1,014 = 23.8%, CPX 94/394 =
# 23.9%); every other level is byte-identical.
BASE_YEARS: dict[str, float] = {
    "MLB": 0.0,
    "AAA": 0.75,
    "AA":  1.5,
    "A+":  3.0,
    "A":   3.75,
    "CPX": 4.25,
    "DSL": 7.5,
}

# Per-level final bias shave (2026-06-25). The heuristic ran systematically LATE
# on debuted players (forward-chained residual ~+1yr, +2 at A+, +4 at DSL - the
# KM recalibration cut the global bias 1.85->1.03 but left it uncorrected). A
# conservative, shrunk, forward-chained -0.5yr shave at every minor level pulls
# debuted ETAs earlier: eta_backtest debuted MAE 1.44->1.23, within-1y
# 0.58->0.66, bias 1.09->0.75. CONSERVATIVE on the survivor-bias guardrail: cap
# 0.5 keeps the overdue (censored-active that "comes due") balloon to ~+99,
# in line with the previously-accepted KM recalibration (+101); higher caps /
# per-level differentiation chased more accuracy but ballooned overdue (+171).
# Passed explicitly by the live caller (storage.py); NOT applied in the backtest
# champion so the gate stays apples-to-apples.
LEVEL_BIAS_ADJ: dict[str, float] = {
    "AAA": 0.5, "AA": 0.5, "A+": 0.5, "A": 0.5, "CPX": 0.5, "DSL": 0.5,
}

# S2 eta-hazard-lite 40-man shave (W-SURPLUS S2, PASSED its gate 2026-07-24, held OFF that
# cycle, re-verified and flipped 2026-07-29). A player already on the 40-man is closer to
# the majors than his level alone implies, and the heuristic did not know it.
#
# These values are the PRODUCTION-frame forward-chained refit, NOT
# data/eta_hazard_eval.json:shippable_full_window_shave. The distinction is load-bearing:
# the lab's champion runs estimate_eta WITHOUT LEVEL_BIAS_ADJ while production runs it WITH,
# so the artifact's table was fitted against a model production does not run. AAA is 0.0 on
# purpose. Once the 0.5 level-bias shave above is applied, the median AAA 40-man residual is
# exactly 0 and the mechanism correctly asks for nothing; shipping the artifact's 0.964 would
# apply a SECOND shave to the 32 of 54 live rows that no longer need one.
#
# A and A+ sit at the a-priori CAP of 1.0 in every vintage against median residuals of 2.0,
# so their magnitude is a conservative BOUND rather than an estimate.
#
# Correcting the frame shrinks the measured effect 43% (d MAE -0.084 -> -0.048) and cleans it
# up at the same time: the zero-information twin falls from 30-40% of the effect to 10-14%.
# Bootstrap CI95 [-0.0529, -0.0256] on MAE and [+0.0116, +0.0253] on within-1yr, both
# P=1.000, permutation p=0.000, 5 of 5 folds agreeing.
#
# Passed by storage.py ONLY for rows whose roster_status carries on_40_man; every other row
# passes None and is byte-identical.
FORTYMAN_ADJ: dict[str, float] = {"AAA": 0.0, "AA": 0.97, "A+": 1.0, "A": 1.0}

# FanGraphs-blend arms (registered 2026-09-25, docs/eta-2026-09-25/ETA_FG_BLEND_GATE.md).
# DEFAULT OFF. None serves the champion unchanged; "A" or "B" serves the blend arm of that
# name for every prospect whose CURRENT FanGraphs list entry publishes an eta_year:
#   arm A: max(floor_year, rnd(0.5 x champion + 0.5 x FanGraphs))
#   arm B: max(floor_year, rnd(0.5 x champion + 0.5 x FanGraphs) - on40)
# where rnd rounds half up and on40 is 1 for a prospect already on the 40-man. Everyone
# else keeps the champion. The weight and the one-year 40-man shift are FIXED, chosen on the
# research lanes' development vintages (lists 2017-2019 and 2022-2023: arm A MAE 0.971 vs
# champion 1.130, arm B 0.953, overdue +52 and +0 against the +110 guardrail). Those
# vintages are spent; the gate's one look is on the fresh 2024 list on or after 2026-09-28.
# Flipping this flag is the owner's call after that look, never the gate's.
ETA_FG_BLEND_ARM: str | None = None
FG_BLEND_ARMS = ("A", "B")
FG_BLEND_WEIGHT = 0.5
FG_BLEND_FORTYMAN_SHIFT = 1

# v38 — Item-4 ETA rebalance: shift weight from current level onto age.
# The level base is modestly de-weighted (×0.90 — a ~10% compression of the
# level term, so two players at different levels sit a touch closer and the
# age-for-level term carries more of the differentiation), and the age_adj
# tiers below are widened ~1.5×. Net effect: within ONE level tier, a young
# prospect (e.g. a 19yo at High-A) now projects meaningfully earlier than an
# old-for-level peer (e.g. a 24yo at High-A) instead of nearly tying them.
# The young-floor still guards against absurd over-compression.
_LEVEL_BASE_WEIGHT = 0.90

# ── C3 2026-07-30: continuous age-for-level ETA adjustment (DEFAULT OFF) ──────
# The shipped age_adj is a nine-tier STAIRCASE on the integer part of
# `diff = age - level_median`, so it jumps 0.35 to 0.40 yr of projected ETA at every
# integer boundary: diff -0.99 and diff -1.00 are a hundredth of a year apart in age
# and 0.40 yr apart in forecast ETA. The knot table below is the SAME function
# evaluated at those boundaries, linearly interpolated between them and clamped past
# +/-4, so the staircase's value at every boundary is preserved exactly and only the
# interior is smoothed. The one deliberate difference is the dead zone: the staircase
# returns a flat 0.0 across the whole open interval (-1, +1), the ramp passes through
# (0, 0) instead, so a 0.7-yr-old-for-level prospect gets 0.245 yr of ETA rather than
# nothing.
#
# DEFAULT OFF and the gate is OWED, not passed. ETA is a forecast with censored
# outcomes, so its arbiter is eta_backtest.py's KM/censoring-aware protocol, which needs
# a resolved-cohort rebuild this lane is not permitted to run. Flipping this flag without
# that backtest would ship an unmeasured change to every ETA on the site.
# Registered in docs/efv-2026-07-30/EFV_LANE_GATES.md as arm C3-ETA (gate OWED).
AGE_ADJ_CONTINUOUS = False
# (diff, age_adj) knots == the shipped staircase evaluated at its own tier boundaries.
_AGE_ADJ_KNOTS: tuple[tuple[float, float], ...] = (
    (-4.0, -1.50), (-3.0, -1.15), (-2.0, -0.80), (-1.0, -0.40), (0.0, 0.0),
    (1.0, +0.35), (2.0, +0.70), (3.0, +1.00), (4.0, +1.25),
)


def age_adj_for_diff(diff: float) -> float:
    """Age-for-level ETA adjustment. Staircase (shipped) or, with
    AGE_ADJ_CONTINUOUS, the linear interpolation of the same knots."""
    if not AGE_ADJ_CONTINUOUS:
        if diff <= -4.0:
            return -1.50
        if diff <= -3.0:
            return -1.15
        if diff <= -2.0:
            return -0.80
        if diff <= -1.0:
            return -0.40
        if diff >= 4.0:
            return +1.25
        if diff >= 3.0:
            return +1.00
        if diff >= 2.0:
            return +0.70
        if diff >= 1.0:
            return +0.35
        return 0.0
    if diff <= _AGE_ADJ_KNOTS[0][0]:
        return _AGE_ADJ_KNOTS[0][1]
    if diff >= _AGE_ADJ_KNOTS[-1][0]:
        return _AGE_ADJ_KNOTS[-1][1]
    for (x0, y0), (x1, y1) in zip(_AGE_ADJ_KNOTS, _AGE_ADJ_KNOTS[1:]):
        if x0 <= diff <= x1:
            return round(y0 + (y1 - y0) * (diff - x0) / (x1 - x0), 4)
    return 0.0

# ── Static fallback expected ages — only used when the caller does not
# supply empirical numbers from level_norms (e.g. unit tests).
EXPECTED_AGES: dict[str, float] = {
    "A":   21.0,
    "A+":  22.0,
    "AA":  23.0,
    "AAA": 24.0,
    "CPX": 18.5,
    "DSL": 18.0,
}

LEVEL_OPS_NORM: dict[str, float] = {
    "DSL": .720, "CPX": .740, "A": .730, "A+": .720, "AA": .710, "AAA": .730,
}
LEVEL_ERA_NORM: dict[str, float] = {
    "DSL": 4.40, "CPX": 4.30, "A": 4.00, "A+": 3.80, "AA": 3.70, "AAA": 4.00,
}

# ── All-Star Break — anchor for the "half-season elapsed" ETA tweak ────────
# MLB's actual ASG date floats year-to-year (~Jul 11-17 across recent
# seasons). Using a stable Jul 15 cutoff for the H1/H2 split. A snapshot
# taken on or after this date is treated as "post-break" — the prospect
# has effectively consumed half of their current level's season already,
# so their ETA gets a small pull-forward (see `HALF_SEASON_ADJ` below).
# Nov-Feb fall into "offseason" because the MLB calendar doesn't have an
# H1/H2 split in that window — the natural level cycle rolls into the
# next regular season regardless.
ALL_STAR_BREAK_MONTH = 7
ALL_STAR_BREAK_DAY = 15
# How much to subtract from base_years when post-break. Calibrated so a
# AAA prospect (base_years=0.5) gets pulled in roughly half a level-cycle
# — i.e., a late-July AAA player projects for a Sep call-up window or an
# early-next-year debut, not a full-year-from-now debut.
HALF_SEASON_ADJ = -0.25


def season_phase(snapshot_date) -> str:
    """Return one of 'pre_break' | 'post_break' | 'offseason' for a
    given date. None / empty → 'pre_break' (conservative default —
    treats unknown timing as start-of-season, so the H1/H2 adjustment
    doesn't fire spuriously)."""
    if not snapshot_date:
        return "pre_break"
    try:
        if hasattr(snapshot_date, "month") and hasattr(snapshot_date, "day"):
            d = snapshot_date
        else:
            d = date.fromisoformat(str(snapshot_date)[:10])
    except (TypeError, ValueError):
        return "pre_break"
    if d.month in {11, 12, 1, 2}:
        return "offseason"
    if (d.month, d.day) >= (ALL_STAR_BREAK_MONTH, ALL_STAR_BREAK_DAY):
        return "post_break"
    return "pre_break"


@dataclass
class ETAResult:
    eta_year: int | None      # projected debut calendar year, or None
    confidence: str           # "high" | "medium" | "low" | "unknown"
    base_years: float | None  # years from current level before any adjustments
    perf_adj: float           # performance adjustment applied
    age_adj: float            # age-for-level adjustment applied
    fv_adj: float             # FV grade adjustment applied
    # v29: Statcast+ adjustment in years. Strong (>=122) shaves 0.25;
    # elite (≥143) shaves 0.5; weak (≤77) adds 0.25. 0.0 when the prospect
    # has no tracked Statcast data. Cuts re-mapped 2026-08-07 with the SC+
    # re-standardization; the populations they select are unchanged.
    statcast_plus_adj: float = 0.0
    # Health adjustment in years. Positive = ETA pushed back due to
    # recent injuries / post-TJ recovery; 0 = no impact.
    health_adj: float = 0.0
    # H1/H2 adjustment in years. Post-All-Star-break snapshots subtract
    # ~0.25 years from base — a AA prospect in late July has burned
    # roughly half their AA year already. Org-promotion tendency
    # (when available) scales the magnitude — see
    # `_org_promotion_phase_weight`. 0.0 in pre-break / offseason for
    # neutral orgs.
    half_season_adj: float = 0.0
    # Which half of the season the snapshot was taken in:
    # "pre_break" | "post_break" | "offseason". Surfaced on the ETA
    # breakdown panel so users see why an in-season ETA differs from
    # a preseason one.
    season_phase: str = "pre_break"
    # Org promotion-phase tendency context (only set when the caller
    # passed `org_promotion_tendency` AND the multiplier deviated from
    # 1.0). Surfaced on the ETA panel so users can see e.g. "TBR
    # promotes 72% in H2 → ETA pulled in harder". None when no data.
    org_promo_h1_rate: float | None = None
    org_promo_h2_rate: float | None = None
    org_promo_weight:  float = 1.0   # 1.0 = neutral / no adjustment
    # v31.8 — Half-year debut bucket. "early" = Apr-Jun (H1) debut
    # projected; "late" = Jul-Sep (H2). Derived from:
    #   * fractional part of `total` years (>0.5 → leans late this year)
    #   * org H1/H2 tendency (H2-heavy → late; H1-heavy → early)
    #   * current level (AAA → early bias; A/A+ → late bias when total
    #     years rounds to a year out)
    # None when ETA itself is None (insufficient signal).
    eta_half: str | None = None      # "early" | "late" | None
    # S2 eta-hazard-lite (2026-07-24 cycle, W-SURPLUS S2): years shaved off
    # the final travel time because the player was ALREADY 40-man-selected
    # at the snapshot (historical selection dates reconstructed from the
    # .cache/mlb_transactions SE "selected the contract" events). 0.0 unless
    # the caller passed fortyman_adj (default None = OFF, byte-identical).
    # Appended LAST so existing field order is untouched.
    fortyman_adj_applied: float = 0.0
    # True when the calendar floor rolled a current-year ETA to next year's early
    # window because the MLB regular season is over (census M01-05, 2026-09-24).
    # Appended after fortyman_adj_applied for the same reason.
    season_end_roll: bool = False
    # FanGraphs-blend arm (ETA_FG_BLEND_ARM, default off). Set only when apply_fg_blend
    # served a blend: the arm name, FanGraphs' published year and the champion's year
    # before the blend. None on every champion result. Appended last, as above.
    fg_blend_arm: str | None = None
    fg_eta_year: int | None = None
    champion_eta_year: int | None = None


def _as_date(v):
    """A date from a date / datetime / ISO string, or None."""
    if v is None or v == "":
        return None
    try:
        if hasattr(v, "month") and hasattr(v, "day"):
            return date(v.year, v.month, v.day)
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def regular_season_over(snapshot_date, regular_season_end, today_year: int) -> bool:
    """True when `snapshot_date` falls after `regular_season_end` in the current year.

    Both dates must sit in `today_year`: the flag is about a window that has already
    passed at compute time, so a backtest vintage dated in another year never trips it.
    Unknown dates return False (the pre-2026-09-24 behaviour: only Nov/Dec rolls)."""
    d = _as_date(snapshot_date)
    end = _as_date(regular_season_end)
    if d is None or end is None:
        return False
    return d.year == end.year == int(today_year) and d > end


def _org_promotion_phase_weight(phase: str, org_tendency: dict | None) -> float:
    """Compute the H1/H2 adjustment MULTIPLIER for a given org based on
    its historical promotion-phase tendency. Returns 1.0 (neutral) when
    no tendency on file or sample too thin.

      h2_rate ≥ 0.60 (clearly H2-heavy):
        post-break  → 1.4   (pull ETA in harder — org loves H2 calls)
        pre-break   → 0.5   (org rarely promotes in H1; weak adjustment)
      h1_rate ≥ 0.70 (clearly H1-heavy):
        post-break  → 0.6   (org already did most of its calls; soft adj)
        pre-break   → 1.0   (neutral — H1-leaning org may still call up)
      otherwise (balanced ~40-60 split):
        always → 1.0 (no tweak from the baseline adjustment)
    """
    if not org_tendency or org_tendency.get("sample_n", 0) < 5:
        return 1.0
    h1 = float(org_tendency.get("h1_rate") or 0.0)
    h2 = float(org_tendency.get("h2_rate") or 0.0)
    if phase == "post_break":
        if h2 >= 0.60:
            return 1.4
        if h1 >= 0.70:
            return 0.6
        return 1.0
    # pre-break
    if h2 >= 0.60:
        return 0.5
    return 1.0


def org_promotion_tendencies(level_changes: dict, org_by_key: dict, *,
                             min_year: int | None = None, before=None,
                             seasons=None) -> dict[str, dict]:
    """Per-org H1/H2 promotion split and aggressiveness index, the dict estimate_eta
    takes as `org_promotion_tendency` (one org's entry).

    `level_changes` maps player_key to dated events; only kinds "promotion" and "debut"
    count, Nov-Feb events are skipped, events on or after the All-Star-break cutoff are
    H2. Each event is credited to `org_by_key[player_key]` (players without an org are
    skipped). An org with fewer than 5 events gets no entry. The aggressiveness index
    is the org's event count over the median count across orgs with an entry.

    storage.py serves it with `min_year` = this year minus 3 and each player's current
    org. The point-in-time form the org keep-or-remove gate scores
    (docs/eta-2026-09-25/ETA_FG_BLEND_GATE.md section 7) passes `before` (events dated
    strictly before it) and `seasons` (event years allowed), with orgs as of the list
    date."""
    before_d = _as_date(before)
    org_h1: dict[str, int] = {}
    org_h2: dict[str, int] = {}
    for key, events in (level_changes or {}).items():
        org = org_by_key.get(key)
        if not org:
            continue
        for ev in events or []:
            if ev.get("kind") not in {"promotion", "debut"}:
                continue
            date_str = ev.get("date") or ""
            if len(date_str) < 10:
                continue
            try:
                d = date.fromisoformat(date_str[:10])
            except ValueError:
                continue
            if min_year is not None and d.year < min_year:
                continue
            if seasons is not None and d.year not in seasons:
                continue
            if before_d is not None and d >= before_d:
                continue
            if d.month in {11, 12, 1, 2}:
                continue
            if (d.month, d.day) >= (ALL_STAR_BREAK_MONTH, ALL_STAR_BREAK_DAY):
                org_h2[org] = org_h2.get(org, 0) + 1
            else:
                org_h1[org] = org_h1.get(org, 0) + 1
    out: dict[str, dict] = {}
    per_org_n: dict[str, int] = {}
    for org in set(list(org_h1) + list(org_h2)):
        h1 = org_h1.get(org, 0)
        h2 = org_h2.get(org, 0)
        n = h1 + h2
        if n < 5:
            continue
        per_org_n[org] = n
        out[org] = {
            "h1_rate":   round(h1 / n, 3),
            "h2_rate":   round(h2 / n, 3),
            "sample_n":  n,
        }
    if per_org_n:
        sorted_n = sorted(per_org_n.values())
        mid = len(sorted_n) // 2
        if len(sorted_n) % 2 == 1:
            median_n = sorted_n[mid]
        else:
            median_n = (sorted_n[mid - 1] + sorted_n[mid]) / 2
        if median_n > 0:
            for org, n in per_org_n.items():
                out[org]["aggressiveness_index"] = round(n / median_n, 3)
    return out


def estimate_eta(
    current_level: str | None,
    age: float | None,
    is_pitcher: bool,
    fv: float | None,
    stats: dict | None,
    expected_ages: dict[str, float] | None = None,
    ops_norm: dict[str, float] | None = None,
    era_norm: dict[str, float] | None = None,
    health: dict | None = None,
    snapshot_date=None,
    org_promotion_tendency: dict | None = None,
    il_status: dict | None = None,
    statcast_plus: int | None = None,
    base_years: dict[str, float] | None = None,
    level_bias_adj: dict[str, float] | None = None,
    fortyman_adj: float | None = None,
    regular_season_end=None,
) -> ETAResult:
    """
    Return an ETAResult for the given prospect attributes.

    Parameters
    ----------
    current_level : str | None
        Highest level reached this season ("MLB", "AAA", "AA", "A+", "A",
        "Rk", "CPX", "DSL") from the StatLine.
    age : float | None
        Decimal age as of today (e.g. 21.4).
    is_pitcher : bool
        True for SP/RP; False for hitters.
    fv : float | None
        Consensus FV grade (20–80 scale).
    stats : dict | None
        Statline dict with keys like "ops", "era", "k_pct", "bb_pct".
    base_years : dict | None
        Override for the per-level base travel-time table — used by
        eta_backtest.py to score candidate recalibrations through the
        EXACT live code path. None → the module BASE_YEARS.
    fortyman_adj : float | None
        S2 eta-hazard-lite (W-SURPLUS S2, 2026-07-24 cycle; DEFAULT-OFF).
        Years to shave off the FINAL travel time because the player was
        already 40-man-selected at the snapshot (selection dates come from
        the .cache/mlb_transactions SE events; the magnitude is fitted
        forward-chained by the S2 lab, never hardcoded here). None (the
        default) = no adjustment, output byte-identical to the pre-hook
        code path. Applied after level_bias_adj, floored at 0.
    regular_season_end : date | str | None
        The current season's MLB regular-season end date (StatsAPI /seasons).
        When the snapshot falls after it, a current-year ETA rolls to next
        year's early window (the same roll Nov/Dec snapshots already get).
        None (the default, and what eta_backtest passes) leaves the calendar
        floor as it was, so the backtest and eta_eval are byte-identical.
    """
    today_year = date.today().year

    # Use empirical norms when supplied; otherwise fall back to the static
    # tables for callers (tests, ad-hoc scripts) that don't compute them.
    age_norm = expected_ages if expected_ages is not None else EXPECTED_AGES
    ops_n    = ops_norm     if ops_norm     is not None else LEVEL_OPS_NORM
    era_n    = era_norm     if era_norm     is not None else LEVEL_ERA_NORM

    # Determine which half of the season we're in (drives the H1/H2 ETA
    # adjustment below). Defaults to "pre_break" when snapshot_date is
    # missing so old callers get the conservative baseline behavior.
    phase = season_phase(snapshot_date)

    # ── Already in the majors ───────────────────────────────────────────────
    if current_level == "MLB":
        return ETAResult(eta_year=today_year, confidence="high",
                         base_years=0.0, perf_adj=0.0, age_adj=0.0, fv_adj=0.0,
                         half_season_adj=0.0, season_phase=phase,
                         org_promo_h1_rate=(org_promotion_tendency or {}).get("h1_rate"),
                         org_promo_h2_rate=(org_promotion_tendency or {}).get("h2_rate"),
                         org_promo_weight=1.0)

    perf_adj = 0.0
    age_adj  = 0.0
    fv_adj   = 0.0
    statcast_plus_adj = 0.0
    signals  = 0          # track how many signals we have for confidence

    # ── Base years from level ───────────────────────────────────────────────
    base_table = base_years if base_years is not None else BASE_YEARS
    base = base_table.get(current_level) if current_level else None

    if base is None:
        # No level → fall back to MLB debut age heuristic
        if age is None:
            return ETAResult(eta_year=None, confidence="unknown",
                             base_years=None, perf_adj=0.0, age_adj=0.0, fv_adj=0.0)
        base = max(0.0, 24.5 - age)
    else:
        signals += 1
        base *= _LEVEL_BASE_WEIGHT   # item-4: modestly de-weight current level

    # ── Performance adjustment ──────────────────────────────────────────────
    if stats and current_level:
        if is_pitcher:
            era_str = stats.get("era")
            if era_str is not None:
                try:
                    era = float(era_str)
                    norm = era_n.get(current_level, 4.00)
                    delta = era - norm          # positive = worse than average
                    if delta < -1.50:
                        perf_adj = -0.75       # completely dominating
                    elif delta < -0.75:
                        perf_adj = -0.50
                    elif delta < -0.25:
                        perf_adj = -0.25
                    elif delta > 1.50:
                        perf_adj = +0.75       # badly struggling
                    elif delta > 0.75:
                        perf_adj = +0.50
                    elif delta > 0.25:
                        perf_adj = +0.25
                    signals += 1
                except (ValueError, TypeError):
                    pass
        else:
            ops_str = stats.get("ops")
            if ops_str is not None:
                try:
                    ops = float(ops_str)
                    norm = ops_n.get(current_level, .720)
                    delta = ops - norm         # positive = above average
                    if delta > .180:
                        perf_adj = -0.75       # completely dominating
                    elif delta > .100:
                        perf_adj = -0.50
                    elif delta > .030:
                        perf_adj = -0.25
                    elif delta < -.180:
                        perf_adj = +0.75
                    elif delta < -.100:
                        perf_adj = +0.50
                    elif delta < -.030:
                        perf_adj = +0.25
                    signals += 1
                except (ValueError, TypeError):
                    pass

    # ── Age-for-level adjustment ────────────────────────────────────────────
    # Direction follows scouting convention: a prospect who is meaningfully
    # YOUNGER than the empirical level median is being aggressively
    # developed and likely to reach MLB faster (negative adj = earlier ETA).
    # A prospect OLDER than the median has likely been passed over and will
    # take longer if they make it at all (positive adj = later ETA).
    #
    # `diff = age - level_median`; positive = old for level.
    # v31.11 — Extra-young tier added (≤-4yr from level mean). The
    # 19-yo-at-AA case (Jesus Made) sits at diff = -4 and was hitting
    # the old -0.75 ceiling alongside the more common 3-yr-young
    # prospects. The new -1.00 tier lets truly precocious prospects
    # outrun the merely-young cohort by one extra adjustment notch.
    if age is not None and current_level in age_norm:
        expected = age_norm[current_level]
        diff = age - expected
        # v38 — Item-4: age_adj tiers widened ~1.5× so age differentiates ETA
        # strongly WITHIN a level tier (paired with the de-weighted level base
        # above). A 19yo at A+ (diff ≈ −3 → −1.15) now projects ~1.9y earlier
        # than a 24yo at A+ (diff ≈ +2 → +0.70), vs ~1.25y under the old tiers.
        # Tier table + the default-OFF continuous variant live in age_adj_for_diff
        # (C3, 2026-07-30). Byte-identical while AGE_ADJ_CONTINUOUS is False.
        #   4+ yr young-for-level -1.50 (aggressive fast-track) .. 3+ yr -1.15
        #   (elite fast-track) .. 3+ yr OLD +1.00 (org filler) .. 4+ yr +1.25.
        age_adj = age_adj_for_diff(diff)
        signals += 1

    # ── FV adjustment ──────────────────────────────────────────────────────
    if fv is not None:
        if fv >= 65:
            fv_adj = -0.75
        elif fv >= 60:
            fv_adj = -0.50
        elif fv >= 55:
            fv_adj = -0.25
        elif fv <= 35:
            fv_adj = +0.75
        elif fv <= 40:
            fv_adj = +0.50
        elif fv <= 45:
            fv_adj = +0.25
        signals += 1

    # ── Statcast+ adjustment ───────────────────────────────────────────────
    # v29: Statcast+ as a soft ETA modifier. Strong composite shaves 0.25y
    # off the forecast; elite-tier shaves a full 0.5y; weak adds 0.25y.
    # Capped so the modifier never dominates the FV / age signals; it is a
    # tiebreaker, not a re-write. Players without tracked Statcast data get
    # no nudge (a None statcast_plus is treated as "no signal").
    #
    # THRESHOLDS RE-MAPPED 2026-08-07 (130/115/85 -> 143/122/77) because SC+
    # was re-standardized to a true 10 points per sigma and a point is now
    # worth ~1.6x what it was. These numbers are chosen to hold the POPULATION
    # each gate selects, not to look familiar: measured against the same board,
    # 143 keeps 1 player where 130 kept 1, 122 keeps 40 where 115 kept 43, and
    # 77 keeps 60 where 85 kept 56. Leaving them at 130/115/85 would have taken
    # the elite-nudge population from 43 to 589. Widening who gets an ETA nudge
    # is a policy change and needs its own eta_backtest evidence; this is not
    # that. Full map: docs/SC_PLUS_RECALIBRATION_GATE.md section 2.
    if statcast_plus is not None:
        try:
            sc = float(statcast_plus)
            if sc >= 143:
                statcast_plus_adj = -0.50
            elif sc >= 122:
                statcast_plus_adj = -0.25
            elif sc <= 77:
                statcast_plus_adj = +0.25
            signals += 1
        except (TypeError, ValueError):
            pass

    # ── Health adjustment ──────────────────────────────────────────────────
    # Post-TJ recovery typically costs a pitcher 12-18 months of game
    # time, and chronic-injury prospects miss enough playing time that
    # the FV-to-MLB pipeline takes longer. We push the ETA back when:
    #   * is_post_tj=True and surgery is within ~18 months of today
    #     (the bulk of the recovery window). Add 1.0 year for pitchers.
    #   * the 12-month IL-stint count is 3+ — chronic profile. Add 0.5.
    #   * total IL days in last 12 months are 200+ — Add 0.5 on top.
    # Capped at +1.5 years total so a healthy-now prospect doesn't get
    # an obscure forecast for a single bad season.
    health_adj = 0.0
    if health:
        if health.get("is_post_tj"):
            tj_iso = health.get("tj_surgery_date")
            if tj_iso:
                try:
                    tj_date = date.fromisoformat(tj_iso)
                    months_since = max(0, (date.today() - tj_date).days // 30)
                    if months_since < 18:
                        health_adj += 1.0 if is_pitcher else 0.5
                except (TypeError, ValueError):
                    pass
        if (health.get("il_stints_12mo") or 0) >= 3:
            health_adj += 0.5
        if (health.get("il_days_12mo") or 0) >= 200:
            health_adj += 0.5
        # Don't double-count: cap at 1.5y so a chronically injured but
        # not currently-recovering player still has a usable forecast.
        health_adj = min(1.5, health_adj)
        if health_adj > 0:
            signals += 1  # contributes to confidence-tier counting

    # v12 — CURRENT IL push-out. The Sebastian Walcott case: out for
    # the season but ETA still shows the current year because the
    # health profile only tracks rolling-12mo signals, not the
    # immediate "off the field right now" state. Read il_status and
    # add an explicit ETA pushback for active IL stints.
    #   * 60+ days on IL OR season-ending description → +1.0y
    #     (lost the year; ETA pushes to next season minimum)
    #   * 30–59 days → +0.5y (significant chunk of season gone)
    #   * Active IL with unknown duration → +0.5y conservative
    # Stacks on top of `health_adj` but the COMBINED cap stays 2.5y
    # so a chronically-injured-AND-currently-IL prospect doesn't get
    # an absurd forecast.
    if il_status and il_status.get("is_on_il"):
        days = il_status.get("days_on_il")
        desc = (il_status.get("description") or "").lower()
        season_ending = any(kw in desc for kw in (
            "season-ending", "season ending", "out for the season",
            "out for season", "torn acl", "torn ucl", "lis franc",
            "lisfranc",
        ))
        if season_ending or (days is not None and days >= 60):
            health_adj += 1.0
        elif days is not None and days >= 30:
            health_adj += 0.5
        else:
            health_adj += 0.5  # conservative default when duration unknown
        signals += 1
    health_adj = min(2.5, health_adj)

    # ── Half-season-elapsed adjustment ─────────────────────────────────────
    # Post-All-Star-break snapshots: the prospect has effectively burned
    # roughly half of their current level's season already, so their
    # ETA should pull in by ~0.25 years. Doesn't fire in pre-break or
    # offseason (the level cycle naturally rolls into the next regular
    # season either way). When the player's ORG has a clear historical
    # promotion-phase tendency, we scale this baseline adjustment:
    # H2-heavy orgs (TBR, OAK-types that bank Sept call-ups) get a
    # stronger pull-in; H1-heavy orgs (front-loaded promoters) get a
    # weaker one. See `_org_promotion_phase_weight` for the table.
    org_weight = _org_promotion_phase_weight(phase, org_promotion_tendency)
    if phase == "post_break":
        half_season_adj = HALF_SEASON_ADJ * org_weight
    elif phase == "pre_break" and org_weight != 1.0:
        # H2-heavy org during the pre-break window — the baseline H1
        # adjustment is 0, but the org's tendency to call up POST-ASB
        # tells us a pre-ASB prospect is even less likely to debut
        # before the break. Apply a small forward push (positive adj)
        # by inverting the multiplier interpretation: a 0.5 weight
        # under pre-break means "lean toward later debut" → +0.10y.
        half_season_adj = +0.10 if org_weight < 1.0 else 0.0
    else:
        half_season_adj = 0.0

    # ── Combine and clamp ──────────────────────────────────────────────────
    # v31.9 — Per-level FLOOR on the cumulative pull-in. Without this,
    # an elite young-for-level prospect at AA (e.g. Jesus Made — 19yo,
    # AA, ~60 FV) gets age_adj −0.75 + fv_adj −0.50 + perf_adj −0.75
    # which collapses base 2.0 → 0.0 and the model says "Early 2026"
    # even though no 19yo in AA realistically debuts within months.
    # Floor caps the negative pull at a fraction of the level's base
    # years for A/A+/AA (where short ETAs by FV/perf alone are risky)
    # and only 25% for AAA (where short ETAs are believable).
    #
    # v31.11 — Rebalanced YOUNG-floor table. The 0.75-AA young-floor
    # introduced in v31.10 was too conservative — Jesus Made (19yo
    # AA, .920 OPS, 60 FV) was forecast for 2028 Early, but he's a
    # realistic 2027 callup given the quality signals stacking. The
    # new YOUNG floors (AA 0.55, A+ 0.65, A 0.70) let the quality
    # cluster compress base to ~1.1y for that profile — round →
    # 2027 Late, which matches the user-anchored expectation.
    #
    # v31.11 — also adds an ORG-AGGRESSIVENESS multiplier. The
    # `org_promotion_tendency.aggressiveness_index` field (computed in
    # storage.py against the league-median promotion volume) scales
    # the floor: top-quintile aggressive orgs (LAD/TBR-types) get
    # floor × 0.90 — they call prospects up sooner given equal
    # quality. Bottom-quintile conservative orgs get floor × 1.10.
    # League-median orgs get 1.00 (no change). Missing tendency data
    # → 1.00 (neutral fallback).
    #
    # The floor never INCREASES the projection beyond what the model
    # would otherwise produce — only prevents over-compression.
    _LEVEL_PULL_FLOOR_FRAC = {
        "AAA": 0.25,   # AAA prospects can debut very quickly
        "AA":  0.50,
        "A+":  0.55,
        "A":   0.60,
        "CPX": 0.65,
        "DSL": 0.65,
    }
    _LEVEL_PULL_FLOOR_FRAC_YOUNG = {
        "AAA": 0.25,   # 21yo at AAA: keep the existing fast-track room
        "AA":  0.55,   # 19-20yo at AA: ~1.1y minimum given quality stack
        "A+":  0.65,
        "A":   0.70,
        "CPX": 0.75,
        "DSL": 0.75,
    }
    _is_very_young_for_level = age_adj <= -0.50
    _pull_frac = (
        _LEVEL_PULL_FLOOR_FRAC_YOUNG.get(current_level or "")
        if _is_very_young_for_level
        else _LEVEL_PULL_FLOOR_FRAC.get(current_level or "")
    )
    # Org-aggressiveness floor multiplier.
    _org_floor_mult = 1.0
    if org_promotion_tendency:
        _aggr = org_promotion_tendency.get("aggressiveness_index")
        try:
            _aggr_v = float(_aggr) if _aggr is not None else None
        except (TypeError, ValueError):
            _aggr_v = None
        if _aggr_v is not None:
            if _aggr_v >= 1.30:
                _org_floor_mult = 0.90
            elif _aggr_v >= 1.10:
                _org_floor_mult = 0.95
            elif _aggr_v <= 0.70:
                _org_floor_mult = 1.10
            elif _aggr_v <= 0.90:
                _org_floor_mult = 1.05
    raw_total = (base + perf_adj + age_adj + fv_adj + statcast_plus_adj
                 + health_adj + half_season_adj)
    if _pull_frac is not None and base is not None:
        # Floor applies to the level-base + prospect-quality cluster
        # (perf/age/fv/statcast). Health + half-season adjustments
        # apply on top — they're separate timing signals (current IL,
        # in-season elapsed) that should still shift ETA regardless
        # of the prospect's quality ceiling.
        floor = base * _pull_frac * _org_floor_mult
        capped_quality = max(floor,
                              base + perf_adj + age_adj + fv_adj + statcast_plus_adj)
        total = capped_quality + health_adj + half_season_adj
    else:
        total = raw_total
    total = max(0.0, total)                 # can't arrive in the past
    # Per-level bias shave (final intercept): the heuristic runs systematically
    # LATE at the lower levels (debuted-player residual ~+1yr at A/A+); a small,
    # shrunk, forward-chained per-level shave pulls those ETAs earlier. Applied
    # last so it corrects the FINAL travel time, not an intermediate term.
    if level_bias_adj and current_level:
        total = max(0.0, total - float(level_bias_adj.get(current_level, 0.0)))
    # S2 eta-hazard-lite 40-man selection shave (DEFAULT-OFF: fires only when
    # the caller passes a fitted fortyman_adj; applied last, like the bias
    # shave, so it corrects the FINAL travel time).
    _fortyman_applied = 0.0
    if fortyman_adj is not None:
        _fortyman_applied = min(float(fortyman_adj), total)
        total = max(0.0, total - float(fortyman_adj))
    eta_year = today_year + round(total)

    if signals >= 3:
        confidence = "high"
    elif signals >= 2:
        confidence = "medium"
    else:
        confidence = "low"

    # v31.8 — Half-year bucket. Three signals contribute:
    #   1. Fractional part of `total`: if the eta_year rounded UP (i.e.
    #      total - round(total) >= 0), the prospect is closer to the
    #      START of the year → "early". If it rounded DOWN (total
    #      below the integer), they're already at year-end of their
    #      projected debut window → "late".
    #   2. Org promo tendency: H2-heavy orgs nudge toward "late",
    #      H1-heavy toward "early".
    #   3. Current-level bias: AAA prospects with eta within 1 year
    #      tend to debut April-June (rosters get reshuffled at the
    #      Super-2 line in early June); A / A+ prospects projected
    #      for a 2-3yr horizon tend to debut "late" (full level cycle
    #      first).
    # Each signal contributes a small ±0.5 score; final sign picks the
    # bucket. Tie → "early" (slight optimism bias; FA market expects
    # April call-ups for plausible 2H impact bats).
    half_score = 0.0
    frac = total - round(total)
    if frac > 0.15:        # we rounded down — already past the year mark
        half_score += 0.5
    elif frac < -0.15:     # rounded up — at the start of the year
        half_score -= 0.5
    # Org tendency layer.
    if org_promotion_tendency and (org_promotion_tendency.get("sample_n") or 0) >= 5:
        h2 = float(org_promotion_tendency.get("h2_rate") or 0.0)
        h1 = float(org_promotion_tendency.get("h1_rate") or 0.0)
        if h2 >= 0.60:
            half_score += 0.4
        elif h1 >= 0.60:
            half_score -= 0.4
    # Current level bias (only fires when ETA is close).
    if eta_year - today_year <= 2:
        lvl = (current_level or "").upper()
        if lvl in ("AAA",):
            half_score -= 0.3   # AAA prospects debut early
        elif lvl in ("A", "A+", "CPX", "DSL"):
            half_score += 0.3   # lower levels usually full season first
    if total < 0.01:
        # Already MLB-ready; bias to early.
        half_score -= 0.5
    eta_half = "late" if half_score > 0.0 else "early"

    # Calendar floor: never emit a sub-year window that has already passed
    # at compute time. Post-break, a current-year "early" (Apr-Jun) window
    # is gone, so it floors to "late"; once the MLB regular season has ended
    # (the caller passes its end date; Nov/Dec always count) the season
    # itself is over, so a current-year ETA rolls to next year's early window.
    # Jan/Feb "offseason" runs leave current-year "early" alone (April is
    # still ahead).
    # Census M01-05 (2026-09-24): the roll used to wait for November, so from
    # the last regular-season game through October 414 prospects (253 AAA,
    # 160 AA) read "Late <this year>", a window that had closed.
    season_end_roll = False
    if eta_year == today_year:
        if phase == "post_break":
            eta_half = "late"
            if regular_season_over(snapshot_date, regular_season_end, today_year):
                eta_year += 1
                eta_half = "early"
                season_end_roll = True
        elif phase == "offseason":
            try:
                _m = (snapshot_date.month if hasattr(snapshot_date, "month")
                      else date.fromisoformat(str(snapshot_date)[:10]).month)
            except (TypeError, ValueError):
                _m = None
            if _m in (11, 12):
                eta_year += 1
                eta_half = "early"
                season_end_roll = True

    return ETAResult(
        eta_year=eta_year,
        confidence=confidence,
        base_years=base,
        perf_adj=round(perf_adj, 2),
        age_adj=round(age_adj, 2),
        fv_adj=round(fv_adj, 2),
        statcast_plus_adj=round(statcast_plus_adj, 2),
        health_adj=round(health_adj, 2),
        half_season_adj=round(half_season_adj, 2),
        season_phase=phase,
        org_promo_h1_rate=(org_promotion_tendency or {}).get("h1_rate"),
        org_promo_h2_rate=(org_promotion_tendency or {}).get("h2_rate"),
        org_promo_weight=round(org_weight, 2),
        eta_half=eta_half,
        fortyman_adj_applied=round(_fortyman_applied, 2),
        season_end_roll=season_end_roll,
    )

# ── FanGraphs-blend arms (default off; see ETA_FG_BLEND_ARM) ────────────────

def round_half_up(x: float) -> int:
    """floor(x + 0.5): the blend's rounding rule (never Python's banker's round)."""
    return int(math.floor(float(x) + 0.5))


def fg_blend_eta_year(champion_year: int | None, fg_eta_year: int | None,
                      floor_year: int, *, on40: bool = False,
                      arm: str = "A") -> int | None:
    """The registered blend arm's debut year for one prospect.

    `champion_year` is the served champion's year, `fg_eta_year` FanGraphs' published
    year (None when FanGraphs publishes none), `floor_year` the earliest year the
    forecast may name (the list year in the gate; the first open season when served).
    Without a FanGraphs year, or without a champion year, the champion stands."""
    if arm not in FG_BLEND_ARMS:
        raise ValueError(f"unknown ETA blend arm {arm!r}; expected one of {FG_BLEND_ARMS}")
    if champion_year is None or fg_eta_year is None:
        return champion_year
    year = round_half_up(FG_BLEND_WEIGHT * float(champion_year)
                         + (1.0 - FG_BLEND_WEIGHT) * float(fg_eta_year))
    if arm == "B" and on40:
        year -= FG_BLEND_FORTYMAN_SHIFT
    return max(int(floor_year), year)


def fg_eta_year_from_per_source(per_source: dict | None) -> int | None:
    """FanGraphs' published eta_year from a consensus point's per_source map.

    Only a CURRENT FanGraphs entry counts: a source the consensus flags dropped_off
    (the player fell off FanGraphs' list) returns None, as does a missing or
    non-integer year."""
    fg = (per_source or {}).get("fangraphs") or {}
    if not isinstance(fg, dict) or fg.get("dropped_off"):
        return None
    tools = fg.get("tools") or {}
    extras = tools.get("_extras") if isinstance(tools, dict) else None
    if not isinstance(extras, dict):
        return None
    raw = extras.get("eta_year")
    if raw is None or raw == "" or isinstance(raw, bool):
        return None
    try:
        f = float(raw)
    except (TypeError, ValueError):
        return None
    if f != f or f != int(f) or not 1990 <= f <= 2100:
        return None
    return int(f)


def live_floor_year(snapshot_date, regular_season_end, today_year: int) -> int:
    """The earliest debut year a served forecast may name: this year, or next year
    once the regular season is over (the same rule estimate_eta's calendar floor
    applies: a snapshot past the season end, or any November/December snapshot)."""
    d = _as_date(snapshot_date)
    if d is not None and d.year == int(today_year) and d.month in (11, 12):
        return int(today_year) + 1
    if regular_season_over(snapshot_date, regular_season_end, today_year):
        return int(today_year) + 1
    return int(today_year)


def apply_fg_blend(result: ETAResult, fg_eta_year: int | None, *, arm: str | None,
                   on40: bool = False, floor_year: int) -> ETAResult:
    """Serve the blend arm on top of a champion ETAResult.

    `arm` None (the default flag) returns `result` itself, so the served path is
    byte-identical while the flag is off. With an arm, a prospect without a
    FanGraphs year also keeps the champion result untouched. Otherwise the year
    becomes the arm's year and the champion's own year is kept alongside it. The
    sub-year half keeps the champion's bucket (the gate scores whole years only),
    except that a current-year window after the All-Star break reads "late", the
    same calendar floor estimate_eta applies."""
    if arm is None or result.eta_year is None or fg_eta_year is None:
        return result
    year = fg_blend_eta_year(result.eta_year, fg_eta_year, floor_year, on40=on40, arm=arm)
    half = result.eta_half
    if year == date.today().year and result.season_phase == "post_break":
        half = "late"
    return replace(result, eta_year=year, eta_half=half, fg_blend_arm=arm,
                   fg_eta_year=int(fg_eta_year), champion_eta_year=result.eta_year)
