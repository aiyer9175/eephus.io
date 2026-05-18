"""
Age-vs-level scoring.

The scouting heuristic: every minor-league level has a typical age range.
A prospect who is meaningfully younger than that baseline is a plus
signal; meaningfully older is a minus. FanGraphs and Baseball America
both note "young for level" in their writeups using roughly these
baselines:

    A       21.0
    A+      22.0
    AA      23.0
    AAA     24.0

Rookie complex leagues are intentionally mixed-age (ACL/FCL/DSL), so
we don't color those — they get tier "unknown".

We bucket the (age - baseline) difference into five tiers matching the
language scouts actually use:

    diff <= -2.0   very-young   "very young for level"
    diff <= -0.5   young        "young for level"
    diff <   0.5   neutral      "age-appropriate"
    diff <   2.0   old          "old for level"
    diff >=  2.0   too-old      "too old for level"

The diff is preserved alongside the tier so the front-end can render
something like "Age 19.4 at AA · 3.6 yrs young" or just color the pill.
"""

from __future__ import annotations

from dataclasses import dataclass


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


def score_age_vs_level(age: float | None, level: str | None) -> AgeVsLevel:
    if age is None or not level or level not in LEVEL_BASELINES:
        return AgeVsLevel(tier="unknown", diff=None)
    diff = round(age - LEVEL_BASELINES[level], 1)
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
