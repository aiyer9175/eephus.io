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

from dataclasses import dataclass
from datetime import date


# ── Base years remaining by current level ──────────────────────────────────
# Calibrated to approximate median time from each level to MLB debut based on
# common scout / front-office rules of thumb.  Expressed in fractional years.
# CPX absorbs what used to be the generic "Rk" bucket — those leagues are
# the same thing post-2021 — and DSL stays separate because foreign-rookie
# prospects average a longer development arc.
BASE_YEARS: dict[str, float] = {
    "MLB": 0.0,
    "AAA": 0.5,
    "AA":  1.5,
    "A+":  2.5,
    "A":   3.5,
    "CPX": 4.8,
    "DSL": 5.5,
}

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


@dataclass
class ETAResult:
    eta_year: int | None      # projected debut calendar year, or None
    confidence: str           # "high" | "medium" | "low" | "unknown"
    base_years: float | None  # years from current level before any adjustments
    perf_adj: float           # performance adjustment applied
    age_adj: float            # age-for-level adjustment applied
    fv_adj: float             # FV grade adjustment applied
    # Health adjustment in years. Positive = ETA pushed back due to
    # recent injuries / post-TJ recovery; 0 = no impact.
    health_adj: float = 0.0


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
    """
    today_year = date.today().year

    # Use empirical norms when supplied; otherwise fall back to the static
    # tables for callers (tests, ad-hoc scripts) that don't compute them.
    age_norm = expected_ages if expected_ages is not None else EXPECTED_AGES
    ops_n    = ops_norm     if ops_norm     is not None else LEVEL_OPS_NORM
    era_n    = era_norm     if era_norm     is not None else LEVEL_ERA_NORM

    # ── Already in the majors ───────────────────────────────────────────────
    if current_level == "MLB":
        return ETAResult(eta_year=today_year, confidence="high",
                         base_years=0.0, perf_adj=0.0, age_adj=0.0, fv_adj=0.0)

    perf_adj = 0.0
    age_adj  = 0.0
    fv_adj   = 0.0
    signals  = 0          # track how many signals we have for confidence

    # ── Base years from level ───────────────────────────────────────────────
    base = BASE_YEARS.get(current_level) if current_level else None

    if base is None:
        # No level → fall back to MLB debut age heuristic
        if age is None:
            return ETAResult(eta_year=None, confidence="unknown",
                             base_years=None, perf_adj=0.0, age_adj=0.0, fv_adj=0.0)
        base = max(0.0, 24.5 - age)
    else:
        signals += 1

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
    if age is not None and current_level in age_norm:
        expected = age_norm[current_level]
        diff = age - expected
        if diff <= -3.0:
            age_adj = -0.75   # 3+ years young-for-level: elite fast-track
        elif diff <= -2.0:
            age_adj = -0.50
        elif diff <= -1.0:
            age_adj = -0.25
        elif diff >= 3.0:
            age_adj = +0.75   # 3+ years old-for-level: organizational filler
        elif diff >= 2.0:
            age_adj = +0.50
        elif diff >= 1.0:
            age_adj = +0.25
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

    # ── Health adjustment ──────────────────────────────────────────────────
    # Post-TJ recovery typically costs a pitcher 12-18 months of game
    # time, and chronic-injury prospects miss enough playing time that
    # the FV-to-MLB pipeline takes longer. We push the ETA back when:
    #   * is_post_tj=True and surgery is within ~18 months of today
    #     (the bulk of the recovery window). Add 1.0 year for pitchers.
    #   * the 24-month IL-stint count is 3+ — chronic profile. Add 0.5.
    #   * total IL days in last 24 months are 200+ — Add 0.5 on top.
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
        if (health.get("il_stints_24mo") or 0) >= 3:
            health_adj += 0.5
        if (health.get("il_days_24mo") or 0) >= 200:
            health_adj += 0.5
        # Don't double-count: cap at 1.5y so a chronically injured but
        # not currently-recovering player still has a usable forecast.
        health_adj = min(1.5, health_adj)
        if health_adj > 0:
            signals += 1  # contributes to confidence-tier counting

    # ── Combine and clamp ──────────────────────────────────────────────────
    total = base + perf_adj + age_adj + fv_adj + health_adj
    total = max(0.0, total)                 # can't arrive in the past
    eta_year = today_year + round(total)

    if signals >= 3:
        confidence = "high"
    elif signals >= 2:
        confidence = "medium"
    else:
        confidence = "low"

    return ETAResult(
        eta_year=eta_year,
        confidence=confidence,
        base_years=base,
        perf_adj=round(perf_adj, 2),
        age_adj=round(age_adj, 2),
        fv_adj=round(fv_adj, 2),
        health_adj=round(health_adj, 2),
    )
