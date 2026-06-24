# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""Game-centric pitch extraction from the MLB Stats API playByPlay feed.

For every game in the manifest, fetch the play-by-play once and emit:
  - one pitch row per isPitch event (call code, pre-pitch count, zone/coords
    where tracked, swing/contact/whiff flags derivable at every level)
  - one PA row per play (event type, is_pa flag, pitch counts) so plate
    appearance reconstruction does not depend on pitch completeness.

Resumable: done gamePks are logged per level-season; shards are append-only.
"""
from __future__ import annotations

import argparse
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (
    API_BASE, DATA_RAW, NON_PA_EVENT_TYPES, SWING_CODES, WHIFF_CODES,
    CONTACT_CODES, FOUL_CODES, INPLAY_CODES, get_json, log_run, make_session,
)

PITCH_DIR = DATA_RAW / "pitches_v2"  # v2: adds stringer pixel coords x/y
SHARD_GAMES = 400
WORKERS = 12

_tls = threading.local()


def thread_session():
    if not hasattr(_tls, "session"):
        _tls.session = make_session()
    return _tls.session


def parse_game(game: dict) -> tuple[list[dict], list[dict]]:
    gamePk = int(game["gamePk"])
    data = get_json(thread_session(), f"{API_BASE}/game/{gamePk}/playByPlay", timeout=45)
    plays = data.get("allPlays", [])
    pitch_rows: list[dict] = []
    pa_rows: list[dict] = []
    base = {
        "gamePk": gamePk,
        "season": int(game["season"]),
        "level": game["level"],
        "date": game["date"],
    }
    for play in plays:
        play_idx = play.get("atBatIndex", -1)
        matchup = play.get("matchup", {})
        batter_id = matchup.get("batter", {}).get("id")
        result = play.get("result", {})
        event_type = result.get("eventType") or ""
        is_pa = event_type not in NON_PA_EVENT_TYPES and bool(event_type)
        events = play.get("playEvents", [])
        pitch_events = [e for e in events if e.get("isPitch")]
        pa_rows.append({
            **base,
            "play_idx": play_idx,
            "inning": play.get("about", {}).get("inning"),
            "half": play.get("about", {}).get("halfInning"),
            "batter_id": batter_id,
            "batter_name": matchup.get("batter", {}).get("fullName"),
            "bat_side": matchup.get("batSide", {}).get("code"),
            "pitcher_id": matchup.get("pitcher", {}).get("id"),
            "pitch_hand": matchup.get("pitchHand", {}).get("code"),
            "event_type": event_type,
            "is_pa": is_pa,
            "n_pitches": len(pitch_events),
        })
        balls, strikes = 0, 0
        pitch_of_pa = 0
        for e in events:
            cnt = e.get("count") or {}
            if e.get("isPitch"):
                pitch_of_pa += 1
                det = e.get("details", {})
                pdata = e.get("pitchData", {}) or {}
                coords = pdata.get("coordinates") or {}
                code = det.get("code") or ""
                pitch_rows.append({
                    **base,
                    "play_idx": play_idx,
                    "pitch_of_pa": pitch_of_pa,
                    "batter_id": batter_id,
                    "bat_side": matchup.get("batSide", {}).get("code"),
                    "pitcher_id": matchup.get("pitcher", {}).get("id"),
                    "pitch_hand": matchup.get("pitchHand", {}).get("code"),
                    "pre_balls": balls,
                    "pre_strikes": strikes,
                    "code": code,
                    "is_swing": code in SWING_CODES,
                    "is_whiff": code in WHIFF_CODES,
                    "is_contact": code in CONTACT_CODES,
                    "is_foul": code in FOUL_CODES,
                    "is_inplay": code in INPLAY_CODES,
                    "is_called_strike": code == "C",
                    "zone": pdata.get("zone"),
                    "px": coords.get("pX"),
                    "pz": coords.get("pZ"),
                    # stringer pixel coords: present at every level, every pitch
                    "sx": coords.get("x"),
                    "sy": coords.get("y"),
                    "sz_top": pdata.get("strikeZoneTop"),
                    "sz_bot": pdata.get("strikeZoneBottom"),
                    "pitch_type": (det.get("type") or {}).get("code"),
                })
            # post-event count becomes pre-count of the next pitch
            # (handles automatic balls/strikes from clock violations too)
            if "balls" in cnt:
                balls = cnt.get("balls", balls)
                strikes = cnt.get("strikes", strikes)
        # tag the final pitch of each PA with the PA outcome
        if pitch_events and pitch_rows:
            pitch_rows[-1]["pa_event_type"] = event_type
            pitch_rows[-1]["is_last_pitch"] = True
    return pitch_rows, pa_rows


def flush(pitch_buf: list[dict], pa_buf: list[dict], out_dir: Path, seq: int) -> int:
    if not pitch_buf and not pa_buf:
        return seq
    stamp = f"{int(time.time())}_{seq:04d}"
    if pitch_buf:
        df = pd.DataFrame(pitch_buf)
        if "pa_event_type" not in df.columns:
            df["pa_event_type"] = None
        if "is_last_pitch" not in df.columns:
            df["is_last_pitch"] = False
        df["is_last_pitch"] = df["is_last_pitch"].fillna(False).astype(bool)
        df.to_parquet(out_dir / f"pitches_{stamp}.parquet", index=False)
    if pa_buf:
        pd.DataFrame(pa_buf).to_parquet(out_dir / f"pa_{stamp}.parquet", index=False)
    return seq + 1


def run_level_season(manifest: pd.DataFrame, season: int, level: str) -> None:
    games = manifest[(manifest.season == season) & (manifest.level == level)]
    if games.empty:
        return
    safe = level.replace("+", "plus")
    out_dir = PITCH_DIR / f"{season}_{safe}"
    out_dir.mkdir(parents=True, exist_ok=True)
    done_path = out_dir / "done.txt"
    fail_path = out_dir / "failed.txt"
    done: set[int] = set()
    if done_path.exists():
        done = {int(x) for x in done_path.read_text().split() if x.strip()}
    todo = [row._asdict() for row in games.itertuples(index=False) if int(row.gamePk) not in done]
    if not todo:
        print(f"{season} {level}: already complete ({len(done)} games)", flush=True)
        return
    print(f"{season} {level}: {len(todo)} games to extract ({len(done)} done)", flush=True)

    pitch_buf: list[dict] = []
    pa_buf: list[dict] = []
    seq = 0
    n_done_this_run = 0
    t0 = time.time()
    done_f = open(done_path, "a")
    fail_f = open(fail_path, "a")
    try:
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futures = {ex.submit(parse_game, g): g for g in todo}
            for fut in as_completed(futures):
                g = futures[fut]
                try:
                    pr, par = fut.result()
                    pitch_buf.extend(pr)
                    pa_buf.extend(par)
                    done_f.write(f"{g['gamePk']}\n")
                except Exception as e:  # noqa: BLE001
                    fail_f.write(f"{g['gamePk']}\t{e}\n")
                n_done_this_run += 1
                if n_done_this_run % SHARD_GAMES == 0:
                    seq = flush(pitch_buf, pa_buf, out_dir, seq)
                    pitch_buf, pa_buf = [], []
                    done_f.flush()
                    rate = n_done_this_run / (time.time() - t0)
                    eta_min = (len(todo) - n_done_this_run) / max(rate, 0.1) / 60
                    print(f"  {season} {level}: {n_done_this_run}/{len(todo)} "
                          f"({rate:.1f} g/s, ETA {eta_min:.0f}m)", flush=True)
        flush(pitch_buf, pa_buf, out_dir, seq)
    finally:
        done_f.close()
        fail_f.close()
    dt = time.time() - t0
    print(f"{season} {level}: DONE {n_done_this_run} games in {dt/60:.1f}m", flush=True)
    log_run("pitch_extract_v1", season=season, level=level,
            n_games=n_done_this_run, minutes=round(dt / 60, 1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", type=int, nargs="+",
                    default=[2025, 2026, 2024, 2023, 2022, 2021])
    ap.add_argument("--levels", nargs="+",
                    default=["AAA", "MLB", "AA", "A+", "A", "CPX"])
    args = ap.parse_args()

    manifest = pd.read_parquet(DATA_RAW / "game_manifest" / "game_manifest.parquet")
    for season in args.seasons:
        for level in args.levels:
            run_level_season(manifest, season, level)
    print("ALL EXTRACTION COMPLETE", flush=True)


if __name__ == "__main__":
    main()
