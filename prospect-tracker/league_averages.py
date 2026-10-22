# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""league_averages - the League Averages panels and the over-time series for
the League tab of /mlbstats/ (owner asks 13 and 14 of 2026-09-30; plan Part 8
item P8.2, task LT-04; the lane design is part8/league_team_stats.md sections
2, 3, 4, 7.1, 7.2 and 8).

WHAT IT WRITES. One panel per season, 2000 to the live season
(`mlb_league_panel_<Y>.json`: one row per player-season, the pooled groups and
the club block), and one series file (`mlb_league_series.json`: the cells of
the over-time charts, season by season). Every number is a sum, a pooled ratio
or a served per-player value re-weighted. Nothing here is a forecast, so there
is no registry row.

THE FLAG. MLBSTATS_LEAGUE_TEAMS_LIVE is the one flag the exporters and, later,
build_site read. While it is False every file goes to
.cache/league_teams/preview/ and nothing under data/ changes (plan 8.D row
14: a new data/ file ships to the webroot, so dark means no new served file).
The flip is its own commit (Q8_15) carrying the flag, the data/ files, the
glossary entries and the registry surface text together.

ROW RULE. A row is a player's StatsAPI season line with playerPool=All
(.cache/fa_statsapi_{hitting,pitching}_<Y>.json). A traded player's row is his
season total under his LAST club (bullpen_export.py, module docstring), which
is why a club filter is left out (see LEFT_OUT).

POOLED RULE. A group's League value hands the summed counts back through the
shipped derivations (mlbstats_rates.hitter_rates over hem_plus.derive_rates;
mlbstats_rates.pitcher_rates over sem_plus.derive_rates), so no second formula
for AVG, OBP, ERA or K% exists here. P/PA, P/IP and P/BF are pitch_rates'
definitions (innings are outs / 3). FIP is the standard formula with the
season constant from league_constants.league_totals on the same sums, and is
labelled apart from the boards' Skill FIP, which is shrunk toward one season's
pool and never pooled. The index rows (HEM+, SEM+, REM+, DEM+) are PA-, IP-,
IP- and innings-weighted means of the per-player values the boards and the
window lab computed; no index is computed here.

REFUSALS (the last good file is kept). A season is refused when either
StatsAPI group's splits are empty; when league PA differs from league batters
faced, or pitches seen from pitches thrown (exact on a complete season, within
LIVE_TOLERANCE on the live one); when the FIP constant recomputed from the
panel's own sums misses league_totals by more than FIP_TOLERANCE; or, on the
live season, when under MIN_BOARD_JOIN of any live board's rows join the
panel.

DISK ONLY. Every input is read from a cache or a served file the pipeline
already writes; this module makes no network request.

Usage:
    python league_averages.py                 # missing completed seasons + the live one
    python league_averages.py --season 2025   # one season, then the series
    python league_averages.py --all           # rebuild every season
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import time
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Optional

import mlbstats_rates
import pitch_rates

MLBSTATS_LEAGUE_TEAMS_LIVE = True

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / ".cache"
PREVIEW_DIR = CACHE_DIR / "league_teams" / "preview"
LAB_DIR = CACHE_DIR / "mlbstats_windows"

SCHEMA = 1
FIRST_SEASON = 2000
PANEL_NAME = "mlb_league_panel_{season}.json"
SERIES_NAME = "mlb_league_series.json"
SOURCE = "league_averages"

LIVE_TOLERANCE = 0.001        # 0.1 percent, the live season's identity slack
FIP_TOLERANCE = 0.0005        # against league_constants.league_totals
MIN_BOARD_JOIN = 0.90         # share of a live board's rows that must join

FLOOR_PA = 100                # the player distribution floor (hitters)
FLOOR_IP = 20.0               # the player distribution floor (pitchers)
TITLE_PA_PER_G = 3.1          # the batting title rule, per club game
TITLE_IP_PER_G = 1.0          # the ERA title rule, per club game
THIN_CELL_N = 20              # a cell under this many players draws hollow

POSITIONS = ("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH")
AGE_BANDS = (("age_24u", "24 and under", None, 24),
             ("age_25_27", "25 to 27", 25, 27),
             ("age_28_30", "28 to 30", 28, 30),
             ("age_31_33", "31 to 33", 31, 33),
             ("age_34o", "34 and over", 34, None))

HIT_COLS = ["mlbam", "name", "club", "lg", "pos", "bats", "age", "g", "pa", "ab",
            "h", "d", "t", "hr", "bb", "ibb", "hbp", "sf", "so", "sb", "cs", "pit",
            "hem", "wrc", "dem", "inn", "war", "bq", "tq"]
PIT_COLS = ["mlbam", "name", "club", "lg", "pos", "throws", "age", "role", "g",
            "gs", "outs", "bf", "er", "r", "h", "bb", "ibb", "hbp", "so", "hr",
            "pit", "strk", "go", "ao", "sv", "hld", "cg", "plus", "plus_board",
            "war", "bq", "tq"]
TEAM_COLS = ["club", "team_id", "lg", "g", "w", "l", "rs", "ra", "pa", "pit_seen",
             "outs", "bf", "pit_thrown", "gs", "sp_outs", "sp_bf", "sp_pit",
             "sp_gs", "rp_outs", "rp_bf", "rp_pit"]

# --------------------------------------------------------------------------- #
# STAT_DEFS: the one definition table the League table, Over time and the
# drawer share. `nd` is the payload precision; `dist` says whether a player
# distribution is computed; `first` is the first season with a source.
# --------------------------------------------------------------------------- #
_D = "the shipped derivation on summed counts (mlbstats_rates)"
STAT_DEFS = {
    "hit": [
        {"key": "avg", "label": "AVG", "formula": "H / AB", "from": _D, "first": 2000, "nd": 3},
        {"key": "obp", "label": "OBP", "formula": "(H + BB + HBP) / (AB + BB + HBP + SF)", "from": _D, "first": 2000, "nd": 3},
        {"key": "slg", "label": "SLG", "formula": "TB / AB", "from": _D, "first": 2000, "nd": 3},
        {"key": "ops", "label": "OPS", "formula": "pooled OBP + pooled SLG", "from": _D, "first": 2000, "nd": 3},
        {"key": "iso", "label": "ISO", "formula": "(TB - H) / AB", "from": _D, "first": 2000, "nd": 3},
        {"key": "babip", "label": "BABIP", "formula": "(H - HR) / (AB - SO - HR + SF)", "from": _D, "first": 2000, "nd": 3},
        {"key": "k_pct", "label": "K%", "formula": "SO / PA", "from": _D, "first": 2000, "nd": 4},
        {"key": "bb_pct", "label": "BB%", "formula": "BB / PA", "from": _D, "first": 2000, "nd": 4},
        {"key": "hr_pct", "label": "HR%", "formula": "HR / PA", "from": "summed counts", "first": 2000, "nd": 4},
        {"key": "p_per_pa", "label": "P/PA", "formula": "pitches seen / PA, over rows with a pitch count", "from": "pitch_rates.p_pa", "first": 2000, "nd": 3},
        {"key": "sb_pct", "label": "SB%", "formula": "SB / (SB + CS)", "from": "summed counts", "first": 2000, "nd": 3},
        {"key": "hem", "label": "HEM+", "formula": "PA-weighted mean of the per-player HEM+", "from": "the window lab panels and the live board (every scored hitter); 2021 the qualified history rows", "first": 2021, "nd": 2, "index": True},
        {"key": "dem", "label": "DEM+", "formula": "fielding-innings-weighted mean of the per-player DEM+", "from": "the window lab panels and the live board (every fielder); 2016 to 2021 the qualified history rows", "first": 2016, "nd": 2, "index": True},
        {"key": "war_600", "label": "{war} per 600 PA", "formula": "summed batting {war} / summed PA x 600", "from": "war_seasons.json", "first": 2000, "nd": 2},
    ],
    "pit": [
        {"key": "era", "label": "ERA", "formula": "ER x 9 / IP", "from": _D, "first": 2000, "nd": 2},
        {"key": "fip", "label": "FIP (standard, season constant)", "formula": "(13 HR + 3 (BB + HBP) - 2 SO) / IP + the season constant from league_constants.league_totals; not the boards' Skill FIP, which is shrunk toward one season's pool and never pooled", "from": "summed counts", "first": 2000, "nd": 2},
        {"key": "whip", "label": "WHIP", "formula": "(H + BB) / IP", "from": "summed counts", "first": 2000, "nd": 3},
        {"key": "k_pct", "label": "K%", "formula": "SO / BF", "from": _D, "first": 2000, "nd": 4},
        {"key": "bb_pct", "label": "BB%", "formula": "BB / BF", "from": _D, "first": 2000, "nd": 4},
        {"key": "k_bb_pct", "label": "K-BB%", "formula": "K% - BB%", "from": _D, "first": 2000, "nd": 4},
        {"key": "hr9", "label": "HR/9", "formula": "HR x 9 / IP", "from": _D, "first": 2000, "nd": 2},
        {"key": "gb_pct", "label": "GB%", "formula": "GO / (GO + AO)", "from": _D, "first": 2000, "nd": 4},
        {"key": "strike_pct", "label": "Strike%", "formula": "strikes / pitches", "from": _D, "first": 2000, "nd": 4},
        {"key": "ip_per_gs", "label": "IP/GS (as the boards)", "formula": "every inning the group pitched / games started, as the boards compute it", "from": _D, "first": 2000, "nd": 2},
        {"key": "sp_ip_per_gs", "label": "Starter IP per start", "formula": "innings pitched in starts / games started (starts only), from the club sp splits; league-wide, so it sits on the all and sp_innings cells only", "from": "pitch_rates starter block over mlb_team_season sp lines", "first": 2000, "nd": 2},
        {"key": "p_per_ip", "label": "P/IP", "formula": "pitches / (outs / 3), over rows with a pitch count", "from": "pitch_rates.p_ip", "first": 2000, "nd": 2},
        {"key": "p_per_bf", "label": "P/BF", "formula": "pitches / BF, over rows with a pitch count", "from": "pitch_rates.p_bf", "first": 2000, "nd": 3},
        {"key": "sem", "label": "SEM+", "formula": "IP-weighted mean of the per-player SEM+", "from": "the window lab panels and the live starter board; 2021 the qualified history rows", "first": 2021, "nd": 2, "index": True},
        {"key": "rem", "label": "REM+", "formula": "IP-weighted mean of the per-player REM+", "from": "the window lab panels and the live bullpen board; 2021 the qualified history rows", "first": 2021, "nd": 2, "index": True},
        {"key": "war_200", "label": "{war} per 200 IP", "formula": "summed pitching {war} / summed IP x 200", "from": "war_seasons.json", "first": 2000, "nd": 2},
    ],
    "team": [
        {"key": "rs_g", "label": "RS/G", "formula": "runs scored / games", "from": "mlb_team_season hitting lines", "first": 2000, "nd": 2},
        {"key": "ra_g", "label": "RA/G", "formula": "runs allowed / games", "from": "mlb_team_season pitching lines", "first": 2000, "nd": 2},
        {"key": "w_pct", "label": "W%", "formula": "W / (W + L)", "from": "mlb_team_season pitching lines", "first": 2000, "nd": 3},
        {"key": "p_per_pa", "label": "Lineup P/PA", "formula": "pitches seen / PA", "from": "pitch_rates.p_pa on the club hitting line", "first": 2000, "nd": 3},
        {"key": "p_per_ip", "label": "Staff P/IP", "formula": "pitches / (outs / 3)", "from": "pitch_rates.p_ip on the club pitching line", "first": 2000, "nd": 2},
        {"key": "sp_p_per_ip", "label": "Rotation P/IP", "formula": "pitches in starts / (outs in starts / 3)", "from": "pitch_rates.p_ip on the club sp split", "first": 2000, "nd": 2},
        {"key": "rp_p_per_ip", "label": "Bullpen P/IP", "formula": "pitches in relief / (outs in relief / 3)", "from": "pitch_rates.p_ip on the club rp split", "first": 2000, "nd": 2},
        {"key": "sp_ip_per_gs", "label": "Rotation IP per start", "formula": "innings in starts / games started", "from": "the club sp split", "first": 2000, "nd": 2},
        {"key": "relief_ip_share", "label": "Relief IP share", "formula": "outs in relief / all outs", "from": "the club sp and rp splits", "first": 2000, "nd": 4},
    ],
}
INDEX_KEYS = {"hit": ("hem", "dem"), "pit": ("sem", "rem")}

# The three filters left out, each with its one reason (plan P8.2, honesty).
LEFT_OUT = [
    {"key": "club", "label": "Club",
     "reason": ("A player's season row sits under his last club, so a club-filtered pooled line "
                "would credit a traded player's whole season to the club he ended with. The "
                "Teams scope is the club view.")},
    {"key": "prospect_cells", "label": "Scouting grade cells",
     "reason": ("No group is keyed by a scouting grade (FV, eFV or a consensus grade): a "
                "realized statistic by grade cell is never computed here "
                "(docs/PROSPECT_ANCHOR_GATE.md).")},
    {"key": "matchup_split", "label": "Against left- or right-handed opponents",
     "reason": ("Matchup splits are out of scope: the club split by opposing hand is the input "
                "to the pre-registered 5e test (docs/diamond-betting.md), and the per-hand HEM+ "
                "estimator changed under M17-3. The hand filter here is the player's own side.")},
]
DEFERRED = [
    {"key": "woba", "label": "wOBA",
     "reason": ("Pooled wOBA waits for X02-08 and M06-18: the boards compute wOBA on the frozen "
                "2013 weights while league_constants solves each season, so a League wOBA would "
                "disagree with the column beside it.")},
]


class Refused(RuntimeError):
    """A season failed a refusal rule; the last good file is kept."""


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def _num(v):
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _int(v):
    f = _num(v)
    return None if f is None else int(round(f))


def _rnd(v, nd):
    return None if v is None else round(float(v), nd)


def _ratio(num, den):
    n, d = _num(num), _num(den)
    if n is None or d is None or d <= 0:
        return None
    return n / d


def _war_label(provider) -> str:
    p = str(provider or "").lower()
    for pre, lab in (("ewar", "eWAR"), ("fwar", "fWAR"), ("bwar", "bWAR")):
        if p.startswith(pre):
            return lab
    return "WAR"


def out_dir() -> Path:
    """Where export writes: data/ only once the flag is flipped."""
    return DATA_DIR if MLBSTATS_LEAGUE_TEAMS_LIVE else PREVIEW_DIR


def season_complete(season: int, today: Optional[date] = None) -> bool:
    """The house rule (mlb_team_season.season_complete): complete from November 1."""
    import mlb_team_season
    return mlb_team_season.season_complete(int(season), today)


def _read_json(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def season_splits(season: int, group: str, cache_dir: Optional[Path] = None) -> list:
    """The StatsAPI season splits for one group, from disk (the file
    fa_sources.fetch_statsapi_season_stats keeps). [] when absent."""
    blob = _read_json(Path(cache_dir or CACHE_DIR) / f"fa_statsapi_{group}_{int(season)}.json")
    if isinstance(blob, dict):
        return ((blob.get("stats") or [{}])[0].get("splits")) or []
    return blob or []


def cached_seasons(cache_dir: Optional[Path] = None, last: Optional[int] = None) -> list:
    """Seasons with both season-line caches on disk, FIRST_SEASON to `last`
    (default this calendar year)."""
    d = Path(cache_dir or CACHE_DIR)
    out = []
    for y in range(FIRST_SEASON, int(last or date.today().year) + 1):
        if ((d / f"fa_statsapi_hitting_{y}.json").exists()
                and (d / f"fa_statsapi_pitching_{y}.json").exists()):
            out.append(y)
    return out


def check_identities(hit_splits: list, pit_splits: list, complete: bool) -> list:
    """League PA against batters faced; pitches seen against pitches thrown.
    Exact on a complete season, within LIVE_TOLERANCE on the live one."""
    def tot(rows, key):
        return sum(int(_num((r.get("stat") or {}).get(key)) or 0) for r in rows)

    def close(a, b):
        if complete:
            return a == b
        return abs(a - b) <= LIVE_TOLERANCE * max(abs(a), abs(b), 1)

    out = []
    pa, bf = tot(hit_splits, "plateAppearances"), tot(pit_splits, "battersFaced")
    if not close(pa, bf):
        out.append(f"league PA {pa} != batters faced {bf}")
    seen, thrown = tot(hit_splits, "numberOfPitches"), tot(pit_splits, "numberOfPitches")
    if not close(seen, thrown):
        out.append(f"pitches seen {seen} != pitches thrown {thrown}")
    return out


# --------------------------------------------------------------------------- #
# side inputs (each fail-soft to "absent", recorded in coverage)
# --------------------------------------------------------------------------- #
def _hands(season: int) -> dict:
    import mlb_people
    try:
        return mlb_people.hands(int(season))
    except mlb_people.NotCached:
        return {}


def _team_lines(season: int) -> Optional[dict]:
    import mlb_team_season
    try:
        return mlb_team_season.team_lines(int(season))
    except mlb_team_season.NotCached:
        return None


def _club_code(team: dict) -> Optional[str]:
    from trades import canonical_org_from_id
    return canonical_org_from_id((team or {}).get("id"), (team or {}).get("name"))


def _war(season: int, data_dir: Optional[Path] = None) -> tuple:
    """({mlbam: (war_bat, war_pit)}, war_provider) for one season."""
    blob = _read_json(Path(data_dir or DATA_DIR) / "war_seasons.json") or {}
    fields = blob.get("fields") or []
    if "season" not in fields:
        return {}, blob.get("war_provider")
    i = {f: n for n, f in enumerate(fields)}
    out = {}
    for mid, pr in (blob.get("players") or {}).items():
        rows = pr[1] if isinstance(pr, list) and len(pr) > 1 else []
        for r in rows:
            if r[i["season"]] == int(season):
                out[int(mid)] = (_num(r[i["war_bat"]]), _num(r[i["war_pit"]]))
    return out, blob.get("war_provider")


def _lab_panel(season: int) -> Optional[dict]:
    """The window lab's memoised panel, read from disk only (never rebuilt
    here: season_panel would rebuild a live or stale panel over the network)."""
    from tools import mlbstats_window_lab as lab
    doc = _read_json(LAB_DIR / f"panel_{int(season)}_v{lab.SCHEMA}.json")
    if not doc or doc.get("schema") != lab.SCHEMA or doc.get("season") != int(season):
        return None
    return doc


def _history_rows(name: str, block: str, season: int, data_dir: Optional[Path]) -> list:
    blob = _read_json(Path(data_dir or DATA_DIR) / f"{name}.json") or {}
    return ((blob.get("history") or {}).get(str(int(season))) or {}).get(block) or []


def _board(name: str, block: str, data_dir: Optional[Path]) -> tuple:
    blob = _read_json(Path(data_dir or DATA_DIR) / f"{name}.json") or {}
    return blob.get(block) or [], blob.get("season"), blob.get("as_of")


def index_values(season: int, live_season: int, data_dir: Optional[Path] = None) -> dict:
    """The per-player index values for one season and where they came from.

    {"hem": {mlbam: v}, "wrc": {...}, "sem": {...}, "rem": {...},
     "dem": {mlbam: (v, inn)}, "basis": {...}, "board_rows": {...}}.
    Order: the window lab's memoised panel (every scored player, 2022 on); the
    live boards for the live season; the qualified history rows (2021, and
    DEM+ 2016 to 2021). Nothing is scored here."""
    out = {"hem": {}, "wrc": {}, "sem": {}, "rem": {}, "dem": {}, "basis": {},
           "board_rows": {}}
    lab = _lab_panel(season)
    if lab is not None:
        for mid, r in (lab.get("hit") or {}).items():
            if _num(r.get("hem")) is not None:
                out["hem"][int(mid)] = _num(r["hem"])
        for mid, r in (lab.get("pit") or {}).items():
            if _num(r.get("sem")) is not None:
                out["sem"][int(mid)] = _num(r["sem"])
            elif _num(r.get("rem")) is not None:
                out["rem"][int(mid)] = _num(r["rem"])
        for mid, r in (lab.get("dfn") or {}).items():
            if _num(r.get("dem")) is not None and _num(r.get("inn")):
                out["dem"][int(mid)] = (_num(r["dem"]), _num(r["inn"]))
        basis = "window lab panel, every scored player"
        out["basis"] = {"hem": basis, "sem": basis, "rem": basis, "dem": basis}
        return out
    if int(season) == int(live_season):
        boards = (("hem", "hitter_leaderboards", "hitters", "hem_plus"),
                  ("sem", "starter_leaderboards", "starters", "sem_plus"),
                  ("rem", "bullpen_leaderboards", "relievers", "rem_plus"),
                  ("dem", "defense_leaderboards", "fielders", "dem_plus"))
        for key, name, block, field in boards:
            rows, b_season, _as_of = _board(name, block, data_dir)
            if b_season is None or int(b_season) != int(season) or not rows:
                continue
            out["board_rows"][key] = [int(r["mlbam"]) for r in rows if r.get("mlbam") is not None]
            for r in rows:
                v = _num(r.get(field))
                if r.get("mlbam") is None or v is None:
                    continue
                if key == "dem":
                    if _num(r.get("inn")):
                        out["dem"][int(r["mlbam"])] = (v, _num(r["inn"]))
                else:
                    out[key][int(r["mlbam"])] = v
                if key == "hem" and _num(r.get("wrc_plus")) is not None:
                    out["wrc"][int(r["mlbam"])] = _num(r["wrc_plus"])
            out["basis"][key] = f"live {name.split('_')[0]} board (its scored pool)"
        return out
    hist = (("hem", "hitter_history", "hitters", "hem_plus", 2021),
            ("sem", "starter_history", "starters", "sem_plus", 2021),
            ("rem", "bullpen_history", "relievers", "rem_plus", 2021),
            ("dem", "defense_history", "fielders", "dem_plus", 2016))
    for key, name, block, field, first in hist:
        if int(season) < first:
            continue
        rows = _history_rows(name, block, season, data_dir)
        for r in rows:
            v = _num(r.get(field))
            if r.get("mlbam") is None or v is None:
                continue
            if key == "dem":
                if _num(r.get("inn")):
                    out["dem"][int(r["mlbam"])] = (v, _num(r["inn"]))
            else:
                out[key][int(r["mlbam"])] = v
        if rows:
            out["basis"][key] = "qualified history rows only"
    return out


def _baserunning_league() -> Optional[dict]:
    """The Baserunning plan's league block (baserunning.md 2.8), verbatim, only
    when that plan's payload exists. No runner-record rate is computed here."""
    for p in (DATA_DIR / "baserunning_leaderboards.json",
              CACHE_DIR / "baserunning" / "preview.json"):
        blob = _read_json(p)
        if isinstance(blob, dict) and isinstance(blob.get("league"), dict):
            return {"source": p.name, "league": blob["league"]}
    return None


# --------------------------------------------------------------------------- #
# roles and qualification (the boards' own predicates)
# --------------------------------------------------------------------------- #
def pitching_role(ip: float, g: float, gs: float) -> str:
    """SP / RP / SW through sem_plus.is_true_starter then rem_plus.is_true_reliever,
    the pair war_board_export._pitching_role calls; the thresholds live there."""
    import rem_plus
    import sem_plus
    line = SimpleNamespace(ip=float(ip or 0.0), g=float(g or 0.0), gs=float(gs or 0.0))
    if sem_plus.is_true_starter(line):
        return "SP"
    if rem_plus.is_true_reliever(line):
        return "RP"
    return "SW"


def board_qualified_hit(r: dict) -> bool:
    """hem_plus's rule: the wOBA denominator at or above QUALIFY_MIN_PA."""
    import hem_plus
    hi = SimpleNamespace(ab=r.get("ab") or 0, bb=r.get("bb") or 0, ibb=r.get("ibb") or 0,
                         sf=r.get("sf") or 0, hbp=r.get("hbp") or 0)
    return hem_plus._woba_denom(hi) >= hem_plus.QUALIFY_MIN_PA


def board_qualified_pit(r: dict) -> bool:
    """sem_plus's rule for a starter, rem_plus's for a reliever; a swingman is
    on neither board."""
    import rem_plus
    import sem_plus
    ip = (r.get("outs") or 0) / 3.0
    if r.get("role") == "SP":
        return (r.get("gs") or 0) >= sem_plus.QUALIFY_MIN_GS or ip >= sem_plus.QUALIFY_MIN_IP
    if r.get("role") == "RP":
        return ((r.get("bf") or 0) >= rem_plus.QUALIFY_MIN_TBF
                or (ip >= rem_plus.QUALIFY_MIN_IP and (r.get("g") or 0) >= rem_plus.QUALIFY_MIN_G))
    return False


def qualify_block() -> dict:
    import hem_plus
    import rem_plus
    import sem_plus
    return {"board": {"hit_woba_pa": hem_plus.QUALIFY_MIN_PA, "sp_gs": sem_plus.QUALIFY_MIN_GS,
                      "sp_ip": sem_plus.QUALIFY_MIN_IP, "rp_bf": rem_plus.QUALIFY_MIN_TBF,
                      "rp_ip": rem_plus.QUALIFY_MIN_IP, "rp_g": rem_plus.QUALIFY_MIN_G},
            "title": {"pa_per_game": TITLE_PA_PER_G, "ip_per_game": TITLE_IP_PER_G,
                      "games": "the player's last club's games played"},
            "floor": {"pa": FLOOR_PA, "ip": FLOOR_IP}}


def _age_band(age) -> Optional[str]:
    a = _num(age)
    if a is None:
        return None
    for key, _label, lo, hi in AGE_BANDS:
        if (lo is None or a >= lo) and (hi is None or a <= hi):
            return key
    return None


# --------------------------------------------------------------------------- #
# groups: one definition list, used by the panel groups and the series cells
# --------------------------------------------------------------------------- #
def _is_pos_player(r):
    return (r.get("pos") or "") != "P"


def _is_pitcher(r):
    return (r.get("pos") or "") == "P"


def _hit_groups() -> list:
    """(key, label, rule, predicate) for hitters. Every group but
    all_incl_p is a filter on the position players (the pitchers-batting
    toggle is off by default)."""
    g = [("all", "All position players", "primary position is not P", _is_pos_player),
         ("all_incl_p", "All, pitchers batting included", "every hitting line", lambda r: True)]
    for p in POSITIONS:
        g.append((f"pos_{p}", p, f"primary position {p}",
                  (lambda p: lambda r: r.get("pos") == p)(p)))
    g.append(("pos_other", "Other", "primary position X, two-way or any other non-pitcher code",
              lambda r: _is_pos_player(r) and r.get("pos") not in POSITIONS))
    for h, lab in (("L", "Bats left"), ("R", "Bats right"), ("S", "Bats both")):
        g.append((f"bats_{h}", lab, f"the player's own bat side {h} (people feed)",
                  (lambda h: lambda r: _is_pos_player(r) and r.get("bats") == h)(h)))
    for key, label, _lo, _hi in AGE_BANDS:
        g.append((key, f"Age {label}", "season age (June 30)",
                  (lambda k: lambda r: _is_pos_player(r) and _age_band(r.get("age")) == k)(key)))
    g.append(("sample_floor", f"{FLOOR_PA}+ PA", f"PA at or above {FLOOR_PA}",
              lambda r: _is_pos_player(r) and (r.get("pa") or 0) >= FLOOR_PA))
    g.append(("sample_board", "Board qualified", "hem_plus.QUALIFY_MIN_PA on the wOBA denominator",
              lambda r: _is_pos_player(r) and bool(r.get("bq"))))
    g.append(("sample_title", "Title qualified", f"{TITLE_PA_PER_G} PA per club game",
              lambda r: _is_pos_player(r) and bool(r.get("tq"))))
    for lg in ("AL", "NL"):
        g.append((f"lg_{lg}", lg, f"last club in the {lg}",
                  (lambda lg: lambda r: _is_pos_player(r) and r.get("lg") == lg)(lg)))
    return g


def _pit_groups() -> list:
    """(key, label, rule, predicate) for pitchers. `all` is every pitching
    line (the league total); every other player group is a filter on the
    pitchers (primary position P, the boards' pool), so the
    position-players-pitching toggle is off by default."""
    g = [("all", "All pitching lines", "every pitching line, two-way players and position players pitching included", lambda r: True),
         ("pitchers_only", "Pitchers", "primary position P (the boards' pool)", _is_pitcher)]
    for role, lab in (("SP", "Starters"), ("RP", "Relievers"), ("SW", "Swingmen")):
        g.append((f"role_{role}", lab, f"classified {role} by sem_plus.is_true_starter and rem_plus.is_true_reliever",
                  (lambda role: lambda r: _is_pitcher(r) and r.get("role") == role)(role)))
    for h, lab in (("L", "Throws left"), ("R", "Throws right")):
        g.append((f"throws_{h}", lab, f"the player's own throwing hand {h} (people feed)",
                  (lambda h: lambda r: _is_pitcher(r) and r.get("throws") == h)(h)))
    for key, label, _lo, _hi in AGE_BANDS:
        g.append((key, f"Age {label}", "season age (June 30)",
                  (lambda k: lambda r: _is_pitcher(r) and _age_band(r.get("age")) == k)(key)))
    g.append(("sample_floor", f"{int(FLOOR_IP)}+ IP", f"IP at or above {int(FLOOR_IP)}",
              lambda r: _is_pitcher(r) and (r.get("outs") or 0) >= FLOOR_IP * 3))
    g.append(("sample_board", "Board qualified", "sem_plus or rem_plus qualification for the classified role",
              lambda r: _is_pitcher(r) and bool(r.get("bq"))))
    g.append(("sample_title", "Title qualified", f"{TITLE_IP_PER_G} IP per club game",
              lambda r: _is_pitcher(r) and bool(r.get("tq"))))
    for lg in ("AL", "NL"):
        g.append((f"lg_{lg}", lg, f"last club in the {lg}",
                  (lambda lg: lambda r: _is_pitcher(r) and r.get("lg") == lg)(lg)))
    return g


ROLE_INNINGS_CELLS = (("sp_innings", "Innings thrown as a starter", "the club sp splits, summed"),
                      ("rp_innings", "Innings thrown in relief", "the club rp splits, summed"))

# The over-time cells (lane 4.3): a subset of the panel groups, plus the role
# innings cells and the club cells.
SERIES_CELLS = {
    "hit": ["all", "all_incl_p", "sample_title"] + [f"pos_{p}" for p in POSITIONS]
           + ["pos_other", "bats_L", "bats_R", "bats_S"] + [k for k, *_ in AGE_BANDS]
           + ["lg_AL", "lg_NL"],
    "pit": ["all", "pitchers_only", "role_SP", "role_RP", "role_SW", "sp_innings",
            "rp_innings", "throws_L", "throws_R"] + [k for k, *_ in AGE_BANDS]
           + ["sample_title", "lg_AL", "lg_NL"],
    "team": ["club_mean", "club_sd"],
}


# --------------------------------------------------------------------------- #
# pooling
# --------------------------------------------------------------------------- #
_HIT_ACC = (("pa", "pa"), ("ab", "ab"), ("h", "h"), ("2b", "d"), ("3b", "t"), ("hr", "hr"),
            ("bb", "bb"), ("ibb", "ibb"), ("hbp", "hbp"), ("sf", "sf"), ("so", "so"),
            ("sb", "sb"), ("cs", "cs"))
_PIT_ACC = (("g", "g"), ("gs", "gs"), ("outs", "outs"), ("tbf", "bf"), ("er", "er"),
            ("r", "r"), ("bb", "bb"), ("so", "so"), ("hr", "hr"), ("hbp", "hbp"),
            ("pit", "pit"), ("strk", "strk"), ("cg", "cg"), ("go", "go"), ("ao", "ao"),
            ("sv", "sv"), ("hld", "hld"))


def _acc(rows: list, pairs) -> dict:
    """Summed counts in the lab's accumulator keys. ABSENT IS NOT ZERO (the
    window lab's _sum_counts rule): a count no row carries stays absent."""
    out: dict = {}
    for r in rows:
        for k, col in pairs:
            v = _num(r.get(col))
            if v is None:
                continue
            out[k] = (out.get(k) or 0.0) + v
    return out


def _pitched(rows, num_col, den_col):
    """(pitches, denominator) over rows that carry a pitch count."""
    n = d = 0.0
    for r in rows:
        p = _num(r.get(num_col))
        if p is None:
            continue
        n += p
        d += _num(r.get(den_col)) or 0.0
    return n, d


def hit_stats(rows: list) -> dict:
    """The pooled hitting statistics of a set of panel rows (unrounded where
    this module computes them; the shipped derivation's own rounding where it
    rounds)."""
    acc = _acc(rows, _HIT_ACC)
    out = {}
    if acc.get("pa"):
        rates = mlbstats_rates.hitter_rates(acc)
        for k in ("avg", "obp", "slg", "ops", "iso", "babip", "k_pct", "bb_pct"):
            out[k] = rates.get(k)
        out["hr_pct"] = _ratio(acc.get("hr"), acc.get("pa"))
    seen, pa = _pitched(rows, "pit", "pa")
    out["p_per_pa"] = pitch_rates.p_pa(seen, pa)
    sb, cs = acc.get("sb") or 0.0, acc.get("cs") or 0.0
    out["sb_pct"] = _ratio(sb, sb + cs)
    out["hem"] = _weighted(rows, "hem", "pa")
    out["dem"] = _weighted(rows, "dem", "inn")
    wr = [r for r in rows if _num(r.get("war")) is not None and (r.get("pa") or 0) > 0]
    tot_pa = sum(r["pa"] for r in wr)
    out["war_600"] = (sum(_num(r["war"]) for r in wr) / tot_pa * 600.0) if tot_pa else None
    return out


def pit_stats(rows: list, fip_constant: Optional[float]) -> dict:
    acc = _acc(rows, _PIT_ACC)
    out = {}
    outs = acc.get("outs") or 0.0
    if outs > 0:
        rates = mlbstats_rates.pitcher_rates(acc, starter=True)
        for k in ("era", "hr9", "k_pct", "bb_pct", "k_bb_pct", "gb_pct", "ip_per_gs", "strike_pct"):
            out[k] = rates.get(k)
        ip = outs / 3.0
        fip_core = (13.0 * (acc.get("hr") or 0.0) + 3.0 * ((acc.get("bb") or 0.0) + (acc.get("hbp") or 0.0))
                    - 2.0 * (acc.get("so") or 0.0)) / ip
        out["fip"] = None if fip_constant is None else fip_core + fip_constant
        h = sum(_num(r.get("h")) or 0.0 for r in rows)
        out["whip"] = (h + (acc.get("bb") or 0.0)) / ip
    thrown, o = _pitched(rows, "pit", "outs")
    out["p_per_ip"] = pitch_rates.p_ip(thrown, o)
    thrown, bf = _pitched(rows, "pit", "bf")
    out["p_per_bf"] = pitch_rates.p_bf(thrown, bf)
    sem_rows = [dict(r, ip=(r.get("outs") or 0) / 3.0) for r in rows if r.get("plus_board") == "sem"]
    rem_rows = [dict(r, ip=(r.get("outs") or 0) / 3.0) for r in rows if r.get("plus_board") == "rem"]
    out["sem"] = _weighted(sem_rows, "plus", "ip")
    out["rem"] = _weighted(rem_rows, "plus", "ip")
    wr = [r for r in rows if _num(r.get("war")) is not None and (r.get("outs") or 0) > 0]
    tot_ip = sum(r["outs"] for r in wr) / 3.0
    out["war_200"] = (sum(_num(r["war"]) for r in wr) / tot_ip * 200.0) if tot_ip else None
    return out


def _weighted(rows, val_col, w_col):
    num = den = 0.0
    for r in rows:
        v, w = _num(r.get(val_col)), _num(r.get(w_col))
        if v is None or not w or w <= 0:
            continue
        num += v * w
        den += w
    return num / den if den else None


def role_innings_stats(team_rows: list, code: str) -> dict:
    """P/IP, P/BF and (sp) starter IP per start over the club role splits,
    through pitch_rates' starter and reliever blocks, which own the definitions."""
    lines = [{"team_id": t.get("team_id"), "np": t.get(f"{code}_pit"),
              "outs": t.get(f"{code}_outs"), "bf": t.get(f"{code}_bf"),
              "g": None, "gs": t.get("sp_gs") if code == "sp" else 0}
             for t in team_rows]
    for ln in lines:
        ln["g"] = ln["gs"] or 0
    blk = pitch_rates._sp_block(lines) if code == "sp" else pitch_rates._rp_block(lines)
    out = {"p_per_ip": blk.get("p_ip"), "p_per_bf": blk.get("p_bf")}
    if code == "sp":
        out["sp_ip_per_gs"] = blk.get("sp_ip_per_gs")
    out["_ip"] = (blk.get("outs") or 0) / 3.0
    out["_n"] = blk.get("n")
    return out


def _club_stat_values(t: dict) -> dict:
    return {
        "rs_g": _ratio(t.get("rs"), t.get("g")),
        "ra_g": _ratio(t.get("ra"), t.get("g")),
        "w_pct": _ratio(t.get("w"), (t.get("w") or 0) + (t.get("l") or 0)),
        "p_per_pa": pitch_rates.p_pa(t.get("pit_seen"), t.get("pa")),
        "p_per_ip": pitch_rates.p_ip(t.get("pit_thrown"), t.get("outs")),
        "sp_p_per_ip": pitch_rates.p_ip(t.get("sp_pit"), t.get("sp_outs")),
        "rp_p_per_ip": pitch_rates.p_ip(t.get("rp_pit"), t.get("rp_outs")),
        "sp_ip_per_gs": _ratio((t.get("sp_outs") or 0) / 3.0, t.get("sp_gs")),
        "relief_ip_share": _ratio(t.get("rp_outs"), t.get("outs")),
    }


def team_stats(team_rows: list) -> dict:
    """League (pooled over the clubs: summed numerators over summed
    denominators) and the club distribution of each club statistic."""
    def tot(col):
        return sum(_num(t.get(col)) or 0.0 for t in team_rows)
    league = _club_stat_values({c: tot(c) for c in TEAM_COLS if c not in ("club", "lg", "team_id")})
    per = {t["club"]: _club_stat_values(t) for t in team_rows}
    out = {}
    for sd in STAT_DEFS["team"]:
        k, nd = sd["key"], sd["nd"]
        vals = [(c, v[k]) for c, v in per.items() if v.get(k) is not None]
        cell = {"league": _rnd(league.get(k), nd)}
        if vals:
            xs = [v for _c, v in vals]
            lo = min(vals, key=lambda cv: (cv[1], cv[0]))
            hi = max(vals, key=lambda cv: (cv[1], cv[0]))
            cell.update({"mean": _rnd(statistics.fmean(xs), nd),
                         "median": _rnd(statistics.median(xs), nd),
                         "sd": _rnd(statistics.stdev(xs), nd) if len(xs) > 1 else None,
                         "n": len(xs), "low": [lo[0], _rnd(lo[1], nd)],
                         "high": [hi[0], _rnd(hi[1], nd)]})
        out[k] = cell
    return out


# --------------------------------------------------------------------------- #
# per-player values (for the distribution columns)
# --------------------------------------------------------------------------- #
def _player_hit(r: dict) -> dict:
    v = hit_stats([r])
    v["hem"] = _num(r.get("hem"))
    v["dem"] = _num(r.get("dem")) if _num(r.get("inn")) else None
    return v


def _player_pit(r: dict, fip_c) -> dict:
    v = pit_stats([r], fip_c)
    v["sem"] = _num(r.get("plus")) if r.get("plus_board") == "sem" else None
    v["rem"] = _num(r.get("plus")) if r.get("plus_board") == "rem" else None
    return v


def _dist(values: list, nd: int) -> Optional[dict]:
    xs = [x for x in values if x is not None]
    if not xs:
        return None
    return {"mean": _rnd(statistics.fmean(xs), nd), "median": _rnd(statistics.median(xs), nd),
            "sd": _rnd(statistics.stdev(xs), nd) if len(xs) > 1 else None, "n": len(xs)}


def _group_block(side: str, rows: list, per: dict, fip_c) -> dict:
    """One group: its size, its denominator, the pooled League values and the
    player distribution over the floor."""
    if side == "hit":
        pooled = hit_stats(rows)
        floor = [r for r in rows if (r.get("pa") or 0) >= FLOOR_PA]
        den = {"pa": int(sum(r.get("pa") or 0 for r in rows))}
    else:
        pooled = pit_stats(rows, fip_c)
        floor = [r for r in rows if (r.get("outs") or 0) >= FLOOR_IP * 3]
        den = {"ip": round(sum(r.get("outs") or 0 for r in rows) / 3.0, 1)}
    league, dist = {}, {}
    for sd in STAT_DEFS[side]:
        k, nd = sd["key"], sd["nd"]
        if k == "sp_ip_per_gs":
            continue
        league[k] = _rnd(pooled.get(k), nd)
        d = _dist([per[r["mlbam"]].get(k) for r in floor], nd)
        if d is not None:
            dist[k] = d
    return {"n": len(rows), **den, "n_floor": len(floor), "league": league, "dist": dist}


# --------------------------------------------------------------------------- #
# the panel
# --------------------------------------------------------------------------- #
def _hit_row(s: dict, hands: dict, idx: dict, war: dict, club_g: dict) -> dict:
    st = s.get("stat") or {}
    pl = s.get("player") or {}
    mid = int(pl["id"])
    club = _club_code(s.get("team") or {})
    dem = idx["dem"].get(mid)
    r = {"mlbam": mid, "name": pl.get("fullName"), "club": club,
         "lg": (s.get("league") or {}).get("name"),
         "pos": (s.get("position") or {}).get("abbreviation"),
         "bats": (hands.get(mid) or {}).get("bats"), "age": _int(st.get("age")),
         "g": _int(st.get("gamesPlayed")), "pa": _int(st.get("plateAppearances")) or 0,
         "ab": _int(st.get("atBats")), "h": _int(st.get("hits")), "d": _int(st.get("doubles")),
         "t": _int(st.get("triples")), "hr": _int(st.get("homeRuns")),
         "bb": _int(st.get("baseOnBalls")), "ibb": _int(st.get("intentionalWalks")),
         "hbp": _int(st.get("hitByPitch")), "sf": _int(st.get("sacFlies")),
         "so": _int(st.get("strikeOuts")), "sb": _int(st.get("stolenBases")),
         "cs": _int(st.get("caughtStealing")), "pit": _int(st.get("numberOfPitches")),
         "hem": idx["hem"].get(mid), "wrc": idx["wrc"].get(mid),
         "dem": None if dem is None else dem[0], "inn": None if dem is None else dem[1],
         "war": (war.get(mid) or (None, None))[0]}
    r["bq"] = board_qualified_hit(r)
    g = club_g.get(club)
    r["tq"] = bool(g) and r["pa"] >= TITLE_PA_PER_G * g
    return r


def _pit_row(s: dict, hands: dict, idx: dict, war: dict, club_g: dict) -> dict:
    st = s.get("stat") or {}
    pl = s.get("player") or {}
    mid = int(pl["id"])
    club = _club_code(s.get("team") or {})
    outs = _int(st.get("outs"))
    if outs is None:
        outs = pitch_rates.outs_from_ip(st.get("inningsPitched")) or 0
    plus, board = None, None
    if mid in idx["sem"]:
        plus, board = idx["sem"][mid], "sem"
    elif mid in idx["rem"]:
        plus, board = idx["rem"][mid], "rem"
    r = {"mlbam": mid, "name": pl.get("fullName"), "club": club,
         "lg": (s.get("league") or {}).get("name"),
         "pos": (s.get("position") or {}).get("abbreviation"),
         "throws": (hands.get(mid) or {}).get("throws"), "age": _int(st.get("age")),
         "g": _int(st.get("gamesPitched")), "gs": _int(st.get("gamesStarted")) or 0,
         "outs": outs, "bf": _int(st.get("battersFaced")), "er": _int(st.get("earnedRuns")),
         "r": _int(st.get("runs")), "h": _int(st.get("hits")),
         "bb": _int(st.get("baseOnBalls")), "ibb": _int(st.get("intentionalWalks")),
         "hbp": _int(st.get("hitByPitch")), "so": _int(st.get("strikeOuts")),
         "hr": _int(st.get("homeRuns")), "pit": _int(st.get("numberOfPitches")),
         "strk": _int(st.get("strikes")), "go": _int(st.get("groundOuts")),
         "ao": _int(st.get("airOuts")), "sv": _int(st.get("saves")),
         "hld": _int(st.get("holds")), "cg": _int(st.get("completeGames")),
         "plus": plus, "plus_board": board,
         "war": (war.get(mid) or (None, None))[1]}
    r["role"] = pitching_role(outs / 3.0, r["g"], r["gs"])
    r["bq"] = board_qualified_pit(r)
    g = club_g.get(club)
    r["tq"] = bool(g) and outs >= 3 * TITLE_IP_PER_G * g
    return r


def _team_rows(lines: Optional[dict], lg_of: dict) -> list:
    if not lines:
        return []
    out = []
    for club, h in sorted((lines.get("hit") or {}).items()):
        p = (lines.get("pit") or {}).get(club) or {}
        sp = (lines.get("sp") or {}).get(club) or {}
        rp = (lines.get("rp") or {}).get(club) or {}
        out.append({"club": club, "team_id": h.get("team_id"), "lg": lg_of.get(club),
                    "g": p.get("g") or h.get("g"), "w": p.get("w"), "l": p.get("l"),
                    "rs": h.get("r"), "ra": p.get("r"), "pa": h.get("pa"),
                    "pit_seen": h.get("pitches"), "outs": p.get("outs"), "bf": p.get("bf"),
                    "pit_thrown": p.get("pitches"), "gs": p.get("gs"),
                    "sp_outs": sp.get("outs"), "sp_bf": sp.get("bf"), "sp_pit": sp.get("pitches"),
                    "sp_gs": sp.get("gs"), "rp_outs": rp.get("outs"), "rp_bf": rp.get("bf"),
                    "rp_pit": rp.get("pitches")})
    return out


def _fip_recompute(pit_rows: list) -> Optional[float]:
    """league_totals' identity on this panel's own sums: ERA minus the FIP core."""
    acc = _acc(pit_rows, _PIT_ACC)
    outs = acc.get("outs") or 0.0
    if outs <= 0:
        return None
    ip = outs / 3.0
    era = 9.0 * (acc.get("er") or 0.0) / ip
    core = (13.0 * (acc.get("hr") or 0.0) + 3.0 * ((acc.get("bb") or 0.0) + (acc.get("hbp") or 0.0))
            - 2.0 * (acc.get("so") or 0.0)) / ip
    return era - core


def live_season_of(today: Optional[date] = None, cache_dir: Optional[Path] = None) -> int:
    today = today or date.today()
    ys = cached_seasons(cache_dir, today.year)
    return max(ys) if ys else today.year


def build_panel(season: int, *, live_season: Optional[int] = None,
                today: Optional[date] = None, cache_dir: Optional[Path] = None,
                data_dir: Optional[Path] = None) -> dict:
    """The panel for one season (lane 7.1). Raises Refused under the module's
    refusal rules; never writes."""
    import league_constants
    season = int(season)
    today = today or date.today()
    live_season = int(live_season if live_season is not None else live_season_of(today, cache_dir))
    complete = season_complete(season, today)
    hit_s = season_splits(season, "hitting", cache_dir)
    pit_s = season_splits(season, "pitching", cache_dir)
    if not hit_s or not pit_s:
        raise Refused(f"{season}: the {'hitting' if not hit_s else 'pitching'} splits came back empty")
    bad = check_identities(hit_s, pit_s, complete)
    if bad:
        raise Refused(f"{season}: identity broken ({'; '.join(bad)})")
    totals = league_constants.league_totals(season)
    if not totals or totals.get("fip_constant") is None:
        raise Refused(f"{season}: league_constants.league_totals has no FIP constant")
    fip_c = float(totals["fip_constant"])

    hands = _hands(season)
    idx = index_values(season, live_season, data_dir)
    war, provider = _war(season, data_dir)
    lines = _team_lines(season)
    club_g = {}
    if lines:
        for club, p in (lines.get("pit") or {}).items():
            if p.get("g"):
                club_g[club] = p["g"]
    hit = [_hit_row(s, hands, idx, war, club_g) for s in hit_s
           if (s.get("player") or {}).get("id") is not None]
    pit = [_pit_row(s, hands, idx, war, club_g) for s in pit_s
           if (s.get("player") or {}).get("id") is not None]
    hit.sort(key=lambda r: r["mlbam"])
    pit.sort(key=lambda r: r["mlbam"])

    fip_here = _fip_recompute(pit)
    if fip_here is None or abs(fip_here - fip_c) > FIP_TOLERANCE:
        raise Refused(f"{season}: FIP constant {fip_here} on the panel's sums misses "
                      f"league_totals {fip_c} by more than {FIP_TOLERANCE}")

    join = {}
    for key, ids in (idx.get("board_rows") or {}).items():
        pool = {r["mlbam"] for r in (pit if key in ("sem", "rem") else hit)}
        n = len(ids)
        j = sum(1 for i in ids if i in pool)
        join[key] = {"board_rows": n, "joined": j, "share": round(j / n, 4) if n else None}
        if n and j / n < MIN_BOARD_JOIN:
            raise Refused(f"{season}: {j} of {n} live {key} board rows join the panel "
                          f"({j / n:.1%}), under {MIN_BOARD_JOIN:.0%}")

    lg_of: dict = {}
    for r in hit + pit:
        if r.get("club") and r.get("lg"):
            lg_of.setdefault(r["club"], Counter())[r["lg"]] += 1
    lg_of = {c: cnt.most_common(1)[0][0] for c, cnt in lg_of.items()}
    teams = _team_rows(lines, lg_of)
    games = sorted(t["g"] for t in teams if t.get("g"))
    games_per_team = int(round(statistics.median(games))) if games else None

    per_hit = {r["mlbam"]: _player_hit(r) for r in hit}
    per_pit = {r["mlbam"]: _player_pit(r, fip_c) for r in pit}
    groups = {"hit": {}, "pit": {}, "team": {}}
    group_defs = {"hit": [], "pit": []}
    for side, defs, rows, per in (("hit", _hit_groups(), hit, per_hit),
                                  ("pit", _pit_groups(), pit, per_pit)):
        for key, label, rule, pred in defs:
            sel = [r for r in rows if pred(r)]
            groups[side][key] = _group_block(side, sel, per, fip_c)
            group_defs[side].append({"key": key, "label": label, "rule": rule})
    if teams:
        for code, (key, label, rule) in zip(("sp", "rp"), ROLE_INNINGS_CELLS):
            st = role_innings_stats(teams, code)
            league = {k: _rnd(v, 2 if k != "p_per_bf" else 3) for k, v in st.items()
                      if not k.startswith("_")}
            groups["pit"][key] = {"n": st["_n"], "ip": round(st["_ip"], 1), "league": league,
                                  "unit": "club role lines"}
            group_defs["pit"].append({"key": key, "label": label, "rule": rule})
        groups["pit"]["all"]["league"]["sp_ip_per_gs"] = groups["pit"]["sp_innings"]["league"].get("sp_ip_per_gs")
        groups["team"]["clubs"] = {"n": len(teams), "stats": team_stats(teams)}

    stat_defs = _stat_defs(provider)
    as_of = _as_of(season, cache_dir)
    doc = {
        "schema": SCHEMA, "season": season, "as_of": as_of, "complete": complete,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "games_per_team": games_per_team,
        "row_rule": ("one row per player-season; a traded player's row is his season total "
                     "under his last club"),
        "sources": {
            "hitting": "statsapi season playerPool=All (.cache/fa_statsapi_hitting)",
            "pitching": "statsapi season playerPool=All (.cache/fa_statsapi_pitching)",
            "people": "sports/1/players (mlb_people)",
            "clubs": "teams/stats season and statSplits sp, rp (mlb_team_season)",
            "index": idx["basis"],
            "war": {"file": "war_seasons.json", "war_provider": provider,
                    "label": _war_label(provider)},
            "baserunning": None,
        },
        "constants": {"fip_constant": round(fip_c, 4),
                      "fip_constant_basis": "league_constants.league_totals on these sums",
                      "fip_constant_panel": round(fip_here, 4)},
        "qualify": qualify_block(),
        "coverage": {
            "n_hit": len(hit), "n_pit": len(pit), "n_teams": len(teams),
            "n_hand": {"hit": sum(1 for r in hit if r.get("bats")),
                       "pit": sum(1 for r in pit if r.get("throws"))},
            "n_age": {"hit": sum(1 for r in hit if r.get("age") is not None),
                      "pit": sum(1 for r in pit if r.get("age") is not None)},
            "n_index": {"hem": sum(1 for r in hit if r.get("hem") is not None),
                        "dem": sum(1 for r in hit if r.get("dem") is not None),
                        "sem": sum(1 for r in pit if r.get("plus_board") == "sem"),
                        "rem": sum(1 for r in pit if r.get("plus_board") == "rem")},
            "n_war": {"hit": sum(1 for r in hit if r.get("war") is not None),
                      "pit": sum(1 for r in pit if r.get("war") is not None)},
            "board_join": join,
        },
        "stats": stat_defs,
        "group_defs": group_defs,
        "filters": filters_block(),
        "notes": {"left_out": LEFT_OUT, "deferred": DEFERRED,
                  "method": method_sentence()},
        "groups": groups,
        "hit": {"cols": HIT_COLS, "rows": [[r.get(c) for c in HIT_COLS] for r in hit]},
        "pit": {"cols": PIT_COLS, "rows": [[r.get(c) for c in PIT_COLS] for r in pit]},
        "team": {"cols": TEAM_COLS, "rows": [[t.get(c) for c in TEAM_COLS] for t in teams]},
    }
    br = _baserunning_league() if season == live_season else None
    if br is not None:
        doc["baserunning"] = br
        doc["sources"]["baserunning"] = br["source"]
    else:
        doc["notes"]["baserunning"] = ("Not joined: the Baserunning plan's payload does not "
                                       "exist yet. Runner-record rates are never computed here.")
    return doc


def _as_of(season: int, cache_dir: Optional[Path]) -> Optional[str]:
    """The date the season lines were read (the cache file's time)."""
    p = Path(cache_dir or CACHE_DIR) / f"fa_statsapi_hitting_{int(season)}.json"
    try:
        return date.fromtimestamp(p.stat().st_mtime).isoformat()
    except OSError:
        return None


def _stat_defs(provider) -> dict:
    lab = _war_label(provider)
    out = {}
    for side, defs in STAT_DEFS.items():
        out[side] = []
        for d in defs:
            e = {k: v for k, v in d.items()}
            for f in ("label", "formula"):
                e[f] = str(e[f]).replace("{war}", lab)
            out[side].append(e)
    return out


def filters_block() -> dict:
    """The filters of the lane's 3.3. Club, grade cells and matchup splits are
    left out (LEFT_OUT)."""
    ages = [{"key": k, "label": lab} for k, lab, *_ in AGE_BANDS]
    sample = [{"key": "every", "label": "Every player"},
              {"key": "floor", "label": f"{FLOOR_PA}+ PA or {int(FLOOR_IP)}+ IP"},
              {"key": "board", "label": "Board qualified"},
              {"key": "title", "label": "Title qualified"},
              {"key": "custom", "label": "Custom minimum"}]
    return {
        "season": {"first": FIRST_SEASON, "default": "live"},
        "side": {"values": ["hit", "pit", "team"], "default": "hit"},
        "hit": {"pos": {"values": list(POSITIONS) + ["other"], "default": "all"},
                "bats": {"values": ["L", "R", "S"], "default": "all"},
                "age": {"values": ages, "default": "all"},
                "sample": {"values": sample, "default": "every"},
                "lg": {"values": ["AL", "NL"], "default": "both"},
                "pitchers_batting": {"values": [False, True], "default": False}},
        "pit": {"role": {"values": ["SP", "RP", "SW"], "default": "all"},
                "throws": {"values": ["L", "R"], "default": "all"},
                "age": {"values": ages, "default": "all"},
                "sample": {"values": sample, "default": "every"},
                "lg": {"values": ["AL", "NL"], "default": "both"},
                "position_players_pitching": {"values": [False, True], "default": False}},
        "default_group": {"hit": "all", "pit": "pitchers_only"},
    }


def method_sentence() -> str:
    return ("League is pooled: each numerator summed over the players shown, over the "
            "denominator summed the same way, through the shipped derivations. Player mean, "
            f"median and SD (sample SD) are over players with {FLOOR_PA} or more PA "
            f"({int(FLOOR_IP)} or more IP). Indexes are weighted by plate appearances or "
            "innings and read on each board's own scale; 100 is the average qualified player "
            "of that board, not the league mean. Descriptive: not a forecast.")


# --------------------------------------------------------------------------- #
# the series
# --------------------------------------------------------------------------- #
def _series_cell(side: str, block: dict) -> dict:
    out = {"n": block.get("n")}
    for k in ("pa", "ip"):
        if k in block:
            out[k] = block[k]
    out.update({k: v for k, v in (block.get("league") or {}).items() if v is not None})
    return out


def build_series(panels: Optional[dict] = None, out: Optional[Path] = None,
                 live_season: Optional[int] = None) -> dict:
    """The over-time series (lane 7.2) from the season panels: `panels` maps a
    season to its panel document, else every panel file in `out` is read."""
    if panels is None:
        panels = {}
        d = Path(out or out_dir())
        for p in sorted(d.glob(PANEL_NAME.format(season="*"))):
            doc = _read_json(p)
            if isinstance(doc, dict) and doc.get("schema") == SCHEMA and doc.get("season"):
                panels[int(doc["season"])] = doc
    seasons = sorted(panels)
    if not seasons:
        raise Refused("no season panel to build the series from")
    last = panels[seasons[-1]]
    live = int(live_season if live_season is not None else seasons[-1])
    provider = ((last.get("sources") or {}).get("war") or {}).get("war_provider")
    cells_def = {"hit": [], "pit": [], "team": []}
    labels = {}
    for y in seasons:
        for side in ("hit", "pit"):
            for g in (panels[y].get("group_defs") or {}).get(side) or []:
                labels.setdefault((side, g["key"]), g)
    for side in ("hit", "pit"):
        for key in SERIES_CELLS[side]:
            g = labels.get((side, key)) or {"key": key, "label": key, "rule": ""}
            cells_def[side].append({"key": key, "label": g["label"], "rule": g["rule"]})
    cells_def["team"] = [{"key": "club_mean", "label": "Club mean", "rule": "unweighted mean over the clubs"},
                         {"key": "club_sd", "label": "Club SD", "rule": "sample SD over the clubs"}]
    out_seasons = {}
    for y in seasons:
        doc = panels[y]
        groups = doc.get("groups") or {}
        s = {"games_per_team": doc.get("games_per_team"), "complete": bool(doc.get("complete")),
             "as_of": doc.get("as_of"), "hit": {}, "pit": {}, "team": {}}
        for side in ("hit", "pit"):
            for key in SERIES_CELLS[side]:
                blk = (groups.get(side) or {}).get(key)
                if blk is not None:
                    s[side][key] = _series_cell(side, blk)
        clubs = ((groups.get("team") or {}).get("clubs") or {}).get("stats") or {}
        if clubs:
            s["team"]["club_mean"] = {k: v.get("mean") for k, v in clubs.items() if v.get("mean") is not None}
            s["team"]["club_sd"] = {k: v.get("sd") for k, v in clubs.items() if v.get("sd") is not None}
            s["team"]["league"] = {k: v.get("league") for k, v in clubs.items() if v.get("league") is not None}
        out_seasons[str(y)] = s
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "live_season": live, "as_of": last.get("as_of"),
        "first_season": seasons[0], "last_season": seasons[-1],
        "method": ("Pooled over each cell's player rows through the shipped derivations "
                   "(the panel's League column); the role-innings cells and sp_ip_per_gs pool "
                   "the club sp and rp splits. A series_ref 'mlb_league_series.json#<side>/<key>' "
                   f"reads seasons[Y][side]['all'][key]. A cell under {THIN_CELL_N} players "
                   "draws hollow. Descriptive: not a forecast."),
        "thin_cell_n": THIN_CELL_N,
        "war": {"war_provider": provider, "label": _war_label(provider)},
        "stats": _stat_defs(provider),
        "cells": cells_def,
        "notes": {"left_out": LEFT_OUT, "deferred": DEFERRED},
        "seasons": out_seasons,
    }


# --------------------------------------------------------------------------- #
# export
# --------------------------------------------------------------------------- #
def _write(path: Path, doc: dict) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(doc, separators=(",", ":")) + "\n").encode("utf-8")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(raw)
    os.replace(tmp, path)
    return len(raw)


def export(season: Optional[int] = None, *, write: bool = True, log: Callable = print,
           out: Optional[Path] = None, today: Optional[date] = None, rebuild_all: bool = False,
           cache_dir: Optional[Path] = None, data_dir: Optional[Path] = None) -> dict:
    """Build the missing completed panels and the live one (or one `season`),
    then the series over every panel on disk. A refused season keeps its last
    good file. Returns a summary dict."""
    t0 = time.time()
    today = today or date.today()
    d = Path(out) if out is not None else out_dir()
    live = live_season_of(today, cache_dir)
    seasons = cached_seasons(cache_dir, live)
    if season is not None:
        todo = [int(season)]
    elif rebuild_all:
        todo = seasons
    else:
        todo = []
        for y in seasons:
            prior = _read_json(d / PANEL_NAME.format(season=y))
            if y == live or not (isinstance(prior, dict) and prior.get("complete")
                                 and prior.get("schema") == SCHEMA):
                todo.append(y)
    built, refused, sizes = {}, {}, {}
    for y in todo:
        try:
            doc = build_panel(y, live_season=live, today=today, cache_dir=cache_dir,
                              data_dir=data_dir)
        except Refused as exc:
            refused[y] = str(exc)
            log(f"  league averages: {exc}; keeping the last good file")
            continue
        built[y] = doc
        if write:
            sizes[y] = _write(d / PANEL_NAME.format(season=y), doc)
    panels = None if write else built
    series = None
    try:
        series = build_series(panels, out=d, live_season=live)
        if write:
            sizes["series"] = _write(d / SERIES_NAME, series)
    except Refused as exc:
        refused["series"] = str(exc)
        log(f"  league averages: {exc}")
    summary = {"out": str(d), "live": MLBSTATS_LEAGUE_TEAMS_LIVE, "live_season": live,
               "built": sorted(built), "refused": refused, "bytes": sizes,
               "seconds": round(time.time() - t0, 1)}
    log(f"  league averages: built {len(built)} panel(s), refused {len(refused)}, "
        f"{summary['seconds']}s, to {d}")
    if series is not None:
        summary["series_seasons"] = len(series["seasons"])
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--season", type=int, default=None)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    s = export(args.season, out=args.out, rebuild_all=args.all)
    return 1 if s["refused"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
