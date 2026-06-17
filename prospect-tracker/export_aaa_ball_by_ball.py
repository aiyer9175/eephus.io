"""Export AAA pitch/contact rows from the MLB Stats API game feed.

This builds a TrackMan-ish CSV that can feed `xwoba.py` when enough
in-play rows expose launch data. The Stats API does not provide a single
official "AAA ball-by-ball CSV" endpoint; this script walks the AAA
schedule (`sportId=11`) and parses each `/feed/live` payload.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from datetime import date, timedelta
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import feed_cache


MLB_STATS_API = "https://statsapi.mlb.com/api/v1"
MLB_GAME_FEED_API = "https://statsapi.mlb.com/api/v1.1/game"
AAA_SPORT_ID = 11
CACHE_DIR = Path(__file__).parent / ".cache" / "aaa_ball_by_ball"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

SESSION = requests.Session()
retries = Retry(total=2, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
adapter = HTTPAdapter(max_retries=retries, pool_connections=40, pool_maxsize=40)
SESSION.mount("https://", adapter)
SESSION.mount("http://", adapter)


PLAY_RESULT_MAP = {
    "single": "Single",
    "double": "Double",
    "triple": "Triple",
    "home_run": "HomeRun",
    "field_error": "Error",
    "force_out": "FieldersChoice",
    "fielders_choice": "FieldersChoice",
    "fielders_choice_out": "FieldersChoice",
    "sac_fly": "Sacrifice",
    "sac_bunt": "Sacrifice",
}


def _get_json(url: str, params: dict | None = None, ttl_seconds: int = 86400) -> dict:
    key = requests.Request("GET", url, params=params).prepare().url or url
    safe = hashlib.md5(key.encode("utf-8")).hexdigest()
    path = CACHE_DIR / f"{safe}.json"
    if path.exists() and time.time() - path.stat().st_mtime <= ttl_seconds:
        return json.loads(path.read_text(encoding="utf-8"))
    time.sleep(0.03)
    resp = SESSION.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


def _safe_float(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _schedule_game_pks(start_date: str, end_date: str, limit: int | None = None) -> list[tuple[int, str | None]]:
    """Return (gamePk, 'YYYY-MM-DD') for completed AAA games in the window.

    The game date rides along so callers can hand it to the shared feed
    cache, which gives completed (immutable) games a permanent TTL.
    """
    data = _get_json(
        f"{MLB_STATS_API}/schedule",
        {
            "sportId": str(AAA_SPORT_ID),
            "startDate": start_date,
            "endDate": end_date,
            "gameTypes": "R",
        },
        ttl_seconds=86400,
    )
    pks: list[tuple[int, str | None]] = []
    for day in data.get("dates", []):
        day_date = day.get("date")
        for game in day.get("games", []):
            status = (game.get("status") or {}).get("detailedState", "")
            if status not in {"Final", "Completed Early"}:
                continue
            pks.append((int(game["gamePk"]), game.get("officialDate") or day_date))
            if limit and len(pks) >= limit:
                return pks
    return pks


def _date_windows(start_date: str, end_date: str, days: int = 7):
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    cur = start
    while cur <= end:
        stop = min(end, cur + timedelta(days=days - 1))
        yield cur.isoformat(), stop.isoformat()
        cur = stop + timedelta(days=1)


def _play_result(play: dict, details: dict) -> str:
    event_type = (
        details.get("eventType")
        or (play.get("result") or {}).get("eventType")
        or ""
    )
    return PLAY_RESULT_MAP.get(str(event_type), "Out")


def _tagged_hit_type(hit_data: dict, play: dict, details: dict) -> str:
    trajectory = (hit_data.get("trajectory") or "").title().replace("_", "")
    if trajectory:
        return trajectory
    event_type = (
        details.get("eventType")
        or (play.get("result") or {}).get("eventType")
        or ""
    )
    return str(event_type)


def rows_from_game(game_pk: int, game_date: str | None = None) -> list[dict]:
    data = feed_cache.get_game_feed(game_pk, game_date=game_date)
    game_data = data.get("gameData") or {}
    game_date = (game_data.get("datetime") or {}).get("officialDate")
    venue = game_data.get("venue") or {}
    rows: list[dict] = []
    for play_idx, play in enumerate(data.get("liveData", {}).get("plays", {}).get("allPlays", [])):
        matchup = play.get("matchup") or {}
        batter = matchup.get("batter") or {}
        pitcher = matchup.get("pitcher") or {}
        bat_side = (matchup.get("batSide") or {}).get("code")
        pitch_hand = (matchup.get("pitchHand") or {}).get("code")
        for pitch_idx, event in enumerate(play.get("playEvents", [])):
            if not event.get("isPitch"):
                continue
            details = event.get("details") or {}
            hit_data = event.get("hitData") or {}
            pitch_data = event.get("pitchData") or {}
            coords = hit_data.get("coordinates") or {}
            in_play = bool(hit_data) or bool(details.get("isInPlay"))
            rows.append({
                "GameID": game_pk,
                "Date": game_date,
                "Venue": venue.get("name"),
                "PlayIndex": play_idx,
                "PitchIndex": pitch_idx,
                "BatterId": batter.get("id"),
                "Batter": batter.get("fullName"),
                "PitcherId": pitcher.get("id"),
                "Pitcher": pitcher.get("fullName"),
                "PitchCall": "InPlay" if in_play else (details.get("code") or details.get("description")),
                "PlayResult": _play_result(play, details) if in_play else "",
                "ExitSpeed": _safe_float(hit_data.get("launchSpeed")),
                "Angle": _safe_float(hit_data.get("launchAngle")),
                "Direction": _safe_float(hit_data.get("launchDirection")),
                "Distance": _safe_float(hit_data.get("totalDistance")),
                "HangTime": _safe_float(hit_data.get("hangTime")),
                "CoordX": _safe_float(coords.get("coordX")),
                "CoordY": _safe_float(coords.get("coordY")),
                "BatterSide": bat_side,
                "PitcherThrows": pitch_hand,
                "TaggedHitType": _tagged_hit_type(hit_data, play, details) if in_play else "",
                "PitchType": (details.get("type") or {}).get("code"),
                "PitchTypeName": (details.get("type") or {}).get("description"),
                "StartSpeed": _safe_float(pitch_data.get("startSpeed")),
                "Zone": pitch_data.get("zone"),
                "Description": details.get("description"),
            })
    return rows


def export_csv(start_date: str, end_date: str, output: Path, limit_games: int | None = None) -> int:
    pks: list[tuple[int, str | None]] = []
    remaining = limit_games
    for start, end in _date_windows(start_date, end_date):
        batch = _schedule_game_pks(start, end, limit=remaining)
        pks.extend(batch)
        if remaining is not None:
            remaining = max(0, remaining - len(batch))
            if remaining == 0:
                break
    output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "GameID", "Date", "Venue", "PlayIndex", "PitchIndex",
        "BatterId", "Batter", "PitcherId", "Pitcher",
        "PitchCall", "PlayResult", "ExitSpeed", "Angle", "Direction",
        "Distance", "HangTime", "CoordX", "CoordY", "BatterSide",
        "PitcherThrows", "TaggedHitType", "PitchType", "PitchTypeName",
        "StartSpeed", "Zone", "Description",
    ]
    count = 0
    with output.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for idx, (game_pk, game_date) in enumerate(pks, 1):
            for row in rows_from_game(game_pk, game_date):
                writer.writerow(row)
                count += 1
            if idx % 50 == 0:
                print(f"processed {idx}/{len(pks)} games · {count} rows")
    print(f"wrote {count} rows from {len(pks)} AAA games -> {output}")
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Export AAA ball-by-ball rows from MLB Stats API.")
    parser.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--output", default="data/aaa_ball_by_ball.csv")
    parser.add_argument("--limit-games", type=int, default=None)
    args = parser.parse_args()
    export_csv(args.start_date, args.end_date, Path(args.output), args.limit_games)


if __name__ == "__main__":
    main()
