# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Arbitration-year reconstruction: which arb step (if any) a player-season was.

THIS IS THE HARD PART OF THE ARBITRATION PROGRAM, not the regression.

There is no service-time ground truth in this tree, and the code says so:
bayes_trade_value.py:4498-4503 states it outright and records that
roster_status.active_roster_days LOOKS like service time and is measured
ANTI-correlated with MLB season count (median 786 days at zero MLB seasons,
0 at six or more). stats.py:3006-3019 `service_phase` is len(mlb_seasons)
bucketed. Neither can place a player relative to the Super Two cut.

So the arb step is FUSED from four sources with explicit precedence, and every
row carries the source that produced it. A row whose step came from the
heuristic is not the same evidence as a row whose step came from a published
service-time figure, and the UI and the gate both have to be able to tell.

PRECEDENCE
  1. mlbtr_service    - MLBTR prints real service time ("5.045"). Ground truth.
  2. spotrac_backprop - the cached forward ARB grid, walked backwards.
                        ADMISSIBLE ONLY FOR SEASONS >= SPOTRAC_MIN_SEASON.
  3. fa_class_backcount - first free-agent class year minus control years.
  4. debut_heuristic  - debut year + salary-path shape. Last resort, flagged.

WHY SPOTRAC IS FENCED TO RECENT SEASONS
spotrac.py:376-379 skips any row with no future salary on file, and the cached
pages are a 2026 snapshot. Back-propagating them to 2013 therefore labels only
players still on a 40-man thirteen years later: the elite survivor tail, whose
raise paths are the flattest and highest in the population. Using them as
pre-2024 labels would not merely be thin, it would be biased in the direction
of the thing being fitted. Source 3 exists to cover the players who left.
"""
from __future__ import annotations

import logging
import re
from functools import lru_cache

_log = logging.getLogger(__name__)

# Spotrac's forward grid may only label seasons at or after this year. See the
# survivorship argument in the module docstring.
SPOTRAC_MIN_SEASON = 2024

# Standard club control. A player reaches free agency after six full service
# years; arbitration covers service years 3, 4 and 5 (four with Super Two).
CONTROL_YEARS = 6
PRE_ARB_YEARS = 3

# Published Super Two cutoffs: the minimum service time (years, days) that
# qualified a 2-plus player for early arbitration in that CLASS year. The cut
# is the top 22% of two-plus-service players and moves every winter, so it
# cannot be derived - it is announced.
#
# *** VERIFY_STATUS: curated-unverified. ***
# These were entered from recall, NOT from a source document, and they have not
# been checked against MLBTR's published cutoff table (the projections post
# carries one back to 2009). Until tools/ingest_arbitration_ledger.py confirms
# them they are a HYPOTHESIS, and the convention here matches
# data/cba_rules.json, which carries the same verify_status marker rather than
# presenting curated values as sourced.
#
# The failure mode this guards: a wrong cutoff moves a player across the Super
# Two boundary, which changes his arb step, which changes the whole raise chain
# and the derived ladder. So SUPER_TWO_VERIFIED gates whether a super_two=True
# call is admissible as a LABEL or only as a diagnostic; see arb_dataset.
SUPER_TWO_VERIFIED = False
SUPER_TWO_CUTOFFS: dict[int, tuple[int, int]] = {
    # class_year: (years, days)
    2011: (2, 135), 2012: (2, 146), 2013: (2, 139), 2014: (2, 133),
    2015: (2, 130), 2016: (2, 131), 2017: (2, 123), 2018: (2, 134),
    2019: (2, 139), 2020: (2, 115), 2021: (2, 125), 2022: (2, 116),
    2023: (2, 128), 2024: (2, 132), 2025: (2, 119), 2026: (2, 116),
}

# A service-time token as MLBTR prints it: "5.045" = 5 years, 45 days.
_SERVICE_RE = re.compile(r"^(\d+)\.(\d{1,3})$")

# Spotrac status tokens, as spotrac._year_cell_status normalizes them.
_SPOTRAC_ARB_RE = re.compile(r"^ARB\s*([1-4])(\s*\(S2\))?$")

# A service year is 172 days. Anything at or above that rolls over.
DAYS_PER_SERVICE_YEAR = 172


def parse_service_token(tok: str) -> tuple[int, int] | None:
    """'5.045' -> (5, 45). None when the token is not a service figure.

    Days are NOT a decimal fraction: 5.045 is five years and forty-five days,
    not five and a bit. Parsing it as a float loses that and quietly moves
    players across the Super Two cut.
    """
    m = _SERVICE_RE.match((tok or "").strip())
    if not m:
        return None
    years, days = int(m.group(1)), int(m.group(2))
    if days >= DAYS_PER_SERVICE_YEAR:
        return None
    return years, days


def super_two_cut(class_year: int) -> tuple[int, int] | None:
    """The published Super Two cutoff for a class year, or None when we do not
    have it. None means UNKNOWN and must not be treated as 'not Super Two'."""
    return SUPER_TWO_CUTOFFS.get(int(class_year))


def _svc_days(yrs: int, days: int) -> int:
    return int(yrs) * DAYS_PER_SERVICE_YEAR + int(days)


def arb_year_from_service(yrs: int, days: int, class_year: int) -> dict:
    """Service time at the END of the platform season -> the arb step for the
    season being NEGOTIATED (class_year).

    Returns {"arb_year": int|None, "super_two": bool|None, "reason": str}.
    arb_year None means the player was not arbitration-eligible for that class
    (pre-arb, or already past six years and a free agent).

    super_two is None, not False, when the cutoff for that class is unknown -
    the distinction between "measured not Super Two" and "we cannot say" is
    load-bearing, because a wrong Super Two call shifts the whole raise chain.
    """
    total = _svc_days(yrs, days)
    if yrs >= CONTROL_YEARS:
        return {"arb_year": None, "super_two": None, "reason": "free_agent"}
    if yrs >= PRE_ARB_YEARS:
        # 3.xxx -> arb 1, 4.xxx -> arb 2, 5.xxx -> arb 3.
        return {"arb_year": yrs - PRE_ARB_YEARS + 1, "super_two": False,
                "reason": "service"}
    if yrs == 2:
        cut = super_two_cut(class_year)
        if cut is None:
            return {"arb_year": None, "super_two": None,
                    "reason": "super_two_cut_unknown"}
        if total >= _svc_days(*cut):
            return {"arb_year": 1, "super_two": True, "reason": "super_two"}
        return {"arb_year": None, "super_two": False, "reason": "pre_arb"}
    return {"arb_year": None, "super_two": False, "reason": "pre_arb"}


def _super_two_chain(arb_year: int, is_s2: bool) -> bool:
    """A Super Two player's ladder has four rungs, so his arb-2 is other
    players' arb-1. The (S2) marker travels with every rung, not just the
    first, which is why the token carries it on ARB 2/3/4 as well."""
    return bool(is_s2)


def backpropagate(status_by_year: dict[int, str], *,
                  appearance_seasons: set[int] | None = None) -> dict[int, dict]:
    """Spotrac's FORWARD grid -> {season: {arb_year, super_two}} for the seasons
    BEFORE the earliest labelled one.

    Spotrac labels future club-control years ("2027: ARB 2"). If 2027 is arb 2
    then 2026 was arb 1, and the pre-arb seasons run back from there. The walk
    decrements one step per season and stops at step 1; it does NOT keep
    counting into pre-arb seasons, because how many pre-arb seasons a player
    had is a service question this grid cannot answer.

    Returns only seasons it can label, including the labelled ones themselves.
    """
    out: dict[int, dict] = {}
    labelled: list[tuple[int, int, bool]] = []
    for year, token in (status_by_year or {}).items():
        m = _SPOTRAC_ARB_RE.match((token or "").strip().upper())
        if m:
            labelled.append((int(year), int(m.group(1)), bool(m.group(2))))
    if not labelled:
        return out
    labelled.sort()
    for year, step, is_s2 in labelled:
        out[year] = {"arb_year": step, "super_two": _super_two_chain(step, is_s2)}
    # Walk backwards from the EARLIEST labelled year.
    first_year, first_step, first_s2 = labelled[0]
    step = first_step
    year = first_year
    while step > 1:
        year -= 1
        step -= 1
        if appearance_seasons is not None and year not in appearance_seasons:
            # A gap in MLB appearances means service did not accrue that year,
            # so the decrement is no longer a safe inference. Stop rather than
            # guess.
            break
        out[year] = {"arb_year": step, "super_two": _super_two_chain(step, first_s2)}
    return out


def from_fa_class(fa_class_year: int, appearance_seasons: set[int],
                  *, control_years: int = CONTROL_YEARS) -> dict[int, dict]:
    """First free-agent class year -> the arb seasons that preceded it.

    A player who first reached free agency for class year Y finished six
    service years in season Y-1, so his arb seasons were Y-1 (arb 3), Y-2
    (arb 2) and Y-3 (arb 1). This is the ONLY source that covers players who
    have since left the league, which is what makes it the counterweight to
    Spotrac's survivor-only grid.

    Assumes an unbroken service path, which is why it is precedence 3: a
    player who lost a year to the minors or the IL shifts every step.
    """
    walk_year = int(fa_class_year) - 1
    out: dict[int, dict] = {}
    for step in (3, 2, 1):
        year = walk_year - (3 - step)
        if year not in appearance_seasons:
            continue
        out[year] = {"arb_year": step, "super_two": None}
    return out


def from_debut(debut_year: int, appearance_seasons: set[int],
               salary_by_year: dict[int, float], league_min_by_year: dict[int, float],
               *, season: int) -> dict | None:
    """Last-resort step for one season from debut year plus salary-path shape.

    The shape signal: a pre-arb player is paid at or near the league minimum,
    and the first season a player's salary clears the minimum by a clear margin
    is his first arbitration year. That is weaker than it sounds - renewals run
    slightly above the minimum and split contracts confuse it - so every row
    produced here is flagged `debut_heuristic` and the gate reports what share
    of each season came from it.
    """
    seasons = sorted(y for y in appearance_seasons if y >= int(debut_year))
    if int(season) not in seasons:
        return None
    first_arb = None
    for y in seasons:
        lm = league_min_by_year.get(y)
        sal = salary_by_year.get(y)
        if lm is None or sal is None:
            continue
        if float(sal) > float(lm) * 1.30:
            first_arb = y
            break
    if first_arb is None:
        return None
    step = seasons.index(int(season)) - seasons.index(first_arb) + 1
    if step < 1 or step > 4:
        return None
    return {"arb_year": step, "super_two": None}


# Source precedence, best first. Emitted verbatim as `arb_year_source`.
SOURCE_PRECEDENCE = ("mlbtr_service", "spotrac_backprop",
                     "fa_class_backcount", "debut_heuristic")


def reconcile(votes: dict[str, dict], *, season: int) -> dict:
    """Fuse per-source votes into one labelled row.

    votes: {source_name: {"arb_year": int|None, "super_two": bool|None}}

    Returns the winning label plus the full vote record, so a disagreement is
    visible in the artifact rather than resolved silently. The winner is the
    highest-precedence source that produced a non-None arb_year, EXCEPT that
    spotrac_backprop is dropped for seasons before SPOTRAC_MIN_SEASON.
    """
    usable = {}
    for src, vote in (votes or {}).items():
        if not vote or vote.get("arb_year") is None:
            continue
        if src == "spotrac_backprop" and int(season) < SPOTRAC_MIN_SEASON:
            continue
        usable[src] = vote
    winner = None
    for src in SOURCE_PRECEDENCE:
        if src in usable:
            winner = src
            break
    if winner is None:
        return {"arb_year": None, "super_two": None, "arb_year_source": None,
                "votes": {k: v.get("arb_year") for k, v in (votes or {}).items()},
                "n_sources": 0, "agree": None}
    win = usable[winner]
    steps = {v.get("arb_year") for v in usable.values()}
    s2_votes = [v.get("super_two") for v in usable.values()
                if v.get("super_two") is not None]
    super_two = win.get("super_two")
    if super_two is None and s2_votes:
        super_two = bool(s2_votes[0])
    return {
        "arb_year": int(win["arb_year"]),
        "super_two": super_two,
        "arb_year_source": winner,
        "votes": {k: v.get("arb_year") for k, v in usable.items()},
        "n_sources": len(usable),
        "agree": (len(steps) == 1) if len(usable) > 1 else None,
    }


def disagreement_report(rows: list[dict]) -> dict:
    """Per-source-pair agreement on arb_year and super_two.

    This is a PUBLISHED quantity and a data-quality gate, not a diagnostic. A
    pooled rate hides the two cells that matter (the pre-arb / Super Two
    boundary and the arb3 / arb4 boundary), so the confusion matrix ships too.
    """
    from itertools import combinations
    by_pair: dict[str, dict] = {}
    for a, b in combinations(SOURCE_PRECEDENCE, 2):
        inter = [r for r in rows
                 if (r.get("votes") or {}).get(a) is not None
                 and (r.get("votes") or {}).get(b) is not None]
        if not inter:
            continue
        agree = sum(1 for r in inter if r["votes"][a] == r["votes"][b])
        conf: dict[str, int] = {}
        for r in inter:
            cell = f"{r['votes'][a]}->{r['votes'][b]}"
            conf[cell] = conf.get(cell, 0) + 1
        by_pair[f"{a}|{b}"] = {
            "n": len(inter),
            "agree": agree,
            "rate": round(agree / len(inter), 4),
            "confusion": dict(sorted(conf.items(), key=lambda kv: -kv[1])),
        }
    src_mix: dict[str, int] = {}
    for r in rows:
        s = r.get("arb_year_source")
        if s:
            src_mix[s] = src_mix.get(s, 0) + 1
    return {"by_pair": by_pair, "source_mix": dict(sorted(src_mix.items())),
            "n_rows": len(rows),
            "n_labelled": sum(1 for r in rows if r.get("arb_year") is not None)}
