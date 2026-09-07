# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MLB Leverage Leaderboards (S-1).

Realized in-game LEVERAGE impact, self-computed from the MLB StatsAPI
winProbability feed (mlb_leverage), for the two sides the reliever board doesn't
cover:

  - BATTERS: WPA (win probability added, batter perspective), pLI (average
    leverage index faced), Clutch (WPA/pLI minus WPA/LI), and context-neutral
    WPA/LI.
  - STARTERS: per-start WPA and WPA/LI (the entry-inning==1 games the reliever
    fold drops).

Descriptive realized-impact metrics (the RIV+ / xREM+ precedent), NOT a predictive
model. The same warm winProbability cache the bullpen board already walks powers
this in ONE extra pass (mlb_leverage.fetch_season_all_leverage). Writes
data/leverage_leaderboards.json.

Run: `python leverage_export.py [season]`
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Optional

import mlb_leverage
from bullpen_export import (load_season_pitching, guard_nonempty_block,
                            team_basis_meta, basis_rows_for, _ingest_red)
from hitter_export import load_season_hitting

_log = logging.getLogger(__name__)
ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
OUT_PATH = DATA_DIR / "leverage_leaderboards.json"
HISTORY_PATH = DATA_DIR / "leverage_history.json"

QUAL_PA = 250       # batter qualification (a regular's sample)
QUAL_STARTS = 5     # starter qualification

# Yearly leverage-history window: the seasons the /mlbstats/ Leverage history
# pills offer. Every game of these seasons is already in the winProbability
# cache (the reliever board + gmLI-3yr lab warm 2019+), so the multi-season
# fold reads from disk; the only network is one schedule + two statline calls
# per season.
HISTORY_SEASONS = [2021, 2022, 2023, 2024, 2025]


def _name_team(rows: list[dict]) -> dict:
    out: dict[int, tuple] = {}
    for r in rows:
        mid = r.get("mlbam")
        if mid is not None:
            out[int(mid)] = (r.get("name"), r.get("team"))
    return out


def _build_batters(bat: dict, bat_nt: dict, pit_nt: dict | None = None) -> list[dict]:
    """Batter board rows (WPA-sorted) from a finalized fold + name/team map.

    The team falls back to the PITCHER name/team map before giving up. The two
    maps come from load_season_hitting / load_season_pitching, which carry their
    own row thresholds, while the leverage fold walks the winProbability feed and
    therefore sees anyone who took a single plate appearance. So a batter can be
    in the fold and absent from the hitting rows: measured 2026-07-31, exactly one
    row (Osleivis Basabe, 1 PA) served a null team for that reason. The pitcher
    map covers the two-way and position-player-pitching cases; anything still
    missing keeps its name and a null team rather than inventing one.
    """
    pit_nt = pit_nt or {}
    batters = []
    for mid, m in bat.items():
        nt = bat_nt.get(mid) or pit_nt.get(mid)
        batters.append({
            "mlbam": mid, "name": m.get("name") or (nt[0] if nt else None),
            "team": nt[1] if nt else None,
            "pa": m.get("pa"), "wpa": m.get("wpa"), "pli": m.get("pli"),
            "clutch": m.get("clutch"), "wpa_li": m.get("wpa_li"),
            "qualified": (m.get("pa") or 0) >= QUAL_PA,
        })
    batters.sort(key=lambda r: (r["wpa"] if r["wpa"] is not None else -99), reverse=True)
    return batters


def _build_starters(strt: dict, pit_nt: dict, pit_gs: Optional[dict]) -> list[dict]:
    """Starter board rows (WPA-sorted); only real starters (GS>0 on the line).

    `pit_gs` None means the season pitching line is UNAVAILABLE, and then this
    does NOT filter - the bullpen_export._active_mlbam_ids posture, where an
    unreachable feed leaves the board intact instead of blanking it.

    Why the sentinel is needed: load_season_pitching returns [] on any failure,
    which used to arrive here as an EMPTY GS map, and an empty map fails the
    `GS > 0` test for every arm, so all 326 starters silently became []. Nothing
    raised, because an empty starter board is a legitimate state (a fold with no
    games in it), so a total source outage and a genuinely empty season published
    the same file. With no GS line we keep every folded starter and serve gs=None
    rather than a fabricated 0."""
    starters = []
    for mid, m in strt.items():
        # filter only when we actually HAVE the season line to filter on
        if pit_gs is not None and pit_gs.get(mid, 0) <= 0:
            continue
        nt = pit_nt.get(mid)
        starters.append({
            "mlbam": mid, "name": m.get("name") or (nt[0] if nt else None),
            "team": nt[1] if nt else None,
            "starts": m.get("starts"), "wpa": m.get("wpa"),
            "wpa_per_start": m.get("wpa_per_start"), "wpa_li": m.get("wpa_li"),
            "gs": pit_gs.get(mid, 0) if pit_gs is not None else None,
            "qualified": (m.get("starts") or 0) >= QUAL_STARTS,
        })
    starters.sort(key=lambda r: (r["wpa"] if r["wpa"] is not None else -99), reverse=True)
    return starters


def _season_boards(season: int, *, leverage_limit: Optional[int] = None, log=print):
    """Load the season name/team maps + fold the winProbability feed once, and
    return (batters, starters, coverage, sources). Cached games make the fold
    free, so a prior season costs one schedule + two statline calls.

    `sources` reports what each input actually delivered (row counts, whether the
    GS filter could run, how many served rows have no team), so a degraded run is
    readable in the payload instead of only in the log."""
    log(f"  leverage: loading {season} name/team maps...")
    hit_rows = load_season_hitting(season)
    pit_rows = load_season_pitching(season)
    bat_nt = _name_team(hit_rows)
    pit_nt = _name_team(pit_rows)
    # None (not {}) when the season pitching line is missing: an empty map would
    # filter EVERY starter off the board. See _build_starters.
    pit_gs: Optional[dict[int, int]] = None
    if pit_rows:
        pit_gs = {}
        for r in pit_rows:
            mid = r.get("mlbam")
            if mid is not None:
                pit_gs[int(mid)] = int(r.get("GS") or 0)
    else:
        _log.warning("leverage %s: season pitching line is EMPTY, so the GS>0 "
                     "starter filter is SKIPPED rather than dropping every "
                     "starter off the board", season)
        log(f"  leverage: no {season} season pitching line; the GS>0 starter "
            f"filter is skipped (feed unavailable, not zero starters)")
    if not hit_rows:
        _log.warning("leverage %s: season hitting line is EMPTY; batter rows keep "
                     "their fold names and serve a null team", season)

    log(f"  leverage: walking winProbability feed ({season}); cached games are free...")
    _rel, bat, strt, cov = mlb_leverage.fetch_season_all_leverage(season, limit=leverage_limit)
    log(f"  leverage: {cov.get('games')}/{cov.get('games_total')} games; "
        f"{len(bat)} batters, {len(strt)} starters folded")
    batters = _build_batters(bat, bat_nt, pit_nt)
    starters = _build_starters(strt, pit_nt, pit_gs)
    # THE SOURCE ROWS BEHIND THIS BOARD, kept so the payload can disclose its own
    # team basis. This module never calls apply_current_team, which reads as "the
    # leverage board is on stats_earned" and is WRONG: its team comes from
    # load_season_hitting / load_season_pitching, both of which apply the remap
    # before returning. Verified against the served data as well as the code, 0
    # of 1,005 leverage rows carry a different team than the same player's row on
    # the bullpen or hitter board. So the page was never mixing two bases; this
    # board simply never said which one it was on.
    src_rows = list(hit_rows) + list(pit_rows)
    n_bat_noteam = sum(1 for b in batters if not b.get("team"))
    n_st_noteam = sum(1 for s in starters if not s.get("team"))
    if n_bat_noteam or n_st_noteam:
        # Never silent: one null team is the known fold-only case (a 1-PA batter
        # absent from the hitting rows), but ALL of them null means the name/team
        # maps failed and the board is serving a teamless leaderboard.
        lvl = (_log.error if (n_bat_noteam >= len(batters) and batters)
               else _log.warning)
        lvl("leverage %s: %d of %d batter rows and %d of %d starter rows resolved "
            "no team", season, n_bat_noteam, len(batters), n_st_noteam, len(starters))
    sources = {
        "n_hitting_rows": len(hit_rows), "n_pitching_rows": len(pit_rows),
        "n_batters_folded": len(bat), "n_starters_folded": len(strt),
        "gs_filter_applied": pit_gs is not None,
        "gs_filter_note": ("Starters are filtered to GS>0 on the season pitching "
                           "line. When that line is unavailable the filter is "
                           "SKIPPED (gs_filter_applied=false) and every folded "
                           "starter is served with gs=null, rather than an empty "
                           "GS map dropping the whole board."),
        "n_batters_no_team": n_bat_noteam, "n_starters_no_team": n_st_noteam,
    }
    return batters, starters, cov, sources, src_rows


def export(season: Optional[int] = None, *, leverage_limit: Optional[int] = None,
           write: bool = True, log=print, today: Optional[str] = None) -> int:
    """Build data/leverage_leaderboards.json and return batters+starters count."""
    season = int(season or date.today().year)
    today = today or date.today().isoformat()

    batters, starters, cov, sources, src_rows = _season_boards(
        season, leverage_limit=leverage_limit, log=log)

    # REFUSE TO PUBLISH EMPTY. This export was the one of the four with no `if not
    # rows` guard at all, so a failed feed wrote a valid-looking file with two
    # empty boards in it and returned 0 as if that were a normal result. Its three
    # siblings all skip the write instead, and so does this now: the previous
    # file stays on disk, which is strictly better than a published blank.
    if not batters and not starters:
        log(f"  leverage: no leverage rows for {season} (feed blocked or empty); "
            f"skipping the write and leaving {OUT_PATH.name} as it is")
        _ingest_red("leverage_leaderboards",
                    (f"{season}: the winProbability fold produced 0 batters and 0 "
                     f"starters; refused to overwrite {OUT_PATH.name} with an "
                     f"empty board."))
        return 0
    # One side empty and the other populated is the partial version of the same
    # failure (an empty GS map used to do exactly that to the starter board), so
    # each block keeps its last good value rather than publishing empty.
    batters, bat_guard = guard_nonempty_block(
        batters, OUT_PATH, key="batters", source="leverage_batters",
        label="leverage", log=log)
    starters, st_guard = guard_nonempty_block(
        starters, OUT_PATH, key="starters", source="leverage_starters",
        label="leverage", log=log)

    payload = {
        "generated_at": today, "season": season, "as_of": today,
        "coverage": cov,
        # What each input delivered this run, and the empty-block guard's verdict
        # for each board, so a degraded run is auditable from the served file.
        "sources": sources,
        "block_guard": {"batters": bat_guard, "starters": st_guard},
        "team_basis": team_basis_meta(basis_rows_for(batters + starters, src_rows),
                                      label="leverage"),
        "note": ("Realized in-game leverage impact, self-computed from the MLB StatsAPI "
                 "winProbability feed (FanGraphs is blocked for autonomous pulls). Batters: "
                 "WPA, average Leverage Index faced (pLI), and Clutch (WPA/pLI minus WPA/LI). "
                 "Starters: per-start WPA and WPA/LI. Descriptive realized value, not a "
                 "predictive model."),
        "batters": batters, "starters": starters,
    }
    n = len(batters) + len(starters)
    log(f"  leverage: {len(batters)} batters ({sum(1 for b in batters if b['qualified'])} qualified), "
        f"{len(starters)} starters")
    if write:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = OUT_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        tmp.replace(OUT_PATH)
        log(f"  leverage: wrote {OUT_PATH.name}")
    return n


def export_history(seasons=None, *, out_path: Optional[Path] = None,
                   write: bool = True, log=print) -> dict:
    """Build data/leverage_history.json - per-season batter + starter leverage
    boards for the /mlbstats/ Leverage yearly-history pills. Every game of these
    seasons is already in the winProbability cache, so the multi-season fold is a
    disk walk (one schedule + two statline calls per season is the only network).
    Only qualified rows are kept (the history board defaults to qualified-only,
    matching the reliever/hitter history files). Best-effort: a season that fails
    to load is logged and skipped, never aborting the run."""
    seasons = list(seasons or HISTORY_SEASONS)
    out_path = out_path or HISTORY_PATH
    hist: dict[str, dict] = {}
    basis_rows: list[dict] = []
    for y in seasons:
        try:
            batters, starters, cov, _src, src_rows = _season_boards(y, log=log)
        except Exception:
            _log.exception("leverage-history: %s failed; skipping", y)
            continue
        batters = [b for b in batters if b["qualified"]]
        starters = [s for s in starters if s["qualified"]]
        basis_rows.extend(basis_rows_for(batters + starters, src_rows))
        if not batters and not starters:
            log(f"  leverage-history: no qualified rows for {y}; skipping")
            continue
        hist[str(y)] = {
            "season": y, "n_batters": len(batters), "n_starters": len(starters),
            "coverage": cov, "batters": batters, "starters": starters,
        }
        log(f"  leverage-history: {y} -> {len(batters)} batters, {len(starters)} starters")
    payload = {
        "generated_at": date.today().isoformat(),
        "seasons": [int(y) for y in hist],
        "note": ("Per-season qualified batter + starter realized-leverage boards for the "
                 "yearly history pills. WPA is realized in-game win-probability impact; pLI "
                 "and Clutch read the leverage of the spots. Descriptive, not predictive."),
        "team_basis": team_basis_meta(basis_rows, label="leverage history",
                                      scope="history"),
        "history": hist,
    }
    if write and hist:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        tmp.replace(out_path)
        log(f"  leverage-history: wrote {out_path.name} ({len(hist)} seasons)")
    return payload


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if len(sys.argv) > 1 and sys.argv[1] == "history":
        _yrs = [int(x) for x in sys.argv[2].split(",")] if len(sys.argv) > 2 else None
        export_history(_yrs, log=print)
    else:
        _season = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else None
        export(_season, log=print)
