# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MLB Projections module - sidecar export (data/mlb_projections.json).

The FA module's Gate-1-validated projection engine, applied to the WHOLE
league: every player with recent MLB history gets a multi-year bWAR path
(mean + P10/P90 probability buckets), and PROSPX prospects get post-ETA
paths from the calibrated FV outcome model. One surface, two clearly
labeled sources:

  VETERANS   the FA Marcel engine (components -> composites -> fitted WAR
             map), decayed along the survivorship-corrected aging curves;
             buckets are the Gate-1 empirical year-1 residual quantiles
             decayed through the same curves (identical machinery to the
             FA class board - fa_market.contract_war_path).
  PROSPECTS  the value_framework outcome model: P(bucket|FV) x per-bucket
             WAR trajectories (FV-scaled, aging-shaped from projected
             debut age), starting at the PROSPX ETA. Floor/ceiling are
             the 10th/90th percentile OUTCOME BUCKETS of the categorical
             - a prospect's downside is busting, not a residual ribbon.

Dollars: each projected season is priced through the platform's convex
tier curve at the winter's ex-ante FA $/WAR level, escalated by the
configured $/WAR inflation per season - the same pricing the FA rational
value and the (re-anchored) prospect surplus use. Veteran SURPLUS covers
the CONTROL WINDOW, not only the contracted part of it (ask C,
2026-09-16): every remaining season a club controls is priced through
salary_path.py - contracted dollars where a contract exists, the CBA
league minimum for pre-arbitration seasons, the arbitration board's
projected award for arbitration seasons - and netted against production
value at the platform discount rate (value_framework discount_rate, read
in _veteran_rows). A season past the end of club control carries a
projection and no price. Prospect surplus IS the platform surplus value
(control-window, service-time aware) - never a parallel number, and it
keeps the clemens_2026 fraction ladder on purpose (docs/
ARBITRATION_GATE.md section 6: a never-debuted player has no prior salary
for the award model to raise off).

Club: a veteran row's `team` is the club that holds him today
(resolve_current_club). Where the Spotrac contract club differs, the row
also carries `contract_club`, the club paying the salary. That field is
AUDIT-ONLY (owner answer M23-2, 2026-09-25): no page reads it, it is
written on those rows only, and their count is team_basis.n_off_contract_club.

Run: python proj_export.py   (also wired into run_monthly after the FA
refresh). Reads only caches + committed artifacts; never writes PROSPX
data (read-only consumer, same contract as the FA module).
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import date
from pathlib import Path

import fa_class
import fa_ident
import fa_market as fm
import fa_projection as fp
import salary_path as sp
import value_framework as vf
from rate_stabilization import REPLACEMENT_WINS
from scrapers import normalize_key

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
FIRST_SEASON = 2027          # first fully projected season; a MANUAL, dated flip
FIRST_SEASON_SET_ON = "2026-06-10"   # the date of the last flip; moves with it
HORIZON = 5                  # 2027..2031
# THE FIRST-SEASON FLIP GUARD (owner answer M15-3, 2026-09-25;
# docs/PROJ_FORWARD_VINTAGE_GATE.md section 4). FIRST_SEASON never rolls by the
# calendar: it moves by hand in its own dated commit, with FIRST_SEASON_SET_ON.
# Before it may move past a season, that season's preseason forecast must be on
# record (a frozen file whose hash still matches, or a no_season entry), so the
# forward score always has the forecast it grades. build_payload calls this
# first, so a premature flip fails the export rather than serving a board whose
# predecessor was never kept.


def assert_first_season_flip_allowed(first_season: int | None = None,
                                     vintage_dir: Path | None = None) -> None:
    import proj_forward_vintage as pfv
    fs = FIRST_SEASON if first_season is None else int(first_season)
    missing = []
    for season in range(pfv.FIRST_FROZEN_SEASON, fs):
        ok, why = pfv.on_record(season, vintage_dir)
        if not ok:
            missing.append(f"{season} ({why})")
    if missing:
        raise RuntimeError(
            f"FIRST_SEASON {fs} refused: the preseason forecast of "
            + ", ".join(missing) + " is not on record. Freeze it with "
            "tools/freeze_proj_forward_vintage.py before the season's first game "
            "(docs/PROJ_FORWARD_VINTAGE_GATE.md), or record a no_season entry by "
            "dated amendment.")


# THE CONTRACT TAIL (owner answer 2026-09-25, census M05-01 step 2). A
# guaranteed contract that runs past the last projected season is priced
# through its last guaranteed season, not only through FIRST_SEASON+HORIZON-1.
# Only CONTRACT dollars are priced out there; an unsigned club-controlled
# season past the horizon still carries no price. The board still PRINTS five
# seasons; the tail WAR each priced season used ships as `warTail`.
# False restores the five-season surplus on every row, byte for byte.
PRICE_CONTRACT_TAIL = True
# THE 2031/2032 SEAM (owner answer VAL2-Q1, 2026-09-30). Which WAR a tail season
# prices on:
#   "chained"         the champion's aging curve CHAINED FROM THE SERVED 2031
#                     WAR: fa_market.chain_aging_tail, the FA module's own seam
#                     (contract_war_path extends the ML path's horizons 6+ with
#                     it), so /projections/ and that path can never use a
#                     different curve or a different start point. It removes
#                     the level step between 2031 (ML path) and 2032 (champion
#                     level): -3.24 WAR on McGonigle, +2.95 on Soto.
#   "champion_level"  the Marcel champion's mean path at its own level
#                     (war_by_year_champ), the VAL_2 shape (36b93e16).
# The chained tail rides the 2031 point of the served path, so a
# docs/PROJ_PATH_SHAPE_GATE.md SERVE flag moves it (section 9.1 already names
# horizons 6-15 through the h5 anchor); the champion level does not.
TAIL_SEAM = "chained"
# THE TAIL'S RANGE (owner answers VAL2-Q3 and VAL2-Q3-REVIEW (b), 2026-09-30).
# The P10/P90 of each tail season, published as warP10Tail / warP90Tail beside
# warTail, so the trade value's range spans every season its point value prices.
# Method, the FA module's own (contract_war_path): the 2031 P10 and P90 heads
# chained along the champion's aging curve with fa_market.chain_aging_tail
# (anchors 0.6 and 1.4 x the champion path, so with a defined anchor each tail
# season keeps the 2031 P10/point and P90/point ratios). THE LOW END IS NOT
# FLOORED (VAL2-Q3-REVIEW (b)): a negative 2031 P10 carries into the later
# seasons along the same chain (TAIL_BAND_P10_FLOOR False), so the range has no
# step at 2032; the FA module floors it at 0. The high end and the point keep
# the floor. Per season only: nothing here sums a quantile point across seasons.
# Requires TAIL_SEAM "chained" (the band is chained from the same 2031 point);
# False ships no tail band and the range spans 2027-2031.
TAIL_BAND = True
# True restores the floored low end (the c3_tail_band build reviewed 2026-09-30).
TAIL_BAND_P10_FLOOR = False


def _tail_band(m: dict, champ_full: list):
    """(p10_tail, p90_tail) for the seasons past the horizon, or None.

    Reads the row's full-length P10/P90 (each side's war_by_year_p10_open /
    war_by_year_p90, whose tail is chain_aging_tail, the P10 one without the
    zero floor; combined by the rho rule on a two-way row). Where a carrier is
    missing or does not reproduce the served five seasons it is recomputed with
    chain_aging_tail from the served warP10/warP90 and the champion path at the
    FA module's anchors (0.6 and 1.4 x), the P10 again without the floor, the
    chain's branch decided on the unmultiplied champion (branch_champ) as the
    point's is, so P10 <= point <= P90 holds on every tail season."""
    if not TAIL_BAND or TAIL_SEAM != "chained":
        return None
    n = len(champ_full)
    out = []
    for key, served, mult, floor in (("_p10Full", m.get("warP10"), 0.6, TAIL_BAND_P10_FLOOR),
                                     ("_p90Full", m.get("warP90"), 1.4, True)):
        full = m.get(key)
        if not served or len(served) < HORIZON or any(x is None for x in served[:HORIZON]):
            return None
        if not (full and len(full) >= n
                and all(abs(float(full[t]) - float(served[t])) < 0.006 for t in range(HORIZON))):
            full = fm.chain_aging_tail([float(x) for x in served[:HORIZON]],
                                       [mult * float(c) for c in champ_full], HORIZON, n,
                                       floor=floor,
                                       branch_champ=[float(c) for c in champ_full])
        out.append([float(x) for x in full[HORIZON:n]])
    return out[0], out[1]


def _tail_war(war: list, champ_full: list, war_full: list | None) -> tuple[list[float], str]:
    """The WAR each season past the horizon prices on, by TAIL_SEAM.

    "chained" reads the row's full served path (each side's war_by_year, summed
    on a two-way row), whose seasons past the horizon ARE
    fa_market.chain_aging_tail. Where that carrier is missing or does not
    reproduce the served five seasons it is recomputed from the served path
    and the champion path with the same function, so the rule never forks."""
    if TAIL_SEAM == "champion_level":
        return [float(w) for w in champ_full[HORIZON:]], "champion_level"
    if TAIL_SEAM != "chained":
        raise ValueError("unknown TAIL_SEAM %r" % (TAIL_SEAM,))
    if (war_full and len(war_full) >= len(champ_full)
            and all(abs(float(war_full[t]) - float(war[t])) < 0.006
                    for t in range(HORIZON))):
        return [float(w) for w in war_full[HORIZON:len(champ_full)]], "served_path"
    full = fm.chain_aging_tail([float(w) for w in war[:HORIZON]],
                               [float(w) for w in champ_full], HORIZON,
                               len(champ_full))
    return [float(w) for w in full[HORIZON:]], "recomputed"
# Exposure floor for the veteran universe: at least one of the last three
# seasons with a real sample (sub-cup-of-coffee players add noise, not
# signal, and the engine's reliability buckets were fitted above this).
MIN_PA, MIN_IP = 100, 30

# ============================================================================
# REST-OF-SEASON TALENT BASIS  (owner decision, 2026-08-05)
# ============================================================================
# WHICH SEASON'S TALENT the rest-of-season (rental) leg is priced on. Read in
# exactly ONE place - `ros_talent_basis()` below - so reverting is this line and
# nothing else. Every served row publishes the tag that basis produced
# (`rosBasis`), and the payload root stamps `ros_talent_basis`.
#
#   "de_aged"       SHIPPED (owner decision, 2026-08-05). The remainder of the
#                   IN-PROGRESS season is priced on war[0] scaled by the exact
#                   one-year INVERSE of the platform's own aging operator
#                   (`deaged_year1` below, the inverse of fa_market._decay_path).
#                   war[0] is the FIRST_SEASON projection, i.e. ONE AGING YEAR
#                   PAST the season actually being sold, so for a veteran the
#                   un-de-aged basis is biased low.
#   "first_season"  the pre-2026-08-05 behaviour: price the remainder on war[0]
#                   itself, no de-aging. SET THIS TO REVERT - nothing else has
#                   to change; rows then ship rosBasis="first_season".
#
# A third TAG, never a setting: rows whose de-aging is UNRESOLVED ship
# rosBasis="first_season_unresolved" even under "de_aged". The policy and the
# measurement behind it are documented on `ros_talent_basis` below.
#
# RECORDED DISSENT (carried here so it is not lost - see
# docs/ros-talent-basis-2026-08-05/DECISION.md for the full numbers). The
# DIRECTION is right and is measured: the de-aging multiplier is monotone in age
# (median 0.77x at 22, 1.01x at 26, 1.22x at 30, 1.40x at 34, 1.64x at 37,
# re-measured 2026-08-05 over 954 rest-of-season rows). The MAGNITUDE is not
# obviously credible as a ONE-STEP operator: +40% of talent at age 34, and 124
# of the 820 resolved rows move more than 1.5x. This is the FORWARD decay path
# read backwards, and those curves are fitted on SURVIVORS, so inverting them
# for an INDIVIDUAL is an assumption, not a measurement. Nothing in this tree
# validates a one-step de-aging operator against observed same-player
# year-over-year WAR. Shipped anyway, by owner decision.
ROS_TALENT_BASIS = "de_aged"
ROS_TALENT_BASES = ("de_aged", "first_season")

# Per-600-PA / per-250-BF denominators: the units fa_market._decay_path carries
# the WAR RATE in. Defined once so the inverse cannot drift from the forward.
_PER_EXPOSURE = {"hit": 600.0, "pit": 250.0}

# A champion year-1 at or below this makes the de-aging RATIO undefined (0/0,
# and outright sign-flipping where it is negative). Those rows are UNRESOLVED
# and fall back to the first_season basis with their own published tag - they
# do not silently take a 1.0 multiplier. See `deaged_year1`.
DEAGE_MIN_CHAMP_WAR = 0.05


def recent_history(seasons_by_year: dict[int, dict],
                   first_season: int) -> list[dict]:
    """The three-season history window the veteran engine projects from, newest
    first. One definition, so every caller windows identically."""
    return [seasons_by_year[t] for t in (first_season - 1, first_season - 2,
                                         first_season - 3)
            if t in seasons_by_year]


def _side_in_universe(side: str, hist: list[dict]) -> bool:
    """The per-side exposure gate the served veteran row itself passed.

    NOT optional in the de-aging operator: a position player with 10 mop-up IP
    across three seasons has a 'pit' corpus row, and an early draft of the probe
    de-aged that side too - Miguel Rojas came out 0.67 -> 3.50 WAR (5.2x) on a
    pitching exposure the served row does not contain, because the pitcher pt
    delta at 38 (-99 BF) was added back to a ~4 BF projection.
    """
    if side == "hit":
        return max(h.get("pa") or 0 for h in hist) >= MIN_PA
    return max(h.get("ip") or 0 for h in hist) >= MIN_IP


def deaged_year1(hist_by_side: dict[str, list[dict]], first_season: int,
                 curves: dict, war_map: dict, league: dict,
                 in_progress: tuple[int, float] | None,
                 rate_only: bool = False) -> dict | None:
    """One-year de-aging of a veteran's champion year-1 WAR, as a RATIO.

    THE OPERATOR IS THE PLATFORM'S OWN AGING CURVE, RUN BACKWARDS. fa_market's
    `_decay_path` is the only WAR aging operator in the tree: moving INTO age a
    it ADDS `fp.curve_delta(curves, side, decay_role, "war_rate", a)` to the
    per-600-PA / per-250-BF WAR rate and `curve_delta(..., "pt", a)` to the
    projected exposure, then re-multiplies. Both deltas are ADDITIVE, so the
    step is exactly invertible: to walk one year BACK from age a, SUBTRACT the
    same two deltas evaluated at a.

    Returns {"ratio", "war1_champ", "war1_deaged", "sides"} or None when the
    de-aging is UNRESOLVED (no side clears the universe gate, or the champion
    year-1 is at/below DEAGE_MIN_CHAMP_WAR so the ratio is undefined). The
    caller decides what an unresolved row does; it must not become 1.0 here.

    `rate_only=True` un-ages the WAR RATE only, holding the Marcel exposure
    projection fixed - the less aggressive half of the operator. Production
    ships the full inverse (rate AND playing time); the variant exists so
    tools/ros_talent_basis_probe.py can keep measuring both from THIS function
    instead of a second copy of the arithmetic.

    Two-way players sum both sides before the ratio is taken, matching the way
    the served `war` path sums them.
    """
    tot_champ = tot_deaged = 0.0
    sides: list[dict] = []
    for side in ("hit", "pit"):
        hist = hist_by_side.get(side) or []
        if not hist or not _side_in_universe(side, hist):
            continue
        age_row = next((h for h in hist if h.get("age")), None)
        if age_row is None:
            continue
        age = age_row["age"] + (first_season - age_row["season"])
        try:
            proj = fp.project_player(hist, side, first_season, curves, league,
                                     age, in_progress=in_progress)
            if proj is None:
                continue
            war1 = fp.war_from_projection(proj, side, war_map, league,
                                          first_season)
        except Exception:                                     # noqa: BLE001
            continue
        expo = float(proj["pt_proj"] or 0.0)
        if expo <= 0.0 or war1 is None:
            continue
        per = _PER_EXPOSURE[side]
        drole = fp.profile_role(hist, side, proj["role"], league)
        rate = float(war1) / expo * per
        d_rate = fp.curve_delta(curves, side, drole, "war_rate", int(age))
        d_pt = fp.curve_delta(curves, side, drole, "pt", int(age))
        expo_back = expo if rate_only else max(0.0, expo - d_pt)
        w_back = max(0.0, rate - d_rate) * expo_back / per
        tot_champ += float(war1)
        tot_deaged += w_back
        sides.append({"side": side, "role": drole, "age": round(age, 1),
                      "expo": round(expo, 1), "war1": round(float(war1), 3),
                      "d_war_rate": round(d_rate, 4), "d_pt": round(d_pt, 2),
                      "deaged": round(w_back, 3)})
    if not sides or tot_champ <= DEAGE_MIN_CHAMP_WAR:
        return None
    return {"ratio": tot_deaged / tot_champ,
            "war1_champ": tot_champ, "war1_deaged": tot_deaged,
            "sides": sides}


def ros_talent_basis(war_now: float, deage) -> tuple[float, str]:
    """THE ONLY READ OF ROS_TALENT_BASIS. Returns (the talent the rest-of-season
    remainder is priced on, the tag published on the row as `rosBasis`).

    `deage` is a ZERO-ARGUMENT CALLABLE returning `deaged_year1`'s result or
    None. Lazy on purpose: flipping the constant back to "first_season" then
    also skips the work, so the revert is genuinely one line.

    UNRESOLVED ROWS (policy chosen 2026-08-05, after measuring them). The
    de-aging ratio is undefined where the champion year-1 is ~0, and where that
    year-1 is NEGATIVE a ratio would flip the sign of the priced talent.
    Measured on the 2026-08-05 artifact: 134 of the 954 rest-of-season rows are
    unresolved, ALL of them for that reason (none for a missing side), and every
    one of them has |war[0]| <= 0.46 - the population this policy governs is
    replacement-level and its dollars are small. Those rows FALL BACK TO THE
    FIRST_SEASON BASIS and SAY SO (rosBasis="first_season_unresolved"), rather
    than
      * taking a silent 1.0 multiplier, which would publish a de-aged basis that
        was never computed, or
      * taking an ADDITIVE de-aging, which for these rows would assert a talent
        change LARGER THAN THE PROJECTION ITSELF, off a denominator the model is
        telling us is noise.
    """
    if ROS_TALENT_BASIS not in ROS_TALENT_BASES:
        raise ValueError(f"ROS_TALENT_BASIS={ROS_TALENT_BASIS!r} is not one of "
                         f"{ROS_TALENT_BASES}; a typo here would silently "
                         "re-price every rental")
    if ROS_TALENT_BASIS == "first_season":
        return war_now, "first_season"
    d = deage()
    if d is None:
        return war_now, "first_season_unresolved"
    return war_now * d["ratio"], "de_aged"

# Two-way "if-healthy" calibration: a two-way player cannot hold a FULL
# dedicated-starter inning load on top of a full hitting season, so naively
# summing each side's playing-time-held (PTH) path double-books durability and
# overstates the healthy ceiling (Ohtani read 10.7/11.56 WAR - above any season
# he has ever posted). The pitching side's PTH is workload-discounted by this
# factor (~a two-way ~130-IP load vs a ~180-IP dedicated starter) before
# summing; hitting PTH (DH, ~full PA) is untouched, and the pricing `war` path
# is unaffected (surplus/value/FA pricing unchanged). Tuned so the if-healthy
# ceiling lands near Ohtani's realistic peak (~9.5, under any 10+ season).
TWO_WAY_PIT_PTH_FACTOR = 0.48

_BUCKET_ORDER = ("bust", "bench", "regular", "good", "star")


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None and v != [] and v != {}}


def _display_names() -> dict[int, str]:
    """{mlbam: display name} - the war_daily index inverted (the same
    identity source fa_ident resolves against, read in reverse)."""
    out: dict[int, str] = {}
    for _norm, cands in fa_ident.war_daily_index().items():
        for mid in cands:
            out.setdefault(mid, "")
    # second pass for the raw display string: war_daily_index normalizes
    # names away, so rebuild from the raw stint frames (war_source facade on
    # the displayed series, eWAR v2, named explicitly: display strings for
    # identity only, fWAR label epoch step D + U, 2026-10-03; the frames are
    # cached by pybaseball underneath).
    import pybaseball  # noqa: F401 - availability probe; frames come via war_source
    import war_source
    for side in ("bat", "pit"):
        try:
            df = war_source.stint_frame(side, provider="ewar_v2")
        except Exception:                                     # noqa: BLE001
            continue
        sub = df[df["mlb_ID"].notna()]
        for row in sub.itertuples(index=False):
            try:
                out[int(row.mlb_ID)] = str(row.name_common)
            except (TypeError, ValueError):
                continue
    return {k: v for k, v in out.items() if v}


# P-POSVAL: the Spotrac contract join copied ct["position"] onto the public row
# unvalidated, so malformed scrape rows shipped fielding-code strings as a
# position ("35" for Christopher Morel, "37" for Santiago Espinal on the
# 2026-07-24 payload - both with aav 0, i.e. the whole contract row was junk).
# Whitelist the vocabulary the surface actually renders; anything else leaves
# the engine's own role token in place instead of overwriting it with noise.
_VALID_POS = {"C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "OF", "DH", "IF",
              "INF", "SP", "RP", "P", "LHP", "RHP", "SIRP", "MIRP", "CL",
              "TWP", "UT", "UTIL"}


def _valid_pos(pos) -> bool:
    return isinstance(pos, str) and pos.strip().upper() in _VALID_POS


# EPOCH-SPOTRAC-1 (2026-10-03): the inline vet join wrote ct["position"] onto
# the row without the P-POSVAL check that _apply_contract runs, so when
# Spotrac's team pages began serving numeric codes in the 'Pos' column
# ("Jhoan Duran | 33 | 29"), 242 vets shipped pos '33', '32', '34' and so on,
# and the 128 pitchers among them rendered as hitter cards (mlb_player_export
# reads isPit from pos; _row_sides below splits on it too). The exporter holds
# no StatsAPI primary position, so the fallback is the engine's own role token
# (path["role"]: SP, RP or H), the same token _apply_contract leaves in place.
# SPOTRAC_POS_CODES_2026_10 fixed the parser (spotrac.SPOTRAC_POS_CODES maps the
# numeric ids, and an unknown value reads as None); this check stays as the guard.
def _vet_pos(two_way: bool, ct: dict | None, role: str) -> str:
    """The served `pos` of a veteran row: TWP for a two-way row, else the
    Spotrac contract position when it is a real position, else the role."""
    if two_way:
        return "TWP"
    pos = (ct or {}).get("position")
    if _valid_pos(pos):
        return pos.strip().upper()
    return role


# ============================================================================
# P-VETTEAM: team + contract identity resolution
# ============================================================================
# The Spotrac join is by NORMALIZED NAME and the roll-up drops any vet without a
# team (`if not tm: continue`). Two independent leaks, measured 2026-07-31 on the
# served payload: 361 of 1,319 vets carried no team and took 40.7 champion Y1 WAR
# out of Team Outlook. Causes:
#   1. Spotrac's team pages only list PRICED contracts (1,161 rows), so pre-arb
#      and optioned players are absent by construction - 356 of the 361.
#   2. Generational suffixes disagree between sources. Spotrac writes "Jazz
#      Chisholm", war_daily writes "Jazz Chisholm Jr." -> keys never met.
# The suffix mismatch also mis-AWARDED contracts: the WSN "Luis Garcia" deal
# joined mlbam 472610 (the reliever, on MIN) instead of 671277 (Luis Garcia Jr.,
# WSN), because the reliever's key matched exactly. Resolution below is
# mlbam-keyed and uses the observed club as the tiebreak.
_SUFFIX_TOKENS = {"jr", "sr", "ii", "iii", "iv"}


def _base_key(key: str) -> str:
    """Normalized key with trailing generational suffixes removed. Guarded at
    two remaining tokens so a genuinely two-token name ("Sammy Sr") survives."""
    parts = key.split("_")
    while len(parts) > 2 and parts[-1] in _SUFFIX_TOKENS:
        parts = parts[:-1]
    return "_".join(parts)


_TEAM_BY_MLBAM: dict[int, str] | None = None
_TEAM_SEEN_BY_MLBAM: dict[int, tuple[str, int]] | None = None
_FEED_ORG_BY_MLBAM: dict[int, tuple[str, str]] | None = None


def _team_by_mlbam(lookback: int = 4) -> dict[int, str]:
    """{mlbam: org code} - the club each player was last seen playing for.
    The season-free view of `_team_seen_by_mlbam`."""
    global _TEAM_BY_MLBAM
    if _TEAM_BY_MLBAM is None:
        _TEAM_BY_MLBAM = {m: org for m, (org, _s)
                          in _team_seen_by_mlbam(lookback).items()}
    return _TEAM_BY_MLBAM


def _team_seen_by_mlbam(lookback: int = 4) -> dict[int, tuple[str, int]]:
    """{mlbam: (org code, season)} - the club each player was last seen playing
    for, and the season he was seen there.

    Reads the StatsAPI season-stat splits the corpus build already caches (no
    new ingest); later seasons overwrite earlier ones, so the map reads as
    "most recent club seen". StatsAPI's season row for a traded player carries
    the club he played for LAST, so on the in-progress season this is the
    club that holds him now. Best-effort: an unavailable cache leaves this
    empty and every join falls back to exactly the pre-fix behaviour."""
    global _TEAM_SEEN_BY_MLBAM
    if _TEAM_SEEN_BY_MLBAM is not None:
        return _TEAM_SEEN_BY_MLBAM
    out: dict[int, tuple[str, int]] = {}
    try:
        import fa_sources
        from trades import canonical_org
    except ImportError:                                        # noqa: BLE001
        _TEAM_SEEN_BY_MLBAM = out
        return out
    for season in range(FIRST_SEASON - lookback, FIRST_SEASON):
        for group in ("hitting", "pitching"):
            try:
                splits = fa_sources.fetch_statsapi_season_stats(season, group)
            except Exception:                                  # noqa: BLE001
                log.warning("team map: statsapi %s %d unavailable", group, season)
                continue
            # `split`, not `sp`: the module-level `import salary_path as sp`
            # (line 59) is shadowed by a loop variable otherwise, which ruff
            # flags as F402 and which would make any later use of the module
            # inside this function silently reach for a stats split.
            for split in splits or []:
                pid = (split.get("player") or {}).get("id")
                name = (split.get("team") or {}).get("name")
                if not pid or not name:
                    continue
                org = canonical_org(name)
                if org:
                    out[int(pid)] = (org, season)
    _TEAM_SEEN_BY_MLBAM = out
    log.info("team map: %d mlbam -> org from statsapi season splits", len(out))
    return out


def _feed_org_by_mlbam() -> dict[int, tuple[str, str]]:
    """{mlbam: (canonical org, event date)} from MLB's transaction feed, the
    same resolver the /mlbstats/ boards repoint `team` with
    (bullpen_export.apply_current_team). Best-effort: an absent table or DB
    leaves it empty and the resolver below falls through to the stats club."""
    global _FEED_ORG_BY_MLBAM
    if _FEED_ORG_BY_MLBAM is not None:
        return _FEED_ORG_BY_MLBAM
    out: dict[int, tuple[str, str]] = {}
    try:
        from storage import authoritative_org_by_mlbam
        from trades import canonical_org
        for mid, (org, when) in (authoritative_org_by_mlbam() or {}).items():
            code = canonical_org(org) if org else None
            if code and when:
                out[int(mid)] = (code, str(when))
    except Exception:                                          # noqa: BLE001
        log.warning("club resolver: transaction feed unavailable; "
                    "serving the stats and contract clubs", exc_info=True)
        out = {}
    _FEED_ORG_BY_MLBAM = out
    log.info("club resolver: %d mlbam -> org from the transaction feed", len(out))
    return out


# CURRENT CLUB, NOT CONTRACT CLUB (2026-09-24, audit X03-02). `team` used to be
# the Spotrac contract club first, on the reading that the contract club is the
# paying club. It is only until the player is traded: the contract moves with
# him, and the monthly Spotrac scrape keeps the old club until the next pass.
# Measured on the served artifact before this change: 134 of the 1,129 vets
# the eWAR board also carries sat on a different club (Tarik Skubal DET on
# /projections/, LAD on /mlbstats/), 104 of them confirmed by MLB's transaction
# feed and the other 30 by StatsAPI's in-progress season row (numTeams 2+). The
# FA class 'from' column, the player links, the trade board org, the Team
# Outlook sums and the ledger's club rows all read this field.
#
# Order, newest evidence first:
#   1. feed         MLB's transaction feed, when the event falls in the current
#                   season or later (the same feed the /mlbstats/ boards use).
#   2. season       the club StatsAPI shows him playing for this season.
#   3. contract     the Spotrac contract club.
#   4. feed_prior   an older feed event, when it is no older than the last
#                   season he was seen playing.
#   5. last_seen    the club he was last seen playing for in an earlier season.
CLUB_SOURCES = ("feed", "season", "contract", "feed_prior", "last_seen")


def resolve_current_club(feed: tuple[str, str] | None,
                         seen: tuple[str, int] | None,
                         contract_club: str | None,
                         season_now: int) -> tuple[str | None, str | None]:
    """(org, source) for one player; pure, so the precedence is testable.

    `feed` is (org, ISO date) from the transaction feed, `seen` is (org,
    season) from StatsAPI, `contract_club` is the Spotrac club and
    `season_now` is the in-progress season."""
    feed_year = None
    if feed and feed[0]:
        try:
            feed_year = int(str(feed[1])[:4])
        except (TypeError, ValueError):
            feed_year = None
    if feed_year is not None and feed_year >= season_now:
        return feed[0], "feed"
    if seen and seen[0] and seen[1] >= season_now:
        return seen[0], "season"
    if contract_club:
        return contract_club, "contract"
    if feed_year is not None and (not seen or feed_year >= seen[1]):
        return feed[0], "feed_prior"
    if seen and seen[0]:
        return seen[0], "last_seen"
    return None, None


def _current_club(mlbam, ct: dict | None) -> tuple[str | None, str | None]:
    """resolve_current_club over the module's cached maps."""
    try:
        mid = int(mlbam)
    except (TypeError, ValueError):
        return (ct or {}).get("team_code"), ("contract" if (ct or {}).get("team_code") else None)
    return resolve_current_club(_feed_org_by_mlbam().get(mid),
                                _team_seen_by_mlbam().get(mid),
                                (ct or {}).get("team_code"), FIRST_SEASON - 1)


# Per-run disclosure of where each veteran's `team` came from; reset by
# _veteran_rows and published as the payload's `team_basis` block.
# {mlbam: (source, contract club or None)}.
_TEAM_BASIS_CENSUS: dict = {}


def _vet_club(mlbam, ct: dict | None) -> str | None:
    """_current_club for a veteran row, recorded for the `team_basis` block."""
    club, src = _current_club(mlbam, ct)
    if mlbam is not None:
        _TEAM_BASIS_CENSUS[mlbam] = (src, (ct or {}).get("team_code"))
    return club


def _resolve_contracts(mlbams, names: dict[int, str], contracts: dict[str, dict],
                       teams: dict[int, str]) -> tuple[dict[int, dict], dict[str, list[int]]]:
    """Assign at most one Spotrac contract per mlbam.

    Returns ({mlbam: contract}, {contract_key: [contested mlbam, ...]}). A
    contract is claimed by the exact normalized key first and by the
    suffix-stripped key second. When several players claim the same contract,
    the one whose OBSERVED club matches the contract's team wins outright;
    if that does not single anyone out the contract is left contested and the
    caller breaks the tie on projected WAR (the pre-fix behaviour)."""
    claims: dict[str, list[int]] = {}
    for mid in mlbams:
        nm = names.get(mid)
        if not nm:
            continue
        ekey = normalize_key(nm)
        for ck in (ekey, _base_key(ekey)):
            if ck in contracts:
                claims.setdefault(ck, []).append(mid)
                break
    assigned: dict[int, dict] = {}
    contested: dict[str, list[int]] = {}
    for ck, cands in claims.items():
        ct = contracts[ck]
        if len(cands) == 1:
            assigned[cands[0]] = ct
            continue
        tm = ct.get("team_code")
        agree = [m for m in cands if tm and teams.get(m) == tm]
        if len(agree) == 1:
            assigned[agree[0]] = ct
        else:
            contested[ck] = cands
    return assigned, contested


def _join_contract(c: dict, slug_to_org: dict[str, str]) -> dict:
    """One collapsed Spotrac row as the projections join reads it.

    A STATUS-ONLY row (spotrac.is_status_only: no positive money year, no
    signed_through) keeps its status_by_year, position and club, carries
    aav_usd None rather than 0, and is marked status_only so it never counts as
    a contract for the plain-key award (`_awards_plain_key`). Since the
    2026-10-03 refetch Spotrac's year columns start at 2027, and a player whose
    only money was 2026 reads this way; served as a $0 AAV he showed on 716 of
    1,400 veteran rows."""
    from spotrac import is_status_only
    out = {**c, "team_code": slug_to_org.get(c.get("team_slug"))}
    if is_status_only(c):
        out["aav_usd"] = None
        out["status_only"] = True
    return out


def _awards_plain_key(ct: dict | None) -> bool:
    """May this contract hand a collided name its plain key? Only a PRICED one.
    A status-only row says which club controls a player, not which of two
    same-named players is the flagship, so it never moves a plain key."""
    return bool(ct) and not ct.get("status_only")


def _award_winner(rows: list[dict], ct: dict | None) -> dict | None:
    """The claimant a contested contract is awarded to: the highest projected
    WAR row, and nobody when the contract is absent or status-only."""
    if not rows or not _awards_plain_key(ct):
        return None
    return max(rows, key=lambda m: m.get("warTotal") or 0.0)


def _season_value_usd(war: float, t: int, dpw_level: float) -> float:
    """One projected season priced on the platform's convex tier curve at
    the winter's ex-ante $/WAR level, escalated t seasons out. In unified
    $/WAR path mode (VAL_5 row 6) season FIRST_SEASON + t at its own level;
    dpw_level and the escalator are not read."""
    if vf.dpw_path_active():
        return vf.season_value_usd(war, FIRST_SEASON + t)
    base_flat = float(vf._config()["dollars_per_war"]["flat"])
    infl = float(vf._config().get("dollars_per_war_inflation", 0.05))
    return vf.tiered_war_value_usd(war) * (dpw_level / base_flat) * ((1 + infl) ** t)


def _ros_surplus_usd(war_now: float, cur_sal: float, ros_frac: float,
                     dpw_level: float) -> float:
    """The rest-of-season (rental) surplus: ONE proration factor applied to the
    WHOLE full-season surplus, f * (V(w_full) - salary_full).

    Extracted to module level so the convention has a single call site and a
    test can pin it against hand arithmetic. The long WHY - and the measured
    size of the V(f*w) error this replaced - lives at the call site in
    `_apply_contract`. Undiscounted and un-escalated (t=0) by construction.

    `war_now` is WHATEVER THE TALENT BASIS PRODUCED (see ROS_TALENT_BASIS): the
    de-aged in-progress-season talent by default, war[0] under "first_season".
    This function does not know or care which; it only prorates.

    Unified $/WAR path mode (VAL_5 row 9): the in-progress season N at its own
    level, compounded forward to B by d(N) (unclipped).
    """
    if vf.dpw_path_active():
        n = FIRST_SEASON - 1
        return float(ros_frac) * (vf.season_value_usd(float(war_now), n)
                                  - float(cur_sal)) * vf.season_discount(n)
    return float(ros_frac) * (_season_value_usd(float(war_now), 0, dpw_level)
                              - float(cur_sal))


# ============================================================================
# The projected per-season $/WAR path (VAL_5): the unified branches
# ============================================================================
# While value_framework.dpw_path_active() is False every function above runs
# its legacy branch verbatim. While it is True (the flip, after the fWAR
# label epoch's step Z): season FIRST_SEASON + t is priced at its own level
# (row 6), discounted by d(s) at the stored nominal rate R to the base season
# (rows 7-8, the tender cliff included), the in-progress season compounds
# forward to B (row 9), and arbitration and minimum seasons carry the companion
# index inside the priced surplus only, published per season as salIdx beside
# salPath, which itself stays unscaled (row 18).

def _unified_salary(c: dict) -> float:
    """The salary a priced season nets in unified mode (row 18): a contracted
    season its contract dollars; an arbitration season the projected award x
    the arbitration index; a pre-arbitration season the projected minimum x the
    minimum's index (league_min_for over the carried table minimum)."""
    usd = float(c["usd"])
    if c.get("src") == "contract":
        return usd
    s = int(c["season"])
    if sp.is_cuttable(c):
        return usd * vf.arb_index_scale(s)
    carried = float(sp.league_min_usd(s))
    return usd * (vf.league_min_for(s, legacy=carried) / carried) if carried else usd


def _unified_salary_index(c: dict) -> float:
    if c.get("src") == "contract":
        return 1.0
    usd = float(c["usd"])
    return _unified_salary(c) / usd if usd else 1.0


def _unified_path_surplus(seasons, war_px, dpw):
    """(d_usd, sur) of a salary path in unified mode: V(w, s) - salary x index."""
    d_usd, sur = [], []
    for c in seasons:
        if c["usd"] is None:
            d_usd.append(None)
            sur.append(None)
            continue
        w = war_px[c["t"]] if c["t"] < len(war_px) else None
        d = _season_value_usd(w or 0.0, c["t"], dpw) - _unified_salary(c)
        d_usd.append(d)
        sur.append(round(d / 1e6, 1))
    return d_usd, sur


def _band_npv_unified(path, war, dpw, r, which: str, run_cliff: bool) -> float:
    """_band_npv in unified mode: the award band endpoint carries the same index
    as the point salary, the discount is the stored R and the base factor d(B)."""
    d = []
    for c in path["seasons"]:
        if c["usd"] is None:
            d.append(None)
            continue
        s = c.get(which)
        s = c["usd"] if s is None else s
        w = war[c["t"]] if c["t"] < len(war) else None
        d.append(_season_value_usd(w or 0.0, c["t"], dpw) - float(s) * _unified_salary_index(c))
    d, _ = sp.club_option_floor(path["seasons"], d)
    d0 = vf.season_discount(FIRST_SEASON)
    if run_cliff:
        cuttable = [sp.is_cuttable(c) and c["usd"] is not None
                    for c in path["seasons"]]
        npv, _ = sp.tender_cliff([x or 0.0 for x in d], cuttable, r)
        return npv * d0
    return d0 * sum(x / ((1 + r) ** t) for t, x in enumerate(d) if x is not None)


def _stamp_dpw_path(payload: dict) -> dict:
    """Row 10 in unified mode: the stamps name P(B), the path by season and the
    pricing basis; the escalator stamp goes (unified mode never reads it)."""
    b = FIRST_SEASON
    payload["dpw_usd"] = int(round(vf.price_level(b)))
    payload.pop("dpw_infl", None)
    payload["dpw_path_by_season"] = {str(s): int(round(vf.price_level(s)))
                                     for s in range(b, b + HORIZON)}
    payload["pricing_basis"] = vf.dpw_path_summary()
    notes = payload.get("notes") or []
    for i, n in enumerate(notes):
        if isinstance(n, str) and n.startswith("dollars:"):
            notes[i] = ("dollars: each season priced on the convex tier curve at its own level on the "
                        f"one written $/WAR path ({vf.dpw_option('level_basis')} basis, escalator "
                        f"{vf.g_ref() * 100:.2f}%/yr), discounted at the stored nominal rate "
                        f"{vf.nominal_rate() * 100:.4f}% to {vf.discount_base_season():.0f}; "
                        + n.split("; ", 1)[1] if "; " in n else n)
    return payload


def _winter_dpw(first_season: int) -> float:
    """Ex-ante $/WAR level for the first projected season: the level of THE
    one written series (data/fa_dpw_series.json pricing.level_usd, VAL_1,
    2026-09-25), the same number /fa/ prices the class at and prospect
    surplus prices every season at. Falls back to the valuation set's flat
    rate only when no series is written."""
    level = fm.written_pricing_level_usd(first_season)
    return level if level else fa_class._flat_dpw_usd()


# ============================================================================
# Veterans - the FA engine over the whole league
# ============================================================================

def _veteran_rows(corpus: dict, names: dict[int, str],
                  contracts: dict[str, dict], dpw: float) -> list[dict]:
    league = corpus["league"]
    curves, war_map = fp.fitted_models(corpus, FIRST_SEASON - 1)
    frac = fp.season_fraction(league, FIRST_SEASON - 1)
    in_prog = (FIRST_SEASON - 1, frac)
    r = float(vf._config()["discount_rate"])
    _unified = vf.dpw_path_active()
    if _unified:
        # VAL_5 rows 7-8: contracts discount at the stored nominal rate R, and
        # d(B) is the base factor (1 under OD-3 base_2027).
        r = vf.nominal_rate()
        _d0 = vf.season_discount(FIRST_SEASON)
    # REST-OF-SEASON CONTROL (2026-08-03). Fraction of the in-progress season
    # still to be played. season_fraction() returns the ELAPSED share and falls
    # back to 1.0 when the league PA substrate is missing, so a broken estimate
    # lands here as 0.0 remaining: the rest-of-season leg silently prices at
    # nothing rather than inventing a full season of value. Clamp is defensive.
    ros_frac = max(0.0, min(1.0, 1.0 - frac))

    by_player: dict[str, dict[int, dict[int, dict]]] = {
        "hit": defaultdict(dict), "pit": defaultdict(dict)}
    for side in ("hit", "pit"):
        for row in corpus[side]:
            if row.get("mlbam") and row["season"] >= FIRST_SEASON - 3:
                by_player[side][row["mlbam"]][row["season"]] = row

    # Spotrac contracts are keyed by NORMALIZED NAME only (no mlbam), so two active
    # players sharing a name (Will Smith C/RP, Max Muncy LAD/ATH) would both join the
    # SAME contract -- corrupting team/pos/salary/surNpv and the team outlook. The
    # resolver above assigns each contract to ONE mlbam (exact key, then
    # suffix-stripped, then observed-club tiebreak); anything it still cannot single
    # out is awarded after the loop to the highest-projected-WAR row (Spotrac's
    # collapse keeps the highest-AAV deal, which belongs to the flagship player).
    # Everyone else honestly carries no contract rather than a wrong one.
    _vet_ids = set(by_player["hit"]) | set(by_player["pit"])
    _name_counts: dict[str, int] = {}
    for _mid in _vet_ids:
        _nm = names.get(_mid)
        if _nm:
            _k = normalize_key(_nm)
            _name_counts[_k] = _name_counts.get(_k, 0) + 1
    _teams = _team_by_mlbam()
    _TEAM_BASIS_CENSUS.clear()
    _ct_by_mlbam, _contested = _resolve_contracts(_vet_ids, names, contracts, _teams)
    _contested_by_mlbam = {m: ck for ck, ms in _contested.items() for m in ms}

    # ---- rest-of-season talent basis (see ROS_TALENT_BASIS) ----------------
    _deage_memo: dict[int, dict | None] = {}

    def _deage(mlbam: int) -> dict | None:
        """Memoized one-year de-aging for one player. Built from the same
        three-season window the projection itself uses, and gated per side by
        the same universe floors, so it can never de-age a side the served row
        does not contain."""
        if mlbam not in _deage_memo:
            hist_by_side = {}
            for _s in ("hit", "pit"):
                _h = recent_history(by_player[_s].get(mlbam) or {}, FIRST_SEASON)
                if _h:
                    hist_by_side[_s] = _h
            _deage_memo[mlbam] = deaged_year1(hist_by_side, FIRST_SEASON, curves,
                                              war_map, league, in_prog)
        return _deage_memo[mlbam]

    def _ros_talent_basis(m: dict, war_now: float) -> tuple[float, str]:
        """Bind this row to the module-level switch (`ros_talent_basis`), which
        is where ROS_TALENT_BASIS is read and where the unresolved-row policy is
        documented. A row with no mlbam cannot be de-aged and is unresolved."""
        return ros_talent_basis(
            war_now, lambda: _deage(m["mlbam"]) if m.get("mlbam") else None)

    def _apply_contract(m: dict, ct: dict) -> None:
        """Stamp the contract-dependent fields (pos/team/thru/aav/sur/surNpv) onto a
        built row. Shared by the inline (unambiguous) join and the post-loop
        collision-winner award so both paths price identically."""
        if not m.get("twoWay") and _valid_pos(ct.get("position")):
            m["pos"] = ct["position"].strip().upper()
        # The club is re-resolved WITH this contract (the post-loop collision
        # award reaches here with a row built contract-less): a contract club
        # only wins when neither the feed nor this season's stats place him.
        _club = _vet_club(m.get("mlbam"), ct)
        if _club:
            m["team"] = _club
        sal = {int(y): int(v) for y, v in (ct.get("salary_by_year") or {}).items()}
        if ct.get("signed_through") is not None:
            m["thru"] = ct["signed_through"]
        if ct.get("aav_usd") is not None:
            m["aav"] = ct["aav_usd"]
        sur = []
        npv = 0.0
        any_sal = False
        for t in range(HORIZON):
            season = FIRST_SEASON + t
            s_usd = sal.get(season)
            if s_usd is None:
                sur.append(None)
                continue
            any_sal = True
            v_usd = _season_value_usd(m["war"][t], t, dpw)
            d_usd = v_usd - s_usd
            sur.append(round(d_usd / 1e6, 1))
            npv += d_usd / ((1 + r) ** t)
        if _unified:
            npv *= _d0
        if any_sal:
            m["sur"] = sur
            m["surNpv"] = int(npv)
        # WHICH SEASONS A CONTRACT PRICED, recorded rather than re-derived.
        # `_apply_salary_paths` runs last and must never re-price a season this
        # function already priced (rule 1 of the salary path, and the letter of
        # test_arb_export::test_gate_c_never_overwrites_a_real_contract moved
        # from the ROW to the SEASON). Both private keys are stripped by that
        # pass, which is the last thing to touch a veteran row.
        m["_salYears"] = sorted(sal)
        # REST-OF-SEASON CONTROL (2026-08-03, owner ask). Until now a contract
        # whose last season is the one in progress produced no `sur` and no
        # `surNpv` at all: the horizon starts at FIRST_SEASON, so the months a
        # club still controls the player were worth exactly zero everywhere on
        # the platform. That made every deadline rental "not tradeable" (the
        # question that opened docs/efv-2026-07-31/TRADE_BOARD_COVERAGE.md,
        # whose answer for A.J. Minter is superseded here: a rental IS a trade
        # asset, it is simply a small one).
        #
        # Deliberate conventions, so the two legs stay comparable:
        #   * UNDISCOUNTED and un-escalated (t=0). This is money and wins now,
        #     and surNpv's own discount origin is t=0 at FIRST_SEASON, so a
        #     naive t=-1 would have inflated the remainder by (1+r).
        #   * TALENT BASIS: the DE-AGED in-progress-season talent (owner
        #     decision, 2026-08-05; ROS_TALENT_BASIS at the top of this file,
        #     which is also the one-line revert). It still deliberately does not
        #     read 2026 results to date, which measure what the SELLING club
        #     already banked; the only question here is WHICH SEASON'S TALENT
        #     the remainder is priced on, not whether to re-bank April.
        #
        #     WHY IT MOVED. war[0] is the FIRST_SEASON (2027) projection, i.e.
        #     ONE AGING YEAR PAST the 2026 season actually being sold, so for a
        #     veteran the remainder was biased low. The de-aging is the exact
        #     inverse of the platform's OWN aging operator (fa_market._decay_path
        #     adds curve_delta war_rate and pt at the age it is moving INTO;
        #     `deaged_year1` subtracts the same two at the player's age), taken
        #     as a RATIO against the champion year-1 and applied to the shipped
        #     war[0] so the ML quantile head's information survives and only the
        #     aging timing moves. tools/ros_talent_basis_probe.py measures the
        #     shipped basis against the alternatives from THIS function
        #     -> data/ros_talent_basis_probe.json.
        #
        #     DISSENT ON THE RECORD (executing agent, 2026-08-05; full numbers
        #     in docs/ros-talent-basis-2026-08-05/DECISION.md). DIRECTION RIGHT,
        #     MAGNITUDE NOT OBVIOUSLY CREDIBLE AS A ONE-STEP OPERATOR: the
        #     median multiplier is monotone in age (0.77x at 22, 1.01x at 26,
        #     1.22x at 30, 1.40x at 34, 1.64x at 37) but +40% of talent at 34 is
        #     the FORWARD decay path's own steepness read backwards, and those
        #     curves are fitted on SURVIVORS, so inverting them for an
        #     INDIVIDUAL is an assumption rather than a measurement. 124 of 820
        #     resolved rows move more than 1.5x. Nothing in this tree validates
        #     a one-step de-aging operator against observed same-player
        #     year-over-year WAR. Shipped by owner decision over that objection.
        #
        #     THE OTHER PUBLISHED BASES REMAIN WORSE, not better: warPTH[0]
        #     (if-healthy) is a DIFFERENT QUANTITY and moves every row up
        #     (+$1.39M median, 54 sign flips) - surplus prices expected value,
        #     not if-healthy; and warY1Champ is simply the non-ML model.
        #   * BOTH LEGS PRORATE THE SAME FULL-SEASON QUANTITY: production is
        #     f * V(w_full), salary is f * salary_full. Until 2026-08-04d the
        #     production leg priced V(f * w_full) instead - it ran the SHRUNKEN
        #     remainder through the convex tier kernel, which classifies a
        #     season by its OWN WAR (value_framework.py:457-482), so a 0.69-WAR
        #     pitcher's 30% remainder was billed at a 0.21-WAR player's per-win
        #     rate while his salary was billed at his real rate. That is a
        #     mechanical proration error, not a valuation choice: the two legs
        #     were prorated on different bases.
        #
        #     THE SIZE OF THE ERROR WAS MEASURED FIRST (2026-08-04, lane R5.2,
        #     re-measured at f=0.301 before this edit) and it refuted the older
        #     intuition in this comment, which claimed the old form under-priced
        #     a STAR rental. The gap f*V(w) - V(f*w) is SINGLE-PEAKED and dies
        #     EXACTLY AT AND ABOVE w = 2.5/f = 8.31 WAR, because the platform's
        #     own curve is LINEAR above the top tier center (2.5) and proration
        #     is exact on a linear segment - there is no convexity left to
        #     mis-price at the top. READ THE UNITS: in RELATIVE terms the gap is
        #     worst for the MID-tier add (it peaks at 88% of the old price near
        #     w=2.46, and is +79% at w=3.00, which is the "+0.79" R5.2 recorded);
        #     in DOLLARS it peaks much higher up the talent scale, at +$10.09M
        #     near w=5.36. Both statements are the same curve.
        #     Clay Holmes (war[0]=0.69, $8,941,176, f=0.301) moves
        #     -$762,764 -> -$715,920, i.e. +$46,844.
        #     Population effect on the 2026-08-04 artifact: 969 vet rows carry a
        #     RoS leg, 421 move by >= $1, NONE move down (the gap is >= 0
        #     everywhere by Jensen), mean +$0.91M, max +$10.08M (Juan Soto), and
        #     4 surTotal sign flips (Lindor, Devers, Schwarber, Suzuki all
        #     negative -> positive). Expect trade-board reordering.
        #
        #     `rosWar` PUBLISHES basis_war * f - the WAR the acquiring club
        #     actually receives, on the SAME talent the dollars were priced off.
        #     It is a display field, and it must not describe a different
        #     quantity than surRos does; `rosBasis` names which basis produced
        #     both, so a served row is self-describing.
        #
        #     A concentration premium may still exist in what clubs PAY; that
        #     is a different claim and it is UNMEASURED. The backtest is
        #     BLOCKED, not merely unfinished: historical per-player salary and
        #     in-season WAR splits do not exist in this tree, and the only
        #     multi-year return valuation (xfv_history) is 0% covered before
        #     2021 and survivor-selected after, leaving 8 usable deadline
        #     trades against a pre-registered floor of 40. Unblocks, in order of
        #     cheapness: trade_value_history has snapshotted every board member
        #     contemporaneously since 2026-06-25 and accrues an unbiased
        #     price-paid series on its own; failing that, per-player historical
        #     salary by season, then in-season WAR splits or dated game logs.
        #     Do NOT ship a premium constant before one of those lands.
        #   * Salary is prorated too: the acquiring club pays only the balance.
        # Applies to EVERY vet with a current-season salary, not just expiring
        # ones. Pricing Minter's remainder while ignoring Judge's would invent
        # a new inconsistency of exactly the class this codebase keeps paying
        # to remove.
        ros_d = None
        cur_sal = sal.get(FIRST_SEASON - 1)
        war_now = (m.get("war") or [None])[0]
        if cur_sal is not None and war_now is not None and ros_frac > 0.0:
            basis_war, basis_tag = _ros_talent_basis(m, float(war_now))
            ros_war = basis_war * ros_frac            # PUBLISHED (display) WAR
            ros_d = _ros_surplus_usd(basis_war, cur_sal, ros_frac, dpw)
            m["surRos"] = round(ros_d / 1e6, 1)
            m["rosWar"] = round(ros_war, 2)
            m["rosFrac"] = round(ros_frac, 3)
            m["rosBasis"] = basis_tag
        # What the player is worth to ACQUIRE right now: the balance of the
        # current season plus the NPV of every controlled season after it.
        # `surNpv` keeps its old meaning (FIRST_SEASON onward) so /projections/
        # and any external reader of that field are unchanged.
        if ros_d is not None or any_sal:
            m["surTotal"] = int((ros_d or 0.0) + npv)
        # The UNROUNDED rest-of-season leg. `surRos` is published to 0.1M and
        # surTotal was built from the raw float, so re-adding the published
        # field would move surTotal by up to $50k on every row that carries
        # one. The salary-path pass rebuilds surTotal and needs the same float.
        if ros_d is not None:
            m["_rosUsd"] = ros_d

    out: list[dict] = []
    _collision_rows: dict[str, list[dict]] = {}
    for mlbam in _vet_ids:
        sides = {}
        for side in ("hit", "pit"):
            seasons = by_player[side].get(mlbam) or {}
            hist = [seasons[t] for t in (FIRST_SEASON - 1, FIRST_SEASON - 2,
                                         FIRST_SEASON - 3) if t in seasons]
            if not hist:
                continue
            if side == "hit":
                if max(h.get("pa") or 0 for h in hist) < MIN_PA:
                    continue
            elif max(h.get("ip") or 0 for h in hist) < MIN_IP:
                continue
            sides[side] = hist
        if not sides:
            continue
        # Two-way (the Ohtani fix): project BOTH sides through the engine
        # and SUM the season paths - a two-way player IS both stat lines,
        # not the larger one. Per-side paths ship too (warHit/warPit) so
        # the player page can render both sections. Bands sum per-side
        # quantiles (a conservative width: the sides aren't perfectly
        # correlated - disclosed in the export notes).
        two_way = len(sides) == 2
        paths: dict[str, dict] = {}
        ages: dict[str, float] = {}
        for s_key, hist_s in sides.items():
            # Anchor the age offset to the row that supplied the age.
            age_row = next((h for h in hist_s if h.get("age")), None)
            if age_row is None:
                continue
            age_s = age_row["age"] + (FIRST_SEASON - age_row["season"])
            p_s = fm.contract_war_path(hist_s, s_key, FIRST_SEASON, HORIZON,
                                       age_s, curves, war_map, league,
                                       in_progress=in_prog)
            if p_s is not None:
                paths[s_key] = p_s
                ages[s_key] = age_s
        if not paths:
            continue
        two_way = two_way and len(paths) == 2
        if two_way:
            def _sum_arr(key):
                a = paths["hit"].get(key)
                b = paths["pit"].get(key)
                if not a or not b:
                    return None
                return [round((a[t] or 0) + (b[t] or 0), 2)
                        for t in range(min(HORIZON, len(a), len(b)))]
            war_arr = _sum_arr("war_by_year")
            # Champion MEAN path (both sides summed) for the team roll-up - the
            # displayed war_arr may be the median-like ML quantile head, which
            # must never be summed across a roster.
            champ_arr = _sum_arr("war_by_year_champ") or war_arr
            # If-healthy display path: workload-discount the pitching side's PTH
            # (a two-way arm can't carry a full starter's innings on top of a
            # full hitting season) before summing. See TWO_WAY_PIT_PTH_FACTOR.
            _hit_pth = paths["hit"].get("war_by_year_pth")
            _pit_pth = paths["pit"].get("war_by_year_pth")
            if _hit_pth and _pit_pth:
                pth_arr = [round((_hit_pth[t] or 0)
                                 + TWO_WAY_PIT_PTH_FACTOR * (_pit_pth[t] or 0), 2)
                           for t in range(min(HORIZON, len(_hit_pth), len(_pit_pth)))]
            else:
                pth_arr = _sum_arr("war_by_year_pth")   # if-healthy display path
            # Band combination at assumed cross-side correlation rho=0.5
            # (a player's hitting and pitching seasons share health/PT
            # shocks but not skill shocks - a documented assumption, less
            # conservative than the previous straight quantile sum).
            _RHO = 0.5
            def _comb_band(key, sign, base=None):
                # `base` is the summed path the band centres on: the served five
                # seasons by default, the full-length path for the contract
                # tail's band (TAIL_BAND), on the same combination rule.
                base = war_arr if base is None else base
                lo_h = paths["hit"].get(key); lo_p = paths["pit"].get(key)
                if not lo_h or not lo_p or not base:
                    return None
                out = []
                mh_ = paths["hit"]["war_by_year"]; mp_ = paths["pit"]["war_by_year"]
                for tt in range(min(len(base), len(lo_h), len(lo_p), len(mh_), len(mp_))):
                    dh = abs((mh_[tt] or 0) - (lo_h[tt] or 0))
                    dp = abs((mp_[tt] or 0) - (lo_p[tt] or 0))
                    d = (dh * dh + dp * dp + 2 * _RHO * dh * dp) ** 0.5
                    out.append(round(base[tt] + sign * d, 2))
                return out
            p10_arr = _comb_band("war_by_year_p10", -1)
            p90_arr = _comb_band("war_by_year_p90", +1)
            path = paths.get("hit") or paths.get("pit")   # role/meta carrier
            age = max(ages.values())
        else:
            side = next(iter(paths))
            path = paths[side]
            age = ages[side]
            war_arr = path["war_by_year"][:HORIZON]
            champ_arr = (path.get("war_by_year_champ") or path["war_by_year"])[:HORIZON]
            pth_arr = (path.get("war_by_year_pth") or war_arr)[:HORIZON]   # if-healthy display path
            # `or None` after the slice never fired ([None] is truthy), so a vet path
            # with no band shipped warP10/warP90 = [None] (a 1-elem null list) instead
            # of None -- gate on the source list being present first.
            p10_arr = (path.get("war_by_year_p10") or None) and path["war_by_year_p10"][:HORIZON]
            p90_arr = (path.get("war_by_year_p90") or None) and path["war_by_year_p90"][:HORIZON]
        name = names.get(mlbam)
        if not name:
            continue
        # The champion MEAN path at its full length (fa_market.MAX_PATH_YEARS,
        # both sides summed on a two-way row): how far the contract tail may
        # run, and the WAR it prices on under TAIL_SEAM "champion_level".
        # Private; stripped by _strip_private once the salary path pass has
        # used it.
        _cf = [paths[s].get("war_by_year_champ") or paths[s]["war_by_year"] for s in paths]
        champ_full = [round(sum(float(a[t] or 0.0) for a in _cf), 2)
                      for t in range(min(len(a) for a in _cf))]
        # The SERVED path at its full length (TAIL_SEAM "chained", owner answer
        # VAL2-Q1): each side's war_by_year, whose seasons past the horizon are
        # fa_market.chain_aging_tail (the champion's aging curve chained from
        # that side's 2031 WAR), summed across sides on a two-way row exactly
        # as `war` is. Private; stripped with the champion path.
        _wf = [paths[s]["war_by_year"] for s in paths]
        war_full = [round(sum(float(a[t] or 0.0) for a in _wf), 2)
                    for t in range(min(len(a) for a in _wf))]
        # Its P10/P90 at full length (TAIL_BAND, owner answer VAL2-Q3): each
        # side's war_by_year_p10_open/p90, whose seasons past the horizon are
        # the same chain_aging_tail applied to the 2031 P10/P90 head (the FA
        # module's seam; the P10 one without the zero floor, owner answer
        # VAL2-Q3-REVIEW (b)), combined across sides on a two-way row by the
        # same rho rule as the five printed seasons. A side with no open
        # carrier (a champion-only path, already floored at every season)
        # reads war_by_year_p10. Private; stripped.
        _k10 = ("war_by_year_p10_open"
                if not TAIL_BAND_P10_FLOOR and all(paths[s].get("war_by_year_p10_open") for s in paths)
                else "war_by_year_p10")
        if two_way:
            p10_full = _comb_band(_k10, -1, war_full)
            p90_full = _comb_band("war_by_year_p90", +1, war_full)
        else:
            p10_full = path.get(_k10) or None
            p90_full = path.get("war_by_year_p90") or None
        _nkey = normalize_key(name)
        _ambiguous = _name_counts.get(_nkey, 0) > 1
        ct = _ct_by_mlbam.get(mlbam)
        m = {
            # Collided names get a collision-safe key (base__mlbam, the thin-card
            # convention); the post-loop award below restores the PLAIN key on the
            # flagship row so existing links / FA / trade joins keep working for him.
            "key": (f"{_nkey}__{mlbam}" if _ambiguous else _nkey), "name": name, "age": age,
            "mlbam": mlbam,
            "src": "vet", "twoWay": True if two_way else None,
            "pos": _vet_pos(two_way, ct, path["role"]),
            # The club that holds him NOW (resolve_current_club): the feed and
            # this season's stats outrank the monthly contract club, which is
            # stale for every player traded since the last Spotrac pass.
            "team": _vet_club(mlbam, ct),
            "war": war_arr,
            # Champion MEAN path (5y) - the SUM basis for the Team Outlook
            # multi-year roll-up (warChamp[0] == warY1Champ below).
            "warChamp": [round(w, 2) for w in champ_arr],
            # If-healthy (playing-time-held) display path - shown on the board's
            # WAR cells; surplus/value below still price off `war` (expected value).
            "warPTH": (pth_arr or war_arr),
            "warP10": p10_arr,
            "warP90": p90_arr,
            # Champion MEAN year-1 for team aggregation (sum across both
            # sides for two-way). The displayed path may be the gated ML
            # quantile head, whose median-like points must not be summed.
            "warY1Champ": round(sum((paths[s].get("war_y1_champ")
                                     if paths[s].get("war_y1_champ") is not None
                                     else paths[s]["war_by_year"][0]) or 0.0
                                    for s in paths), 2),
            "_warChampFull": champ_full,
            # The champion MEAN path past the five printed seasons, public (owner
            # answer Q-A (b), 2026-09-30): the aging curve /fa/'s future-class
            # overlay chains its seasons past 2031 along (fa_export.
            # FUTURE_CLASS_TAIL), the same curve this module's contract tail
            # chains on, so the two pages extend a path with one curve. Read by
            # /fa/ only; nothing on /projections/ prices or prints it.
            "warChampTail": champ_full[HORIZON:] or None,
            "_warFull": war_full,
            "_p10Full": p10_full,
            "_p90Full": p90_full,
        }
        # Projected RATE lines (fa_projection.rate_path - the year-1 Marcel
        # components walked along the per-component aging curves). Hitters:
        # wOBA + wRC+; pitchers: FIP; two-way rows carry both. Display
        # surfaces only - WAR/pricing are untouched by these.
        _rh = (paths.get("hit") or {}).get("rates_by_year") or []
        _rp = (paths.get("pit") or {}).get("rates_by_year") or []
        if _rh:
            m["woba"] = [r.get("woba") for r in _rh[:HORIZON]]
            m["wrc"] = [r.get("wrc_plus") for r in _rh[:HORIZON]]
        if _rp:
            m["fip"] = [r.get("fip") for r in _rp[:HORIZON]]
        if two_way:
            m["warHit"] = [round(w, 2) for w in paths["hit"]["war_by_year"][:HORIZON]]
            m["warPit"] = [round(w, 2) for w in paths["pit"]["war_by_year"][:HORIZON]]
        m["warTotal"] = round(sum(m["war"]), 1)
        m["warTotalPTH"] = round(sum(m.get("warPTH") or m["war"]), 1)  # if-healthy display total
        if p10_arr:
            # RVA09 (2026-10-02): a sum of per-season quantiles is not a quantile
            # of the total, so it ships under the Comon suffix, the name
            # fa_export gives the same comonotone sum. A plain warTotalP10 /
            # warTotalP90 on /fa/ is the copula-simulated total; here it would
            # have been the sum under the same name.
            m["warTotalP10Comon"] = round(sum(p10_arr), 1)
            m["warTotalP90Comon"] = round(sum(p90_arr), 1)
        if ct:
            _apply_contract(m, ct)
            # A resolved collision winner takes the plain key back (links/joins).
            if _ambiguous and contracts.get(_nkey) is ct and _awards_plain_key(ct):
                m["key"] = _nkey
        m = _clean(m)
        out.append(m)
        _ck = _contested_by_mlbam.get(mlbam)
        if _ck:
            _collision_rows.setdefault(_ck, []).append(m)
    # Contracts the resolver could not single out: award to the highest-projected-WAR
    # claimant only (Spotrac's collapse keeps the highest-AAV deal, i.e. the flagship).
    # THE AWARD HAS TO REACH THE PATH PASS. `_resolve_contracts` deliberately
    # leaves a contested contract OUT of `_ct_by_mlbam`, so handing that map to
    # `_apply_salary_paths` would show it ct=None for exactly the row that just
    # took a contract: rule 1's second lock would be off and the board grid
    # would be free to price a season the contract already buys. `_ct_final` is
    # the contract set the ROWS actually got.
    _ct_final = dict(_ct_by_mlbam)
    for _ck, rows in _collision_rows.items():
        ct = contracts.get(_ck)
        winner = _award_winner(rows, ct)
        if winner is None:
            continue
        _apply_contract(winner, ct)   # mutates the row already in `out`
        if winner.get("mlbam") is not None:
            _ct_final[winner["mlbam"]] = ct
        if winner["key"].split("__")[0] == _ck:
            winner["key"] = _ck       # flagship keeps the plain key (links/joins)
    # THE SALARY PATH (ask C, 2026-09-16; GATE C before it). Price every
    # remaining season a club controls, not only the ones a contract prices.
    # Runs LAST so it can never overwrite a real contract - the guarantee is now
    # per SEASON rather than per ROW, which is the whole change: a row is no
    # longer skipped wholesale because some season of it is contracted.
    _apply_salary_paths(out, dpw, r, _ct_final)
    out.sort(key=lambda m: -(m.get("warTotal") or 0))
    return out



#: What the salary path reached, and what it did not. Filled by
#: `_apply_salary_paths` (the only place that sees both the built rows and the
#: /arbitration/ board) and published verbatim by `_accountability_block`. A
#: census a reader can check beats a claim a reader has to trust: this one says
#: how many seasons were priced from a contract, from the board and from class
#: closure, how many rows have NO established control window and why, how many
#: the non-tender option cuts, and how many negative pre-arbitration dollars
#: are deliberately left unpriced (decision D11).
_SALARY_PATH_CENSUS: dict = {}


def _legacy_arbitration_paths(rows, dpw, r, log=None) -> dict:
    """GATE C exactly as it served from 2026-08-09 to 2026-09-16. THE REVERT.

    `SALARY_PATH_MODE = "off"` runs this and nothing else, so reverting the
    control-window salary path is one constant rather than a re-implementation,
    and `test_salary_path_off_mode` can assert the payload is byte-for-byte the
    pre-change one. docs/ARBITRATION_GATE.md section 11e fixes in advance which
    failing GATE C2 clause reverts how far.

    SCOPE LIMIT, and it was deliberate. This runs ONLY for players who already
    have an observed MLB record and a resolved arbitration step - the population
    the model was fit on. It never touches a prospect. A never-debuted player's
    arbitration years are four to seven seasons out, he has no prior salary, the
    raise model cannot run at all, and extrapolating a model fit on observed
    awards onto him is the exact shape of a prior failure in this tree.

    ITS DEFECT, which is the whole of ask C: the skip is per ROW. A veteran on a
    one-year 2026 deal carries a rest-of-season surplus, so `surTotal` is not
    None, so the 2027 and 2028 arbitration steps already sitting on the board
    were never read. 408 veterans and about 1,400 club-controlled seasons priced
    at nothing that way.
    """
    board = sp.board_rows()
    paths = {}
    for mlbam, row in (board.get("rows") or {}).items():
        per = {st["season"]: st["usd"] for st in row["steps"]
               if st.get("usd") is not None}
        if per:
            paths[mlbam] = per
    if not paths:
        return {"priced": 0, "reason": "arbitration board not exported"}
    priced = 0
    for m in rows:
        if m.get("surNpv") is not None or m.get("surTotal") is not None:
            m.setdefault("salSrc", "contract")
            continue
        per = paths.get(m.get("mlbam"))
        if not per:
            continue
        sur = []
        npv = 0.0
        any_sal = False
        for t in range(HORIZON):
            season = FIRST_SEASON + t
            s_usd = per.get(season)
            if s_usd is None:
                sur.append(None)
                continue
            any_sal = True
            v_usd = _season_value_usd(m["war"][t], t, dpw)
            d_usd = v_usd - s_usd
            sur.append(round(d_usd / 1e6, 1))
            npv += d_usd / ((1 + r) ** t)
        if not any_sal:
            continue
        m["sur"] = sur
        m["surNpv"] = int(npv)
        if m.get("surTotal") is None:
            m["surTotal"] = int(npv)
        m["salSrc"] = "arb_projection"
        priced += 1
    if log:
        log("  gate C: priced %d rows off the arbitration projection" % priced)
    return {"priced": priced}


def _strip_private(m: dict) -> None:
    """Drop the private carrier keys `_apply_contract` records for this pass.
    `_clean` runs BEFORE the path pass (inside the row loop), so it cannot do
    this; the path pass is the last thing to touch a veteran row, so it does."""
    for k in ("_salYears", "_rosUsd", "_warChampFull", "_warFull", "_p10Full", "_p90Full"):
        m.pop(k, None)


def _band_npv(path, war, dpw, r, which: str, run_cliff: bool) -> float:
    """The surplus NPV with the salary held at one END of the board's own award
    band and the WAR path held at its MEAN.

    The two errors are NOT fused into one range, and the reason is measured:
    they are positively correlated (a better season raises both the projection
    and the award), the correlation is estimated nowhere in this tree, and the
    board's band (22% at arb-1, widening 8 points a rung) is documented as
    deliberately not a calibrated interval. Fusing them would launder that into
    a served interval. Measured on the path-priced rows: the salary band is
    about 1.9% of the WAR band at the median, and above 25% of it on 8.4% of
    rows - which is why it ships as its own field rather than as a footnote.

    The same cliff rule runs on the band endpoint, because the cliff is
    monotone in the season surplus: a uniformly cheaper salary can only raise
    the floored total. Skipping it here would let a floored `surNpv` sit ABOVE
    an unfloored `surSalHi` and break the published ordering.

    THIS RETURNS THE PROJECTED LEG ONLY. The rest-of-season leg is a contracted
    salary against a fraction of the first season, so it carries no award
    uncertainty and it is added back by the CALLER, which is what makes the
    published pair bracket the published `surTotal` rather than a number no
    surface shows.
    """
    if vf.dpw_path_active():
        return _band_npv_unified(path, war, dpw, r, which, run_cliff)
    d = []
    for c in path["seasons"]:
        if c["usd"] is None:
            d.append(None)
            continue
        s = c.get(which)
        s = c["usd"] if s is None else s
        w = war[c["t"]] if c["t"] < len(war) else None
        d.append(_season_value_usd(w or 0.0, c["t"], dpw) - s)
    # The club's right to decline a losing club option holds at the band
    # endpoints too (sp.club_option_floor, owner answer VAL2-Q2).
    d, _ = sp.club_option_floor(path["seasons"], d)
    if run_cliff:
        cuttable = [sp.is_cuttable(c) and c["usd"] is not None
                    for c in path["seasons"]]
        npv, _ = sp.tender_cliff([x or 0.0 for x in d], cuttable, r)
        return npv
    return sum(x / ((1 + r) ** t) for t, x in enumerate(d) if x is not None)


def _apply_salary_paths(rows, dpw, r, contracts=None, say=None) -> dict:
    """Price every remaining season a club controls, through ONE salary path.

    Replaces GATE C's `_apply_arbitration_paths`. The invariant that change
    turns on is unchanged in intent and moved in letter: A SEASON A CONTRACT
    PRICES IS NEVER RE-PRICED. What changes is that a ROW is no longer skipped
    wholesale because some season of it is contracted, which is what left 408
    veterans and about 1,400 club-controlled seasons at zero.

    Per row: build the path (salary_path.py owns every rule), price each season
    at `_season_value_usd(war) - salary`, run the non-tender option on the
    arbitration seasons, and stamp the payload keys. Contracted seasons are
    re-derived here from the SAME salary `_apply_contract` used, so a row whose
    window is entirely contracted comes out byte-identical - which is what the
    "133 rows signed through 2028+ must not move" assertion checks.

    Runs LAST, after the collision-winner re-award, so the contract set it sees
    is final.
    """
    global _SALARY_PATH_CENSUS
    mode = sp.SALARY_PATH_MODE
    board = sp.board_rows()
    vintage = board.get("vintage")
    brows = board.get("rows") or {}
    census = {
        "mode": mode,
        "vintage": vintage,
        # Whether the board the path priced off is older than this payload by
        # more than six weeks. R6/decision D9: there is no ordering bug to fix -
        # the monthly runs arb_export (step 6b7) BEFORE the chained daily's
        # proj_export - but a plain nightly or a standalone --rebuild-only
        # prices off the last monthly board, which is that board's own cadence.
        # Disclosed here and asserted in test_calibration_vintage rather than
        # re-plumbed.
        "stale": _board_is_stale(vintage),
        "sv_rows": sum(1 for row in brows.values() if row.get("sv")),
        "board_rows": len(brows),
    }
    if mode == "off" or not brows:
        out = _legacy_arbitration_paths(rows, dpw, r, log=say)
        for m in rows:
            _strip_private(m)
        census["priced_rows"] = out.get("priced", 0)
        census["reason"] = out.get("reason")
        _SALARY_PATH_CENSUS = {k: v for k, v in census.items() if v is not None}
        return out

    opts_all = sp.options()
    lm = sp.league_min_table()
    raise_fn = sp.board_raise_fn() if mode in ("closure", "full") else None
    census["closure_estimator"] = (
        "fitted" if raise_fn is not None else
        ("not_run" if mode in ("ladder",) else "unavailable"))
    if mode in ("closure", "full") and raise_fn is None:
        # LOUD, NOT SHORT. `board_raise_fn` degrades to None on a cold tree (no
        # panel, a stale cache), and a silent degrade ships a materially
        # different board with a green suite: closure prices 467 seasons on
        # 245 rows, and 17.8% of the money this change adds comes through it.
        # The only trace used to be one census string nothing asserted. Serving
        # the shorter window is a decision, so it is made by a person moving
        # SALARY_PATH_MODE, not by an exception nobody saw.
        raise RuntimeError(
            "salary path mode %r needs the arb raise estimator and "
            "salary_path.board_raise_fn() returned None; build the panel, or "
            'set salary_path.SALARY_PATH_MODE = "ladder" to serve without '
            "class closure" % (mode,))
    rows_by_src = defaultdict(int)
    seasons_by_src = defaultdict(int)
    seasons_by_tok = defaultdict(int)
    usd_by_tok = defaultdict(list)
    truncated = defaultdict(int)
    cliff_first = defaultdict(int)
    opt_seasons = defaultdict(int)
    by_sal_src = defaultdict(int)
    prearb_neg = {"seasons": 0, "usd": 0}
    arb_neg_kept = {"seasons": 0, "usd": 0}
    cliff_rows = band_rows = priced = 0
    rule1_repairs = []
    cba_floored = 0
    buyout_rows = 0
    tail = {"rows": 0, "seasons": 0, "salary_usd": 0, "surplus_npv_usd": 0,
            "capped_rows": 0, "capped_seasons": 0}
    opt_decl = {"rows": 0, "seasons": 0, "usd_added_npv": 0}
    last_h = FIRST_SEASON + HORIZON - 1

    for m in rows:
        sal_years = m.get("_salYears")
        mlbam = m.get("mlbam")
        ct = (contracts or {}).get(mlbam)
        war = m.get("war") or []
        # THE CONTRACT TAIL (PRICE_CONTRACT_TAIL). The pricing WAR is the
        # served path for the projected seasons and, after them, the seam
        # TAIL_SEAM names (see _tail_war); the tail may run only as far as the
        # champion path does.
        champ_full = m.get("_warChampFull") or []
        tail_last = None
        _ct_years = [int(y) for y in ((ct or {}).get("salary_by_year") or {})]
        if PRICE_CONTRACT_TAIL and _ct_years and max(_ct_years) > last_h:
            reach = FIRST_SEASON + len(champ_full) - 1
            tail_last = min(max(_ct_years), reach)
            _beyond = [y for y in _ct_years if y > reach]
            if _beyond:
                tail["capped_rows"] += 1
                tail["capped_seasons"] += len(_beyond)
            if tail_last <= last_h:
                tail_last = None
        war_px = list(war)
        if tail_last is not None and len(war_px) >= HORIZON:
            _tw, _how = _tail_war(war_px, champ_full, m.get("_warFull"))
            war_px = war_px[:HORIZON] + _tw
            tail["seam_" + _how] = tail.get("seam_" + _how, 0) + 1
        band_tail = _tail_band(m, champ_full) if tail_last is not None else None
        path = sp.salary_path(
            mlbam, key=m.get("key"), first_season=FIRST_SEASON, horizon=HORIZON,
            contract=ct, board_row=brows.get(mlbam), league_min=lm,
            opts=opts_all.get(m.get("key")), mode=mode, raise_fn=raise_fn,
            vintage=vintage, tail_last=tail_last)
        seasons = path["seasons"]
        # RULE 1, ASSERTED RATHER THAN ASSUMED. `_apply_contract` recorded the
        # seasons it priced; every one of them inside the horizon must come
        # back from the path as `contract`, at the same dollars.
        if sal_years:
            _sby = {int(y): int(v) for y, v in
                    ((ct or {}).get("salary_by_year") or {}).items()}
            for y in sal_years:
                t = y - FIRST_SEASON
                if 0 <= t < len(seasons) and seasons[t]["src"] != "contract":
                    # RESTORE THE DOLLARS, NOT ONLY THE LABEL. Relabelling a
                    # season `contract`/`signed` while it keeps an arbitration
                    # projection hides the defect from every token-based test,
                    # and clearing the label alone would leave guaranteed money
                    # unpriced. Counted, and the count is asserted at 0 on the
                    # served artifact by test_salary_path_must_not_move.
                    rule1_repairs.append([m.get("key"), y])
                    log.error("salary path re-priced a contracted season: "
                              "%s %s", m.get("key"), y)
                    _u = _sby.get(y)
                    seasons[t].update(src="contract", tok="signed", cls=None,
                                      usd=_u, lo=_u, hi=_u)
        d_usd, sur = [], []
        for c in seasons:
            if c["usd"] is None:
                d_usd.append(None)
                sur.append(None)
                continue
            w = war_px[c["t"]] if c["t"] < len(war_px) else None
            d = _season_value_usd(w or 0.0, c["t"], dpw) - c["usd"]
            d_usd.append(d)
            sur.append(round(d / 1e6, 1))
        _unified = vf.dpw_path_active()
        if _unified:
            # VAL_5 row 18: the companion index inside the priced surplus only.
            d_usd, sur = _unified_path_surplus(seasons, war_px, dpw)
        # THE CLUB'S RIGHT (owner answer VAL2-Q2): a club option season the
        # club would decline prices at zero, never below. Before the tender
        # cliff, so an arbitration season's continuation sees the floored value.
        _raw_d = list(d_usd)
        d_usd, opt_declined = sp.club_option_floor(seasons, d_usd)
        for y in opt_declined:
            t = y - FIRST_SEASON
            sur[t] = round(d_usd[t] / 1e6, 1)
            opt_decl["seasons"] += 1
            opt_decl["usd_added_npv"] += int(-_raw_d[t] / ((1 + r) ** t))
        if opt_declined:
            opt_decl["rows"] += 1
        any_priced = any(x is not None for x in d_usd)
        raw_npv = sum(d / ((1 + r) ** t)
                      for t, d in enumerate(d_usd) if d is not None)
        cut = None
        npv = raw_npv
        if mode == "full" and any_priced:
            npv, cut = sp.apply_cliff(path, d_usd, r)
        if _unified:
            npv *= vf.season_discount(FIRST_SEASON)
        if cut is not None:
            for t in range(cut, len(sur)):
                sur[t] = None
            cliff_rows += 1
            cliff_first[str(seasons[cut]["season"])] += 1
        ros_usd = m.get("_rosUsd")
        _strip_private(m)

        # ---- census, on the path as it will be served ---------------------
        for c in seasons:
            if c["usd"] is None:
                continue
            seasons_by_src[c["src"]] += 1
            seasons_by_tok[c["tok"] or "?"] += 1
            if c["src"] != "contract":
                usd_by_tok[c["tok"] or "?"].append(int(c["usd"]))
            if c.get("opt"):
                opt_seasons[c["opt"]] += 1
            d = d_usd[c["t"]]
            if d is not None and d < 0:
                if c["src"] != "contract" and not sp.is_cuttable(c):
                    # D11: a club abandons a pre-arbitration player by option or
                    # designation, not by declining to tender him. The mechanism
                    # is different, the copy would be wrong, so the option is NOT
                    # priced and the residual is published instead.
                    prearb_neg["seasons"] += 1
                    prearb_neg["usd"] += int(d)
                elif sp.is_cuttable(c) and not c["cut"]:
                    arb_neg_kept["seasons"] += 1
                    arb_neg_kept["usd"] += int(d)
        for s in set(c["src"] for c in seasons if c["usd"] is not None):
            rows_by_src[s] += 1
        if path["truncated"]:
            truncated[path["truncated"]] += 1
        if path.get("tail_last") is not None:
            _tc = [c for c in seasons[HORIZON:] if c["usd"] is not None]
            tail["rows"] += 1
            tail["seasons"] += len(_tc)
            tail["salary_usd"] += sum(int(c["usd"]) for c in _tc)
            tail["surplus_npv_usd"] += int(sum(
                d_usd[c["t"]] / ((1 + r) ** c["t"]) for c in _tc
                if d_usd[c["t"]] is not None and not c["cut"]))

        # ---- stamp -------------------------------------------------------
        has_ct = ros_usd is not None or any(c["src"] == "contract" for c in seasons
                                            if c["usd"] is not None)
        has_arb = any(c["src"] in ("arb_ladder", "class_closure")
                      for c in seasons if c["usd"] is not None)
        m["salSrc"] = ("contract+arb" if (has_ct and has_arb)
                       else "contract" if has_ct
                       else "arb_projection" if has_arb else "pending")
        by_sal_src[m["salSrc"]] += 1
        if any(x is not None for x in sur):
            m["sur"] = sur
        else:
            m.pop("sur", None)
        if any_priced:
            m["surNpv"] = int(npv)
            priced += 1
        else:
            m.pop("surNpv", None)
        if ros_usd is not None or any_priced:
            m["surTotal"] = int((ros_usd or 0.0) + npv)
        else:
            m.pop("surTotal", None)
        # The WAR each tail season priced on (TAIL_SEAM: the champion's aging
        # curve chained from the 2031 WAR), one entry per
        # season FIRST_SEASON+HORIZON .. the last tail season (None on a gap
        # year the contract lists no dollars for). `war` stays the five
        # projected seasons the board prints.
        if path.get("tail_last") is not None:
            m["warTail"] = [round(war_px[c["t"]], 2) if c["usd"] is not None else None
                            for c in seasons[HORIZON:]]
        else:
            m.pop("warTail", None)
        # The tail's own P10/P90 per season (TAIL_BAND, owner answer VAL2-Q3),
        # aligned with warTail: what the trade value's range prices the tail on.
        if path.get("tail_last") is not None and band_tail is not None:
            m["warP10Tail"] = [round(band_tail[0][c["t"] - HORIZON], 2) + 0.0 if c["usd"] is not None else None
                               for c in seasons[HORIZON:]]
            m["warP90Tail"] = [round(band_tail[1][c["t"] - HORIZON], 2) if c["usd"] is not None else None
                               for c in seasons[HORIZON:]]
            tail["band_rows"] = tail.get("band_rows", 0) + 1
        else:
            m.pop("warP10Tail", None)
            m.pop("warP90Tail", None)
        pl = sp.payload_path(path)
        if pl:
            m["salPath"] = pl
            m["salVintage"] = vintage
            if _unified:
                # salIdx: the index each salPath season was netted at (row 18).
                m["salIdx"] = [round(_unified_salary_index(c), 6) for c in seasons
                               if c["usd"] is not None]
        if path["last_controlled"] is not None:
            m["salThru"] = path["last_controlled"]
        if path["truncated"]:
            m["salTrunc"] = path["truncated"]
        # THE CONTROL WINDOW, DERIVED ONCE (2026-09-17). `salThru` is the last
        # season the path PRICES; `ctrlThru` is the last season the club
        # CONTROLS, and they are different objects on 481 served rows. Every
        # surface reads these four keys and none of them recomputes
        # max(thru, salThru) in JS, which is how the site acquired five answers
        # to one question. salary_path.control_end owns the rule.
        ce = sp.control_end(path, m.get("thru"), FIRST_SEASON, HORIZON)
        if ce["end"] is not None:
            m["ctrlThru"] = ce["end"]
        if ce["open"]:
            m["ctrlOpen"] = True
        if ce["est"]:
            m["ctrlEst"] = True
        if ce["why"]:
            m["ctrlWhy"] = ce["why"]
        if path["cut_season"] is not None:
            m["salCut"] = path["cut_season"]
        so = sp.payload_options(path)
        if so:
            m["salOpt"] = so
        # The club option seasons the club would decline on the mean path,
        # each priced at $0 in `sur` (sp.club_option_floor).
        if opt_declined:
            m["salOptDecl"] = opt_declined
        else:
            m.pop("salOptDecl", None)
        # The salary band ships only where the board publishes a genuine award
        # band. A contracted season and a pre-arbitration minimum carry lo == hi
        # by construction (dollars and a CBA rule are not estimates), so a row
        # made only of those would ship a degenerate band that says nothing.
        if any_priced and any(c["lo"] != c["hi"] for c in seasons
                              if c["usd"] is not None):
            lo = _band_npv(path, war_px, dpw, r, "hi", mode == "full")
            hi = _band_npv(path, war_px, dpw, r, "lo", mode == "full")
            # NAMED FOR THE SURPLUS, ORDERED ASCENDING. A LOW salary gives a
            # HIGH surplus, so `surSalLo` is the surplus at the HIGH award.
            #
            # AND IT CARRIES THE REST-OF-SEASON LEG, because every surface
            # prints this pair beside `surTotal` (= surRos + surNpv), not
            # beside `surNpv`: the board detail line, the player-card Surplus
            # tile and the trade row's `surplus_salary_band_mm` all do. A band
            # over the projected seasons alone left 69 of 307 band rows with a
            # published surplus ABOVE the top of its own published band -
            # Caminero $371.4M against $364.6M-$367.2M. The pair is now the
            # same object as the headline, so the ordering the test pins is the
            # ordering a reader sees.
            _ros = float(ros_usd or 0.0)
            m["surSalLo"] = int(_ros + min(lo, hi))
            m["surSalHi"] = int(_ros + max(lo, hi))
            band_rows += 1
        cba_floored += int(path.get("cba_floored") or 0)
        if path.get("closure_buyout"):
            buyout_rows += 1

    census.update({
        "priced_rows": priced,
        "rows_by_salsrc": dict(sorted(by_sal_src.items())),
        "salary_path_rows": dict(sorted(rows_by_src.items())),
        "salary_path_seasons": dict(sorted(seasons_by_src.items())),
        "seasons_by_token": dict(sorted(seasons_by_tok.items())),
        "truncated": dict(sorted(truncated.items())),
        "cliff_rows": cliff_rows,
        "cliff_first_season": dict(sorted(cliff_first.items())),
        "band_rows": band_rows,
        "option_seasons": dict(sorted(opt_seasons.items())),
        # D11 residual: negative pre-arbitration season dollars the cliff
        # deliberately does not price, and negative ARBITRATION season dollars
        # the backward induction deliberately KEEPS because a later season in
        # the same window pays for them.
        "prearb_negative_seasons": prearb_neg,
        "arb_negative_seasons_kept": arb_neg_kept,
        # RULE 1, COUNTED. Every season a contract priced that the path did not
        # return as `contract`. Asserted at 0 on the served artifact - a
        # non-zero value means a contract reached a row without reaching this
        # pass, which is how a contested Spotrac key used to slip through.
        "rule1_repairs": rule1_repairs,
        # CBA Article VI floors applied where the path's own prior season is a
        # CONTRACT the /arbitration/ board's chain never saw.
        "cba_floored_steps": cba_floored,
        # What the buy-out guard declines to price: rows whose contract covers
        # their last listed grid season, so class closure does not run and any
        # arbitration season after the contract stays unpriced. The guard is
        # what holds the "133 rows signed through 2028+ move $0" invariant;
        # lifting it is its own measured change.
        "closure_buyout_rows": buyout_rows,
        # THE SALARY LEG'S OWN LEVEL, published so the compression is visible
        # on the served artifact rather than only in a lab. The /arbitration/
        # board's arb-1 step tops out about an order of magnitude below the
        # realized arb-1 maximum, because arb_export.build_board builds its
        # feature row from `panel_rows` while `war3` and `career_war` are
        # attached only to the SCORED rows: the arb-1 ridge sees 0.0 for two of
        # its champion features on the board rows. That is upstream of this
        # module and it moves /arbitration/'s published ladder, so it is not
        # repaired here; GATE C2 clause C10' scores it against realized awards
        # and docs/ARBITRATION_GATE.md section 11i names it as the blocking
        # defect on the salary leg. Direction: arbitration salaries too LOW,
        # therefore surplus too HIGH, hardest on the stars.
        "arb_step_levels": {
            tok: {"n": len(v), "median_usd": sorted(v)[len(v) // 2],
                  "max_usd": max(v)}
            for tok, v in sorted(usd_by_tok.items()) if v
        },
        # The curated option file's own size, beside the option census, so the
        # coverage of the D10 disclosure is legible: it is a hand-kept
        # supplement, not a league-wide option inventory.
        "option_file_rows": len(opts_all),
        # THE CONTRACT TAIL (PRICE_CONTRACT_TAIL, owner answer 2026-09-25):
        # rows whose guarantee runs past the horizon and is priced through its
        # last season on the TAIL_SEAM path; the guaranteed seasons and
        # dollars that adds; the discounted surplus those seasons contribute;
        # and the rows whose guarantee outruns the champion path (priced only
        # as far as it reaches, and still labelled as clamped).
        # THE CLUB'S RIGHT (owner answer VAL2-Q2): rows and club option
        # seasons the club would decline on the mean path, each priced at $0
        # rather than at its negative surplus, and the discounted dollars that
        # floor adds back.
        "club_option_decline": dict(opt_decl, enabled=bool(sp.CLUB_OPTION_DECLINE)),
        "contract_tail": dict(tail, enabled=bool(PRICE_CONTRACT_TAIL),
                              war_basis=("war_by_year_champ" if TAIL_SEAM == "champion_level"
                                         else "chain_aging_tail"),
                              seam=TAIL_SEAM,
                              band=bool(TAIL_BAND and TAIL_SEAM == "chained"),
                              band_p10_floor=bool(TAIL_BAND_P10_FLOOR)),
    })
    _SALARY_PATH_CENSUS = {k: v for k, v in census.items() if v is not None}
    if say:
        say("  salary path (%s): %d rows priced, %d seasons, cliff on %d"
            % (mode, priced, sum(seasons_by_src.values()), cliff_rows))
    return {"priced": priced, "mode": mode}


def _board_is_stale(vintage, days: int = 45) -> bool:
    """Is the /arbitration/ board the path priced off older than this payload by
    more than `days`? Disclosed, not repaired (decision D9)."""
    if not vintage:
        return True
    try:
        y, mo, d = (int(x) for x in str(vintage).split("-"))
        return (date.today() - date(y, mo, d)).days > days
    except (TypeError, ValueError):
        return True


# ============================================================================
# Prospects - the calibrated FV outcome model, post-ETA
# ============================================================================

def _prospect_calibration_shift() -> float:
    """The SHIPPED intercept-only mean-path correction (prospect_path
    candidate #2, pre-registered + gated: held-out bias 0.341 -> 0.110
    on identical rows, MAE down, slope within tolerance). Fit on the
    first-3-season SUM; applied as shift/3 per season to the first three
    projected seasons. Display layer only - surplus keeps its own
    isotonic calibration (never double-corrected)."""
    try:
        d = json.loads((DATA_DIR / "prospect_path_eval.json").read_text(encoding="utf-8"))
        blk = d.get("calibration_intercept_only") or {}
        if blk.get("ship") and blk.get("full_window_shift") is not None:
            return float(blk["full_window_shift"])
    except (OSError, ValueError):
        pass
    return 0.0


# BASIS REPAIR 2026-08-03. THE board eFV number, mirroring build_site's
# `_load_xfv_grades` precedence exactly (which in turn mirrors
# storage.BOARD_GRADE_FIELD and the prospx client's efvBoardValue): the
# calibrated board value first, then the realized grade, then the RETIRED
# quantile as a legacy fallback. This file kept a private quantile-FIRST copy of
# the precedence when the board unified onto raw xfv_grade on 2026-07-25, so
# /projections/ went on serving the retired quantile as the eFV headline while
# the board, the homepage and prospx served xfv_grade: one player, two different
# eFV numbers. The SCALE itself is owned by efv_board_scale.board_value(); there
# is deliberately no second copy of the coefficients here to drift.
try:
    from efv_board_scale import board_value as _efv_board_value
except Exception:                                            # pragma: no cover
    def _efv_board_value(rec):
        return (rec or {}).get("xfv_grade")


def _board_grade(rec: dict | None):
    """The DISPLAYED eFV grade for an xfv.json record, or None. Unrounded -
    callers that display it round to NEAREST (eFV is not a scouting FV)."""
    rec = rec or {}
    g = _efv_board_value(rec)
    if g is None:
        g = rec.get("xfv_grade_realized")
    if g is None:
        g = rec.get("xfv_grade_quantile")
    return float(g) if isinstance(g, (int, float)) else None


def _prospect_rows(dpw: float) -> list[dict]:
    try:
        players = json.loads((DATA_DIR / "timeseries.json")
                             .read_text(encoding="utf-8")).get("players") or []
    except (OSError, ValueError):
        log.warning("mlb projections: timeseries.json unavailable - no prospects")
        return []
    cal_shift = _prospect_calibration_shift()
    try:
        xfv_by = (json.loads((DATA_DIR / "xfv.json").read_text(encoding="utf-8"))
                  .get("by_player") or {})
    except (OSError, ValueError):
        xfv_by = {}
    out: list[dict] = []
    for p in players:
        cons_fv = p.get("fv_close")
        # DISPLAY grade: THE board eFV headline, on the SAME precedence as
        # build_site._load_xfv_grades and storage.BOARD_GRADE_FIELD (see
        # _board_grade above), so /projections/, the homepage Top Prospects module
        # and the PROSPX board all show the same eFV number for the same player.
        _rec = xfv_by.get(p.get("player_key")) or {}
        _xg = _board_grade(_rec)
        fv = _xg if _xg is not None else cons_fv
        fv_source = "xfv" if _xg is not None else "consensus"
        # PRICING grade: DELIBERATELY the retired per-side quantile, NOT the displayed
        # board grade. The FV>=45 gate + p_bucket / WAR-path / surplus / prime curves are
        # all calibrated on the CONSENSUS 20-80 scale, which is exactly the scale the
        # quantile map lands on; the pure-model grade sits lower and floors a pile at 20,
        # and pricing on it once inflated the projected prospect pool ~+60% vs consensus.
        # This is the same split efv_export documents in meta.grade_scale: the board
        # displays xfv_grade while surplus_mm stays priced through xfv_grade_quantile,
        # which is why the 2026-07-30 grade refit moved zero dollars. So display and
        # pricing are two different numbers here ON PURPOSE - do not "unify" them without
        # re-fitting the value curves. Mirrors fa_fit.py's blocker-FV rule.
        _pq = _rec.get("xfv_grade_quantile")
        price_fv = _pq if (fv_source == "xfv" and _pq is not None) else fv
        eta = (p.get("eta") or {}).get("year")
        if (price_fv is None or price_fv < 45 or not eta or p.get("status") != "active"
                or eta > FIRST_SEASON + HORIZON - 1):
            continue
        pos = p.get("position")
        is_pit = vf.is_pitcher_position(pos)
        reliever = vf.is_reliever_position(pos)
        role = vf._role_key(is_pit)
        probs = vf.p_bucket_given_fv(float(price_fv), is_pit)
        if not probs:
            continue
        age = p.get("age")
        # P-ETACLAMP: anchor the trajectory to the SHIPPED eta, not the raw one.
        # The row ships eta_yr = max(eta, FIRST_SEASON) and both the board
        # (assets/projections.js warAt) and the team roll-up offset the path by
        # that shipped value - but debut_age was computed from the RAW eta, so
        # every prospect whose eta had already passed (98 of 232 on the
        # 2026-07-24 payload, 42%) got a trajectory shaped for a debut at their
        # CURRENT age and then rendered one calendar year later. Aging, scaling
        # and the surplus eta_years term (which already used the clamped value)
        # now agree.
        eta_shipped = max(int(eta), FIRST_SEASON)
        debut_age = (float(age) + max(0, eta_shipped - (FIRST_SEASON - 1))) if age else None
        scale = vf._war_scale_for(float(price_fv), role)
        paths = [vf._bucket_season_wars(role, i, reliever, debut_age, scale)
                 for i in range(len(_BUCKET_ORDER))]
        n_yrs = len(paths[0])
        mean_path = [round(sum(pr * paths[i][t] for i, pr in enumerate(probs)), 2)
                     for t in range(n_yrs)]
        if cal_shift:
            # intercept-only mean correction, first three seasons (the
            # window it was fit on), floored at 0
            mean_path = [round(max(0.0, w - cal_shift / 3.0), 2) if t < 3 else w
                         for t, w in enumerate(mean_path)]

        def _q_bucket(q: float) -> int:
            cum = 0.0
            for i, pr in enumerate(probs):
                cum += pr
                if cum >= q:
                    return i
            return len(probs) - 1

        lo_b, hi_b = _q_bucket(0.10), _q_bucket(0.90)
        eta_yr = eta_shipped
        # P-PWINDOW: the prospect war[] arrays are ETA-ALIGNED (index 0 = the
        # debut season) while the veteran arrays are CALENDAR-aligned at
        # FIRST_SEASON, so `sum(path[:HORIZON])` is NOT "the same HORIZON window
        # as the veteran rows" its comment claimed - for a 2031-ETA prospect it
        # summed 2031-2035 and labelled it a 2027-2031 total. Measured on the
        # 2026-07-24 payload: 79 prospects with eta>2027 shipped 155.2 total WAR
        # against 101.7 actually inside the window (1.53x). The board already
        # windows correctly in JS (warShown); the PAYLOAD field did not, and
        # mlb_player_export / fa_export / bayes_trade_value read it directly.
        _in_win = max(0, HORIZON - (eta_yr - FIRST_SEASON))

        def _wtot(series):
            return round(sum(series[:_in_win]), 1)

        # RVA02 (2026-10-02): ONE PROSPECT, ONE SURPLUS. The prospect's surplus is
        # the eFV export's surplus_mm for the same player, the number the Trade
        # Machine board (trade_value_mm), PROSPX and the Club Ledger farm row
        # serve. This module used to reprice it here through
        # vf.surplus_value_mm(price_fv, eta_years = shipped ETA - 2026), whole
        # seasons from the shipped ETA, while the eFV export prices the same
        # grade on the timeseries surplus record's own eta_years. On the
        # 2026-10-01 payload that put 54 of 178 prospects above every other
        # surface (derek_curiel $79.2M against $78.1M, enddy_azocar $25.3M
        # against $23.3M, ratio up to 1.086). A prospect number recomputed
        # through value_framework is on the Club Ledger NEVER list, so the row
        # now copies the eFV figure and prices nothing itself.
        _sx = _rec.get("surplus_mm")
        sv = float(_sx) if isinstance(_sx, (int, float)) else None
        # PRIME/TALENT display path (warPTH) + headline peak: reconciled to the
        # industry-style prime anchor so the board shows "what he is if he
        # sticks" (a 62-FV SS ~ 3-4 WAR, star ceiling ~5) instead of the
        # realized-mean ramp. The expected `war` above is unchanged and still
        # prices surplus.
        prime = vf.prospect_prime_path(float(price_fv), is_pit, debut_age, reliever)
        out.append(_clean({
            "key": p.get("player_key"), "name": p.get("player_name"),
            # Headshot join key. Veteran rows have carried `mlbam` since the
            # board shipped; prospect rows carried none (0 of 209), so the
            # projections board could not render a prospect photo at all.
            "mlbam": p.get("mlbam_id"),
            "age": age, "src": "prospect", "fv": fv, "consensus_fv": cons_fv,
            "fv_source": fv_source, "eta": eta_yr,
            "pos": pos, "team": p.get("org"),
            "war": [round(w, 2) for w in mean_path],
            "warP10": [round(w, 2) for w in paths[lo_b]],
            "warP90": [round(w, 2) for w in paths[hi_b]],
            # Totals sum the SAME CALENDAR window as the veteran rows: the war
            # arrays are ETA-aligned, so the in-window count is HORIZON minus the
            # seasons before debut (see P-PWINDOW above). The arrays themselves
            # keep the full control window for the card path.
            "warTotal": _wtot(mean_path),
            # RVA09: the SUM of the per-season P10 / P90 bucket path, served
            # under the Comon suffix fa_export already uses for a summed
            # quantile. It is not the P10 / P90 of the total.
            "warTotalP10Comon": _wtot(paths[lo_b]),
            "warTotalP90Comon": _wtot(paths[hi_b]),
            # Prime/talent display path (not used for $): board WAR cells.
            "warPTH": [round(w, 2) for w in prime["mean"]] if prime else None,
            "warPTHP10": [round(w, 2) for w in prime["p10"]] if prime else None,
            "warPTHP90": [round(w, 2) for w in prime["p90"]] if prime else None,
            "warTotalPTH": _wtot(prime["mean"]) if prime else None,
            "warTotalPTHP10": _wtot(prime["p10"]) if prime else None,
            "warTotalPTHP90": _wtot(prime["p90"]) if prime else None,
            "warPeak": prime["peak"] if prime else None,
            "bucketLo": _BUCKET_ORDER[lo_b], "bucketHi": _BUCKET_ORDER[hi_b],
            "pBust": round(probs[0], 3),
            "surNpv": int(round(sv * 1e6)) if sv is not None else None,
        }))
    out.sort(key=lambda m: -(m.get("warTotal") or 0))
    return out


# ============================================================================
# Payload
# ============================================================================

def _cohort_intercepts() -> dict[str, float]:
    """side:ageband -> additive year-1 WAR intercept, from the committed
    retro backtest (proj_backtest.py, fit on 2022-24 residuals, gated on
    the 2025 holdout). Applied at the TEAM ROLL-UP only - the per-player
    display keeps the engine's mean. Missing artifact = no-op.

    GATED on the artifact's own ship_decision (added 2026-07-31). Until now
    this read the intercepts unconditionally, so re-running proj_backtest.py
    served whatever it produced even when the challenger LOST its holdout.
    That is not hypothetical: re-fitting on the post-E3 paths yields
    cohort_recentered 7.29 against plain recentered 7.19, i.e. the intercepts
    become actively harmful, and the old code would have shipped them the
    moment anyone regenerated the artifact. The 2026-08-04 proj_backtest run
    persisted challenger_wins False, so this returns {} and the served roll-up
    is plain uniform recentering (the retro block's `recentered` arm)."""
    # CONSERVATIVE-DIRECTION GUARD, verified 2026-08-07 (silent-empty sweep).
    # Empty here means DO NOT APPLY THE CHALLENGER: the roll-up keeps the
    # engine's own mean, which is the arm the gate validated. An unreadable
    # artifact and a lost holdout therefore land on the same, safe side, so
    # this is not an instance of the fetch-fails-into-empty-but-valid pattern
    # and does not want a sentinel or a red. Do not re-flag it.
    try:
        d = json.loads((DATA_DIR / "team_outlook_eval.json").read_text(encoding="utf-8"))
        rb = (d.get("retro_backtest") or {})
        if not ((rb.get("ship_decision") or {}).get("challenger_wins")):
            return {}
        return rb.get("cohort_intercepts_fit_2022_24") or {}
    except (OSError, ValueError):
        return {}


def _age_band(age) -> str:
    a = int(age) if age else 28
    for lo, hi in ((0, 25), (26, 29), (30, 33), (34, 99)):
        if lo <= a <= hi:
            return f"{lo}-{hi}"
    return "34-99"


def _last_controlled_season(m: dict) -> int:
    """Last season this player counts on his team's CONTROLLED roster - the
    'control cliff' that makes the out-year team WAR decline as players reach
    free agency.

    - Prospect: controlled the full window from his ETA (6-year control >> the
      5-year horizon), so he never cliffs inside the horizon.
    - Veteran with a Spotrac contract: through ``signed_through`` (``thru``).
    - Veteran without a contract row: an AGE-based proxy (the pipeline carries
      no service time) - a pre-arb/arb player (age <= 24) holds the full horizon,
      a likely pending free agent (age >= 29) holds only the first season.

    UNCHANGED BY ASK C, DELIBERATELY (decision D5). `salThru` - the last season
    the salary path prices - is the successor input here and it is a better
    statement than the age proxy, but switching this function moves Team
    Outlook out-year WAR, the playoff odds that ride on it and the
    contract-aware rank gate in bayes_trade_value, none of which is in this
    change's blast radius. It moves in its own measured change. What ships now
    is the cheaper half of the incoherence: where `salThru` exists, the player
    card and the trade-board tooltip SUPPRESS the control-years line and show
    the path instead, so no surface states two different window lengths at
    once.

    AND IT IS NOT THE CLUB CONTROL WINDOW. The window every surface now prints
    is `ctrlThru` (salary_path.control_end), stamped a few hundred lines above
    this one. This function computes an age-proxy control SHARE for the Team
    Outlook roll-up, 551 of 894 rows of it disagree with `min(salThru, last)`,
    and the copy on that board says so in those words rather than promising a
    control model the code does not call.
    """
    last = FIRST_SEASON + HORIZON - 1
    if m.get("src") == "prospect":
        return last
    thru = m.get("thru")
    if thru:
        try:
            t = int(thru)
            # A contract that still covers the first projected season governs
            # the cliff. A stale / already-expired `thru` (option years, past
            # deals on a still-rostered player) is ignored - the player is on
            # the current roster, so fall through to the age proxy, which never
            # drops the first season.
            if t >= FIRST_SEASON:
                return min(t, last)
        except (TypeError, ValueError):
            pass
    try:
        age = int(m.get("age"))
    except (TypeError, ValueError):
        age = 28
    rem = max(0, min(HORIZON - 1, 29 - age))
    return FIRST_SEASON + rem


# The pitcher entries of _VALID_POS, the vocabulary mlb_player_export.
# _is_pitcher_pos reads too, so the Team Outlook split and the player card agree.
_PIT_POS = {"SP", "RP", "P", "LHP", "RHP", "SIRP", "MIRP", "CL"}


def _row_sides(m: dict) -> list[str]:
    if m.get("twoWay"):
        return ["hit", "pit"]              # two-way = both stat lines
    # EPOCH-SPOTRAC-1: `pos` is validated where it is written (_vet_pos and
    # _apply_contract), so a numeric Spotrac code never reaches this split.
    return ["pit" if str(m.get("pos") or "").strip().upper() in _PIT_POS else "hit"]


def _depth_pool(corpus: dict, names: dict[int, str],
                contracts: dict[str, dict], vet_mlbams: set) -> tuple[dict, dict]:
    """Per-season WAR for every projectable player the exposure floors exclude
    from the display list - the retro backtest showed the floor-gated
    universe carries only ~560 of the league's ~1000 WAR while the full
    >=1-input-season population, on real rosters, sums to ~870-935. These
    players never appear in the UI table; their WAR joins the Team Outlook
    roll-up per team (contract team), shrinking the uniform depth allowance to
    a small remainder.

    RANGE RECONCILED 2026-08-04. This said "~870-930" while
    test_team_outlook_calibration floors the same quantity at 900, and that
    test's own docstring flagged the disagreement ("whichever is right, both
    should not stand") back when the served value was 886.3 and sat between
    them. It no longer does: after the F-DEF ship restored the vet paths and
    the stale cohort-intercept vector was dropped, the served sum is 932.9, so
    the top of the stated range was the stale half. Widened to 935; the test's
    900 floor stands unchanged and now has real headroom.

    Multi-year: champion MEANS (use_ml=False pins the champion path) are summed
    season-by-season - the same mean basis the rostered roll-up uses - and each
    depth player counts only through his control window
    (_last_controlled_season; depth players are nearly all non-contracted, so
    the age proxy dominates), so the depth pool also cliffs in the out-years.
    Returns ({org: [war_2027..2031]}, accounting)."""
    league = corpus["league"]
    curves, war_map = fp.fitted_models(corpus, FIRST_SEASON - 1)
    in_prog = (FIRST_SEASON - 1, fp.season_fraction(league, FIRST_SEASON - 1))
    by_player: dict[str, dict[int, dict[int, dict]]] = {
        "hit": defaultdict(dict), "pit": defaultdict(dict)}
    for side in ("hit", "pit"):
        for row in corpus[side]:
            if row.get("mlbam") and row["season"] >= FIRST_SEASON - 3:
                by_player[side][row["mlbam"]][row["season"]] = row
    team_war: dict[str, list[float]] = defaultdict(lambda: [0.0] * HORIZON)
    war_unassigned = [0.0] * HORIZON
    n = n_unassigned = 0
    # Contract joins are by normalized name (Spotrac has no mlbam): a depth player
    # sharing a name with ANY projectable player (vet or depth) must not inherit the
    # namesake's contract/team - count name keys over the full projectable universe
    # and leave collided names unassigned (honest) instead of crediting the wrong club.
    _dp_name_counts: dict[str, int] = {}
    for _mid in (set(by_player["hit"]) | set(by_player["pit"])) | vet_mlbams:
        _nm = names.get(_mid)
        if _nm:
            _k = normalize_key(_nm)
            _dp_name_counts[_k] = _dp_name_counts.get(_k, 0) + 1
    for mlbam in (set(by_player["hit"]) | set(by_player["pit"])) - vet_mlbams:
        champ = [0.0] * HORIZON
        age_any = None
        for side in ("hit", "pit"):
            seasons = by_player[side].get(mlbam) or {}
            hist = [seasons[t] for t in (FIRST_SEASON - 1, FIRST_SEASON - 2,
                                         FIRST_SEASON - 3) if t in seasons]
            if not hist:
                continue
            # Anchor the age offset to the row that supplied the age.
            age_row = next((h for h in hist if h.get("age")), None)
            age = (age_row["age"] + (FIRST_SEASON - age_row["season"])) if age_row else None
            age_any = age or age_any
            cp = fm.contract_war_path(hist, side, FIRST_SEASON, HORIZON, age,
                                      curves, war_map, league,
                                      in_progress=in_prog, use_ml=False)
            if cp is None:
                continue
            arr = cp.get("war_by_year_champ") or cp.get("war_by_year") or []
            for t in range(HORIZON):
                if t < len(arr):
                    champ[t] += float(arr[t] or 0.0)
        if not any(champ):
            continue
        n += 1
        name = names.get(mlbam)
        _dk = normalize_key(name) if name else None
        ct = (contracts.get(_dk) if (_dk and _dp_name_counts.get(_dk, 0) == 1) else None)
        # Same resolver the vet rows use: the depth pool is nearly all pre-arb
        # players, exactly the population Spotrac's contract pages omit.
        org = _current_club(mlbam, ct)[0]
        last_ctrl = _last_controlled_season(
            {"src": "vet", "thru": (ct or {}).get("signed_through"), "age": age_any})
        bucket = team_war[org] if org else war_unassigned
        if not org:
            n_unassigned += 1
        for t in range(HORIZON):
            if FIRST_SEASON + t <= last_ctrl:
                bucket[t] += champ[t]
    acct = {"n_depth_players": n,
            "depth_war_y1": round(sum(v[0] for v in team_war.values()), 1),
            "depth_war_5y": round(sum(sum(v) for v in team_war.values()), 1),
            "n_unassigned": n_unassigned,
            "war_unassigned_y1": round(war_unassigned[0], 1),
            "war_unassigned_5y": round(sum(war_unassigned), 1)}
    return {k: [round(x, 2) for x in v] for k, v in team_war.items()}, acct


def _record_farm_block_outage(err: Exception) -> None:
    """Raise an unreadable timeseries.json into the ingest-health RED ledger.

    NOT a conservative-direction guard, unlike _cohort_intercepts: the caller
    reads this with `farm.get(tm)`, so an empty return drops the farm rank,
    grade, surplus and top-prospect columns from all 30 Team Outlook rows and
    the page renders normally without them.

    timeseries.json is also the artifact that was found TRUNCATED in the middle
    on 2026-08-06, which is a ValueError here, not an OSError: the exact shape
    where the file exists, the pipeline looks healthy and a surface quietly
    empties. Filed through bullpen_export.record_ingest (the live-module
    resolution) under a name in run_monthly.SCHEDULED_EXPORTS, or the row is
    dropped at drain time. Best-effort: reporting never fails an export."""
    log.error("proj export: timeseries.json unreadable (%s); the farm columns "
              "on every Team Outlook row will be absent this run", err)
    try:
        from bullpen_export import record_ingest
        record_ingest("proj_team_outlook_farm", ok=False, n_rows=0,
                      message=(f"timeseries.json unreadable ({err}); farm rank, "
                               "grade, surplus and top prospect are missing from "
                               "all 30 Team Outlook rows"))
    except Exception:                      # noqa: BLE001
        log.debug("could not record the farm-block outage row", exc_info=True)


def _org_farm_blocks() -> dict[str, dict]:
    """Farm-system context joined onto the Team Outlook rows - the org
    dashboard columns the retired /teams/ page carried (merged into the
    projections module 2026-06-12): farm rank + grade score, net active
    prospect surplus, and the top prospect with his FV."""
    try:
        ts = json.loads((DATA_DIR / "timeseries.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        _record_farm_block_outage(e)
        return {}
    out: dict[str, dict] = {}
    for o in ts.get("org_summary") or []:
        org = o.get("org")
        if not org:
            continue
        top = (o.get("prospects") or [{}])[0]
        out[org] = {
            "farmRank": o.get("farm_rank"),
            "farmScore": o.get("farm_score"),
            "farmSurplusMM": o.get("_active_surplus_net_mm"),
            "topProspect": ({"name": top.get("name"),
                             "key": top.get("player_key"),
                             "fv": top.get("fv_label")}
                            if top.get("name") else None),
        }

    # System Duration: surplus-weighted arrival timing per org. etaMean is the
    # bond-math "duration" of a farm (when its surplus arrives, on average);
    # etaByYear is the arrival curve (share of farm surplus landing each season,
    # last bucket = FIRST_SEASON+HORIZON and later). Weight = expected surplus
    # $ (floored at 0 so an over-valued negative-surplus prospect never pulls
    # the center); count-weight fallback keeps a zero-surplus org from vanishing.
    LAST = FIRST_SEASON + HORIZON            # the "and later" bucket edge
    acc: dict[str, dict] = {}
    for p in ts.get("players") or []:
        org = p.get("org")
        eta = p.get("eta") or {}
        yr = eta.get("year")
        if not org or yr is None or org not in out:
            continue
        try:
            yr = int(yr)
        except (TypeError, ValueError):
            continue
        w = max(0.0, float((p.get("surplus") or {}).get("value_mm") or 0.0))
        yr_c = min(LAST, max(FIRST_SEASON, yr))
        a = acc.setdefault(org, {"wsum": 0.0, "wyr": 0.0, "n": 0,
                                 "by": [0.0] * (HORIZON + 1), "cn": 0, "cyr": 0.0})
        a["n"] += 1
        a["cyr"] += yr_c          # count-weighted center fallback
        a["cn"] += 1
        a["wsum"] += w
        a["wyr"] += w * yr_c
        a["by"][yr_c - FIRST_SEASON] += w if w > 0 else 0.0
    for org, a in acc.items():
        if a["wsum"] > 0:
            eta_mean = a["wyr"] / a["wsum"]
            tot = sum(a["by"]) or 1.0
            eta_by = [round(x / tot, 3) for x in a["by"]]
        else:                     # no positive surplus: fall back to count-weight
            eta_mean = a["cyr"] / a["cn"] if a["cn"] else None
            eta_by = None
        out[org]["etaMean"] = round(eta_mean, 2) if eta_mean is not None else None
        out[org]["etaByYear"] = eta_by
        out[org]["etaN"] = a["n"]
    return out


def _team_outlook(vets: list[dict], prospects: list[dict],
                  depth_team_war: dict | None = None,
                  depth_acct: dict | None = None,
                  intercepts: dict | None = None) -> list[dict]:
    """Team WAR roll-up. The DISPLAY headline is the first projected season
    (47.7 replacement baseline + roster WAR -> projected wins; PRE-FREE-AGENCY
    frame, forward-gated against actual standings). On top of that, the
    multi-year controlled-core machinery powers an organizational CONTROL
    metric: `lockedPct` = the WAR-weighted share of the core's projected
    2027-31 production that the team actually controls (controlled WAR / the
    same players' everyone-stays WAR). Aging affects both numerator and
    denominator, so it cancels - lockedPct isolates cost control: 1.0 = every
    contributor locked through the horizon, low = a core about to leak to free
    agency. `byYear[].war` (controlled WAR per season) drives the decline
    sparkline. Prospects contribute at their org from their ETA forward.

    REPLACEMENT_WINS comes from rate_stabilization (shared with the retro
    backtest in proj_backtest.py)."""
    # bWAR is calibrated so the league's players sum to ~1000 WAR every
    # season (verified 1000/1000/1000 for 2023-25 in war_daily). eWAR v2,
    # the served basis since 2026-09-03, keeps that identity by construction:
    # its per-season replacement scale is re-derived so the league sum equals
    # (0.5 - 47.7/162) x team-games; data/ewar_eval.json accounting_league_sum
    # reads max_abs_deviation_from_target 0.0, with 2023/2024/2025 ewar_sum
    # 999.0 / 998.59 / 999.0 against bwar_sum 1000.35 / 999.79 / 1000.44
    # (build window 2011-2026). The 1000 benchmark below stands under either
    # basis; it is not a constant the rebase re-derives. The
    # rostered universe captures ~56% of that pool (Marcel regression +
    # shrunk playing time + exposure floors), which read as a ~15-win
    # negative bias on every team (the best team projected 83 wins).
    LEAGUE_WINS = 2430.0
    intercepts = intercepts or {}
    depth_team_war = depth_team_war or {}

    teams: dict[str, dict] = {}

    def _team(tm: str) -> dict:
        return teams.setdefault(tm, {
            "raw":  [0.0] * HORIZON,  # CONTROLLED champion-mean roster WAR/season
            "full": [0.0] * HORIZON,  # everyone-stays WAR/season (control denominator)
            "coh":  [0.0] * HORIZON,  # cohort-intercept adjustment, per season
            "n":    [0] * HORIZON,
            "top": []})               # (year1_war, name, key) for the top-3 strip

    # Veterans contribute their champion MEAN per season (the displayed ML
    # quantile head is median-like and must NOT be summed), only through their
    # control window - the 'control cliff' that makes the out-years decline.
    for m in vets:
        tm = m.get("team")
        champ = m.get("warChamp") or []
        if not tm or not champ:
            continue
        last_ctrl = _last_controlled_season(m)
        sides = _row_sides(m)
        age0 = m.get("age")
        t_ = _team(tm)
        for t in range(HORIZON):
            if t >= len(champ):
                continue
            w = champ[t]
            if w is None:
                continue
            # Everyone-stays denominator counts every horizon season (the WAR
            # the player would give THIS team if he never left).
            t_["full"][t] += w
            if FIRST_SEASON + t > last_ctrl:
                continue
            t_["raw"][t] += w
            t_["n"][t] += 1
            # Cohort intercept, re-banded by age-in-season (out-year application
            # is an approximation - the fit was on year-1 residuals).
            band = _age_band((age0 + t) if age0 is not None else None)
            for side in sides:
                t_["coh"][t] += intercepts.get(f"{side}:{band}", 0.0)
        y1 = (m.get("war") or [None])[0]   # displayed year-1 WAR for the strip
        if y1 is not None:
            t_["top"].append((y1, m.get("name"), m.get("key")))

    # Prospects join from their ETA season forward (their mean `war[]` is
    # ETA-aligned, not calendar-aligned). 6-year control >> the horizon, so no
    # in-horizon cliff.
    for m in prospects:
        tm = m.get("team")
        eta = m.get("eta")
        war = m.get("war") or []
        if not tm or eta is None or not war:
            continue
        off = int(eta) - FIRST_SEASON
        if off >= HORIZON:
            continue
        t_ = _team(tm)
        for t in range(max(0, off), HORIZON):
            idx = t - off
            if idx < len(war) and war[idx] is not None:
                t_["raw"][t] += war[idx]
                t_["full"][t] += war[idx]   # prospects are controlled all horizon
                t_["n"][t] += 1
        if off <= 0 and war[0] is not None:
            t_["top"].append((war[0], m.get("name"), m.get("key")))

    farm = _org_farm_blocks()

    # Per-season INDEPENDENT recenter to the 2,430-win league sum. Calibration
    # mirrors year-1 (cohort intercepts + sub-floor depth pool + uniform
    # remainder); applied to every season. In the out-years the freed
    # control-cliff WAR + unassigned depth + future entrants ride the (growing)
    # remainder, pulling teams toward .500 unless their controlled core sustains.
    season_remainder = [0.0] * HORIZON
    for t in range(HORIZON):
        cal_sum = 30 * REPLACEMENT_WINS
        for tm, t_ in teams.items():
            depth_t = (depth_team_war.get(tm) or [0.0] * HORIZON)[t]
            cal_sum += t_["raw"][t] + t_["coh"][t] + depth_t
        season_remainder[t] = (LEAGUE_WINS - cal_sum) / max(len(teams), 1)

    raw_wins_sum_y1 = 30 * REPLACEMENT_WINS + sum(t_["raw"][0] for t_ in teams.values())
    out = []
    for tm, t_ in teams.items():
        t_["top"].sort(reverse=True)
        depth_arr = depth_team_war.get(tm) or [0.0] * HORIZON
        by_year = []
        for t in range(HORIZON):
            war_cal = t_["raw"][t] + t_["coh"][t] + depth_arr[t]
            wins = round(REPLACEMENT_WINS + war_cal + season_remainder[t], 1)
            by_year.append({
                "season": FIRST_SEASON + t,
                "war": round(t_["raw"][t], 1),
                "wins": wins,
                "losses": round(162.0 - wins, 1),
                "winsRaw": round(REPLACEMENT_WINS + t_["raw"][t], 1),
                "depthWar": round(war_cal - t_["raw"][t] + season_remainder[t], 1),
                "n": t_["n"][t],
            })
        y1 = by_year[0]
        # Organizational CONTROL: WAR-weighted share of the core's projected
        # 2027-31 production the team controls (controlled / everyone-stays).
        ctrl5 = sum(t_["raw"])
        full5 = sum(t_["full"])
        locked = max(0.0, min(1.0, ctrl5 / full5)) if full5 > 0.01 else None
        # Window Alignment: does the farm arrive while the big-league core is
        # still under control? coreCenter = WAR-weighted midpoint of the
        # controlled core's 2027-31 production; etaAlignYears = farm arrival
        # center minus coreCenter. <= 0: farm lands inside the window (aligned);
        # positive: it arrives after the core has leaked to free agency (gap).
        fb = farm.get(tm)
        core_w = sum(max(0.0, b["war"]) for b in by_year)
        core_center = (sum((b["season"]) * max(0.0, b["war"]) for b in by_year) / core_w
                       if core_w > 0.01 else None)
        eta_mean = (fb or {}).get("etaMean")
        align = (round(eta_mean - core_center, 2)
                 if (fb and eta_mean is not None and core_center is not None) else None)
        if fb is not None:
            fb = dict(fb)
            fb["coreCenter"] = round(core_center, 2) if core_center is not None else None
            fb["etaAlignYears"] = align
        out.append({
            "team": tm,
            # Back-compat year-1 top-level fields (GFX + older consumers read
            # these directly; identical to the prior single-season output).
            "war": y1["war"], "wins": y1["wins"], "losses": y1["losses"],
            "winsRaw": y1["winsRaw"], "depthWar": y1["depthWar"], "n": y1["n"],
            "byYear": by_year,
            # Cost-controlled core strength + lock-up security.
            "lockedPct": round(locked, 3) if locked is not None else None,
            "ctrlWar5y": round(ctrl5, 1),   # controlled WAR banked over the horizon
            "fullWar5y": round(full5, 1),   # everyone-stays WAR (the denominator)
            "top": [{"name": n, "key": k, "war": round(w, 1)}
                    for w, n, k in t_["top"][:3]],
            "farm": fb,
        })
    out.sort(key=lambda r: -r["wins"])
    _write_team_outlook_eval(out, raw_wins_sum_y1, season_remainder, depth_acct or {})
    return out


def _forward_vintage_on_record(season: int) -> bool:
    import proj_forward_vintage as pfv
    return bool(pfv.on_record(season)[0])


def _write_team_outlook_eval(rows: list[dict], raw_wins_sum_y1: float,
                             season_remainder: list[float], depth_acct: dict) -> None:
    """data/team_outlook_eval.json - the league-sum accounting plus the
    shipped calibration composition, committed per the eval-artifact
    standing rule. The retro_backtest block (proj_backtest.py) is
    PRESERVED across re-exports - it is the measurement the calibration
    rests on. The forward gate (MAE vs actual wins) stays pending until
    the first projected season completes; only the first season is
    forward-gateable (out-years are a controlled-core trajectory)."""
    try:
        payload = json.loads((DATA_DIR / "team_outlook_eval.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        payload = {}
    # Whether the cohort-intercept vector serves, read through the same gate
    # the roll-up uses, so the calibration text below and the tripwire never
    # describe a vector the roll-up did not apply.
    vector_serving = bool(_cohort_intercepts())
    by_season = []
    for t in range(HORIZON):
        seas = [r["byYear"][t] for r in rows if t < len(r.get("byYear") or [])]
        by_season.append({
            "season": FIRST_SEASON + t,
            "roster_war_sum": round(sum(s["war"] for s in seas), 1),
            "wins_sum": round(sum(s["wins"] for s in seas), 1),  # recenters to 2,430
            "remainder_recenter_wins_per_team": round(season_remainder[t], 2),
        })
    payload.update({
        "generated_at": date.today().isoformat(),
        "first_season": FIRST_SEASON,
        "horizon": HORIZON,
        "league_sum_accounting": {
            # Year-1 aliases (back-compat with the calibration guards + external
            # readers); the full series lives under by_season.
            "roster_war_sum": round(sum(r["war"] for r in rows), 1),
            "remainder_recenter_wins_per_team": round(season_remainder[0], 2),
            "roster_war_sum_y1": round(sum(r["war"] for r in rows), 1),
            "league_war_benchmark": 1000,
            "benchmark_basis": ("a league WAR pool of 1000 per season: bWAR sums 1000/1000/1000 for 2023/2024/2025 (war_daily), and the projections' training label since the 2026-10 epoch, published fWAR, fixes its own league pool at 1000 per season by construction (57/43 split)"),
            "raw_wins_sum": round(raw_wins_sum_y1, 1),
            "raw_wins_sum_y1": round(raw_wins_sum_y1, 1),
            "target_wins_sum": 2430,
            "depth_pool": depth_acct,
            "by_season": by_season,
            "coverage_decomposition_2025": {
                "returning_player_war": 940, "new_entrant_war": 61,
                "new_entrant_players": 253,
                "note": "new-entrant WAR is covered by the ETA-prospect block "
                        "and the recentering remainder; the original level gap "
                        "was the exposure-floor universe (see retro_backtest)"},
        },
        "calibration": {
            "kind": ("v2: per-team sub-floor depth pool + cohort intercepts "
                     "(side x age band, retro-backtest-fit 2022-24, holdout-gated) "
                     "+ small uniform remainder to the 2,430-win league sum, "
                     "applied per season"
                     if vector_serving else
                     "v2: per-team sub-floor depth pool + uniform remainder to "
                     "the 2,430-win league sum, applied per season; the cohort "
                     "intercepts (side x age band, retro-backtest-fit 2022-24) "
                     "lost their holdout gate and are not applied"),
            "cohort_intercepts_applied": vector_serving,
            "limitations": [
                "depth-pool team assignment needs a contract row; unassigned depth WAR rides the uniform remainder",
                "spread stays projection-compressed (correct for a mean projection; bands carry the uncertainty)"],
        },
        "multi_year": {
            "kind": "controlled-core: each player counts only through his control "
                    "window (_last_controlled_season); each season is independently "
                    "recentered to the 2,430-win league sum",
            "display_metric": "the surface shows year-1 W-L + WAR plus lockedPct = "
                    "WAR-weighted control share (controlled / everyone-stays WAR over "
                    "2027-31); aging cancels, so it isolates cost control",
            "limitations": [
                f"only the first season ({FIRST_SEASON}) is forward-gateable; "
                "out-years (2028+) are a controlled-core competitive trajectory, "
                "NOT scored against actual standings",
                "the cliff is Spotrac signed_through where present, else an "
                "age-based proxy (no service time in the pipeline). It is NOT "
                "the club control window on the players board, which is the "
                "salary path's own end (ctrlThru)",
                "cohort intercepts were fit on year-1 residuals; out-year "
                "application re-bands by age but is an approximation"],
        },
        "forward_gate": {
            "status": "pending",
            "first_scoreable": f"end of the {FIRST_SEASON} season",
            "scope": f"first season only; {FIRST_SEASON + 1}+ are not gateable",
            "metric": "MAE vs actual wins; baseline = prior-season wins carry-forward",
            # The forecast it grades is the write-once preseason freeze, never
            # this nightly file (owner answer M15-2, PROJ_FORWARD_VINTAGE_GATE).
            "forecast": "the frozen preseason copy of the first projected season, "
                        "taken before its first game and pinned by hash; never a nightly build",
            "forecast_on_record": _forward_vintage_on_record(FIRST_SEASON)},
    })
    # System Duration / Window Alignment coverage + league distribution. A
    # descriptive rollup of committed inputs (eta model validated, surplus
    # validated, controlled-core WAR), so this is disclosure, not a new gate.
    aligns = [r["farm"]["etaAlignYears"] for r in rows
              if r.get("farm") and r["farm"].get("etaAlignYears") is not None]
    etas = [r["farm"]["etaMean"] for r in rows
            if r.get("farm") and r["farm"].get("etaMean") is not None]
    aligns_sorted = sorted(aligns)
    payload["window_alignment"] = {
        "kind": "surplus-weighted farm ETA (etaMean) vs the controlled-core WAR "
                "center (coreCenter); etaAlignYears = etaMean - coreCenter, "
                "<= 0 = farm arrives inside the controlled-core window "
                "(aligned). That window is the age-proxy cliff "
                "(_last_controlled_season), not the club control window the "
                "players board prints",
        "weight": "expected surplus $ (value_mm), floored at 0; count-weight fallback",
        "eta_coverage_orgs": len(etas),
        "align_coverage_orgs": len(aligns),
        "eta_mean_range": [round(min(etas), 2), round(max(etas), 2)] if etas else None,
        "align_median": (round(aligns_sorted[len(aligns_sorted) // 2], 2)
                         if aligns_sorted else None),
        "align_range": [round(aligns_sorted[0], 2), round(aligns_sorted[-1], 2)]
                       if aligns_sorted else None,
        "aligned_org_count": sum(1 for a in aligns if a <= 0),
        "limitations": [
            "etaMean is surplus-weighted by the platform surplus model (its "
            "uncertainty flows through); coreCenter is the controlled-core "
            "trajectory, not a scored contention forecast",
            "orgs whose farm carries no positive-surplus prospect fall back to "
            "a count-weighted center and report no arrival curve"],
    }
    # Serve-vector tripwire (W3.9): the eval's own question, answered at every
    # refresh. retro_backtest (proj_backtest.py, preserved across re-exports)
    # scores the vector this exporter actually serves (served_recentered)
    # beside plain recentering. If served ever reads WORSE than plain on the
    # holdout fold, the serve vector is actively costing wins and the artifact
    # flags itself rather than waiting for a reader to notice.
    _hm = (((payload.get("retro_backtest") or {}).get("ship_decision") or {})
           .get("holdout_mae") or {})
    _srv, _plain = _hm.get("served_recentered"), _hm.get("recentered")
    _flag = (bool(_srv > _plain)
             if isinstance(_srv, (int, float)) and isinstance(_plain, (int, float))
             else None)
    payload["serve_vector_flag"] = _flag
    payload["serve_vector_tripwire"] = {
        "question": ("does the served vector read worse than plain "
                     "recentering on the holdout retro fold"),
        "holdout_mae_served_recentered": _srv,
        "holdout_mae_recentered": _plain,
        "flag": _flag,
        # served_recentered scores the vector proj_backtest read when it last
        # ran. When the gate has since switched the vector off, that arm
        # describes a vector this export does not apply, and the tripwire
        # says so instead of implying it meters the live roll-up.
        "vector_serving": vector_serving,
        "vector_note": (None if vector_serving else
                        "the cohort-intercept vector does not serve; "
                        "served_recentered scores the vector as it stood when "
                        "proj_backtest last ran ("
                        + str((payload.get("retro_backtest") or {}).get("generated_at"))
                        + "), and the live roll-up is the plain recentered arm"),
        "source": ("retro_backtest.ship_decision.holdout_mae "
                   "(proj_backtest.py; preserved across re-exports; "
                   "flag is None when the block is absent)"),
    }
    (DATA_DIR / "team_outlook_eval.json").write_text(
        json.dumps(payload, indent=1), encoding="utf-8")


# ============================================================================
# Current-season (2026) view - Bayesian + Pythag blend, log5 SOS, playoff odds
# ============================================================================
# DARK-LAUNCHED, ADDITIVE overlay. This runs OUTSIDE _team_outlook, after it
# returns, and only ever writes a nested `current` block (+ two flat mirrors) on
# each row - the 2027 byYear[]/wins/war/lockedPct output and team_outlook_eval
# are never touched. When live standings/schedule are absent (offline / degraded
# local build) every team's `current` is None and the row is byte-for-byte the
# 2027-only output. FIRST_SEASON=2027 is the first PROJECTED season; the
# in-progress current season is FIRST_SEASON-1 = 2026.
_PYTHAG_EXP = 1.83               # fixed fallback exponent (baseball-reference standard)
_PYTHAGENPAT_EXP = 0.287         # Smyth/Patriot Pythagenpat: exp = RPG**0.287
CURRENT_PRIOR_PSEUDO_GAMES = 40  # k: prior worth ~1/4 season; wPrior=0.5 at G=40
# StatsAPI 40-man roster status codes -> "out for the bulk of the season" flag,
# used ONLY for the display-only ilOut60 badge (NOT any projection number).
_IL60_CODES = {"D60", "D7D60", "60"}


def _pythag_pct(rs: float | None, ra: float | None,
                g: float | None = None) -> float | None:
    """Pythagorean win expectation from runs scored/allowed.

    When games played `g` is known, use Pythagenpat (Smyth/Patriot): the exponent
    scales with the run environment, exp = ((RS+RA)/G)**0.287, which is materially
    more accurate than a fixed exponent for extreme offenses/pitching and is the
    modern sabermetric standard. Falls back to the fixed 1.83 when G is unavailable
    (e.g. RS/RA present but gamesPlayed absent). NOTE the caller prefers StatsAPI's
    own xWinLoss when present; this fires only when that is missing."""
    if rs is None or ra is None or rs < 0 or ra < 0 or (rs + ra) <= 0:
        return None
    if g and g > 0:
        rpg = (rs + ra) / g
        exp = rpg ** _PYTHAGENPAT_EXP if rpg > 0 else _PYTHAG_EXP
    else:
        exp = _PYTHAG_EXP
    rse = rs ** exp
    rae = ra ** exp
    if rse + rae <= 0:
        return None
    return rse / (rse + rae)


def _talent_prior_pct(win_total: float) -> float:
    """The pure roster-talent prior as a win rate: the model's recentered year-1
    (2027) team win total / 162, clamped to a sane [.20, .80]. This reuses the
    EXISTING machinery (the same `wins` the 2027 view already published) - it does
    NOT recompute the model, and 2026-vs-2027 talent drift is negligible next to
    the k=40 shrinkage."""
    return min(0.80, max(0.20, win_total / 162.0))


def _current_blend(rec: dict, prior_pct: float,
                   k: float = CURRENT_PRIOR_PSEUDO_GAMES) -> dict:
    """Bayesian blend of the roster-talent prior, actual record, and Pythag for
    the in-progress season. Prior acts as k pseudo-games, so it dominates in April
    and fades (never fully) toward the in-season signals by September; Pythag gets
    twice actual's share of the in-season weight (it predicts future record
    better). Projected full-season record banks games played and projects the
    remainder at the forward-looking (prior+Pythag) rate."""
    g = rec.get("gamesPlayed") or 0
    wins = rec.get("wins")
    losses = rec.get("losses")
    actual_pct = rec.get("pct")
    if actual_pct is None and wins is not None and g:
        actual_pct = wins / g
    if actual_pct is None:
        actual_pct = 0.5
    # Prefer StatsAPI's own xWinLoss pythag; else compute from RS/RA.
    if rec.get("pythagWins") is not None and rec.get("pythagLosses") is not None:
        pw, pl = rec["pythagWins"], rec["pythagLosses"]
        pythag_pct = pw / (pw + pl) if (pw + pl) > 0 else None
    else:
        pythag_pct = _pythag_pct(rec.get("rs"), rec.get("ra"), g)
    if pythag_pct is None:
        pythag_pct = prior_pct   # no run data yet -> lean on the prior

    w_prior = k / (k + g)
    in_season = 1.0 - w_prior
    w_actual = in_season * (1.0 / 3.0)
    w_pythag = in_season * (2.0 / 3.0)
    # Forward rate for un-played games drops `actual` (those games are banked).
    fwd_denom = w_prior + w_pythag
    forward_pct = ((w_prior * prior_pct + w_pythag * pythag_pct) / fwd_denom
                   if fwd_denom > 0 else prior_pct)
    wins_to_date = wins if wins is not None else round(actual_pct * g)
    cur_wins = int(round(wins_to_date + max(0, 162 - g) * forward_pct))
    cur_wins = min(162, max(0, cur_wins))
    cur_losses = 162 - cur_wins
    return {
        "gamesPlayed": g,
        "record": f"{wins}-{losses}" if wins is not None and losses is not None else None,
        "actualPct": round(actual_pct, 3),
        "pythagPct": round(pythag_pct, 3),
        "talentPriorPct": round(prior_pct, 3),
        "curWins": cur_wins,
        "curLosses": cur_losses,
        "curPct": round(cur_wins / 162.0, 3),
        "gb": rec.get("divGb"),
        "blendWeights": {"prior": round(w_prior, 3),
                         "actual": round(w_actual, 3),
                         "pythag": round(w_pythag, 3)},
    }


def _season_is_complete(regular_season_end: str | None, today=None) -> bool:
    """True once `today` is on or after the season's last scheduled
    regular-season date. False when the date is missing or unreadable, so an
    unknown calendar keeps the old fetch-failure fallback."""
    import datetime as _dt
    if not regular_season_end:
        return False
    try:
        end = _dt.date.fromisoformat(str(regular_season_end)[:10])
    except ValueError:
        return False
    return (today or _dt.date.today()) >= end


def _final_standings_order(standings: dict[str, dict]) -> dict[str, tuple]:
    """{org: key} that orders a settled field the way the league did: the
    division leader (divisionRank 1, the rule franchise_export.division_champions
    reads) first in its division, wild cards by wildCardRank, and division
    winners by leagueRank. Lower ranks higher. Used only on a wins tie."""
    out: dict[str, tuple] = {}
    for org, rec in standings.items():
        div_rank = rec.get("divRank")
        lg_rank = rec.get("leagueRank") or 99
        leader = div_rank == 1
        out[org] = (0 if leader else 1,
                    lg_rank if leader else (rec.get("wcRank") or 99),
                    lg_rank, org)
    return out


def _attach_current_season(rows: list[dict], standings: dict[str, dict],
                           il_out60: dict[str, int] | None = None,
                           season: int | None = None, *,
                           regular_season_end: str | None = None,
                           today=None) -> str | None:
    """Overlay the `current` block onto each team_outlook row IN PLACE and return
    the schedule-source flag ('live' | 'balanced_fallback' | 'season_complete' |
    None). rows carry the 2027 view; `standings` is standings_now(2026). No-op
    returning None when `standings` is empty (degraded/offline) - the 2027 output
    is left untouched.

    `regular_season_end` defaults to the cached StatsAPI /seasons date. Once
    `today` is on or after it and the live schedule lists nothing, the season is
    over: no game is scheduled, and the final standings decide the field."""
    if not standings:
        return None
    season = season or (FIRST_SEASON - 1)
    il_out60 = il_out60 or {}
    if regular_season_end is None:
        regular_season_end = _regular_season_end_on_disk(season)

    # 1) blend: pure talent prior (2027 team win total / 162) + actual + Pythag.
    prior_by_team: dict[str, float] = {}
    for r in rows:
        tm = r.get("team")
        rec = standings.get(tm)
        if not rec:
            r["current"] = None
            continue
        prior_pct = _talent_prior_pct(r.get("wins") or 0.0)
        prior_by_team[tm] = prior_pct
        cur = _current_blend(rec, prior_pct)
        cur["ilOut60"] = il_out60.get(tm)
        r["current"] = cur
        # flat mirrors for GFX / sortless consumers (mirror war/wins at :859)
        r["curWins"] = cur["curWins"]
        r["curPct"] = cur["curPct"]

    # 2) shared remaining schedule (live -> fallback), used by BOTH SOS + MC.
    import proj_current as pc
    teams_present = [r["team"] for r in rows if r.get("current")]
    # Pass the standings' own counts so the schedule read is reconciled against
    # them: the standings is disk-cached and the schedule is not, and the games
    # in that seam are final (dropped by the schedule) and unbooked (missing
    # from gamesPlayed), so without this every club can lose a game. Measured
    # 2026-09-17: a 09-16 standings cache against a 09-17 schedule read put all
    # 30 clubs on a 161-game season.
    played_now = {r["team"]: (r["current"].get("gamesPlayed") or 0)
                  for r in rows if r.get("current")}
    sched = pc.remaining_schedule(season, played=played_now)
    sched_source = "live"
    if not sched and _season_is_complete(regular_season_end, today):
        # THE SEASON IS OVER, SO NOTHING IS LEFT TO PLAY. The fallback below
        # fills 162 - gamesPlayed per club, and a club whose season ended at 161
        # (a rainout never made up) got a phantom game against a club already
        # done. Measured 2026-10-01: NYY 93-68 and BAL 79-82 each drew one, the
        # mirrored pairs gave BOS and CHW one too, and CHW 84-78 winning its
        # phantom tied CLE 85-77 for the AL Central, served as CLE Division
        # 74.9 percent and CHW 25.1 percent after the season had ended.
        sched = {}
        sched_source = "season_complete"
    elif not sched:
        # fallback needs a per-team games-remaining estimate: 162 - gamesPlayed.
        gr = {r["team"]: max(0, 162 - (r["current"]["gamesPlayed"] or 0))
              for r in rows if r.get("current")}
        sched = pc.balanced_remaining(teams_present, games_remaining=gr)
        sched_source = "balanced_fallback"

    # 3) log5 SOS + remaining-win expectation over that schedule.
    talent = {tm: prior_by_team.get(tm, 0.5) for tm in teams_present}
    sos_vals: dict[str, float] = {}
    for r in rows:
        cur = r.get("current")
        if not cur:
            continue
        tm = r["team"]
        opps = sched.get(tm) or []
        if not opps:
            cur["sos"] = None
            cur["remGames"] = 0
            cur["remWinExp"] = 0.0
            continue
        opp_pcts = [talent.get(o, 0.5) for o in opps]
        sos = sum(opp_pcts) / len(opp_pcts)
        rem_win_exp = sum(pc.log5(talent.get(tm, 0.5), op) for op in opp_pcts)
        cur["sos"] = round(sos, 4)
        cur["remGames"] = len(opps)
        cur["remWinExp"] = round(rem_win_exp, 1)
        sos_vals[tm] = sos
    # SOS rank: 1 = hardest (highest opponent talent). Ties broken by org.
    for rank, tm in enumerate(sorted(sos_vals, key=lambda t: (-sos_vals[t], t)), 1):
        for r in rows:
            if r.get("team") == tm and r.get("current"):
                r["current"]["sosRank"] = rank

    # 4) Monte-Carlo playoff odds over the SAME schedule + pure talent.
    mc_teams = {}
    for r in rows:
        cur = r.get("current")
        tm = r.get("team")
        rec = standings.get(tm)
        if not cur or not rec:
            continue
        mc_teams[tm] = {"wins": rec.get("wins") or 0, "losses": rec.get("losses") or 0,
                        "p": talent.get(tm, 0.5),
                        "league": rec.get("league"), "div": rec.get("div")}
    pairs = pc.remaining_pairs(season) if sched_source == "live" else _pairs_from_sched(sched)
    # A settled field breaks a wins tie by the league's own final ranks, not
    # by a draw, so Division, Bye and Playoffs land on 0 or 1.
    tiebreak = (_final_standings_order({tm: standings[tm] for tm in mc_teams})
                if sched_source == "season_complete" else None)
    odds = pc.simulate_playoffs(mc_teams, pairs, tiebreak=tiebreak)
    for r in rows:
        cur = r.get("current")
        if cur is None:
            continue
        o = odds.get(r.get("team"))
        if o:
            cur.update(o)
        else:
            # EVERY KEY THE BRACKET CAN EMIT, or a club that degraded carries
            # some of them and not others and every downstream reader has to
            # guess which. The postseason block only exists on a complete
            # thirty-club field, so this is the shape the futures export reads
            # to decide whether it has anything to publish at all.
            for kf in ("playoffPct", "divisionPct", "wildcardPct",
                       "projWinsMean", "projWinsP10", "projWinsP90",
                       "byePct", "wcRoundPct", "ldsPct", "lcsPct",
                       "pennantPct", "wsPct", "winTotal", "mc"):
                cur.setdefault(kf, None)
    return sched_source


def _fair_american(p, *, lo: float = 0.005, hi: float = 0.995):
    """American odds implied by a probability, or None outside a stated band.

    THE RAILS ARE THE POINT. `divisionPct == 1.0` and `playoffPct == 0.0` are
    both live in the served artifact right now, and this is the one column a
    reader is most likely to carry to a book. p = 1 gives minus infinity and
    p = 0 gives plus infinity, and an infinity rendered into a price cell is
    worse than a blank because it looks like a number.

    Outside the band the cell is empty and the row still sorts on the
    probability, which is the quantity the model actually produced.
    """
    try:
        p = float(p)
    except (TypeError, ValueError):
        return None
    if not (lo <= p <= hi):
        return None
    return round(-100.0 * p / (1.0 - p)) if p >= 0.5 else round(100.0 * (1.0 - p) / p)


FUTURES_AS_OF_TEMPLATE = ("As of the end of the regular season ({mlb_regular_end}): "
                          "postseason results are not in these odds.")


def futures_as_of_note(generated_at, regular_season_end) -> str | None:
    """The one line the Futures board prints once the regular season is over.

    THE SIMULATOR NEVER SEES A POSTSEASON GAME. It reads the regular-season
    schedule only (proj_current asks StatsAPI for gameType R) and plays the
    bracket from final standings, so from the first postseason game on it keeps
    publishing pre-bracket odds and no series result reaches them. Nothing is
    recomputed here; the line says what the numbers are.

    Built from the payload's own two dates: the build date (the UTC date of
    generated_at) and the season's last scheduled regular-season date. None
    before that date, and None when either date is missing or unreadable, so a
    regular-season build carries no line.

    THE DATE PRINTED IS THE SEASON'S END (site pass SP-D5, 2026-10-08). The line
    printed the build date, so /projections/ and /franchise/ read "As of the end
    of the regular season (2026-10-02)" for a season that ended 2026-09-27. It
    now prints regular_season_end, the same StatsAPI regularSeasonEndDate the
    site season state serves as mlb_regular_end; the build date only decides
    whether the line shows.
    """
    import datetime as _dt
    if not generated_at or not regular_season_end:
        return None
    build, end = str(generated_at)[:10], str(regular_season_end)[:10]
    try:
        if _dt.date.fromisoformat(build) < _dt.date.fromisoformat(end):
            return None
    except ValueError:
        return None
    return FUTURES_AS_OF_TEMPLATE.format(mlb_regular_end=end)


def _regular_season_end_on_disk(season: int) -> str | None:
    """regularSeasonEndDate for `season` from the cached StatsAPI /seasons
    payload, or None. Disk only: the futures write fetches nothing new."""
    try:
        from mgmt_decisions import regular_season_end_on_disk
        return regular_season_end_on_disk(season)
    except Exception:                                          # noqa: BLE001
        return None


def build_futures(rows: list, *, season: int | None = None,
                  regular_season_end: str | None = None) -> dict:
    """data/futures.json: the season-long outright board, model side only.

    THERE IS NO MARKET HERE AND THEREFORE NO EDGE. No futures price has ever
    been captured by this platform, so every value column a reader might expect
    is absent rather than estimated, and the payload says which one is missing
    and what would have to happen first.

    THE PRICE COLUMN IS NOT CALLED FAIR. "Fair" asserts zero expected value,
    which requires the probability to be right, and the model behind these
    numbers carries no validated forward record. It is an IMPLIED price: what
    the model's own probability would be worth if it were correct.

    DEGRADES TO AN EMPTY BOARD WITH A REASON. `simulate_playoffs` returns
    nothing on a partial standings read, the overlay then sets every postseason
    key to None, and a board of thirty nulls is worse than a board of none.
    """
    import datetime as _dt

    clubs = []
    for r in rows:
        cur = r.get("current") or {}
        if cur.get("wsPct") is None:
            continue
        mc = cur.get("mc") or {}
        wt = cur.get("winTotal") or {}
        clubs.append({
            "team": r.get("team"),
            "record": cur.get("record"),
            "projWins": cur.get("projWinsMean"),
            "winTotalP10": cur.get("projWinsP10"),
            "winTotalP90": cur.get("projWinsP90"),
            "winTotalSd": wt.get("sd"),
            "divisionPct": cur.get("divisionPct"),
            "playoffPct": cur.get("playoffPct"),
            "byePct": cur.get("byePct"),
            "pennantPct": cur.get("pennantPct"),
            "wsPct": cur.get("wsPct"),
            "impliedAmericanWS": _fair_american(cur.get("wsPct")),
            "impliedAmericanPennant": _fair_american(cur.get("pennantPct")),
            "impliedAmericanDivision": _fair_american(cur.get("divisionPct")),
            "mcWs": (mc.get("ws") or {}),
            "mcPennant": (mc.get("pennant") or {}),
            "mcPlayoff": (mc.get("playoff") or {}),
        })
    clubs.sort(key=lambda c: -(c["wsPct"] or 0))

    import hashlib
    key = "|".join(f"{c['team']}:{c['divisionPct']}:{c['playoffPct']}:{c['byePct']}:"
                   f"{c['pennantPct']}:{c['wsPct']}:{c['projWins']}"
                   for c in sorted(clubs, key=lambda x: str(x["team"])))
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12] if clubs else None

    sims = None
    for r in rows:
        mc = ((r.get("current") or {}).get("mc") or {})
        if mc.get("sims"):
            sims = mc["sims"]
            break

    generated_at = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    return {
        "generated_at": generated_at,
        "produced_by": "proj_export.build_futures",
        "season": season,
        "regular_season_end": regular_season_end,
        "as_of_note": futures_as_of_note(generated_at, regular_season_end),
        "content_hash": digest,
        "sims": sims,
        "clubs": clubs,
        "empty_reason": (None if clubs else
                         "The season simulator returned no postseason block "
                         "(partial standings read, or not a complete "
                         "thirty-club field), so no board of thirty nulls is "
                         "published."),
        "no_market": {
            "captured": False,
            "what_is_missing": (
                "No futures price has been captured, so there is no book "
                "number, edge column, value flag or expected return."),
            "what_would_have_to_happen": (
                "Capture needs a weekly outrights pull at about 20 credits a "
                "month from the 500-credit monthly tier shared with game odds "
                "and props, so it is an owner decision."),
            "and_then_still_not_an_edge": (
                "A captured price would still be unvalidated: the futures "
                "backtest has not been run, and nothing here may be published "
                "as value until it has."),
        },
        "why_the_price_column_is_not_called_fair": (
            "A fair price asserts zero expected value, which requires the "
            "probability to be right. These probabilities come from a "
            "simulator with no validated forward record, so the column is the "
            "price implied by the model's own probability."),
        "what_the_intervals_are": (
            "Intervals are Monte Carlo error only: how far the number moves "
            "if the simulation is re-run. Error in the talent estimate "
            "underneath it is much larger and not measured here."),
        "win_total_basis": (
            "The win band is schedule noise at a fixed talent estimate: no "
            "talent uncertainty, in-season drift, injuries or trades. It is "
            "narrower than a real forecast interval by an unmeasured amount."),
    }


def _pairs_from_sched(sched: dict[str, list[str]]) -> list[tuple[str, str]]:
    """Reconstruct (home, away) pairs from a {org:[opp,...]} fallback schedule,
    de-duplicating the mirrored entries (each game appears on both teams)."""
    seen: dict[tuple, int] = {}
    pairs: list[tuple[str, str]] = []
    for tm, opps in sched.items():
        for op in opps:
            key = tuple(sorted((tm, op)))
            seen[key] = seen.get(key, 0) + 1
    for (a, b), cnt in seen.items():
        for _ in range(max(1, cnt // 2)):
            pairs.append((a, b))
    return pairs


def _il_out60(season: int) -> dict[str, int]:
    """Display-only {org: count of 40-man players on the 60-day IL}. Best-effort;
    {} on any failure (badge just doesn't render). Never feeds a projection."""
    try:
        import proj_current  # noqa: F401  (keep import graph explicit)
        from trades import canonical_org
        from scrapers import _fetch
    except Exception:                                          # noqa: BLE001
        return {}
    teams_url = "https://statsapi.mlb.com/api/v1/teams?sportId=1&season={}".format(season)
    fr = _fetch(teams_url, f"statsapi_teams_{season}", accept_json=True)
    if fr.status != 200 or not fr.body:
        return {}
    out: dict[str, int] = {}
    try:
        teams = json.loads(fr.body).get("teams") or []
    except (ValueError, TypeError):
        return {}
    for t in teams:
        tid, name = t.get("id"), t.get("name")
        org = canonical_org(name or "")
        if not tid or not org or len(org) > 3:
            continue
        rr = _fetch("https://statsapi.mlb.com/api/v1/teams/{}/roster?rosterType=40Man"
                    "&season={}".format(tid, season),
                    f"statsapi_roster_40man_{tid}_{season}", accept_json=True)
        if rr.status != 200 or not rr.body:
            continue
        try:
            roster = json.loads(rr.body).get("roster") or []
        except (ValueError, TypeError):
            continue
        n = sum(1 for p in roster
                if ((p.get("status") or {}).get("code")) in _IL60_CODES)
        if n:
            out[org] = n
    return out


# ============================================================================
# Model Accountability (/projections/#view=accountability)
# ============================================================================
# Curated, ordered registry rows that power the projections surface, paired
# with a friendly card label. The view renders each model's owner-committed
# verdict + methodology straight from the audit ledger (model_registry.json),
# never a re-derived claim, alongside the held-out backtest tables below.
_ACCOUNTABILITY_MODELS = [
    ("fa_war_paths_decay", "Veteran WAR paths"),
    ("mlb_projections_prospects", "Prospect post-ETA paths"),
    ("team_win_projections", "Team win totals"),
    ("prospect_surplus", "Surplus pricing"),
]


def _read_data_json(name: str) -> dict:
    """Best-effort read of a committed data/ artifact; missing or unparseable
    degrades to {} so the accountability block surfaces whatever is present.

    CONSERVATIVE-DIRECTION GUARD, verified 2026-08-07 (silent-empty sweep).
    Every caller of this is the accountability surface, whose contract is that
    it prints only verdicts it read from the committed ledger. An empty read
    therefore omits a CARD; it can never leave a stale or unbacked verdict on
    screen, which is the failure that would matter here. The artifacts are
    committed to the repo and their freshness is separately gated by
    test_methodology_freshness.py, so absence is a repo-level break with its
    own alarm rather than a silent nightly one. Do not re-flag it."""
    try:
        return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _accountability_block() -> dict:
    """The Model Accountability surface: the projection models' verdicts +
    methodology from data/model_registry.json, plus the held-out backtest
    'receipts' read verbatim from the committed eval artifacts. Pure
    surfacing - no metric is computed here; the registry is the single source
    of truth (refreshed monthly, gated by test_methodology_freshness.py).
    Each backtest is keyed by its eval_artifact so the frontend can attach it
    to the matching card. Missing artifacts degrade to empty."""
    reg = _read_data_json("model_registry.json")
    by_id = {m["model_id"]: m for m in reg.get("models", [])}
    # The salary-path census (ask C). Computed in `_apply_salary_paths`, which
    # is the only place that sees both the built rows and the board, and read
    # here because this block is where the payload publishes what it did and
    # did not reach. Empty on a payload built without veterans.
    keep = ("model_id", "summary", "surface", "predicts", "champion",
            "baseline", "metric", "verdict", "remeasure_pending", "notes",
            "eval_artifact", "last_checked", "artifact_age_days", "stale")
    models = []
    for mid, label in _ACCOUNTABILITY_MODELS:
        m = by_id.get(mid)
        if m:
            models.append({"label": label, **{k: m.get(k) for k in keep}})

    # Team win totals: the retro backtest (2022-25, holdout-gated) read
    # straight from the committed artifact - per-season team-wins MAE/r for
    # the shipped engine vs the prior-wins baseline, pooled player bias, the
    # ship decision, and the still-pending forward gate.
    to = _read_data_json("team_outlook_eval.json")
    retro = to.get("retro_backtest") or {}
    # The table scores the arm that SERVES, chosen by the same ship decision
    # _cohort_intercepts() gates on: the cohort-intercept arm only when the
    # challenger won its holdout, plain uniform recentering otherwise. It used
    # to read cohort_recentered unconditionally, so after the 2026-08-04 gate
    # loss the card printed an arm the roll-up no longer applies.
    served_arm = ("cohort_recentered"
                  if (retro.get("ship_decision") or {}).get("challenger_wins")
                  else "recentered")
    team_wins = {
        "design": retro.get("design"),
        "served_arm": served_arm,
        "retro_generated_at": retro.get("generated_at"),
        "per_season": [
            {"season": s.get("season"),
             "n_assigned_players": s.get("n_assigned_players"),
             "is_holdout": s.get("is_holdout"),
             "mae": (s.get(served_arm) or {}).get("mae"),
             "r": (s.get(served_arm) or {}).get("r"),
             "baseline_mae": (s.get("baseline_prior_wins") or {}).get("mae"),
             "baseline_r": (s.get("baseline_prior_wins") or {}).get("r")}
            for s in (retro.get("team_level_per_season") or [])
        ],
        "player_pooled": (retro.get("player_level") or {}).get("pooled"),
        "ship_decision": retro.get("ship_decision"),
        "forward_gate": to.get("forward_gate"),
    } if retro else {}

    # Veteran WAR paths: the touched-once 2022-24 holdout - the shipped
    # champion (proj_lgbm_v1) against the prior champion / baseline
    # (marcel_decay_v2), per horizon. Holdout labels mature only through h4.
    he = _read_data_json("proj_horizon_eval.json")
    cb = he.get("challenger_blocks") or {}

    def _horizon_rows(block) -> list[dict]:
        # `coverage` is the POOLED band coverage. The eval harness's own
        # docstring warns absent seasons (actual=0) sit inside almost any
        # P10-P90 band, so pooled coverage reads trivially high (~0.9+) and is
        # NOT band reliability. Surface the honest reads alongside it -
        # coverage_survived (only players who actually played the target
        # season, plus its n) and the pinball loss (the proper quantile scoring
        # rule) - so the accountability view is not misleadingly optimistic.
        # All four are already computed and committed on each horizon block by
        # proj_eval; this is pure surfacing (additive - the frontend still
        # reads h/n/mae/bias/coverage and degrades absent the new fields).
        hz = (block or {}).get("horizons") or {}
        return [{"h": int(h), "n": v.get("n"), "mae": v.get("mae"),
                 "bias": v.get("bias"), "coverage": v.get("coverage"),
                 "coverage_survived": v.get("coverage_survived"),
                 "n_survived": v.get("n_survived"),
                 "pinball_q10": v.get("pinball_q10"),
                 "pinball_q90": v.get("pinball_q90"),
                 "mae_star": v.get("mae_star"), "n_star": v.get("n_star")}
                for h, v in sorted(hz.items(), key=lambda kv: int(kv[0]))]

    vet_horizons = {
        "frame": "2022-2024 holdout (touched once; labels mature through h4)",
        "champion": {"model": "proj_lgbm_v1",
                     "horizons": _horizon_rows(cb.get("holdout_2022_2024"))},
        "baseline": {"model": "marcel_decay_v2",
                     "horizons": _horizon_rows(cb.get("holdout_2022_2024_champion"))},
    } if cb.get("holdout_2022_2024") else {}

    # Prospect post-ETA paths: forward-chained debut cohorts. The FV-only
    # scouting-consensus model (the shipped champion, labeled "baseline" in
    # the artifact's A/B) vs the MiLB-stats ridge challenger that lost its
    # pre-registered gate - committed either way.
    pe = _read_data_json("prospect_path_eval.json")
    champ = pe.get("baseline_pooled_oos") or {}
    chall = pe.get("challenger_pooled_oos") or {}
    prospect_paths = {
        "scored_years": pe.get("scored_years"),
        "champion": {"label": "FV outcome model (scouting consensus)",
                     "n": champ.get("n"), "mae": champ.get("mae"),
                     "spearman": champ.get("spearman")},
        "challenger": {"label": "MiLB-stats ridge (committed loss)",
                       "n": chall.get("n"), "mae": chall.get("mae"),
                       "spearman": chall.get("spearman")},
        "ship_decision": pe.get("ship_decision"),
    } if champ else {}

    # EACH SURFACE SERVES THE ENGINE THAT WON ITS OWN GATE (owner answer M15-1,
    # 2026-09-25, "use whichever model wins"): /projections/ the ML heads that
    # beat the champion on the player-level holdout, /fa/ the champion path its
    # market model passed Gate 2 on (fa_market.enriched_signings, use_ml=False).
    # Both pages disclose it, and both disclosures read THIS block, which copies
    # the two committed eval artifacts, so neither verdict is a sentence in code.
    base_by_h = {r["h"]: r for r in ((vet_horizons.get("baseline") or {}).get("horizons") or [])}
    proj_rows = [{"h": r["h"], "n": r.get("n"), "mae": r.get("mae"),
                  "mae_comparator": (base_by_h.get(r["h"]) or {}).get("mae")}
                 for r in ((vet_horizons.get("champion") or {}).get("horizons") or [])]
    g2 = _read_data_json("fa_gate2_eval.json")
    g2_pooled = {k: {"mae_model": v.get("mae_model"), "mae_base": v.get("mae_base"),
                     "n": v.get("n")}
                 for k, v in (g2.get("pooled") or {}).items()
                 if k in ("guarantee", "aav", "years") and isinstance(v, dict)}
    surface_engines = {
        "rule": "each surface serves the engine that won its own gate "
                "(owner answer M15-1, 2026-09-25)",
        "projections": {
            "engine": (vet_horizons.get("champion") or {}).get("model"),
            "comparator": (vet_horizons.get("baseline") or {}).get("model"),
            "gate": "player-level WAR holdout, both engines on the same frame",
            "frame": "2022-2024 holdout",
            "artifact": "data/proj_horizon_eval.json",
            "generated_at": he.get("generated_at"),
            # the gate row's own caveat, printed beside the figures it qualifies
            "registry_row": "fa_war_paths_decay",
            "remeasure_pending": (by_id.get("fa_war_paths_decay") or {}).get("remeasure_pending"),
            "by_horizon": proj_rows,
        } if proj_rows else None,
        "fa": {
            "engine": "marcel_decay_v2",
            "input": "champion paths (fa_market.enriched_signings, use_ml=False)",
            "gate": "FA Gate 2, market model",
            "artifact": "data/fa_gate2_eval.json",
            "generated_at": g2.get("generated_at"),
            "registry_row": "fa_market",
            "remeasure_pending": (by_id.get("fa_market") or {}).get("remeasure_pending"),
            "war_provider": g2.get("war_provider"),
            "pass": g2.get("pass"),
            "pooled": g2_pooled,
        } if g2_pooled else None,
    }

    return {
        "generated_at": date.today().isoformat(),
        "registry_version": reg.get("version"),
        "verdict_enum": reg.get("verdict_enum"),
        "models": models,
        # What the salary path reached and what it did not, published in the
        # payload rather than left in a log line: coverage by source and by
        # token, the rows whose control window is NOT established and why, the
        # non-tender census, the pre-arb negative dollars the cliff
        # deliberately does not price (decision D11), and the board vintage the
        # whole thing was priced off.
        "salary_path": dict(_SALARY_PATH_CENSUS),
        # keyed by eval_artifact so the frontend attaches each table to its card
        "backtests": {
            "data/team_outlook_eval.json": team_wins,
            "data/proj_horizon_eval.json": vet_horizons,
            "data/prospect_path_eval.json": prospect_paths,
        },
        "surface_engines": surface_engines,
    }


def _off_contract_club(v: dict) -> str | None:
    """The Spotrac contract club of a veteran row when it differs from the
    row's `team`, else None. One test for both the count in `team_basis` and
    the audit-only `contract_club` field, so the two cannot disagree."""
    _src, ct_club = _TEAM_BASIS_CENSUS.get(v.get("mlbam"), (None, None))
    if ct_club and v.get("team") and ct_club != v["team"]:
        return ct_club
    return None


def _stamp_contract_club(vets: list[dict]) -> int:
    """AUDIT-ONLY (owner answer M23-2, 2026-09-25): write `contract_club`, the
    Spotrac club paying the salary, on exactly the veteran rows where it
    differs from the row's current `team`, and nowhere else. No page reads
    it; it lets an audit see which club a traded player's contract was
    scraped under without re-running the Spotrac join. Returns the number
    of rows stamped, which equals team_basis.n_off_contract_club."""
    n = 0
    for v in vets:
        v.pop("contract_club", None)
        club = _off_contract_club(v)
        if club:
            v["contract_club"] = club
            n += 1
    return n


def _stamp_fa_class(vets: list[dict]) -> int:
    """QMLP09: `fa: true` on exactly the veteran rows whose key is a member
    of data/fa_class.json, the test mlb_player_export uses for the identity
    map's `fa` flag. The board reads it for its '$ FA' chip instead of
    fetching the 1.9 MB player_links.json at boot. Absent on every other row.
    Returns the number of rows stamped (published as n_fa)."""
    try:
        fa = json.loads((DATA_DIR / "fa_class.json").read_text(encoding="utf-8"))
        keys = {m.get("key") for m in fa.get("members") or [] if m.get("key")}
    except (OSError, ValueError):
        keys = set()
    n = 0
    for v in vets:
        v.pop("fa", None)
        if v.get("key") in keys:
            v["fa"] = True
            n += 1
    return n


def _team_basis_block(vets: list[dict]) -> dict:
    """The disclosure for the club every veteran row is counted under, read
    from the census _vet_club kept while the rows were built."""
    from collections import Counter
    by_src: Counter = Counter()
    n_off_contract = 0
    for v in vets:
        src, _ct_club = _TEAM_BASIS_CENSUS.get(v.get("mlbam"), (None, None))
        by_src[src or "none"] += 1
        if _off_contract_club(v):
            n_off_contract += 1
    return {
        "basis": "current_club",
        "order": list(CLUB_SOURCES),
        "n_rows": len(vets),
        "by_source": {k: by_src.get(k, 0) for k in (*CLUB_SOURCES, "none")},
        "n_off_contract_club": n_off_contract,
        "contract_club_field": ("Audit-only: each of those rows carries contract_club, "
                                "the Spotrac club paying the salary. No page reads it."),
        "note": ("The club that holds the player today: MLB's transaction feed for "
                 "a move this season, then the club StatsAPI shows him playing for "
                 "this season, then the Spotrac contract club, then his last "
                 "club seen. A traded player's contract moves with him, so the "
                 "contract club is used only when neither newer source places him."),
    }


def build_payload() -> dict:
    """The /projections/ payload. In unified $/WAR path mode (VAL_5 row 10) the
    stamps name P(B), the path by season and the pricing basis."""
    assert_first_season_flip_allowed()
    payload = _build_payload_body()
    if vf.dpw_path_active():
        _stamp_dpw_path(payload)
    return payload


def _build_payload_body() -> dict:
    corpus = fp.build_corpus()
    names = _display_names()
    from spotrac import scrape_all_spotrac_contracts, build_contracts_by_key, _SPOTRAC_TEAM_SLUGS
    slug_to_org = {slug: code for code, slug in _SPOTRAC_TEAM_SLUGS.items()}
    contracts = {}
    for key, c in build_contracts_by_key(scrape_all_spotrac_contracts()).items():
        contracts[key] = _join_contract(c, slug_to_org)
    dpw = _winter_dpw(FIRST_SEASON)
    vets = _veteran_rows(corpus, names, contracts, dpw)
    prospects = _prospect_rows(dpw)
    depth_team_war, depth_acct = _depth_pool(
        corpus, names, contracts, {m["mlbam"] for m in vets if m.get("mlbam")})
    team_outlook = _team_outlook(vets, prospects, depth_team_war, depth_acct,
                                 _cohort_intercepts())
    # Current-season (2026) overlay - ADDITIVE, dark-launched. Best-effort: any
    # fetch failure (offline / degraded local build) leaves team_outlook exactly
    # as the 2027-only output and mc_schedule_source None. FIRST_SEASON-1 = 2026.
    mc_schedule_source = None
    try:
        from fa_fit_backtest import standings_now as _standings_now
        _sn = _standings_now(FIRST_SEASON - 1)
        if _sn:
            mc_schedule_source = _attach_current_season(
                team_outlook, _sn, il_out60=_il_out60(FIRST_SEASON - 1),
                season=FIRST_SEASON - 1)
    except Exception:                                          # noqa: BLE001
        log.warning("current-season overlay skipped (best-effort)", exc_info=True)
    # Audit-only payer field (M23-2): after every consumer above has read the
    # rows, so nothing in this build can price or roll up on it.
    _stamp_contract_club(vets)
    n_fa = _stamp_fa_class(vets)
    cfg = vf._config()
    if vf.dpw_path_active() and "dollars_per_war_inflation" not in cfg:
        raise vf.DpwPathError("dollars_per_war_inflation absent in unified $/WAR path mode")
    # One read of the escalation knob: the payload field and the dollars note
    # both say what _season_value_usd actually applied (0.0 in production).
    _dpw_infl = float(cfg.get("dollars_per_war_inflation", 0.05))
    re_anchor = (cfg["dollars_per_war"].get("_fa_reanchor") or {})
    return {
        "generated_at": date.today().isoformat(),
        # Which dollar calibration priced surNpv on the veteran rows. Prospect
        # surNpv is copied from the eFV export (RVA02), which carries its own
        # stamp; test_calibration_vintage holds the two stamps equal.
        "calibration": vf.calibration_stamp(),
        "first_season": FIRST_SEASON, "horizon": HORIZON,
        # Provenance for the rest-of-season control leg (surRos / surTotal):
        # the share of the in-progress season already played, and therefore the
        # share still being sold. Published so a reader can reconstruct surRos
        # instead of taking it on trust.
        "season_fraction": round(fp.season_fraction(corpus["league"],
                                                    FIRST_SEASON - 1), 3),
        "ros_fraction": round(max(0.0, min(1.0, 1.0 - fp.season_fraction(
            corpus["league"], FIRST_SEASON - 1))), 3),
        # Which TALENT the remainder was priced on (provenance stamp, not a
        # second behaviour read - the switch itself is read once, in
        # `_ros_talent_basis`). Per-row `rosBasis` can differ from this where a
        # row's de-aging was unresolved; see ROS_TALENT_BASIS.
        "ros_talent_basis": ROS_TALENT_BASIS,
        "dpw_usd": int(dpw),
        "dpw_infl": _dpw_infl,
        "dpw_reanchor": re_anchor or None,
        "n_vets": len(vets), "n_prospects": len(prospects),
        # Veteran rows carrying fa: true (current FA class members). Its
        # presence tells the board the rows carry the flag.
        "n_fa": n_fa,
        # Where each veteran's `team` came from (resolve_current_club), and how
        # many rows sit on a club other than their Spotrac contract club.
        "team_basis": _team_basis_block(vets),
        "vets": vets, "prospects": prospects,
        "team_outlook": team_outlook,
        "current_season": (FIRST_SEASON - 1) if mc_schedule_source else None,
        "mc_schedule_source": mc_schedule_source,
        "accountability": _accountability_block(),
        "notes": [
            "veterans: proj_lgbm_v1 quantile heads (horizons 1-5) stacked on the FA module's Marcel champion; war = the median head lifted toward the quantile-implied mean where it sits below it, bands = the P10/P90 heads; warChamp = the champion mean path (the FA pricing path and the Team Outlook sum basis); rows the heads cannot score fall back to the champion with Gate-1 residual-quantile bands",
            "prospects: P(bucket|FV) x calibrated per-bucket WAR trajectories from projected debut age, starting at the PROSPX ETA; floor/ceiling = 10th/90th-percentile OUTCOME buckets; surNpv = the eFV surplus (the eFV export's surplus_mm, the figure the Trade Machine board serves), copied and not repriced here",
            "quantile totals: warTotalP10Comon / warTotalP90Comon are the SUM of the per-season P10 / P90, not the P10 / P90 of the total, and are never printed as a range",
            f"dollars: convex tier pricing at the {FIRST_SEASON} ex-ante FA $/WAR level "
            "(the one written series /fa/ prices the class on; prospect seasons price at the same level), "
            + (f"escalated {_dpw_infl * 100:.1f}%/yr" if _dpw_infl else "flat across seasons")
            + "; veteran surplus over the control window: contracted seasons at their salary, pre-arbitration seasons at the league minimum, arbitration seasons at the projected award, discounted at the platform rate"
            + (f"; a guarantee that runs past {FIRST_SEASON + HORIZON - 1} is priced through its last season, "
               + ("those seasons on the champion mean path (warChamp extended, published per season as warTail), "
                  if TAIL_SEAM == "champion_level" else
                  f"those seasons on the champion (Marcel) aging curve chained from the served {FIRST_SEASON + HORIZON - 1} WAR "
                  "(the FA module's seam, fa_market.chain_aging_tail; published per season as warTail), ")
               + "and an unsigned season past it carries no price"
               if PRICE_CONTRACT_TAIL else
               f"; nothing past {FIRST_SEASON + HORIZON - 1} is priced"),
            "two-way players project BOTH sides, summed per season (per-side paths in warHit/warPit; bands combine at assumed cross-side correlation rho=0.5 - documented)",
            f"veteran universe: >= {MIN_PA} PA or >= {MIN_IP} IP in one of the last three seasons",
            f"rest-of-season leg: talent basis '{ROS_TALENT_BASIS}' - " + (
                f"the remainder of the in-progress season is priced on the {FIRST_SEASON} "
                "projection de-aged one year by the inverse of the fitted aging curves "
                "(the platform's own decay operator, run backwards); rows whose de-aging "
                "is unresolved keep the undecayed projection and ship "
                "rosBasis='first_season_unresolved'"
                if ROS_TALENT_BASIS == "de_aged" else
                f"the remainder of the in-progress season is priced on the {FIRST_SEASON} "
                "projection itself, one aging year past the season being sold"),
        ],
    }


def export() -> int:
    payload = build_payload()
    raw = json.dumps(payload, separators=(",", ":"))
    (DATA_DIR / "mlb_projections.json").write_text(raw, encoding="utf-8")
    log.info("mlb projections export: %dKB, %d vets + %d prospects",
             len(raw) // 1024, payload["n_vets"], payload["n_prospects"])
    # THE FUTURES BOARD RIDES THE SAME PAYLOAD, from export() rather than from
    # inside _attach_current_season. The overlay is called directly by tests on
    # two-club synthetic universes, and writing an untracked artifact from there
    # would leave a file conftest's revert cannot restore.
    write_futures(payload.get("team_outlook") or [])
    return len(raw)


# The markets the ledger records, and the only ones it will ever be allowed to
# score. Each is a probability this board publishes for a club-season, so each
# resolves to a 0 or a 1 once the season is over. `winTotal` is deliberately
# absent: it is a count, not a probability, and it would need a different loss.
LEDGER_MARKETS = ("divisionPct", "playoffPct", "byePct", "pennantPct", "wsPct")

#: THE LEDGER LIVES OUTSIDE data/, AND THE REASON IS WRITTEN DOWN TWICE ALREADY.
#: deploy/nightly-build.sh runs `git checkout -- .` before every pipeline. An
#: accruing file inside data/ therefore has three possible states and two of them
#: destroy it: TRACKED means every appended entry is reverted at 03:10 with no
#: error anywhere (this is what killed the public betting record, see the
#: .gitignore note on data/betting_record.json), and UNTRACKED-AND-UNIGNORED is
#: worse still, because it survives today and one `git add -A` arms the tracked
#: failure later. Only `.cache/` both escapes the checkout and sits on the backup
#: list in deploy/WEBMASTER.md, so it is also the only state that survives a box
#: rebuild.
#:
#: So `.cache/futures/ledger.json` is the SOURCE OF TRUTH and
#: `data/futures_ledger.json` is a DERIVED re-render, published by rsync and safe
#: to lose. Same seam as betting_shadow.py, for the same reason.
#:
#: A JSON OBJECT AND NOT A JSONL LOG, matching the shadow ledger rather than the
#: public record: resolution fills `resolved` and the realized outcomes in on
#: entries already written, which a one-line-per-append log cannot express
#: without an envelope-per-mutation format this file does not have.
FUTURES_CACHE_DIR = DATA_DIR.parent / ".cache" / "futures"
FUTURES_LEDGER_CACHE = FUTURES_CACHE_DIR / "ledger.json"
FUTURES_LEDGER_DERIVED = DATA_DIR / "futures_ledger.json"
FUTURES_LEDGER_PATH = FUTURES_LEDGER_CACHE


def append_futures_ledger(fut: dict, *, season: int | None = None,
                          today: str | None = None,
                          path: Path | None = None) -> dict:
    """Append what this build published, so a forward record can start accruing.

    data/futures.json carries the sentence "These probabilities come from a
    simulator with no validated forward record", and that sentence stays true
    forever unless something writes the record down. A probability published
    tonight and overwritten tomorrow night can never be scored: by the time the
    season resolves, the only number left on disk is the last one, taken when
    most of the uncertainty had already gone.

    THIS SCORES NOTHING. It records. Resolution needs final standings and a
    postseason result, and the ledger states how many entries are waiting rather
    than implying any of them have been graded.

    IDEMPOTENT PER DAY. The nightly run, a rebuild_only and a hand run on the
    same date collapse to one entry, the last written. Without that, a day the
    box was run four times would carry four times the weight of a day it ran
    once, and the record would be measuring pipeline activity.
    """
    import datetime as _dt

    path = path or FUTURES_LEDGER_PATH
    today = today or _dt.date.today().isoformat()
    season = int(season or _dt.date.today().year)
    # READ THE CACHE, and fall back to the derived copy exactly once so a box that
    # already has a data/ ledger from before the seam existed keeps its history
    # instead of restarting the clock at zero.
    led = {}
    for src in (path, FUTURES_LEDGER_DERIVED if path == FUTURES_LEDGER_CACHE else None):
        if src is None:
            continue
        try:
            led = json.loads(src.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if led.get("entries"):
            if src is not path:
                log.info("futures ledger: adopting %d entr%s from %s (pre-seam copy)",
                         len(led["entries"]), "y" if len(led["entries"]) == 1 else "ies",
                         src.name)
            break
    entries = [e for e in (led.get("entries") or [])
               if not (e.get("as_of") == today and int(e.get("season", -1)) == season)]
    clubs = [{"team": c.get("team"), "record": c.get("record"),
              "projWins": c.get("projWins"),
              **{m: c.get(m) for m in LEDGER_MARKETS}}
             for c in (fut.get("clubs") or [])]
    if clubs:
        entries.append({
            "as_of": today,
            "season": season,
            # so an entry can be CHECKED against a re-run rather than trusted
            "content_hash": fut.get("content_hash"),
            "sims": fut.get("sims"),
            "n_clubs": len(clubs),
            "resolved": False,
            "clubs": clubs,
        })
    entries.sort(key=lambda e: (int(e.get("season", 0)), str(e.get("as_of"))))
    by_season: dict[str, int] = {}
    for e in entries:
        by_season[str(e.get("season"))] = by_season.get(str(e.get("season")), 0) + 1
    out = {
        "_meta": {
            "produced_by": "proj_export.append_futures_ledger",
            "markets": list(LEDGER_MARKETS),
            "n_entries": len(entries),
            "n_resolved": sum(1 for e in entries if e.get("resolved")),
            "entries_by_season": by_season,
            "first_as_of": entries[0]["as_of"] if entries else None,
            "last_as_of": entries[-1]["as_of"] if entries else None,
            "one_entry_per_day": ("A rebuild on a date already present replaces that "
                                  "date's entry, so repeat runs on one day add no "
                                  "weight."),
            "nothing_here_is_scored": (
                "No entry has been graded and no accuracy claim rests on this file. "
                "Scoring needs a completed season (division winners, the playoff "
                "field, bye holders, both pennants, the World Series winner) joined "
                "to the entry live on each date."),
            "why_win_total_is_absent": (
                "winTotal is a count that resolves to a number rather than a 0 or 1, "
                "so it needs a different loss and is kept out of the "
                f"{len(LEDGER_MARKETS)} outright markets here."),
        },
        "entries": entries,
    }
    raw = json.dumps(out, indent=1)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(raw, encoding="utf-8")
    tmp.replace(path)
    # The derived copy is what rsync publishes. It is written from the same
    # object rather than re-derived, so the two can never disagree, and losing it
    # costs nothing.
    if path == FUTURES_LEDGER_CACHE:
        FUTURES_LEDGER_DERIVED.parent.mkdir(parents=True, exist_ok=True)
        tmp = FUTURES_LEDGER_DERIVED.with_suffix(".json.tmp")
        tmp.write_text(raw, encoding="utf-8")
        tmp.replace(FUTURES_LEDGER_DERIVED)
    return out


def write_futures(rows: list) -> int:
    season = FIRST_SEASON - 1
    fut = build_futures(rows, season=season,
                        regular_season_end=_regular_season_end_on_disk(season))
    # The forward record starts here, and it can only ever start once. Appending
    # BEFORE the write keeps futures.json and the ledger describing the same
    # build; content_hash is a digest of the clubs alone, so the summary block
    # below does not invalidate it.
    led = append_futures_ledger(fut)
    fut["ledger"] = {
        "path": "data/futures_ledger.json",
        "source_of_truth": ".cache/futures/ledger.json",
        "n_entries": led["_meta"]["n_entries"],
        "n_resolved": led["_meta"]["n_resolved"],
        "first_as_of": led["_meta"]["first_as_of"],
        "markets": led["_meta"]["markets"],
        "what_it_is": ("Each build appends its published probabilities, one entry "
                       "per day. Nothing in it is scored yet: scoring needs a "
                       "completed season joined to the entries live through it."),
    }
    raw = json.dumps(fut, separators=(",", ":"))
    (DATA_DIR / "futures.json").write_text(raw, encoding="utf-8")
    log.info("futures export: %d clubs, hash %s, ledger %d entr%s",
             len(fut["clubs"]), fut["content_hash"],
             led["_meta"]["n_entries"],
             "y" if led["_meta"]["n_entries"] == 1 else "ies")
    return len(raw)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(export())
