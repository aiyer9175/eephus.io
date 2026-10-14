# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""mlbstats_trends_export - every player-season index, 2016 to the live season,
for the per-player drawer on /mlbstats/ (owner ask 18 of 2026-09-30, "Show
stat visualizations for each player when clicked on in the MLB Stats module";
plan Part 8 item P8.2, task LT-06; the lane design is
part8/league_team_stats.md sections 6.2, 6.3, 7.4 and 8).

WHAT IT WRITES. One file, `mlbstats_trends.json`: per player, one positional
row per season and family, fetched by the page on the first drawer open only.

    h   [season, hem, pa]            HEM+ and plate appearances
    p   [season, plus, ip, board]    SEM+ (board "sp") or REM+ (board "rp"),
                                     with the season's innings (outs / 3)
    d   [season, dem, inn, pos]      DEM+, fielding innings, primary position
    l   [season, wpa, pa]            batter WPA (the Leverage board)

WHERE EACH SEASON COMES FROM, IN ORDER (the same order league_averages.
index_values reads, so the League tab and the drawer print one number):
  1. the window lab's memoised season panel (.cache/mlbstats_windows/, every
     scored player, 2022 on), read from disk and never rebuilt here;
  2. the live boards, for the live season;
  3. the qualified history payloads (hitter_history.json and its siblings:
     2021 for HEM+, SEM+, REM+ and WPA; 2016 to 2021 for DEM+).
`sources` names the basis of every family and season (for `p`, of each board).
The Leverage board's starters carry no WPA trend here: the design's drawer
(6.2) draws WPA by season for batters, and a starter's drawer reads `p`. Nothing is scored
here: every value is one a board, a history payload or the lab already
computed, rounded the way the board prints it (plus stats to the nearest
whole number).

THE REFUSAL. Where a lab panel and a history payload both carry a player's
season, the two must agree on the index (the history rows are the served
board of that season; the lab rescored the same season with the board's own
scorer). Any disagreement refuses the whole file and keeps the last good one,
because a drawer that prints a different HEM+ from the board beside it is
worse than no drawer. A payload with fewer players than the file on disk for
the same live season is not written either.

THE FLAG. MLBSTATS_DRAWER_LIVE gates the drawer's files (this one and
mlbstats_rolling_export's). While it is False they are written under
.cache/league_teams/preview/ and nothing under data/ changes; the flip is its
own commit.

DISK ONLY. No network request.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

MLBSTATS_DRAWER_LIVE = True

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / ".cache"
PREVIEW_DIR = CACHE_DIR / "league_teams" / "preview"
LAB_DIR = CACHE_DIR / "mlbstats_windows"
OUT_NAME = "mlbstats_trends.json"
SCHEMA = 1
FIRST_SEASON = 2016
SOURCE = "mlbstats_trends_export"

FIELDS = {"h": ["season", "hem", "pa"],
          "p": ["season", "plus", "ip", "board"],
          "d": ["season", "dem", "inn", "pos"],
          "l": ["season", "wpa", "pa"]}

#: (family, history payload, block, index field, first season it covers)
HISTORY = (("h", "hitter_history", "hitters", "hem_plus", 2021),
           ("sp", "starter_history", "starters", "sem_plus", 2021),
           ("rp", "bullpen_history", "relievers", "rem_plus", 2021),
           ("d", "defense_history", "fielders", "dem_plus", 2016),
           ("l", "leverage_history", "batters", "wpa", 2021))

#: (family, live board, block, index field)
BOARDS = (("h", "hitter_leaderboards", "hitters", "hem_plus"),
          ("sp", "starter_leaderboards", "starters", "sem_plus"),
          ("rp", "bullpen_leaderboards", "relievers", "rem_plus"),
          ("d", "defense_leaderboards", "fielders", "dem_plus"),
          ("l", "leverage_leaderboards", "batters", "wpa"))

WPA_TOLERANCE = 0.0005      # both sides print three decimals


class Refused(Exception):
    """The file is not written; the last good one stands."""


def out_dir() -> Path:
    """data/ only once the flag is flipped; the preview directory until then."""
    return DATA_DIR if MLBSTATS_DRAWER_LIVE else PREVIEW_DIR


def _num(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _nearest(v) -> Optional[int]:
    """Plus stats round to the nearest whole number, halves up (house rule)."""
    f = _num(v)
    return None if f is None else int(math.floor(f + 0.5))


def _r(v, nd: int):
    f = _num(v)
    return None if f is None else round(f, nd)


def _read_json(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def lab_panel(season: int, lab_dir: Optional[Path] = None) -> Optional[dict]:
    """The window lab's memoised panel for one season, from disk only."""
    from tools import mlbstats_window_lab as lab
    doc = _read_json(Path(lab_dir or LAB_DIR) / f"panel_{int(season)}_v{lab.SCHEMA}.json")
    if not isinstance(doc, dict) or doc.get("schema") != lab.SCHEMA \
            or doc.get("season") != int(season):
        return None
    return doc


def _history(name: str, block: str, season: int, data_dir: Path) -> list:
    blob = _read_json(data_dir / f"{name}.json") or {}
    return ((blob.get("history") or {}).get(str(int(season))) or {}).get(block) or []


def live_boards(data_dir: Optional[Path] = None) -> dict:
    """{"season", "as_of", "rows": {family: rows}} off the six live boards."""
    d = Path(data_dir or DATA_DIR)
    out = {"season": None, "as_of": None, "rows": {}}
    for fam, name, block, _field in BOARDS:
        blob = _read_json(d / f"{name}.json") or {}
        if blob.get("season") is None:
            continue
        s = int(blob["season"])
        if out["season"] is None or s > out["season"]:
            out["season"] = s
        a = blob.get("as_of")
        if a and (out["as_of"] is None or str(a) > out["as_of"]):
            out["as_of"] = str(a)
        out["rows"][fam] = (s, blob.get(block) or [])
    out["rows"] = {f: rows for f, (s, rows) in out["rows"].items() if s == out["season"]}
    return out


# --------------------------------------------------------------------------- #
# one season's rows per family
# --------------------------------------------------------------------------- #
def _lab_rows(lab: dict) -> dict:
    """{family: {mlbam: row}} off a lab panel, in the payload's positional form
    (without the season, which the caller prepends)."""
    out = {f: {} for f in ("h", "sp", "rp", "d", "l")}
    for mid, r in (lab.get("hit") or {}).items():
        if _num(r.get("hem")) is not None:
            out["h"][int(mid)] = [_nearest(r["hem"]), int(r.get("pa") or 0)]
    for mid, r in (lab.get("pit") or {}).items():
        ip = _r((r.get("outs") or 0) / 3.0, 1)
        if _num(r.get("sem")) is not None:
            out["sp"][int(mid)] = [_nearest(r["sem"]), ip, "sp"]
        if _num(r.get("rem")) is not None:
            out["rp"][int(mid)] = [_nearest(r["rem"]), ip, "rp"]
    for mid, r in (lab.get("dfn") or {}).items():
        if _num(r.get("dem")) is not None:
            out["d"][int(mid)] = [_nearest(r["dem"]), _r(r.get("inn"), 1), r.get("pos")]
    for mid, r in (lab.get("lev_bat") or {}).items():
        if _num(r.get("wpa")) is not None:
            out["l"][int(mid)] = [_r(r["wpa"], 3), int(r.get("pa") or 0)]
    return out


def _board_rows(fam: str, rows: list, field: str) -> dict:
    """{mlbam: row} off history or live-board rows for one family."""
    out = {}
    for r in rows:
        mid = r.get("mlbam")
        v = _num(r.get(field))
        if mid is None or v is None:
            continue
        if fam == "h":
            out[int(mid)] = [_nearest(v), int(r.get("pa") or 0)]
        elif fam in ("sp", "rp"):
            out[int(mid)] = [_nearest(v), _r(r.get("ip"), 1), fam]
        elif fam == "d":
            out[int(mid)] = [_nearest(v), _r(r.get("inn"), 1), r.get("pos")]
        elif fam == "l":
            out[int(mid)] = [_r(v, 3), int(r.get("pa") or 0)]
    return out


def _agree(fam: str, a, b) -> bool:
    if fam == "l":
        return a is not None and b is not None and abs(a - b) <= WPA_TOLERANCE + 1e-9
    return a == b


def build(*, data_dir: Optional[Path] = None, lab_dir: Optional[Path] = None,
          log: Callable = print) -> dict:
    """The payload. Raises Refused on a lab and history disagreement."""
    d = Path(data_dir or DATA_DIR)
    live = live_boards(d)
    if live["season"] is None:
        raise Refused("no live board carries a season")
    live_season = live["season"]
    seasons = list(range(FIRST_SEASON, live_season + 1))
    players: dict = {}
    sources = {f: {} for f in FIELDS}
    check = {"shared": 0, "disagree": 0, "by_family": {}}
    conflicts: list = []

    def put(fam_key: str, season: int, rows: dict) -> None:
        fam = "p" if fam_key in ("sp", "rp") else fam_key
        for mid, row in rows.items():
            players.setdefault(str(mid), {}).setdefault(fam, []).append([season] + row)

    for y in seasons:
        lab = lab_panel(y, lab_dir)
        hist = {}
        for fam, name, block, field, first in HISTORY:
            if y >= first:
                rows = _history(name, block, y, d)
                if rows:
                    hist[fam] = _board_rows(fam, rows, field)
        chosen: dict = {}
        basis: dict = {}
        if lab is not None:
            lr = _lab_rows(lab)
            for fam, rows in lr.items():
                if rows:
                    chosen[fam], basis[fam] = rows, "window lab panel, every scored player"
            # the refusal: a shared (player, season) index must agree
            for fam, hrows in hist.items():
                lrows = lr.get(fam) or {}
                shared = set(hrows) & set(lrows)
                bad = [m for m in shared if not _agree(fam, lrows[m][0], hrows[m][0])]
                c = check["by_family"].setdefault(fam, {"shared": 0, "disagree": 0})
                c["shared"] += len(shared)
                c["disagree"] += len(bad)
                check["shared"] += len(shared)
                check["disagree"] += len(bad)
                for m in sorted(bad)[:5]:
                    conflicts.append(f"{y} {fam} {m}: lab {lrows[m][0]} vs history {hrows[m][0]}")
        if y == live_season:
            for fam, name, block, field in BOARDS:
                if fam in chosen or fam not in live["rows"]:
                    continue
                rows = _board_rows(fam, live["rows"][fam], field)
                if rows:
                    chosen[fam], basis[fam] = rows, f"live {name}, its scored pool"
        for fam, rows in hist.items():
            if fam not in chosen:
                chosen[fam], basis[fam] = rows, "qualified history rows only"
        for fam_key, rows in chosen.items():
            put(fam_key, y, rows)
            if fam_key in ("sp", "rp"):
                sources["p"].setdefault(str(y), {})[fam_key] = basis[fam_key]
            else:
                sources[fam_key][str(y)] = basis[fam_key]
    if conflicts:
        raise Refused(f"{check['disagree']} lab and history disagreements on a shared "
                      f"player-season index, e.g. " + "; ".join(conflicts[:5]))
    for blk in players.values():
        for fam in blk:
            blk[fam].sort(key=lambda r: (r[0], str(r[-1]) if fam == "p" else ""))
    players = {k: players[k] for k in sorted(players, key=int)}
    counts = {fam: sum(len(b.get(fam) or []) for b in players.values()) for fam in FIELDS}
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "as_of": live["as_of"],
        "live_season": live_season,
        "seasons": seasons,
        "flag": {"MLBSTATS_DRAWER_LIVE": MLBSTATS_DRAWER_LIVE},
        "fields": FIELDS,
        "rounding": "plus stats to the nearest whole number; innings to one decimal; WPA to three",
        "sources": sources,
        "check": {"rule": ("where a window lab panel and a history payload both carry a "
                           "player-season, the index must agree, or the file is refused"),
                  **check},
        "counts": {"players": len(players), "rows": counts},
        "players": players,
    }


def _write(path: Path, doc: dict) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(doc, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(raw)
    os.replace(tmp, path)
    return len(raw)


def export(*, write: bool = True, out: Optional[Path] = None,
           data_dir: Optional[Path] = None, lab_dir: Optional[Path] = None,
           log: Callable = print) -> dict:
    """Build and write the file. A refusal keeps the last good file, and a
    payload with fewer players than the file on disk for the same live season
    is not written. Returns a summary dict."""
    t0 = time.time()
    path = Path(out) if out is not None else out_dir() / OUT_NAME
    if path.suffix != ".json":
        path = path / OUT_NAME
    try:
        doc = build(data_dir=data_dir, lab_dir=lab_dir, log=log)
    except Refused as exc:
        log(f"  drawer trends: {exc}; keeping the last good file")
        return {"out": str(path), "refused": str(exc), "written": False}
    prior = _read_json(path)
    if isinstance(prior, dict) and prior.get("live_season") == doc["live_season"] \
            and (prior.get("counts") or {}).get("players", 0) > doc["counts"]["players"]:
        log("  drawer trends: the new file is thinner than the one on disk; kept")
        return {"out": str(path), "refused": "thinner than the last good file",
                "written": False}
    size = _write(path, doc) if write else 0
    summary = {"out": str(path), "refused": None, "written": bool(write), "bytes": size,
               "players": doc["counts"]["players"], "rows": doc["counts"]["rows"],
               "shared_checked": doc["check"]["shared"],
               "seconds": round(time.time() - t0, 1)}
    log(f"  drawer trends: {summary['players']:,} players, {size:,} bytes, "
        f"{summary['shared_checked']:,} lab and history player-seasons agree, "
        f"{summary['seconds']}s, to {path}")
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    s = export(out=a.out)
    return 1 if s.get("refused") else 0


if __name__ == "__main__":
    raise SystemExit(main())
