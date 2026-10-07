# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""mlbstats_rolling_export - per-player game logs for the /mlbstats/ drawer's
rolling panels (owner ask 18 of 2026-09-30; plan Part 8 item P8.2, task LT-06;
the lane design is part8/league_team_stats.md sections 6.2, 6.3, 7.4 and 8).

WHAT IT WRITES. One small file per player on a live board (hitters, starters,
relievers), `mlbstats_player/<mlbam>.json`, holding RAW per-game counts in game
order, so the page can draw a 15- or 30-game window (5 or 10 starts) with no
refetch and never opens a line on a one-game rate:

    hit  date, pa, ab, h, d, t, hr, bb, hbp, sf, so, pit
    pit  date, gs, bf, outs, so, bb, er, pit, li

A two-way player's file carries both blocks. Beside the directory,
`mlbstats_player_index.json` carries the counts, the corpus built_at, the
frame's covers_through, the boards' last game date, the board reconciliation
and the list of players with a file.

THE FRAME. mlbstats_games.player_game_frame(season), the public per-game frame
(the play corpus, or the cached payloads where no corpus exists, with the
scorer's credits), games ordered by first-play startTime.

THE STALE RULE COMPARES GAME DATES, NEVER BUILD STAMPS. covers_through is the
last game date the frame holds. The boards' last game date is the latest cached
game date on or before the boards' as_of, which is the last game their season
lines can include. The export refuses (keeping the last good files; the page
then says the rolling window is not built) only when covers_through is more
than MAX_LAG_DAYS before the boards' last game date. From the season's end to
Opening Day both dates stop moving, so the panel keeps building all winter even
though the boards' as_of moves every night and the corpus built_at does not; a
build-stamp rule would refuse every night of the off-season.

THE RECONCILIATION. Where the frame covers every game the boards cover, each
player's summed games must equal his board line on plate appearances, batters
faced, starts and outs (measured on 2026: every board player, exactly). More
than BOARD_MISMATCH_SHARE of a board's players off on those refuses the build.
At bats and walks are reported, not gated: an official scoring change made
after a payload was cached moves them by one for a handful of players.

THE FLAG. mlbstats_trends_export.MLBSTATS_DRAWER_LIVE. While it is False every
file goes under .cache/league_teams/preview/ and nothing under data/ changes.
data/mlbstats_player/ is gitignored and shipped by both deploy consumers.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

import mlbstats_games
import mlbstats_trends_export as trends

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
PREVIEW_DIR = trends.PREVIEW_DIR
SHARD_DIR_NAME = "mlbstats_player"
SERVED_DIR = DATA_DIR / "mlbstats_player"
INDEX_NAME = "mlbstats_player_index.json"
SCHEMA = 1
SOURCE = "mlbstats_rolling_export"

HIT_COLS = ["date", "pa", "ab", "h", "d", "t", "hr", "bb", "hbp", "sf", "so", "pit"]
PIT_COLS = ["date", "gs", "bf", "outs", "so", "bb", "er", "pit", "li"]

#: The corpus may trail the boards' last game by this many days and still
#: build (a night's refresh can miss; two cannot).
MAX_LAG_DAYS = 2
#: The share of a board's players allowed off on an exact key (PA, BF, GS,
#: outs) when the frame covers every game the board does.
BOARD_MISMATCH_SHARE = 0.01

#: (board, block, side, {frame key: board key}); the gated keys are exact.
BOARDS = (("hitter_leaderboards", "hitters", "hit", {"pa": "pa", "ab": "ab", "hr": "hr", "bb": "bb"}),
          ("starter_leaderboards", "starters", "pit", {"gs": "gs", "bf": "tbf", "g": "g", "outs": "ip"}),
          ("bullpen_leaderboards", "relievers", "pit", {"bf": "tbf", "g": "g", "outs": "ip"}))
GATED = ("pa", "bf", "gs", "outs")


class Refused(Exception):
    """Nothing is written; the last good files stand."""


def out_dir() -> Path:
    """data/ only once the drawer flag is flipped; the preview directory until then."""
    return DATA_DIR if trends.MLBSTATS_DRAWER_LIVE else PREVIEW_DIR


def _read_json(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def boards(data_dir: Optional[Path] = None) -> dict:
    """{"season", "as_of", "rows": {board: rows}} off the three live boards whose
    players get a file."""
    d = Path(data_dir or DATA_DIR)
    out = {"season": None, "as_of": None, "rows": {}}
    for name, block, _side, _keys in BOARDS:
        blob = _read_json(d / f"{name}.json") or {}
        if blob.get("season") is None:
            continue
        s = int(blob["season"])
        if out["season"] is not None and s != out["season"]:
            raise Refused(f"the live boards disagree on the season ({out['season']} and {s})")
        out["season"] = s
        a = blob.get("as_of")
        if a and (out["as_of"] is None or str(a)[:10] > out["as_of"]):
            out["as_of"] = str(a)[:10]
        out["rows"][name] = blob.get(block) or []
    return out


def boards_last_game_date(as_of: Optional[str], game_dates) -> Optional[str]:
    """The latest game date on or before the boards' as_of: the last game the
    boards' season lines can include. None when no cached game is that early."""
    if not as_of:
        return None
    eligible = [d for d in game_dates if d and d <= str(as_of)[:10]]
    return max(eligible) if eligible else None


def stale_reason(covers_through: Optional[str], boards_last_game: Optional[str],
                 max_lag_days: int = MAX_LAG_DAYS) -> Optional[str]:
    """Why the frame is too far behind the boards to build, or None. Compares
    GAME dates only (never a build stamp)."""
    if not covers_through:
        return "the frame covers no game of the live season"
    if not boards_last_game:
        return None
    lag = (date.fromisoformat(boards_last_game) - date.fromisoformat(covers_through)).days
    if lag > max_lag_days:
        return (f"the frame covers games through {covers_through}, {lag} days before the "
                f"boards' last game on {boards_last_game} (more than {max_lag_days})")
    return None


def board_check(frame, rows_by_board: dict, *, complete: bool) -> dict:
    """Each board player's summed games against his board line."""
    hit = frame.hit.groupby("mlbam")[["pa", "ab", "hr", "bb"]].sum()
    pit = frame.pit.groupby("mlbam")[["gs", "bf", "outs"]].sum()
    pit["g"] = frame.pit.groupby("mlbam").size()
    out = {"complete": bool(complete), "boards": {}}
    for name, _block, side, keys in BOARDS:
        sums = hit if side == "hit" else pit
        rows = rows_by_board.get(name) or []
        blk = {"players": 0, "without_games": 0, "mismatched": {}}
        for r in rows:
            mid = r.get("mlbam")
            if mid is None:
                continue
            blk["players"] += 1
            if int(mid) not in sums.index:
                blk["without_games"] += 1
                continue
            for fk, bk in keys.items():
                bv = r.get(bk)
                if bv is None:
                    continue
                want = int(round(float(bv) * 3)) if fk == "outs" else int(bv)
                if int(sums.loc[int(mid), fk]) != want:
                    blk["mismatched"][fk] = blk["mismatched"].get(fk, 0) + 1
        out["boards"][name] = blk
    return out


def gate_failures(check: dict) -> list:
    """The exact keys whose mismatch share is over BOARD_MISMATCH_SHARE, when
    the frame covers every game the boards do."""
    if not check.get("complete"):
        return []
    bad = []
    for name, blk in check["boards"].items():
        n = max(blk["players"], 1)
        for k in GATED:
            m = blk["mismatched"].get(k, 0)
            if m / n > BOARD_MISMATCH_SHARE:
                bad.append(f"{name} {k}: {m} of {blk['players']}")
    return bad


def _games(df, mlbam: int, cols: list) -> list:
    sub = df[df["mlbam"] == mlbam]
    out = []
    for r in sub[cols].itertuples(index=False):
        row = []
        for c, v in zip(cols, r):
            if c == "date":
                row.append(v)
            elif c == "li":
                row.append(None if v != v else round(float(v), 2))
            else:
                row.append(int(v))
        out.append(row)
    return out


def build(*, data_dir: Optional[Path] = None, frame=None, game_dates=None,
          log: Callable = print) -> tuple[dict, dict]:
    """(index, {mlbam: shard}). Raises Refused."""
    b = boards(data_dir)
    if b["season"] is None:
        raise Refused("no live board carries a season")
    season = b["season"]
    if frame is None:
        frame = mlbstats_games.player_game_frame(season, log=log)
    meta = dict(frame.meta)
    covers = meta.get("covers_through")
    if game_dates is None:
        game_dates = mlbstats_games.season_game_dates(season)
    dates = set(game_dates) | set(frame.hit["date"].dropna()) | set(frame.pit["date"].dropna())
    last = boards_last_game_date(b["as_of"], dates)
    why = stale_reason(covers, last)
    if why:
        raise Refused(why)
    complete = bool(covers and last and covers >= last)
    check = board_check(frame, b["rows"], complete=complete)
    bad = gate_failures(check)
    if bad:
        raise Refused("the frame does not reconcile with the boards: " + "; ".join(bad))

    hitters = {int(r["mlbam"]) for r in b["rows"].get("hitter_leaderboards") or []
               if r.get("mlbam") is not None}
    pitchers = {int(r["mlbam"]) for n in ("starter_leaderboards", "bullpen_leaderboards")
                for r in b["rows"].get(n) or [] if r.get("mlbam") is not None}
    hit_ids = set(frame.hit["mlbam"].astype(int))
    pit_ids = set(frame.pit["mlbam"].astype(int))
    shards: dict = {}
    no_games = 0
    for mid in sorted(hitters | pitchers):
        doc = {"schema": SCHEMA, "mlbam": mid, "season": season, "as_of": b["as_of"],
               "covers_through": covers, "sides": []}
        if mid in hitters and mid in hit_ids:
            doc["hit"] = {"cols": HIT_COLS, "games": _games(frame.hit, mid, HIT_COLS)}
            doc["sides"].append("hit")
        if mid in pitchers and mid in pit_ids:
            doc["pit"] = {"cols": PIT_COLS, "games": _games(frame.pit, mid, PIT_COLS)}
            doc["sides"].append("pit")
        if not doc["sides"]:
            no_games += 1
            continue
        shards[mid] = doc
    if not shards:
        raise Refused("no board player has a game in the frame")
    index = {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "season": season, "as_of": b["as_of"],
        "boards_last_game": last, "covers_through": covers,
        "first_game": meta.get("first_game"),
        "corpus_built_at": meta.get("corpus_built_at"),
        "frame_source": meta.get("source"), "games": meta.get("games"),
        "max_lag_days": MAX_LAG_DAYS,
        "stale_rule": ("refuse only when covers_through is more than max_lag_days before "
                       "the boards' last game date; game dates, never build stamps"),
        "flag": {"MLBSTATS_DRAWER_LIVE": trends.MLBSTATS_DRAWER_LIVE},
        "cols": {"hit": HIT_COLS, "pit": PIT_COLS},
        "order": "games by the first play's startTime; date is the US Eastern calendar day",
        "counts": {"players": len(shards),
                   "hit": sum(1 for s in shards.values() if "hit" in s),
                   "pit": sum(1 for s in shards.values() if "pit" in s),
                   "two_way": sum(1 for s in shards.values() if len(s["sides"]) == 2),
                   "board_players_without_games": no_games},
        "board_check": check,
        "players": {"hit": sorted(m for m, s in shards.items() if "hit" in s),
                    "pit": sorted(m for m, s in shards.items() if "pit" in s)},
    }
    return index, shards


def _write(path: Path, doc: dict) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(doc, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
    try:
        if path.read_bytes() == raw:
            return len(raw)
    except OSError:
        pass
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(raw)
    os.replace(tmp, path)
    return len(raw)


def export(*, write: bool = True, out: Optional[Path] = None,
           data_dir: Optional[Path] = None, frame=None, game_dates=None,
           log: Callable = print) -> dict:
    """Build and write the shards and the index (the index last). A refusal
    writes nothing and the last good files stand. A player who left the boards
    loses his file. Returns a summary dict."""
    t0 = time.time()
    root = Path(out) if out is not None else out_dir()
    shard_dir = root / SHARD_DIR_NAME
    try:
        index, shards = build(data_dir=data_dir, frame=frame, game_dates=game_dates, log=log)
    except Refused as exc:
        log(f"  drawer rolling: {exc}; keeping the last good files")
        return {"out": str(root), "refused": str(exc), "written": False}
    total = 0
    removed = 0
    if write:
        shard_dir.mkdir(parents=True, exist_ok=True)
        for mid, doc in shards.items():
            total += _write(shard_dir / f"{mid}.json", doc)
        keep = {f"{m}.json" for m in shards}
        for p in shard_dir.glob("*.json"):
            if p.name not in keep:
                p.unlink()
                removed += 1
        _write(root / INDEX_NAME, index)
    summary = {"out": str(root), "refused": None, "written": bool(write),
               "players": index["counts"]["players"], "bytes": total, "removed": removed,
               "covers_through": index["covers_through"],
               "boards_last_game": index["boards_last_game"],
               "seconds": round(time.time() - t0, 1)}
    log(f"  drawer rolling: {summary['players']:,} player files ({total:,} bytes), games "
        f"through {summary['covers_through']} against the boards' {summary['boards_last_game']}, "
        f"{summary['seconds']}s, to {shard_dir}")
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    s = export(out=a.out)
    return 1 if s.get("refused") else 0


if __name__ == "__main__":
    raise SystemExit(main())
