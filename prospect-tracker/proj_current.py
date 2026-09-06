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
MC_SIMS = int(os.environ.get("EEPHUS_MC_SIMS", "20000"))
"""RAISED FROM 2,000 on 2026-09-06, and the reason is a number rather than a
preference. At 2,000 the 95 percent Wilson half-width on a p = 0.5 cell is about
0.022, which is larger than most of the effects this simulator is asked to show:
a two-point difference in playoff odds between two clubs is inside the noise of
the run that produced it. At 20,000 it is about 0.007.

The cost is 2.6 seconds for a full thirty-club season with a bracket, measured,
against 0.3 at the old count. That is not a trade worth thinking about.

It does NOT make the numbers more correct, only less noisy: the talent estimate
underneath them is unchanged and carries all the uncertainty that actually
matters. `mc` publishes the sampling interval so a reader can see which of the
two they are looking at."""
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


# --------------------------------------------------------------------------
# Monte Carlo honesty: a probability without its sampling error is a claim the
# simulator cannot support.
# --------------------------------------------------------------------------

POSTSEASON_SEED_OFFSET = 1_000_003
"""The bracket draws from its OWN stream. Sharing the regular-season generator
would make every bracket result move when the schedule length changes, which
makes a bracket change and a schedule change indistinguishable in a diff."""

# Home patterns from the HIGHER seed's point of view. H = the higher seed hosts.
WC_PATTERN = "HHH"          # best-of-3, all three at the higher seed
LDS_PATTERN = "HHAAH"       # best-of-5, 2-2-1
L7_PATTERN = "HHAAAHH"      # best-of-7, 2-3-2, for the LCS and the World Series


def mc_interval(count: int, n_sims: int, z: float = 1.959964) -> dict:
    """The sampling interval on one probability cell, WILSON on the raw count.

    NOT WALD ON THE ROUNDED PROBABILITY. The Wald standard error
    sqrt(p(1-p)/n) is identically ZERO at count 0 and at count n, and those are
    exactly the cells a World Series column is full of: on the served artifact
    today, 13 of 30 clubs already sit at playoffPct 0.0 or 1.0. Publishing
    "World Series 0.0 percent, plus or minus 0.00" asserts the simulator has
    ruled a club out with no sampling noise, which is false. At 0 of 20,000
    Wilson gives an upper bound near 0.00019, which agrees with the
    rule-of-three bound 3/n.

    NO PROBABILITY MAY BE PUBLISHED WITH A STATED UNCERTAINTY OF EXACTLY ZERO.
    """
    n = int(n_sims)
    if n <= 0:
        return {"p": None, "lo95": None, "hi95": None, "method": "none",
                "waldSE": None, "n": 0}
    k = min(max(int(count), 0), n)
    p_hat = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = (p_hat + z2 / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p_hat * (1 - p_hat) / n + z2 / (4 * n * n))
    wald = math.sqrt(p_hat * (1 - p_hat) / n)
    return {
        "p": round(p_hat, 6),
        "lo95": round(max(0.0, centre - half), 6),
        "hi95": round(min(1.0, centre + half), 6),
        "method": "wilson",
        "waldSE": round(wald, 6),
        "waldIsDegenerate": bool(k == 0 or k == n),
        "n": n,
    }


def _pmf_from_counts(counts: list[int], n: int, dp: int = 5) -> list[float]:
    """Counts to probabilities at `dp` places by largest-remainder apportionment.

    The INTEGER numerators sum to 10**dp exactly. The emitted floats sum to 1.0
    only to within float epsilon, so nothing may assert equality against 1.0.

    At any n that divides 10**dp the remainders are all zero and this is a plain
    division; both 2000 and 20000 do divide it. It exists so that changing the
    simulation count to a value that does NOT divide cannot silently produce a
    distribution that fails to sum, and a test exercises it at a count that does
    not divide or the branch never runs at all.
    """
    scale = 10 ** dp
    # NORMALIZE ON THE COUNTS, NOT ON n. The two are the same for a complete
    # sample and different for any subset, and the largest-remainder step hands
    # the whole shortfall out either way: called with counts that do not sum to
    # n it silently returned a distribution summing to 0.00102 instead of 1.
    # Passing n at all is a consistency check, not the denominator.
    total = sum(counts)
    if total <= 0 or n <= 0:
        return [0.0] * len(counts)
    exact = [c * scale / total for c in counts]
    floors = [int(x) for x in exact]
    short = scale - sum(floors)
    if short > 0:
        order = sorted(range(len(counts)), key=lambda i: (-(exact[i] - floors[i]), i))
        for i in order[:short]:
            floors[i] += 1
    return [f / scale for f in floors]


def _win_total_block(samples: list[int], n_sims: int) -> dict:
    """The full win-total distribution over its own observed support.

    THE SUFFIX-SUM KEY CARRIES ITS CONDITIONING BECAUSE THE DISTRIBUTION DOES
    NOT. Every game is drawn Bernoulli at a talent point estimate that is fixed
    for the whole run: there is no parameter uncertainty on that estimate, no
    in-season talent drift, no injury and no trade process. So this is
    P(W = k | talent is exactly the blend point estimate), which is narrower
    than a real forecast, and `basis` says so in words rather than leaving a
    reader to infer it from a percentile that looks tight.

    The quantiles come from `_percentile` on the same sorted sample the six
    existing keys use, so p10 and p90 here are the SAME objects as projWinsP10
    and projWinsP90. Reading them off the CDF instead would disagree by one win
    whenever an order statistic lands on a support boundary.
    """
    if not samples:
        return {}
    s = sorted(samples)
    lo, hi = s[0], s[-1]
    counts = [0] * (hi - lo + 1)
    for w in s:
        counts[w - lo] += 1
    pmf = _pmf_from_counts(counts, n_sims)
    sf, run = [], 0.0
    for i in range(len(pmf)):
        run = sum(pmf[i + 1:])
        sf.append(round(run, 5))
    return {
        "sims": int(n_sims),
        "min": int(lo),
        "pmf": pmf,
        "sfScheduleOnly": sf,
        "mean": round(statistics.mean(s), 2),
        "sd": round(statistics.pstdev(s), 3) if len(s) > 1 else 0.0,
        "quantiles": {"p10": _percentile(s, 0.10), "p50": _percentile(s, 0.50),
                      "p90": _percentile(s, 0.90)},
        "basis": (
            "P(W = k) conditional on talent being exactly the blend point "
            "estimate. Every game is a Bernoulli draw at a win probability that "
            "is fixed for the whole run, so this distribution carries SAMPLING "
            "spread only: no uncertainty on the talent estimate itself, no "
            "in-season drift, no injury process and no trades. A real forecast "
            "interval is wider than this one and the difference is not small."),
    }


def home_odds_multiplier(home_rate: float) -> float:
    """m = h / (1 - h), the odds ratio a home team enjoys. 1.0 at h = 0.5.

    COMPUTE FROM RAW COUNTS, NEVER FROM A ROUNDED RATE: publishing a multiplier
    derived from a truncated rate gives a reader a number that does not
    reproduce from the rate printed beside it.
    """
    h = float(home_rate)
    if not (0.0 < h < 1.0):
        return 1.0
    return h / (1.0 - h)


def apply_home_edge(p_neutral: float, mult: float) -> float:
    """p -> p*m / (p*m + (1-p)).

    Algebraically sigmoid(logit(p) + ln m), computed with no log and no exp, so
    it is exact and finite at p = 0 and p = 1, keeps both as fixed points, is
    strictly monotone, needs no clamp, and gives every matchup the SAME odds
    ratio.

    THE ADDITIVE FORM IT REPLACES DOES NONE OF THAT. Adding a constant to a
    probability and clamping saturates asymmetrically: a 0.95 favourite gains
    almost nothing and a 0.05 underdog gains the full amount, so the same
    "edge" means a different thing in every matchup, and the clamp silently
    caps it at the tails where the pennant races actually live.
    """
    m = float(mult)
    p = float(p_neutral)
    num = p * m
    den = num + (1.0 - p)
    return num / den if den > 0 else p


def _series(hi: str, lo: str, best_of: int, pattern: str, ph_home: dict,
            rng: random.Random) -> str:
    """One postseason series, returning the winner.

    `pattern[i]` says who hosts game i, from the HIGHER seed's point of view.
    Best-of-seven is "HHAAAHH": the higher seed hosts games 1, 2, 6 and 7,
    which is FOUR home games and not five. A pattern that gave one club more
    than (best_of // 2) + 1 home games would be a different sport and a test
    rejects it.
    """
    need = best_of // 2 + 1
    w_hi = w_lo = 0
    for i in range(best_of):
        host_is_hi = pattern[i] == "H"
        p = ph_home[(hi, lo)] if host_is_hi else 1.0 - ph_home[(lo, hi)]
        if rng.random() < p:
            w_hi += 1
        else:
            w_lo += 1
        if w_hi == need or w_lo == need:
            break
    return hi if w_hi > w_lo else lo


def _bracket_once(seeds_by_lg: dict, wins: dict, ph_home: dict,
                  post) -> dict:
    """One postseason, from six seeds a side to a champion.

    THE CURRENT FORMAT, spelled out because it is not the old one. Seeds 1 to 3
    are the division winners by record, 4 to 6 the wild cards by record. Seeds 1
    and 2 have byes. The wild-card round is best-of-three with EVERY game at the
    higher seed: 3 hosts 6 and 4 hosts 5. There is NO RESEEDING, so 1 meets the
    4/5 winner and 2 meets the 3/6 winner whatever happens below them. The
    division series is 2-2-1, the championship series and the World Series are
    2-3-2, and World Series home field goes to the better regular-season record.

    Ties anywhere are uniform coin flips. That is a real simplification: the
    actual tiebreakers are head-to-head and then intradivision record, and this
    module carries neither. It is disclosed rather than modelled.
    """
    out = {k: set() for k in ("wc", "bye", "lds", "lcs", "pennant")}
    out["ws"] = None
    pennants = []
    for lg in sorted(seeds_by_lg):
        s1, s2, s3, s4, s5, s6 = seeds_by_lg[lg]
        out["bye"].update((s1, s2))
        out["wc"].update((s3, s4, s5, s6))
        w36 = _series(s3, s6, 3, WC_PATTERN, ph_home, post)
        w45 = _series(s4, s5, 3, WC_PATTERN, ph_home, post)
        out["lds"].update((s1, s2, w36, w45))
        d1 = _series(s1, w45, 5, LDS_PATTERN, ph_home, post)
        d2 = _series(s2, w36, 5, LDS_PATTERN, ph_home, post)
        out["lcs"].update((d1, d2))
        hi, lo = (d1, d2) if wins[d1] >= wins[d2] else (d2, d1)
        champ = _series(hi, lo, 7, L7_PATTERN, ph_home, post)
        out["pennant"].add(champ)
        pennants.append(champ)
    if len(pennants) == 2:
        a, b = pennants
        hi, lo = (a, b) if wins[a] >= wins[b] else (b, a)
        out["ws"] = _series(hi, lo, 7, L7_PATTERN, ph_home, post)
    return out


def simulate_playoffs(teams: dict[str, dict], pairs: list[tuple[str, str]], *,
                      n_sims: int | None = None, home_edge: float | None = None,
                      seed: int | None = None,
                      bracket: bool = True) -> dict[str, dict]:
    """Rest-of-season Monte Carlo -> per-team odds under the current MLB bracket
    (3 division winners + 3 wildcards per league).

    teams[org] = {'wins', 'losses', 'p' (true-talent win%), 'league', 'div'}.
    pairs      = remaining games as (home_org, away_org). Games whose teams are not
                 both in `teams` are skipped. Returns {} unless every team carries a
                 league and division (a partial/degraded standings read -> no odds).

    Returns {org: {playoffPct, divisionPct, wildcardPct, projWinsMean,
    projWinsP10, projWinsP90}} and, on a complete league, the postseason block
    {byePct, wcRoundPct, ldsPct, lcsPct, pennantPct, wsPct}, the full win-total
    distribution `winTotal`, and `mc`, the sampling interval on every published
    probability.

    THE POSTSEASON DEGRADES AND NEVER RAISES. The bracket indexes six seeds a
    side and pairs two pennant winners, so it is defined only on a complete
    thirty-club, two-league, six-division field. Callers that are not one are
    real and live in this repo's own tests: two orgs in a single division, or a
    one-league slice through the overlay. On any of those a bracket would
    IndexError, proj_export swallows the exception, and the current slate would
    blank for all thirty clubs with nobody told. So the shape is checked once,
    up front, and a field that does not qualify gets the six original keys and
    nothing else.
    """
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

    lg_sizes = {lg: sum(1 for o in orgs if league[o] == lg) for lg in leagues}
    do_bracket = bool(
        bracket and len(orgs) == 30 and len(leagues) == 2
        and all(len(divs_by_league[lg]) == 3 for lg in leagues)
        and all(n == 15 for n in lg_sizes.values()))

    playoff = {o: 0 for o in orgs}
    division = {o: 0 for o in orgs}
    wildcard = {o: 0 for o in orgs}
    win_samples: dict[str, list[int]] = {o: [] for o in orgs}
    rounds = {k: {o: 0 for o in orgs}
              for k in ("bye", "wc", "lds", "lcs", "pennant", "ws")}

    # THE BRACKET DRAWS FROM ITS OWN STREAM. Sharing the regular-season
    # generator would make every postseason number move when the schedule
    # length changes, so a bracket change and a schedule change would be
    # indistinguishable in a diff.
    post = random.Random((MC_SEED if seed is None else seed)
                         + POSTSEASON_SEED_OFFSET)
    ph_home: dict = {}
    if do_bracket:
        for a in orgs:
            for b in orgs:
                if a != b:
                    ph_home[(a, b)] = min(
                        max(log5(p[a], p[b]) + home_edge, 1e-3), 1.0 - 1e-3)

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
        seeds_by_lg: dict = {}
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
            if do_bracket:
                # `rest` is already sorted by (wins, uniform) descending, so
                # rest[:3] IS seeds 4, 5 and 6 in order at no extra draw.
                # THE SEEDING TIEBREAK DRAWS FROM `post`, NOT FROM `rng`.
                # Using the regular-season generator here consumed extra draws
                # whenever the bracket was on, which shifted every later
                # simulation: switching the bracket on moved playoffPct from
                # 0.340 to 0.417 on the same field and the same seed. A
                # postseason feature is not allowed to move a regular-season
                # number, and the test that pins byte-identity across
                # bracket=False is what caught it.
                dw = sorted(div_winners, key=lambda o: (wins[o], post.random()),
                            reverse=True)
                if len(dw) == 3 and len(rest) >= 3:
                    seeds_by_lg[lg] = tuple(dw) + tuple(rest[:3])
        if do_bracket and len(seeds_by_lg) == 2:
            res = _bracket_once(seeds_by_lg, wins, ph_home, post)
            for k in ("bye", "wc", "lds", "lcs", "pennant"):
                for o in res[k]:
                    rounds[k][o] += 1
            if res["ws"]:
                rounds["ws"][res["ws"]] += 1

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
        row = {
            "playoffPct": play_pct,
            "divisionPct": div_pct,
            "wildcardPct": round(play_pct - div_pct, 3),
            "projWinsMean": round(statistics.mean(s), 1) if s else None,
            "projWinsP10": _percentile(s, 0.10),
            "projWinsP90": _percentile(s, 0.90),
        }
        if do_bracket:
            row.update({
                "byePct": round(rounds["bye"][o] / n_sims, 3),
                "wcRoundPct": round(rounds["wc"][o] / n_sims, 3),
                "ldsPct": round(rounds["lds"][o] / n_sims, 3),
                "lcsPct": round(rounds["lcs"][o] / n_sims, 3),
                "pennantPct": round(rounds["pennant"][o] / n_sims, 3),
                "wsPct": round(rounds["ws"][o] / n_sims, 3),
            })
            row["winTotal"] = _win_total_block(s, n_sims)
            # EVERY PUBLISHED PROBABILITY CARRIES ITS SAMPLING INTERVAL. The
            # World Series column is mostly zeros and ones, and a zero with no
            # stated uncertainty asserts the simulator has ruled a club out.
            row["mc"] = {
                "sims": int(n_sims),
                "playoff": mc_interval(playoff[o], n_sims),
                "division": mc_interval(division[o], n_sims),
                "pennant": mc_interval(rounds["pennant"][o], n_sims),
                "ws": mc_interval(rounds["ws"][o], n_sims),
                "note": (
                    "Wilson intervals on the raw simulation counts. They are "
                    "MONTE CARLO error only: they say how much the number would "
                    "move if the simulation were run again, and nothing about "
                    "whether the talent estimate underneath it is right."),
            }
        out[o] = row
    return out
