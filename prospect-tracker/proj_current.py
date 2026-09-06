# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""proj_current.py — shared machinery for the Projections "Current (2026)" view.

This is the SINGLE source for three things the current-season Team Outlook build
needs, so log5 and the remaining-schedule are not defined twice across the SOS
and Monte-Carlo paths (they must agree or playoff odds and remaining-win
expectation reconcile off different game lists):

  * log5(pa, pb)               - Bill James win-probability of A over B.
  * remaining_schedule(season) - {org: [opp_org, ...]} of UNPLAYED regular-season
                                 games from StatsAPI /schedule, and the paired
                                 remaining_pairs() list[(home, away)] over the SAME
                                 fetch. Disk-cached; returns {} / [] on failure.
  * balanced_remaining(...)     - a NAMED, disclosed fallback schedule (round-robin
                                 with unbalanced intra-division weighting) used only
                                 when the live schedule is unfetchable. The caller
                                 sets mc_schedule_source='balanced_fallback' so the
                                 beta badge can say so.
  * simulate_playoffs(...)      - pure-stdlib rest-of-season Monte Carlo -> per-team
                                 playoff / division / wildcard odds + a projected-win
                                 distribution, under the current MLB bracket.

Pure stdlib (random, math, os, statistics) + feed_cache.SESSION for the one
network call, so the simulator runs locally against synthetic inputs with no
pybaseball / corpus dependency. Every entry point degrades to empty/None rather
than raising, matching the degraded-local-data rule (the current-season view is
dark-launched; when data is absent the 2027 projection view is unaffected).
"""
from __future__ import annotations

import json
import logging
import math
import os
import random
import statistics
import time
from datetime import date, timedelta
from pathlib import Path

log = logging.getLogger("proj_current")

_SCHEDULE_API = "https://statsapi.mlb.com/api/v1/schedule"
_CACHE_DIR = Path(__file__).parent / ".cache" / "proj_current"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_SCHEDULE_TTL = 12 * 3600  # 12h: a nightly build re-pulls, same-day reruns are free

# Monte-Carlo knobs (env-overridable; defaults tuned to ride inside the nightly
# export under its existing OOM/time guardrails — bump MC_SIMS post-soak).
MC_SIMS = int(os.environ.get("EEPHUS_MC_SIMS", "2000"))
MC_HOME_EDGE = float(os.environ.get("EEPHUS_MC_HOME_EDGE", "0"))
MC_SEED = int(os.environ.get("EEPHUS_MC_SEED", "12345"))

# AL/NL division membership by 3-letter org, used ONLY by the balanced-fallback
# schedule. The live path never needs this (division.id rides on standings_now).
_DIVISIONS: dict[str, list[str]] = {
    "AL_E": ["BAL", "BOS", "NYY", "TBR", "TOR"],
    "AL_C": ["CHW", "CLE", "DET", "KCR", "MIN"],
    "AL_W": ["ATH", "HOU", "LAA", "SEA", "TEX"],
    "NL_E": ["ATL", "MIA", "NYM", "PHI", "WSN"],
    "NL_C": ["CHC", "CIN", "MIL", "PIT", "STL"],
    "NL_W": ["ARI", "COL", "LAD", "SDP", "SFG"],
}


# --------------------------------------------------------------------------- #
# win probability
# --------------------------------------------------------------------------- #
def log5(p_a: float, p_b: float) -> float:
    """P(A beats B) from two true-talent win rates (Bill James log5). Clamps the
    inputs off the 0/1 rails; a degenerate denominator falls back to a coin flip."""
    pa = min(max(p_a, 1e-6), 1.0 - 1e-6)
    pb = min(max(p_b, 1e-6), 1.0 - 1e-6)
    denom = pa + pb - 2.0 * pa * pb
    if denom <= 0:
        return 0.5
    return (pa - pa * pb) / denom


# --------------------------------------------------------------------------- #
# remaining schedule
# --------------------------------------------------------------------------- #
def _fetch_schedule_raw(start_date: str, end_date: str) -> dict:
    """Raw regular-season /schedule JSON for the window, disk-cached by span.
    Reuses feed_cache.SESSION (429-retrying); best-effort ({} on any failure)."""
    path = _CACHE_DIR / f"sched_{start_date}_{end_date}.json"
    if path.exists() and time.time() - path.stat().st_mtime <= _SCHEDULE_TTL:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    try:
        import feed_cache
        time.sleep(0.04)
        resp = feed_cache.SESSION.get(
            _SCHEDULE_API,
            params={"sportId": 1, "startDate": start_date,
                    "endDate": end_date, "gameType": "R"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(path)
        return data
    except Exception:                                          # noqa: BLE001
        log.warning("proj_current: /schedule fetch failed %s..%s", start_date, end_date)
        return {}


# statuses that mean the game has NOT been played yet
_UNPLAYED = {"Preview", "Pre-Game", "Scheduled", "Warmup", "Delayed Start"}


SCHEDULED_GAMES = 162
"""Games in a full modern regular season. Used only by `season_shortfall`, which
CHECKS against it rather than asserting from it: a shortened or expanded season
should show up as a shortfall on every club at once, which reads as a schedule
problem rather than as a club problem."""


def remaining_pairs(season: int, *, today: date | None = None) -> list[tuple[str, str]]:
    """[(home_org, away_org), ...] for every game not yet FINAL, from `today`
    through season end. [] on fetch failure.

    A GAME IN PROGRESS IS NOT A GAME PLAYED. This used to skip anything whose
    abstract state was "Live", on the reasoning that an in-progress game counts
    as roughly played. It does not: the standings read that supplies base_wins
    has not booked it either, so the game counted as NEITHER played nor
    remaining and simply vanished from the season. Every club with a game in
    progress at build time was projected over a schedule one game short, and
    since builds run in the evening that is most of the league most nights.

    A live game is now included and simulated from its pre-game state, which is
    the only state the simulator has. That slightly understates certainty for a
    game already half-decided, and understating certainty is the safe direction:
    the alternative silently deletes the game.

    CLUBS RESOLVE BY ID, NOT BY NAME. The name path works on this endpoint
    today, because /schedule returns "Arizona Diamondbacks" rather than the
    "D-backs" that /standings returns and that the length guard below would
    drop. That is luck, not design, and it is the same guard that did drop
    Arizona out of the standings reader until 2026-09-06. Ids do not change and
    names do."""
    start = (today or date.today())
    # season end guard: MLB regular season wraps by early October; pad to Nov.
    end = date(season, 11, 5)
    if start > end:
        return []
    data = _fetch_schedule_raw(start.isoformat(), end.isoformat())
    if not data:
        return []
    from trades import canonical_org_from_id
    out: list[tuple[str, str]] = []
    for d in data.get("dates", []):
        for g in d.get("games", []):
            status = ((g.get("status") or {}).get("abstractGameState")) or ""
            detailed = ((g.get("status") or {}).get("detailedState")) or ""
            if status == "Final" or detailed in {"Final", "Game Over", "Completed Early"}:
                continue
            teams = g.get("teams") or {}
            ht = (teams.get("home") or {}).get("team") or {}
            at = (teams.get("away") or {}).get("team") or {}
            ho = canonical_org_from_id(ht.get("id"), ht.get("name") or "")
            ao = canonical_org_from_id(at.get("id"), at.get("name") or "")
            if ho and ao and len(ho) <= 3 and len(ao) <= 3:
                out.append((ho, ao))
    return out


def season_shortfall(teams: dict, pairs: list, scheduled: int = SCHEDULED_GAMES) -> dict:
    """{org: games unaccounted for}, zero when a club's season adds up.

    WHY THIS EXISTS RATHER THAN A COMMENT. The live-game defect above was
    invisible for exactly one reason: nothing ever checked that wins + losses +
    remaining equalled a season. A club projected over 161 games looks entirely
    normal in every output, and the only symptom is playoff odds that are
    slightly too confident for the clubs that happened to be playing when the
    build ran.

    A non-zero shortfall is a build problem, not a display one, so it is emitted
    and a club that carries one gets no win-total interval: a band around a
    distribution that is missing games is false precision on a biased estimate.
    """
    played = {o: int(t.get("wins") or 0) + int(t.get("losses") or 0)
              for o, t in teams.items()}
    rem = {o: 0 for o in teams}
    for home, away in pairs:
        if home in rem:
            rem[home] += 1
        if away in rem:
            rem[away] += 1
    return {o: int(scheduled - played[o] - rem[o]) for o in teams}


def remaining_schedule(season: int, *, today: date | None = None) -> dict[str, list[str]]:
    """{org: [opponent_org, ...]} of unplayed regular-season games (both home and
    away), derived from remaining_pairs(). {} on fetch failure -> caller falls
    back to balanced_remaining()."""
    pairs = remaining_pairs(season, today=today)
    if not pairs:
        return {}
    sched: dict[str, list[str]] = {}
    for home, away in pairs:
        sched.setdefault(home, []).append(away)
        sched.setdefault(away, []).append(home)
    return sched


def _div_of(org: str) -> str | None:
    for dv, members in _DIVISIONS.items():
        if org in members:
            return dv
    return None


def balanced_remaining(teams: list[str], games_remaining: dict[str, int] | None = None,
                       *, intra_div_weight: float = 0.76,
                       default_games: int = 60) -> dict[str, list[str]]:
    """DISCLOSED FALLBACK: synthesize a plausible remaining schedule when the live
    one is unfetchable. Each team's opponents are drawn deterministically, weighted
    ~0.76 intra-division vs rest-of-league to mimic MLB's unbalanced format. This
    understates the true SOS spread — the caller MUST flag mc_schedule_source=
    'balanced_fallback' so the UI discloses it."""
    rng = random.Random(MC_SEED)
    sched: dict[str, list[str]] = {t: [] for t in teams}
    for t in teams:
        n = (games_remaining or {}).get(t, default_games)
        div = _div_of(t)
        div_opps = [o for o in teams if o != t and _div_of(o) == div]
        other = [o for o in teams if o != t and _div_of(o) != div]
        for _ in range(max(0, n)):
            pool = div_opps if (div_opps and rng.random() < intra_div_weight) else (other or div_opps)
            if not pool:
                continue
            sched[t].append(pool[rng.randrange(len(pool))])
    return sched


# --------------------------------------------------------------------------- #
# Monte-Carlo playoff odds
# --------------------------------------------------------------------------- #
def _percentile(sorted_vals: list[int], q: float) -> int:
    """Nearest-rank percentile of an ascending int list."""
    if not sorted_vals:
        return 0
    idx = min(len(sorted_vals) - 1, max(0, int(round(q * (len(sorted_vals) - 1)))))
    return sorted_vals[idx]


def simulate_playoffs(teams: dict[str, dict], pairs: list[tuple[str, str]], *,
                      n_sims: int | None = None, home_edge: float | None = None,
                      seed: int | None = None) -> dict[str, dict]:
    """Rest-of-season Monte Carlo -> per-team odds under the current MLB bracket
    (3 division winners + 3 wildcards per league).

    teams[org] = {'wins', 'losses', 'p' (true-talent win%), 'league', 'div'}.
    pairs      = remaining games as (home_org, away_org). Games whose teams are not
                 both in `teams` are skipped. Returns {} unless every team carries a
                 league and division (a partial/degraded standings read -> no odds).

    Returns {org: {playoffPct, divisionPct, wildcardPct, projWinsMean,
    projWinsP10, projWinsP90}}."""
    if not teams:
        return {}
    if any(t.get("league") is None or t.get("div") is None for t in teams.values()):
        return {}
    n_sims = n_sims or MC_SIMS
    home_edge = MC_HOME_EDGE if home_edge is None else home_edge
    rng = random.Random(MC_SEED if seed is None else seed)

    orgs = list(teams.keys())
    base_wins = {o: int(teams[o].get("wins") or 0) for o in orgs}
    p = {o: float(teams[o].get("p") or 0.5) for o in orgs}
    league = {o: teams[o]["league"] for o in orgs}
    div = {o: teams[o]["div"] for o in orgs}
    leagues = sorted({league[o] for o in orgs})
    divs_by_league: dict[int, set] = {}
    for o in orgs:
        divs_by_league.setdefault(league[o], set()).add(div[o])
    # only simulate games where both teams are known
    sim_pairs = [(h, a) for h, a in pairs if h in p and a in p]

    playoff = {o: 0 for o in orgs}
    division = {o: 0 for o in orgs}
    wildcard = {o: 0 for o in orgs}
    win_samples: dict[str, list[int]] = {o: [] for o in orgs}

    for _ in range(n_sims):
        wins = dict(base_wins)
        for home, away in sim_pairs:
            ph = min(max(log5(p[home], p[away]) + home_edge, 1e-3), 1.0 - 1e-3)
            if rng.random() < ph:
                wins[home] += 1
            else:
                wins[away] += 1
        for o in orgs:
            win_samples[o].append(wins[o])
        # bracket per league, independently
        for lg in leagues:
            lg_orgs = [o for o in orgs if league[o] == lg]
            div_winners: set = set()
            for dv in divs_by_league[lg]:
                members = [o for o in lg_orgs if div[o] == dv]
                if not members:
                    continue
                best = max(m for m in (wins[o] for o in members))
                tied = [o for o in members if wins[o] == best]
                w = tied[rng.randrange(len(tied))]
                div_winners.add(w)
                division[w] += 1
            # wildcards: top-3 by wins among non-division-winners in the league
            rest = [o for o in lg_orgs if o not in div_winners]
            rest.sort(key=lambda o: (wins[o], rng.random()), reverse=True)
            wc = set(rest[:3])
            for o in wc:
                wildcard[o] += 1
            for o in div_winners | wc:
                playoff[o] += 1

    out: dict[str, dict] = {}
    for o in orgs:
        s = sorted(win_samples[o])
        # DERIVE THE PART FROM THE WHOLE, NEVER THE WHOLE FROM TWO PARTS.
        #
        # Division and wildcard are disjoint, so the counts satisfy
        # playoff == division + wildcard exactly. The previous version rounded
        # each part to three places and ADDED them, which is unbounded above:
        # two independent roundings can each add half a thousandth, so the sum
        # can exceed 1. It did. Milwaukee served playoffPct 1.001 on
        # 2026-09-06, from 0.997 + 0.004, and a probability above one on a
        # public page is the kind of error a reader cannot un-see.
        #
        # Rounding the WHOLE and subtracting gives both bounds for free:
        # playoff_count <= n_sims so playoffPct <= 1.0, and
        # playoff_count >= division_count so wildcardPct >= 0. The identity the
        # UI stacks on holds by construction because the third number is
        # defined as the difference of the first two.
        #
        # `playoff` was already being counted here and never read.
        div_pct = round(division[o] / n_sims, 3)
        play_pct = round(playoff[o] / n_sims, 3)
        out[o] = {
            "playoffPct": play_pct,
            "divisionPct": div_pct,
            "wildcardPct": round(play_pct - div_pct, 3),
            "projWinsMean": round(statistics.mean(s), 1) if s else None,
            "projWinsP10": _percentile(s, 0.10),
            "projWinsP90": _percentile(s, 0.90),
        }
    return out
