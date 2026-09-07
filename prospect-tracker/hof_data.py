# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Hall of Fame data shelf: the career frame, the public benchmark
metrics, and the label contract (plan lanes H-DATA-3, H-DATA-4 and the label
half of H-PRED-1, docs/master-plan-2026-09-05-opus.md).

WHAT THIS IS. One module that turns the Baseball-Reference war_daily stint
frame into a per-player career shelf, and then reimplements the PUBLIC Hall of
Fame benchmarks on top of it so this repo is measured AGAINST the public work
instead of asserting over it. The benchmarks here are WAR7, JAWS, career WAA,
the positive-WAA sum, and an in-house WAR ink. Every one of them is a
reproduction target, not an invention.

WHAT THIS IS NOT. It is not a Hall of Fame model, not a ballot source, and not
a position source. It does not know who is in the Hall. It does not know what
position anybody played. It does not carry counting stats: the war_daily frame
has PA, G, Inn, IPouts and the run decomposition, and no hits, no home runs,
no saves and no wins, so every milestone feature in the plan waits on the
Lahman drop (H-DATA-1).

THE PROVIDER PIN THAT GOVERNS THE WHOLE MODULE. eWAR exists only from 2011
(data/ewar.json covers seasons 2011-2026), so a Hall of Fame career that ends
in 1935 has no eWAR at all and a career that straddles 2011 would be spliced
from two different WAR definitions. Every number in this module is therefore
bWAR: WAR_PROVIDER is the frozen string 'bwar' and it is the ONLY value ever
passed to war_source.stint_frame. No public function in this module accepts a
provider argument, so a caller cannot reach the eWAR default by accident.
war_source.DEFAULT_PROVIDER is 'ewar_v2'; that default is what the pin exists
to defeat, and test_hof_data pins both halves.

REPRODUCTION CONTROL (measured 2026-09-06 against .cache/war_daily, exact to
the tenth published by Baseball-Reference):

    Babe Ruth        career 182.6   WAR7 84.4   JAWS 133.5   22 seasons
    Walter Johnson   career 168.4   WAR7 92.0   JAWS 130.2   21 seasons
    Cy Young         career 163.6   WAR7 78.0   JAWS 120.8   22 seasons
    Barry Bonds      career 162.8   WAR7 72.7   JAWS 117.7   22 seasons
    Willie Mays      career 156.2   WAR7 73.6   JAWS 114.9   23 seasons

These are two-way totals: a season's WAR is the sum across the batting and
pitching frames before anything else happens, which is why Ruth's 182.6 and
Johnson's 168.4 both come out whole. A shelf that cannot reproduce JAWS cannot
be benchmarked against JAWS, so career_frame is wrong until these five rows
come back. reproduction_check() runs the comparison.

THE TENTHS MUST BE ROUNDED ON THE PRINTED DECIMAL, NOT ON THE DOUBLE, and
this is not cosmetic. The war_daily frame carries season WAR at TWO decimals,
so a career sum lands on the double nearest a two-decimal value, and that
double can sit just BELOW the tenths half. There is no tie and half-to-even
never enters it. Measured this session: Walter Johnson's career sums to the
double that prints as 168.35, whose exact value is 168.3499999999999943...,
and Willie Mays's WAR7 to the double that prints as 73.55, exact value
73.5499999999999971.... Python's round() rounds the double it is handed, so it
correctly returns 168.3 and 73.5, and those two of the fifteen published cells
come out a tenth low against Baseball-Reference. round_half_up() round-trips
through the shortest decimal representation instead (Decimal(repr(x)) with
ROUND_HALF_UP), which recovers the 168.35 the two-decimal export printed and
carries it up to 168.4. Measured over the fifteen cells this session, exactly
two move under that treatment: Johnson's career WAR and Mays's WAR7. B-Ref
itself carries more precision than the published CSV, so the gap between the
printed decimal and the double is an artifact of the export, not a
disagreement about the WAR.

THE FRAME, MEASURED THIS SESSION (.cache/war_daily, 2026-09-06):
  bat.parquet  126,518 stint rows by 49 columns, 1871-2026, 23,650 bbref ids
  pit.parquet   57,849 stint rows by 43 columns, 1871-2026, 12,108 bbref ids
  union         23,786 bbref ids, 117,173 player-seasons with a WAR value
  eligible E     3,620 players (10 or more seasons with a WAR row, last season
                 at or before current year minus 5, so 2021 or earlier today)

E BY POSITION CLASS at as_of_year 2026, with the count whose class rests on
the weak positional-rate basis in brackets:
  SP 1,057 [0]   OF 972 [384]   MI 789 [401]   RP 306 [0]   C 267 [0]
  1B/DH 229 [40]
The C class carries zero rate-basis members because a pre-1953 catcher cannot
be found at all; those catchers are inside the MI bracket. Median JAWS by
class: SP 18.22, 1B/DH 17.50, OF 17.27, MI 13.03, RP 8.29, C 7.22. 187 of the
3,620 carry a Negro Leagues season (2,259 player-seasons); 204 carry a season
in a nineteenth-century or outlaw major.

NEGRO LEAGUES AND THE NINETEENTH CENTURY ARE IN THE FRAME (owner decision 13:
include, with an era factor and a disclosure). Measured league-season rows:
  the four long-running Negro Leagues {NNL, ECL, NN2, NAL}: 8,072 batting and
  3,171 pitching stint rows over 2,263 players. This reproduces the master
  plan's count exactly, which is how the frame identity was verified.
  all seven leagues MLB recognised as major in 2020, adding {ANL, EWL, NSL}:
  8,655 batting and 3,411 pitching rows over 2,364 players, and 7,665 batting
  plus 3,038 pitching player-seasons.
  Nineteenth-century and outlaw majors {AA, UA, PL, FL} are present too.
THE DISCLOSURE, measured from the frame's own team-game maxima: Negro Leagues
seasons are short. Median longest team schedule by league is NNL 92 games,
ECL 71, ANL 81, EWL 61, NSL 52, NN2 63, NAL 50, against 155 to 156 in the
contemporaneous AL and NL. Raw Negro Leagues WAR is therefore accumulated over
roughly a third to three fifths of a white-major-league season, and era_factor
exposes that ratio. It is NOT applied by default, because scaling a career up
by schedule length is a claim about playing-time counterfactuals that this
module does not make.

WHAT THIS MODULE REFUSES TO CLAIM.
  1. That it knows WHAT A PLAQUE SAYS. The ballot source is now ingested
     (data/hof_ballots.json) and the labels resolve, so the old refusal here,
     that no ballot source exists, is retired. What replaces it is narrower and
     harder: the source records which ELECTORATE voted, never the role the
     plaque names. An inductee who played and was later enshrined as a manager
     reads as a player induction, and Connie Mack, Casey Stengel, Bucky Harris,
     Al Lopez and Billy Southworth all reach the eligible universe that way.
     Until H-DATA-PLAQUE lands, label_any means INDUCTED BY ANY ROUTE, PLAQUE
     ROLE UNVERIFIED, the unverified set is published in
     data/hof_ledger_eval.json, and hall_line still returns a shelf with
     line=None because a Hall-sized line needs the count of players inducted AS
     PLAYERS and that count is exactly what is not known.
  2. That it knows what position a player played. The war_daily frame carries
     no position column. position_class infers one, and the inference is
     measurably weak before 1953: see POSITION_CLASS_NOTE.
  3. That WAR ink is a public metric. Black Ink and Gray Ink are Bill James
     counting-stat measures and are NOT what this computes. war_ink here is an
     in-house WAR-rank measure, defined in war_ink, and it should never be
     printed next to a published Black Ink number as though they matched.
  4. That the pitching WAA column closes the B-Ref identity. On the batting
     frame WAR == WAA + WAR_rep to the last bit (max residual 0.0 over 114,495
     rows). On the pitching frame it does NOT: max residual 2.62, mean 0.096
     over 57,653 rows, and WAA_adj is worse (max 16.89, mean 0.786). The
     pitching WAA served here is B-Ref's published column, carried as
     published.
"""

from __future__ import annotations

import datetime as _dt
import decimal
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

#: The repo root, for the artifacts this module writes and the ballot panel it
#: reads.
ROOT = Path(__file__).resolve().parent


def round_half_up(x, ndigits: int = 1) -> float:
    """Round the PRINTED decimal half away from zero, which is what
    Baseball-Reference does.

    NOT a half-to-even fix and NOT a tie-break. The two-decimal export means a
    career sum lands on the double nearest a two-decimal value, and that double
    can sit just below the tenths half: 168.35 is really 168.3499999999999943...
    and 73.55 is really 73.5499999999999971..., both truncated from the exact
    expansions measured this session.
    Python's round() rounds the double, so round(168.35, 1) is 168.3 and
    round(73.55, 1) is 73.5, and those are Walter Johnson's career WAR and
    Willie Mays's WAR7, two of the fifteen reproduction cells.

    Decimal(repr(f)) is the load-bearing part. repr gives the shortest decimal
    that round-trips, so it recovers the '168.35' the export printed and
    ROUND_HALF_UP carries it to 168.4. Decimal(f) would NOT work: it expands
    the double, and that expansion quantizes to 168.3 under ROUND_HALF_UP
    exactly as the builtin does."""
    if x is None:
        return float("nan")
    f = float(x)
    if math.isnan(f) or math.isinf(f):
        return f
    q = decimal.Decimal(1).scaleb(-int(ndigits))
    return float(decimal.Decimal(repr(f)).quantize(
        q, rounding=decimal.ROUND_HALF_UP))

# ---------------------------------------------------------------------------
# The pin.
# ---------------------------------------------------------------------------

WAR_PROVIDER: str = "bwar"
"""FROZEN. The only provider string this module will ever pass to war_source.

eWAR (war_source.DEFAULT_PROVIDER == 'ewar_v2') covers 2011-2026 only. A Hall
of Fame career frame that read it would splice two WAR definitions inside a
single career and would carry no WAR at all for anybody who retired before
2011, which is most of the Hall. Do not add a provider parameter to anything
public in this module; the absence of one is the guarantee."""

SIDES: tuple[str, str] = ("bat", "pit")

# ---------------------------------------------------------------------------
# Eligibility.
# ---------------------------------------------------------------------------

MIN_SEASONS: int = 10
"""BBWAA rule 3B: a player must have played in ten championship seasons."""

ELIGIBILITY_LAG_YEARS: int = 5
"""BBWAA rule 3A: five full seasons out of the game before the first ballot.
Applied here as last_season at or before current_year - 5, which is the
frame-side approximation. It cannot see a player who is retired but whose
final season is inside the window for a different reason, and it cannot see
the early-ballot exceptions the BBWAA has granted; both wait on the ballot
source."""

# ---------------------------------------------------------------------------
# Leagues.
# ---------------------------------------------------------------------------

NEGRO_LEAGUES: frozenset[str] = frozenset(
    {"NNL", "ECL", "ANL", "EWL", "NSL", "NN2", "NAL"})
"""All seven leagues MLB recognised as major in December 2020."""

NEGRO_LEAGUES_CORE4: frozenset[str] = frozenset({"NNL", "ECL", "NN2", "NAL"})
"""The four long-running Negro Leagues. This is the set the master plan
counted (8,072 batting and 3,171 pitching rows, 2,263 players); kept so the
plan's figure stays reproducible from this module."""

OTHER_HISTORICAL_MAJORS: frozenset[str] = frozenset({"AA", "UA", "PL", "FL"})
"""American Association 1882-1891, Union Association 1884, Players League
1890, Federal League 1914-1915."""

MODERN_MAJORS: frozenset[str] = frozenset({"AL", "NL"})

SCHEDULE_REFERENCE_GAMES: int = 154
"""The denominator era_factor reports against. 154 rather than 162 because the
Negro Leagues overlapped the 154-game AL and NL, and the measured AL/NL
team-game maximum over 1920-1948 is 155 to 156."""

# ---------------------------------------------------------------------------
# Position classes.
# ---------------------------------------------------------------------------

CLASSES: tuple[str, ...] = ("C", "MI", "1B/DH", "OF", "SP", "RP")

RELIEF_SHARE_RP: float = 0.70
"""A pitcher is a reliever at or above this share of career relief outs."""

PITCHER_MIN_IPOUTS: int = 900
"""300 innings. Below it a pitching line is a curiosity, not a career."""

PITCH_SEASON_OUTS: int = 600
BAT_SEASON_PA: int = 650
"""One season of work on each side, used to put pitching and batting playing
time on the same scale. A career is a pitcher's when it clears
PITCHER_MIN_IPOUTS and IPouts/600 exceeds PA/650.

WHY EXPOSURE AND NOT WAR. The first cut of this rule compared career pitching
WAR to career batting WAR, and it filed 297 of the 3,572 careers with 300 or
more innings as hitters, including Jordan Lyles (-2.17 pitching WAR against
-0.24 batting WAR on 1,509 innings), because a below-replacement pitcher who
almost never bats can have the smaller negative on the batting side. The
exposure rule files 3,556 of the 3,572 as pitchers and leaves exactly 16 on
the hitting side: John Ward, Kid Gleason, Babe Ruth, Elmer Smith, Cy Seymour,
Johnny Cooney, George Van Haltren, Shohei Ohtani and eight more, which is the
real two-way list. 8 careers sit inside 25 percent either way, and John Ward
(12.35 pitching seasons against 12.48 batting) is the closest call in the
frame; Baseball-Reference's own JAWS files him at shortstop, so the rule
agrees with the public shelf on the hardest case it has."""

MI_RATE_CUT: float = 2.0
"""Career positional-adjustment runs per 650 PA at or above which a fielder is
filed under MI. Measured career rates: Ozzie Smith 9.75, Luke Appling 9.48,
Cal Ripken 8.04, Derek Jeter 7.42, Joe Morgan 4.49, Charlie Gehringer 4.92,
Pie Traynor 4.36, Mike Schmidt 2.72, then Ken Griffey Jr 1.19, Willie Mays
-1.01, George Brett -1.82, Rod Carew -2.09. Third base sits at the cut, so
third basemen file under MI: the class list this module was asked for has no
third-base slot, and folding third into the infield beats folding it into the
corner outfield."""

CORNER_RATE_CUT: float = -8.0
"""Below this rate a fielder without a fielding-component signature is filed
1B/DH rather than OF. Measured: Lou Gehrig -6.68, Babe Ruth -6.43, Edgar
Martinez -9.17, Frank Thomas -11.30, David Ortiz -13.13, against corner
outfielders Ted Williams -6.33, Tony Gwynn -4.95, Barry Bonds -5.22."""

POSITION_COMPONENT_FIRST_YEAR: int = 1953
"""runs_catcher, runs_infield and runs_outfield are null before this. Measured
non-zero fraction of runs_catcher by decade: 0.000 for every decade from the
1870s through the 1940s, then 0.047 in the 1950s and 0.051 to 0.077 after."""

POSITION_CLASS_NOTE: str = (
    "position_class infers a class from run components (1953 and later) or "
    "from the positional-adjustment rate alone (before 1953). The rate-only "
    "fallback was scored against the component basis on 1,239 careers with "
    "3,000 or more PA that began in 1955 or later: 72.2 percent agreement "
    "overall, 81.1 percent excluding catchers, and 0 of 135 catchers "
    "recovered, 122 of whom land in MI. Pre-1953 catchers carry a "
    "positional-adjustment rate that is indistinguishable from second base "
    "and BELOW shortstop (Bill Dickey 5.20, Mickey Cochrane 5.05, Gabby "
    "Hartnett 5.11, against Charlie Gehringer 4.92, Rogers Hornsby 5.18, Joe "
    "Cronin 8.99, Luke Appling 9.48). So: a class carrying pos_basis "
    "'positional_rate' is a guess, the C class is empty before 1953 by "
    "construction, and hall_line reports the low-confidence count per class "
    "rather than hiding it. A real position source (Lahman Appearances, plan "
    "lane H-DATA-1) retires this whole function. "
    "THE COMPONENT BASIS MISFILES TOO, and it misfiles for a stated reason: "
    "runs_catcher, runs_infield and runs_outfield are fielding RUNS, not "
    "playing time, so a short bad stint can outweigh a long one. Craig Biggio "
    "(runs_catcher -26 against runs_infield -22) files C where B-Ref files "
    "him at second base, and Robin Yount (runs_outfield -23 against "
    "runs_infield +7) files OF where B-Ref files him at shortstop. Both are "
    "playing-time questions the frame cannot answer."
)

# ---------------------------------------------------------------------------
# WAR ink.
# ---------------------------------------------------------------------------

INK_LEAD_POINTS: int = 4
INK_TOPTEN_POINTS: int = 1
INK_TOPTEN_DEPTH: int = 10

# ---------------------------------------------------------------------------
# The label contract (H-PRED-1). No ballot source exists in this repo.
# ---------------------------------------------------------------------------

BALLOT_SOURCE: str = "data/hof_ballots.json"
"""The artifact plan lane H-DATA-2 produces, and it is BUILT.

Both upstreams are ingested by tools/hof_ballot_ingest.py: the StatsAPI awards
endpoint /awards/MLBHOF/recipients (inductees only, 354 rows over 85 election
seasons) and the Baseball-Reference election pages (/awards/hof_<year>.shtml),
which carry the vote shares for the non-inductees.

ONE DEFECT IN IT IS REPAIRED AT LOAD TIME rather than in the file. StatsAPI
names inductees by MLBAM id and Baseball-Reference names ballot rows by bbref
id, and where the ingest could not bridge the two the inductee was dropped from
the ledger: 130 of 354, of whom 63 sit inside the eligible universe. See
crosswalk_bbref_mlbam.
"""

BALLOT_SOURCE_FIELDS: tuple[str, ...] = (
    "player_id",        # bbref id, the join key this module already uses
    "election_year",
    "route",            # 'BBWAA' | 'VETERANS' | 'SPECIAL'
    "ballot_number",    # 1-based position in the player's own BBWAA window
    "votes",
    "ballots_cast",
    "vote_pct",
    "elected",          # bool
    "dropped_off",      # bool: fell under the five percent threshold
)


class BallotSourceMissing(NotImplementedError):
    """Raised by every label function. NotImplementedError on purpose: a
    caller that catches it is asking for a label that does not exist yet, and
    the only correct response is to ingest the ballot source, never to guess a
    membership list."""


CENSORED = None
"""The label value for a player whose ballot window has not closed. It is None
and it is NEVER 0. A censored player scored 0 teaches a merit model that a
still-eligible candidate is a confirmed non-Hall-of-Famer, which is exactly
backwards, and it is the single failure mode assert_no_censored_zero exists to
catch."""


# ---------------------------------------------------------------------------
# Frame loading. The pin lives here and nowhere else.
# ---------------------------------------------------------------------------

_FRAME_CACHE: dict = {}
_CAREER_CACHE: dict = {}


def stint_frame(side: str, *, offline: bool = False) -> pd.DataFrame:
    """One war_daily stint frame, on bWAR, memoised per process.

    ``offline=True`` reads war_source's own last-good parquet directly instead
    of going through pybaseball. That path exists because
    ``pybaseball.bwar_pitch`` carries no disk cache decorator, so the pitching
    side is a live download on every process (war_source documents this at
    length), and a test suite must not depend on the network. The bytes are
    the same bytes war_source wrote; this module does not re-derive the path.
    """
    if side not in SIDES:
        raise ValueError(f"side must be one of {SIDES}, got {side!r}")
    key = (side, bool(offline))
    hit = _FRAME_CACHE.get(key)
    if hit is not None:
        return hit
    import war_source
    if offline:
        df = war_source._load_last_good(side)
        if df is None or not len(df):
            raise RuntimeError(
                f"hof_data: offline read found no last-good {side} frame at "
                f"{war_source._cache_path(side)}; run once online first")
    else:
        # THE PIN. This is the only stint_frame call in the module.
        df = war_source.stint_frame(side, provider=WAR_PROVIDER)
    _FRAME_CACHE[key] = df
    return df


def clear_cache() -> None:
    """Drop every memoised object in this module.

    FOUR CACHES, NOT TWO. The old version cleared the frame caches only, so a
    test that cleared between an unrepaired and a repaired ledger read got the
    stale one back and passed for the wrong reason.
    """
    _FRAME_CACHE.clear()
    _CAREER_CACHE.clear()
    _BALLOT_CACHE.clear()
    _XWALK_CACHE.clear()


_XWALK_CACHE: dict = {}


def crosswalk_bbref_mlbam() -> dict:
    """{str(mlbam id): bbref player_ID}, read straight off the war_daily parquets.

    WHY THIS EXISTS. StatsAPI names the Hall of Fame inductees by MLBAM id and
    Baseball-Reference names ballot rows by bbref id. Where the ingest could not
    bridge the two, the inductee simply did not enter the ledger, and the label
    layer then said he is not in the Hall. Measured on 2026-09-06 that was 130 of
    354 inductees, and 63 of them sit inside the eligible universe: the shipped
    `label_any` called Charlie Gehringer, Ed Delahanty, Eddie Plank, Buck Ewing
    and Jesse Burkett non-Hall-of-Famers, 33 as a resolved zero and 30 as
    censored.

    Both parquets already carry BOTH ids, so the bridge was on disk the whole
    time. Measured: 23,681 pairs, 23,681 distinct on each side, one to one.

    NO `offline` PARAMETER, deliberately. This reads war_source's last-good
    parquet BY PATH and never calls `war_source.stint_frame`, so it can never
    turn `label_frame(offline=True)` into a network call. That is a real hazard
    and not a hypothetical: the pitching side of pybaseball carries no disk
    cache, and hof_data documents it as a live download on every process.

    Returns {} if the parquets are not readable, which leaves the ledger exactly
    as it was before this function existed. That is the safe direction, but it is
    also SILENT, so `_load_ballots` records whether the crosswalk was available
    and `tools/hof_ledger_check.py` fails loudly when it was not.
    """
    # A COPY, NEVER THE CACHE ITSELF. Handing out the interior means a caller
    # holds a live reference that `clear_cache()` empties underneath it. That
    # is not hypothetical: the ledger producer captured the crosswalk, ran a
    # horizon sweep that clears caches between arms, and then serialized zero
    # pairs into the artifact while the repair it was documenting had worked
    # perfectly.
    if _XWALK_CACHE:
        return dict(_XWALK_CACHE)
    try:
        import war_source
        import pandas as _pd
    except Exception:                              # noqa: BLE001
        return {}
    out: dict = {}
    for side in SIDES:
        try:
            path = war_source._cache_path(side)
            df = _pd.read_parquet(path, columns=["player_ID", "mlb_ID"])
        except Exception:                          # noqa: BLE001
            continue
        df = df.dropna(subset=["player_ID", "mlb_ID"])
        for pid, mid in zip(df["player_ID"], df["mlb_ID"]):
            try:
                out[str(int(mid))] = str(pid)
            except (TypeError, ValueError):
                continue
    _XWALK_CACHE.update(out)
    return dict(_XWALK_CACHE)


# ---------------------------------------------------------------------------
# Season frame.
# ---------------------------------------------------------------------------

def season_frame(*, offline: bool = False) -> pd.DataFrame:
    """One row per (player_ID, year_ID): WAR summed across sides and stints.

    Columns: player_ID, year_ID, war, waa, bat_war, pit_war, lg_ID, age, pa,
    ipouts, exposure, name.

    Rows with a null WAR are dropped BEFORE the sum. Measured: 12,023 null-WAR
    batting rows, every one of them flagged pitcher='Y' with a mean of 0.029
    PA (designated-hitter-era pitchers who never batted), and 196 null-WAR
    pitching rows. Dropping them costs nothing and keeps the sum honest.

    lg_ID is the league of the stint with the most playing time that season,
    where playing time is PA on the batting side and IPouts on the pitching
    side. It is used for the WAR ink ranks and for the Negro Leagues flag.
    """
    parts = []
    for side in SIDES:
        raw = stint_frame(side, offline=offline)
        keep = ["player_ID", "name_common", "year_ID", "lg_ID", "age",
                "WAR", "WAA"]
        d = raw.loc[:, [c for c in keep if c in raw.columns]].copy()
        d["pa"] = (pd.to_numeric(raw["PA"], errors="coerce").fillna(0.0)
                   if side == "bat" else 0.0)
        d["ipouts"] = (pd.to_numeric(raw["IPouts"], errors="coerce").fillna(0.0)
                       if side == "pit" else 0.0)
        d["exposure"] = d["pa"] if side == "bat" else d["ipouts"]
        d["side"] = side
        d["WAR"] = pd.to_numeric(d["WAR"], errors="coerce")
        d["WAA"] = pd.to_numeric(d["WAA"], errors="coerce")
        parts.append(d.dropna(subset=["WAR"]))
    a = pd.concat(parts, ignore_index=True)

    is_bat = (a["side"].values == "bat")
    a["bat_war"] = np.where(is_bat, a["WAR"].values, 0.0)
    a["pit_war"] = np.where(is_bat, 0.0, a["WAR"].values)

    g = a.groupby(["player_ID", "year_ID"], sort=False)
    out = g.agg(
        war=("WAR", "sum"),
        waa=("WAA", "sum"),
        bat_war=("bat_war", "sum"),
        pit_war=("pit_war", "sum"),
        age=("age", "max"),
        pa=("pa", "sum"),
        ipouts=("ipouts", "sum"),
        exposure=("exposure", "sum"),
        name=("name_common", "first"),
    ).reset_index()

    # Primary league: the stint with the most playing time.
    lead = (a.sort_values("exposure", ascending=False, kind="mergesort")
              .drop_duplicates(subset=["player_ID", "year_ID"], keep="first")
              .loc[:, ["player_ID", "year_ID", "lg_ID"]])
    out = out.merge(lead, on=["player_ID", "year_ID"], how="left")
    return out


# ---------------------------------------------------------------------------
# The public benchmark shelf.
# ---------------------------------------------------------------------------

def war7(season_wars: Sequence[float]) -> float:
    """Sum of the seven best seasons. Fewer than seven seasons sums them all,
    negatives included, which is what Baseball-Reference does and which only
    ever bites players who cannot clear MIN_SEASONS anyway."""
    v = sorted((float(x) for x in season_wars), reverse=True)
    return float(sum(v[:7]))


def jaws(career_war: float, war7_value: float) -> float:
    """Jaffe WAR Score: the mean of career WAR and WAR7. Not ours."""
    return (float(career_war) + float(war7_value)) / 2.0


def positive_waa(season_waas: Sequence[float]) -> float:
    """Sum of the seasons with WAA above zero, the below-average seasons
    discarded rather than netted. This is the shape Hall Rating and wWAR use to
    stop a long tail of replacement-level seasons from paying for a peak.

    The columns support it on both sides, but not equally. On the batting frame
    WAR == WAA + WAR_rep exactly (max residual 0.0 over 114,495 rows). On the
    pitching frame the identity does NOT close: max residual 2.62, mean 0.096
    over 57,653 rows, and WAA_adj is further off (max 16.89, mean 0.786). The
    pitching WAA here is B-Ref's published column, carried as published."""
    tot = 0.0
    for x in season_waas:
        if x is None:
            continue
        f = float(x)
        if math.isnan(f) or f <= 0.0:
            continue
        tot += f
    return tot


def war_ink(seasons: pd.DataFrame) -> pd.Series:
    """In-house WAR ink: INK_LEAD_POINTS for each league-leading season plus
    INK_TOPTEN_POINTS for each top-INK_TOPTEN_DEPTH season, ranked on the
    player-season WAR total inside (year_ID, lg_ID).

    THIS IS NOT BLACK INK OR GRAY INK. Bill James's ink measures rank counting
    stats (home runs, wins, strikeouts) and weight the categories. This ranks
    one thing, WAR, and it exists so the shelf has a peak-prominence column
    before the Lahman counting stats land. Do not print it beside a published
    Black Ink number.

    Hitters and pitchers rank in ONE pool per league-season, so 'top ten in the
    league' means top ten among everybody, not top ten among hitters. A leading
    season scores 4, not 5: the lead points replace the top-ten point.

    Short seasons are not adjusted. A Negro Leagues league-season fielded far
    fewer teams over a 39 to 99 game schedule, so leading it is a different
    achievement from leading a 154-game eight-team AL, and era_factor is the
    disclosure, not a correction applied here."""
    s = seasons.dropna(subset=["lg_ID"]).copy()
    s["rank"] = (s.groupby(["year_ID", "lg_ID"])["war"]
                  .rank(method="min", ascending=False))
    r = s["rank"].values
    s["ink"] = np.where(r <= 1.0, float(INK_LEAD_POINTS),
                        np.where(r <= INK_TOPTEN_DEPTH,
                                 float(INK_TOPTEN_POINTS), 0.0))
    return s.groupby("player_ID")["ink"].sum()


def _schedule_table(*, offline: bool = False) -> pd.DataFrame:
    """(year_ID, lg_ID) -> longest team schedule observed, from the batting
    frame's G column. A proxy for schedule length, and the only one the frame
    supports: there is no schedule table here."""
    b = stint_frame("bat", offline=offline)
    tg = b.groupby(["year_ID", "lg_ID", "team_ID"])["G"].max().reset_index()
    return (tg.groupby(["year_ID", "lg_ID"])["G"].max()
              .reset_index(name="max_team_g"))


def era_factor(seasons: pd.DataFrame, *, offline: bool = False) -> pd.Series:
    """Per player: SCHEDULE_REFERENCE_GAMES divided by the playing-time-weighted
    mean of the longest team schedule in each of his league-seasons.

    THE DISCLOSURE, NOT A CORRECTION. This is returned for reporting and it is
    never multiplied into career_war, war7, jaws or ink. Measured medians of
    the longest team schedule per league-season, straight out of the frame's
    own G column: NNL 92, ECL 71, ANL 81, EWL 61, NSL 52, NN2 63, NAL 50,
    against 155 in the 1920-1948 AL and 156 in the NL. A Negro Leagues career
    therefore reads roughly 1.7x to 3.1x on this scale, and that ratio is a
    statement about schedule length only. Scaling a career by it would assert
    that the missing games would have been played at the same rate against the
    same competition, which this module does not claim."""
    sched = _schedule_table(offline=offline)
    s = seasons.merge(sched, on=["year_ID", "lg_ID"], how="left")
    w = s["exposure"].where(s["exposure"] > 0, 1.0)
    s = s.assign(_num=s["max_team_g"] * w, _den=w)
    g = s.groupby("player_ID").agg(num=("_num", "sum"), den=("_den", "sum"))
    den = g["den"].where(g["den"] > 0, np.nan)
    return (SCHEDULE_REFERENCE_GAMES / (g["num"] / den)).rename("era_factor")


# ---------------------------------------------------------------------------
# Position class.
# ---------------------------------------------------------------------------

def _position_inputs(*, offline: bool = False,
                    season_cutoff=None) -> pd.DataFrame:
    """Career sums of every column that carries a positional signal.

    `season_cutoff` truncates BOTH stint frames to seasons at or before that
    year before summing, which is what makes pos_class, relief_share,
    relief_coverage and pos_rate point-in-time. Without it a 1995 cutoff would
    still know how a pitcher's career ENDED: relief_share is a career quantity
    and a starter who finished in the bullpen would file as an RP at a cutoff
    where he had never relieved.
    """
    b = stint_frame("bat", offline=offline)
    p = stint_frame("pit", offline=offline)
    if season_cutoff is not None:
        cut = int(season_cutoff)
        b = b[pd.to_numeric(b["year_ID"], errors="coerce") <= cut]
        p = p[pd.to_numeric(p["year_ID"], errors="coerce") <= cut]
    bg = b.groupby("player_ID").agg(
        pa=("PA", "sum"),
        runs_position=("runs_position", "sum"),
        runs_catcher=("runs_catcher", "sum"),
        runs_infield=("runs_infield", "sum"),
        runs_outfield=("runs_outfield", "sum"),
        bat_war=("WAR", "sum"),
    )
    pit = p.copy()
    rel = pd.to_numeric(pit["IPouts_relief"], errors="coerce")
    start = pd.to_numeric(pit["IPouts_start"], errors="coerce")
    outs = pd.to_numeric(pit["IPouts"], errors="coerce")
    # IPouts_relief is null on 32 percent of 1920-1949 pitcher-seasons and on
    # 81 percent before 1900; IPouts - IPouts_start recovers some of them.
    pit["_rel"] = rel.fillna(outs - start)
    pit["_known"] = pit["_rel"].notna().astype(float) * outs.fillna(0.0)
    pg = pit.groupby("player_ID").agg(
        ipouts=("IPouts", "sum"),
        ipouts_relief=("_rel", "sum"),
        ipouts_relief_known=("_known", "sum"),
        gs=("GS", "sum"),
        g=("G", "sum"),
        pit_war=("WAR", "sum"),
    )
    j = bg.join(pg, how="outer")
    for c in j.columns:
        j[c] = pd.to_numeric(j[c], errors="coerce").fillna(0.0)
    pa = j["pa"].values
    j["pos_rate"] = np.where(
        pa > 0, j["runs_position"].values / np.where(pa > 0, pa, 1.0) * 650.0,
        np.nan)
    ip = j["ipouts"].values
    safe_ip = np.where(ip > 0, ip, 1.0)
    j["relief_share"] = np.where(
        ip > 0, j["ipouts_relief"].values / safe_ip, np.nan)
    j["relief_coverage"] = np.where(
        ip > 0, j["ipouts_relief_known"].values / safe_ip, np.nan)
    return j


def position_class(row) -> tuple[str, str]:
    """(class, basis) for one row of _position_inputs.

    basis is 'fielding_components' when runs_catcher / runs_infield /
    runs_outfield carry a signal (1953 and later), 'positional_rate' when they
    do not, and 'pitching' for pitchers. Read POSITION_CLASS_NOTE before
    trusting a 'positional_rate' row: catchers are unrecoverable on that basis.

    Pitcher first: PITCHER_MIN_IPOUTS or more career outs AND more pitching
    exposure than batting exposure, on the PITCH_SEASON_OUTS / BAT_SEASON_PA
    scale. Babe Ruth clears the outs test (3,664 outs, 6.11 pitching seasons)
    and fails the exposure test (10,625 PA, 16.35 batting seasons), so he
    files as a fielder, which is where Baseball-Reference's own JAWS puts him.
    Walter Johnson (29.58 against 3.90) and Mariano Rivera (6.42 against 0.01)
    file as pitchers."""
    ipouts = float(row.ipouts or 0.0)
    pa = float(row.pa or 0.0)
    if (ipouts >= PITCHER_MIN_IPOUTS
            and ipouts / PITCH_SEASON_OUTS > pa / BAT_SEASON_PA):
        share = row.relief_share
        if share is None or (isinstance(share, float) and math.isnan(share)):
            return ("SP", "pitching")
        return (("RP" if float(share) >= RELIEF_SHARE_RP else "SP"),
                "pitching")

    rate = row.pos_rate
    have_rate = rate is not None and not math.isnan(float(rate))
    rc = abs(float(row.runs_catcher or 0.0))
    rif = abs(float(row.runs_infield or 0.0))
    rof = abs(float(row.runs_outfield or 0.0))
    if max(rc, rif, rof) > 0.0:
        if rc >= rif and rc >= rof:
            return ("C", "fielding_components")
        if rof > rif:
            return ("OF", "fielding_components")
        if have_rate and float(rate) >= MI_RATE_CUT:
            return ("MI", "fielding_components")
        return ("1B/DH", "fielding_components")

    if not have_rate:
        return ("1B/DH", "positional_rate")
    r = float(rate)
    if r >= MI_RATE_CUT:
        return ("MI", "positional_rate")
    if r < CORNER_RATE_CUT:
        return ("1B/DH", "positional_rate")
    return ("OF", "positional_rate")


# ---------------------------------------------------------------------------
# The career frame.
# ---------------------------------------------------------------------------

def current_year() -> int:
    return _dt.date.today().year


def career_frame(*, offline: bool = False,
                 as_of_year=None, season_cutoff=None) -> pd.DataFrame:
    """One row per bbref player_ID. The shelf.

    `as_of_year` GATES ELIGIBILITY AND NOTHING ELSE. `season_cutoff` is the one
    that makes the FEATURES point-in-time: it drops every season after that year
    before any aggregation, so a call at 1995 sees the career as it stood in
    1995. Ask for `as_of_year=1995` alone and you still get Barry Bonds at 162.8
    career WAR, which is correct for a shelf and useless for a predictor. See
    `as_of` below.

    Columns
      player_ID, name, first_season, last_season, n_seasons
      career_war, war7, jaws, career_waa, waa_pos, ink
      pos_class, pos_basis, relief_share, relief_coverage, pos_rate
      pa, ipouts, bat_war, pit_war
      ngl_seasons, ngl_share, historical_major_seasons, era_factor
      eligible, seasons (list of (year, war) tuples, ascending)

    ELIGIBLE UNIVERSE E: n_seasons at or above MIN_SEASONS and last_season at
    or before as_of_year - ELIGIBILITY_LAG_YEARS. Measured at as_of_year 2026:
    3,620 players out of the 23,786 with any WAR row. Their career WAR runs
    -6.88 to 182.62, median 14.70, mean 20.32.

    'A season' means a season with a WAR row on either side, not a season with
    a plate appearance. The two differ for a designated-hitter-era pitcher.
    """
    year = int(as_of_year or current_year())
    cut = None if season_cutoff is None else int(season_cutoff)
    # THE CUTOFF IS PART OF THE CACHE KEY. Without it the first full-career call
    # poisons every point-in-time call after it, returning a 2026 career for a
    # 1995 question with no error anywhere. That is the leak that would have been
    # hardest to see, because the frame it hands back is perfectly well formed.
    key = (bool(offline), year, cut)
    hit = _CAREER_CACHE.get(key)
    if hit is not None:
        return hit.copy()

    seasons = season_frame(offline=offline)
    if cut is not None:
        seasons = seasons[pd.to_numeric(seasons["year_ID"], errors="coerce") <= cut]
    g = seasons.groupby("player_ID")
    out = g.agg(
        name=("name", "last"),
        first_season=("year_ID", "min"),
        last_season=("year_ID", "max"),
        n_seasons=("year_ID", "size"),
        career_war=("war", "sum"),
        career_waa=("waa", "sum"),
        bat_war=("bat_war", "sum"),
        pit_war=("pit_war", "sum"),
        pa=("pa", "sum"),
        ipouts=("ipouts", "sum"),
    )
    out["war7"] = g["war"].apply(lambda s: war7(s.values))
    out["waa_pos"] = g["waa"].apply(lambda s: positive_waa(s.values))
    out["jaws"] = (out["career_war"] + out["war7"]) / 2.0
    out["ink"] = war_ink(seasons).reindex(out.index).fillna(0.0)

    srt = seasons.sort_values(["player_ID", "year_ID"], kind="mergesort")
    out["seasons"] = (srt.assign(_t=list(zip(srt["year_ID"].astype(int),
                                             srt["war"].astype(float))))
                        .groupby("player_ID")["_t"].apply(list)
                        .reindex(out.index))

    out["ngl_seasons"] = (
        seasons.assign(_n=seasons["lg_ID"].isin(NEGRO_LEAGUES).astype(int))
        .groupby("player_ID")["_n"].sum().reindex(out.index).fillna(0)
        .astype(int))
    out["historical_major_seasons"] = (
        seasons.assign(
            _h=seasons["lg_ID"].isin(OTHER_HISTORICAL_MAJORS).astype(int))
        .groupby("player_ID")["_h"].sum().reindex(out.index).fillna(0)
        .astype(int))
    out["ngl_share"] = out["ngl_seasons"] / out["n_seasons"]
    out["era_factor"] = era_factor(seasons, offline=offline).reindex(out.index)

    pos = _position_inputs(offline=offline,
                           season_cutoff=cut).reindex(out.index)
    cls = [position_class(r) for r in pos.itertuples()]
    out["pos_class"] = [c for c, _ in cls]
    out["pos_basis"] = [b for _, b in cls]
    out["pos_rate"] = pos["pos_rate"]
    out["relief_share"] = pos["relief_share"]
    out["relief_coverage"] = pos["relief_coverage"]

    out["eligible"] = ((out["n_seasons"] >= MIN_SEASONS)
                       & (out["last_season"] <= year - ELIGIBILITY_LAG_YEARS))
    out = out.reset_index()
    _CAREER_CACHE[key] = out
    return out.copy()


def as_of(player_id: str, cutoff: int, *, offline: bool = False):
    """H-PRED-2. This player's shelf row AS IT STOOD at `cutoff`, or None.

    Strictly seasons at or before `cutoff`, on every feature: career WAR, WAR7,
    JAWS, WAA, positive-WAA sum, WAR ink, exposure, position class and the era
    columns. A player with no season at or before the cutoff returns None rather
    than a row of zeros, because "had not played yet" and "played and was worth
    nothing" are different statements and a model must not be handed the second
    when the first is true.

    THE POINT-IN-TIME PROPERTY, which is what makes this worth having: this
    returns the same row as running the unparameterised frame over inputs
    physically truncated at `cutoff`. test_hof_point_in_time pins that by
    truncating independently rather than by trusting the parameter.

    Two things it deliberately does NOT do. It does not gate eligibility, which
    is `as_of_year`'s job and a separate question. And it does not pretend the
    ballot is knowable: a merit feature frame says what a career looked like,
    not what the writers were about to do with it.

    POS_CLASS IS UNSTABLE EARLY, and a model reading it has to know. The
    classifier requires PITCHER_MIN_IPOUTS (900) career outs before it will call
    anyone a pitcher, so at an early cutoff a real pitcher with thin exposure
    files as a FIELDER: Mariano Rivera at a 1996 cutoff has 524 outs and comes
    back "1B/DH". Measured against the full frame: at a 1995 cutoff 166 players
    (6.6% of the full frame's pitchers) are not yet classed as pitchers, and 7
    of the 2,358 that are move between SP and RP; at 2005 it is 147 (5.1%) and
    12 of 2,738. That is the threshold working, not a truncation defect, and it
    is the honest content of a point-in-time answer: at that date the exposure
    to decide was not there yet. Do not read an early pos_class as a claim about
    what the player turned out to be.
    """
    cf = career_frame(offline=offline, as_of_year=int(cutoff),
                      season_cutoff=int(cutoff))
    hit = cf[cf["player_ID"] == player_id]
    if not len(hit):
        return None
    return hit.iloc[0]


def eligible_universe(*, offline: bool = False,
                      as_of_year=None) -> pd.DataFrame:
    """E. career_frame filtered to eligible."""
    cf = career_frame(offline=offline, as_of_year=as_of_year)
    return cf[cf["eligible"]].reset_index(drop=True)


# ---------------------------------------------------------------------------
# The reproduction control. If this fails, nothing downstream is worth reading.
# ---------------------------------------------------------------------------

REPRODUCTION_TARGETS: dict = {
    # bbref id: (name, career WAR, WAR7, JAWS) as Baseball-Reference publishes
    # them. Two-way totals, tenths, half-up.
    "ruthba01":  ("Babe Ruth", 182.6, 84.4, 133.5),
    "johnswa01": ("Walter Johnson", 168.4, 92.0, 130.2),
    "youngcy01": ("Cy Young", 163.6, 78.0, 120.8),
    "bondsba01": ("Barry Bonds", 162.8, 72.7, 117.7),
    "mayswi01":  ("Willie Mays", 156.2, 73.6, 114.9),
}


def reproduction_check(*, offline: bool = False,
                       as_of_year=None) -> pd.DataFrame:
    """The acceptance test for the whole shelf, as a frame a human can read.

    Columns: player_ID, name, career_war / war7 / jaws (this module, half-up
    to the tenth), the same three columns suffixed _pub (Baseball-Reference),
    and ok. Every row must be ok."""
    cf = career_frame(offline=offline,
                      as_of_year=as_of_year).set_index("player_ID")
    rows = []
    for pid, (name, car, w7, jw) in REPRODUCTION_TARGETS.items():
        if pid not in cf.index:
            rows.append({"player_ID": pid, "name": name, "career_war": None,
                         "war7": None, "jaws": None, "career_war_pub": car,
                         "war7_pub": w7, "jaws_pub": jw, "ok": False})
            continue
        r = cf.loc[pid]
        got = (round_half_up(r["career_war"]), round_half_up(r["war7"]),
               round_half_up(r["jaws"]))
        rows.append({
            "player_ID": pid, "name": name,
            "career_war": got[0], "war7": got[1], "jaws": got[2],
            "career_war_pub": car, "war7_pub": w7, "jaws_pub": jw,
            "ok": got == (car, w7, jw),
        })
    return pd.DataFrame(rows)


#: The committed, dated record of the acceptance test above, and the registered
#: eval artifact for `hof_benchmark_shelf`.
#:
#: WHY IT IS WRITTEN AT ALL. The reproduction check is the only thing standing
#: between this shelf and a plausible-looking set of numbers. JAWS, WAR7 and
#: career WAR all have published values for every player, so a reimplementation
#: that is subtly wrong (a wrong replacement level, seasons counted by games
#: rather than by WAR rank, a pitcher/batter WAR that double-counts a two-way
#: season) produces a frame that looks entirely reasonable and disagrees with
#: Baseball-Reference in the third significant figure. Running the check in
#: process and printing PASS leaves no record; a reader six months from now
#: cannot tell whether it ever ran, on which players, or against which
#: published values.
REPRO_ARTIFACT_PATH = ROOT / "data" / "hof_benchmark_repro.json"


def write_reproduction_artifact(*, offline: bool = True, as_of_year=None,
                                out: Path | None = None) -> dict:
    """Run the acceptance test and commit the result, with its date.

    `offline=True` by default: the check must be reproducible from the cached
    WAR frame alone, and a producer that silently reaches the network would make
    the artifact a record of today's Baseball-Reference rather than of this
    code."""
    df = reproduction_check(offline=offline, as_of_year=as_of_year)
    recs = df.to_dict(orient="records")
    n_ok = sum(1 for r in recs if r.get("ok"))
    art = {
        "generated_at": _dt.datetime.now(_dt.timezone.utc)
                        .replace(microsecond=0).isoformat(),
        "n_targets": len(recs),
        "n_exact": n_ok,
        # Say both numbers. "15 of 15" is the comparison count (three published
        # figures per player) and reads as a much larger check than it is; the
        # PLAYER count is five, and five is the number that bounds what this
        # check can catch. A reader given only the 15 would overrate it.
        "n_players": len(recs),
        "n_comparisons": 3 * len(recs),
        "n_comparisons_exact": sum(
            (1 if r.get("career_war") == r.get("career_war_pub") else 0)
            + (1 if r.get("war7") == r.get("war7_pub") else 0)
            + (1 if r.get("jaws") == r.get("jaws_pub") else 0)
            for r in recs),
        "all_exact": n_ok == len(recs) and len(recs) > 0,
        "offline": bool(offline),
        "as_of_year": as_of_year,
        "tolerance": ("EXACT after half-up rounding to one decimal. Not a "
                      "tolerance band: these three numbers are published to the "
                      "tenth, so anything short of agreement to the tenth means "
                      "the reimplementation differs and the difference has not "
                      "been explained."),
        "baseline": ("Baseball-Reference published career WAR, WAR7 and JAWS, "
                     "transcribed into REPRODUCTION_TARGETS"),
        "rows": recs,
        "what_this_does_not_show": (
            "agreement on the benchmark shelf, and nothing about whether the "
            "shelf predicts induction. It is a correctness check on a "
            "reimplementation, not evidence for any Hall of Fame claim."),
    }
    dest = Path(out) if out is not None else REPRO_ARTIFACT_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(art, indent=1, default=str) + chr(10),
                    encoding="utf-8")
    return art


# ---------------------------------------------------------------------------
# The Hall-sized line.
# ---------------------------------------------------------------------------

@dataclass
class HallLine:
    """What the frame can say about a class WITHOUT the ballot source.

    ``line`` is the JAWS threshold that admits exactly ``n_enshrined`` players
    from the eligible universe of this class. It is None until a caller
    supplies that count, because this module does not know who is in the Hall
    and will not guess. When the ballot source lands, n_enshrined comes from
    label_any and this becomes the real Hall-sized line."""
    cls: str
    n_eligible: int
    n_rate_basis: int
    quantiles: dict
    median_jaws: float
    line: float = None
    n_enshrined: int = None
    reason: str = ""
    above_line: tuple = field(default_factory=tuple)


def hall_line(cls: str, *, n_enshrined=None, offline: bool = False,
              as_of_year=None) -> HallLine:
    """The Hall-sized line for one position class.

    Relievers are split from starters at RELIEF_SHARE_RP (0.70 of career relief
    outs). WHERE THE DATA SUPPORTS IT, and it does not always: IPouts_relief is
    null on 32 percent of 1920-1949 pitcher-seasons and on 81 percent of
    pre-1900 seasons. This module fills the gap with IPouts - IPouts_start
    where IPouts_start is present, and reports what is left as
    relief_coverage on every pitcher row. A pitcher whose relief_coverage is
    low is a starter by default, because the fallback cannot invent relief
    innings it has no record of. MEASURED over the 1,363 pitchers in the
    eligible universe: mean relief_coverage 0.939, 92.7 percent of them fully
    covered, 6.8 percent below 0.9. The split then puts 306 in RP and 1,057 in
    SP, and the RP relief shares run 0.700 to 1.000 with a median of 0.971, so
    the class is not sitting on the threshold.

    n_rate_basis counts the members of the class whose position was inferred
    from the positional-adjustment rate alone. Read POSITION_CLASS_NOTE: for
    the C class that count is structurally zero (no pre-1953 catcher can be
    found), and for MI it is inflated by exactly those missing catchers."""
    if cls not in CLASSES:
        raise ValueError(f"class must be one of {CLASSES}, got {cls!r}")
    E = eligible_universe(offline=offline, as_of_year=as_of_year)
    sub = E[E["pos_class"] == cls]
    qs = ({q: float(sub["jaws"].quantile(q))
           for q in (0.50, 0.75, 0.90, 0.95, 0.99)} if len(sub) else {})
    hl = HallLine(
        cls=cls,
        n_eligible=int(len(sub)),
        n_rate_basis=int((sub["pos_basis"] == "positional_rate").sum()),
        quantiles=qs,
        median_jaws=float(sub["jaws"].median()) if len(sub) else float("nan"),
    )
    if n_enshrined is None:
        hl.reason = (
            "line=None: the Hall-sized line needs the count of players "
            "inducted AS PLAYERS at this class, and that is not known. The "
            f"ballot source ({BALLOT_SOURCE}) IS built, but it records which "
            "electorate voted and not what the plaque says, so managers and "
            "executives who also played cannot be separated out. Pass "
            "n_enshrined from outside, or wait for H-DATA-PLAQUE.")
        return hl
    n = int(n_enshrined)
    if n <= 0 or n > len(sub):
        raise ValueError(
            f"n_enshrined={n} is outside the {len(sub)} eligible {cls} "
            "players")
    top = sub.nlargest(n, "jaws")
    hl.n_enshrined = n
    hl.line = float(top["jaws"].min())
    hl.above_line = tuple(top["name"].astype(str).tolist())
    hl.reason = (
        f"line is the {n}th best JAWS among {len(sub)} eligible {cls} "
        "players, so it is Hall-SIZED by construction and says nothing about "
        "who the voters actually chose.")
    return hl


# ---------------------------------------------------------------------------
# The label contract (H-PRED-1).
# ---------------------------------------------------------------------------
#
# TWO LABELS, and the resolution rules are these. The ballot source IS built,
# so the code below runs them; this block is the contract they implement.
#
# L_bbwaa (PRIMARY). Elected by the Baseball Writers' Association of America
#   inside the player's OWN ballot window.
#     1 : the player appears on a BBWAA ballot and is elected on it.
#     0 : the player's BBWAA window is CLOSED without election. A window closes
#         three ways, and all three count as a resolved zero:
#           a. the player falls below the five percent retention threshold and
#              drops off;
#           b. the player exhausts the ballot (ten years since 2015, fifteen
#              before, with the 2014 transition rule for players already on);
#           c. the player was never placed on a ballot at all despite clearing
#              rule 3B, which the screening committee resolves.
#     CENSORED (None) : the window is still open. On the ballot with years
#         left, or eligible and not yet balloted. NEVER 0.
#   Veterans committee election does NOT set L_bbwaa to 1. It is a different
#   electorate answering a different question, and folding it in would teach
#   the model that the writers elected people the writers rejected.
#
# L_any (SECONDARY, the owner's amended decision 12). Inducted by ANY route.
#     1 : inducted as a player, BBWAA or any veterans or special committee.
#     0 : the player is dead or otherwise past every committee window and was
#         never inducted. In practice the era-committee route never fully
#         closes for a living player, so a resolved 0 on this label is a
#         judgement about committee windows, not a fact, and the label ships
#         with the censoring sensitivity table the plan asks for.
#     CENSORED (None) : any committee window still open.
#   Executives, managers, umpires and Negro Leagues pioneers inducted as
#   contributors SHOULD NOT be L_any=1 as players. THAT IS THE INTENT AND IT IS
#   NOT IMPLEMENTED, because the second half of the old sentence here, that the
#   route field separates them, is FALSE. `route` is the ELECTORATE that voted
#   (BBWAA 137, VETERANS 147, UNKNOWN 70) and `route_note` is non-null on 21 of
#   354 rows and encodes no role. No field in the source names the plaque.
#
#   So until H-DATA-PLAQUE lands, L_any means INDUCTED BY ANY ROUTE, PLAQUE ROLE
#   UNVERIFIED. The unverified set is published in data/hof_ledger_eval.json and
#   the ledger repair makes it LARGER, not smaller, because the players it
#   recovers include managers who also played. Nothing downstream may publish a
#   Hall-sized line, a snub list or a deserved-versus-inducted verdict off this
#   label while that is true.
#
# THE INVARIANT: a censored player never carries a zero. Pinned by
# assert_no_censored_zero and by test_hof_data.


#: How many years the writers' ballot runs. Ten since the 2014 rule change,
#: fifteen before it. This is a FALLBACK ONLY: `bbwaa_window_close_year` infers
#: the window from the panel itself (a candidate appears every year until he is
#: resolved, so vanishing from the ballot IS the resolution), and the counts here
#: are consulted only when the panel ends mid-window and that inference cannot be
#: made. Counting appearances against a rule was the first implementation and it
#: was wrong: the 2014 change shortened the window for players already on the
#: ballot too, so a fifteen-year count left Barry Bonds censored.
BBWAA_WINDOW_YEARS_MODERN = 10
BBWAA_WINDOW_YEARS_LEGACY = 15
BBWAA_WINDOW_RULE_CHANGE_YEAR = 2015

#: THE COMMITTEE HORIZON, and it is a MODELLING ASSUMPTION rather than a fact.
#:
#: The writers' ballot closes. The era and veterans committees never formally do:
#: they have elected players fifty and sixty years after retirement, and on a
#: strict reading no non-inducted player is EVER a resolved zero for the
#: any-route label. A strict reading also makes the label useless, because the
#: negative class would be empty.
#:
#: So a player is scored zero for L_any only once this many years have passed
#: since his writers' window closed, and censored before that. The default is 25.
#: It is arbitrary, it is stated, and `label_sensitivity()` publishes how many
#: labels flip at 15, 20, 25, 30 and 40 so a reader can see what it costs.
COMMITTEE_HORIZON_YEARS = 25


def _load_ballots(path=None, *, crosswalk=None) -> dict:
    """The ballot panel, indexed for lookup. Raises BallotSourceMissing when the
    artifact is absent, which is still the honest answer on a fresh checkout."""
    p = Path(path or (ROOT / BALLOT_SOURCE))
    if not p.exists():
        raise BallotSourceMissing(
            f"the ballot panel {BALLOT_SOURCE} does not exist. Build it with "
            "`python tools/hof_ballot_ingest.py` (plan lane H-DATA-2). It is "
            "NOT optional and must not be replaced by a hand-typed membership "
            "list: that would be an unversioned answer key silently training "
            "the merit model.")
    doc = json.loads(p.read_text(encoding="utf-8"))
    by_pid: dict = {}
    for r in doc.get("rows") or []:
        pid = r.get("player_id")
        if pid:
            by_pid.setdefault(pid, []).append(r)
    inducted: dict = {}
    unresolved: list = []
    for r in doc.get("statsapi_inductees") or []:
        pid = r.get("player_id")
        if pid:
            inducted[pid] = r
        else:
            unresolved.append(r)
    n_from_ingest = len(inducted)

    # THE REPAIR. An inductee StatsAPI named by MLBAM id but the ingest could not
    # bridge to a bbref id was dropped from the ledger entirely, and the label
    # layer then reported him as not in the Hall. Both war_daily parquets carry
    # both ids, so the bridge is on disk; `crosswalk={}` reproduces the
    # unrepaired ledger for the before-and-after receipt.
    xwalk = crosswalk_bbref_mlbam() if crosswalk is None else dict(crosswalk)
    n_from_xwalk = 0
    still: list = []
    for r in unresolved:
        pid = xwalk.get(str(r.get("mlbam_id")))
        if pid and pid not in inducted:
            inducted[pid] = {**r, "player_id": pid,
                             "route_source": "war_daily mlbam crosswalk"}
            n_from_xwalk += 1
        elif not pid:
            still.append(r)
    # A player elected by the writers appears in the ballot table with
    # elected=True; that is an induction too, and StatsAPI's ids do not resolve
    # for everyone, so both sources feed the any-route ledger.
    for pid, rows in by_pid.items():
        if pid in inducted:
            continue
        won = [r for r in rows if r.get("elected")]
        if won:
            inducted[pid] = {"player_id": pid, "route": "BBWAA",
                             "election_year": min(r["election_year"] for r in won),
                             "route_source": "ballot table, elected"}
    # PLAQUE ROLE IS NOT KNOWN AND THE REPAIR MAKES THAT WORSE, not better. The
    # source records which ELECTORATE voted, never what the plaque says, so an
    # inductee who played and was later enshrined as a manager reads as a player
    # induction. Connie Mack, Casey Stengel, Bucky Harris, Al Lopez and Billy
    # Southworth all enter the eligible universe this way. Naming them is the
    # only honest thing available until H-DATA-PLAQUE lands, and it is why no
    # Hall-sized line and no snub list may be published from this ledger.
    unverified = []
    for pid, r in inducted.items():
        route = (r.get("route") or "").upper()
        won_ballot = any(x.get("elected") for x in by_pid.get(pid) or [])
        if not won_ballot and route != "BBWAA":
            unverified.append({"player_id": pid,
                               "name": r.get("player_name"),
                               "election_year": r.get("election_year"),
                               "route": r.get("route")})
    return {
        "by_pid": by_pid, "inducted": inducted, "doc": doc,
        "resolution": {
            "from_ballot_tables": n_from_ingest,
            "from_mlbam_crosswalk": n_from_xwalk,
            "unresolved": len(still),
            "unresolved_names": sorted(x.get("player_name") or "" for x in still),
            "crosswalk_available": bool(xwalk),
            "crosswalk_pairs": len(xwalk),
            "plaque_role_unverified": sorted(unverified,
                                             key=lambda x: (x["name"] or "")),
            "what_the_unresolved_are": (
                "overwhelmingly people who never played: managers, executives, "
                "commissioners, union leaders, umpires and Negro Leagues "
                "pioneers. A crosswalk built from playing records cannot find "
                "them and should not: they have no player record to find. That "
                "is why the residual is reported rather than chased."),
        },
    }


_BALLOT_CACHE: dict = {}


def ballots(path=None, *, crosswalk=None) -> dict:
    """The ballot panel, memoised.

    THE CACHE KEY INCLUDES THE CROSSWALK. It used to be the path alone while
    `crosswalk` changes the result, so inside one process the first call won and
    the label layer became call-order dependent: a test that read the unrepaired
    ledger first would then get it back from a call that asked for the repaired
    one.
    """
    key = (str(path or ""), None if crosswalk is None else tuple(sorted(crosswalk)))
    if key not in _BALLOT_CACHE:
        _BALLOT_CACHE[key] = _load_ballots(path, crosswalk=crosswalk)
    return _BALLOT_CACHE[key]


def _window_years(first_year: int) -> int:
    return (BBWAA_WINDOW_YEARS_MODERN
            if int(first_year) >= BBWAA_WINDOW_RULE_CHANGE_YEAR
            else BBWAA_WINDOW_YEARS_LEGACY)


def _panel_last_election(b: dict) -> int | None:
    """The most recent BBWAA election year the panel covers."""
    yrs = [r["election_year"] for rows in b["by_pid"].values() for r in rows
           if r["route"] == "BBWAA"]
    return max(yrs) if yrs else None


def bbwaa_window_close_year(player_id: str, *, ballots_=None) -> int | None:
    """The year the writers' window closed for this player, or None if it is
    still open or he never appeared.

    THE WINDOW IS INFERRED FROM THE PANEL, NOT FROM A RULE, and the first
    version got that wrong. It counted appearances against a fifteen-year window
    for anybody whose first ballot predated the 2015 rule change, which is not
    what happened: the change shortened the window for players ALREADY on the
    ballot too, with three named exceptions. Barry Bonds, who appeared ten times
    from 2013 to 2022 and was never elected, came back CENSORED under that rule
    when he is the most-discussed resolved non-inductee in the game.

    The panel already knows the answer without any rule at all. A candidate
    stays on the ballot every year until he is resolved, so a player whose LAST
    appearance is before the panel's most recent election, and who was neither
    elected nor recorded as falling under five percent, has left the ballot. The
    year he left it is the year his window closed.
    """
    b = ballots_ or ballots()
    rows = [r for r in b["by_pid"].get(player_id, []) if r["route"] == "BBWAA"]
    if not rows:
        return None
    if any(r.get("elected") for r in rows):
        return min(r["election_year"] for r in rows if r.get("elected"))
    if any(r.get("dropped_off") for r in rows):
        return min(r["election_year"] for r in rows if r.get("dropped_off"))
    last = max(r["election_year"] for r in rows)
    latest = _panel_last_election(b)
    if latest is not None and last < latest:
        return last
    # He is on the most recent ballot the panel covers, so the window is open.
    # The appearance count is kept as a second check for a panel that ends
    # mid-window, where "did not appear last year" cannot be observed.
    first = min(r["election_year"] for r in rows)
    nums = [r.get("ballot_number") for r in rows if r.get("ballot_number")]
    if nums and max(nums) >= _window_years(first):
        return last
    return None


def label_bbwaa(player_id: str, *, as_of_year=None, ballots_=None,
                ballots=None):
    """L_bbwaa for one bbref player_ID. Returns 1, 0 or CENSORED (None).

    RESOLVED BY THREE ROUTES, and only these: elected, fell under five percent,
    or exhausted the ballot. A player still inside his window is CENSORED and
    NEVER zero, because a zero there says the writers decided no about somebody
    they have not finished deciding on, and it does that hardest to the best
    recent candidates.

    A player who NEVER APPEARED on a ballot is also censored, not zero. The
    screening committee's decision not to list somebody is a different event
    from the writers voting him down, this panel cannot tell one from the other,
    and treating absence as rejection would silently label thousands of
    marginal players as considered-and-refused.
    """
    b = ballots_ or (ballots if isinstance(ballots, dict) else None) or globals()["ballots"]()
    year = int(as_of_year or current_year())
    rows = [r for r in b["by_pid"].get(player_id, [])
            if r["route"] == "BBWAA" and r["election_year"] <= year]
    if not rows:
        return CENSORED
    if any(r.get("elected") for r in rows):
        return 1
    close = bbwaa_window_close_year(player_id, ballots_=b)
    if close is not None and close <= year:
        return 0
    return CENSORED


def label_any(player_id: str, *, as_of_year=None, ballots_=None, ballots=None,
              horizon_years: int | None = None):
    """L_any for one bbref player_ID. Returns 1, 0 or CENSORED (None).

    Induction by ANY route is the primary label (owner decision 12, 2026-09-06),
    because it matches who is actually in the Hall, which is the honest target
    for a question phrased as "who belongs".

    THE ZERO IS THE HARD PART. The committees never formally close, so a strict
    reading censors every non-inductee forever and leaves the negative class
    empty. `COMMITTEE_HORIZON_YEARS` is the stated assumption that closes it:
    zero only once that many years have passed since the writers' window shut.
    `label_sensitivity()` publishes what other horizons would do.
    """
    b = ballots_ or (ballots if isinstance(ballots, dict) else None) or globals()["ballots"]()
    year = int(as_of_year or current_year())
    h = COMMITTEE_HORIZON_YEARS if horizon_years is None else int(horizon_years)
    ind = b["inducted"].get(player_id)
    if ind and int(ind.get("election_year") or 9999) <= year:
        return 1
    close = bbwaa_window_close_year(player_id, ballots_=b)
    if close is None:
        return CENSORED
    return 0 if (year - close) >= h else CENSORED


def label_frame(*, offline: bool = False, as_of_year=None, ballots_=None):
    """The eligible universe joined to both labels.

    Returns the feature half with `label_bbwaa`, `label_any`, `censored_bbwaa`
    and `censored_any` columns. `assert_no_censored_zero` is run over the result
    before it is returned.

    A CENSORED ROW IS NaN IN THE FRAME, NOT None. The label lists are built as
    python objects containing None and pandas coerces them to float64 NaN on
    assignment. The dtype is deliberately left alone, because a nullable
    integer column would change what every downstream comparison means. The
    trap that follows from it is that `bool(nan) is True`, so a caller writing
    `if row.label_any:` treats every censored player as an inductee. Test for
    the label with `== 1`, `== 0` or `.isna()`, never for truthiness.
    """
    b = ballots_ or ballots()
    uni = eligible_universe(offline=offline, as_of_year=as_of_year)
    yr = int(as_of_year or current_year())
    lb = [label_bbwaa(pid, as_of_year=yr, ballots_=b) for pid in uni["player_ID"]]
    la = [label_any(pid, as_of_year=yr, ballots_=b) for pid in uni["player_ID"]]
    out = uni.copy()
    out["label_bbwaa"] = lb
    out["label_any"] = la
    out["censored_bbwaa"] = [v is CENSORED for v in lb]
    out["censored_any"] = [v is CENSORED for v in la]
    assert_no_censored_zero(
        [{"player_id": pid, "label": v, "censored": c}
         for pid, v, c in zip(out["player_ID"], lb, out["censored_bbwaa"])])
    assert_no_censored_zero(
        [{"player_id": pid, "label": v, "censored": c}
         for pid, v, c in zip(out["player_ID"], la, out["censored_any"])])
    return out


def label_sensitivity(*, offline: bool = False, as_of_year=None,
                      horizons=(15, 20, 25, 30, 40)) -> dict:
    """What the committee horizon costs, published rather than argued.

    The horizon is the one arbitrary constant in the label. This reports how
    many players are positive, negative and censored at each candidate value, so
    a reader can see whether a result depends on it.
    """
    b = ballots()
    uni = eligible_universe(offline=offline, as_of_year=as_of_year)
    yr = int(as_of_year or current_year())
    out = {}
    for h in horizons:
        vals = [label_any(pid, as_of_year=yr, ballots_=b, horizon_years=h)
                for pid in uni["player_ID"]]
        out[str(h)] = {
            "positive": sum(1 for v in vals if v == 1),
            "negative": sum(1 for v in vals if v == 0),
            "censored": sum(1 for v in vals if v is CENSORED),
        }
    return {
        "as_of_year": yr,
        "default_horizon_years": COMMITTEE_HORIZON_YEARS,
        "by_horizon": out,
        "what_the_horizon_is": (
            "a MODELLING ASSUMPTION, not a fact. The writers' ballot closes; the "
            "era and veterans committees never formally do, and they have "
            "elected players fifty years after retirement. On a strict reading "
            "no non-inducted player is ever a resolved zero for the any-route "
            "label and the negative class is empty. The horizon closes it, and "
            "this table is what it costs."),
    }


BBWAA_DROP_RULE_FIRST_YEAR = 1979
"""The five percent retention rule began in 1979.

`tools/hof_ballot_ingest.py` applies `vote_pct < 0.05` as a dropped-off flag all
the way back to 1936, where no such rule existed. MEASURED 2026-09-06: 307
players carry an earliest dropped-off year that PRECEDES their last real BBWAA
appearance, by up to thirty years. Any fold keyed on that year is not a forward
chain, because it claims the writers' verdict was observable years before the
writers had finished voting on him.

`bbwaa_window_close_year` is deliberately NOT changed. It is shipped, its output
feeds `label_bbwaa` and `label_any`, and moving it would move labels. The
correction lives in `resolution_year`, which is new and which nothing serves.
"""

RESOLUTION_ROUTES = ("elected", "dropped_off", "left_ballot",
                     "inducted_never_balloted", "committee_horizon")
"""How a player's label became observable.

`exhausted` is deliberately ABSENT even though it is a real route. Separating a
player who used up his ballot eligibility from one who simply stopped appearing
needs the era-varying ballot cap, which went from fifteen years to ten in 2014
and was different again before 1962. We do not have that table, and a route that
silently mixed two mechanisms would be worse than one honest `left_ballot`.
"""


def _bbwaa_panel_years(b: dict) -> list:
    """Every year the WRITERS actually voted, ascending.

    NOT the ingest's `years_with_no_election`, which lists five years. The
    writers also voted only every other year from 1956 to 1966 while the
    committees kept meeting, so on the BBWAA panel there are TEN empty years:
    1940, 1941, 1943, 1944, 1946, 1957, 1959, 1961, 1963 and 1965. A route that
    resolved at `last + 1` could therefore name a year in which no verdict could
    possibly have been observed.
    """
    ys = {r.get("election_year") for r in (b.get("doc") or {}).get("rows") or []
          if (r.get("route") or "").upper() == "BBWAA" and r.get("election_year")}
    return sorted(int(y) for y in ys if y)


def _dropped_off_at(bb_rows, year: int) -> bool:
    """Did a drop flag on `year` actually END this candidacy?

    TWO CONDITIONS, and the second was found by a test rather than reasoned out.

    (a) The election is at or after BBWAA_DROP_RULE_FIRST_YEAR. The five percent
        retention rule did not exist before 1979 and the ingest applies the flag
        back to 1936.

    (b) The flagged year is the player's LAST appearance. A flag on an earlier
        year did not end anything, because he came back. Measured: 88 non-elected
        players carry a drop flag on a year they went on to survive, and the
        1979 restriction alone does NOT catch them. Harvey Haddix is flagged in
        1979 and appears through 1985; Edd Roush is flagged in five separate
        years from 1936 and appears through 1960. Resolving either at his first
        flag would date his verdict years before the writers had finished with
        him, which is exactly the look-ahead this function exists to remove.
    """
    if int(year) < BBWAA_DROP_RULE_FIRST_YEAR:
        return False
    return any(r.get("dropped_off") and int(r["election_year"]) == int(year)
               for r in bb_rows)


def resolution_year(player_id: str, *, label: str = "bbwaa", ballots_=None):
    """The year this player's label became OBSERVABLE, or None if it has not.

    NOT `bbwaa_window_close_year`, and the differences are the point:

      (a) a dropped-off flag is honoured only for elections at or after
          BBWAA_DROP_RULE_FIRST_YEAR. Otherwise 307 players resolve decades
          before the writers were done with them.
      (b) the left-ballot route resolves at the next year the PANEL sat, strictly
          after his last appearance, not at that appearance and not at last + 1.
      (c) elected resolves at the first year he was elected, which matches
          `bbwaa_window_close_year` exactly.
      (d) label='any' adds `inducted_never_balloted` for an inductee with no
          BBWAA row at all.

    THE AS-OF IDENTITY WITH `label_frame` IS NOT GENERAL AND IS NOT CLAIMED. Two
    structural reasons, both published rather than argued away. Clause (b)
    deliberately disagrees with `label_bbwaa` at Y equal to the last appearance.
    And `label_any` is NON-MONOTONE in Y: it checks the induction ledger before
    the window close, so a player enshrined by a committee more than
    COMMITTEE_HORIZON_YEARS after his window closed reads a resolved zero for
    decades and then flips to one.
    """
    b = ballots_ if ballots_ is not None else ballots()
    rows = (b.get("by_pid") or {}).get(player_id) or []
    bb = [r for r in rows if (r.get("route") or "").upper() == "BBWAA"
          and r.get("election_year")]

    if label == "any":
        ind = (b.get("inducted") or {}).get(player_id)
        if ind is not None:
            y = ind.get("election_year")
            return int(y) if y else None
        base = resolution_year(player_id, label="bbwaa", ballots_=b)
        return None if base is None else int(base) + COMMITTEE_HORIZON_YEARS

    won = [int(r["election_year"]) for r in bb if r.get("elected")]
    if won:
        return min(won)
    if not bb:
        return None
    last = max(int(r["election_year"]) for r in bb)
    if _dropped_off_at(bb, last):
        return last
    nxt = [y for y in _bbwaa_panel_years(b) if y > last]
    return nxt[0] if nxt else None


def resolution_route(player_id: str, *, label: str = "bbwaa", ballots_=None):
    """Which of RESOLUTION_ROUTES produced `resolution_year`, or None."""
    b = ballots_ if ballots_ is not None else ballots()
    rows = (b.get("by_pid") or {}).get(player_id) or []
    bb = [r for r in rows if (r.get("route") or "").upper() == "BBWAA"
          and r.get("election_year")]
    if label == "any":
        if player_id in (b.get("inducted") or {}):
            return "elected" if bb else "inducted_never_balloted"
        return ("committee_horizon"
                if resolution_year(player_id, label="bbwaa", ballots_=b) is not None
                else None)
    if any(r.get("elected") for r in bb):
        return "elected"
    if not bb:
        return None
    last = max(int(r["election_year"]) for r in bb)
    if _dropped_off_at(bb, last):
        return "dropped_off"
    return "left_ballot" if [y for y in _bbwaa_panel_years(b) if y > last] else None


def resolution_frame(*, offline: bool = False, as_of_year=None, ballots_=None):
    """`label_frame` plus the four resolution columns.

    Nothing serves this. It exists so a forward-chained fold can be keyed on the
    year a label became observable rather than on the year the player retired,
    which is the difference between a forward chain and a look-ahead.
    """
    b = ballots_ if ballots_ is not None else ballots()
    df = label_frame(offline=offline, as_of_year=as_of_year, ballots_=b).copy()
    pids = list(df["player_ID"])
    df["res_year_bbwaa"] = [resolution_year(x, label="bbwaa", ballots_=b) for x in pids]
    df["res_year_any"] = [resolution_year(x, label="any", ballots_=b) for x in pids]
    df["res_route_bbwaa"] = [resolution_route(x, label="bbwaa", ballots_=b) for x in pids]
    df["res_route_any"] = [resolution_route(x, label="any", ballots_=b) for x in pids]
    return df


def assert_no_censored_zero(rows: Iterable) -> int:
    """THE CENSORING INVARIANT, as an assertion a caller can run.

    ``rows`` is any iterable of mappings carrying 'player_id', 'label' and
    'censored'. Raises ValueError naming the offenders if a censored row
    carries a label of 0 (or 0.0, or False, which is the same mistake wearing
    a different type). Returns the number of rows checked.

    Why this is a hard error and not a warning: a censored player scored 0 is
    a label that says 'the voters decided no' about a player the voters have
    not finished deciding on. It biases every recent cohort toward zero, it
    does it hardest to the best active candidates, and it is silent."""
    n = 0
    bad = []
    for r in rows:
        n += 1
        try:
            censored = r["censored"]
            label = r["label"]
            pid = r.get("player_id", "?")
        except (TypeError, KeyError) as exc:
            raise ValueError(
                "assert_no_censored_zero needs mappings with 'player_id', "
                f"'label' and 'censored'; row {n} raised {exc!r}") from exc
        if not censored:
            continue
        if label is CENSORED:
            continue
        if label is False or (isinstance(label, (int, float))
                              and float(label) == 0.0):
            bad.append(pid)
    if bad:
        raise ValueError(
            f"{len(bad)} censored player(s) carry a zero label, which is the "
            "one thing the label contract forbids: "
            f"{bad[:20]}{' and more' if len(bad) > 20 else ''}. A censored "
            "label must be hof_data.CENSORED (None).")
    return n
