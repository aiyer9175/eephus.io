#!/usr/bin/env python3
# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""build_pitch_physics - the payload-direct pitch sidecar League Trends reads.

WHAT IT IS. A no-network CLI that flattens ``.cache/win_prob/<pk>.json`` (one
file per game, each a LIST of plays) into two season tables under
``.cache/pbp_physics/<Y>/`` (League Trends plan, section 5.1):

  pitches-<Y>.parquet  one row per ``isPitch`` playEvent: game_pk,
                       at_bat_index, pitch_number, half, inning, batter,
                       pitcher, bat_side, pitch_hand, pitch_type, start_speed,
                       ivb (breaks.breakVerticalInduced), hb
                       (breaks.breakHorizontal), spin (breaks.spinRate), ext
                       (pitchData.extension), zone, call_code, launch_speed,
                       launch_angle and start_time (the game's first-play
                       about.startTime).
  games-<Y>.parquet    one row per game: game_pk, start_time, date (the first
                       play's start on the America/New_York calendar),
                       home_score and away_score (the last play's result), sb
                       and cs, and the game's pitch count.

The physics and batted-ball fields are in the payloads but not in the play
corpus, which is why this is a sidecar and not a corpus column; it never writes
``.cache/pbp_corpus`` (the out directory is refused if it resolves there).

WHO THREW AND SAW EACH PITCH. As in mlbstats_games, a pitch's own
``defense.pitcher`` and ``offense.batter`` name the players (a mid plate
appearance change splits the plate appearance), with ``matchup`` as the
fallback. bat_side and pitch_hand are the plate appearance's ``matchup`` sides.

STOLEN BASES AND CAUGHT STEALING (plan 4.4, ruling R4). Counted from
``runners[].details.eventType``: ``stolen_base_*`` is a stolen base, and
``caught_stealing_*`` and ``pickoff_caught_stealing_*`` are caught stealing.
One count per runner event: a runner who carries several movement entries for
one event (a caught stealing with a throwing error, say) counts once, keyed by
(at bat, runner, event type, playIndex). The play's own result event is never
counted beside its runner entry.

INCREMENTAL, AND COMPLETED SEASONS FROZEN. A season below the live season (the
current year on the US Eastern calendar) is flattened once and then marked
``frozen`` in the manifest; a frozen season is never re-read or rewritten. The
live season is incremental by game_pk: a game is flattened when it is new or
its payload's (size, mtime) moved since the last night, a game whose payload
is gone keeps its rows (the box prunes win_prob under disk pressure), and a
night with nothing new writes nothing at all, manifest included.

THE MANIFEST. ``.cache/pbp_physics/manifest.json`` carries ``covers_through``
(the latest first-play date over every season, America/New_York) and per
season: games, pitches, first_game, covers_through, frozen, built_at.

Nothing here is a model, a rate or a forecast: every column is copied from the
payload or counted from it.

Run:
    python tools/build_pitch_physics.py [--seasons 2018,2019,2021] [--live-season Y]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

import mlbstats_games as G  # noqa: E402  (public sniff_start, game_date, season_index)

CACHE_DIR = ROOT / ".cache"
WIN_PROB_DIR = CACHE_DIR / "win_prob"
OUT_DIR = CACHE_DIR / "pbp_physics"
CORPUS_DIR = CACHE_DIR / "pbp_corpus"

SCHEMA_VERSION = 1

PITCH_COLS = ["game_pk", "at_bat_index", "pitch_number", "half", "inning",
              "batter", "pitcher", "bat_side", "pitch_hand", "pitch_type",
              "start_speed", "ivb", "hb", "spin", "ext", "zone", "call_code",
              "launch_speed", "launch_angle", "start_time"]
GAME_COLS = ["game_pk", "start_time", "date", "home_score", "away_score",
             "sb", "cs", "pitches"]
_FLOAT_COLS = ("start_speed", "ivb", "hb", "spin", "ext", "launch_speed", "launch_angle")
_INT_COLS = ("at_bat_index", "pitch_number", "inning", "zone")

SB_PREFIX = ("stolen_base",)
CS_PREFIX = ("caught_stealing", "pickoff_caught_stealing")

try:
    import orjson as _orjson
except ImportError:                          # pragma: no cover - orjson is optional
    _orjson = None


def _nolog(*_a, **_k) -> None:
    return None


def _loads(raw: bytes):
    return _orjson.loads(raw) if _orjson is not None else json.loads(raw.decode("utf-8"))


def _pid(block) -> Optional[int]:
    v = block.get("id") if isinstance(block, dict) else None
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _code(block) -> Optional[str]:
    return block.get("code") if isinstance(block, dict) else None


# --------------------------------------------------------------------------- #
# one game (pure)
# --------------------------------------------------------------------------- #
def steal_counts(plays: list) -> tuple[int, int]:
    """(stolen bases, caught stealing) from runners[].details.eventType, one
    count per runner event."""
    seen: set = set()
    sb = cs = 0
    for play in plays or ():
        abi = play.get("atBatIndex", (play.get("about") or {}).get("atBatIndex"))
        for r in play.get("runners") or ():
            d = r.get("details") or {}
            et = d.get("eventType") or ""
            if et.startswith(CS_PREFIX):
                kind = "cs"
            elif et.startswith(SB_PREFIX):
                kind = "sb"
            else:
                continue
            key = (abi, _pid(d.get("runner")), et, d.get("playIndex"))
            if key in seen:
                continue
            seen.add(key)
            if kind == "sb":
                sb += 1
            else:
                cs += 1
    return sb, cs


def flatten_game(plays: list, game_pk: int) -> tuple[list, Optional[dict]]:
    """(pitch rows in PITCH_COLS order, the game row or None) for one payload."""
    if isinstance(plays, dict):
        plays = plays.get("winProbability") or []
    start = None
    for play in plays or ():
        st = (play.get("about") or {}).get("startTime")
        if st:
            start = st
            break
    rows: list = []
    home = away = None
    for play in plays or ():
        about = play.get("about") or {}
        abi = play.get("atBatIndex", about.get("atBatIndex"))
        m = play.get("matchup") or {}
        mb, mp = _pid(m.get("batter")), _pid(m.get("pitcher"))
        side, hand = _code(m.get("batSide")), _code(m.get("pitchHand"))
        half, inning = about.get("halfInning"), about.get("inning")
        res = play.get("result") or {}
        if res.get("homeScore") is not None and res.get("awayScore") is not None:
            home, away = res.get("homeScore"), res.get("awayScore")
        for ev in play.get("playEvents") or ():
            if not ev.get("isPitch"):
                continue
            det = ev.get("details") or {}
            pdat = ev.get("pitchData") or {}
            br = pdat.get("breaks") or {}
            hd = ev.get("hitData") or {}
            rows.append([
                int(game_pk), abi, ev.get("pitchNumber"), half, inning,
                _pid((ev.get("offense") or {}).get("batter")) or mb,
                _pid((ev.get("defense") or {}).get("pitcher")) or mp,
                side, hand, _code(det.get("type")),
                pdat.get("startSpeed"), br.get("breakVerticalInduced"),
                br.get("breakHorizontal"), br.get("spinRate"), pdat.get("extension"),
                pdat.get("zone"), _code(det.get("call")),
                hd.get("launchSpeed"), hd.get("launchAngle"), start,
            ])
    if start is None:
        return rows, None
    sb, cs = steal_counts(plays)
    game = {"game_pk": int(game_pk), "start_time": start, "date": G.game_date(start),
            "home_score": home, "away_score": away, "sb": sb, "cs": cs,
            "pitches": len(rows)}
    return rows, game


def pitch_frame(rows: list) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=PITCH_COLS)
    df["game_pk"] = df["game_pk"].astype("int64")
    for c in ("batter", "pitcher"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    for c in _INT_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int16")
    for c in _FLOAT_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("float32")
    for c in ("half", "bat_side", "pitch_hand", "pitch_type", "call_code", "start_time"):
        df[c] = df[c].astype("string")
    return df


def game_frame(games: list) -> pd.DataFrame:
    df = pd.DataFrame(games, columns=GAME_COLS)
    df["game_pk"] = df["game_pk"].astype("int64")
    for c in ("home_score", "away_score"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int16")
    for c in ("sb", "cs", "pitches"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("int32")
    for c in ("start_time", "date"):
        df[c] = df[c].astype("string")
    return df


# --------------------------------------------------------------------------- #
# files
# --------------------------------------------------------------------------- #
def table_path(out_dir: Path, table: str, season: int) -> Path:
    return Path(out_dir) / str(int(season)) / f"{table}-{int(season)}.parquet"


def sources_path(out_dir: Path, season: int) -> Path:
    return Path(out_dir) / str(int(season)) / f"sources-{int(season)}.json"


def manifest_path(out_dir: Path) -> Path:
    return Path(out_dir) / "manifest.json"


def load_manifest(out_dir: Path) -> dict:
    try:
        man = json.loads(manifest_path(out_dir).read_text(encoding="utf-8"))
        if isinstance(man, dict) and man.get("schema_version") == SCHEMA_VERSION:
            return man
    except (OSError, ValueError):
        pass
    return {"schema_version": SCHEMA_VERSION, "built_at": None, "generated_at": None,
            "covers_through": None, "seasons": {}}


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _write_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def _sig(path: Path) -> Optional[list]:
    try:
        st = path.stat()
    except OSError:
        return None
    return [st.st_size, st.st_mtime_ns]


def _guard_out(out_dir: Path) -> None:
    """The sidecar never writes the play corpus."""
    o = Path(out_dir).resolve()
    c = CORPUS_DIR.resolve()
    if o == c or c in o.parents:
        raise SystemExit(f"refused: {o} is the play corpus; the sidecar writes .cache/pbp_physics")


def live_season_default() -> int:
    d = G.game_date(datetime.now(timezone.utc).isoformat())
    return int(d[:4]) if d else datetime.now(timezone.utc).year


# --------------------------------------------------------------------------- #
# the build
# --------------------------------------------------------------------------- #
def _sort(pit: pd.DataFrame, gam: pd.DataFrame) -> tuple:
    order = gam[["game_pk", "start_time"]].rename(columns={"start_time": "_g_start"})
    pit = pit.merge(order, on="game_pk", how="left")
    pit = (pit.sort_values(["_g_start", "game_pk", "at_bat_index"], kind="mergesort")
           .drop(columns="_g_start").reset_index(drop=True))
    gam = gam.sort_values(["start_time", "game_pk"], kind="mergesort").reset_index(drop=True)
    return pit, gam


def build_season(season: int, pks: list, *, win_prob_dir: Path, out_dir: Path,
                 log: Callable = _nolog) -> dict:
    """Flatten one season. Returns {"status", "games", "pitches", "added",
    "covers_through", ...}; writes only when a game was added or moved."""
    season = int(season)
    pit_p, gam_p = table_path(out_dir, "pitches", season), table_path(out_dir, "games", season)
    src_p = sources_path(out_dir, season)
    have = pit_p.exists() and gam_p.exists()
    try:
        known = json.loads(src_p.read_text(encoding="utf-8")) if have else {}
    except (OSError, ValueError):
        known = {}
    old_pit = pd.read_parquet(pit_p) if have else None
    old_gam = pd.read_parquet(gam_p) if have else None
    have_pks = set(int(v) for v in old_gam["game_pk"]) if old_gam is not None else set()

    todo: list = []
    sigs: dict = dict(known)
    for pk in sorted(int(p) for p in pks):
        sig = _sig(win_prob_dir / f"{pk}.json")
        if sig is None:
            continue                       # pruned: its rows (if any) stand
        if pk in have_pks and known.get(str(pk)) == sig:
            continue
        todo.append((pk, sig))

    t0 = time.time()
    new_rows: list = []
    new_games: list = []
    done: list = []
    for pk, sig in todo:
        try:
            plays = _loads((win_prob_dir / f"{pk}.json").read_bytes())
        except (OSError, ValueError):
            continue
        rows, game = flatten_game(plays, pk)
        if game is None:
            continue
        new_rows.extend(rows)
        new_games.append(game)
        done.append(pk)
        sigs[str(pk)] = sig
    if not done:
        n_g = 0 if old_gam is None else len(old_gam)
        n_p = 0 if old_pit is None else len(old_pit)
        cov = None if old_gam is None or not n_g else str(old_gam["date"].max())
        return {"status": "unchanged", "season": season, "games": n_g, "pitches": n_p,
                "added": 0, "covers_through": cov}

    pit_new, gam_new = pitch_frame(new_rows), game_frame(new_games)
    if old_pit is not None:
        gone = set(done)
        pit = pd.concat([old_pit[~old_pit["game_pk"].isin(gone)], pit_new], ignore_index=True)
        gam = pd.concat([old_gam[~old_gam["game_pk"].isin(gone)], gam_new], ignore_index=True)
    else:
        pit, gam = pit_new, gam_new
    pit, gam = _sort(pit, gam)
    _write_parquet(pit, pit_p)
    _write_parquet(gam, gam_p)
    _write_bytes_atomic(src_p, json.dumps(sigs, sort_keys=True, separators=(",", ":")).encode("ascii"))
    added = len([pk for pk in done if pk not in have_pks])
    log(f"  physics: {season} {len(done):,} games flattened ({added:,} new) in "
        f"{round(time.time() - t0, 1)}s; {len(gam):,} games, {len(pit):,} pitches")
    return {"status": "built", "season": season, "games": int(len(gam)),
            "pitches": int(len(pit)), "added": added, "reflattened": len(done) - added,
            "covers_through": str(gam["date"].max()) if len(gam) else None,
            "first_game": str(gam["date"].min()) if len(gam) else None}


def build(*, win_prob_dir: Optional[Path] = None, out_dir: Optional[Path] = None,
          seasons=None, live_season: Optional[int] = None,
          log: Callable = _nolog) -> dict:
    """Build or extend the sidecar. Frozen seasons are skipped untouched; the
    live season is incremental; the manifest is rewritten only when a season
    changed. Returns {"seasons": {Y: result}, "covers_through", "wrote"}."""
    wp = Path(win_prob_dir or WIN_PROB_DIR)
    od = Path(out_dir or OUT_DIR)
    _guard_out(od)
    live = int(live_season or live_season_default())
    man = load_manifest(od)
    blocks = man.setdefault("seasons", {})
    idx = G.season_index(wp, od / "_index", log=log)
    by_season: dict = {}
    for pk, (s, _st) in idx.items():
        if s is not None:
            by_season.setdefault(int(s), []).append(int(pk))
    want = sorted(by_season) if not seasons else sorted(int(s) for s in seasons)
    out: dict = {}
    changed = False
    for s in want:
        blk = blocks.get(str(s)) or {}
        if blk.get("frozen") and table_path(od, "pitches", s).exists() \
                and table_path(od, "games", s).exists():
            out[s] = {"status": "frozen", "season": s, "games": blk.get("games"),
                      "pitches": blk.get("pitches"), "added": 0,
                      "covers_through": blk.get("covers_through")}
            continue
        res = build_season(s, by_season.get(s, []), win_prob_dir=wp, out_dir=od, log=log)
        freeze = s < live and res["games"] > 0
        if res["status"] == "built" or (freeze and not blk.get("frozen")):
            changed = True
            blocks[str(s)] = {
                "games": res["games"], "pitches": res["pitches"],
                "first_game": res.get("first_game", blk.get("first_game")),
                "covers_through": res["covers_through"], "frozen": bool(freeze),
                "built_at": (datetime.now(timezone.utc).isoformat(timespec="seconds")
                             if res["status"] == "built" else blk.get("built_at")),
            }
            if res["status"] == "unchanged" and not blk.get("first_game"):
                g = pd.read_parquet(table_path(od, "games", s), columns=["date"])
                blocks[str(s)]["first_game"] = str(g["date"].min())
        out[s] = res
    covs = [b.get("covers_through") for b in blocks.values() if b.get("covers_through")]
    cov = max(covs) if covs else None
    if changed:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        man.update({"built_at": now, "generated_at": now, "covers_through": cov,
                    "live_season": live, "source_cache": str(wp)})
        _write_bytes_atomic(manifest_path(od),
                            json.dumps(man, indent=1, sort_keys=True).encode("ascii"))
    return {"seasons": out, "covers_through": cov, "wrote": changed}


def main(argv=None) -> int:                 # pragma: no cover - the CLI
    ap = argparse.ArgumentParser(description="Flatten win_prob payloads into the pitch sidecar.")
    ap.add_argument("--seasons", default="", help="comma list; default every cached season")
    ap.add_argument("--live-season", type=int, default=None)
    ap.add_argument("--cache-dir", default=None)
    ap.add_argument("--out-dir", default=None)
    a = ap.parse_args(argv)
    seasons = [int(x) for x in a.seasons.split(",") if x.strip()] or None
    res = build(win_prob_dir=Path(a.cache_dir) if a.cache_dir else None,
                out_dir=Path(a.out_dir) if a.out_dir else None,
                seasons=seasons, live_season=a.live_season, log=print)
    for s, r in sorted(res["seasons"].items()):
        print(f"{s}: {r['status']}, {r['games']} games, {r['pitches']} pitches, "
              f"{r['added']} added, through {r['covers_through']}")
    print(f"covers_through {res['covers_through']}; manifest written: {res['wrote']}")
    return 0


if __name__ == "__main__":                  # pragma: no cover
    raise SystemExit(main())
