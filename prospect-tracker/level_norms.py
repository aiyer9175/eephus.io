"""
Empirical age + performance benchmarks per MiLB / MLB level.

Computed from the prospect tracker's own `career_stats` rows joined to the
`players.birth_date` column. We compute:

  * Age norms — for every season in the lookback window, take each player's
    age at the season midpoint (Jul 1) and aggregate by level. The mean /
    median / p25 / p75 give us the actual age distribution.

  * Performance norms — average OPS (hitters) and ERA (pitchers) by level
    over the same window.

Why empirical instead of hard-coded?
    The previous baselines were rough "FanGraphs convention" numbers
    (A=21, A+=22, AA=23, AAA=24). They under-estimate AA/AAA by 1-2 years
    because real rosters contain a lot of older org-filler / Quad-A
    veterans the prospect-tracking convention ignored. Using the actual
    league-average age sharpens the "young for level" signal — a 22-year-old
    at AA is genuinely 1.5 years young against an empirical median of 23.5,
    not 1.0 year young against an artificial 23.0.

These norms are recomputed at every export. The frontend gets them under
`level_norms` in the timeseries.json so prospect detail pages can show the
actual benchmark a player is being compared against.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from dataclasses import dataclass


# Minimum playing time at a level for a player's row to count toward the
# benchmark. Filters out single-game promotions / rehab assignments which
# would otherwise drag the average age up at higher levels.
MIN_GAMES_HITTER  = 10
MIN_IP_PITCHER    = 10.0

# How many recent seasons to include. 2 keeps the benchmarks current but
# wide enough to be statistically stable; 1 would over-weight whatever
# happened to be the most recent draft class.
DEFAULT_SEASONS_WINDOW = 2

# Floor on sample size — levels with fewer players than this in the window
# fall back to the static baseline. The DSL is sometimes under-sampled
# because most DSL players aren't tracked as prospects.
MIN_SAMPLE_N = 30


@dataclass
class LevelAgeNorm:
    avg_age: float
    median_age: float
    p25_age: float
    p75_age: float
    sample_n: int


@dataclass
class LevelPerfNorm:
    avg_ops: float | None       # hitters
    avg_era: float | None       # pitchers
    sample_n_ops: int
    sample_n_era: int


# Static fallback baselines — same numbers the codebase used before, kept
# here so a level with too few empirical samples still gets a baseline.
FALLBACK_AGE_BASELINE: dict[str, float] = {
    "DSL": 18.0,
    "CPX": 18.5,
    "Rk":  19.0,
    "A":   21.0,
    "A+":  22.0,
    "AA":  23.0,
    "AAA": 24.0,
    "MLB": 27.5,
}
FALLBACK_OPS_NORM: dict[str, float] = {
    "Rk": .750, "CPX": .740, "A": .730, "A+": .720, "AA": .710, "AAA": .730,
}
FALLBACK_ERA_NORM: dict[str, float] = {
    "Rk": 4.20, "CPX": 4.30, "A": 4.00, "A+": 3.80, "AA": 3.70, "AAA": 4.00,
}


def _parse_float(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _summarize(values: list[float]) -> tuple[float, float, float, float, int]:
    """Return (mean, median, p25, p75, n) — pure-Python percentile."""
    values = sorted(values)
    n = len(values)
    if n == 0:
        return 0.0, 0.0, 0.0, 0.0, 0
    return (
        sum(values) / n,
        values[n // 2],
        values[max(0, n * 1 // 4)],
        values[min(n - 1, n * 3 // 4)],
        n,
    )


def compute_level_norms(
    career_stats: dict[str, list[dict]],
    birth_dates: dict[str, str],
    seasons_window: int = DEFAULT_SEASONS_WINDOW,
    today: date | None = None,
) -> dict[str, dict]:
    """
    Build {level: {age, perf}} dicts from per-player career rows.

    `career_stats`  : {player_key: [season_row, ...]}
    `birth_dates`   : {player_key: 'YYYY-MM-DD'}
    `seasons_window`: how many of the most-recent calendar years to include.
                      We deliberately keep the in-progress current season —
                      its early-season skew is real signal for "what does
                      this level look like right now."
    """
    today = today or date.today()
    cutoff_year = today.year - seasons_window  # inclusive lower bound

    ages_by_level: dict[str, list[float]] = defaultdict(list)
    ops_by_level: dict[str, list[float]] = defaultdict(list)
    era_by_level: dict[str, list[float]] = defaultdict(list)

    for player_key, rows in career_stats.items():
        bd_str = birth_dates.get(player_key)
        if not bd_str:
            continue
        try:
            bd = date.fromisoformat(bd_str)
        except (TypeError, ValueError):
            continue
        for r in rows or []:
            level = r.get("level")
            season = r.get("season")
            if not level or season is None or season < cutoff_year:
                continue
            is_pitcher = bool(r.get("is_pitcher"))
            games = int(r.get("games") or 0)
            ip = _parse_float(r.get("ip"))
            # Skip cup-of-coffee promotions so the average age isn't
            # skewed by a few MLB rehabbers at AAA or a one-start AA promotion.
            if is_pitcher and (ip or 0) < MIN_IP_PITCHER:
                continue
            if not is_pitcher and games < MIN_GAMES_HITTER:
                continue

            # Age at season midpoint — the player's age while actually
            # playing at this level, not their current age.
            mid_season = date(season, 7, 1)
            age_at_season = (mid_season - bd).days / 365.25
            # Drop implausible records (negative age, > 50 yrs).
            if age_at_season < 14 or age_at_season > 50:
                continue
            ages_by_level[level].append(age_at_season)

            if is_pitcher:
                era = _parse_float(r.get("era"))
                if era is not None and 0 < era < 30:
                    era_by_level[level].append(era)
            else:
                ops = _parse_float(r.get("ops"))
                if ops is not None and 0 < ops < 2.0:
                    ops_by_level[level].append(ops)

    out: dict[str, dict] = {}
    for level in set(ages_by_level) | set(ops_by_level) | set(era_by_level):
        mean, med, p25, p75, n_age = _summarize(ages_by_level.get(level, []))
        ops_values = ops_by_level.get(level, [])
        era_values = era_by_level.get(level, [])
        out[level] = {
            "age": (
                {
                    "avg_age":    round(mean, 2),
                    "median_age": round(med,  2),
                    "p25_age":    round(p25,  2),
                    "p75_age":    round(p75,  2),
                    "sample_n":   n_age,
                }
                if n_age >= MIN_SAMPLE_N
                else {
                    # Too few samples — fall back to static baseline.
                    "avg_age":    FALLBACK_AGE_BASELINE.get(level, 22.0),
                    "median_age": FALLBACK_AGE_BASELINE.get(level, 22.0),
                    "p25_age":    FALLBACK_AGE_BASELINE.get(level, 22.0) - 1.0,
                    "p75_age":    FALLBACK_AGE_BASELINE.get(level, 22.0) + 1.0,
                    "sample_n":   n_age,
                    "fallback":   True,
                }
            ),
            "perf": {
                "avg_ops": (
                    round(sum(ops_values) / len(ops_values), 3)
                    if len(ops_values) >= MIN_SAMPLE_N
                    else FALLBACK_OPS_NORM.get(level)
                ),
                "avg_era": (
                    round(sum(era_values) / len(era_values), 2)
                    if len(era_values) >= MIN_SAMPLE_N
                    else FALLBACK_ERA_NORM.get(level)
                ),
                "sample_n_ops": len(ops_values),
                "sample_n_era": len(era_values),
            },
        }
    return out


def age_baselines_from_norms(norms: dict[str, dict]) -> dict[str, float]:
    """Pull a flat {level: median_age} dict from the rich norms structure.
    The median is more robust than the mean against a couple of 30-year-old
    AAA rehabbers skewing the curve up."""
    out: dict[str, float] = dict(FALLBACK_AGE_BASELINE)
    for level, blob in norms.items():
        age = blob.get("age", {})
        out[level] = age.get("median_age", out.get(level, 22.0))
    return out


def ops_norms_from_norms(norms: dict[str, dict]) -> dict[str, float]:
    out = dict(FALLBACK_OPS_NORM)
    for level, blob in norms.items():
        v = (blob.get("perf") or {}).get("avg_ops")
        if v is not None:
            out[level] = v
    return out


def era_norms_from_norms(norms: dict[str, dict]) -> dict[str, float]:
    out = dict(FALLBACK_ERA_NORM)
    for level, blob in norms.items():
        v = (blob.get("perf") or {}).get("avg_era")
        if v is not None:
            out[level] = v
    return out
