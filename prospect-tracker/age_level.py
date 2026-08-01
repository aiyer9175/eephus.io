# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""
Age-vs-level scoring.

The scouting heuristic: every minor-league level has a typical age range.
A prospect who is meaningfully younger than that baseline is a plus
signal; meaningfully older is a minus.

Baselines used to be hard-coded (FanGraphs convention: A=21, A+=22,
AA=23, AAA=24). Since we now track every player at every level through
their `career_stats`, we instead compute the *empirical* median age at
each level from the last 2 seasons in `level_norms.compute_level_norms`,
and the exporter passes those numbers in.

The static baseline below stays as a safety net for code paths that call
this function without supplying their own (tests, ad-hoc scripts).

Rookie complex leagues are intentionally mixed-age (ACL/FCL/DSL), so
we don't color those — they get tier "unknown".

Tier bucketing (unchanged):

    diff <= -2.0   very-young   "very young for level"
    diff <= -0.5   young        "young for level"
    diff <   0.5   neutral      "age-appropriate"
    diff <   2.0   old          "old for level"
    diff >=  2.0   too-old      "too old for level"
"""

from __future__ import annotations

from dataclasses import dataclass


# Default baselines — only used when caller doesn't pass empirical numbers.
LEVEL_BASELINES: dict[str, float] = {
    "A":   21.0,
    "A+":  22.0,
    "AA":  23.0,
    "AAA": 24.0,
}


@dataclass
class AgeVsLevel:
    tier: str          # "very-young" | "young" | "neutral" | "old" | "too-old" | "unknown"
    diff: float | None  # age - baseline; None when we can't score (rookie level, missing age, etc.)


def score_age_vs_level(age: float | None, level: str | None,
                       baselines: dict[str, float] | None = None) -> AgeVsLevel:
    """
    Score a prospect against the typical age at their current level.

    Args:
        age      : prospect's current age (decimal years).
        level    : their highest-reached level this season ("A", "A+", etc.).
        baselines: optional override map {level: median_age}. When omitted
                   we use the static `LEVEL_BASELINES`. The pipeline injects
                   empirical medians computed from `career_stats`.
    """
    use = baselines if baselines is not None else LEVEL_BASELINES
    if age is None or not level or level not in use:
        return AgeVsLevel(tier="unknown", diff=None)
    diff = round(age - use[level], 1)
    if diff <= -2.0:
        tier = "very-young"
    elif diff <= -0.5:
        tier = "young"
    elif diff < 0.5:
        tier = "neutral"
    elif diff < 2.0:
        tier = "old"
    else:
        tier = "too-old"
    return AgeVsLevel(tier=tier, diff=diff)
