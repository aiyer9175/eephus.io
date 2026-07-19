# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Proprietary and confidential

"""Canonical affiliated-baseball level ladder for Advancement Pace+ (descriptive only).

LEVEL_MAP_VERSION governs the ladder ordering and the statsapi sportId mapping.
MLB is deliberately NOT a rung of the MiLB-only ladder: the public statistic
describes progression through the affiliated minors; the MLB debut is recorded
as a terminal event, not an advancement step, so pre-debut and post-debut
players are scored on the same scale.

Known aggregations at sportId grain (statsapi):
  - sportId 16 ("Rookie") aggregates ACL, FCL, and DSL complex leagues. DSL vs
    domestic complex cannot be separated at this grain; entry age + pathway
    carry that distinction into the peer baseline instead.
  - Low-A / Single-A naming changes (2021 realignment) are absorbed by sportId:
    14 is the low full-season level in every season, 13 the high full-season level.
  - Short-season leagues (pre-2021 NYPL/Pioneer etc.) report under their
    historical sportIds; anything outside {11,12,13,14,16} is excluded and the
    exclusion is counted in the lineage report.
  - Rehab assignments, fall/winter leagues, independent and foreign leagues,
    and spring training are NOT in the season-line sources and therefore cannot
    create advancement steps. Rehab games at a lower level appear inside that
    season's level PA totals only; the highest-meaningful-level construction
    (see raw_pace) means a rehab stint can never reduce a player's ladder height.
"""

LEVEL_MAP_VERSION = "1.0.0"

# statsapi sportId -> level code
SPORT_TO_LEVEL = {11: "AAA", 12: "AA", 13: "A+", 14: "A", 16: "Rk"}

# ladder height (MiLB-only score). MLB kept out of the rung scale.
LEVEL_RANK = {"Rk": 1, "A": 2, "A+": 3, "AA": 4, "AAA": 5}

LADDER = ["Rk", "A", "A+", "AA", "AAA"]  # bottom -> top
MAX_RANK = LEVEL_RANK["AAA"]

LEVEL_LABEL = {
    "Rk": "Complex / Rookie",
    "A": "Low-A",
    "A+": "High-A",
    "AA": "Double-A",
    "AAA": "Triple-A",
}
