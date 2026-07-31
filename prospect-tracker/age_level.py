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

C3 audit 2026-07-30 - the 5 tiers stay a STAIRCASE, deliberately, and here is why
(recorded so the next continuity pass does not re-open it):

  * The NUMBER is already continuous, and the number is what every SCORING consumer
    reads. `diff` feeds $DvM+'s trajectory term (storage: age_term = -diff), the GRPO
    `age_vs_level` feature, and bayes_trade_value.age_for_level_buffer
    (years_young * 0.30, capped) - all of them linear in diff, none of them tier-aware.
  * Nothing in the BOARD ORDERING reads a tier. The board tie-break (`storage._tbs_proxy`)
    is tool composite + Statcast+ + the '+' upside flag + an IL drag; it never touches
    age-for-level, so the "TBS staircase reorders the board" hypothesis is false and
    measured board movement from this file is exactly zero rows.
  * The tiers are a DISPLAY LABEL (plus two org counters and the spotlight riser/faller
    gate), and a label must agree with the number printed beside it. `diff` is rounded to
    1dp for display, so bucketing the UNROUNDED value would put "-2.0 / young for level"
    on 155 of 4,254 live cards - trading a phantom problem for a visible contradiction.
    Bucketing the rounded value is the correct choice for a label, not an oversight.

Real defect found next door and NOT fixable here: storage.py's org rollup tests
`avl.tier == "very-old"`, a tier this module never emits (it emits "too-old"), so
`very_old_count` is permanently 0 and the farm Readiness net (very_young - very_old) is
one-sided. Reported to the storage owner; fixing it from this side by renaming the tier
would break every other consumer of the documented tier vocabulary.
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
