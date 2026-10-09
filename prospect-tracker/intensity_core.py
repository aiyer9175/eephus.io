# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""intensity_core.py - the construction core of the game-intensity index (`ix_v1`).

REGISTERED BEFORE THIS CODE. docs/diamond-betting.md, the section "Game intensity:
stakes, matchup quality and the postseason" (owner ask 8 of 2026-09-30; plan Part 8,
P8.9, item IX-H1), froze the construction this module builds. Section references
below name that section by its title, never by its letter.

WHAT THIS MODULE IS. Pure functions, nothing else: no file is read, nothing is
fetched, nothing is written, and no served module is imported. It holds

1. the frozen literals of the section (copied here, never imported; plan stop X4),
2. the literature Elo walk (constants copied from tools/betting_elo.py, the
   `LITERATURE_K` block: base 1500, K 4, 24 points of home field, flat start every
   season),
3. the regular-season conditioning simulator, built on proj_current's rest-of-season
   loop and bracket (`simulate_playoffs()` and `_bracket_once()`), run twice with one
   game's result forced each way under common random numbers,
4. the exact series recursion and the exact bracket probability of advancing, for
   postseason games,
5. both postseason formats through one `fmt` parameter: "five" (five clubs a league:
   2018, 2019 and 2021) and "six" (six clubs a league, 2022 on),
6. the percentile ranks behind Q and A, the stakes score S, the index and its bands,
7. a Monte Carlo standard-error helper per game.

WHAT IT NEVER DOES. It computes nothing for a real game by itself. Every caller in
this commit is a test on fixtures and synthetic leagues. The section's disqualification
paragraph binds every later caller: any number relating the index, a component of it
or a close variant to a game outcome or a price before that stage's look disqualifies
the stage. Only the registered stage-1 lab (tools/intensity_lab.py, at its look) and
the dark builder (after its builder amendment) may call this on real games.

COMMON RANDOM NUMBERS, AND THE ONE PLACE THIS DEPARTS FROM proj_current. In
proj_current the division tie draws, the wild-card tie draws and the seeding order
draw from the same generators as the games and the bracket, and how many draws a
tie consumes depends on the standings. Forcing one game can create or remove a tie,
which would shift every later simulation's game draws, and from then on the two
forced runs would be independent rather than paired. So here the games draw from one
generator at `seed` (exactly one uniform per remaining game per simulation, in
schedule order, the forced game's uniform consumed and then overridden), and each
simulation's ties, seeding order and bracket draw from their own generator, seeded
from (`seed`, the simulation's index) and identical in the two forced runs. Every
other draw lines up, and only paths that the forced result changes differ. Ties stay
coin flips, as in proj_current at the lane's base commit (its later `tiebreak`
argument applies only after the regular season and is not part of `ix_v1`).
"""
from __future__ import annotations

import math
import random

# ---------------------------------------------------------------------------
# The frozen literals of `ix_v1`. Pinned to the section's text by
# test_intensity_core.py; a change here is a change to the construction and is
# recorded in the section the same day (X9).
# ---------------------------------------------------------------------------
CONSTRUCTION = "ix_v1"

#: G_REF, the mean G of an Opening Day game between average clubs. The registered
#: synthetic league: 30 equal clubs at 0-0 on a 162-game schedule of 52 division,
#: 64 league and 46 interleague games, 300,000 simulations at seed 20260930, no data.
#: The gate tool's own commit (Q10_07) recomputed it once from that league
#: (tools/intensity_lab.py --g-ref, 2026-10-09: 0.011575302, rounded to five
#: decimals) and recorded the frozen literal in the section by the dated amendment
#: "G_REF recorded"; it is never computed at a look.
G_REF_DRAFT = 0.01145
G_REF: float | None = 0.01158
G_REF_SEED = 20260930
G_REF_SIMS = 300_000
G_REF_CLUBS = 30
G_REF_SCHEDULE = {"division": 52, "league": 64, "interleague": 46}

#: The index weights and bands. Policy, fixed before any outcome is read, never fitted.
W_STAKES = 0.60
W_QUALITY = 0.15
W_STARTERS = 0.15
W_DIVISION = 0.10
W_RIVALRY = 0.0          # INT-A4, answered 2026-10-01: a label only, no weight
BANDS = (30, 50, 70)
BAND_NAMES = ("routine", "raised", "high", "peak")

#: The literature Elo, copied (never imported) from tools/betting_elo.py.
ELO_BASE = 1500.0
ELO_K = 4.0
ELO_HOME_POINTS = 24.0

#: 24 Elo points at a coin flip, as a win-probability edge (arithmetic):
#: 1 / (1 + 10 ** (-24 / 400)) - 0.5 = 0.03448.
HOME_EDGE = 0.0345

#: The conditioning simulator.
SIMS = 20_000
SEED = 12345

#: The IX-A focus set: graded games with |ds| >= 0.05, defined on features only.
FOCUS_THRESHOLD = 0.05

# Copied from proj_current (the lane's base commit 64bf1bb3), never imported.
POSTSEASON_SEED_OFFSET = 1_000_003
WC_PATTERN = "HHH"           # best-of-three, every game at the higher seed
WC_GAME_PATTERN = "H"        # the five-club format's one-game wild card
LDS_PATTERN = "HHAAH"        # best-of-five, 2-2-1
L7_PATTERN = "HHAAAHH"       # best-of-seven, 2-3-2
PROB_FLOOR = 1e-3

FORMATS = ("five", "six")
#: Seasons each format covers in the registered frames. 2020 is excluded
#: throughout (no corpus season); seasons before 2018 carry no stakes value.
FIVE_CLUB_SEASONS = (2018, 2019, 2021)
SIX_CLUB_FIRST_SEASON = 2022


def format_for_season(season: int) -> str:
    """The postseason format of a season the registered frames read."""
    s = int(season)
    if s in FIVE_CLUB_SEASONS:
        return "five"
    if s >= SIX_CLUB_FIRST_SEASON:
        return "six"
    raise ValueError(f"no registered postseason format for {s}")


def _check_fmt(fmt: str) -> int:
    if fmt not in FORMATS:
        raise ValueError(f"unknown postseason format {fmt!r}")
    return 5 if fmt == "five" else 6


# ---------------------------------------------------------------------------
# Elo: the literature walk, flat start every season, strictly before the date.
# ---------------------------------------------------------------------------
def elo_win_prob(r_home: float, r_away: float, home_points: float = ELO_HOME_POINTS) -> float:
    """P(home win) from two ratings, the logistic-in-base-10 form."""
    return 1.0 / (1.0 + 10.0 ** (-((r_home - r_away + home_points) / 400.0)))


def _season_of(row: dict) -> str:
    return str(row.get("date") or "")[:4]


def _usable(row: dict) -> bool:
    return bool(row.get("home_org") and row.get("away_org")
                and row.get("home_runs") is not None and row.get("away_runs") is not None
                and row.get("date"))


def elo_walk(games: list[dict], *, k: float = ELO_K, home_points: float = ELO_HOME_POINTS,
             base: float = ELO_BASE) -> list[dict]:
    """The chronological walk over completed games, one entry per usable game.

    Each entry carries the two ratings and the home probability AS THEY STOOD before
    the game, then the game updates them (r_home += K (y - p), r_away -= K (y - p)).
    Ratings reset to `base` whenever the season (the date's year) changes. Rows are the
    betting_model compact rows (game_pk, date, home_org, away_org, home_runs,
    away_runs); a row missing a side, a score or a date is neither predicted nor
    learned from."""
    ratings: dict[str, float] = {}
    season = None
    out = []
    for g in sorted((r for r in (games or []) if _usable(r)),
                    key=lambda r: (str(r.get("date")), r.get("game_pk") or 0)):
        if _season_of(g) != season:
            season = _season_of(g)
            ratings = {}
        h, a = g["home_org"], g["away_org"]
        r_h, r_a = ratings.get(h, base), ratings.get(a, base)
        p = elo_win_prob(r_h, r_a, home_points)
        out.append({"game_pk": g.get("game_pk"), "date": g["date"], "home_org": h,
                    "away_org": a, "r_home": r_h, "r_away": r_a, "p_home": p})
        y = 1.0 if int(g["home_runs"]) > int(g["away_runs"]) else 0.0
        delta = k * (y - p)
        ratings[h] = r_h + delta
        ratings[a] = r_a - delta
    return out


def elo_ratings_before(games: list[dict], date: str, *, k: float = ELO_K,
                       home_points: float = ELO_HOME_POINTS,
                       base: float = ELO_BASE) -> dict[str, float]:
    """{org: rating} after every final dated strictly before `date` in `date`'s season.

    A game ON `date` never enters, whatever its start time: the build reads standings
    through D-1. Clubs with no final yet are absent (their rating is `base`)."""
    season = str(date)[:4]
    rows = [r for r in (games or []) if _usable(r)
            and _season_of(r) == season and str(r["date"]) < str(date)]
    ratings: dict[str, float] = {}
    for g in sorted(rows, key=lambda r: (str(r.get("date")), r.get("game_pk") or 0)):
        h, a = g["home_org"], g["away_org"]
        r_h, r_a = ratings.get(h, base), ratings.get(a, base)
        p = elo_win_prob(r_h, r_a, home_points)
        y = 1.0 if int(g["home_runs"]) > int(g["away_runs"]) else 0.0
        delta = k * (y - p)
        ratings[h] = r_h + delta
        ratings[a] = r_a - delta
    return ratings


def elo_talent(rating: float, base: float = ELO_BASE) -> float:
    """A rating as a win rate against an average club: 1 / (1 + 10^(-(r - base) / 400))."""
    return 1.0 / (1.0 + 10.0 ** (-(float(rating) - base) / 400.0))


def talent_from_ratings(ratings: dict[str, float], orgs) -> dict[str, float]:
    """{org: win rate against an average club}; a club with no rating is average."""
    return {o: elo_talent(ratings.get(o, ELO_BASE)) for o in orgs}


# ---------------------------------------------------------------------------
# Per-game probability: proj_current's log5 with an additive home edge, clamped.
# ---------------------------------------------------------------------------
def log5(p_a: float, p_b: float) -> float:
    """P(A beats B) from two win rates (Bill James log5), copied from proj_current."""
    pa = min(max(p_a, 1e-6), 1.0 - 1e-6)
    pb = min(max(p_b, 1e-6), 1.0 - 1e-6)
    denom = pa + pb - 2.0 * pa * pb
    if denom <= 0:
        return 0.5
    return (pa - pa * pb) / denom


def p_home_game(p_home_talent: float, p_away_talent: float,
                home_edge: float = HOME_EDGE) -> float:
    """P(home win): log5 plus the additive home edge, clamped as proj_current clamps."""
    return min(max(log5(p_home_talent, p_away_talent) + home_edge, PROB_FLOOR),
               1.0 - PROB_FLOOR)


def _ph_table(orgs, talent: dict[str, float], home_edge: float) -> dict:
    return {(a, b): p_home_game(talent[a], talent[b], home_edge)
            for a in orgs for b in orgs if a != b}


# ---------------------------------------------------------------------------
# The sampled bracket (proj_current's `_bracket_once`, with a format parameter).
# ---------------------------------------------------------------------------
def _series(hi: str, lo: str, best_of: int, pattern: str, ph_home: dict,
            rng: random.Random) -> str:
    """One sampled series; `pattern[i]` says who hosts game i from the higher seed's
    side. Copied from proj_current."""
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


def bracket_once(seeds_by_lg: dict, wins: dict, ph_home: dict, post: random.Random,
                 fmt: str = "six") -> dict:
    """One sampled postseason from the seeds to a champion.

    "six" is proj_current's `_bracket_once` line for line: seeds 1 to 3 are the
    division winners, 4 to 6 the wild cards; 1 and 2 have byes; 3 hosts 6 and 4 hosts
    5 in a best-of-three with every game at the higher seed; no reseeding (1 meets the
    4/5 winner, 2 the 3/6 winner); division series 2-2-1; the championship series and
    the World Series 2-3-2 with home field to the better record, the first-listed club
    on a tie.

    "five" is the 2018, 2019 and 2021 format in the same idiom: seeds 1 to 3 the
    division winners, 4 and 5 the wild cards; one wild-card game at seed 4; seed 1
    meets the wild-card winner and 2 meets 3 in the division series; the later rounds
    as in "six"."""
    n = _check_fmt(fmt)
    out = {k: set() for k in ("wc", "bye", "lds", "lcs", "pennant")}
    out["ws"] = None
    pennants = []
    for lg in sorted(seeds_by_lg):
        seeds = seeds_by_lg[lg]
        if len(seeds) != n:
            raise ValueError(f"{fmt} format needs {n} seeds a league, got {len(seeds)}")
        if fmt == "six":
            s1, s2, s3, s4, s5, s6 = seeds
            out["bye"].update((s1, s2))
            out["wc"].update((s3, s4, s5, s6))
            w36 = _series(s3, s6, 3, WC_PATTERN, ph_home, post)
            w45 = _series(s4, s5, 3, WC_PATTERN, ph_home, post)
            out["lds"].update((s1, s2, w36, w45))
            d1 = _series(s1, w45, 5, LDS_PATTERN, ph_home, post)
            d2 = _series(s2, w36, 5, LDS_PATTERN, ph_home, post)
        else:
            s1, s2, s3, s4, s5 = seeds
            out["bye"].update((s1, s2, s3))
            out["wc"].update((s4, s5))
            w45 = _series(s4, s5, 1, WC_GAME_PATTERN, ph_home, post)
            out["lds"].update((s1, s2, s3, w45))
            d1 = _series(s1, w45, 5, LDS_PATTERN, ph_home, post)
            d2 = _series(s2, s3, 5, LDS_PATTERN, ph_home, post)
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


# ---------------------------------------------------------------------------
# The regular-season conditioning simulator.
# ---------------------------------------------------------------------------
class _Field:
    """The validated thirty-club field: leagues, divisions, base wins, talents."""

    def __init__(self, teams: dict[str, dict], fmt: str):
        self.n_seeds = _check_fmt(fmt)
        self.fmt = fmt
        if not teams:
            raise ValueError("an empty field has no stakes")
        if any(t.get("league") is None or t.get("div") is None for t in teams.values()):
            raise ValueError("every club needs a league and a division")
        self.orgs = sorted(teams)
        self.base_wins = {o: int(teams[o].get("wins") or 0) for o in self.orgs}
        self.talent = {o: float(teams[o].get("p") if teams[o].get("p") is not None else 0.5)
                       for o in self.orgs}
        league = {o: teams[o]["league"] for o in self.orgs}
        div = {o: teams[o]["div"] for o in self.orgs}
        self.leagues = sorted({league[o] for o in self.orgs})
        self.lg_orgs = {lg: [o for o in self.orgs if league[o] == lg] for lg in self.leagues}
        self.divs = {lg: {dv: [o for o in self.lg_orgs[lg] if div[o] == dv]
                          for dv in sorted({div[o] for o in self.lg_orgs[lg]})}
                     for lg in self.leagues}
        if not (len(self.orgs) == 30 and len(self.leagues) == 2
                and all(len(self.divs[lg]) == 3 for lg in self.leagues)
                and all(len(self.lg_orgs[lg]) == 15 for lg in self.leagues)):
            raise ValueError("stakes need the full thirty-club, two-league, "
                             "six-division field")
        self.league = league
        self.div = div


def _sim_stream_seed(seed: int, i: int) -> int:
    """The per-simulation stream for ties, seeding order and the bracket: the same
    integer in both forced runs of simulation i."""
    return (int(seed) + POSTSEASON_SEED_OFFSET) * 4_294_967_296 + int(i)


def _season_outcome(field: _Field, wins: dict, ph_home: dict, stream: random.Random):
    """Seed the field from final wins and play the bracket, all on `stream`.

    Division winners: most wins, a tie a uniform draw. Wild cards: the best records
    among the rest, ties by a uniform key. Seeds 1 to 3: the division winners by wins,
    ties by a uniform key. Returns (the set of postseason clubs, the champion)."""
    made: set = set()
    seeds_by_lg: dict = {}
    n_wc = field.n_seeds - 3
    for lg in field.leagues:
        div_winners = []
        for dv, members in field.divs[lg].items():
            best = max(wins[o] for o in members)
            tied = [o for o in members if wins[o] == best]
            div_winners.append(tied[stream.randrange(len(tied))])
        rest = [o for o in field.lg_orgs[lg] if o not in div_winners]
        rest.sort(key=lambda o: (wins[o], stream.random()), reverse=True)
        wc = rest[:n_wc]
        dw = sorted(div_winners, key=lambda o: (wins[o], stream.random()), reverse=True)
        made.update(dw)
        made.update(wc)
        seeds_by_lg[lg] = tuple(dw) + tuple(wc)
    res = bracket_once(seeds_by_lg, wins, ph_home, stream, field.fmt)
    return made, res["ws"]


def _setup(teams, pairs, fmt, home_edge):
    field = _Field(teams, fmt)
    known = set(field.orgs)
    sim_pairs = [(h, a) for h, a in pairs if h in known and a in known]
    if len(sim_pairs) != len(pairs):
        raise ValueError("every remaining game must be between two clubs of the field")
    ph_home = _ph_table(field.orgs, field.talent, home_edge)
    ph = [ph_home[(h, a)] for h, a in sim_pairs]
    return field, sim_pairs, ph_home, ph


def simulate_forced(teams: dict[str, dict], pairs: list[tuple[str, str]], *,
                    forced: tuple[int, str] | None = None, fmt: str = "six",
                    n_sims: int = SIMS, seed: int = SEED, home_edge: float = HOME_EDGE,
                    trace: bool = False) -> dict:
    """ONE run of the rest-of-season and bracket simulation, one game's result forced.

    teams[org] = {'wins', 'p' (win rate against an average club), 'league', 'div'}.
    pairs = the remaining regular-season games in schedule order, (home, away),
    including the game being forced. forced = (index into pairs, 'home' or 'away'), or
    None for the unforced run. The forced game's uniform is drawn and then overridden,
    so every other game's draw is the same in every run at the same seed.

    Returns counts over the simulations: playoff and World Series counts per club,
    the summed final wins per club, and with trace=True the per-simulation game
    outcomes (1 = home won) as bytes."""
    field, sim_pairs, ph_home, ph = _setup(teams, pairs, fmt, home_edge)
    if forced is not None:
        k_forced, side = int(forced[0]), forced[1]
        if not 0 <= k_forced < len(sim_pairs) or side not in ("home", "away"):
            raise ValueError(f"bad forced game {forced!r}")
        forced_bit = 1 if side == "home" else 0
    else:
        k_forced, forced_bit = -1, 0
    rng = random.Random(int(seed))
    po = {o: 0 for o in field.orgs}
    ws = {o: 0 for o in field.orgs}
    win_sum = {o: 0 for o in field.orgs}
    traces = [] if trace else None
    for i in range(int(n_sims)):
        wins = dict(field.base_wins)
        outs = bytearray(len(sim_pairs))
        for k, (h, a) in enumerate(sim_pairs):
            bit = 1 if rng.random() < ph[k] else 0
            if k == k_forced:
                bit = forced_bit
            outs[k] = bit
            wins[h if bit else a] += 1
        made, champ = _season_outcome(field, wins, ph_home,
                                      random.Random(_sim_stream_seed(seed, i)))
        for o in made:
            po[o] += 1
        if champ is not None:
            ws[champ] += 1
        for o in field.orgs:
            win_sum[o] += wins[o]
        if trace:
            traces.append(bytes(outs))
    out = {"n_sims": int(n_sims), "seed": int(seed), "fmt": fmt, "forced": forced,
           "playoff": po, "ws": ws, "win_sum": win_sum}
    if trace:
        out["trace"] = traces
    return out


def paired_standard_error(sum_d: float, sum_d2: float, n: int) -> float | None:
    """The Monte Carlo standard error of a mean of paired per-simulation differences.

    Under common random numbers each simulation yields one difference d_i (for G, the
    home club's World Series indicator forced-win minus forced-loss plus the same for
    the away club, in -2..2); the estimate is mean(d) and its standard error
    sd(d) / sqrt(n), with the n - 1 variance. None below two simulations."""
    n = int(n)
    if n < 2:
        return None
    var = (float(sum_d2) - float(sum_d) ** 2 / n) / (n - 1)
    return math.sqrt(max(var, 0.0) / n)


def regular_season_stakes(teams: dict[str, dict], pairs: list[tuple[str, str]],
                          game_indices: list[int], *, fmt: str = "six",
                          n_sims: int = SIMS, seed: int = SEED,
                          home_edge: float = HOME_EDGE) -> dict:
    """dWS and dPO for each listed game, by forcing it each way under common random
    numbers, in one pass.

    Equivalent, count for count, to calling `simulate_forced` twice per game (forced
    'home', forced 'away') at the same seed: each simulation draws every game once,
    plays the natural season on its own stream, and for each listed game replays the
    season with that game's result flipped on an identically seeded stream; the
    natural season is one of the two forced runs. A test pins the equivalence.

    Returns {'games': [one dict per listed game], 'proj_wins': {org: mean final wins
    in the unforced run}, 'n_sims', 'seed', 'fmt'}. Per game: home, away, dpo_h,
    dpo_a, dws_h, dws_a, G and the paired standard errors of G and of the two dPO."""
    field, sim_pairs, ph_home, ph = _setup(teams, pairs, fmt, home_edge)
    idx = [int(k) for k in game_indices]
    if any(not 0 <= k < len(sim_pairs) for k in idx):
        raise ValueError("a listed game is not in the remaining schedule")
    rng = random.Random(int(seed))
    n = int(n_sims)
    # per listed game: counts[(team, variant)] for variant 'H' (home forced to win)
    # and 'A' (away forced to win), and the paired sums
    acc = []
    for k in idx:
        h, a = sim_pairs[k]
        acc.append({"ws": {"hH": 0, "hA": 0, "aH": 0, "aA": 0},
                    "po": {"hH": 0, "hA": 0, "aH": 0, "aA": 0},
                    "g": [0.0, 0.0], "ph": [0.0, 0.0], "pa": [0.0, 0.0]})
    win_sum = {o: 0 for o in field.orgs}
    for i in range(n):
        wins = dict(field.base_wins)
        outs = bytearray(len(sim_pairs))
        for k, (h, a) in enumerate(sim_pairs):
            bit = 1 if rng.random() < ph[k] else 0
            outs[k] = bit
            wins[h if bit else a] += 1
        for o in field.orgs:
            win_sum[o] += wins[o]
        stream_seed = _sim_stream_seed(seed, i)
        natural = _season_outcome(field, wins, ph_home, random.Random(stream_seed))
        for j, k in enumerate(idx):
            h, a = sim_pairs[k]
            flipped_wins = dict(wins)
            if outs[k]:
                flipped_wins[h] -= 1
                flipped_wins[a] += 1
            else:
                flipped_wins[a] -= 1
                flipped_wins[h] += 1
            flipped = _season_outcome(field, flipped_wins, ph_home,
                                      random.Random(stream_seed))
            res_h, res_a = (natural, flipped) if outs[k] else (flipped, natural)
            c = acc[j]
            hH, hA = int(res_h[1] == h), int(res_a[1] == h)
            aH, aA = int(res_h[1] == a), int(res_a[1] == a)
            ph_H, ph_A = int(h in res_h[0]), int(h in res_a[0])
            pa_H, pa_A = int(a in res_h[0]), int(a in res_a[0])
            c["ws"]["hH"] += hH
            c["ws"]["hA"] += hA
            c["ws"]["aH"] += aH
            c["ws"]["aA"] += aA
            c["po"]["hH"] += ph_H
            c["po"]["hA"] += ph_A
            c["po"]["aH"] += pa_H
            c["po"]["aA"] += pa_A
            d = (hH - hA) + (aA - aH)
            c["g"][0] += d
            c["g"][1] += d * d
            dh, da = ph_H - ph_A, pa_A - pa_H
            c["ph"][0] += dh
            c["ph"][1] += dh * dh
            c["pa"][0] += da
            c["pa"][1] += da * da
    games = []
    for j, k in enumerate(idx):
        h, a = sim_pairs[k]
        c = acc[j]
        dws_h = (c["ws"]["hH"] - c["ws"]["hA"]) / n
        dws_a = (c["ws"]["aA"] - c["ws"]["aH"]) / n
        games.append({
            "index": k, "home": h, "away": a, "game_type": "R",
            "dpo_h": (c["po"]["hH"] - c["po"]["hA"]) / n,
            "dpo_a": (c["po"]["aA"] - c["po"]["aH"]) / n,
            "dws_h": dws_h, "dws_a": dws_a, "G": dws_h + dws_a,
            "G_se": paired_standard_error(c["g"][0], c["g"][1], n),
            "dpo_h_se": paired_standard_error(c["ph"][0], c["ph"][1], n),
            "dpo_a_se": paired_standard_error(c["pa"][0], c["pa"][1], n),
            "counts": {"ws": dict(c["ws"]), "po": dict(c["po"])},
        })
    return {"games": games, "proj_wins": {o: win_sum[o] / n for o in field.orgs},
            "n_sims": n, "seed": int(seed), "fmt": fmt, "home_edge": home_edge}


# ---------------------------------------------------------------------------
# Postseason: the exact series recursion and the exact bracket.
# ---------------------------------------------------------------------------
def series_prob(probs: list[float], need: int, w_hi: int, w_lo: int) -> float:
    """P(the higher seed wins the series) from state (w_hi, w_lo), exact.

    probs[k] = P(higher seed wins game k), k counting from 0 over the whole series,
    so the next game's index is w_hi + w_lo."""
    memo: dict = {}

    def f(a: int, b: int) -> float:
        if a >= need:
            return 1.0
        if b >= need:
            return 0.0
        key = (a, b)
        if key not in memo:
            p = probs[a + b]
            memo[key] = p * f(a + 1, b) + (1.0 - p) * f(a, b + 1)
        return memo[key]

    return f(int(w_hi), int(w_lo))


def series_swing(probs: list[float], need: int, w_hi: int, w_lo: int) -> float:
    """P(win the series | win the next game) - P(win the series | lose it), the same
    number for both clubs."""
    return series_prob(probs, need, w_hi + 1, w_lo) - series_prob(probs, need, w_hi, w_lo + 1)


def game_probs(hi: str, lo: str, best_of: int, pattern: str, ph_home: dict) -> list[float]:
    """P(higher seed wins game k) for every game of a series, from the home pattern."""
    return [ph_home[(hi, lo)] if pattern[i] == "H" else 1.0 - ph_home[(lo, hi)]
            for i in range(best_of)]


def _node(rnd: str, best_of: int, pattern: str, host: str, left, right) -> dict:
    return {"round": rnd, "best_of": best_of, "pattern": pattern, "host": host,
            "left": left, "right": right}


def bracket_tree(seeds_by_lg: dict, fmt: str) -> dict:
    """The bracket of `bracket_once` as a tree. A leaf is a club; a node is a series
    with host rule 'left' (the left side is the higher seed) or 'wins' (the better
    record hosts, the left side on a tie)."""
    n = _check_fmt(fmt)
    champs = []
    for lg in sorted(seeds_by_lg):
        seeds = seeds_by_lg[lg]
        if len(seeds) != n:
            raise ValueError(f"{fmt} format needs {n} seeds a league, got {len(seeds)}")
        if fmt == "six":
            s1, s2, s3, s4, s5, s6 = seeds
            w36 = _node("F", 3, WC_PATTERN, "left", s3, s6)
            w45 = _node("F", 3, WC_PATTERN, "left", s4, s5)
            d1 = _node("D", 5, LDS_PATTERN, "left", s1, w45)
            d2 = _node("D", 5, LDS_PATTERN, "left", s2, w36)
        else:
            s1, s2, s3, s4, s5 = seeds
            w45 = _node("F", 1, WC_GAME_PATTERN, "left", s4, s5)
            d1 = _node("D", 5, LDS_PATTERN, "left", s1, w45)
            d2 = _node("D", 5, LDS_PATTERN, "left", s2, s3)
        champs.append(_node("L", 7, L7_PATTERN, "wins", d1, d2))
    if len(champs) != 2:
        raise ValueError("a bracket needs two leagues")
    return _node("W", 7, L7_PATTERN, "wins", champs[0], champs[1])


def _clubs(node) -> set:
    if isinstance(node, str):
        return {node}
    return _clubs(node["left"]) | _clubs(node["right"])


def _pair_state(series_state: dict, x: str, y: str) -> tuple[int, int]:
    st = (series_state or {}).get(frozenset((x, y))) or {}
    return int(st.get(x, 0)), int(st.get(y, 0))


def _hi_lo(node: dict, x: str, y: str, wins: dict) -> tuple[str, str]:
    """x comes from the left subtree, y from the right."""
    if node["host"] == "left":
        return x, y
    return (x, y) if wins[x] >= wins[y] else (y, x)


def _p_beats(node: dict, x: str, y: str, wins: dict, ph_home: dict,
             series_state: dict) -> float:
    """P(x wins the series against y at this node), from the recorded state."""
    hi, lo = _hi_lo(node, x, y, wins)
    w = _pair_state(series_state, hi, lo)
    need = node["best_of"] // 2 + 1
    p_hi = series_prob(game_probs(hi, lo, node["best_of"], node["pattern"], ph_home),
                       need, w[0], w[1])
    return p_hi if x == hi else 1.0 - p_hi


def winner_dist(node, wins: dict, ph_home: dict, series_state: dict) -> dict:
    """{club: P(club wins this node)} under the recorded series states."""
    if isinstance(node, str):
        return {node: 1.0}
    left = winner_dist(node["left"], wins, ph_home, series_state)
    right = winner_dist(node["right"], wins, ph_home, series_state)
    out: dict = {}
    for x, px in left.items():
        for y, py in right.items():
            if px == 0.0 or py == 0.0:
                continue
            p = _p_beats(node, x, y, wins, ph_home, series_state)
            out[x] = out.get(x, 0.0) + px * py * p
            out[y] = out.get(y, 0.0) + px * py * (1.0 - p)
    return out


def _path_to_meeting(root: dict, x: str, y: str) -> list:
    """The nodes from the root down to the series where x and y meet, as
    (node, side_of_x) pairs; raises when they cannot meet."""
    path = []
    node = root
    while not isinstance(node, str):
        lc, rc = _clubs(node["left"]), _clubs(node["right"])
        if x in lc and y in rc:
            path.append((node, "left"))
            return path
        if y in lc and x in rc:
            path.append((node, "right"))
            return path
        if x in lc and y in lc:
            path.append((node, "left"))
            node = node["left"]
        elif x in rc and y in rc:
            path.append((node, "right"))
            node = node["right"]
        else:
            break
    raise ValueError(f"{x} and {y} do not meet in this bracket")


def advance_after(root: dict, club: str, node: dict, wins: dict, ph_home: dict,
                  series_state: dict) -> float:
    """P(club wins the World Series | club wins the series at `node`), exact: the
    product over every later series of P(club beats the winner of the other side),
    each later series from 0-0 unless a state is recorded."""
    # the ancestors of `node`, root first, with the side `node` sits on
    chain = []
    cur = root
    while cur is not node:
        if isinstance(cur, str):
            raise ValueError("node is not in this bracket")
        if _contains(cur["left"], node):
            chain.append((cur, "left"))
            cur = cur["left"]
        elif _contains(cur["right"], node):
            chain.append((cur, "right"))
            cur = cur["right"]
        else:
            raise ValueError("node is not in this bracket")
    prob = 1.0
    for anc, side in chain:
        other = anc["right"] if side == "left" else anc["left"]
        opp = winner_dist(other, wins, ph_home, series_state)
        p = 0.0
        for o, po in opp.items():
            if side == "left":
                p += po * _p_beats(anc, club, o, wins, ph_home, series_state)
            else:
                p += po * (1.0 - _p_beats(anc, o, club, wins, ph_home, series_state))
        prob *= p
    return prob


def _contains(tree, node) -> bool:
    if tree is node:
        return True
    if isinstance(tree, str):
        return False
    return _contains(tree["left"], node) or _contains(tree["right"], node)


def postseason_stakes(seeds_by_lg: dict, wins: dict, talent: dict[str, float],
                      home: str, away: str, *, fmt: str = "six",
                      series_state: dict | None = None,
                      home_edge: float = HOME_EDGE) -> dict:
    """dWS for both clubs of a postseason game, exact.

    seeds_by_lg = {league: (seed 1, seed 2, ...)}; wins = final regular-season wins
    (home field in the championship series and the World Series); talent = {org: win
    rate against an average club}; series_state = {frozenset((x, y)): {x: wins, y:
    wins}} for every series played or begun before the game, from finals dated before
    it (a pair meets at most once in a postseason, so the pair names the series).

    dSeries is the exact swing of this game on its series from the recorded state,
    with each remaining game's probability from the round's home pattern;
    dWS_T = dSeries x P(T wins the World Series | T wins this series), the second
    factor from the exact bracket under the recorded states. No random draw, so the
    standard error is 0."""
    root = bracket_tree(seeds_by_lg, fmt)
    seeded = sorted(_clubs(root))
    ph_home = _ph_table(seeded, talent, home_edge)
    path = _path_to_meeting(root, home, away)
    node = path[-1][0]
    state = series_state or {}
    # both clubs must be able to reach this series under the recorded states
    home_side = path[-1][1]
    away_side = "right" if home_side == "left" else "left"
    for club, side in ((home, home_side), (away, away_side)):
        if winner_dist(node[side], wins, ph_home, state).get(club, 0.0) < 1.0 - 1e-12:
            raise ValueError(f"{club} has not reached this series under the recorded states")
    x_left = home if home_side == "left" else away
    y_right = away if x_left == home else home
    hi, lo = _hi_lo(node, x_left, y_right, wins)
    w_hi, w_lo = _pair_state(state, hi, lo)
    need = node["best_of"] // 2 + 1
    if w_hi >= need or w_lo >= need:
        raise ValueError("that series is already decided")
    probs = game_probs(hi, lo, node["best_of"], node["pattern"], ph_home)
    d_series = series_swing(probs, need, w_hi, w_lo)
    adv_h = advance_after(root, home, node, wins, ph_home, state)
    adv_a = advance_after(root, away, node, wins, ph_home, state)
    dws_h, dws_a = d_series * adv_h, d_series * adv_a
    return {"home": home, "away": away, "game_type": node["round"], "fmt": fmt,
            "best_of": node["best_of"], "game_number": w_hi + w_lo + 1,
            "state": {hi: w_hi, lo: w_lo}, "d_series": d_series,
            "advance_h": adv_h, "advance_a": adv_a,
            "dpo_h": None, "dpo_a": None,
            "dws_h": dws_h, "dws_a": dws_a, "G": dws_h + dws_a, "G_se": 0.0,
            "method": "exact"}


def world_series_probs(seeds_by_lg: dict, wins: dict, talent: dict[str, float], *,
                       fmt: str = "six", series_state: dict | None = None,
                       home_edge: float = HOME_EDGE) -> dict:
    """{club: P(wins the World Series)} under the recorded states, exact."""
    root = bracket_tree(seeds_by_lg, fmt)
    ph_home = _ph_table(sorted(_clubs(root)), talent, home_edge)
    return winner_dist(root, wins, ph_home, series_state or {})


# ---------------------------------------------------------------------------
# S, Q, A, D and the index.
# ---------------------------------------------------------------------------
def _g_ref(g_ref: float | None) -> float:
    ref = G_REF if g_ref is None else g_ref
    if ref is None:
        raise ValueError("G_REF is not frozen yet (the gate tool's commit, Q10_07, "
                         "writes it); pass g_ref explicitly")
    if ref <= 0:
        raise ValueError("G_REF must be positive")
    return float(ref)


def stakes_multiple(G: float, g_ref: float | None = None) -> float:
    """L = G / G_REF, G clamped to its range [0, 2]."""
    return min(max(float(G), 0.0), 2.0) / _g_ref(g_ref)


def stakes_score(G: float, g_ref: float | None = None) -> float:
    """S = ln(1 + L) / ln(1 + 2 / G_REF), in [0, 1]: 0 when nothing rides on the game,
    1 for a World Series game 7 (G = 2)."""
    ref = _g_ref(g_ref)
    return math.log1p(stakes_multiple(G, ref)) / math.log1p(2.0 / ref)


def percentile_ranks(values: dict) -> dict:
    """{key: percentile rank in [0, 1]}: (average rank - 1) / (n - 1), ties averaged,
    the lowest 0 and the highest 1; a single value or an all-tied field is 0.5."""
    items = [(k, float(v)) for k, v in values.items() if v is not None]
    n = len(items)
    if n == 0:
        return {}
    if n == 1:
        return {items[0][0]: 0.5}
    out = {}
    for k, v in items:
        below = sum(1 for _, w in items if w < v)
        equal = sum(1 for _, w in items if w == v)
        out[k] = (below + (equal - 1) / 2.0) / (n - 1)
    return out


def matchup_quality(proj_wins: dict, home: str, away: str) -> float:
    """Q = min(q_h, q_a), each club's percentile rank of projected full-season wins
    over the field."""
    q = percentile_ranks(proj_wins)
    return min(q[home], q[away])


def starter_percentile(pitcher_id, board: dict) -> float | None:
    """A probable's percentile of SEM+ among the qualified starters on the pricing
    board ({pitcher id: SEM+}); None when the probable is unannounced or not on it."""
    if pitcher_id is None or board is None or pitcher_id not in board \
            or board[pitcher_id] is None:
        return None
    return percentile_ranks(board)[pitcher_id]


def starters_score(home_pitcher, away_pitcher, board: dict) -> float | None:
    """A = min(a_h, a_a), or None (never zero) when either is missing."""
    a_h = starter_percentile(home_pitcher, board)
    a_a = starter_percentile(away_pitcher, board)
    if a_h is None or a_a is None:
        return None
    return min(a_h, a_a)


def division_flag(div_home, div_away) -> int:
    """D: 1 for a division game."""
    return int(div_home is not None and div_home == div_away)


def index_value(S: float, Q: float, A: float | None, D: int) -> int | None:
    """II = round(100 x (0.60 S + 0.15 Q + 0.15 A + 0.10 D)), nearest integer, a half
    rounding up (so the lane's World Series game 7 between elite clubs and aces,
    88.5, is 89); None when A is null, because II is not published then."""
    if A is None:
        return None
    raw = 100.0 * (W_STAKES * S + W_QUALITY * Q + W_STARTERS * A + W_DIVISION * D)
    return int(math.floor(round(raw, 9) + 0.5))


def band_of(ii: int | None) -> str | None:
    """Under 30 routine, 30 to 49 raised, 50 to 69 high, 70 and over peak."""
    if ii is None:
        return None
    lo, mid, hi = BANDS
    if ii < lo:
        return BAND_NAMES[0]
    if ii < mid:
        return BAND_NAMES[1]
    if ii < hi:
        return BAND_NAMES[2]
    return BAND_NAMES[3]
