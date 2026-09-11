# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The FanGraphs WAR frame, component by component, as PURE functions.

WHY THIS MODULE EXISTS (plan docs/master-plan-2026-09-09-fangraphs-ewar-betting.md,
Part 1, wave W1.1 "the faithful replica"). The owner locked fWAR as the primary
frame on 2026-09-09. Before any component is improved it must first be REPRODUCED
from inputs and gated against the published value, component by component, so that
every later departure is a named, measured change and not an accident of the build.

Nothing here reads a file, fetches anything or writes anything. Every function
takes numbers and returns numbers. The one reader that assembles inputs and scores
the replica against the published feed is tools/fwar_replica_eval.py. Nothing on
the site reads this module: eWAR v3 is a new artifact that no served consumer
touches until the owner's label-epoch decision (plan W1.4).

POSITION PLAYERS (library page "WAR for Position Players", sheet C4 section 1)

    WAR         = (Batting + BaseRunning + Fielding + Positional + League + Replacement) / RPW
    wRAA        = ((wOBA - lgwOBA) / wOBAScale) * PA
    Batting     = wRAA + (lgR/PA - PF*lgR/PA)*PA + (lgR/PA - league non-pitcher wRC/PA)*PA
    wSB         = SB*runSB + CS*runCS - lgwSB*(1B + BB + HBP - IBB)
    BaseRunning = wSB + UBR + wGDP                   UBR and wGDP CONSUMED (need play-by-play)
    Fielding    = consumed from the feed, catcher framing residual included (CONSUMED)
    Positional  = sum over positions of (innings / 1458) * ladder, DH included,
                  plus the pitcher-batting credit (see below)
    League      = -(league sum of Batting + BaseRunning + Fielding + Positional) / lgPA * PA
    Replacement = 570 * (MLB games / 2430) * (RPW / lgPA) * PA
    RPW         = 9 * (MLB R / MLB IP) * 1.5 + 3

PITCHERS (library page "WAR for Pitchers", sheet C5 section 1)

    FIP     = (13*HR + 3*(BB + HBP) - 2*(K + IFFB)) / IP + constant   (IFFB = 0 is plain FIP)
    FIPR9   = FIP + (lgRA9 - lgERA)                  ADDITIVE, not multiplicative
    pFIPR9  = FIPR9 / (PF/100) + 9*CFraming/IP       FIP park factor divided in; framing
                                                     earned on his pitches charged back (9)
    RAAP9   = league FIPR9 - pFIPR9                  own league (AL or NL), not MLB
    dRPW    = (((18 - IP/G)*lgFIPR9 + (IP/G)*pFIPR9) / 18 + 2) * 1.5   lgFIPR9 = own league
    RepLvl  = 0.03*(1 - GS/G) + 0.12*(GS/G)
    WAR'    = (RAAP9/dRPW + RepLvl) * IP/9
    relief  = WAR' * (1 + gmLI)/2                    on the WHOLE quantity, replacement included
    WAR     = WAR' + WARIP*IP                        WARIP pins MLB pitchers to 430 per 2430 games

MEASURED CONVENTIONS THE LIBRARY PAGES DO NOT STATE. Each was read back from the
published feed (commands and outputs in the W1.1 lane result); they are what makes
the replica land, and each is a place a naive build would silently differ.

  1. lgPA in the replacement term is EVERY plate appearance in MLB, pitchers
     batting included (the season's batters-faced total). 570 * (G/2430) * RPW / lgPA
     reproduces the feed's replacement-per-PA to six decimals in 15 of 16 seasons.
  2. RPW for hitters is one MLB constant per season: feed rar / war equals
     9*(R/IP)*1.5+3 from league totals to four decimals every season 2011-2025.
  3. Pitchers who bat are credited a positional adjustment of c * PA, one rate per
     season, set so the average pitcher-batter comes out near zero runs above
     replacement: c = -(pitcher-pool wRAA / pitcher-pool PA) - replacement per PA.
     The feed's c is a single value for all 293 pitcher-batters in 2011; the pool
     formula lands within 0.0016 runs per PA of it every season (at most about 0.2
     runs on a full pitcher batting season).
  4. The league adjustment is NOT "each league's served components sum to zero":
     summed per league, the feed does not balance (2011 AL +160 runs, NL -156). It
     balances MLB-wide exactly, framing included, and the per-league rate is
     reproduced to at most 0.00062 runs per PA when every component is split to the
     league of each stint by stint PA. The residual is FanGraphs computing it on
     per-stint components the season rows do not expose.
  5. 2020 has THREE leagues, not two: the league adjustment is one rate per
     regional schedule group (East, Central, West, both AL and NL clubs together).
  6. FanGraphs prices pitchers PER ROLE: its leaderboard splits RAR into Starting
     and Relieving parts that sum to the total. Pricing the start innings and the
     relief innings as two separate lines (starter replacement on the first,
     reliever replacement and leverage on the second) beats the single blended line
     in both seasons the split was checked on.
  7. Pitcher RAR is WAR times the pitcher's own dynamic runs per win, not the
     season RPW.
  8. The lgFIPR9 inside dRPW is the pitcher's OWN league's FIPR9, not MLB's. The
     library's worked example (Stroman 2016: AL FIPR9 4.56, pFIPR9 4.12, IP/G
     204/32) prints dRPW 9.61; the AL value reproduces 9.61, MLB's 4.52 gives 9.57.
  9. FanGraphs charges a pitcher the catcher framing runs earned on his pitches
     (the `CFraming` column of its PITCHING leaderboard; the catcher is credited
     the same runs inside Fielding, so the league's runs are counted once). No
     library page states it. It is the team-level residual that no park factor
     could close: back-solving a park factor from published WAR gave team values
     4 to 8 points off FanGraphs' own FIP park factor in 2011 (Brewers 95 vs 103
     with Lucroy catching), and the pitcher RAR residual correlated -0.988 with
     pitcher CFraming. Added as runs per nine after the park factor, it takes
     2011 pitcher RAR from 73.0 to 99.7 percent within a run. Placement was
     measured four ways (after the pitcher's RAR, levered with relief, before
     and after the park factor); the last three tie within 0.01 runs of MAE.

WHAT THIS MODULE DELIBERATELY DOES NOT DO. It does not improve anything: the
positional ladder is FanGraphs' fixed table here (the plan's decision to read OUR
ladder belongs to the improvement waves, W1.3 and section 1.4), the pitching runs
leg is plain FIP when IFFB is absent, and the leverage multiplier levers the whole
quantity exactly as FanGraphs does.
"""
from __future__ import annotations

from typing import Iterable, Mapping, Optional, Sequence

# --------------------------------------------------------------------------
# Conventions (FanGraphs, not fitted)
# --------------------------------------------------------------------------

#: WAR handed out per 2,430 MLB games, and its split between the two sides.
WAR_PER_SEASON = 1000.0
POSITION_SHARE = 0.57
PITCHER_SHARE = 0.43
FULL_SEASON_GAMES = 2430.0

#: Runs per 162 defensive games (1,458 innings) at each position.
FG_LADDER: Mapping[str, float] = {
    "C": 12.5, "1B": -12.5, "2B": 2.5, "3B": 2.5, "SS": 7.5,
    "LF": -7.5, "CF": 2.5, "RF": -7.5, "DH": -17.5,
}
LADDER_INNINGS = 9.0 * 162.0

#: A stolen base is worth 0.2 runs every season, by convention.
RUN_SB = 0.2

#: Pitcher replacement level, wins per nine innings, by role.
SP_REPLACEMENT = 0.12
RP_REPLACEMENT = 0.03

#: 2020's three regional schedule groups, keyed by StatsAPI division id.
REGION_OF_DIVISION: Mapping[int, str] = {
    201: "East", 204: "East", 202: "Central", 205: "Central", 200: "West", 203: "West",
}


def replacement_totals(mlb_games: float) -> tuple[float, float]:
    """(position-player WAR, pitcher WAR) handed out for a season of `mlb_games`."""
    scale = float(mlb_games) / FULL_SEASON_GAMES
    return (WAR_PER_SEASON * POSITION_SHARE * scale, WAR_PER_SEASON * PITCHER_SHARE * scale)


# --------------------------------------------------------------------------
# League constants (the solved values live in league_constants.py; these are
# the closed forms, kept here so a synthetic row can be tested end to end)
# --------------------------------------------------------------------------

def runs_per_win(lg_runs: float, lg_ip: float) -> float:
    """FanGraphs' closed form, one MLB constant per season."""
    return 9.0 * (float(lg_runs) / float(lg_ip)) * 1.5 + 3.0


def run_cs(lg_runs: float, lg_outs: float) -> float:
    """Runs per caught stealing, NEGATIVE: -(2 * runs per out + 0.075)."""
    return -(2.0 * float(lg_runs) / float(lg_outs) + 0.075)


def lg_wsb_rate(lg_sb: float, lg_cs: float, lg_1b: float, lg_bb: float,
                lg_hbp: float, lg_ibb: float, rcs: float, rsb: float = RUN_SB) -> float:
    """League stolen-base runs per opportunity, pooled MLB-wide."""
    den = float(lg_1b) + float(lg_bb) + float(lg_hbp) - float(lg_ibb)
    return (float(lg_sb) * rsb + float(lg_cs) * rcs) / den


# --------------------------------------------------------------------------
# Batting
# --------------------------------------------------------------------------

WOBA_KEYS = ("ubb", "hbp", "1b", "2b", "3b", "hr")


def woba_parts(bb: float, ibb: float, hbp: float, h: float, d: float, t: float,
               hr: float, ab: float, sf: float,
               weights: Mapping[str, float]) -> tuple[float, float]:
    """(numerator, denominator) of wOBA from counting stats and one season's
    weights. The denominator is AB + BB - IBB + SF + HBP; plate appearances are
    NOT the denominator (sacrifice bunts and interference are out of it)."""
    singles = h - d - t - hr
    ubb = bb - ibb
    num = (weights["ubb"] * ubb + weights["hbp"] * hbp + weights["1b"] * singles
           + weights["2b"] * d + weights["3b"] * t + weights["hr"] * hr)
    den = ab + ubb + sf + hbp
    return num, den


def woba(num: float, den: float) -> Optional[float]:
    return None if den <= 0 else num / den


def wraa(woba_value: float, lg_woba: float, scale: float, pa: float) -> float:
    """Runs above average from wOBA, multiplied by PA (FanGraphs' convention)."""
    return (woba_value - lg_woba) / scale * pa


def wrc(woba_value: float, lg_woba: float, scale: float, lg_r_pa: float, pa: float) -> float:
    """Weighted runs created: wRAA put back on the run scale."""
    return ((woba_value - lg_woba) / scale + lg_r_pa) * pa


def park_runs(pa: float, lg_r_pa: float, pf: float) -> float:
    """The additive park term of Batting Runs: (lgR/PA - PF*lgR/PA) * PA, PF as a
    decimal (0.95 for 95)."""
    return (lg_r_pa - pf * lg_r_pa) * pa


def league_batting_runs(pa: float, lg_r_pa: float, lg_nonp_wrc_pa: float) -> float:
    """The league term of Batting Runs: (lgR/PA - league non-pitcher wRC/PA) * PA."""
    return (lg_r_pa - lg_nonp_wrc_pa) * pa


def batting_runs(wraa_value: float, stints: Iterable[tuple[float, float, float]],
                 lg_r_pa: float) -> float:
    """Batting Runs for one player-season priced PER STINT.

    `stints` is [(pa, pf, league non-pitcher wRC/PA)] per team stint. wRAA is
    linear in events, so the season total needs no split; only the park and league
    terms depend on where the plate appearances happened, and those need only the
    stint's PA, never its events."""
    tot = float(wraa_value)
    for pa, pf, nonp in stints:
        tot += park_runs(pa, lg_r_pa, pf) + league_batting_runs(pa, lg_r_pa, nonp)
    return tot


def implied_pf(batting: float, wraa_value: float, league_term: float,
               lg_r_pa: float, pa: float) -> Optional[float]:
    """Back-solve the park factor (as a decimal) from a published Batting value.
    The plan's leaderboard back-solve (W1.1): Batting - wRAA - league term is the
    park term, and the park term is linear in PF."""
    if pa <= 0 or lg_r_pa <= 0:
        return None
    return 1.0 - (batting - wraa_value - league_term) / (lg_r_pa * pa)


# --------------------------------------------------------------------------
# Baserunning
# --------------------------------------------------------------------------

def wsb(sb: float, cs: float, singles: float, bb: float, hbp: float, ibb: float,
        rcs: float, lg_wsb: float, rsb: float = RUN_SB) -> float:
    """Stolen-base runs above average: SB*runSB + CS*runCS - lgwSB*(1B+BB+HBP-IBB).
    runCS is negative and ADDED, which is how the published value reproduces."""
    return sb * rsb + cs * rcs - lg_wsb * (singles + bb + hbp - ibb)


def baserunning(wsb_value: float, ubr_plus_wgdp: float) -> float:
    """BsR = wSB + UBR + wGDP. UBR and wGDP need play-by-play with runner
    advancement for every season and are CONSUMED from the published feed."""
    return wsb_value + ubr_plus_wgdp


# --------------------------------------------------------------------------
# Positional and league
# --------------------------------------------------------------------------

def dh_innings(total_innings: float, fielded_innings: float) -> float:
    """DH innings = total defensive-plus-DH innings minus innings in the field.
    StatsAPI publishes DH games only (innings 0); B-Ref's `Inn` includes them."""
    return max(0.0, float(total_innings) - float(fielded_innings))


def positional(innings_by_pos: Mapping[str, float], dh_inn: float = 0.0,
               ladder: Mapping[str, float] = FG_LADDER) -> float:
    """(innings / 1458) * ladder, summed over positions, DH innings priced at the
    DH rung. Positions not on the ladder (P) carry no adjustment here."""
    tot = 0.0
    for pos, inn in innings_by_pos.items():
        if pos == "DH":
            continue
        rung = ladder.get(pos)
        if rung is not None:
            tot += float(inn) / LADDER_INNINGS * rung
    return tot + float(dh_inn) / LADDER_INNINGS * ladder["DH"]


def pitcher_batting_rate(pool_wraa: float, pool_pa: float, replacement_per_pa: float) -> Optional[float]:
    """The per-PA positional credit a pitcher-batter carries (convention 3 in the
    module docstring): minus the pitcher pool's wRAA per PA, minus replacement per
    PA, so the average pitcher-batter lands near zero above replacement."""
    if pool_pa <= 0:
        return None
    return -float(pool_wraa) / float(pool_pa) - float(replacement_per_pa)


def league_adjustment_rate(league_runs_sum: float, league_pa: float) -> Optional[float]:
    """-(league Batting + BaseRunning + Fielding + Positional) / league PA."""
    if league_pa <= 0:
        return None
    return -float(league_runs_sum) / float(league_pa)


def league_adjustment(stint_pa_rates: Iterable[tuple[float, float]]) -> float:
    """sum over stints of PA * the stint league's rate."""
    return sum(float(pa) * float(rate) for pa, rate in stint_pa_rates)


# --------------------------------------------------------------------------
# Replacement and the position-player total
# --------------------------------------------------------------------------

def replacement_per_pa(mlb_games: float, rpw: float, lg_pa: float) -> float:
    """570 * (G/2430) * RPW / lgPA, lgPA being every MLB plate appearance."""
    pos_war, _ = replacement_totals(mlb_games)
    return pos_war * float(rpw) / float(lg_pa)


def replacement_runs(pa: float, mlb_games: float, rpw: float, lg_pa: float) -> float:
    return replacement_per_pa(mlb_games, rpw, lg_pa) * float(pa)


def hitter_rar(batting: float, bsr: float, fielding: float, framing: float,
               pos: float, league: float, replacement: float) -> float:
    return batting + bsr + fielding + framing + pos + league + replacement


def hitter_war(rar: float, rpw: float) -> float:
    return rar / rpw


# --------------------------------------------------------------------------
# Pitchers
# --------------------------------------------------------------------------

def fip_constant(lg_era: float, lg_hr: float, lg_bb: float, lg_hbp: float,
                 lg_k: float, lg_ip: float, lg_iffb: float = 0.0) -> float:
    """lgERA - (13*lgHR + 3*(lgBB+lgHBP) - 2*(lgK+lgIFFB)) / lgIP. With lgIFFB = 0
    it is the plain FIP constant; walks INCLUDE intentional ones."""
    return lg_era - (13.0 * lg_hr + 3.0 * (lg_bb + lg_hbp) - 2.0 * (lg_k + lg_iffb)) / lg_ip


def fip(hr: float, bb: float, hbp: float, k: float, ip: float, constant: float,
        iffb: float = 0.0) -> Optional[float]:
    """FIP (iffb = 0, the plain constant) or ifFIP (iffb given, the ifFIP constant)."""
    if ip <= 0:
        return None
    return (13.0 * hr + 3.0 * (bb + hbp) - 2.0 * (k + iffb)) / ip + constant


def fipr9(fip_value: float, lg_ra9: float, lg_era: float) -> float:
    """FIP carried onto the RA9 scale ADDITIVELY. eWAR v2 multiplies instead
    (ewar.py pitching_component), which widens the spread 7.8 to 9.6 percent."""
    return fip_value + (lg_ra9 - lg_era)


def pfipr9(fipr9_value: float, pf: float) -> float:
    """Park-adjusted FIPR9, PF as a decimal, divided in."""
    return fipr9_value / pf


def framing_charge_per9(cframing: float, ip: float) -> float:
    """Convention 9: the framing runs a pitcher's catchers earned on his pitches,
    as runs per nine added to his park-adjusted FIPR9. Positive framing (called
    strikes stolen for him) raises his runs; zero innings charge nothing."""
    if not ip or ip <= 0:
        return 0.0
    return 9.0 * float(cframing or 0.0) / float(ip)


def raap9(league_fipr9: float, pfipr9_value: float) -> float:
    """Runs above average per nine against the pitcher's OWN league."""
    return league_fipr9 - pfipr9_value


def dynamic_rpw(ip: float, g: float, lg_fipr9: float, pfipr9_value: float) -> float:
    """Per-pitcher runs per win: a pitcher who allows fewer runs lowers the run
    environment of his own innings and so needs fewer runs per win."""
    ipg = float(ip) / float(g)
    return (((18.0 - ipg) * lg_fipr9 + ipg * pfipr9_value) / 18.0 + 2.0) * 1.5


def replacement_level(gs: float, g: float) -> float:
    """Wins per nine above replacement, continuous in the start share."""
    share = float(gs) / float(g) if g > 0 else 0.0
    return RP_REPLACEMENT * (1.0 - share) + SP_REPLACEMENT * share


def leverage_multiplier(gmli: Optional[float]) -> float:
    """(1 + gmLI) / 2, applied to the WHOLE relief quantity."""
    return (1.0 + (1.0 if gmli is None else float(gmli))) / 2.0


def pitcher_war_prime(raap9_value: float, drpw: float, repl: float, ip: float) -> float:
    """Wins above replacement before leverage and before the WARIP pin."""
    return (raap9_value / drpw + repl) * float(ip) / 9.0


def role_line(ip: float, g: float, starter: bool, league_fipr9: float,
              lg_fipr9: float, pfipr9_value: float, gmli: Optional[float]) -> dict:
    """One role's line (start innings or relief innings) priced on its own:
    starter replacement 0.12 with no leverage, reliever replacement 0.03 levered
    by (1+gmLI)/2. Returns {"war0", "drpw", "ip"}; an empty role prices to zero.

    `league_fipr9` is the RAAP9 baseline and `lg_fipr9` the dRPW environment; the
    replica passes the pitcher's own league FIPR9 for both (convention 8). They
    stay separate arguments so an improvement arm can move one without the other."""
    if ip <= 0 or g <= 0:
        return {"war0": 0.0, "drpw": None, "ip": 0.0}
    d = dynamic_rpw(ip, g, lg_fipr9, pfipr9_value)
    rep = SP_REPLACEMENT if starter else RP_REPLACEMENT
    w = pitcher_war_prime(raap9(league_fipr9, pfipr9_value), d, rep, ip)
    if not starter:
        w *= leverage_multiplier(gmli)
    return {"war0": w, "drpw": d, "ip": float(ip)}


def blended_line(ip: float, g: float, gs: float, league_fipr9: float, lg_fipr9: float,
                 pfipr9_value: float, gmli: Optional[float]) -> dict:
    """The single-line reading of the library formula: one dRPW, replacement
    continuous in GS/G, leverage on the relief share of the quantity. Kept as the
    documented alternative to role pricing (convention 6)."""
    d = dynamic_rpw(ip, g, lg_fipr9, pfipr9_value)
    w = pitcher_war_prime(raap9(league_fipr9, pfipr9_value), d, replacement_level(gs, g), ip)
    share = float(gs) / float(g)
    w *= share + (1.0 - share) * leverage_multiplier(gmli)
    return {"war0": w, "drpw": d, "ip": float(ip)}


def warip(target_war: float, sum_war0: float, sum_ip: float) -> float:
    """WAR per inning that pins MLB pitchers to the 430-per-2430-games total."""
    return (float(target_war) - float(sum_war0)) / float(sum_ip)


def pitcher_war(lines: Sequence[dict], warip_value: float) -> tuple[float, float]:
    """(WAR, RAR) from priced role lines. Each line's WAR carries its share of the
    pin; RAR is each line's WAR times its own dynamic runs per win (convention 7)."""
    war = rar = 0.0
    for ln in lines:
        if not ln["ip"]:
            continue
        w = ln["war0"] + warip_value * ln["ip"]
        war += w
        rar += w * ln["drpw"]
    return war, rar


def pf_from_fip_minus(fip_minus: float, fip_value: float, league_fip: float) -> Optional[float]:
    """Back-solve the park factor (decimal) from FIP-:
    FIP- = 100 * (FIP + (FIP - FIP*PF)) / league FIP."""
    if not fip_value or fip_value <= 0:
        return None
    return 2.0 - float(fip_minus) * float(league_fip) / (100.0 * float(fip_value))


# --------------------------------------------------------------------------
# Scoring helpers (used by the eval and the tests)
# --------------------------------------------------------------------------

#: The W1.1 gate: a component clears when at least this share of rows per season
#: sits within TOLERANCE_RUNS of the published value.
TOLERANCE_RUNS = 1.0
GATE_SHARE = 0.99


def gate_row(diffs: Sequence[float], tol: float = TOLERANCE_RUNS,
             share: float = GATE_SHARE) -> dict:
    """n, n within tol, share within tol, MAE, max |diff| and the verdict."""
    xs = [abs(float(x)) for x in diffs if x is not None and x == x]
    n = len(xs)
    if not n:
        return {"n": 0, "n_within": 0, "share_within": None, "mae": None, "max": None,
                "verdict": "NO_ROWS"}
    k = sum(1 for x in xs if x <= tol)
    s = k / n
    return {"n": n, "n_within": k, "share_within": round(s, 4),
            "mae": round(sum(xs) / n, 4), "max": round(max(xs), 3),
            "verdict": "PASS" if s >= share else "FAIL"}
