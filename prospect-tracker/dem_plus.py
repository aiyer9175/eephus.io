# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""DEM+ (Defense Evaluation Metric +) - the model core.

The fielding member of the HEM+ / REM+ / SEM+ family, pre-registered in
docs/dem-plus-2026-09-11/DEM_PLUS_GATE.md before any number was computed.

WHAT IT IS. A sample-shrunk fielding RATE, runs per 1,000 defensive innings,
on the `100 + 10z` ruler: 100 is the average fielder in the pool (200 or more
defensive innings), ten points is one standard deviation of the pool's SHRUNK
rates. The runs are FanGraphs' served fielding runs, read verbatim from MLB's
sabermetrics feed, plus catcher framing recovered as the exact residual of the
same feed's run line. This module computes the index; it computes no fielding
run of its own.

WHY NOT THE RATIO SCALE OF ITS SIBLINGS. HEM+, REM+ and SEM+ divide by a league
rate that is positive. Fielding runs are zeroed within every position and
season, so the league rate is zero and a ratio divides by it. The WAR/PA+
convention (ten points per standard deviation) is the only honest ruler for a
signed rate centred on zero, and a point of DEM+ is therefore NOT a point of
HEM+.

TWO NUMBERS, KEPT APART. The positional adjustment (a shortstop's credit for
playing shortstop) and volume (innings) are real value, and they ride as
context columns (`pos_runs`, `def_runs`, `inn`). Neither moves DEM+, which is
the glove per inning. A first baseman can read DEM+ 115 and still post
negative Def, exactly as a DH can post a high HEM+ and a low WAR.

WHAT IT IS NOT. Not an input to eWAR (fielding stays on fielding_blend_w 0.0),
not an eFV feature (do-not-reopen 17), not read by betting or projections. It
is a steadier read of FanGraphs' published series, never a claim to measure
defense better than fWAR; framing inside the catcher number is parity with
fWAR, not an improvement.

PURE: no network, no I/O. defense_export.py assembles the inputs and writes
the board; tools/dem_plus_lab.py is the pre-registered forward validation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

#: The positions whose innings and runs enter. P and DH never do.
DEF_POSITIONS = ("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF")

#: Tie-break order for a primary position: the harder rung wins an innings tie.
POSITION_RUNG = ("C", "SS", "CF", "2B", "3B", "RF", "LF", "1B")

PER_INNINGS = 1000.0          # rate basis: runs per 1,000 defensive innings
DEM_PER_SIGMA = 10.0          # convention 3, the WAR/PA+ ruler
POOL_MIN_INN = 200.0          # contributes to the pool's mean and sd
QUALIFY_MIN_INN = 400.0       # leaderboard-qualified

#: Per-position shrink constants, in innings: the exposure at which a season's
#: rate is half signal. FROZEN from the pre-registered fit window (predictor
#: seasons 2016 to 2018, single-position player-seasons with 300+ innings at the
#: position both years, the positional_fit.fit_signal rule) BEFORE the gate
#: window was read. LF had 29 pairs, one short of the 30-pair floor, so it keeps
#: the data/positional_fit.json range-only constant. Fit output, for the record:
#:   C  r 0.6176 n 128   1B r 0.2360 n 69   2B r 0.4618 n 54   3B r 0.4943 n 50
#:   SS r 0.6297 n 73    CF r 0.6836 n 50   RF r 0.7202 n 46
#: Catchers shrink least because framing is measured on every pitch; first
#: basemen shrink most because the spread there is mostly noise.
K_INN = {"C": 417.0, "1B": 3116.0, "2B": 1151.0, "3B": 1018.0,
         "SS": 616.0, "LF": 935.0, "CF": 452.0, "RF": 368.0}

#: A framing residual smaller than this is treated as the feed's rounding.
FRAMING_EPS = 0.05

#: The first season on the one Statcast fielding frame FanGraphs made
#: retroactive. Earlier seasons are UZR and are never pooled with these.
FIRST_SEASON = 2016

#: Whether a club rollup may carry catcher framing. OFF until the betting
#: program's pre-registered `catch_frame_rate` read (docs/diamond-betting.md 5d-D,
#: first look about 2026-10-06) is recorded: a public club-level framing total is
#: the one number that invites an early eyeball of the skill that column
#: measures. Per-catcher framing still displays (parity with fWAR); Team DEM+ and
#: its run totals roll over non-catchers only. Restoring it is this one constant.
TEAM_ROLLUP_FRAMING = False

TIER_ORDER = ["Elite", "Above-avg", "Average", "Below-avg"]
#: The remClass breaks, as WAR/PA+ uses them on the same ruler.
DEM_ELITE = 120.0
DEM_ABOVE = 107.0
DEM_AVG = 93.0


def _round(v, nd):
    return None if v is None else round(float(v), nd)


@dataclass
class Fielder:
    """One fielder-season. `fld_runs` and `frm_runs` are PUBLISHED values."""
    key: str
    name: str = ""
    team: str = ""
    mlbam: Optional[int] = None
    inn_by_pos: dict = field(default_factory=dict)
    fld_runs: float = 0.0              # FanGraphs fielding, excluding framing
    frm_runs: Optional[float] = None   # catcher framing; None when absent
    pos_runs: Optional[float] = None   # FanGraphs positional adjustment
    putouts: float = 0.0
    assists: float = 0.0
    errors: float = 0.0
    # computed
    inn: float = 0.0
    primary_pos: str = ""
    rate: Optional[float] = None
    rate_shrunk: Optional[float] = None
    rel: Optional[float] = None
    dem_plus: Optional[int] = None
    dem_plus_raw: Optional[float] = None
    tier: str = ""
    qualified: bool = False


def def_innings(f: Fielder) -> float:
    return sum(float(v or 0.0) for p, v in (f.inn_by_pos or {}).items()
               if p in DEF_POSITIONS)


def primary_position(f: Fielder) -> str:
    """Most defensive innings; ties go to the harder rung."""
    cand = {p: float(v or 0.0) for p, v in (f.inn_by_pos or {}).items()
            if p in DEF_POSITIONS and (v or 0) > 0}
    if not cand:
        return ""
    return max(cand, key=lambda p: (cand[p], -POSITION_RUNG.index(p)))


def fld_total(f: Fielder) -> float:
    """Fielding plus framing, the run total DEM+ rates. Framing only counts on a
    fielder who caught: the residual on anyone else is the feed's rounding."""
    frm = f.frm_runs if (f.frm_runs is not None
                         and float((f.inn_by_pos or {}).get("C") or 0) > 0) else 0.0
    return float(f.fld_runs or 0.0) + float(frm or 0.0)


def shrink_k(f: Fielder) -> float:
    """Innings-weighted mean of K_INN over the positions played."""
    num = den = 0.0
    for p, v in (f.inn_by_pos or {}).items():
        if p in K_INN and (v or 0) > 0:
            num += K_INN[p] * float(v)
            den += float(v)
    return num / den if den else max(K_INN.values())


def derive(f: Fielder) -> None:
    f.inn = def_innings(f)
    f.primary_pos = primary_position(f)
    if f.inn <= 0:
        f.rate = f.rate_shrunk = f.rel = None
        return
    tot = fld_total(f)
    k = shrink_k(f)
    f.rate = PER_INNINGS * tot / f.inn
    # Shrunk toward zero: FanGraphs zeroes fielding runs within each position
    # and season, so zero IS the position mean.
    f.rate_shrunk = PER_INNINGS * tot / (f.inn + k)
    f.rel = f.inn / (f.inn + k)


@dataclass
class Pool:
    n: int = 0
    mean_rate: float = 0.0
    sd_rate: float = 1.0


def build_pool(fielders: Iterable[Fielder]) -> Pool:
    """Mean and sample sd of the SHRUNK rate over pool fielders, unweighted, so
    the served spread is exactly the one the scale advertises."""
    vals = [f.rate_shrunk for f in fielders
            if f.rate_shrunk is not None and f.inn >= POOL_MIN_INN]
    if len(vals) < 2:
        return Pool()
    mu = sum(vals) / len(vals)
    sd = (sum((v - mu) ** 2 for v in vals) / (len(vals) - 1)) ** 0.5
    return Pool(n=len(vals), mean_rate=mu, sd_rate=sd if sd > 0 else 1.0)


def dem_plus(f: Fielder, pool: Pool) -> Optional[int]:
    if f.rate_shrunk is None or pool.sd_rate <= 0:
        return None
    raw = 100.0 + DEM_PER_SIGMA * (f.rate_shrunk - pool.mean_rate) / pool.sd_rate
    f.dem_plus_raw = raw
    f.dem_plus = int(round(raw))
    return f.dem_plus


def assign_tiers(fielders: list[Fielder]) -> None:
    for f in fielders:
        v = f.dem_plus
        if v is None:
            f.tier = ""
        elif v >= DEM_ELITE:
            f.tier = "Elite"
        elif v >= DEM_ABOVE:
            f.tier = "Above-avg"
        elif v >= DEM_AVG:
            f.tier = "Average"
        else:
            f.tier = "Below-avg"


def fielding_pct(f: Fielder) -> Optional[float]:
    ch = (f.putouts or 0.0) + (f.assists or 0.0) + (f.errors or 0.0)
    return ((f.putouts or 0.0) + (f.assists or 0.0)) / ch if ch > 0 else None


def build_alignment(fielders: list[Fielder],
                    active_ids: Optional[frozenset] = None) -> tuple[list[dict], int]:
    """Tonight's defensive alignment: for each position, the active-roster fielder
    with the most innings AT THAT POSITION. Same split as team_offense: the
    construction is roster-filtered, the aggregate is the season as played.
    Returns (slots, n_dropped)."""
    avail = fielders if active_ids is None else [
        f for f in fielders if f.mlbam is None or int(f.mlbam) in active_ids]
    dropped = len(fielders) - len(avail)
    if not avail:
        avail, dropped = fielders, 0
    slots = []
    used: set = set()
    for p in DEF_POSITIONS:
        cand = sorted((f for f in avail if float((f.inn_by_pos or {}).get(p) or 0) > 0
                       and f.key not in used),
                      key=lambda f: -float(f.inn_by_pos.get(p) or 0))
        if not cand:
            continue
        f = cand[0]
        used.add(f.key)
        slot = {"pos": p, "key": f.key, "mlbam": f.mlbam, "name": f.name,
                "inn_at_pos": round(float(f.inn_by_pos.get(p) or 0), 1),
                "dem_plus": f.dem_plus}
        if p == "C" and f.frm_runs is not None:
            slot["frm_runs"] = _round(f.frm_runs, 1)
        slots.append(slot)
    return slots, dropped


def _caught(f: Fielder) -> bool:
    return float((f.inn_by_pos or {}).get("C") or 0) > 0


def team_defense(team: str, fielders: list[Fielder],
                 active_ids: Optional[frozenset] = None) -> dict:
    """Team DEM+: the innings-weighted mean of every fielder's unrounded DEM+,
    over the season as played (not roster-filtered, the Offense+ rule), plus the
    run totals as context. The alignment is tonight's and IS filtered.

    While TEAM_ROLLUP_FRAMING is False, anyone who caught is left out of the
    rollup and its run totals, so no club-level number carries framing; the
    alignment still names the catcher, without his framing total."""
    scored = [f for f in fielders if f.dem_plus_raw is not None and f.inn > 0]
    rolled = scored if TEAM_ROLLUP_FRAMING else [f for f in scored if not _caught(f)]
    out = {"team": team, "n_fielders": len(rolled),
           "rollup_includes_catchers": bool(TEAM_ROLLUP_FRAMING)}
    if not rolled:
        return out
    den = sum(f.inn for f in rolled)
    raw = sum(f.dem_plus_raw * f.inn for f in rolled) / den if den else None
    out["team_dem_plus"] = None if raw is None else int(round(raw))
    out["team_dem_plus_raw"] = _round(raw, 2)
    out["team_inn"] = round(den, 1)
    out["n_above_avg"] = sum(1 for f in rolled if (f.dem_plus or 0) >= 100)
    out["team_fld_runs"] = round(sum(float(f.fld_runs or 0) for f in rolled), 1)
    if TEAM_ROLLUP_FRAMING:
        frm = [f.frm_runs for f in rolled if f.frm_runs is not None and _caught(f)]
        out["team_frm_runs"] = round(sum(frm), 1) if frm else None
    out["team_fld_total"] = round(sum(fld_total(f) for f in rolled), 1)
    pr = [f.pos_runs for f in rolled if f.pos_runs is not None]
    out["team_pos_runs"] = round(sum(pr), 1) if pr else None
    align, dropped = build_alignment(scored, active_ids)
    if not TEAM_ROLLUP_FRAMING:
        for s in align:
            s.pop("frm_runs", None)
    out["alignment"] = align
    out["n_off_roster_dropped"] = dropped
    return out


def _pos_pct(scored: list[Fielder]) -> dict:
    """Midrank percentile of DEM+ within each primary position, over pool
    fielders. Context for reading a first baseman against first basemen; the
    headline stays the one pooled ruler the gate registered."""
    by: dict = {}
    for f in scored:
        if f.inn >= POOL_MIN_INN and f.primary_pos:
            by.setdefault(f.primary_pos, []).append(f.dem_plus_raw)
    out = {}
    for f in scored:
        vals = by.get(f.primary_pos) or []
        if f.inn < POOL_MIN_INN or len(vals) < 5:
            continue
        lo = sum(1 for v in vals if v < f.dem_plus_raw)
        eq = sum(1 for v in vals if v == f.dem_plus_raw)
        out[f.key] = int(round(100.0 * (lo + (eq + 1) / 2.0 - 0.5) / len(vals)))
    return out


def score_pool(fielders: list[Fielder],
               active_ids: Optional[frozenset] = None,
               season: Optional[int] = None) -> dict:
    """Derive, pool, score, tier, roll up by team. Pure. A season before
    FIRST_SEASON is refused: it is on a different fielding frame."""
    if season is not None and int(season) < FIRST_SEASON:
        raise ValueError(f"DEM+ is defined from {FIRST_SEASON}; {season} is on the "
                         "UZR frame and is never pooled with these")
    live = [f for f in fielders]
    for f in live:
        derive(f)
    live = [f for f in live if f.rate_shrunk is not None]
    pool = build_pool(live)
    for f in live:
        dem_plus(f, pool)
        f.qualified = f.inn >= QUALIFY_MIN_INN
    assign_tiers(live)
    by_team: dict[str, list[Fielder]] = {}
    for f in live:
        by_team.setdefault(f.team or "", []).append(f)
    teams = [team_defense(t, fs, active_ids) for t, fs in by_team.items() if t]
    teams.sort(key=lambda t: (t.get("team_dem_plus_raw") if t.get("team_dem_plus_raw")
                              is not None else -999), reverse=True)
    scored = [f for f in live if f.dem_plus is not None]
    scored.sort(key=lambda f: (f.dem_plus_raw or 0), reverse=True)
    pos_pct = _pos_pct(scored)
    rows = [fielder_row(f) for f in scored]
    vals = sorted(r["dem_plus_raw"] for r in rows if r["dem_plus_raw"] is not None)
    for r in rows:
        if r["key"] in pos_pct:
            r["dem_plus_pos_pct"] = pos_pct[r["key"]]
        v = r["dem_plus_raw"]
        if v is not None and vals:
            lo = sum(1 for s in vals if s < v)
            eq = sum(1 for s in vals if s == v)
            r["dem_plus_pct"] = int(round(100.0 * (lo + (eq + 1) / 2.0 - 0.5) / len(vals)))
    return {
        "fielders": rows,
        "teams": teams,
        "pool": {"n": pool.n, "mean_rate": _round(pool.mean_rate, 4),
                 "sd_rate": _round(pool.sd_rate, 4),
                 "n_qualified": sum(1 for f in scored if f.qualified),
                 "n_provisional": sum(1 for f in scored if not f.qualified)},
    }


def fielder_row(f: Fielder) -> dict:
    tot = fld_total(f)
    frm_ok = f.frm_runs is not None and float((f.inn_by_pos or {}).get("C") or 0) > 0
    row = {
        "key": f.key, "mlbam": f.mlbam, "name": f.name, "team": f.team,
        "pos": f.primary_pos,
        "pos_inn": {p: round(float(v), 1) for p, v in sorted(
            (f.inn_by_pos or {}).items(), key=lambda kv: -float(kv[1] or 0))
            if p in DEF_POSITIONS and (v or 0) > 0},
        "inn": round(f.inn, 1), "qualified": f.qualified, "tier": f.tier,
        "dem_plus": f.dem_plus, "dem_plus_raw": _round(f.dem_plus_raw, 2),
        "rel": _round(f.rel, 3),
        "rate_1000": _round(f.rate, 3), "rate_1000_shrunk": _round(f.rate_shrunk, 4),
        "fld_runs": _round(f.fld_runs, 1), "fld_total": _round(tot, 1),
        "fld_pct": _round(fielding_pct(f), 3),
    }
    if frm_ok:
        row["frm_runs"] = _round(f.frm_runs, 1)
    if f.pos_runs is not None:
        row["pos_runs"] = _round(f.pos_runs, 1)
        row["def_runs"] = _round(tot + float(f.pos_runs), 1)
    return row
