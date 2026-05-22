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
    # Hitter rate stats — averages across qualified hitters at the level.
    avg_ops:    float | None
    avg_iso:    float | None       # SLG - AVG
    avg_bb_pct: float | None
    avg_k_pct:  float | None
    # Pitcher rate stats — averages across qualified pitchers at the level.
    avg_era:      float | None
    avg_whip:     float | None
    avg_k_per_9:  float | None
    avg_bb_per_9: float | None
    avg_hr_per_9: float | None
    # Per-stat sample sizes. Kept separate because hr_per_9 only populates
    # for pitcher rows from pipeline runs that include the HR-allowed field,
    # so older rows in the cache can leave it sparse.
    sample_n_ops:    int
    sample_n_era:    int


# Static fallback baselines — same numbers the codebase used before, kept
# here so a level with too few empirical samples still gets a baseline.
# Fallbacks no longer carry an "Rk" entry — that bucket folded into CPX
# with the post-2021 rookie-league cleanup. DSL stays as its own level
# because its age curve runs ~2y younger than CPX and its run
# environment is meaningfully different from US complex ball.
FALLBACK_AGE_BASELINE: dict[str, float] = {
    "DSL": 18.0,
    "CPX": 18.5,
    "A":   21.0,
    "A+":  22.0,
    "AA":  23.0,
    "AAA": 24.0,
    "MLB": 27.5,
}
FALLBACK_OPS_NORM: dict[str, float] = {
    "DSL": .720, "CPX": .740, "A": .730, "A+": .720, "AA": .710, "AAA": .730, "MLB": .720,
}
FALLBACK_ERA_NORM: dict[str, float] = {
    "DSL": 4.40, "CPX": 4.30, "A": 4.00, "A+": 3.80, "AA": 3.70, "AAA": 4.00, "MLB": 4.10,
}

# Static fallback for the expanded rate stats. These are rough league-wide
# averages used only when the empirical sample at a level falls below
# MIN_SAMPLE_N. Hitter ISO scales modestly upward toward AAA; pitcher
# K/9 climbs and HR/9 inflates at the high minors / MLB because hitters
# get better at punishing pitches.
FALLBACK_ISO_NORM: dict[str, float] = {
    "DSL": .115, "CPX": .125, "A": .130, "A+": .135, "AA": .140, "AAA": .155, "MLB": .165,
}
FALLBACK_BB_PCT_NORM: dict[str, float] = {
    "DSL": 11.0, "CPX": 9.5, "A": 9.0, "A+": 8.8, "AA": 8.5, "AAA": 8.5, "MLB": 8.4,
}
FALLBACK_K_PCT_NORM: dict[str, float] = {
    "DSL": 22.0, "CPX": 23.0, "A": 23.5, "A+": 23.0, "AA": 22.5, "AAA": 22.5, "MLB": 22.0,
}
FALLBACK_WHIP_NORM: dict[str, float] = {
    "DSL": 1.45, "CPX": 1.42, "A": 1.38, "A+": 1.34, "AA": 1.31, "AAA": 1.34, "MLB": 1.28,
}
FALLBACK_K9_NORM: dict[str, float] = {
    "DSL": 8.4, "CPX": 8.6, "A": 9.0, "A+": 9.1, "AA": 9.2, "AAA": 9.1, "MLB": 8.9,
}
FALLBACK_BB9_NORM: dict[str, float] = {
    "DSL": 4.3, "CPX": 4.2, "A": 3.7, "A+": 3.5, "AA": 3.3, "AAA": 3.4, "MLB": 3.2,
}
FALLBACK_HR9_NORM: dict[str, float] = {
    "DSL": 0.5, "CPX": 0.7, "A": 0.8, "A+": 0.9, "AA": 1.0, "AAA": 1.2, "MLB": 1.3,
}
# Pitcher K% / BB% — strikeouts and walks as % of batters faced. Modern
# pitching is K-heavy and the values trend upward with level as pitchers
# get better and hitters stay competitive at a higher quality floor.
FALLBACK_PITCHER_K_PCT_NORM: dict[str, float] = {
    "DSL": 21.0, "CPX": 22.0, "A": 23.5, "A+": 24.0, "AA": 24.5, "AAA": 24.0, "MLB": 23.0,
}
FALLBACK_PITCHER_BB_PCT_NORM: dict[str, float] = {
    "DSL": 11.0, "CPX": 10.5, "A": 9.5, "A+": 9.0, "AA": 8.5, "AAA": 8.8, "MLB": 8.3,
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
    # Hitter rate-stat distributions per level.
    ops_by_level:    dict[str, list[float]] = defaultdict(list)
    iso_by_level:    dict[str, list[float]] = defaultdict(list)
    bb_pct_by_level: dict[str, list[float]] = defaultdict(list)
    k_pct_by_level:  dict[str, list[float]] = defaultdict(list)
    # Pitcher rate-stat distributions per level.
    era_by_level:    dict[str, list[float]] = defaultdict(list)
    whip_by_level:   dict[str, list[float]] = defaultdict(list)
    k9_by_level:     dict[str, list[float]] = defaultdict(list)
    bb9_by_level:    dict[str, list[float]] = defaultdict(list)
    hr9_by_level:    dict[str, list[float]] = defaultdict(list)
    # Per-batter pitcher rates — K% / BB% measured against TBF. Modern
    # convention is to report these instead of K/9 / BB/9 because they're
    # less sensitive to starter vs. reliever workload differences.
    pitcher_k_pct_by_level:  dict[str, list[float]] = defaultdict(list)
    pitcher_bb_pct_by_level: dict[str, list[float]] = defaultdict(list)

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
                whip = _parse_float(r.get("whip"))
                if whip is not None and 0 < whip < 5.0:
                    whip_by_level[level].append(whip)
                k9 = _parse_float(r.get("k_per_9"))
                if k9 is not None and 0 < k9 < 25:
                    k9_by_level[level].append(k9)
                bb9 = _parse_float(r.get("bb_per_9"))
                if bb9 is not None and 0 <= bb9 < 15:
                    bb9_by_level[level].append(bb9)
                hr9 = _parse_float(r.get("hr_per_9"))
                if hr9 is not None and 0 <= hr9 < 5:
                    hr9_by_level[level].append(hr9)
                pk = _parse_float(r.get("k_pct"))
                if pk is not None and 0 < pk < 60:
                    pitcher_k_pct_by_level[level].append(pk)
                pbb = _parse_float(r.get("bb_pct"))
                if pbb is not None and 0 <= pbb < 30:
                    pitcher_bb_pct_by_level[level].append(pbb)
            else:
                ops = _parse_float(r.get("ops"))
                if ops is not None and 0 < ops < 2.0:
                    ops_by_level[level].append(ops)
                # ISO = SLG - AVG; the row already carries both as strings
                # (".445" / ".265"). Either value being non-numeric just
                # drops the sample, same as for any other rate stat.
                slg = _parse_float(r.get("slg"))
                avg = _parse_float(r.get("avg"))
                if slg is not None and avg is not None and 0 <= slg < 1.0 and 0 <= avg < 1.0:
                    iso_by_level[level].append(slg - avg)
                bb_pct = _parse_float(r.get("bb_pct"))
                if bb_pct is not None and 0 <= bb_pct < 30:
                    bb_pct_by_level[level].append(bb_pct)
                k_pct = _parse_float(r.get("k_pct"))
                if k_pct is not None and 0 <= k_pct < 60:
                    k_pct_by_level[level].append(k_pct)

    def _avg_or_fallback(values, fallback_map, level, ndigits):
        if len(values) >= MIN_SAMPLE_N:
            return round(sum(values) / len(values), ndigits)
        return fallback_map.get(level)

    def _std_or_none(values, min_n):
        """Population stdev of a value list, or None when the sample is
        below `min_n`. Callers fall back to the 0.15×mu rule of thumb."""
        if len(values) < min_n:
            return None
        import statistics
        try:
            return round(statistics.pstdev(values), 4)
        except statistics.StatisticsError:
            return None

    out: dict[str, dict] = {}
    all_levels = (
        set(ages_by_level)
        | set(ops_by_level) | set(iso_by_level)
        | set(bb_pct_by_level) | set(k_pct_by_level)
        | set(era_by_level) | set(whip_by_level)
        | set(k9_by_level) | set(bb9_by_level) | set(hr9_by_level)
        | set(pitcher_k_pct_by_level) | set(pitcher_bb_pct_by_level)
    )
    for level in all_levels:
        mean, med, p25, p75, n_age = _summarize(ages_by_level.get(level, []))
        ops_values    = ops_by_level.get(level, [])
        iso_values    = iso_by_level.get(level, [])
        bb_pct_values = bb_pct_by_level.get(level, [])
        k_pct_values  = k_pct_by_level.get(level, [])
        era_values    = era_by_level.get(level, [])
        whip_values   = whip_by_level.get(level, [])
        k9_values     = k9_by_level.get(level, [])
        bb9_values    = bb9_by_level.get(level, [])
        hr9_values    = hr9_by_level.get(level, [])
        pitcher_k_pct_values  = pitcher_k_pct_by_level.get(level, [])
        pitcher_bb_pct_values = pitcher_bb_pct_by_level.get(level, [])
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
                # Hitter norms
                "avg_ops":    _avg_or_fallback(ops_values,    FALLBACK_OPS_NORM,    level, 3),
                "avg_iso":    _avg_or_fallback(iso_values,    FALLBACK_ISO_NORM,    level, 3),
                "avg_bb_pct": _avg_or_fallback(bb_pct_values, FALLBACK_BB_PCT_NORM, level, 1),
                "avg_k_pct":  _avg_or_fallback(k_pct_values,  FALLBACK_K_PCT_NORM,  level, 1),
                # Pitcher norms
                "avg_era":      _avg_or_fallback(era_values,  FALLBACK_ERA_NORM,    level, 2),
                "avg_whip":     _avg_or_fallback(whip_values, FALLBACK_WHIP_NORM,   level, 2),
                "avg_k_per_9":  _avg_or_fallback(k9_values,   FALLBACK_K9_NORM,     level, 2),
                "avg_bb_per_9": _avg_or_fallback(bb9_values,  FALLBACK_BB9_NORM,    level, 2),
                "avg_hr_per_9": _avg_or_fallback(hr9_values,  FALLBACK_HR9_NORM,    level, 2),
                "avg_pitcher_k_pct":  _avg_or_fallback(pitcher_k_pct_values,  FALLBACK_PITCHER_K_PCT_NORM,  level, 1),
                "avg_pitcher_bb_pct": _avg_or_fallback(pitcher_bb_pct_values, FALLBACK_PITCHER_BB_PCT_NORM, level, 1),
                # Sample counts — let the UI hide noisy fallback comparisons.
                "sample_n_ops":      len(ops_values),
                "sample_n_iso":      len(iso_values),
                "sample_n_bb_pct":   len(bb_pct_values),
                "sample_n_k_pct":    len(k_pct_values),
                "sample_n_era":      len(era_values),
                "sample_n_whip":     len(whip_values),
                "sample_n_k_per_9":  len(k9_values),
                "sample_n_bb_per_9": len(bb9_values),
                "sample_n_hr_per_9": len(hr9_values),
                "sample_n_pitcher_k_pct":  len(pitcher_k_pct_values),
                "sample_n_pitcher_bb_pct": len(pitcher_bb_pct_values),
                # Empirical stdevs for the Z-score family (Phase A3).
                # Replaces the historical `sigma = 0.15 * mu` approximation
                # used in `_compute_peripheral_stf_plus`. Only populated
                # when the sample is ≥30 — below that, callers should
                # fall back to the 15%-of-mean rule of thumb.
                "std_pitcher_k_pct":  _std_or_none(pitcher_k_pct_values,  30),
                "std_pitcher_bb_pct": _std_or_none(pitcher_bb_pct_values, 30),
                "std_hr_per_9":       _std_or_none(hr9_values,            30),
            },
        }
    return out


def age_baselines_from_norms(norms: dict[str, dict]) -> dict[str, float]:
    """Pull a flat {level: avg_age} dict from the rich norms structure.

    Uses the arithmetic mean. The mean is more sensitive than the
    median to outliers (e.g., a 30-year-old AAA rehabber on his way
    back from injury), but the team wants the comparison anchored at
    the cohort's actual average rather than the middle value. The
    median is still computed and stored on the norms dict as
    ``median_age`` for callers that want it, falling back through it
    when ``avg_age`` is unavailable in older cached norms blobs.
    """
    out: dict[str, float] = dict(FALLBACK_AGE_BASELINE)
    for level, blob in norms.items():
        age = blob.get("age", {})
        out[level] = age.get("avg_age",
                             age.get("median_age",
                                     out.get(level, 22.0)))
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
