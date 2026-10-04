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

Each row also carries `war`, the player's OWN SIDE of eWAR joined by MLBAM id
(batting on the batter board, pitching on the starter board), with the build
stamp that dates it in `ewar_vintage`. Realized impact beside season value: the
reader gets both without leaving the board.

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
                            team_basis_meta, basis_rows_for, _ingest_red,
                            WAR_RATE_MIN_COVERAGE)
from hitter_export import load_season_hitting
# This board carries the eWAR stamp because it carries an eWAR column: the
# stamp and the number it dates always ship together.
from war_source import safe_ewar_vintage as _war_source_vintage

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


def _stamp_war(batters: list[dict], starters: list[dict], season: int) -> dict:
    """eWAR beside the WPA columns (E3), joined by MLBAM id from the SAME side
    map the three player boards read (bullpen_export._side_war_by_season, lru
    cached for the process, so this costs no second WAR read).

    THE SIDE IS THE BOARD'S SIDE: a batter row carries his POSITION-PLAYER eWAR
    and a starter row his PITCHING eWAR, which is what makes a two-way player
    honest on both boards instead of carrying one summed number on each.

    ABSENT IFF NO CELL. The join is the id and the season, nothing else: a row
    the eWAR artifact covers gets its value whatever this board's `pa` or
    `starts` say, because those come from the winProbability fold rather than
    the season line (a null there is a feed shape, not a missing season, and
    blanking a covered player's eWAR beside a GS of 30 would be unreadable).
    The WAR-RATE columns gate on their denominator because they divide by it;
    this one does not divide. A row the artifact does not cover gets no field:
    absent reads as "no eWAR row", while a 0.0 would read as a real
    replacement-level season.

    BOTH REFUSALS ARE DISCLOSED. An unreadable artifact or a failed
    Baseball-Reference read stamps nothing and returns `refused`; coverage below
    bullpen_export.WAR_RATE_MIN_COVERAGE of a board's rows is the degenerate
    fetch score_war_rate refuses on, and that board refuses with it rather than
    printing a handful of numbers beside six hundred blanks. Without this the
    served block read the same for "the artifact was unreadable" and "the season
    is uncovered", and a log line said "joined for 0/659" as if 0 were a
    coverage fact.

    Returns a meta block (per side counts and any refusal), never raises."""
    meta = {"n_batters": 0, "n_starters": 0, "n_batter_rows": len(batters),
            "n_starter_rows": len(starters), "available": False}
    try:
        from bullpen_export import _side_war_by_season
        war_by = _side_war_by_season()
    except Exception as e:   # noqa: BLE001 - best-effort join, never aborts a board
        _log.warning("leverage eWAR unavailable (WAR fetch failed: %s)", e)
        meta["refused"] = f"WAR fetch failed: {e}"
        return meta

    def _join(rows: list[dict], side: str, label: str) -> int:
        cells, n_pool = [], 0
        for r in rows:
            mid = r.get("mlbam")
            if mid is None:
                continue
            n_pool += 1
            try:
                w = ((war_by.get(int(mid)) or {}).get(int(season)) or {}).get(side)
            except (TypeError, ValueError):   # a non-numeric id is one blank row
                continue
            if w is not None:
                cells.append((r, w))
        if not n_pool:
            return 0
        if len(cells) < WAR_RATE_MIN_COVERAGE * n_pool:
            _log.warning("leverage eWAR REFUSED on %s: %d of %d rows covered "
                         "for %s", label, len(cells), n_pool, season)
            meta[f"{label}_refused"] = (
                f"eWAR covered {len(cells)} of {n_pool} {label} "
                f"(floor {WAR_RATE_MIN_COVERAGE:.0%})")
            return 0
        for r, w in cells:
            v = round(float(w), 1)
            r["war"] = 0.0 if v == 0 else v   # the house -0 rule, in the JSON too
        return len(cells)

    meta["n_batters"] = _join(batters, "bat", "batters")
    meta["n_starters"] = _join(starters, "pit", "starters")
    meta["available"] = True
    meta["note"] = ("war is the player's own SIDE of eWAR: batting on the batter "
                    "board, pitching on the starter board. A row the eWAR "
                    "artifact does not cover carries no value, and a board the "
                    "artifact barely covers is refused whole rather than part "
                    "stamped.")
    return meta


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
    # eWAR beside the realized-impact columns (E3). Stamped HERE, on the season
    # boards themselves, so the live payload and every history season carry the
    # same join by the same rule.
    war_meta = _stamp_war(batters, starters, season)
    if war_meta.get("refused"):
        log(f"  leverage: eWAR refused ({war_meta['refused']})")
    else:
        log(f"  leverage: eWAR joined for {war_meta['n_batters']}/{len(batters)} "
            f"batters and {war_meta['n_starters']}/{len(starters)} starters")
        for _side in ("batters", "starters"):
            if war_meta.get(f"{_side}_refused"):
                log(f"  leverage: eWAR refused on {_side} "
                    f"({war_meta[f'{_side}_refused']})")
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
        "gs_filter_note": ("Starters need GS>0 on the season pitching line. "
                           "Without that line the filter is SKIPPED "
                           "(gs_filter_applied=false) and every folded starter "
                           "serves with gs=null."),
        "n_batters_no_team": n_bat_noteam, "n_starters_no_team": n_st_noteam,
        "ewar_join": war_meta,
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

    # THE BUILD STAMP SHIPS IFF THE COLUMN DOES, and the column is read off the
    # SERVED rows rather than off the join's own counters, because a board kept
    # by guard_nonempty_block is last run's rows and carries last run's `war`.
    has_war = any("war" in r for r in batters) or any("war" in r for r in starters)
    ewar_stamp = {"ewar_vintage": _war_source_vintage(as_of=today)} if has_war else {}

    payload = {
        "generated_at": today, "season": season, "as_of": today,
        "coverage": cov,
        # What each input delivered this run, and the empty-block guard's verdict
        # for each board, so a degraded run is auditable from the served file.
        "sources": sources,
        "block_guard": {"batters": bat_guard, "starters": st_guard},
        # WHICH BUILD the eWAR column on these rows comes from, and whether it
        # has fallen behind the frame under it (audit F10-02 / F11-01). Present
        # iff an eWAR column is, on this board as on the others; a refused join
        # stays readable in sources.ewar_join.
        **ewar_stamp,
        "team_basis": team_basis_meta(basis_rows_for(batters + starters, src_rows),
                                      label="leverage"),
        "note": ("Realized in-game leverage impact, computed from the MLB StatsAPI "
                 "winProbability feed (FanGraphs blocks automated pulls). Batters: WPA, "
                 "pLI (average Leverage Index faced), Clutch (WPA/pLI minus WPA/LI). "
                 "Starters: per-start WPA and WPA/LI. Descriptive, not predictive."),
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
    # Same iff as the live board: the stamp dates a column, so it ships only
    # where one of the seasons actually carries one.
    has_war = any("war" in r for y in hist.values()
                  for r in y["batters"] + y["starters"])
    ewar_stamp = ({"ewar_vintage": _war_source_vintage(as_of=date.today().isoformat())}
                  if has_war else {})
    payload = {
        "generated_at": date.today().isoformat(),
        "seasons": [int(y) for y in hist],
        "note": ("Qualified batters and starters by season. WPA: realized win-probability "
                 "impact; pLI and Clutch: the leverage of the spots. Descriptive, not "
                 "predictive."),
        "team_basis": team_basis_meta(basis_rows, label="leverage history",
                                      scope="history"),
        # The history rows carry the same eWAR column as the live board, so
        # they carry the same build stamp: the block ships iff the column does.
        **ewar_stamp,
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
