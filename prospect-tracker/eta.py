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

These are intentionally coarse ±0.25/0.5 yr nudges on top of the base
travel time, then rounded to the nearest calendar year.  The result is a
heuristic, not a model trained on historical debut timelines — prospects are
too individually variable for high-precision point estimates.  We surface a
confidence tier ("high" / "medium" / "low") so the UI can communicate that.

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
BASE_YEARS: dict[str, float] = {
    "MLB": 0.0,
    "AAA": 0.5,
    "AA":  1.5,
    "A+":  2.5,
    "A":   3.5,
    "Rk":  4.5,
    "CPX": 5.0,
    "DSL": 5.5,
}

# ── Expected age at each level (FanGraphs / BA convention) ─────────────────
EXPECTED_AGES: dict[str, float] = {
    "A":   21.0,
    "A+":  22.0,
    "AA":  23.0,
    "AAA": 24.0,
    "Rk":  19.0,
    "CPX": 18.5,
}

# ── Level-typical performance benchmarks ───────────────────────────────────
# OPS and ERA norms at each level — rough MiLB averages.
LEVEL_OPS_NORM: dict[str, float] = {
    "Rk":  .750, "CPX": .740, "A": .730, "A+": .720, "AA": .710, "AAA": .730,
}
LEVEL_ERA_NORM: dict[str, float] = {
    "Rk":  4.20, "CPX": 4.30, "A": 4.00, "A+": 3.80, "AA": 3.70, "AAA": 4.00,
}


@dataclass
class ETAResult:
    eta_year: int | None      # projected debut calendar year, or None
    confidence: str           # "high" | "medium" | "low" | "unknown"
    base_years: float | None  # years from current level before any adjustments
    perf_adj: float           # performance adjustment applied
    age_adj: float            # age-for-level adjustment applied
    fv_adj: float             # FV grade adjustment applied


def estimate_eta(
    current_level: str | None,
    age: float | None,
    is_pitcher: bool,
    fv: float | None,
    stats: dict | None,
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
                    norm = LEVEL_ERA_NORM.get(current_level, 4.00)
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
                    norm = LEVEL_OPS_NORM.get(current_level, .720)
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
    if age is not None and current_level in EXPECTED_AGES:
        expected = EXPECTED_AGES[current_level]
        diff = age - expected               # positive = old for level
        if diff >= 3.0:
            age_adj = -0.75
        elif diff >= 2.0:
            age_adj = -0.50
        elif diff >= 1.0:
            age_adj = -0.25
        elif diff <= -2.0:
            age_adj = +0.50                 # very young for level
        elif diff <= -1.0:
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

    # ── Combine and clamp ──────────────────────────────────────────────────
    total = base + perf_adj + age_adj + fv_adj
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
    )
