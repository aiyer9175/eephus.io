# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""betting_model.py - MLB game probabilities from the site's own surfaces.

THE POINT: everything a book prices, this platform already measures. Team
offense is HEM+ rolled up to `offense_plus`; the rotation is SEM+ rolled up to
`rotation_plus` with the listed probable's own SEM+ available per start; the
bullpen is REM+ rolled up to `bullpen_plus`; park run environment is the same
Savant index the FA engine reads out of data/fa_meta.json. No new data source
is invented here. The model is a run-scoring regression on those four inputs
plus home field, and a Poisson-difference margin on top of it.

THE SCORING MODEL (two rows per game, one per scoring side)

    runs_S = b0 + b1*z_off_S + b2*z_prev_O + b3*park + b4*home

      z_off_S    the scoring team's offense_plus, standardized across the 30
                 teams for the season.
      z_prev_O   the OPPONENT's run prevention for THIS game: the listed
                 probable's SEM+ for the share of the game a starter covers
                 (ip_per_gs / 9), the opponent's bullpen_plus for the rest,
                 standardized on the team-level prevention distribution. With
                 no probable announced, the opponent's rotation_plus stands in.
      park       the home park's Savant runs index / 100 - 1 (0 = neutral).
      home       1 when S bats last.

    The coefficients are FIT, not assumed (`fit_coefficients`), on completed
    games read out of the existing .cache/game_feeds StatsAPI feed cache. That
    matters: a plus-stat sigma is not a run, and guessing the conversion is
    where a model like this usually goes wrong. When no fit is available the
    module falls back to literature priors (LITERATURE_COEFFS) and says so in
    `coefficients()["source"]`.

    Expected runs go into a Poisson-difference (Skellam) margin, computed by
    direct convolution so there is no scipy dependency in the serving path.
    That gives the moneyline (P(margin > 0), with the measured extra-innings
    home rate splitting the tie mass), the runline (P(margin >= 2)), and the
    total (Poisson on the run sum).

WHAT THIS MODEL IS NOT, AND THE PAGE SAYS SO
    Poisson underdisperses real run scoring: baseball scores in clumps, so the
    true margin distribution has fatter tails than the convolution assumes.
    That pushes runline and total probabilities toward the middle. The
    moneyline is the least exposed of the three.

    Worse, and this is the reason the module ships UNVALIDATED: the team
    inputs are SEASON-TO-DATE aggregates. Backtesting 2026 games against
    August's leaderboards means the features already contain the outcomes
    being predicted. `backtest()` runs, reports honest numbers, and labels
    them contaminated. Nothing here unlocks a published pick. A pick ships
    only once vintage-dated team inputs exist and a clean out-of-sample
    number does.

THE VINTAGE PATH (leaderboard_vintages.py), which is how that gets fixed.
    `inputs_as_of(date)` returns the team, pitcher AND park inputs from the
    newest nightly snapshot whose knowledge cutoff is STRICTLY BEFORE that date,
    so nothing that happened on or after the game can reach its features. A
    snapshot written before the park column existed returns `parks: None`, and
    the vintage backtest prices those games on a NEUTRAL park rather than on the
    live index; it never silently borrows today's number for a past game. Until
    the nightly snapshot has been running long enough, there is no such
    vintage for any date, and the read falls back to the live leaderboards
    with `contaminated: True` and a logged warning. Nothing in this module
    silently looks forward.

    `backtest()` therefore reports TWO modes and labels both: the contaminated
    mode (the old numbers, in-sample and forward-split) and the vintage mode,
    which grades only the games it can grade honestly and starts at n = 0. The
    vintage sample is what gates `min_edge`; see VINTAGE_MIN_GRADED_GAMES for
    the threshold and the measurement behind it.

DE-VIGGING (`devig`) uses the PROPORTIONAL method: each side's raw implied
probability divided by the book's overround. It is the standard, it is
transparent, and it is the one an edge number can be audited against.
Shin and the power/additive methods shift favourite-longshot weight around;
they are not used, and swapping one in would change every edge on the page,
so the method name travels in the payload.

CLI:
    python betting_model.py --context      # league constants + fitted coefficients
    python betting_model.py --backtest     # both modes, both labelled
    python betting_model.py --gate         # the min_edge gate state, one screen
    python betting_model.py --game NYM CLE # one matchup, hand-checkable
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("betting_model")

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
FEED_CACHE = ROOT / ".cache" / "game_feeds"
GAME_CACHE = ROOT / ".cache" / "betting"
CONTEXT_PATH = DATA_DIR / "betting_model_context.json"
EVAL_PATH = DATA_DIR / "betting_model_eval.json"

MODEL_VERSION = "betting_runs_v1"

# Share of a game the listed starter is expected to cover when the pitcher has
# no measured ip_per_gs. 5.2 IP is roughly the 2026 league average start.
DEFAULT_SP_SHARE = 5.2 / 9.0

# Fallbacks for a checkout with no feed cache. Sourced from published league
# run environments (2023-2025 MLB sat at 4.3-4.6 R/G per team, home teams won
# 52-54%), NOT from anything measured here. `coefficients()["source"]` says
# which set is live, and the page prints it.
LITERATURE_COEFFS = {
    "b0": 4.45,      # league runs per team per game
    "b1": 0.32,      # runs per sigma of team offense
    "b2": -0.32,     # runs per sigma of opponent run prevention
    "b3": 3.20,      # runs per unit of park index deviation (1.10 park -> +0.32)
    "b4": 0.09,      # home field, in runs, per side
    "source": "literature-priors",
    "n_rows": 0,
}
LITERATURE_TIE_HOME = 0.50       # home win rate once a game reaches extras
# Shrink strength for the extra-innings home rate. A season carries ~140 extra
# inning games, whose raw rate swings +/- 4 points on noise alone, so the
# measured value is shrunk toward a coin flip on a 100-game prior.
TIE_SHRINK_K = 100.0

# --- the vintage gate ------------------------------------------------------
# How many games the VINTAGE-mode backtest must grade before `min_edge` may be
# fitted at all. This number is measured, not picked to look serious.
#
# The claim a published pick rests on is that the model beats the home-field
# baseline out of sample. Grade that as a paired Brier difference, one game per
# pair. In the existing forward split (2026-06-24 onward, n = 521, coefficient
# leakage removed but feature leakage still present) that difference is
# +0.005794 in the model's favour with a paired standard deviation of 0.08647,
# so t = 1.529: the module's own "beats both baselines" line is NOT significant
# even with the leak helping it. Detecting a margin that size at one-sided 95%
# needs
#
#     n = (1.645 * 0.08647 / 0.005794)^2 = 603 games
#
# rounded to 600. Two honesty notes travel with it. First, a clean margin is
# very likely SMALLER than the contaminated one, so 600 games makes the test
# possible, it does not make it pass. Second, 600 is a FLOOR on the sample, not
# a substitute for the test: `min_edge_gate` still requires the paired
# difference to clear zero at one-sided 95% on that sample, and still requires
# a graded price history to sweep the threshold on.
#
# At the measured 2026 rate of 13.1 completed games per calendar date, 600
# games is about 46 slate days of nightly snapshots.
VINTAGE_MIN_GRADED_GAMES = 600
# Below these the vintage mode reports counts only and no metrics: 100 games is
# 200 design rows, the same floor `fit_coefficients` already enforces, and 50
# eval games is the floor the existing forward split uses.
VINTAGE_MIN_FIT_GAMES = 100
VINTAGE_MIN_EVAL_GAMES = 50
# The fit half is a TARGET SIZE, not a share, and that is a deliberate choice
# about how long this takes. A 60/40 split would put 40% of the archive in the
# eval half, so reaching 600 graded games would need 1,500 gradable ones, about
# 115 slate days. The fit half does not need to be large: five coefficients and
# two one-parameter corrections are comfortably estimated on 300 games (600
# design rows, three times the floor `fit_coefficients` enforces). Anchoring
# the fit at 300 and giving everything later to the eval window reaches 600
# graded games at ~900 gradable, about 69 slate days. The fit window stays
# anchored at the earliest dates as the archive grows, which drifts the eval
# window further from the fit over time: that is the conservative direction,
# it makes the test harder rather than easier.
VINTAGE_FIT_TARGET_GAMES = 300
# ...but never more than half the covered DATES, so a young archive still
# produces an eval window instead of one enormous fit.
VINTAGE_FIT_MAX_DATE_SHARE = 0.5
# One-sided 95% normal critical value, used for both the Brier-skill gate and
# the ROI lower bound in the min_edge sweep.
Z_95_ONE_SIDED = 1.645


# ---------------------------------------------------------------------------
# small io helpers
# ---------------------------------------------------------------------------
def _load_json(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _data(name: str):
    return _load_json(DATA_DIR / name)


def _org(name: str | None) -> str | None:
    """Anything team-shaped -> the canonical 3-letter org code. The site runs
    TWO code sets: the leaderboards carry StatsAPI abbreviations (SD, SF, TB,
    KC, AZ, CWS, WSH, ATH) while park factors and fantasy_schedule carry the
    Baseball-Reference style (SDP, SFG, TBR, KCR, ARI, CHW, WSN, ATH).
    canonical_org maps the first onto the second, so EVERY join in this module
    goes through it. Mixing the two silently drops eight clubs."""
    if not name:
        return None
    try:
        from trades import canonical_org
        return canonical_org(name)
    except Exception:                                            # pragma: no cover
        return None


def _mean_sd(xs: list[float]) -> tuple[float, float]:
    n = len(xs)
    if not n:
        return 0.0, 1.0
    mu = sum(xs) / n
    var = sum((x - mu) ** 2 for x in xs) / n
    return mu, (math.sqrt(var) or 1.0)


# ---------------------------------------------------------------------------
# team + pitcher inputs off the committed leaderboards
# ---------------------------------------------------------------------------
def _assemble_team_inputs(off: dict, rots: dict, pens: dict,
                          starter_ip: dict, relief_ip: dict) -> dict:
    """The standardization, written ONCE.

    The live path and the vintage path both land here, which is the point: a
    z-score computed one way on today's leaderboards and another way on a
    stored snapshot would make the backtest incomparable to the served model
    for a reason nobody would ever see."""
    orgs = sorted(set(off) & set(pens) & set(rots))
    if not orgs:
        # LOG THE COUNTS, not the outcome. The board published "team
        # leaderboards have not been built yet" while all three leaderboards
        # held 30 clubs, because this is an INTERSECTION: one source that parses
        # to zero orgs, or a code-set mismatch that makes the sets disjoint,
        # empties it with every file on disk fully populated. The three counts
        # are the only thing that separates those cases, so they go in the log
        # and (through `team_inputs_detail`) onto the page.
        log.error("betting_model: team inputs are EMPTY - the intersection of the "
                  "three team leaderboards is 0 orgs (offense %d, rotation %d, "
                  "bullpen %d). Every game on the board will fail to price.",
                  len(off), len(rots), len(pens))
        return {}
    # Team run prevention = rotation and bullpen weighted by their ACTUAL
    # innings split, not a guessed 60/40. The split moves several points a year
    # and moves more than that for an opener-heavy staff.
    prev = {}
    for o in orgs:
        sip, rip = starter_ip.get(o, 0.0), relief_ip.get(o, 0.0)
        w = sip / (sip + rip) if (sip + rip) > 0 else DEFAULT_SP_SHARE
        prev[o] = w * rots[o] + (1.0 - w) * pens[o]

    off_mu, off_sd = _mean_sd([off[o] for o in orgs])
    prev_mu, prev_sd = _mean_sd([prev[o] for o in orgs])
    out = {}
    for o in orgs:
        sip, rip = starter_ip.get(o, 0.0), relief_ip.get(o, 0.0)
        out[o] = {
            "org": o,
            "offense_plus": off[o],
            "rotation_plus": rots[o],
            "bullpen_plus": pens[o],
            "prev_plus": prev[o],
            "sp_ip_share": (sip / (sip + rip)) if (sip + rip) > 0 else DEFAULT_SP_SHARE,
            "z_off": (off[o] - off_mu) / off_sd,
            "z_prev": (prev[o] - prev_mu) / prev_sd,
        }
    out["_scale"] = {"off_mu": off_mu, "off_sd": off_sd,
                     "prev_mu": prev_mu, "prev_sd": prev_sd}
    return out


def team_inputs_detail() -> dict:
    """{"teams": {...}, "sources": {...}} - the live team inputs AND the
    per-leaderboard org counts that produced them.

    THE COUNTS EXIST SO A BLANK BOARD CAN BE DIAGNOSED RATHER THAN GUESSED AT.
    `team_inputs` returns the INTERSECTION of three org sets, so "empty" has at
    least three distinct causes (a missing file, a source that parsed to zero
    rows, and two code sets that do not overlap) and they need different fixes.
    Reporting only the outcome cost this module a published false diagnosis;
    see `betting_export.team_input_failure_reason`."""
    files = {"offense": "hitter_leaderboards.json",
             "rotation": "starter_leaderboards.json",
             "bullpen": "bullpen_leaderboards.json"}
    blobs = {k: _data(v) for k, v in files.items()}

    off = {}
    for t in (blobs["offense"] or {}).get("teams") or []:
        o = _org(t.get("team"))
        if o and t.get("offense_plus") is not None:
            off[o] = float(t["offense_plus"])
    pens, relief_ip = {}, {}
    for t in (blobs["bullpen"] or {}).get("teams") or []:
        o = _org(t.get("team"))
        if o and t.get("bullpen_plus") is not None:
            pens[o] = float(t["bullpen_plus"])
            relief_ip[o] = float(t.get("relief_ip") or 0.0)
    rots, starter_ip = {}, {}
    for t in (blobs["rotation"] or {}).get("teams") or []:
        o = _org(t.get("team"))
        if o and t.get("rotation_plus") is not None:
            rots[o] = float(t["rotation_plus"])
            starter_ip[o] = float(t.get("starter_ip") or 0.0)

    parsed = {"offense": off, "rotation": rots, "bullpen": pens}
    sources = {
        k: {"file": files[k],
            "present": blobs[k] is not None,
            "n_orgs": len(parsed[k]),
            "as_of": (blobs[k] or {}).get("as_of")}
        for k in files
    }
    teams = _assemble_team_inputs(off, rots, pens, starter_ip, relief_ip)
    sources["n_orgs_joined"] = len([o for o in teams if not o.startswith("_")])
    return {"teams": teams, "sources": sources}


def team_inputs() -> dict:
    """{org: {...}} team strength, standardized, from the LIVE leaderboards.

    Empty when the leaderboards are absent (fresh checkout), which the caller
    degrades on. These are season-to-date: for a backtest that must not see
    the future, go through `inputs_as_of`. A caller that has to EXPLAIN an
    empty return wants `team_inputs_detail` instead."""
    return team_inputs_detail()["teams"]


def starter_inputs() -> dict:
    """{mlbam: {sem_plus, ip_per_gs, name, org}} from starter_leaderboards, so a
    game can be priced on the announced probable rather than the rotation
    average. Relievers are folded in too (openers, bulk relief)."""
    out = {}
    rot = _data("starter_leaderboards.json") or {}
    for r in rot.get("starters") or []:
        mid = r.get("mlbam")
        if not mid or r.get("sem_plus") is None:
            continue
        out[int(mid)] = {"mlbam": int(mid), "name": r.get("name"),
                         "org": _org(r.get("team")),
                         "sem_plus": float(r["sem_plus"]),
                         "ip_per_gs": float(r.get("ip_per_gs") or 0.0) or None,
                         "role": r.get("role") or "SP"}
    pen = _data("bullpen_leaderboards.json") or {}
    for r in pen.get("relievers") or []:
        mid = r.get("mlbam")
        if not mid or r.get("rem_plus") is None or int(mid) in out:
            continue
        out[int(mid)] = {"mlbam": int(mid), "name": r.get("name"),
                         "org": _org(r.get("team")),
                         "sem_plus": float(r["rem_plus"]),   # same 100/10z scale
                         "ip_per_gs": None, "role": "RP"}
    return out


def park_index() -> dict:
    """{org: runs index / 100}. data/fa_meta.json carries the Savant park
    factors the FA engine already reads; no second copy is fetched. Missing
    parks resolve neutral at lookup, never invented."""
    meta = _data("fa_meta.json") or {}
    pf = meta.get("park_factors") or {}
    out = {}
    for org, v in pf.items():
        try:
            out[str(org)] = float((v or {}).get("runs") or 100) / 100.0
        except (TypeError, ValueError):
            continue
    return out


# ---------------------------------------------------------------------------
# the vintage read path
# ---------------------------------------------------------------------------
# One warning per process, not one per game. A 1,705-game backtest with no
# vintages would otherwise emit 1,705 identical lines and bury everything else
# in the nightly log.
_VINTAGE_FALLBACK_WARNED = False
# {vintage_date: (teams, starters, parks|None)}. A vintage is reduced once and
# reused by every game it prices; without this a backtest rebuilds the same
# 30-team standardization fifteen times a day. `parks` is None (never {}) when
# the record predates the park column: see `parks_from_vintage`.
_VINTAGE_CACHE: dict[str, tuple[dict, dict, dict | None]] = {}

# The park index a game gets when its vintage carries no park column. Empty is
# NEUTRAL here and only here, because `expected_runs` already resolves a missing
# org to 1.00 (ATH has no Savant park entry), so an empty index makes the park
# term drop out of the regression entirely. It is a named constant rather than a
# bare {} at three call sites so the fallback is greppable, and every game that
# takes it is counted into the vintage block's `park_basis`.
NEUTRAL_PARK_INDEX: dict[str, float] = {}


def reset_vintage_cache() -> None:
    """Drop the memoized vintages, here and in the store. Tests that write
    vintages into a tmp dir call this; the pipeline never needs it."""
    global _VINTAGE_FALLBACK_WARNED
    _VINTAGE_CACHE.clear()
    _VINTAGE_FALLBACK_WARNED = False
    lv = _vintage_module()
    if lv:
        lv.reset_cache()


def _vintage_module():
    try:
        import leaderboard_vintages
        return leaderboard_vintages
    except Exception:                                            # pragma: no cover
        return None


def team_inputs_from_vintage(rec: dict) -> dict:
    """A stored vintage record -> the same {org: {...}} shape `team_inputs`
    returns, through the same standardization."""
    cols = list(rec.get("team_columns") or ())
    try:
        i_off = cols.index("offense_plus")
        i_rot = cols.index("rotation_plus")
        i_pen = cols.index("bullpen_plus")
        i_sip = cols.index("starter_ip")
        i_rip = cols.index("relief_ip")
    except ValueError:                                           # pragma: no cover
        return {}
    off, rots, pens, sip, rip = {}, {}, {}, {}, {}
    for org, row in (rec.get("teams") or {}).items():
        if not isinstance(row, list) or len(row) <= max(i_off, i_rot, i_pen, i_sip, i_rip):
            continue
        if row[i_off] is None or row[i_rot] is None or row[i_pen] is None:
            continue
        off[org] = float(row[i_off])
        rots[org] = float(row[i_rot])
        pens[org] = float(row[i_pen])
        sip[org] = float(row[i_sip] or 0.0)
        rip[org] = float(row[i_rip] or 0.0)
    return _assemble_team_inputs(off, rots, pens, sip, rip)


def starter_inputs_from_vintage(rec: dict) -> dict:
    """A stored vintage record -> the same {mlbam: {...}} shape
    `starter_inputs` returns. Names are not stored (the model never reads
    one), so the display name comes back None."""
    cols = list(rec.get("pitcher_columns") or ())
    try:
        i_plus = cols.index("plus")
        i_ip = cols.index("ip_per_gs")
        i_org = cols.index("org")
        i_role = cols.index("role")
    except ValueError:                                           # pragma: no cover
        return {}
    out = {}
    for mid, row in (rec.get("pitchers") or {}).items():
        if not isinstance(row, list) or len(row) <= max(i_plus, i_ip, i_org, i_role):
            continue
        if row[i_plus] is None:
            continue
        try:
            key = int(mid)
        except (TypeError, ValueError):
            continue
        out[key] = {"mlbam": key, "name": None, "org": row[i_org],
                    "sem_plus": float(row[i_plus]),
                    "ip_per_gs": float(row[i_ip]) if row[i_ip] else None,
                    "role": row[i_role] or "SP"}
    return out


def parks_from_vintage(rec: dict) -> dict | None:
    """A stored vintage record -> {org: runs index / 100}, or None when the
    record has no park column.

    NONE IS THE SENTINEL AND IT MATTERS. `park_index()` reads the LIVE
    data/fa_meta.json, whose factors are `fa_fit.park_factors(CLASS_YEAR - 1)`,
    i.e. the IN-PROGRESS season. Handing that to a vintage-mode game lets the
    eval window contribute to the park index used to fit and to price it, which
    is the leak leaderboard_vintages exists to close and which the mode label
    was denying. Returning {} here would be just as bad in the other direction:
    the caller could not tell "no park column" from "a league of neutral parks",
    so it could not mark the games. None forces the caller to choose, out loud."""
    parks = (rec or {}).get("parks")
    if not isinstance(parks, dict) or not parks:
        return None
    out: dict[str, float] = {}
    for org, v in parks.items():
        try:
            out[str(org)] = float(v)
        except (TypeError, ValueError):
            continue
    return out or None


def inputs_as_of(game_date: str | None, *, allow_fallback: bool = True) -> dict:
    """The team and pitcher inputs for a game on `game_date`, from the newest
    vintage whose knowledge cutoff is STRICTLY BEFORE it.

    Returns a bundle, always, with the provenance attached:

        {"teams": {...}, "starters": {...}, "parks": {...}|None,
         "parks_resolved": bool,
         "source": "vintage"|"live-leaderboards",
         "vintage_date": "2026-08-05"|None, "covers_through": ...|None,
         "contaminated": bool, "note": "..."}

    `parks` is None with `parks_resolved: False` when the vintage predates the
    park column. It is NOT quietly filled from `park_index()`: that index is the
    in-progress season's, so filling it would put the leak back on the one input
    that had it. The caller prices those games on NEUTRAL_PARK_INDEX and counts
    them.

    THE FALLBACK IS LOUD ON PURPOSE. With no vintage for the date this returns
    the LIVE season-to-date leaderboards, which contain the game being priced,
    and says so: `contaminated: True` plus a once-per-process log warning. The
    fallback is the current behaviour of the whole module, so nothing regresses
    while the store fills up; what changes is that a caller can no longer be
    unaware of which one it got. `allow_fallback=False` returns an empty bundle
    instead, which is what the vintage backtest uses so it cannot accidentally
    grade a game on contaminated features."""
    global _VINTAGE_FALLBACK_WARNED
    lv = _vintage_module()
    rec = None
    if lv and game_date:
        try:
            rec = lv.as_of(game_date)
        except Exception:                                        # pragma: no cover
            rec = None
    if rec:
        vd = rec.get("vintage_date")
        if vd not in _VINTAGE_CACHE:
            _VINTAGE_CACHE[vd] = (team_inputs_from_vintage(rec),
                                  starter_inputs_from_vintage(rec),
                                  parks_from_vintage(rec))
        teams, starters, parks = _VINTAGE_CACHE[vd]
        note = (f"priced on the leaderboard vintage of {vd} "
                f"(covers through {rec.get('covers_through')})")
        if parks is None:
            note += ("; that record carries no park column, so the park term must be "
                     "taken as neutral rather than from the live index")
        return {"teams": teams, "starters": starters, "parks": parks,
                "parks_resolved": parks is not None, "source": "vintage",
                "vintage_date": vd, "covers_through": rec.get("covers_through"),
                "contaminated": False, "note": note}
    if not allow_fallback:
        return {"teams": {}, "starters": {}, "parks": None, "parks_resolved": False,
                "source": "none",
                "vintage_date": None, "covers_through": None, "contaminated": False,
                "note": f"no leaderboard vintage exists strictly before {game_date}"}
    if not _VINTAGE_FALLBACK_WARNED:
        _VINTAGE_FALLBACK_WARNED = True
        log.warning("betting_model: no leaderboard vintage strictly before %s; "
                    "falling back to the LIVE season-to-date leaderboards. Any "
                    "number produced from this read is leakage-contaminated. Run "
                    "leaderboard_vintages.snapshot() nightly to fix it.", game_date)
    return {"teams": team_inputs(), "starters": starter_inputs(),
            "parks": park_index(), "parks_resolved": True,
            "source": "live-leaderboards", "vintage_date": None,
            "covers_through": None, "contaminated": True,
            "note": ("no vintage exists strictly before this date, so the live "
                     "season-to-date leaderboards and the live park index were used; "
                     "they contain the game being priced and this number is "
                     "contaminated")}


def _vintage_resolver():
    """(resolve, stats).

    `resolve(game) -> (teams, starters, parks) or None`. None means the game has
    no vintage and must be skipped rather than graded on live leaderboards.

    THE THIRD ELEMENT IS THE FIX FOR THE PARK LEAK. It used to be a 2-tuple and
    the caller reached past it for `park_index()`, the live in-progress-season
    index, in both the coefficient fit and the pricing. A vintage with no park
    column now yields NEUTRAL_PARK_INDEX and the date is recorded in `stats`, so
    the eval artifact can say how many games were graded with the park term off
    instead of quietly graded with a leaking one.

    Memoized by GAME DATE inside the closure. The solvers evaluate the whole
    schedule dozens of times over a grid, and every game on a slate resolves
    to the same vintage, so this is the difference between a backtest that
    finishes and one that does not. `stats["park_source_by_date"]` is therefore
    keyed by date too; per-GAME counts are derived by the caller, which is the
    only place that knows the fit/eval split."""
    by_date: dict[str, tuple | None] = {}
    stats: dict = {"park_source_by_date": {}}

    def _resolve(g):
        d = g.get("date")
        if d not in by_date:
            b = inputs_as_of(d, allow_fallback=False)
            if b["source"] == "vintage" and b["teams"]:
                parks = b.get("parks")
                if parks is None:
                    parks = NEUTRAL_PARK_INDEX
                    stats["park_source_by_date"][d] = "neutral"
                else:
                    stats["park_source_by_date"][d] = "vintage"
                by_date[d] = (b["teams"], b["starters"], parks)
            else:
                by_date[d] = None
        return by_date[d]
    return _resolve, stats


# ---------------------------------------------------------------------------
# fitted (or literature) coefficients
# ---------------------------------------------------------------------------
def coefficients() -> dict:
    """The live run-scoring coefficients. Fitted set if data/betting_model_context.json
    exists, literature priors otherwise. Callers print `source` on the page."""
    ctx = _load_json(CONTEXT_PATH) or {}
    c = ctx.get("coefficients")
    if isinstance(c, dict) and all(k in c for k in ("b0", "b1", "b2", "b3", "b4")):
        return c
    return dict(LITERATURE_COEFFS)


def league_context() -> dict:
    ctx = _load_json(CONTEXT_PATH) or {}
    return {
        "season": ctx.get("season"),
        "n_games": ctx.get("n_games") or 0,
        "lg_rpg": ctx.get("lg_rpg"),
        "home_win_rate": ctx.get("home_win_rate"),
        "extra_inning_home_rate": ctx.get("extra_inning_home_rate_shrunk") or LITERATURE_TIE_HOME,
        "home_logit_offset": float(ctx.get("home_logit_offset") or 0.0),
        "generated_at": ctx.get("generated_at"),
        "source": (coefficients() or {}).get("source"),
    }


# ---------------------------------------------------------------------------
# the game model
# ---------------------------------------------------------------------------
def game_prevention_z(team: dict, starter: dict | None, teams: dict) -> tuple[float, dict]:
    """(z, detail) for one side's run prevention IN THIS GAME.

    The listed probable's own SEM+ covers ip_per_gs/9 of the game; the team
    bullpen covers the rest. With nobody announced the team's rotation average
    stands in for the starter share, which is exactly what a book does with a
    TBD."""
    scale = teams.get("_scale") or {}
    mu = scale.get("prev_mu", 100.0)
    sd = scale.get("prev_sd", 1.0) or 1.0
    pen_plus = team.get("bullpen_plus", 100.0)
    if starter and starter.get("sem_plus") is not None:
        share = (starter.get("ip_per_gs") or (DEFAULT_SP_SHARE * 9.0)) / 9.0
        share = max(0.25, min(0.85, share))
        sp_plus = float(starter["sem_plus"])
        src = "probable"
    else:
        share = float(team.get("sp_ip_share") or DEFAULT_SP_SHARE)
        sp_plus = float(team.get("rotation_plus", 100.0))
        src = "rotation-average"
    blended = share * sp_plus + (1.0 - share) * pen_plus
    return (blended - mu) / sd, {
        "starter_plus": round(sp_plus, 1), "bullpen_plus": round(pen_plus, 1),
        "starter_share": round(share, 3), "blend_plus": round(blended, 1),
        "source": src,
    }


def expected_runs(home_org: str, away_org: str, *, home_sp: dict | None = None,
                  away_sp: dict | None = None, teams: dict | None = None,
                  parks: dict | None = None, coeffs: dict | None = None,
                  home_adj: float | None = None,
                  diff_shrink: float | None = None) -> dict | None:
    """Expected runs for both sides, plus the components that produced them.
    None when either club is missing from the leaderboards.

    THE HOME-FIELD CORRECTION, because the raw fit gets it wrong for a
    structural reason worth naming. Fitting runs scored on a home dummy
    recovers only +0.013 runs of home field in 2026, while home teams actually
    won 52.3% of those same games. Both numbers are right: a home team leading
    after the top of the ninth DOES NOT BAT, so its runs-scored column is
    censored exactly in the games it wins. Regressing on runs therefore
    understates home field almost to zero.

    `home_adj` is the run-differential shift that reconciles them, solved in
    build_context so that the model's mean home win probability equals the
    observed home win rate. It is applied as +adj/2 to the home side and
    -adj/2 to the away side, so the runline moves coherently with the
    moneyline and the fair TOTAL is left untouched (the two halves cancel).
    Zero when no context has been built.

    THE MARGIN SHRINK, for a defect the first calibration table caught. The
    raw linear predictor put 2026 games as far apart as 90/10, and the bins
    above 0.80 came back 0.86 predicted against 0.67 actual: the model was
    more sure than the season was. `diff_shrink` scales the run DIFFERENTIAL
    toward zero while holding the pair mean, so it shrinks the moneyline and
    the runline together and leaves the fair total alone. It is fitted by
    minimizing log loss on completed games (`_solve_diff_shrink`), not chosen.
    1.0 when no context has been built."""
    teams = teams if teams is not None else team_inputs()
    parks = parks if parks is not None else park_index()
    c = coeffs or coefficients()
    if home_adj is None or diff_shrink is None:
        ctx = _load_json(CONTEXT_PATH) or {}
        if home_adj is None:
            home_adj = float(ctx.get("home_field_runs_adj") or 0.0)
        if diff_shrink is None:
            diff_shrink = float(ctx.get("diff_shrink") or 1.0)
    h, a = teams.get(home_org), teams.get(away_org)
    if not h or not a:
        return None
    park = (parks.get(home_org) or 1.0) - 1.0
    zp_home, det_home = game_prevention_z(h, home_sp, teams)
    zp_away, det_away = game_prevention_z(a, away_sp, teams)

    def _runs(z_off, z_prev_opp, is_home):
        return (c["b0"] + c["b1"] * z_off + c["b2"] * z_prev_opp
                + c["b3"] * park + (c["b4"] if is_home else 0.0)
                + (home_adj / 2.0 if is_home else -home_adj / 2.0))

    raw_home = _runs(h["z_off"], zp_away, True)
    raw_away = _runs(a["z_off"], zp_home, False)
    mid, half = (raw_home + raw_away) / 2.0, (raw_home - raw_away) / 2.0
    lam_home = max(1.5, min(9.5, mid + diff_shrink * half))
    lam_away = max(1.5, min(9.5, mid - diff_shrink * half))
    return {
        "lam_home": lam_home, "lam_away": lam_away,
        "home_field_runs_adj": round(float(home_adj), 4),
        "diff_shrink": round(float(diff_shrink), 4),
        "park_index": round(park + 1.0, 3),
        "home": {"org": home_org, "z_off": round(h["z_off"], 3),
                 "offense_plus": h["offense_plus"], "prevention": det_home},
        "away": {"org": away_org, "z_off": round(a["z_off"], 3),
                 "offense_plus": a["offense_plus"], "prevention": det_away},
    }


def _poisson_pmf(lam: float, k_max: int) -> list[float]:
    """pmf[0..k_max] for Poisson(lam), recurrence form (no factorials, no
    overflow at the tail)."""
    out = [math.exp(-lam)]
    for k in range(1, k_max + 1):
        out.append(out[-1] * lam / k)
    return out


def margin_distribution(lam_home: float, lam_away: float, k_max: int = 24) -> dict:
    """P(home runs - away runs = d) for d in [-k_max, k_max], by direct
    convolution of two Poissons (a Skellam, computed without Bessel functions
    so the serving path has no scipy dependency)."""
    ph = _poisson_pmf(lam_home, k_max)
    pa = _poisson_pmf(lam_away, k_max)
    dist = {}
    for i, p_i in enumerate(ph):
        if p_i < 1e-12:
            continue
        for j, p_j in enumerate(pa):
            if p_j < 1e-12:
                continue
            d = i - j
            dist[d] = dist.get(d, 0.0) + p_i * p_j
    return dist


def total_distribution(lam_home: float, lam_away: float, k_max: int = 40) -> list[float]:
    """P(total runs = k) - the sum of two independent Poissons is Poisson."""
    return _poisson_pmf(lam_home + lam_away, k_max)


def game_probabilities(home_org: str, away_org: str, *, home_sp=None, away_sp=None,
                       teams=None, parks=None, coeffs=None, tie_home=None,
                       home_adj=None, diff_shrink=None) -> dict | None:
    """The full model view of one game: moneyline, runline, fair total.

    Ties do not exist in MLB, so the P(margin = 0) mass is split by the
    MEASURED extra-innings home win rate (league_context, shrunk toward a coin
    flip on a 100-game prior), not by an invented constant."""
    er = expected_runs(home_org, away_org, home_sp=home_sp, away_sp=away_sp,
                       teams=teams, parks=parks, coeffs=coeffs, home_adj=home_adj,
                       diff_shrink=diff_shrink)
    if not er:
        return None
    lam_h, lam_a = er["lam_home"], er["lam_away"]
    dist = margin_distribution(lam_h, lam_a)
    p_tie = dist.get(0, 0.0)
    th = tie_home if tie_home is not None else (league_context().get("extra_inning_home_rate")
                                               or LITERATURE_TIE_HOME)
    p_home_reg = sum(p for d, p in dist.items() if d > 0)
    p_home = p_home_reg + p_tie * th
    # Runline. A -1.5 favourite must win by 2+. The +1.5 dog needs the game
    # inside one run OR an outright win, which is 1 - P(margin >= 2).
    p_home_minus15 = sum(p for d, p in dist.items() if d >= 2)
    p_away_minus15 = sum(p for d, p in dist.items() if d <= -2)
    tot = total_distribution(lam_h, lam_a)
    fair_total = lam_h + lam_a

    def over(line: float) -> float:
        need = math.floor(line) + 1 if line != int(line) else int(line) + 1
        return sum(tot[k] for k in range(need, len(tot)))

    return {
        "home_org": home_org, "away_org": away_org,
        "lam_home": round(lam_h, 3), "lam_away": round(lam_a, 3),
        "p_home": round(p_home, 5), "p_away": round(1.0 - p_home, 5),
        "p_home_minus_1_5": round(p_home_minus15, 5),
        "p_away_minus_1_5": round(p_away_minus15, 5),
        "p_home_plus_1_5": round(1.0 - p_away_minus15, 5),
        "p_away_plus_1_5": round(1.0 - p_home_minus15, 5),
        "fair_total": round(fair_total, 2),
        "over": over,                      # callable; the export resolves a line
        "components": er,
        "model_version": MODEL_VERSION,
    }


# ---------------------------------------------------------------------------
# market math
# ---------------------------------------------------------------------------
def devig(decimals: dict, method: str = "proportional") -> dict:
    """Raw prices -> fair (no-vig) probabilities.

    PROPORTIONAL method: q_i = 1/decimal_i, then p_i = q_i / sum(q). The sum of
    the raw implieds is the overround (a two-way MLB moneyline at -110/-110
    sums to 1.0476, a 4.76% hold); dividing it out spreads the vig in
    proportion to each side's raw probability.

    This is a CHOICE. Shin's method and the power method both take relatively
    more vig off the longshot, which moves a fair probability by up to a point
    on a lopsided moneyline and therefore moves every edge on the page. The
    method name ships in the payload so the number can be audited."""
    if method != "proportional":
        raise ValueError(f"unsupported de-vig method {method!r}")
    raw = {}
    for k, d in (decimals or {}).items():
        try:
            dv = float(d)
        except (TypeError, ValueError):
            continue
        if dv > 1.0:
            raw[k] = 1.0 / dv
    s = sum(raw.values())
    if not raw or s <= 0:
        return {}
    return {k: v / s for k, v in raw.items()}


def hold_pct(decimals: dict) -> float | None:
    """The book's hold on a market: sum of raw implieds minus 1, in percent."""
    raw = [1.0 / float(d) for d in (decimals or {}).values() if _pos(d)]
    return None if not raw else (sum(raw) - 1.0) * 100.0


def _pos(d) -> bool:
    try:
        return float(d) > 1.0
    except (TypeError, ValueError):
        return False


def ev_per_unit(p: float, decimal: float) -> float:
    """Expected profit on a 1-unit stake at `decimal` odds given probability p."""
    return p * (decimal - 1.0) - (1.0 - p)


def kelly_fraction(p: float, decimal: float) -> float:
    """Full-Kelly stake fraction. INFORMATIONAL ONLY on this site: the public
    record is flat 1 unit, always, because a variable stake makes a published
    ROI unauditable and invites the exact behaviour the disclaimer warns
    against. Negative means no bet."""
    b = decimal - 1.0
    if b <= 0:
        return 0.0
    return max(0.0, (p * b - (1.0 - p)) / b)


def edge(p_model: float, p_fair: float) -> float:
    """Our probability minus the de-vigged market probability. Positive means
    the model thinks the market is short."""
    return p_model - p_fair


# ---------------------------------------------------------------------------
# offline game results (for fitting + backtest)
# ---------------------------------------------------------------------------
_SPORT_RE = re.compile(rb"/api/v1/sports/(\d+)")


def _mlb_feed_paths() -> list[Path]:
    """MLB (sportId 1) game feeds inside the existing StatsAPI feed cache.
    The cache is mostly minor-league, so the sport is sniffed off the first
    few KB rather than parsing 18k files."""
    if not FEED_CACHE.exists():
        return []
    out = []
    for p in sorted(FEED_CACHE.glob("*.json")):
        try:
            head = p.open("rb").read(9000)
        except OSError:
            continue
        m = _SPORT_RE.search(head)
        if m and m.group(1) == b"1":
            out.append(p)
    return out


def _write_rows(path, rows) -> None:
    """Sibling temp then an atomic, RETRYING replace.

    The results cache is read by the backtest while the nightly may be
    rewriting it, and a half-written JSON array that still parses is the
    failure mode this codebase spent 2026-08-06 removing from its other
    artifacts.

    The retry is not optional on Windows: os.replace raises PermissionError
    (WinError 5) whenever a reader holds the target open, so a bare call would
    turn a routine concurrent read into an exception that propagates out of
    build_game_cache and discards a completed 1.5GB feed walk. storage owns the
    hardened version, with a 30 second deadline and backoff; reuse it rather
    than growing a second, weaker copy here.

    A failed swap leaves the PREVIOUS cache intact, which is the right outcome:
    results are regenerable, and being a run behind beats serving a truncated
    results set to a published record."""
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    try:
        tmp.write_text(json.dumps(rows), encoding="utf-8")
        try:
            from storage import _atomic_replace
        except Exception:                                     # noqa: BLE001
            _atomic_replace = None
        if _atomic_replace is not None:
            _atomic_replace(tmp, path)
        else:
            os.replace(tmp, path)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


SCHEDULE_API = "https://statsapi.mlb.com/api/v1/schedule"


def _row_from_schedule(g: dict, fallback_date: str | None) -> dict | None:
    """One schedule game -> the SAME compact row shape the feed walk produces.

    Kept byte-compatible with the feed path on purpose: the two sources have to
    be mergeable by game_pk, and a row whose shape depends on which door it came
    through would make the fit and the backtest quietly source-dependent."""
    if (g.get("status") or {}).get("abstractGameState") != "Final":
        return None
    # gameType=R is a query parameter, not a promise about the payload. The
    # backtest must never see spring training, exhibition or postseason games:
    # they carry different team quality and different roster rules, and the fit
    # would silently absorb both.
    if (g.get("gameType") or "R") != "R":
        return None
    teams = g.get("teams") or {}
    home, away = teams.get("home") or {}, teams.get("away") or {}
    line = g.get("linescore") or {}
    lt = line.get("teams") or {}
    hr = (lt.get("home") or {}).get("runs", home.get("score"))
    ar = (lt.get("away") or {}).get("runs", away.get("score"))
    if hr is None or ar is None:
        return None
    ho = _org((home.get("team") or {}).get("abbreviation")
              or (home.get("team") or {}).get("name"))
    ao = _org((away.get("team") or {}).get("abbreviation")
              or (away.get("team") or {}).get("name"))
    if not ho or not ao:
        return None
    return {
        "game_pk": g.get("gamePk"),
        "season": str(g.get("season") or ""),
        "date": g.get("officialDate") or fallback_date,
        "home_org": ho, "away_org": ao,
        "home_runs": int(hr), "away_runs": int(ar),
        "innings": line.get("currentInning"),
        "home_sp": (home.get("probablePitcher") or {}).get("id"),
        "away_sp": (away.get("probablePitcher") or {}).get("id"),
    }


def fetch_finals(start_date: str, end_date: str, *, log_fn=None) -> list[dict]:
    """Final regular-season MLB games in a date range, straight from StatsAPI.

    ONE request for the whole range. This exists so the results set does not
    depend on the Statcast feed cache filling up as a side effect of an
    unrelated job: measured on 2026-08-06, .cache/game_feeds held 0 of 15 games
    for 2026-08-05 and 0 of 11 for 2026-08-06, so the feed walk could not have
    seen a single game the leaderboard vintages were able to price."""
    import feed_cache
    resp = feed_cache.SESSION.get(
        SCHEDULE_API,
        params={"sportId": 1, "startDate": start_date, "endDate": end_date,
                "gameType": "R", "hydrate": "probablePitcher,linescore"},
        timeout=30)
    resp.raise_for_status()
    data = resp.json()
    out = []
    for d in data.get("dates") or []:
        for g in d.get("games") or []:
            row = _row_from_schedule(g, d.get("date"))
            if row and row.get("game_pk"):
                out.append(row)
    if log_fn:
        log_fn(f"betting_model: StatsAPI returned {len(out)} final games "
               f"for {start_date}..{end_date}")
    return out


def _topup_game_cache(cached: list[dict], *, log_fn=None) -> tuple[list[dict], bool]:
    """Extend the cached results with anything final since the last cached date.

    THE BUG THIS FIXES (2026-08-06). build_game_cache returned the cached file
    whenever it existed and the ONLY caller passed no force, so the results set
    could never advance past the day it was first written. It sat at
    2026-08-04 while the first vintage-gradable game date was 2026-08-06, which
    means every game the vintages could honestly price was outside the results
    set and `n_graded` was structurally pinned at 0 no matter how many nightly
    vintages accrued. The validation clock read as running and was not.

    Re-fetches the LAST cached date as well as everything after it, because a
    late-finishing game is written while that date is still the newest one and
    would otherwise be skipped forever.

    A fetch failure returns the cache untouched and says so. Results are the
    input to a published record; degrading them silently is worse than being a
    day behind."""
    today = _dt.date.today().isoformat()
    season = today[:4]

    # ANCHOR TO ONE SEASON. The schedule endpoint honours a date RANGE, not a
    # season, so a range that spans an offseason returns both: measured live,
    # 2025-09-20..2026-04-10 came back {'2026': 206, '2025': 121}. Merging that
    # would pool two seasons into one file, and every production caller reads
    # completed_games(None), so the fit would regress last season's outcomes
    # against THIS season's live team ratings and the published n_games would
    # roughly double at the rollover.
    #
    # docs/diamond-betting.md is explicit that this sample must not exist: a
    # partial 2026 tail plus an early 2027 run "should not" be accepted as one
    # sample, "the leaderboards reset between seasons". Resuming inside the
    # current season is what keeps the honest sample honest.
    #
    # Ignoring dates at or beyond today also stops a single bad or future-dated
    # row from making `last >= today` true forever, which would silently freeze
    # the top-up: the exact failure this function exists to fix.
    in_season = [r.get("date") for r in cached
                 if r.get("date") and r["date"] < today
                 and str(r.get("season") or r["date"][:4]) == season]
    # First run of a new season: start at the season boundary rather than
    # reaching back across the offseason.
    last = max(in_season) if in_season else f"{season}-01-01"
    try:
        fresh = fetch_finals(last, today, log_fn=log_fn)
    except Exception as exc:                                  # noqa: BLE001
        log.warning("betting_model: could not refresh completed games from "
                    "StatsAPI (%s); serving the cache, last game %s", exc, last)
        return cached, False

    if not fresh:
        # A 200 with zero usable rows is not the same as "no new games", and
        # treating it as such is exactly the empty-but-valid failure this
        # module keeps meeting. It happens for real when a hydrate key is
        # renamed and _row_from_schedule starts returning None for everything.
        # Logged through the module logger, not log_fn, because the production
        # caller passes no log_fn and this must not be silent there.
        log.warning("betting_model: StatsAPI returned no usable final games for "
                    "%s..%s. If games were played in that window the response "
                    "shape has changed and the results set is now frozen.",
                    last, today)
        return cached, False

    by_pk = {r["game_pk"]: r for r in cached if r.get("game_pk")}
    before = len(by_pk)
    # CONTENT change, not just cardinality. The range deliberately re-reads the
    # last cached date to catch a game that finished late, and a corrected score
    # replaces a row without changing the count. Deciding to write on `added`
    # alone would return the corrected rows to this caller and leave the wrong
    # ones on disk, so the next process would read the stale score back.
    changed = False
    for r in fresh:
        if str(r.get("season") or (r.get("date") or "")[:4]) != season:
            continue        # belt and braces: never let a neighbouring season in
        pk = r["game_pk"]
        if by_pk.get(pk) != r:
            changed = True
        by_pk[pk] = r
    rows = sorted(by_pk.values(),
                  key=lambda r: (r.get("date") or "", r.get("game_pk") or 0))
    added = len(rows) - before
    if changed:
        log.info("betting_model: results now through %s (+%d new, %d fetched)",
                 max(r.get("date") or "" for r in rows), added, len(fresh))
        if log_fn:
            log_fn(f"betting_model: +{added} completed game(s), now through "
                   f"{max(r.get('date') or '' for r in rows)}")
    return rows, changed


def build_game_cache(*, force: bool = False, refresh: bool = True,
                     log_fn=None) -> list[dict]:
    """Completed MLB games as compact rows.

    Two doors. The FULL build walks .cache/game_feeds, which is a 1.5GB scan of
    ~18k mostly-minor-league files, so it runs once and is cached. Every
    subsequent call tops the cache up from the StatsAPI schedule instead, which
    is one request.

    That split is the fix for the frozen-cache bug described on _topup_game_cache.
    Pass refresh=False for an offline read that is guaranteed not to touch the
    network."""
    GAME_CACHE.mkdir(parents=True, exist_ok=True)
    out_path = GAME_CACHE / "completed_games.json"
    if out_path.exists() and not force:
        cached = _load_json(out_path)
        if isinstance(cached, list) and cached:
            if not refresh:
                return cached
            rows, changed = _topup_game_cache(cached, log_fn=log_fn)
            if changed:
                _write_rows(out_path, rows)
            return rows
    rows: list[dict] = []
    paths = _mlb_feed_paths()
    if log_fn:
        log_fn(f"betting_model: scanning {len(paths)} MLB feeds")
    for p in paths:
        d = _load_json(p)
        if not isinstance(d, dict):
            continue
        gd = d.get("gameData") or {}
        if (gd.get("status") or {}).get("abstractGameState") != "Final":
            continue
        game = gd.get("game") or {}
        if game.get("type") != "R":
            continue
        teams = gd.get("teams") or {}
        line = ((d.get("liveData") or {}).get("linescore") or {})
        lt = line.get("teams") or {}
        hr, ar = (lt.get("home") or {}).get("runs"), (lt.get("away") or {}).get("runs")
        if hr is None or ar is None:
            continue
        pp = gd.get("probablePitchers") or {}
        rows.append({
            "game_pk": game.get("pk"),
            "season": str(game.get("season") or ""),
            "date": (gd.get("datetime") or {}).get("officialDate"),
            "home_org": _org((teams.get("home") or {}).get("abbreviation")
                             or (teams.get("home") or {}).get("name")),
            "away_org": _org((teams.get("away") or {}).get("abbreviation")
                             or (teams.get("away") or {}).get("name")),
            "home_runs": int(hr), "away_runs": int(ar),
            "innings": line.get("currentInning"),
            "home_sp": (pp.get("home") or {}).get("id"),
            "away_sp": (pp.get("away") or {}).get("id"),
        })
    rows = [r for r in rows if r["home_org"] and r["away_org"]]

    # COLD BOOTSTRAP. The feed walk finds nothing on a box whose .cache/game_feeds
    # is empty or has been pruned, and on 2026-08-06 that was the live state:
    # 0 of 15 feeds for 2026-08-05 and 0 of 11 for 2026-08-06. Writing that empty
    # result and returning it would persist an empty-but-valid [] that every
    # consumer reads as "no games have been played", and because the top-up
    # branch above requires a NON-EMPTY cache, the StatsAPI door could never be
    # reached to repair it. The walk would simply run again, find nothing again,
    # and the results set would be permanently zero.
    #
    # So when the walk comes back empty, fall through to StatsAPI for the season
    # rather than committing the empty answer.
    if not rows and refresh:
        log.warning("betting_model: the game-feed walk found no completed MLB "
                    "games (%d MLB feeds on disk). Falling back to StatsAPI for "
                    "the season rather than caching an empty results set.",
                    len(paths))
        try:
            season = str(_dt.date.today().year)
            rows = fetch_finals(f"{season}-01-01", _dt.date.today().isoformat(),
                                log_fn=log_fn)
            rows.sort(key=lambda r: (r.get("date") or "", r.get("game_pk") or 0))
        except Exception as exc:                              # noqa: BLE001
            log.error("betting_model: StatsAPI bootstrap failed too (%s); the "
                      "results set stays EMPTY and every betting number "
                      "downstream is unfitted", exc)

    if not rows:
        # Never persist an empty results set. A missing file re-tries next run;
        # a committed [] looks like a legitimately empty season forever.
        log.error("betting_model: refusing to cache an EMPTY completed-games "
                  "set; leaving %s as it was so the next run retries",
                  out_path.name)
        return rows

    _write_rows(out_path, rows)
    if log_fn:
        log_fn(f"betting_model: cached {len(rows)} completed games -> {out_path}")
    return rows


def completed_games(season: str | None = None, *, refresh: bool = True) -> list[dict]:
    rows = build_game_cache(refresh=refresh)
    return [r for r in rows if not season or r.get("season") == str(season)]


# ---------------------------------------------------------------------------
# fitting
# ---------------------------------------------------------------------------
def _design_rows(games: list[dict], teams: dict, parks: dict, starters: dict,
                 resolve=None):
    """Two rows per game (each side as the scoring side) -> (X, y, meta).

    `resolve(game) -> (teams, starters, parks) | None` swaps in per-game
    features, so the SAME design code serves the live path and the vintage path.
    A game the resolver declines is dropped, never quietly graded on the
    fallback. The PARK comes out of the resolver too: it is a fitted feature
    (b3), so a resolver-supplied game whose park still came from the caller's
    live index would leak into the coefficient itself."""
    X, y, meta = [], [], []
    for g in games:
        gt, gs, gpk = teams, starters, parks
        if resolve is not None:
            got = resolve(g)
            if not got:
                continue
            gt, gs, gpk = got
        h, a = gt.get(g["home_org"]), gt.get(g["away_org"])
        if not h or not a:
            continue
        park = (gpk.get(g["home_org"]) or 1.0) - 1.0
        zp_home, _ = game_prevention_z(h, gs.get(g.get("home_sp")), gt)
        zp_away, _ = game_prevention_z(a, gs.get(g.get("away_sp")), gt)
        X.append([1.0, h["z_off"], zp_away, park, 1.0])
        y.append(float(g["home_runs"]))
        meta.append((g, "home"))
        X.append([1.0, a["z_off"], zp_home, park, 0.0])
        y.append(float(g["away_runs"]))
        meta.append((g, "away"))
    return X, y, meta


def fit_coefficients(games: list[dict] | None = None, *, teams=None, parks=None,
                     starters=None, resolve=None) -> dict | None:
    """OLS for the five run-scoring coefficients. None when there is nothing to
    fit on (no feed cache), which is what sends `coefficients()` to the
    literature priors."""
    import numpy as np

    teams = teams if teams is not None else team_inputs()
    parks = parks if parks is not None else park_index()
    starters = starters if starters is not None else starter_inputs()
    games = games if games is not None else completed_games()
    if not games or (not teams and resolve is None):
        return None
    X, y, _ = _design_rows(games, teams, parks, starters, resolve)
    if len(X) < 200:
        return None
    A, b = np.asarray(X, dtype=float), np.asarray(y, dtype=float)
    beta, *_ = np.linalg.lstsq(A, b, rcond=None)
    resid = b - A @ beta
    ss_tot = float(((b - b.mean()) ** 2).sum())
    return {
        "b0": float(beta[0]), "b1": float(beta[1]), "b2": float(beta[2]),
        "b3": float(beta[3]), "b4": float(beta[4]),
        "source": "fitted",
        "n_rows": len(X),
        "rmse": float(math.sqrt(float((resid ** 2).mean()))),
        "r2": float(1.0 - float((resid ** 2).sum()) / ss_tot) if ss_tot else None,
    }


def _p_home_series(games, teams, parks, starters, coeffs, tie_home, adj, shrink,
                   resolve=None):
    """(predicted p_home, observed home win) for every game. The inner loop of
    both solvers and of the grader, written once so they cannot drift apart.
    `resolve` has the same contract as in `_design_rows`."""
    ps, ys = [], []
    for g in games:
        gt, gs, gpk = teams, starters, parks
        if resolve is not None:
            got = resolve(g)
            if not got:
                continue
            gt, gs, gpk = got
        gp = game_probabilities(g["home_org"], g["away_org"],
                                home_sp=gs.get(g.get("home_sp")),
                                away_sp=gs.get(g.get("away_sp")),
                                teams=gt, parks=gpk, coeffs=coeffs,
                                tie_home=tie_home, home_adj=adj, diff_shrink=shrink)
        if gp:
            ps.append(gp["p_home"])
            ys.append(1 if g["home_runs"] > g["away_runs"] else 0)
    return ps, ys


def _solve_home_adj(games, teams, parks, starters, coeffs, tie_home, target: float,
                    shrink: float = 1.0, resolve=None) -> float:
    """The run-differential shift that makes the model's MEAN home win
    probability equal the observed home win rate. Bisection over a bounded
    interval; one parameter, one target, no free lunch. See the docstring on
    expected_runs for why the raw fit needs it."""
    def mean_p(adj: float) -> float:
        ps, _ = _p_home_series(games, teams, parks, starters, coeffs, tie_home, adj,
                               shrink, resolve)
        return sum(ps) / len(ps) if ps else 0.5

    lo, hi = -0.60, 1.20
    if mean_p(lo) > target or mean_p(hi) < target:
        return 0.0
    for _ in range(20):
        mid = (lo + hi) / 2.0
        if mean_p(mid) < target:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2.0, 4)


def _solve_diff_shrink(games, teams, parks, starters, coeffs, tie_home,
                       adj: float = 0.0, resolve=None) -> tuple[float, float]:
    """(shrink, log loss) minimizing log loss over a coarse-to-fine grid.

    ONE parameter. A value below 1 means the linear predictor spread the
    league further apart than the results did, which is the normal failure
    mode for a model built out of season-long rate stats: the inputs are
    themselves shrunk estimates, and stacking them recovers less signal than
    their spread implies."""
    def ll(s: float) -> float:
        ps, ys = _p_home_series(games, teams, parks, starters, coeffs, tie_home, adj, s,
                                resolve)
        return _logloss(ps, ys) if ps else 9.9

    best_s, best_l = 1.0, ll(1.0)
    for step, span in ((0.1, 8), (0.02, 5)):
        centre = best_s
        for i in range(-span, span + 1):
            s = round(centre + i * step, 4)
            if s < 0.2 or s > 1.6:
                continue
            l = ll(s)
            if l < best_l:
                best_s, best_l = s, l
    return best_s, round(best_l, 6)


def build_context(*, season: str | None = None, write: bool = True, log_fn=None) -> dict:
    """Fit the coefficients and measure the league constants, then write
    data/betting_model_context.json. Offline; safe to re-run."""
    games = completed_games(season)
    teams, parks, starters = team_inputs(), park_index(), starter_inputs()
    coeffs = fit_coefficients(games, teams=teams, parks=parks, starters=starters)
    n = len(games)
    lg_rpg = (sum(g["home_runs"] + g["away_runs"] for g in games) / (2.0 * n)) if n else None
    home_wins = sum(1 for g in games if g["home_runs"] > g["away_runs"])
    home_rate = (home_wins / n) if n else None
    extras = [g for g in games if (g.get("innings") or 9) > 9]
    x_wins = sum(1 for g in extras if g["home_runs"] > g["away_runs"])
    tie_raw = (x_wins / len(extras)) if extras else None
    tie_shrunk = ((x_wins + 0.5 * TIE_SHRINK_K) / (len(extras) + TIE_SHRINK_K)
                  if extras else LITERATURE_TIE_HOME)
    # Two one-parameter corrections, solved in sequence and then refined once,
    # because they interact: shrinking the differential moves the mean home
    # probability, and shifting home field moves the log loss the shrink is
    # minimizing. Two passes is enough; the second changes the shrink in the
    # third decimal.
    adj, shrink, shrink_ll = 0.0, 1.0, None
    if n and coeffs:
        shrink, shrink_ll = _solve_diff_shrink(games, teams, parks, starters, coeffs,
                                               tie_shrunk, 0.0)
        adj = _solve_home_adj(games, teams, parks, starters, coeffs, tie_shrunk,
                              home_rate, shrink)
        shrink, shrink_ll = _solve_diff_shrink(games, teams, parks, starters, coeffs,
                                               tie_shrunk, adj)
        adj = _solve_home_adj(games, teams, parks, starters, coeffs, tie_shrunk,
                              home_rate, shrink)
    ctx = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "model_version": MODEL_VERSION,
        "season": season or (games[-1]["season"] if games else None),
        "n_games": n,
        "lg_rpg": round(lg_rpg, 4) if lg_rpg else None,
        "home_win_rate": round(home_rate, 4) if home_rate else None,
        "extra_inning_games": len(extras),
        "extra_inning_home_rate_raw": round(tie_raw, 4) if tie_raw is not None else None,
        "extra_inning_home_rate_shrunk": round(tie_shrunk, 4),
        "home_field_runs_adj": adj,
        "diff_shrink": shrink,
        "diff_shrink_log_loss": shrink_ll,
        "diff_shrink_note": ("run-differential shrink fitted by log loss on completed games; "
                             "below 1.0 means the raw predictor separated clubs further than "
                             "the results did, and the fair total is untouched by it"),
        "home_field_note": ("the runs regression recovers almost no home field because a "
                            "home team leading after the top of the ninth never bats; the "
                            "adjustment restores the observed home win rate as a run "
                            "differential, leaving the fair total unchanged"),
        "coefficients": coeffs or dict(LITERATURE_COEFFS),
        "source_note": ("fit on completed games read out of .cache/game_feeds, offline; "
                        "team inputs are season-to-date leaderboards, so this fit is "
                        "IN-SAMPLE and cannot validate the model"),
    }
    if write:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        CONTEXT_PATH.write_text(json.dumps(ctx, indent=1), encoding="utf-8")
        if log_fn:
            log_fn(f"betting_model: wrote {CONTEXT_PATH.name} (n={n})")
    return ctx


# ---------------------------------------------------------------------------
# backtest
# ---------------------------------------------------------------------------
def _brier(ps: list[float], ys: list[int]) -> float:
    return sum((p - y) ** 2 for p, y in zip(ps, ys)) / max(1, len(ps))


def _logloss(ps: list[float], ys: list[int]) -> float:
    eps = 1e-9
    return -sum(y * math.log(max(p, eps)) + (1 - y) * math.log(max(1 - p, eps))
                for p, y in zip(ps, ys)) / max(1, len(ps))


def _paired_brier_skill(ps: list[float], ys: list[int], base: float) -> dict:
    """Is the model's Brier better than a constant baseline's, and by enough?

    The pairing matters. Comparing two Brier scores game by game removes the
    game-to-game variance that dominates a raw difference of means, which is
    the only reason a 0.006 margin is measurable at all. d_i is positive when
    the model beat the baseline on that game.

        delta   mean of d_i (positive = the model is better)
        t       delta / standard error
        beats_baseline_95  t >= 1.645, i.e. the one-sided 95% lower bound on
                           delta clears zero

    `n_for_95` is how many games a margin THIS SIZE would need to reach that
    bar, which is where VINTAGE_MIN_GRADED_GAMES came from."""
    n = len(ps)
    if n < 2:
        return {"delta": None, "sd": None, "t": None,
                "beats_baseline_95": False, "n_for_95": None}
    d = [((base - y) ** 2) - ((p - y) ** 2) for p, y in zip(ps, ys)]
    mu = sum(d) / n
    var = sum((x - mu) ** 2 for x in d) / n
    sd = math.sqrt(var)
    se = sd / math.sqrt(n) if sd else 0.0
    t = (mu / se) if se else None
    return {
        "delta": round(mu, 6),
        "sd": round(sd, 5),
        "t": round(t, 3) if t is not None else None,
        "beats_baseline_95": bool(t is not None and t >= Z_95_ONE_SIDED),
        "n_for_95": (round((Z_95_ONE_SIDED * sd / mu) ** 2) if (sd and mu > 0) else None),
        "baseline": round(base, 4),
        "note": ("paired per-game Brier difference against the constant home-field "
                 "baseline; positive means the model is better, and t >= 1.645 is the "
                 "one-sided 95% bar"),
    }


def _calibration(ps: list[float], ys: list[int], bins: int = 10) -> list[dict]:
    out = []
    for i in range(bins):
        lo, hi = i / bins, (i + 1) / bins
        sel = [(p, y) for p, y in zip(ps, ys) if (lo <= p < hi or (i == bins - 1 and p == 1.0))]
        if not sel:
            continue
        out.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": len(sel),
                    "pred": round(sum(p for p, _ in sel) / len(sel), 4),
                    "actual": round(sum(y for _, y in sel) / len(sel), 4)})
    return out


def sweep_min_edge(rows: list[dict], *, grid=None, z: float = Z_95_ONE_SIDED,
                   min_bets: int = 100) -> dict:
    """The smallest edge threshold whose graded ROI lower bound clears zero.

    `rows` are SETTLED bets: {"edge": model minus de-vigged fair, "decimal":
    the price taken, "won": bool}. For each candidate threshold the qualifying
    bets are re-graded at flat 1 unit, and the threshold is accepted only when

        mean(profit) - z * stderr(profit) > 0

    which is a one-sided 95% lower bound on ROI per unit risked. The SMALLEST
    qualifying threshold wins, because a higher one is a smaller sample
    pretending to be a stronger result.

    Returns {"min_edge": float|None, "reason": str, "candidates": [...]}.
    None is the normal answer and stays the answer until a graded price
    history exists: this module has never held one, since the odds ingest only
    started caching snapshots and nothing has settled against them yet."""
    grid = list(grid) if grid is not None else [round(0.005 * i, 3) for i in range(1, 21)]
    if not rows:
        return {"min_edge": None, "n_rows": 0, "candidates": [],
                "reason": ("no settled bets with both a model edge and a taken price; "
                           "the threshold cannot be swept on data that does not exist")}
    cands = []
    for thr in sorted(grid):
        sel = [r for r in rows
               if r.get("edge") is not None and float(r["edge"]) >= thr
               and _pos(r.get("decimal"))]
        n = len(sel)
        if n < min_bets:
            cands.append({"edge": thr, "n": n, "qualified": False,
                          "reason": f"n < {min_bets}"})
            continue
        profits = [(float(r["decimal"]) - 1.0) if r.get("won") else -1.0 for r in sel]
        mu = sum(profits) / n
        var = sum((p - mu) ** 2 for p in profits) / n
        se = math.sqrt(var / n) if var else 0.0
        lower = mu - z * se
        cands.append({"edge": thr, "n": n, "roi": round(mu, 5),
                      "roi_lower_95": round(lower, 5), "qualified": bool(lower > 0)})
    ok = [c for c in cands if c.get("qualified")]
    if not ok:
        return {"min_edge": None, "n_rows": len(rows), "candidates": cands,
                "reason": ("no edge threshold produced an ROI whose one-sided 95% lower "
                           "bound clears zero on the graded sample")}
    best = ok[0]
    return {"min_edge": best["edge"], "n_rows": len(rows), "candidates": cands,
            "reason": (f"smallest threshold whose graded ROI lower bound clears zero "
                       f"(n={best['n']}, ROI {best['roi']:+.3f}, "
                       f"lower bound {best['roi_lower_95']:+.3f})")}


def _odds_history_dates() -> list[str]:
    """Dates with at least one cached odds snapshot. Filenames only, so this
    costs nothing and never parses a snapshot."""
    d = ROOT / ".cache" / "odds"
    if not d.exists():
        return []
    return sorted({p.name[:10] for p in d.glob("*.json") if len(p.name) >= 10})


def _shadow_graded_bets() -> list[dict]:
    """Settled paper bets from the shadow ledger, or [] when it does not exist.

    THE CIRCLE THIS BREAKS. sweep_min_edge needs settled bets carrying a taken
    price, and min_edge_gate was only ever called with graded_bets=None, so the
    third gate could never open: publishing a pick needed min_edge, and min_edge
    needed settled picks. betting_shadow records what the model WOULD have bet at
    the price actually on the board and settles it against the result, which
    supplies that history without the site claiming anything.

    Deliberately best effort and silent on absence: a missing ledger is the
    normal state before the first slate is logged, and the gate already reports
    `have: 0` in that case, which is the honest answer."""
    try:
        import betting_shadow
        return betting_shadow.graded_bets()
    except Exception:                                         # noqa: BLE001
        log.debug("betting_model: shadow ledger unavailable", exc_info=True)
        return []


def min_edge_gate(vintage_block: dict | None, *, graded_bets: list[dict] | None = None) -> dict:
    """Whether `min_edge` may be set at all, and what it is if so.

    THREE GATES, all of which must be open. Every one of them is currently
    closed, and the honest thing is to say which:

      1. VINTAGE SAMPLE. The vintage-mode backtest must have graded at least
         VINTAGE_MIN_GRADED_GAMES games. See that constant for the derivation:
         it is the n at which the observed (contaminated, therefore optimistic)
         margin over the home-field baseline would be detectable at one-sided
         95%.
      2. OUT-OF-SAMPLE SKILL. On that sample, the paired Brier difference
         against the home-field baseline must clear zero at one-sided 95%.
         Sample size alone is not evidence; this is the actual claim.
      3. A GRADED PRICE HISTORY. A threshold is a statement about EV against
         real prices, so it can only be swept on settled bets with a taken
         price. Cached odds snapshots accumulate nightly alongside the
         vintages, and the join that produces settled rows is not built yet.

    Gate 3 is why `min_edge` would still be None on the day gates 1 and 2 open:
    a calibrated probability is not an edge until there is a market to have an
    edge against."""
    vb = vintage_block or {}
    n_graded = int(vb.get("n_graded") or 0)
    skill = vb.get("skill_vs_home_base") or {}
    odds_dates = _odds_history_dates()
    # None means "look for them"; an explicit [] still means "none".
    rows = list(graded_bets if graded_bets is not None else _shadow_graded_bets())
    sweep = sweep_min_edge(rows)

    gates = [
        {"id": "vintage_sample",
         "need": f"{VINTAGE_MIN_GRADED_GAMES} vintage-graded games",
         "have": n_graded,
         "open": n_graded >= VINTAGE_MIN_GRADED_GAMES,
         "why": ("the contaminated forward margin over the home-field baseline is "
                 "+0.005794 Brier with a paired sd of 0.08647, so a margin that size "
                 "needs 603 games to clear one-sided 95%; 600 is that number, and a "
                 "clean margin will be smaller, so this is a floor and not a pass")},
        {"id": "out_of_sample_skill",
         "need": "paired Brier vs the home-field baseline, t >= 1.645",
         "have": skill.get("t"),
         "open": bool(skill.get("beats_baseline_95")),
         "why": ("sample size is not evidence; the model has to actually beat "
                 "'always take the home team' on games it could not see")},
        {"id": "graded_price_history",
         "need": ("settled bets with a taken price, enough that some edge threshold "
                  "clears an ROI lower bound of zero on at least 100 of them"),
         "have": len(rows),
         "open": bool(sweep.get("min_edge") is not None),
         "why": ("an edge threshold is a claim about EV against real prices; "
                 f"{len(odds_dates)} dates of odds snapshots are cached and no "
                 "settled-bet join exists yet")},
    ]
    all_open = all(g["open"] for g in gates)
    return {
        "min_edge": sweep.get("min_edge") if all_open else None,
        "all_gates_open": all_open,
        "gates": gates,
        "odds_snapshot_dates": len(odds_dates),
        "sweep": {k: sweep[k] for k in ("n_rows", "reason") if k in sweep},
        "policy": ("min_edge stays null until all three gates are open. A threshold "
                   "invented to make a pick appear is the single most dishonest number "
                   "this module could publish."),
    }


def _fit_tie_home(fit_games: list[dict]) -> float:
    """The extra-innings home win rate measured on a FIT window only, shrunk
    toward a coin flip on the same 100-game prior build_context uses. Falls
    back to the literature constant when the window has no extra-inning games,
    never to a season-wide number the eval window helped produce."""
    extras = [g for g in fit_games if (g.get("innings") or 9) > 9]
    if not extras:
        return LITERATURE_TIE_HOME
    wins = sum(1 for g in extras if g["home_runs"] > g["away_runs"])
    return (wins + 0.5 * TIE_SHRINK_K) / (len(extras) + TIE_SHRINK_K)


def backtest(*, season: str | None = None, split_date: str | None = None,
             write: bool = True, log_fn=None) -> dict:
    """Grade the model on completed games, in BOTH modes, offline.

    MODE 1, CONTAMINATED (`in_sample`, `forward`). The team inputs
    (offense_plus / rotation_plus / bullpen_plus / SEM+) are SEASON-TO-DATE
    aggregates as of the last leaderboard build, so every game graded here
    contributed to the features used to predict it. `forward` refits the
    coefficients on games before `split_date` and grades only games after it,
    which removes coefficient leakage but NOT feature leakage. Both are
    reported, both carry `mode: "contaminated"`, and neither can validate
    anything.

    MODE 2, VINTAGE (`vintage`). Each game is priced on the newest
    leaderboard vintage whose knowledge cutoff is strictly before it
    (leaderboard_vintages.as_of). Games with no such vintage are SKIPPED, not
    graded on the fallback, and the count of skipped games is reported. Until
    the nightly snapshot has been running, that is every game and the honest n
    is zero. When the sample is large enough the coefficients and both
    one-parameter corrections are refit inside the vintage window too, on
    vintage features.

    THE PARK INDEX IS PART OF "FEATURES" AND USED NOT TO BE. Until 2026-08-05
    this function built `parks = park_index()` once and handed the LIVE index
    (data/fa_meta.json = `fa_fit.park_factors(CLASS_YEAR - 1)`, the in-progress
    season) to the vintage fit AND the vintage pricing, so eval-window games
    contributed to the park factor used to grade them while the mode label said
    "no leakage". Parks now travel in the vintage record; a record written before
    that column existed prices its games on a NEUTRAL park and the count lands in
    `vintage.park_basis`. The contaminated modes below are UNCHANGED: they are
    labelled contaminated and their numbers stay comparable to the old artifact.

    `validated` is False, `gates_picks` is False and `min_edge` is None until
    the vintage mode carries the sample AND the skill AND a graded price
    history; `min_edge_gate` reports which of the three is missing.

    Baselines are what make the number readable: 0.500 flat, and the measured
    home-field rate. A model that cannot beat "always take the home team" has
    not earned a page."""
    games = completed_games(season)
    teams, parks, starters = team_inputs(), park_index(), starter_inputs()
    lv = _vintage_module()
    cov = {}
    if lv:
        try:
            cov = lv.coverage()
        except Exception:                                        # pragma: no cover
            cov = {}
    result = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "model_version": MODEL_VERSION,
        "season": season,
        "validated": False,
        "contaminated": True,
        "contamination": ("team inputs are season-to-date leaderboards, so every graded "
                          "game is inside its own features; this measures calibration, "
                          "not out-of-sample skill"),
        "gates_picks": False,
        "min_edge": None,
        "n_games": len(games),
        "modes": ["contaminated", "vintage"],
        "headline_mode": "contaminated",
        "vintage_coverage": cov,
    }
    if not games or not teams:
        result["status"] = "no data"
        result["note"] = ("no completed-game cache and/or no leaderboards; run "
                          "betting_model.build_game_cache() on a box that has "
                          ".cache/game_feeds")
        result["vintage"] = _empty_vintage_block(cov, len(games))
        result["min_edge_gate"] = min_edge_gate(result["vintage"])
        if write:
            EVAL_PATH.write_text(json.dumps(result, indent=1), encoding="utf-8")
        return result

    def _grade(fit_games, eval_games, label, mode, resolve=None):
        coeffs = fit_coefficients(fit_games, teams=teams, parks=parks, starters=starters,
                                  resolve=resolve) or dict(LITERATURE_COEFFS)
        # The extra-innings home rate is measured on the FIT window too. It used
        # to come from league_context(), which is fitted over the WHOLE season:
        # a small leak (one shrunk scalar off ~140 games) but a real one, and a
        # mode that calls itself honest cannot carry it.
        tie = _fit_tie_home(fit_games)
        # The home-field reconciliation is refit on the FIT window too, so the
        # forward split does not smuggle the evaluation window's home rate in
        # through the back door.
        fit_home_rate = (sum(1 for g in fit_games if g["home_runs"] > g["away_runs"])
                         / max(1, len(fit_games)))
        shrink, _ = _solve_diff_shrink(fit_games, teams, parks, starters, coeffs, tie, 0.0,
                                       resolve)
        adj = _solve_home_adj(fit_games, teams, parks, starters, coeffs, tie,
                              fit_home_rate, shrink, resolve)
        ps, ys, tot_err, n_tot = [], [], 0.0, 0
        for g in eval_games:
            gt, gs, gpk = teams, starters, parks
            if resolve is not None:
                got = resolve(g)
                if not got:
                    continue
                # `gpk`, not the enclosing `parks`. The enclosing one is the LIVE
                # park index (fa_meta.json = the in-progress season), and pricing
                # a vintage-mode eval game on it is the leak this lane closed.
                gt, gs, gpk = got
            gp = game_probabilities(g["home_org"], g["away_org"],
                                    home_sp=gs.get(g.get("home_sp")),
                                    away_sp=gs.get(g.get("away_sp")),
                                    teams=gt, parks=gpk, coeffs=coeffs, tie_home=tie,
                                    home_adj=adj, diff_shrink=shrink)
            if not gp:
                continue
            ps.append(gp["p_home"])
            ys.append(1 if g["home_runs"] > g["away_runs"] else 0)
            tot_err += abs(gp["fair_total"] - (g["home_runs"] + g["away_runs"]))
            n_tot += 1
        if not ps:
            return None
        base_home = sum(ys) / len(ys)
        return {
            "label": label,
            "mode": mode,
            "honest": mode == "vintage",
            "n": len(ps),
            "coefficients": coeffs,
            "home_field_runs_adj": adj,
            "diff_shrink": shrink,
            "extra_inning_home_rate": round(tie, 4),
            "brier": round(_brier(ps, ys), 5),
            "brier_flat_500": round(_brier([0.5] * len(ps), ys), 5),
            "brier_home_base": round(_brier([base_home] * len(ps), ys), 5),
            "log_loss": round(_logloss(ps, ys), 5),
            "log_loss_flat_500": round(_logloss([0.5] * len(ps), ys), 5),
            "accuracy": round(sum(1 for p, y in zip(ps, ys)
                                  if (p >= 0.5) == bool(y)) / len(ps), 4),
            "home_win_rate": round(base_home, 4),
            "mean_p_home": round(sum(ps) / len(ps), 4),
            "total_mae": round(tot_err / n_tot, 3) if n_tot else None,
            "skill_vs_home_base": _paired_brier_skill(ps, ys, base_home),
            "calibration": _calibration(ps, ys),
        }

    # --- mode 1: contaminated -------------------------------------------
    result["in_sample"] = _grade(games, games,
                                 "in-sample (coefficients and features both leak)",
                                 "contaminated")
    dates = sorted({g["date"] for g in games if g.get("date")})
    sd = split_date or (dates[int(len(dates) * 0.7)] if len(dates) > 20 else None)
    if sd:
        fit_g = [g for g in games if (g.get("date") or "") < sd]
        ev_g = [g for g in games if (g.get("date") or "") >= sd]
        if len(fit_g) > 200 and len(ev_g) > 50:
            result["split_date"] = sd
            result["forward"] = _grade(fit_g, ev_g,
                                       f"forward from {sd} (coefficient leakage removed, "
                                       "feature leakage remains)",
                                       "contaminated")

    # --- mode 2: vintage --------------------------------------------------
    result["vintage"] = _grade_vintage(games, cov, _grade, log_fn=log_fn)
    result["min_edge_gate"] = min_edge_gate(result["vintage"])
    result["min_edge"] = result["min_edge_gate"]["min_edge"]
    result["gates_picks"] = bool(result["min_edge"] is not None)
    result["validated"] = bool(result["min_edge_gate"]["all_gates_open"])
    result["contaminated"] = not result["validated"]
    result["headline_mode"] = "vintage" if result["validated"] else "contaminated"

    result["status"] = "ran"
    result["note"] = ("Two modes, both labelled. The in-sample and forward numbers are "
                      "CONTAMINATED: their features are season-to-date leaderboards that "
                      "contain the games being graded. The vintage number is the honest "
                      f"one and it graded {result['vintage'].get('n_graded', 0)} games. "
                      "A pick threshold is set from the vintage mode or from nothing.")
    if write:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        EVAL_PATH.write_text(json.dumps(result, indent=1), encoding="utf-8")
        if log_fn:
            log_fn(f"betting_model: wrote {EVAL_PATH.name} "
                   f"(vintage-graded {result['vintage'].get('n_graded', 0)} of "
                   f"{len(games)} games)")
    return result


def _empty_vintage_block(cov: dict, n_games: int) -> dict:
    return {
        "label": "vintage (each game priced on leaderboards dated strictly before it)",
        "mode": "vintage",
        "honest": True,
        "status": "no vintages",
        "n_vintages": int((cov or {}).get("n_vintages") or 0),
        "n_gradable": 0,
        "n_graded": 0,
        "n_skipped_no_vintage": n_games,
        "min_fit_games": VINTAGE_MIN_FIT_GAMES,
        "min_eval_games": VINTAGE_MIN_EVAL_GAMES,
        "min_graded_games_for_min_edge": VINTAGE_MIN_GRADED_GAMES,
        # None, not a zeroed block: "nothing was graded" and "everything graded
        # on a neutral park" are different facts and the reader gets to tell them
        # apart. `_grade_vintage` replaces this the moment anything resolves.
        "park_basis": None,
        "note": ("no completed game has a leaderboard vintage dated strictly before it, "
                 "so the honest sample is empty; run leaderboard_vintages.snapshot() "
                 "nightly and this number starts climbing"),
    }


def _vintage_cut_index(gradable: list[dict], dates: list[str]) -> int:
    """The index in `dates` where the fit window ends and the eval window
    begins. Whole slates never straddle the boundary, because the split is by
    date. See VINTAGE_FIT_TARGET_GAMES for why this is a target size rather
    than a share."""
    per_date: dict[str, int] = {}
    for g in gradable:
        per_date[g.get("date")] = per_date.get(g.get("date"), 0) + 1
    cum, target_idx = 0, len(dates) - 1
    for i, d in enumerate(dates):
        cum += per_date.get(d, 0)
        if cum >= VINTAGE_FIT_TARGET_GAMES:
            target_idx = i + 1
            break
    half_idx = max(1, int(len(dates) * VINTAGE_FIT_MAX_DATE_SHARE))
    return max(1, min(target_idx, half_idx, len(dates) - 1))


def _grade_vintage(games: list[dict], cov: dict, grade_fn, *, log_fn=None) -> dict:
    """The honest mode. Grades only games that have a vintage strictly before
    them, and refits everything inside that window on vintage features.

    The split is by DATE, not by row, so no two games from the same slate land
    on opposite sides of the fit/eval boundary.

    THE PARK BASIS IS REPORTED, not assumed. Every input this mode uses is dated
    strictly before its game, but the park column only exists on schema 2
    vintages; games whose record predates it are priced with the park term at a
    flat neutral and counted here. That is a stated loss of a feature, which is
    an honest number. Silently borrowing the live index for them, which is what
    this did before, was not."""
    reset_vintage_cache()
    block = _empty_vintage_block(cov, len(games))
    resolve, rstats = _vintage_resolver()
    gradable = [g for g in games if resolve(g)]
    block["n_gradable"] = len(gradable)
    block["n_skipped_no_vintage"] = len(games) - len(gradable)
    if not gradable:
        return block
    dates = sorted({g.get("date") for g in gradable if g.get("date")})
    block["first_graded_date"] = dates[0] if dates else None
    block["last_graded_date"] = dates[-1] if dates else None
    need = VINTAGE_MIN_FIT_GAMES + VINTAGE_MIN_EVAL_GAMES
    if len(gradable) < need or len(dates) < 4:
        block["status"] = "insufficient vintage coverage"
        block["note"] = (f"{len(gradable)} games have a vintage; the honest mode needs at "
                         f"least {need} to split into a fit and an eval window, and "
                         f"{VINTAGE_MIN_GRADED_GAMES} graded before min_edge may be fitted")
        block["park_basis"] = _park_basis(rstats, gradable, [])
        return block
    cut = dates[_vintage_cut_index(gradable, dates)]
    fit_g = [g for g in gradable if (g.get("date") or "") < cut]
    ev_g = [g for g in gradable if (g.get("date") or "") >= cut]
    if len(fit_g) < VINTAGE_MIN_FIT_GAMES or len(ev_g) < VINTAGE_MIN_EVAL_GAMES:
        block["status"] = "insufficient vintage coverage"
        block["note"] = (f"vintage split at {cut} leaves {len(fit_g)} fit and {len(ev_g)} "
                         f"eval games, below the {VINTAGE_MIN_FIT_GAMES}/"
                         f"{VINTAGE_MIN_EVAL_GAMES} floors")
        block["park_basis"] = _park_basis(rstats, gradable, ev_g)
        return block
    park_basis = _park_basis(rstats, gradable, ev_g)
    # THE MODE LABEL SAYS WHAT IS ACTUALLY DATED. It used to read "features dated
    # strictly before each game; no leakage", which was false for the park index
    # in every build, and would go on being false for any game whose vintage
    # predates the park column even now.
    if park_basis["n_games_neutral_park"]:
        label = (f"vintage forward from {cut} (team, pitcher and park inputs dated "
                 f"strictly before each game, except {park_basis['n_games_neutral_park']} "
                 f"games whose vintage predates the park column and are priced on a "
                 f"NEUTRAL park)")
    else:
        label = (f"vintage forward from {cut} (team, pitcher and park inputs all dated "
                 f"strictly before each game; coefficients and both one-parameter "
                 f"corrections refit inside the window)")
    graded = grade_fn(fit_g, ev_g, label, "vintage", resolve)
    if not graded:                                               # pragma: no cover
        block["status"] = "insufficient vintage coverage"
        block["note"] = "the vintage split produced no gradable rows"
        block["park_basis"] = park_basis
        return block
    block.update(graded)
    block["status"] = "graded"
    block["split_date"] = cut
    block["n_graded"] = graded["n"]
    block["park_basis"] = park_basis
    block["note"] = (f"{graded['n']} games graded on vintage features; "
                     f"{VINTAGE_MIN_GRADED_GAMES} are needed before min_edge may be "
                     "fitted, and the paired-Brier gate must also clear")
    if park_basis["n_games_neutral_park"]:
        block["note"] += (f". {park_basis['n_eval_games_neutral_park']} of the eval "
                          f"games carry no park term at all (their vintage predates the "
                          f"park column); the park index is NOT borrowed from the live "
                          f"file, which would leak the in-progress season")
    if log_fn:
        log_fn(f"betting_model: vintage mode graded {graded['n']} games "
               f"(brier {graded['brier']} vs home base {graded['brier_home_base']}; "
               f"park basis {park_basis['source']}, "
               f"{park_basis['n_games_neutral_park']} neutral-park games)")
    if park_basis["n_games_neutral_park"]:
        log.warning("betting_model: %d of %d vintage-gradable games have no dated park "
                    "index and were priced on a NEUTRAL park (dates %s..%s). Nightly "
                    "snapshots written from leaderboard_vintages schema 2 onward carry "
                    "one; this number falls to zero on its own as the archive rolls "
                    "forward, and it is never patched with the live index.",
                    park_basis["n_games_neutral_park"], len(gradable),
                    park_basis["neutral_park_first_date"],
                    park_basis["neutral_park_last_date"])
    return block


def _park_basis(rstats: dict, gradable: list[dict], eval_games: list[dict]) -> dict:
    """Which park index priced the vintage sample, in counts.

    The resolver memoizes by DATE (a slate shares a vintage), so the per-game
    counts have to be derived here, where the fit/eval split is known. The eval
    count is the one that matters for the published claim: it is the window the
    Brier gate reads."""
    by_date = (rstats or {}).get("park_source_by_date") or {}
    neutral_dates = sorted(d for d, v in by_date.items() if v == "neutral")
    n_neutral = sum(1 for g in gradable if by_date.get(g.get("date")) == "neutral")
    n_neutral_eval = sum(1 for g in eval_games if by_date.get(g.get("date")) == "neutral")
    n_dated = len(gradable) - n_neutral
    return {
        "source": ("vintage" if not n_neutral else
                   ("neutral" if not n_dated else "mixed")),
        "n_games_vintage_park": n_dated,
        "n_games_neutral_park": n_neutral,
        "n_eval_games_neutral_park": n_neutral_eval,
        "n_dates_neutral_park": len(neutral_dates),
        "neutral_park_first_date": neutral_dates[0] if neutral_dates else None,
        "neutral_park_last_date": neutral_dates[-1] if neutral_dates else None,
        "note": ("the park index is read from each game's own vintage record; a record "
                 "written before the park column existed prices its games on a NEUTRAL "
                 "park (the park term drops out) rather than on the live index, which "
                 "is the in-progress season and would leak the eval window into its own "
                 "features"),
    }


if __name__ == "__main__":                                       # pragma: no cover
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="MLB game probability model (eephus.io).")
    ap.add_argument("--context", action="store_true", help="fit + write betting_model_context.json")
    ap.add_argument("--backtest", action="store_true", help="grade on completed games (offline)")
    ap.add_argument("--gate", action="store_true",
                    help="the min_edge gate state off the last backtest artifact")
    ap.add_argument("--game", nargs=2, metavar=("AWAY", "HOME"), help="price one matchup")
    ap.add_argument("--season", default=None)
    args = ap.parse_args()

    if args.context:
        print(json.dumps(build_context(season=args.season, log_fn=print), indent=1))
    if args.backtest:
        r = backtest(season=args.season, log_fn=print)
        for k in ("in_sample", "forward", "vintage"):
            b = r.get(k)
            if not b or b.get("n") is None:
                continue
            print(f"  [{b.get('mode')}] {b['label']}: n={b['n']} brier={b['brier']} "
                  f"(flat .500 {b['brier_flat_500']}, home-base {b['brier_home_base']}) "
                  f"acc={b['accuracy']} total MAE={b['total_mae']} "
                  f"skill t={(b.get('skill_vs_home_base') or {}).get('t')}")
        v = r.get("vintage") or {}
        print(f"  vintage coverage: {v.get('n_vintages', 0)} snapshots, "
              f"{v.get('n_graded', 0)} of {r.get('n_games', 0)} games gradable "
              f"({v.get('status')})")
        print(f"  min_edge: {r.get('min_edge')}")
        for g in (r.get("min_edge_gate") or {}).get("gates") or []:
            print(f"    gate {g['id']}: {'OPEN' if g['open'] else 'closed'} "
                  f"(have {g['have']}, need {g['need']})")
    if args.gate:
        ev = _load_json(EVAL_PATH) or {}
        print(json.dumps(min_edge_gate(ev.get("vintage")), indent=1))
    if args.game:
        away, home = _org(args.game[0]), _org(args.game[1])
        gp = game_probabilities(home, away)
        if not gp:
            print(f"no leaderboard rows for {away} / {home}")
        else:
            gp.pop("over", None)
            print(json.dumps(gp, indent=1))
