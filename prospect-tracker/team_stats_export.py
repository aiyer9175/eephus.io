# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""team_stats_export - the Team Stats payload for the Teams tab of /mlbstats/
(owner asks 15 and 20 of 2026-09-30; plan Part 8 item P8.2, task LT-05, queue
Q8_10; the lane design is part8/league_team_stats.md sections 5 and 7.3, with
plan 8.D row 2 and 8.E for the shared pieces).

WHAT IT WRITES. One file, `mlb_team_stats.json`: the thirty clubs of one
season with the EM+ team rollups on two club bases, the record and runs, MLB's
expected record, pitch counts with team PAR, lineup depth and the In-Game
Management club tendencies; plus a `history` block of the completed seasons.
Every number is a served value copied, a served value re-weighted, a sum or a
pooled ratio, or MLB's published expected record. Nothing here is a forecast,
and nothing relates a team column to wins, runs or outcomes.

THE TWO CLUB BASES (8.D row 2: one definition, two memberships).
  * club today (`roster`): the rollups the four board payloads serve and
    betting reads (bullpen_export.TEAM_BASIS = "current_roster"), COPIED
    unchanged from hitter_, starter_, bullpen_ and defense_leaderboards.json
    and war_leaderboards.json, never recomputed. copy_check() re-reads every
    board and refuses the payload when a single copied value differs.
  * earned: each player's season index weighted by the plate appearances or
    innings he took for each club. The player's season exposure (the PA, IP or
    fielding innings his board row or lab panel row carries, the weight the
    club-today rollup uses) is split across his clubs in proportion to his
    stint rows in war_source.stint_frame (PA for hitters, IPouts for
    pitchers, Inn for fielders; the frame war_board_export._earned_by_club
    reads, through the same door). A player with one club keeps his whole
    weight, so the two bases differ only by who holds a traded player. A
    season index is a season rate, so this re-weights served values and
    scores nothing new. Past seasons carry the earned basis only.

RECORDS. Through franchise_export._standings only (the site's one standings
parser; each division champion there is the unique divisionRank 1, never the
feed's divisionChamp flag, and this payload carries no division-title field).
xW-L is MLB's expectedRecords `xWinLoss` entry; a club whose xWinLoss wins
plus losses differ from its games played is refused. One-run and
extra-inning records come from splitRecords.

PITCH COUNTS. pitch_rates owns P/PA, P/IP and team PAR. Club today copies the
boards' pitch keys when the boards carry them (Q8_03, behind
pitch_rates.SERVE_PITCH_RATES); earned reads the club lines in
mlb_team_season: lineup P/PA over every plate appearance the club took,
staff P/IP, rotation and bullpen P/IP from the club sp and rp splits,
rotation IP/GS as innings thrown in starts per start (never the served
ip_per_gs), and the relief share of innings. The league role anchors from
the club splits must equal pitch_rates' anchors from the player splits within
ANCHOR_TOLERANCE.

TENDENCIES. Copied unchanged from management_board.json (clubs.rows and
teams.rows) with that module's own sentences. Style z columns carry no value
colour and no plus sign; realized columns keep their family floors.

F-SCORE HOOK (8.E). When data/fscore.json exists (the F-SCORE plan's FS-2)
each club's score, letter and rank are copied verbatim into `fscore`; until
then the payload says the join is pending. Whichever of this task and FS-2
lands second wires the page column.

THE FLAG. league_averages.MLBSTATS_LEAGUE_TEAMS_LIVE. While it is False the
file goes to .cache/league_teams/preview/ and nothing under data/ changes
(plan 8.D row 14). The flip is Q8_15's one commit.

Usage:
    python team_stats_export.py                  # the live season plus history
    python team_stats_export.py --out some/dir   # write somewhere else
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import league_averages
import pitch_rates

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUT_NAME = "mlb_team_stats.json"
SCHEMA = 1
SOURCE = "team_stats_export"
N_CLUBS = 30
FIRST_SEASON = 2000
ANCHOR_TOLERANCE = 0.001      # club-split against player-split league anchors
LEAGUE_OF = {103: "AL", 104: "NL"}

# (board file, block of player rows) per index family.
BOARD_OF = {"hem": ("hitter_leaderboards", "hitters"),
            "sem": ("starter_leaderboards", "starters"),
            "rem": ("bullpen_leaderboards", "relievers"),
            "dem": ("defense_leaderboards", "fielders")}
WAR_BOARD = "war_leaderboards"
SIX_BOARDS = ("hitter_leaderboards", "starter_leaderboards", "bullpen_leaderboards",
              "defense_leaderboards", "leverage_leaderboards", WAR_BOARD)

# The club-today block: each board's team keys, copied verbatim. The pitch keys
# exist only while pitch_rates.SERVE_PITCH_RATES is on (Q8_03); absent, None.
ROSTER_KEYS = {
    "hitter_leaderboards": ("offense_plus", "offense_plus_raw", "team_pa", "n_hitters",
                            "heart_hem", "lineup_p_pa", "lineup_par"),
    "starter_leaderboards": ("rotation_plus", "rotation_plus_raw", "starter_ip", "total_gs",
                             "n_starters", "front_sem", "rot_p_ip", "rot_par",
                             "rot_pit_per_gs"),
    "bullpen_leaderboards": ("bullpen_plus", "bullpen_plus_raw", "leverage_deploy_plus",
                             "leverage_deploy_cov", "leverage_deploy_n", "relief_ip",
                             "n_relievers", "high_lev_core_rem", "team_wpa", "sd", "md",
                             "pen_p_ip", "pen_par"),
    "defense_leaderboards": ("team_dem_plus", "team_dem_plus_raw", "team_inn", "n_fielders"),
    WAR_BOARD: ("war", "war_bat", "war_sp", "war_rp", "war_sw", "n_players"),
}

# The four rollups: key, board, the board's unrounded team value, its weight,
# the index family, the exposure unit, the stint-frame side and column.
ROLLUPS = (
    ("offense_plus", "hitter_leaderboards", "offense_plus_raw", "team_pa", "hem", "pa", "bat", "PA"),
    ("rotation_plus", "starter_leaderboards", "rotation_plus_raw", "starter_ip", "sem", "ip", "pit", "IPouts"),
    ("bullpen_plus", "bullpen_leaderboards", "bullpen_plus_raw", "relief_ip", "rem", "ip", "pit", "IPouts"),
    ("team_dem_plus", "defense_leaderboards", "team_dem_plus_raw", "team_inn", "dem", "inn", "bat", "Inn"),
)
LEAGUE_MEAN_KEYS = {"offense_plus": "offense_plus_pa_weighted",
                    "rotation_plus": "rotation_plus_ip_weighted",
                    "bullpen_plus": "bullpen_plus_ip_weighted",
                    "team_dem_plus": "team_dem_plus_inn_weighted"}

# Management club tendencies, copied verbatim (management.js boardCols and the
# running-game board). Style z columns: no ladder, no plus sign, no colour.
STYLE_Z_KEYS = ("z_hook", "z_pen", "z_bench", "z_ibb", "z_visit")
CLUB_STYLE_KEYS = ("games", "partial", "hook_median_pitches") + STYLE_Z_KEYS + (
    "pen_per_game", "bench_per_game", "ibb_per_game", "visit_per_game",
    "mean_li", "share_li_high")
MWPA_FAMILIES = ("pitching_change", "pinch_hit", "pinch_run", "intentional_walk",
                 "bunt", "steal")
RUNNING_KEYS = ("attempts", "success_rate", "share_2B", "share_3B", "mean_breakeven_faced")
FSCORE_KEYS = ("score", "letter", "rank")

HISTORY_COLS = ["club", "g", "w", "l", "rs", "ra", "xw", "xl",
                "p_per_pa", "p_per_ip", "sp_p_per_ip", "rp_p_per_ip", "sp_ip_per_gs",
                "relief_ip_share", "lineup_par", "rotation_par", "bullpen_par",
                "offense_plus", "rotation_plus", "bullpen_plus", "team_dem_plus"]

COPY = {
    "lead": "Every number here is what happened, copied, summed or re-weighted. "
            "Descriptive: not a forecast.",
    "plus_scale": "100 is the average qualified player of each board, not the average "
                  "club. The league's own weighted mean of each rollup sits beside it.",
    "basis_roster": "Club today: the rollups the Hitters, Starters, Bullpen and Defense "
                    "team tabs serve, copied unchanged. A traded player's whole season "
                    "counts for the club that holds him now.",
    "basis_earned": "Earned: each player's season index weighted by the plate appearances "
                    "or innings he took for each club, split by his Baseball-Reference "
                    "stint rows. It re-weights the served per-player values and scores "
                    "nothing new.",
    "past_seasons": "Past seasons show the earned basis only: a club-today rollup of a "
                    "past season would put its players under the clubs that hold them now.",
    "xwl": "xW-L is MLB's published expected record (xWinLoss) over the games played.",
    "w_minus_xw": "W - xW is the gap between the record and the record the runs imply. "
                  "It describes the games played and nothing else.",
    "pitches": "Pitch counts are what each club earned: lineup P/PA over every plate "
               "appearance it took, pitchers' bats included; rotation and bullpen P/IP "
               "from MLB's starter and reliever splits, innings counted as outs / 3. "
               "Team PAR is 100 x a club's rate over the mean of the thirty club rates, "
               "so the clubs average 100 and 110 is 10 percent more pitches. Rotation "
               "IP/GS is innings thrown in starts per start.",
    "depth": "Heart 3 is the mean HEM+ of the club's top three qualified hitters; Rest is "
             "the PA-weighted HEM+ of its other hitters; the gap is Heart 3 minus Rest. "
             "Same rows and club basis as Offense+ (club today).",
    "coverage": "Swingmen and arms under the board floors sit in neither Rotation+ nor "
                "Bullpen+, and hitters with no HEM+ sit outside Offense+.",
}


class Refused(RuntimeError):
    """The payload failed a check; the last good file is kept."""


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def _num(v):
    if v is None or v == "" or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _rnd(v, nd):
    return None if v is None else round(float(v), nd)


def _nearest(v):
    """Plus stats and PAR round to the nearest point (halves up)."""
    return None if v is None else int(math.floor(float(v) + 0.5))


def _ratio(num, den):
    n, d = _num(num), _num(den)
    if n is None or d is None or d <= 0:
        return None
    return n / d


def _read_json(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _canon(code) -> Optional[str]:
    from trades import canonical_org
    return canonical_org(str(code).strip()) if code not in (None, "") else None


def out_path() -> Path:
    """data/ only once the flag is flipped; the preview directory until then."""
    return league_averages.out_dir() / OUT_NAME


def _board(name: str, data_dir: Optional[Path]) -> dict:
    return _read_json(Path(data_dir or DATA_DIR) / f"{name}.json") or {}


def _board_teams(name: str, data_dir: Optional[Path]) -> dict:
    """{canonical club: (board spelling, team row)} of one board's teams block."""
    out = {}
    for t in _board(name, data_dir).get("teams") or []:
        club = _canon(t.get("team"))
        if club:
            out[club] = (t.get("team"), t)
    return out


# --------------------------------------------------------------------------- #
# per-player season index values and their exposure
# --------------------------------------------------------------------------- #
def season_index(season: int, live_season: int, data_dir: Optional[Path] = None) -> dict:
    """{family: {mlbam: (index value, season exposure)}} plus "basis".

    The live season reads the four board payloads with the exact fields the
    club-today rollups weight (hem_plus by pa, sem_plus and rem_plus by ip,
    dem_plus_raw by inn). A completed season reads the window lab's memoised
    panel (every scored player, 2022 on). Earlier seasons have no source and
    return empty families. Nothing is scored here."""
    out = {"hem": {}, "sem": {}, "rem": {}, "dem": {}, "basis": None}
    if int(season) == int(live_season):
        fields = {"hem": ("hem_plus", "pa"), "sem": ("sem_plus", "ip"),
                  "rem": ("rem_plus", "ip"), "dem": ("dem_plus_raw", "inn")}
        for fam, (name, block) in BOARD_OF.items():
            blob = _board(name, data_dir)
            if blob.get("season") is None or int(blob["season"]) != int(season):
                continue
            vf, ef = fields[fam]
            for r in blob.get(block) or []:
                v, e = _num(r.get(vf)), _num(r.get(ef))
                if r.get("mlbam") is None or v is None or not e or e <= 0:
                    continue
                out[fam][int(r["mlbam"])] = (v, e)
        out["basis"] = "the live boards' scored pools"
        return out
    lab = league_averages._lab_panel(season)
    if lab is None:
        return out
    for mid, r in (lab.get("hit") or {}).items():
        v, e = _num(r.get("hem")), _num(r.get("pa"))
        if v is not None and e and e > 0:
            out["hem"][int(mid)] = (v, e)
    for mid, r in (lab.get("pit") or {}).items():
        e = _num(r.get("outs"))
        if not e or e <= 0:
            continue
        if _num(r.get("sem")) is not None:
            out["sem"][int(mid)] = (_num(r["sem"]), e / 3.0)
        elif _num(r.get("rem")) is not None:
            out["rem"][int(mid)] = (_num(r["rem"]), e / 3.0)
    for mid, r in (lab.get("dfn") or {}).items():
        v = _num(r.get("dem_raw"))
        v = _num(r.get("dem")) if v is None else v
        e = _num(r.get("inn"))
        if v is not None and e and e > 0:
            out["dem"][int(mid)] = (v, e)
    out["basis"] = "the window lab's season panel (every scored player)"
    return out


# --------------------------------------------------------------------------- #
# stints
# --------------------------------------------------------------------------- #
_FRAMES: dict = {}


def stint_frame(side: str):
    """war_board_export._stint_frame: the door the Earned eWAR basis reads,
    one read per process. Only the exposure columns are used here."""
    if side not in _FRAMES:
        import war_board_export
        _FRAMES[side] = war_board_export._stint_frame(side)
    return _FRAMES[side]


def stint_shares(frame, season: int, column: str, clubs: set) -> tuple[dict, dict]:
    """({mlbam: {club: share}}, meta) for one season and exposure column.

    A share is the stint's exposure over the player's whole-season exposure in
    the frame, so a player's shares sum to 1 over his resolvable clubs plus
    whatever sits on a code outside `clubs`, the season's thirty canonical
    clubs (counted, never assigned: trades.canonical_org passes an unknown code
    through unchanged)."""
    sub = frame[frame["year_ID"] == int(season)]
    per: dict = {}
    unmapped: dict = {}
    for mid, team, x in zip(sub["mlb_ID"].tolist(), sub["team_ID"].tolist(),
                            sub[column].tolist()):
        m, w = _num(mid), _num(x)
        if m is None or w is None or w <= 0:
            continue
        club = _canon(team)
        p = per.setdefault(int(m), {"_total": 0.0})
        p["_total"] += w
        if club not in clubs:
            unmapped[str(team)] = unmapped.get(str(team), 0) + 1
            continue
        p[club] = p.get(club, 0.0) + w
    shares = {}
    for m, p in per.items():
        tot = p.pop("_total")
        shares[m] = {c: w / tot for c, w in p.items()}
    return shares, {"n_players": len(shares), "unmapped_codes": sorted(unmapped)}


def earned_rollups(season: int, *, live_season: Optional[int] = None,
                   data_dir: Optional[Path] = None, frames: Optional[dict] = None,
                   index: Optional[dict] = None,
                   clubs: Optional[set] = None) -> tuple[dict, dict]:
    """({club: {key: value}}, meta): the four EM+ rollups on the earned basis.

    rollup(club) = sum(v x e x share) / sum(e x share) over the family's scored
    players, where v is the player's season index, e his season exposure and
    share his stint share at the club (stint_shares). `frames` ({"bat": df,
    "pit": df}), `index` (season_index's shape) and `clubs` (the season's
    canonical clubs) may be passed in; each defaults to the real source (the
    clubs to the season's standings)."""
    live = int(live_season if live_season is not None else season)
    idx = index if index is not None else season_index(season, live, data_dir)
    clubs = set(clubs) if clubs is not None else set(records(season))
    acc: dict = {}
    meta = {"index_basis": idx.get("basis"), "families": {}}
    share_memo: dict = {}
    for key, _board_name, _raw, _w, fam, unit, side, col in ROLLUPS:
        vals = idx.get(fam) or {}
        fm = {"n_players": len(vals), "n_unassigned": 0, "exposure": 0.0,
              "exposure_assigned": 0.0, "unit": unit}
        if not vals:
            meta["families"][key] = fm
            continue
        if (side, col) not in share_memo:
            frame = (frames or {}).get(side)
            if frame is None:
                frame = stint_frame(side)
            share_memo[(side, col)] = stint_shares(frame, season, col, clubs)
        shares, smeta = share_memo[(side, col)]
        fm["unmapped_codes"] = smeta["unmapped_codes"]
        lg_num = lg_den = 0.0
        for mid, (v, e) in vals.items():
            fm["exposure"] += e
            sh = shares.get(int(mid))
            if not sh:
                fm["n_unassigned"] += 1
                continue
            for club, s in sh.items():
                w = e * s
                a = acc.setdefault(club, {}).setdefault(key, [0.0, 0.0, 0])
                a[0] += v * w
                a[1] += w
                a[2] += 1
                lg_num += v * w
                lg_den += w
                fm["exposure_assigned"] += w
        fm["league_mean"] = _rnd(lg_num / lg_den, 2) if lg_den else None
        fm["exposure"] = _rnd(fm["exposure"], 1)
        fm["exposure_assigned"] = _rnd(fm["exposure_assigned"], 1)
        meta["families"][key] = fm
    out: dict = {}
    for club, fams in acc.items():
        row = {}
        for key, *_rest in ROLLUPS:
            unit = _rest[4]
            a = fams.get(key)
            raw = (a[0] / a[1]) if a and a[1] > 0 else None
            row[key] = _nearest(raw)
            row[f"{key}_raw"] = _rnd(raw, 2)
            row[f"{key}_{unit}"] = _rnd(a[1], 1) if a else None
            row[f"{key}_n"] = a[2] if a else 0
        out[club] = row
    return out, meta


# --------------------------------------------------------------------------- #
# club today (copied) and the league's own weighted means
# --------------------------------------------------------------------------- #
def roster_block(data_dir: Optional[Path] = None) -> tuple[dict, dict, dict]:
    """({club: {key: value}}, {club: board spelling}, {board: (season, as_of)}).
    Every value is the board's own, unchanged; a key the board lacks is None."""
    out: dict = {}
    spelling: dict = {}
    stamps: dict = {}
    for name, keys in ROSTER_KEYS.items():
        blob = _board(name, data_dir)
        stamps[name] = {"season": blob.get("season"), "as_of": blob.get("as_of")}
        teams = _board_teams(name, data_dir)
        if len(teams) != N_CLUBS:
            raise Refused(f"{name}: {len(teams)} clubs resolve, expected {N_CLUBS}")
        for club, (code, t) in teams.items():
            spelling.setdefault(club, code)
            row = out.setdefault(club, {})
            for k in keys:
                row[k] = t.get(k)
    return out, spelling, stamps


def copy_check(roster: dict, data_dir: Optional[Path] = None) -> list[str]:
    """Problems where a copied club-today value differs from its board; []
    when every value matches. The exporter refuses on any problem."""
    problems = []
    for name, keys in ROSTER_KEYS.items():
        for club, (_code, t) in _board_teams(name, data_dir).items():
            for k in keys:
                if (roster.get(club) or {}).get(k) != t.get(k):
                    problems.append(f"{name} {club} {k}: {roster.get(club, {}).get(k)!r} "
                                    f"against {t.get(k)!r}")
    return problems


def roster_league_means(data_dir: Optional[Path] = None) -> dict:
    """The league's own weighted mean of each served rollup (the boards' raw team
    values weighted by each club's PA, IP or innings) and the SD across clubs.
    100 is the average qualified player, not the average club, so these sit
    beside the column and are never typed by a page."""
    means, sds = {}, {}
    for key, name, raw_k, w_k, *_rest in ROLLUPS:
        rows = [t for _c, t in _board_teams(name, data_dir).values()
                if _num(t.get(raw_k)) is not None and _num(t.get(w_k))]
        den = sum(_num(t[w_k]) for t in rows)
        means[LEAGUE_MEAN_KEYS[key]] = _rnd(
            sum(_num(t[raw_k]) * _num(t[w_k]) for t in rows) / den, 2) if den else None
        xs = [_num(t[raw_k]) for t in rows]
        sds[key] = _rnd(statistics.pstdev(xs), 2) if len(xs) > 1 else None
    return {"means": means, "club_sd": sds}


def depth_block(data_dir: Optional[Path] = None) -> dict:
    """{club: {heart_hem, rest_hem, gap, pa_share_hem_100, n_rest}} on the
    Offense+ rows and basis (club today: the hitter board's rows by its team).

    Heart 3 is the board's served heart_hem; the three hitters behind it are
    found the way hem_plus.team_offense finds them (qualified, top three by
    HEM+). Refuses when the rows do not rebuild the served Offense+ or Heart 3,
    which would mean the membership read here is not the board's."""
    import hem_plus
    blob = _board("hitter_leaderboards", data_dir)
    teams = _board_teams("hitter_leaderboards", data_dir)
    by_team: dict = {}
    for r in blob.get("hitters") or []:
        if _num(r.get("hem_plus")) is None or not _num(r.get("pa")):
            continue
        by_team.setdefault(r.get("team"), []).append(r)
    out = {}
    for club, (code, t) in teams.items():
        rows = by_team.get(code) or []
        den = sum(r["pa"] for r in rows)
        if not den:
            continue
        off = sum(r["hem_plus"] * r["pa"] for r in rows) / den
        if _num(t.get("offense_plus_raw")) is None or abs(off - t["offense_plus_raw"]) > 1e-6:
            raise Refused(f"depth {club}: the board rows rebuild Offense+ {off} against "
                          f"the served {t.get('offense_plus_raw')}")
        front = sorted([r for r in rows if r["pa"] >= hem_plus.QUALIFY_MIN_PA],
                       key=lambda r: (-r["hem_plus"], -r["pa"]))[:3]
        heart = _nearest(sum(r["hem_plus"] for r in front) / len(front)) if front else None
        if front and t.get("heart_hem") is not None and heart != t["heart_hem"]:
            # hem_plus rounds with round(); a halfway mean is the only way the
            # two can differ, and then the served value stands.
            if abs(sum(r["hem_plus"] for r in front) / len(front) - t["heart_hem"]) > 0.5:
                raise Refused(f"depth {club}: Heart 3 rebuilds {heart} against the "
                              f"served {t['heart_hem']}")
        keys = {r.get("mlbam") for r in front}
        rest = [r for r in rows if r.get("mlbam") not in keys]
        rden = sum(r["pa"] for r in rest)
        rest_hem = (sum(r["hem_plus"] * r["pa"] for r in rest) / rden) if rden else None
        heart_v = t.get("heart_hem")
        out[club] = {
            "heart_hem": heart_v,
            "rest_hem": _rnd(rest_hem, 1),
            "gap": _rnd(heart_v - rest_hem, 1) if heart_v is not None and rest_hem is not None else None,
            "pa_share_hem_100": _rnd(sum(r["pa"] for r in rows if r["hem_plus"] >= 100) / den, 3),
            "n_rest": len(rest),
        }
    return out


# --------------------------------------------------------------------------- #
# records, pitch counts, tendencies
# --------------------------------------------------------------------------- #
_STANDINGS: list = []


def standings() -> dict:
    """franchise_export._standings rows, {club: {season: row}}, read once."""
    if not _STANDINGS:
        import franchise_export
        _STANDINGS.append(franchise_export._standings()[0])
    return _STANDINGS[0]


def records(season: int, rows: Optional[dict] = None) -> dict:
    """{club: record block} for one season. Refuses when 30 clubs do not carry a
    row or a club's xWinLoss wins plus losses differ from its games played."""
    rows = standings() if rows is None else rows
    out = {}
    for club, by_season in rows.items():
        r = by_season.get(int(season))
        if not r:
            continue
        xw, xl, g = r.get("xw"), r.get("xl"), r.get("gp")
        if xw is None or xl is None or g is None or xw + xl != g:
            raise Refused(f"records {season} {club}: xWinLoss {xw}-{xl} does not sum "
                          f"to games played {g}")
        out[club] = {
            "lg": LEAGUE_OF.get(r.get("league_id")),
            "g": g, "w": r.get("w"), "l": r.get("l"),
            "rs": r.get("rs"), "ra": r.get("ra"), "rd": r.get("rd"),
            "xw": xw, "xl": xl,
            "w_minus_xw": (r["w"] - xw) if r.get("w") is not None else None,
            "one_run": r.get("one_run"), "extra_inning": r.get("extra_inning"),
        }
    if len(out) != N_CLUBS:
        raise Refused(f"records {season}: {len(out)} clubs, expected {N_CLUBS}")
    return out


def _team_lines(season: int) -> dict:
    import mlb_team_season
    try:
        lines = mlb_team_season.team_lines(int(season))
    except mlb_team_season.NotCached as exc:
        raise Refused(f"pitches {season}: {exc}") from None
    for kind in ("hit", "pit", "sp", "rp"):
        if len(lines.get(kind) or {}) != N_CLUBS:
            raise Refused(f"pitches {season}: {len(lines.get(kind) or {})} clubs on "
                          f"{kind}, expected {N_CLUBS}")
    return lines


def pitch_block(lines: dict) -> tuple[dict, dict]:
    """({club: pitch counts}, league) on the earned basis, from the club lines.
    Rates through pitch_rates (innings are outs / 3); team PAR through
    pitch_rates.team_par over the thirty clubs."""
    per = {}
    for club in lines["hit"]:
        h, p, sp, rp = (lines[k][club] for k in ("hit", "pit", "sp", "rp"))
        per[club] = {
            "pa": h.get("pa"), "pit_seen": h.get("pitches"),
            "p_per_pa": pitch_rates.p_pa(h.get("pitches"), h.get("pa")),
            "ip": pitch_rates.innings(p.get("outs")), "pit_thrown": p.get("pitches"),
            "p_per_ip": pitch_rates.p_ip(p.get("pitches"), p.get("outs")),
            "sp_ip": pitch_rates.innings(sp.get("outs")), "sp_gs": sp.get("gs"),
            "sp_p_per_ip": pitch_rates.p_ip(sp.get("pitches"), sp.get("outs")),
            "sp_ip_per_gs": _ratio((_num(sp.get("outs")) or 0) / 3.0, sp.get("gs")),
            "rp_ip": pitch_rates.innings(rp.get("outs")),
            "rp_p_per_ip": pitch_rates.p_ip(rp.get("pitches"), rp.get("outs")),
            "relief_ip_share": _ratio(rp.get("outs"), p.get("outs")),
        }
    pars = {"lineup_par": pitch_rates.team_par({c: v["p_per_pa"] for c, v in per.items()}),
            "rotation_par": pitch_rates.team_par({c: v["sp_p_per_ip"] for c, v in per.items()}),
            "bullpen_par": pitch_rates.team_par({c: v["rp_p_per_ip"] for c, v in per.items()})}

    def tot(kind, f):
        return sum(_num(x.get(f)) or 0 for x in lines[kind].values())
    league = {
        "p_per_pa": pitch_rates.p_pa(tot("hit", "pitches"), tot("hit", "pa")),
        "p_per_ip": pitch_rates.p_ip(tot("pit", "pitches"), tot("pit", "outs")),
        "sp_p_per_ip": pitch_rates.p_ip(tot("sp", "pitches"), tot("sp", "outs")),
        "rp_p_per_ip": pitch_rates.p_ip(tot("rp", "pitches"), tot("rp", "outs")),
        "sp_ip_per_gs": _ratio(tot("sp", "outs") / 3.0, tot("sp", "gs")),
        "relief_ip_share": _ratio(tot("rp", "outs"), tot("pit", "outs")),
        "rs_g": _ratio(tot("hit", "r"), tot("hit", "g")),
        "pa": int(tot("hit", "pa")), "ip": _rnd(tot("pit", "outs") / 3.0, 1),
    }
    out = {}
    for club, v in per.items():
        out[club] = {
            "pa": v["pa"], "pit_seen": v["pit_seen"], "p_per_pa": _rnd(v["p_per_pa"], 3),
            "lineup_par": _nearest(pars["lineup_par"].get(club)),
            "ip": _rnd(v["ip"], 1), "pit_thrown": v["pit_thrown"],
            "p_per_ip": _rnd(v["p_per_ip"], 2),
            "sp_ip": _rnd(v["sp_ip"], 1), "sp_gs": v["sp_gs"],
            "sp_p_per_ip": _rnd(v["sp_p_per_ip"], 2),
            "rotation_par": _nearest(pars["rotation_par"].get(club)),
            "sp_ip_per_gs": _rnd(v["sp_ip_per_gs"], 2),
            "rp_ip": _rnd(v["rp_ip"], 1), "rp_p_per_ip": _rnd(v["rp_p_per_ip"], 2),
            "bullpen_par": _nearest(pars["bullpen_par"].get(club)),
            "relief_ip_share": _rnd(v["relief_ip_share"], 3),
        }
    lg = {k: (_rnd(v, 3) if isinstance(v, float) else v) for k, v in league.items()}
    lg["par_mean"] = {k: _rnd(statistics.fmean([x for x in d.values() if x is not None]), 6)
                      for k, d in pars.items()}
    return out, lg


def anchor_check(lines: dict, season: int, fetch: bool = False) -> dict:
    """The league role anchors from the club splits against pitch_rates' anchors
    from the player splits (8.D row 2 pin i). Refuses past ANCHOR_TOLERANCE."""
    def pooled(kind):
        np_ = sum(_num(x.get("pitches")) or 0 for x in lines[kind].values())
        outs = sum(_num(x.get("outs")) or 0 for x in lines[kind].values())
        return pitch_rates.p_ip(np_, outs)
    try:
        lr = pitch_rates.league_rates("MLB", int(season), fetch=fetch)
    except Exception as exc:   # noqa: BLE001 - an absent role cache is disclosed
        return {"checked": False, "why": f"{type(exc).__name__}: {exc}"}
    out = {"checked": True, "basis": lr.get("basis")}
    for code in ("sp", "rp"):
        club, player = pooled(code), (lr.get(code) or {}).get("p_ip")
        rel = (abs(club - player) / player) if club and player else None
        out[code] = {"club_splits": _rnd(club, 4), "player_splits": _rnd(player, 4),
                     "rel_diff": _rnd(rel, 6)}
        if rel is None:
            out["checked"] = False
        elif rel > ANCHOR_TOLERANCE:
            raise Refused(f"anchors {season} {code}: club splits {club} against player "
                          f"splits {player} ({rel:.4%})")
    return out


def tendencies(season: int, data_dir: Optional[Path] = None) -> tuple[dict, dict]:
    """({club: {"style": {...}, "running": {...}}}, the module's sentences) for
    one season, copied unchanged from management_board.json. {} for a season
    the management board does not carry (2020, and before 2018)."""
    mg = _board("management_board", data_dir)
    clubs, teams = mg.get("clubs") or {}, mg.get("teams") or {}
    out: dict = {}
    style_keys = CLUB_STYLE_KEYS + tuple(f"mwpa_{f}" for f in MWPA_FAMILIES) + tuple(
        f"n_{f}" for f in MWPA_FAMILIES)
    for r in clubs.get("rows") or []:
        if r.get("season") == int(season):
            c = _canon(r.get("club"))
            if c:
                out.setdefault(c, {})["style"] = {k: r[k] for k in style_keys if k in r}
    for r in teams.get("rows") or []:
        if r.get("season") == int(season):
            c = _canon(r.get("team"))
            if c:
                out.setdefault(c, {})["running"] = {k: r[k] for k in RUNNING_KEYS if k in r}
    sentences = {
        "style_sentence": clubs.get("style_sentence"),
        "columns_are_realized_not_skill": clubs.get("columns_are_realized_not_skill"),
        "agent_sentence": clubs.get("agent_sentence"),
        "sort_by_realized_is_a_rank_by_what_happened":
            clubs.get("sort_by_realized_is_a_rank_by_what_happened"),
        "realized_header_tag": clubs.get("realized_header_tag"),
        "floors": clubs.get("floors"),
        "running_columns_are_style_not_skill": teams.get("columns_are_style_not_skill"),
        "why_no_plus_metric": ((mg.get("sections") or {}).get("team_style") or {})
            .get("why_no_plus_metric"),
    }
    return out, sentences


def fscore_join(data_dir: Optional[Path] = None) -> tuple[Optional[dict], dict]:
    """({club: {score, letter, rank}} copied verbatim, meta) when data/fscore.json
    exists (F-SCORE FS-2); (None, the pending note) until then."""
    p = Path(data_dir or DATA_DIR) / "fscore.json"
    blob = _read_json(p)
    if not isinstance(blob, dict):
        return None, {"joined": False,
                      "note": "data/fscore.json is not on disk yet; the F-SCORE column "
                              "joins here verbatim once FS-2 lands"}
    out = {}
    for code, row in (blob.get("clubs") or {}).items():
        c = _canon(code)
        if c and isinstance(row, dict):
            out[c] = {k: row.get(k) for k in FSCORE_KEYS}
    return out, {"joined": True, "generated_at": blob.get("generated_at"),
                 "as_of": blob.get("as_of"), "n": len(out)}


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #
def live_season_of(data_dir: Optional[Path] = None) -> int:
    s = _board("hitter_leaderboards", data_dir).get("season")
    if s is None:
        raise Refused("hitter_leaderboards.json carries no season")
    return int(s)


def _earned_league_means(meta: dict) -> dict:
    return {LEAGUE_MEAN_KEYS[k]: (meta["families"].get(k) or {}).get("league_mean")
            for k in LEAGUE_MEAN_KEYS}


def history(live_season: int, *, frames: Optional[dict] = None,
            data_dir: Optional[Path] = None, log: Callable = print) -> dict:
    """The completed seasons, earned basis only: {"cols", "seasons": {Y:
    {"rows", "league", "index_basis"}}, "refused": {Y: why}}. A season with no
    window lab panel carries no EM+ values (null cells)."""
    seasons, refused = {}, {}
    rows_all = standings()
    for y in range(FIRST_SEASON, int(live_season)):
        try:
            rec = records(y, rows_all)
            lines = _team_lines(y)
            pitches, lg = pitch_block(lines)
        except Refused as exc:
            refused[str(y)] = str(exc)
            continue
        idx = season_index(y, live_season, data_dir)
        earned, emeta = ({}, {"index_basis": None, "families": {}})
        if idx.get("basis"):
            earned, emeta = earned_rollups(y, live_season=live_season, data_dir=data_dir,
                                           frames=frames, index=idx, clubs=set(rec))
        rows = []
        for club in sorted(rec):
            r, p, e = rec[club], pitches.get(club) or {}, earned.get(club) or {}
            vals = {**r, **p, **{k: e.get(k) for k in LEAGUE_MEAN_KEYS}}
            rows.append([club if c == "club" else vals.get(c) for c in HISTORY_COLS])
        seasons[str(y)] = {"rows": rows, "index_basis": emeta.get("index_basis"),
                           "league": {**{k: lg[k] for k in ("p_per_pa", "p_per_ip",
                                                             "sp_p_per_ip", "rp_p_per_ip",
                                                             "sp_ip_per_gs", "relief_ip_share",
                                                             "rs_g")},
                                      "earned": _earned_league_means(emeta)
                                      if emeta.get("index_basis") else None}}
    if refused:
        log(f"  team stats: history refused {len(refused)} season(s): {sorted(refused)}")
    return {"cols": HISTORY_COLS, "seasons": seasons, "refused": refused}


def build(season: Optional[int] = None, *, data_dir: Optional[Path] = None,
          frames: Optional[dict] = None, with_history: bool = True,
          today: Optional[date] = None, log: Callable = print) -> dict:
    """The whole payload for the live season (or `season`). Raises Refused."""
    import mlb_team_season
    today = today or date.today()
    live = live_season_of(data_dir)
    season = int(season) if season is not None else live
    is_live = season == live

    rec = records(season)
    lines = _team_lines(season)
    pitches, pitch_lg = pitch_block(lines)
    anchors = anchor_check(lines, season)
    earned, emeta = earned_rollups(season, live_season=live, data_dir=data_dir, frames=frames,
                                   clubs=set(rec))
    tend, tend_copy = tendencies(season, data_dir)
    fscore, fscore_meta = fscore_join(data_dir) if is_live else (None, {"joined": False})

    roster, spelling, stamps = ({}, {}, {})
    roster_means, depth = (None, {})
    war_earned = {}
    if is_live:
        roster, spelling, stamps = roster_block(data_dir)
        problems = copy_check(roster, data_dir)
        if problems:
            raise Refused(f"club today: {len(problems)} copied value(s) differ from "
                          f"their board, first {problems[0]}")
        roster_means = roster_league_means(data_dir)
        depth = depth_block(data_dir)
        for club, (_code, t) in _board_teams(WAR_BOARD, data_dir).items():
            war_earned[club] = t.get("war_earned")

    clubs = sorted(rec)
    if set(clubs) != set(pitches):
        raise Refused(f"records and pitch lines name different clubs: "
                      f"{sorted(set(clubs) ^ set(pitches))}")
    teams = []
    for club in clubs:
        e = dict(earned.get(club) or {})
        if is_live:
            e["war"] = war_earned.get(club)
        row = {"club": club, "code": spelling.get(club),
               "team_id": (lines["hit"].get(club) or {}).get("team_id"),
               **rec[club],
               "roster": roster.get(club) if is_live else None,
               "earned": e,
               "pitches": pitches.get(club),
               "depth": depth.get(club) if is_live else None,
               "tendencies": tend.get(club)}
        if fscore is not None:
            row["fscore"] = fscore.get(club)
        teams.append(row)

    fetched = mlb_team_season.cached(season, "hit").get("fetched_at")
    payload = {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "season": season, "live_season": live,
        "complete": mlb_team_season.season_complete(season, today),
        "as_of": {"boards": stamps, "team_lines": fetched},
        "flag": {"MLBSTATS_LEAGUE_TEAMS_LIVE": league_averages.MLBSTATS_LEAGUE_TEAMS_LIVE},
        "basis": {
            "roster": "the served rollups, copied unchanged (bullpen_export.TEAM_BASIS "
                      "current_roster)" if is_live else None,
            "earned": "season index x the season exposure split by stint share "
                      "(war_source.stint_frame through war_board_export._stint_frame)",
            "records": "franchise_export._standings; xWinLoss; splitRecords",
            "pitches": "StatsAPI teams/stats and statSplits sp, rp (mlb_team_season)",
            "tendencies": "management_board.json clubs.rows and teams.rows, style not skill",
        },
        "league": {
            "roster": roster_means,
            "earned": {"means": _earned_league_means(emeta)},
            "pitches": pitch_lg,
            "anchors": anchors,
            "coverage": {
                "offense_pa": (emeta["families"].get("offense_plus") or {}).get("exposure"),
                "league_pa": pitch_lg.get("pa"),
                "rotation_ip": (emeta["families"].get("rotation_plus") or {}).get("exposure"),
                "bullpen_ip": (emeta["families"].get("bullpen_plus") or {}).get("exposure"),
                "league_ip": pitch_lg.get("ip"),
            },
        },
        "earned_meta": emeta,
        "columns": {
            "style_z": list(STYLE_Z_KEYS),
            "no_value_colour": list(STYLE_Z_KEYS),
            "realized": [f"mwpa_{f}" for f in MWPA_FAMILIES],
            "value_ruler": {"offense_plus": "ratio", "rotation_plus": "z",
                            "bullpen_plus": "z", "leverage_deploy_plus": "z",
                            "team_dem_plus": "z"},
        },
        "copy": {**COPY, "tendencies": tend_copy},
        "fscore": fscore_meta,
        "teams": teams,
    }
    if with_history:
        payload["history"] = history(live, frames=frames, data_dir=data_dir, log=log)
    return payload


def _write(path: Path, doc: dict) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(doc, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(raw)
    os.replace(tmp, path)
    return len(raw)


def export(season: Optional[int] = None, *, write: bool = True, out: Optional[Path] = None,
           data_dir: Optional[Path] = None, frames: Optional[dict] = None,
           log: Callable = print) -> dict:
    """Build and write the payload. A refusal keeps the last good file, and a
    payload thinner than the one on disk (fewer clubs or history seasons) is
    not written. Returns a summary dict."""
    t0 = time.time()
    path = Path(out) if out is not None else out_path()
    if path.suffix != ".json":
        path = path / OUT_NAME
    try:
        doc = build(season, data_dir=data_dir, frames=frames, log=log)
    except Refused as exc:
        log(f"  team stats: {exc}; keeping the last good file")
        return {"out": str(path), "refused": str(exc), "written": False}
    prior = _read_json(path)
    n_hist = len((doc.get("history") or {}).get("seasons") or {})
    if isinstance(prior, dict) and prior.get("season") == doc["season"]:
        p_hist = len((prior.get("history") or {}).get("seasons") or {})
        if len(prior.get("teams") or []) > len(doc["teams"]) or p_hist > n_hist:
            log("  team stats: the new payload is thinner than the file on disk; kept")
            return {"out": str(path), "refused": "thinner than the last good file",
                    "written": False}
    size = _write(path, doc) if write else 0
    summary = {"out": str(path), "refused": None, "written": bool(write),
               "bytes": size, "season": doc["season"], "teams": len(doc["teams"]),
               "history_seasons": n_hist, "seconds": round(time.time() - t0, 1)}
    log(f"  team stats: {summary['teams']} clubs, {n_hist} history seasons, "
        f"{size} bytes, {summary['seconds']}s, to {path}")
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--season", type=int, default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    s = export(args.season, out=args.out)
    return 1 if s.get("refused") else 0


if __name__ == "__main__":
    raise SystemExit(main())
