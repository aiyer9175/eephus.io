"""Section 5f gate harness, first half: the POWER PRECONDITION and its refusals.

docs/diamond-betting.md section 5f registers a precondition specific to the
pinch-hit candidate, computed BEFORE any outcome is joined: at each split
quantile, the RMS of (candidate p_home minus served p_home) over the eval games,
from features and fit-half coefficients only. If sqrt(n_eval) times that RMS is
below 1.645 at ANY quantile, the look records UNDERPOWERED with the RMS and
n_eval, the outcome comparison is not computed, and the candidate is neither
passed nor closed.

This module holds exactly that and nothing that reads a result:

  * `check_look_date` refuses to run before the end of the 2027 regular season.
    5f allows one look per season, after the last regular-season game, and the
    first is the end of 2027. The end date is SUPPLIED (the StatsAPI seasons
    endpoint states it) and is never guessed; a supplied date before
    EARLIEST_LOOK_FLOOR, or in a season before FIRST_LOOK_SEASON, is refused.
  * `refuse_outcome_fields` refuses any input row carrying a key outside the
    feature-only allowlist, so an outcome column cannot ride in by accident.
  * `power_precondition` is the arithmetic above.
  * `run_precondition` chains the three and says whether the outcome join is
    permitted. It never performs the join; that is the later look step's job,
    and only when this returns POWERED.

Pure and offline: no file, no network, no game outcome. Imported by path in
test_schema5_builders (tools/ is not a package).
"""
from __future__ import annotations

import math
from datetime import date

#: The first season whose regular-season end opens the 5f look (section 5f,
#: Clock: "the first is the end of the 2027 regular season").
FIRST_LOOK_SEASON = 2027

#: No supplied regular-season end earlier than this is believed. An MLB regular
#: season has not ended before late September in a full year; a date before
#: September 1 of the look season is a typo or a fixture, and the look waits.
EARLIEST_LOOK_FLOOR = date(FIRST_LOOK_SEASON, 9, 1)

#: The split quantiles 5f names; the precondition must hold at ALL of them.
SPLIT_QUANTILES = (0.6, 0.7, 0.8)

#: One-sided 95%: the expected-t bar the precondition compares against.
Z_ONE_SIDED = 1.645

#: The only keys a precondition row may carry. Everything else is refused, so
#: a frame that picked up home_runs, a win flag or a score cannot pass through.
ALLOWED_ROW_KEYS = frozenset({"game_pk", "date", "p_candidate", "p_served"})


class LookRefused(RuntimeError):
    """The look date rule refused this run."""


class OutcomeJoinRefused(RuntimeError):
    """An input carried something other than features, or the precondition
    failed and the outcome comparison may not be computed."""


def _as_date(v) -> date | None:
    if v is None:
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def check_look_date(today, regular_season_end) -> None:
    """Raise LookRefused unless `today` is after a believable end of a regular
    season of FIRST_LOOK_SEASON or later."""
    t = _as_date(today)
    end = _as_date(regular_season_end)
    if t is None:
        raise LookRefused("no run date; the look date rule cannot be checked")
    if end is None:
        raise LookRefused("the regular-season end date was not supplied; it is read "
                          "from the StatsAPI seasons endpoint, never guessed")
    if end.year < FIRST_LOOK_SEASON:
        raise LookRefused(f"the {end.year} regular season is before the first 5f look "
                          f"({FIRST_LOOK_SEASON})")
    if end < date(end.year, EARLIEST_LOOK_FLOOR.month, EARLIEST_LOOK_FLOOR.day):
        raise LookRefused(f"a regular-season end of {end.isoformat()} is before "
                          f"{EARLIEST_LOOK_FLOOR.month:02d}-{EARLIEST_LOOK_FLOOR.day:02d}; "
                          "not believed")
    if t < EARLIEST_LOOK_FLOOR or t <= end:
        raise LookRefused(f"{t.isoformat()} is not after the end of the regular season "
                          f"({end.isoformat()}); 5f allows one look per season, after "
                          "the last regular-season game")


def refuse_outcome_fields(rows) -> None:
    """Raise OutcomeJoinRefused if any row carries a key outside
    ALLOWED_ROW_KEYS, or a probability outside [0, 1]."""
    for i, r in enumerate(rows or []):
        if not isinstance(r, dict):
            raise OutcomeJoinRefused(f"row {i} is not a mapping")
        extra = set(r) - ALLOWED_ROW_KEYS
        if extra:
            raise OutcomeJoinRefused(
                f"row {i} carries {sorted(extra)}; the precondition reads features "
                "and fit-half coefficients only, never an outcome")
        for k in ("p_candidate", "p_served"):
            v = r.get(k)
            if not isinstance(v, (int, float)) or isinstance(v, bool) or not 0.0 <= v <= 1.0:
                raise OutcomeJoinRefused(f"row {i} {k} is not a probability")


def power_precondition(rows_by_quantile: dict) -> dict:
    """{"status": "POWERED" | "UNDERPOWERED", "by_quantile": {q: {n_eval, rms,
    expected_t, holds}}}. Each row is {"p_candidate", "p_served"} for one eval
    game at that split quantile. A quantile with no rows cannot hold."""
    out: dict = {"by_quantile": {}, "bar": Z_ONE_SIDED,
                 "quantiles": list(SPLIT_QUANTILES)}
    for q in SPLIT_QUANTILES:
        rows = (rows_by_quantile or {}).get(q) or []
        refuse_outcome_fields(rows)
        n = len(rows)
        if n == 0:
            out["by_quantile"][q] = {"n_eval": 0, "rms": None, "expected_t": None,
                                     "holds": False}
            continue
        ms = sum((r["p_candidate"] - r["p_served"]) ** 2 for r in rows) / n
        rms = math.sqrt(ms)
        et = math.sqrt(n) * rms
        out["by_quantile"][q] = {"n_eval": n, "rms": rms, "expected_t": et,
                                 "holds": et >= Z_ONE_SIDED}
    ok = all(v["holds"] for v in out["by_quantile"].values())
    out["status"] = "POWERED" if ok else "UNDERPOWERED"
    return out


def run_precondition(rows_by_quantile: dict, *, today=None,
                     regular_season_end=None) -> dict:
    """The look's first step. Refuses before the look date; computes the
    precondition; says whether the outcome join is permitted. Performs no join."""
    check_look_date(today, regular_season_end)
    pre = power_precondition(rows_by_quantile)
    if pre["status"] == "UNDERPOWERED":
        pre["outcome_join"] = ("REFUSED: UNDERPOWERED at one or more split quantiles; "
                               "the candidate is neither passed nor closed (5f)")
    else:
        pre["outcome_join"] = ("PERMITTED: the later look step may compute the "
                               "registered outcome comparison; this module does not")
    return pre


def require_powered(pre: dict) -> None:
    """The guard a look step calls before it touches any outcome."""
    if (pre or {}).get("status") != "POWERED":
        raise OutcomeJoinRefused("the 5f power precondition did not hold; the outcome "
                                 "comparison is not computed")
