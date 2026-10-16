# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eWAR v3, the skill and position parts (candidate parts 3 to 6): the pure core.

Registered in docs/ebr-2026-09-30/EBR_GATE.md part 9.4, which this module
implements and does not extend. Owner answers of 2026-10-01: SWAR-Q0 (b), the
positional ladder is a named candidate part of eWAR v3; SWAR-Q1 (b), HEM+, SEM+,
REM+ and DEM+ go inside eWAR v3 as shrunk-skill parts, one house WAR on
FanGraphs' frame; SWAR-Q2 (c), the shrunk-skill parts display as "eWAR skill"
while files and ids stay `swar`; SWAR-Q3 (c), the batting part reads HEM+ and
xHEM+ as two arms of one corrected family. Nothing here is served: the preview
builder (tools/build_swar.py) writes under .cache/swar/preview only, no exporter
imports this module, and EBR_3_EWAR_V3 wires the surfaces behind EWAR_V3_LIVE.

THE FOUR RULES (part 9.4).
  1. Never sum or scale an index. Every delta comes from the shrunk RATES under
     HEM+, SEM+, REM+ and DEM+, the rates those modules already compute.
  2. Delta = skill arm minus actual arm, through the same function, so the park
     term, the framing charge, IFFB, replacement and the league pool cancel and
     a delta needs no FanGraphs leaderboard input.
  3. Re-centre every delta to zero per season and side, so a part moves wins
     between players and never creates them.
  4. Every shrink constant and pool target is taken by reference from hem_plus,
     rem_plus, sem_plus and dem_plus: none is copied, none is refit here. A
     change to any of them is a new registration.

THE PARTS, in the gate's names.
  S1   candidate part 4, the HEM+ arm: each hitter's uBB, HBP, 1B, 2B, 3B and
       HR rates shrunk toward HEM+'s pool with HEM+'s own constants, skill and
       actual wOBA priced on the season's SOLVED weights (league_constants),
       the delta the wRAA difference (fwar_frame.wraa).
  S1x  candidate part 4, the xHEM+ arm: for a hitter-season with a Savant
       xwOBA and 200 or more PA (the subset the xHEM+ gate speaks for), the
       Savant xwOBA re-levelled by the served xHEM+ column's own normalizer;
       every other hitter-season takes the HEM+ arm's value.
  S2   candidate part 5: K, BB, HBP and HR per batter faced shrunk with REM+'s
       and SEM+'s constants toward the start-share blend of the SEM+ and REM+
       pool means (sigma = 1 reproduces SEM+'s target, sigma = 0 REM+'s), the
       FIP difference carried through FanGraphs' pitcher chain twice, re-pinned
       so pitchers' deltas sum to zero. Two home-run variants (orchestrator
       ruling X8): HR shrunk with the shipped K_HOMERUN, and HR left at fWAR's
       own home-run term. Leverage L-A: the published gmLI levers both arms;
       L-B (gmLI 1 in both arms) is a disclosure, never served.
  S3   candidate part 6: FanGraphs' fielding plus framing runs shrunk by DEM+'s
       innings constants, the delta -(1 - rel) x (Fld + Frm). 2016 on.
  S4   candidate part 3: our positional ladder, refit per season on the six
       seasons ending at that season (positional_fit.fit_ladder), with the
       ladder's own DH exposure, against the feed's published positional runs.

THE RULES AT THE EDGES. Rows the replica marks `is_pitcher` (position code 1,
fielded only P) are pitcher-batters: g_bat = g_batx = g_fld = g_pos = 0, they
keep the frame's own line and sit outside the re-centring (invariant 7: zero
delta, so their plate appearances carry none of the correction). Position
players who pitch (the nopp rule: a pitching row whose primary position is not
P or TWP) carry Delta = 0 and sit outside the re-pin. A two-way player is
shrunk as a hitter on the hitting side and as a pitcher on the pitching side.

PURE: no network, no I/O, no module-level data. tools/build_swar.py assembles
the inputs (caches, the frozen fWAR vintage, the EM+ modules' pools, the
replica's feed-only pitcher chain) and writes the preview. The invariants of
part 9.4 are pinned by test_swar.py and the served-path separation by
test_swar_unserved.py. This module never imports fg_leaderboards and never
relates a delta to any next-season quantity.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Optional

import dem_plus
import fwar_frame as F
import hem_plus
import rem_plus
import sem_plus

#: Version of this construction. A changed EM+ constant, ladder module or
#: replica pitcher chain is a new construction and a new registration.
SWAR_VERSION = "swar/2"   # swar/2: the preview also carries part 11.3 (S2b, R2, RA9*)

#: The six wOBA events, in fwar_frame's and league_constants' key order.
BAT_EVENTS = F.WOBA_KEYS

#: HEM+'s per-event shrink constants, BY REFERENCE (rule 4).
BAT_K: Mapping[str, float] = {
    "ubb": hem_plus.K_UBB, "hbp": hem_plus.K_HBP, "1b": hem_plus.K_1B,
    "2b": hem_plus.K_2B, "3b": hem_plus.K_3B, "hr": hem_plus.K_HR,
}

#: The four FIP components and REM+'s (and so SEM+'s) constants, BY REFERENCE.
PIT_COMPONENTS = ("k", "bb", "hbp", "hr")
PIT_K: Mapping[str, float] = {
    "k": rem_plus.K_STRIKEOUT, "bb": rem_plus.K_WALK,
    "hbp": rem_plus.K_HBP, "hr": rem_plus.K_HOMERUN,
}

#: StatsAPI stat keys of the four components, the names the replica's pitcher
#: chain reads and its count_map hook accepts.
PIT_STAT_KEYS: Mapping[str, str] = {
    "k": "strikeOuts", "bb": "baseOnBalls", "hbp": "hitByPitch", "hr": "homeRuns",
}

#: The two home-run variants of the pitching part (orchestrator ruling X8).
HR_SHRUNK, HR_FWAR = "hr_shrunk", "hr_fwar"
HR_VARIANTS = (HR_SHRUNK, HR_FWAR)

#: The hitter-side candidate parts, in the gate's names.
HITTER_PARTS = ("pos", "bat", "batx", "fld")

#: The xHEM+ arm speaks for hitter-seasons with a Savant value at this PA floor:
#: HEM+'s own leaderboard qualification (200 PA), by reference.
XHEM_ARM_MIN_PA = hem_plus.QUALIFY_MIN_PA

#: The Savant pool floor the served xHEM+ column anchors on: the local
#: `_XHEM_MIN_PA = 100.0` inside hitter_export._join_xhem_plus, which is not
#: importable; test_swar.py pins this value to that source line.
XHEM_POOL_MIN_PA = 100.0

#: The primary-position labels a pitching row may carry and still be a pitcher
#: (bullpen_export.rows_from_pitching_splits keeps P by default and TWP on
#: request); any other label is a position player pitching (the nopp rule).
PITCHER_POSITIONS = ("P", "TWP")

#: The ladder's positions that carry fielding innings (positional_fit's
#: LADDER_POSITIONS less DH), and its DH rung name.
LADDER_FIELDERS = dem_plus.DEF_POSITIONS
LADDER_DH = "DH"

#: Innings per 650 PA of exposure is 650 x the fit's innings per PA
#: (positional_fit.fit_all, `inn650 = ladder["inn_per_pa"] * 650.0`).
LADDER_PA_BASIS = 650.0


# --------------------------------------------------------------------------
# rows
# --------------------------------------------------------------------------

@dataclass
class HitterRow:
    """One hitting-group row of the frozen vintage, joined to its season
    counting line, its fielding innings and (optionally) its Savant xwOBA."""
    mlbam: int
    pa: float = 0.0
    ab: float = 0.0
    h: float = 0.0
    doub: float = 0.0
    trip: float = 0.0
    hr: float = 0.0
    bb: float = 0.0
    ibb: float = 0.0
    hbp: float = 0.0
    sf: float = 0.0
    code: str = ""                 # StatsAPI primary position code on the hitting row
    inn_by_pos: dict = field(default_factory=dict)
    fwar: float = 0.0              # published hitting-group WAR (the base)
    pos_fg: float = 0.0            # the feed's published positional runs
    fld: float = 0.0               # the feed's fielding runs
    frm: Optional[float] = None    # the feed's framing residual (saber_feed.framing_residual)
    xwoba: Optional[float] = None  # Savant est_woba, when the source carries him
    name: str = ""


@dataclass
class PitcherRow:
    """One pitching-group row of the frozen vintage, joined to its season
    pitching line and the replica's role innings."""
    mlbam: int
    ip: float = 0.0
    g: float = 0.0
    gs: float = 0.0
    start_ip: float = 0.0          # the replica's role innings (B-Ref start share)
    tbf: float = 0.0
    k: float = 0.0
    bb: float = 0.0
    hbp: float = 0.0
    hr: float = 0.0
    abbr: str = "P"                # StatsAPI primary position abbreviation on the pitching row
    fwar: float = 0.0              # published pitching-group WAR (the base)
    gmli: Optional[float] = None   # the published gmLI (the feed value)
    name: str = ""


def is_pitcher_batter(code: str, inn_by_pos: Mapping[str, float]) -> bool:
    """The replica's `is_pitcher` mark: position code 1 and fielded only P
    (tools/fwar_replica_eval.hitters). A two-way player (code Y) is a hitter."""
    return str(code) == "1" and set(inn_by_pos or {}) <= {"P"}


def is_nopp(abbr: Optional[str]) -> bool:
    """The nopp rule: a pitching row whose primary position is neither P nor
    TWP is a position player pitching. A blank label is kept as a pitcher, the
    rule bullpen_export.rows_from_pitching_splits applies."""
    return bool(abbr) and str(abbr) not in PITCHER_POSITIONS


def start_share(start_ip: float, ip: float) -> float:
    """sigma = start innings / IP, clipped to [0, 1]; 0 with no innings."""
    if ip is None or ip <= 0:
        return 0.0
    return max(0.0, min(1.0, float(start_ip or 0.0) / float(ip)))


def is_swingman(gs: float, g: float) -> bool:
    """Neither SEM+'s starter (GS/G at or above MIN_START_SHARE) nor REM+'s
    reliever (GS/G at or below MAX_START_SHARE): the band between the two
    modules' own thresholds, by reference."""
    if not g or g <= 0:
        return False
    share = float(gs or 0.0) / float(g)
    return rem_plus.MAX_START_SHARE < share < sem_plus.MIN_START_SHARE


# --------------------------------------------------------------------------
# S1: the HEM+ arm (candidate part 4)
# --------------------------------------------------------------------------

def hem_hitter(row: HitterRow) -> hem_plus.Hitter:
    """The HEM+ record of one row, the field mapping of hitter_export.build_hitters."""
    return hem_plus.Hitter(key=str(row.mlbam), name=row.name, mlbam=row.mlbam,
                           pa=row.pa, ab=row.ab, h=row.h, doub=row.doub, trip=row.trip,
                           hr=row.hr, bb=row.bb, ibb=row.ibb, hbp=row.hbp, sf=row.sf)


def woba_denominator(row: HitterRow) -> float:
    """D = AB + BB - IBB + SF + HBP (hem_plus._woba_denom, by reference)."""
    return hem_plus._woba_denom(hem_hitter(row))


def event_counts(row: HitterRow) -> dict[str, float]:
    """n_e for e in {uBB, HBP, 1B, 2B, 3B, HR}; uBB = BB - IBB, 1B = H - 2B - 3B - HR."""
    hi = hem_hitter(row)
    return {"ubb": max(0.0, (row.bb or 0.0) - (row.ibb or 0.0)), "hbp": row.hbp or 0.0,
            "1b": hem_plus._singles(hi), "2b": row.doub or 0.0, "3b": row.trip or 0.0,
            "hr": row.hr or 0.0}


def batting_pool(rows: Iterable[HitterRow]) -> hem_plus.Pool:
    """HEM+'s own pool over the season's hitters (hem_plus.build_pool: the
    D >= POOL_MIN_PA rows anchor the means), as hem_plus.score_pool builds it."""
    hitters = [hem_hitter(r) for r in rows]
    return hem_plus.build_pool([h for h in hitters if hem_plus._woba_denom(h) > 0])


def pool_means(pool: hem_plus.Pool) -> dict[str, float]:
    """mu_s,e per event off HEM+'s Pool."""
    return {"ubb": pool.mean_ubb, "hbp": pool.mean_hbp, "1b": pool.mean_1b,
            "2b": pool.mean_2b, "3b": pool.mean_3b, "hr": pool.mean_hr}


def woba_actual(row: HitterRow, weights: Mapping[str, float]) -> Optional[float]:
    """wOBA_i = sum_e W_s,e n_i,e / D_i on the season's solved weights."""
    d = woba_denominator(row)
    if d <= 0:
        return None
    n = event_counts(row)
    return sum(float(weights[e]) * n[e] for e in BAT_EVENTS) / d


def woba_skill(row: HitterRow, pool: hem_plus.Pool, weights: Mapping[str, float],
               k: Mapping[str, float] = BAT_K) -> Optional[float]:
    """wOBA~_i = sum_e W_s,e r~_i,e, r~ = (n + K mu) / (D + K) through rem_plus._shrink,
    HEM+'s recipe with the season's weights in place of HEM+'s frozen set. With
    HEM+'s frozen weights this equals hem_plus.woba_skill (invariant 2)."""
    d = woba_denominator(row)
    if d <= 0:
        return None
    n = event_counts(row)
    mu = pool_means(pool)
    tot = 0.0
    for e in BAT_EVENTS:
        r_tilde = rem_plus._shrink(n[e] / d, d, float(k[e]), mu[e])
        tot += float(weights[e]) * r_tilde
    return tot


def batting_delta(row: HitterRow, pool: hem_plus.Pool, weights: Mapping[str, float],
                  scale: float, k: Mapping[str, float] = BAT_K) -> float:
    """g_bat,i = ((wOBA~ - wOBA) / scale) x PA, the wRAA difference; 0 on a
    pitcher-batter and on a row with no wOBA denominator."""
    if is_pitcher_batter(row.code, row.inn_by_pos):
        return 0.0
    wa = woba_actual(row, weights)
    ws = woba_skill(row, pool, weights, k)
    if wa is None or ws is None or not row.pa or row.pa <= 0:
        return 0.0
    return F.wraa(ws, wa, scale, row.pa)


# --------------------------------------------------------------------------
# S1x: the xHEM+ arm (candidate part 4, SWAR-Q3 (c))
# --------------------------------------------------------------------------

def savant_pool_mean(entries: Iterable[tuple[int, float, float]],
                     min_pa: float = XHEM_POOL_MIN_PA) -> Optional[float]:
    """xbar_s: the PA-weighted mean Savant xwOBA over the season's Savant rows
    at PA >= min_pa with a positive est_woba, the normalizer the served xHEM+
    column uses (hitter_export._join_xhem_plus). None on an empty pool."""
    num = den = 0.0
    for _mid, ew, pa in entries:
        if pa is None or ew is None or pa < min_pa or ew <= 0:
            continue
        num += float(ew) * float(pa)
        den += float(pa)
    return (num / den) if den > 0 else None


def xwoba_levelled(xwoba: float, lg_woba: float, xbar: float) -> float:
    """xwOBA~_i = xwOBA_i x lgwOBA_s / xbar_s."""
    return float(xwoba) * float(lg_woba) / float(xbar)


def uses_xhem_arm(row: HitterRow, xbar: Optional[float],
                  min_pa: float = XHEM_ARM_MIN_PA) -> bool:
    """Whether the xHEM+ arm departs from the HEM+ arm on this row: a Savant
    value, PA at or above the floor, a pool normalizer, and not a pitcher-batter."""
    return (row.xwoba is not None and xbar is not None and xbar > 0
            and row.pa is not None and row.pa >= min_pa
            and not is_pitcher_batter(row.code, row.inn_by_pos))


def xbatting_delta(row: HitterRow, g_bat: float, xbar: Optional[float],
                   lg_woba: float, scale: float, weights: Mapping[str, float],
                   min_pa: float = XHEM_ARM_MIN_PA) -> float:
    """g_batx,i = ((xwOBA~ - wOBA) / scale) x PA where the arm speaks, else the
    HEM+ arm's value g_bat."""
    if not uses_xhem_arm(row, xbar, min_pa):
        return g_bat
    wa = woba_actual(row, weights)
    if wa is None:
        return g_bat
    return F.wraa(xwoba_levelled(row.xwoba, lg_woba, xbar), wa, scale, row.pa)


# --------------------------------------------------------------------------
# S3: the DEM+ fielding part (candidate part 6)
# --------------------------------------------------------------------------

def dem_fielder(row: HitterRow) -> dem_plus.Fielder:
    return dem_plus.Fielder(key=str(row.mlbam), name=row.name, mlbam=row.mlbam,
                            inn_by_pos=dict(row.inn_by_pos or {}),
                            fld_runs=float(row.fld or 0.0), frm_runs=row.frm)


def fielding_reliability(row: HitterRow, k_inn: Mapping[str, float] = dem_plus.K_INN
                         ) -> Optional[float]:
    """rel_i = inn / (inn + K_i), K_i the innings-weighted mean of K_INN over the
    positions played (dem_plus.shrink_k); None with no defensive innings."""
    f = dem_fielder(row)
    inn = dem_plus.def_innings(f)
    if inn <= 0:
        return None
    if k_inn is dem_plus.K_INN:
        k = dem_plus.shrink_k(f)
    else:
        num = den = 0.0
        for p, v in (f.inn_by_pos or {}).items():
            if p in k_inn and (v or 0) > 0:
                num += float(k_inn[p]) * float(v)
                den += float(v)
        k = num / den if den else max(k_inn.values())
    return inn / (inn + k)


def fielding_delta(row: HitterRow, k_inn: Mapping[str, float] = dem_plus.K_INN) -> float:
    """g_fld,i = rel x (Fld + Frm) - (Fld + Frm) = -(1 - rel) x (Fld + Frm);
    framing counts only on a fielder who caught (dem_plus.fld_total). Zero on a
    pitcher-batter and on a row with no defensive innings."""
    if is_pitcher_batter(row.code, row.inn_by_pos):
        return 0.0
    rel = fielding_reliability(row, k_inn)
    if rel is None:
        return 0.0
    return -(1.0 - rel) * dem_plus.fld_total(dem_fielder(row))


# --------------------------------------------------------------------------
# S4: our positional ladder (candidate part 3)
# --------------------------------------------------------------------------

def dh_exposure(pa: float, inn_by_pos: Mapping[str, float], inn_per_pa: float) -> float:
    """DH_i = max(0, PA x a_s - fielded innings), the ladder's own DH spec
    (positional_fit._ladder_design: fielded innings over the ladder's fielding
    positions, P excluded)."""
    fielded = sum(float(v or 0.0) for p, v in (inn_by_pos or {}).items() if p in LADDER_FIELDERS)
    return max(0.0, float(pa or 0.0) * float(inn_per_pa) - fielded)


def ladder_positional(pa: float, inn_by_pos: Mapping[str, float],
                      ladder: Mapping[str, float], inn_per_pa: float) -> Optional[float]:
    """Pos~_i = sum_p L_s[p] inn_i,p / I_s + L_s[DH] DH_i / I_s, I_s = 650 x a_s.
    The fielding sum is dem_plus.ladder_pos_runs on the same ladder (invariant 5).
    None when the ladder lacks a rung for a position played."""
    inn_650 = LADDER_PA_BASIS * float(inn_per_pa)
    fielding_part = dem_plus.ladder_pos_runs(dict(inn_by_pos or {}), dict(ladder), inn_650)
    if fielding_part is None or LADDER_DH not in ladder:
        return None
    return fielding_part + float(ladder[LADDER_DH]) * dh_exposure(pa, inn_by_pos, inn_per_pa) / inn_650


def position_delta(row: HitterRow, ladder: Mapping[str, float], inn_per_pa: float) -> float:
    """g_pos,i = Pos~_i - Pos_FG,i; a pitcher-batter keeps the frame's credit (0)."""
    if is_pitcher_batter(row.code, row.inn_by_pos):
        return 0.0
    pos = ladder_positional(row.pa, row.inn_by_pos, ladder, inn_per_pa)
    if pos is None:
        return 0.0
    return pos - float(row.pos_fg or 0.0)


# --------------------------------------------------------------------------
# re-centring (rule 3) and the assembled series (part 9.7)
# --------------------------------------------------------------------------

def recentre(g: Mapping[int, float], pa: Mapping[int, float],
             exclude: Iterable[int] = ()) -> dict[int, float]:
    """d_i = g_i - PA_i x (sum_k g_k) / (sum_k PA_k), MLB-wide per plate
    appearance over the rows of the side inside the rule. A row in `exclude`
    (a pitcher-batter, invariant 7) carries d = 0 and sits outside both sums; a
    row with no plate appearance takes no re-centring (its term is PA_i x c =
    0). The sum of d over the side is zero by construction."""
    out_rule = set(int(i) for i in exclude)
    inside = [i for i in g if int(i) not in out_rule]
    tot_pa = sum(float(pa.get(i) or 0.0) for i in inside)
    c = (sum(float(g[i]) for i in inside) / tot_pa) if tot_pa > 0 else 0.0
    return {i: (0.0 if int(i) in out_rule else float(v) - float(pa.get(i) or 0.0) * c)
            for i, v in g.items()}


def assembled_delta(parts: Mapping[str, Mapping[int, float]], admitted: Iterable[str],
                    pa: Mapping[int, float], exclude: Iterable[int] = ()) -> dict[int, float]:
    """Part 9.7: g_i = the sum over admitted parts of that part's g_i, then one
    re-centring over the side's rows (every id in `pa` and in the parts).
    Linear, so it equals the sum of the admitted parts' own re-centred deltas;
    with nothing admitted every d_i is 0."""
    names = [n for n in admitted]
    ids: set[int] = set(int(i) for i in pa)
    for n in names:
        ids.update(int(i) for i in parts[n].keys())
    g = {i: sum(float(parts[n].get(i, 0.0)) for n in names) for i in sorted(ids)}
    return recentre(g, pa, exclude)


def hitter_test_value(fwar: float, d: float, rpw: float) -> float:
    """fWAR_i + d_i / RPW_s."""
    return float(fwar) + float(d) / float(rpw)


# --------------------------------------------------------------------------
# S2: the SEM+ and REM+ pitching part (candidate part 5)
# --------------------------------------------------------------------------

def starter_object(row: PitcherRow) -> sem_plus.Starter:
    return sem_plus.Starter(key=str(row.mlbam), name=row.name, mlbam=row.mlbam,
                            g=row.g, gs=row.gs, ip=row.ip, tbf=row.tbf,
                            so=row.k, bb=row.bb, hbp=row.hbp, hr=row.hr)


def reliever_object(row: PitcherRow) -> rem_plus.Reliever:
    return rem_plus.Reliever(key=str(row.mlbam), name=row.name, mlbam=row.mlbam,
                             g=row.g, gs=row.gs, ip=row.ip, tbf=row.tbf,
                             so=row.k, bb=row.bb, hbp=row.hbp, hr=row.hr)


def pitching_pools(rows: Iterable[PitcherRow]) -> tuple[sem_plus.Pool, rem_plus.Pool]:
    """(SEM+ pool, REM+ pool) over the season's pitchers, each module's own
    membership rule by reference: SEM+ over true starters among P and TWP rows
    (starter_export's board call), REM+ over rem_plus.pool_members of the P rows
    (bullpen_export's default). No opener is dropped here: the opener rule
    needs the leverage feed's entry inning, which this build does not read."""
    rows = list(rows)
    starters = [starter_object(r) for r in rows if not r.abbr or r.abbr in PITCHER_POSITIONS]
    relievers = [reliever_object(r) for r in rows if not r.abbr or r.abbr == "P"]
    sp = sem_plus.build_pool([s for s in starters if sem_plus.is_true_starter(s)])
    rp = rem_plus.build_pool(rem_plus.pool_members(relievers))
    return sp, rp


def pool_rates(pool) -> dict[str, float]:
    """nu_c off a SEM+ or REM+ Pool."""
    return {"k": pool.mean_k_pct, "bb": pool.mean_bb_pct,
            "hbp": pool.mean_hbp_pct, "hr": pool.mean_hr_rate}


def blend_target(sigma: float, sp_pool, rp_pool) -> dict[str, float]:
    """nu_j,c = sigma x nu_SP,c + (1 - sigma) x nu_RP,c, the swingman start-share
    blend; sigma = 1 is SEM+'s target and sigma = 0 REM+'s, exactly."""
    sp, rp = pool_rates(sp_pool), pool_rates(rp_pool)
    s = max(0.0, min(1.0, float(sigma)))
    return {c: s * sp[c] + (1.0 - s) * rp[c] for c in PIT_COMPONENTS}


def actual_counts(row: PitcherRow) -> dict[str, float]:
    return {"k": float(row.k or 0.0), "bb": float(row.bb or 0.0),
            "hbp": float(row.hbp or 0.0), "hr": float(row.hr or 0.0)}


def shrunk_counts(row: PitcherRow, target: Mapping[str, float], variant: str = HR_SHRUNK,
                  k: Mapping[str, float] = PIT_K) -> dict[str, float]:
    """m~_j,c = TBF x (m + K nu) / (TBF + K) through rem_plus._shrink. Under the
    HR_FWAR variant the home-run count is left at the actual count (fWAR's own
    home-run term). A row with no batters faced keeps its counts."""
    if variant not in HR_VARIANTS:
        raise ValueError(f"unknown home-run variant {variant!r}; use one of {HR_VARIANTS}")
    m = actual_counts(row)
    if not row.tbf or row.tbf <= 0:
        return m
    out = {}
    for c in PIT_COMPONENTS:
        if c == "hr" and variant == HR_FWAR:
            out[c] = m[c]
            continue
        q = rem_plus._shrink(m[c] / row.tbf, row.tbf, float(k[c]), float(target[c]))
        out[c] = row.tbf * q
    return out


def dfip(row: PitcherRow, m_tilde: Mapping[str, float]) -> float:
    """dFIP_j = (13 (m~HR - HR) + 3 ((m~BB - BB) + (m~HBP - HBP)) - 2 (m~K - K)) / IP.
    Exact: the FIP constant and IFFB are common to both arms and cancel; no 1.0
    floor applies to a runs delta."""
    if not row.ip or row.ip <= 0:
        return 0.0
    m = actual_counts(row)
    return (rem_plus.FIP_HR * (m_tilde["hr"] - m["hr"])
            + rem_plus.FIP_BBHBP * ((m_tilde["bb"] - m["bb"]) + (m_tilde["hbp"] - m["hbp"]))
            - rem_plus.FIP_K * (m_tilde["k"] - m["k"])) / float(row.ip)


def skill_fip(row: PitcherRow, m_tilde: Mapping[str, float], constant: float,
              floor: Optional[float] = None) -> Optional[float]:
    """The skill arm's FIP on the pool constant: with no IFFB it equals
    sem_plus / rem_plus.fip_skill, floor aside (invariant 3)."""
    if not row.ip or row.ip <= 0:
        return None
    v = (rem_plus.FIP_HR * m_tilde["hr"] + rem_plus.FIP_BBHBP * (m_tilde["bb"] + m_tilde["hbp"])
         - rem_plus.FIP_K * m_tilde["k"]) / float(row.ip) + float(constant)
    return v if floor is None else max(v, floor)


def count_map(rows: Iterable[PitcherRow], sp_pool, rp_pool, variant: str = HR_SHRUNK,
              k: Mapping[str, float] = PIT_K) -> dict[int, dict[str, float]]:
    """{mlbam: {StatsAPI key: shrunk count}} for tools/fwar_replica_eval.pitchers
    (count_map=...): the skill arm's counts for every pitcher under the nopp
    rule (a position player pitching is left out, so his arm is the actual one)."""
    out: dict[int, dict[str, float]] = {}
    for r in rows:
        if is_nopp(r.abbr) or not r.ip or r.ip <= 0:
            continue
        tgt = blend_target(start_share(r.start_ip, r.ip), sp_pool, rp_pool)
        mt = shrunk_counts(r, tgt, variant, k)
        out[int(r.mlbam)] = {PIT_STAT_KEYS[c]: mt[c] for c in PIT_COMPONENTS}
    return out


def pfipr9(fip: float, pf: float, lg_ra9: float, lg_era: float) -> float:
    """FIPR9 / PF, the replica's price(): fip + (lgRA9 - lgERA), divided by the park factor."""
    return F.pfipr9(F.fipr9(float(fip), float(lg_ra9), float(lg_era)), float(pf))


def pitcher_war0(ip: float, g: float, gs: float, start_ip: float, lg9: float,
                 pfr: float, gmli: Optional[float]) -> float:
    """war0 (before the WARIP pin) of one pitcher-season on the replica's role
    pricing: the start line at SP replacement, the relief line at RP replacement
    levered by (1 + gmLI) / 2 (fwar_frame.role_line). L-A passes the published
    gmLI; L-B passes 1.0."""
    g_rel = float(g) - float(gs)
    lines = [F.role_line(float(start_ip), float(gs), True, lg9, lg9, pfr, gmli),
             F.role_line(float(ip) - float(start_ip), g_rel, False, lg9, lg9, pfr, gmli)]
    return sum(ln["war0"] for ln in lines)


def dwar0(ip: float, g: float, gs: float, start_ip: float, lg9: float, pf: float,
          fip: float, dfip_value: float, lg_ra9: float, lg_era: float,
          gmli: Optional[float]) -> float:
    """war0(skill) - war0(actual): the same chain twice, the skill arm's pFIPR9
    being the actual arm's plus dFIP / PF."""
    actual = pitcher_war0(ip, g, gs, start_ip, lg9, pfipr9(fip, pf, lg_ra9, lg_era), gmli)
    skill = pitcher_war0(ip, g, gs, start_ip, lg9,
                         pfipr9(float(fip) + float(dfip_value), pf, lg_ra9, lg_era), gmli)
    return skill - actual


def pitching_delta(dwar0_by_id: Mapping[int, float], ip_by_id: Mapping[int, float],
                   nopp: Iterable[int] = ()) -> dict[int, float]:
    """Delta_j = dwar0_j - IP_j x (sum_k dwar0_k) / (sum_k IP_k), the WARIP
    re-pin over the pitchers inside the rule; a nopp row carries 0 and sits
    outside the re-pin. The deltas inside the rule sum to zero."""
    out_rule = set(int(i) for i in nopp)
    inside = [i for i in dwar0_by_id if int(i) not in out_rule]
    tot_ip = sum(float(ip_by_id.get(i) or 0.0) for i in inside)
    c = (sum(float(dwar0_by_id[i]) for i in inside) / tot_ip) if tot_ip > 0 else 0.0
    out: dict[int, float] = {}
    for i, v in dwar0_by_id.items():
        out[i] = 0.0 if int(i) in out_rule else float(v) - float(ip_by_id.get(i) or 0.0) * c
    return out


def pitcher_test_value(fwar: float, delta: float) -> float:
    """fWAR_j + Delta_j."""
    return float(fwar) + float(delta)
