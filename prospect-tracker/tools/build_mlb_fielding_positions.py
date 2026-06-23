#!/usr/bin/env python3
"""Build data/mlb_fielding_positions.json from MLB StatsAPI fielding splits.

The trade-value engine uses this sidecar to resolve current defensive usage,
surface games-by-position, and apply a small multiposition bonus. The builder
merges MLB identities from the player-page export plus debut/graduation sidecars
so the coverage matches the trade board instead of only the public player pages.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import stats  # noqa: E402

DATA_DIR = ROOT / "data"
OUT = DATA_DIR / "mlb_fielding_positions.json"


def _load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _candidate_rows() -> list[dict]:
    rows_by_key: dict[str, dict] = {}

    detail = _load_json(DATA_DIR / "mlb_player_detail.json") or {}
    for key, row in (detail.get("players") or {}).items():
        mlbam = row.get("mlbam")
        if key and mlbam:
            rows_by_key[str(key)] = {
                "key": str(key),
                "name": row.get("name") or str(key).replace("_", " ").title(),
                "mlbam": int(mlbam),
                "team": row.get("team"),
                "status": "mlb_detail",
            }

    for filename in ("debuts.json", "graduates.json"):
        payload = _load_json(DATA_DIR / filename)
        if payload is None:
            continue
        rows = payload.get("players") if isinstance(payload, dict) else payload
        for row in rows or []:
            key = row.get("player_key")
            mlbam = row.get("mlbam_id") or row.get("mlbam")
            if not key or not mlbam:
                continue
            rows_by_key.setdefault(
                str(key),
                {
                    "key": str(key),
                    "name": row.get("player_name") or str(key).replace("_", " ").title(),
                    "mlbam": int(mlbam),
                    "team": row.get("org"),
                    "status": row.get("status"),
                },
            )

    rows = list(rows_by_key.values())
    rows.sort(key=lambda r: (r.get("name") or "", r["key"]))
    return rows


def _floatish(value) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _fielding_url(mlbam: int, season: int) -> str:
    hydrate = f"stats(group=[fielding],type=season,season={season},sportId=1,gameType=[R])"
    return f"{stats.MLB_STATS_API}/people/{mlbam}?{urlencode({'hydrate': hydrate})}"


def _fetch_one(row: dict, season: int, *, force: bool, ttl: int) -> tuple[str, dict | None, str | None]:
    key = row["key"]
    url = _fielding_url(int(row["mlbam"]), season)
    try:
        resp = stats.requests.get(url, timeout=20, force=force, ttl=ttl)
        data = resp.json()
    except Exception as exc:  # noqa: BLE001 - one player should not fail the artifact
        return key, None, str(exc)

    people = data.get("people") or []
    stat_groups = (people[0].get("stats") or []) if people else []
    positions: dict[str, dict] = {}
    for group in stat_groups:
        for split in group.get("splits") or []:
            stat = split.get("stat") or {}
            pos_info = stat.get("position") or split.get("position") or {}
            pos = (pos_info.get("abbreviation") or "").upper()
            if not pos:
                continue
            games = _floatish(stat.get("gamesPlayed") or stat.get("games"))
            starts = _floatish(stat.get("gamesStarted"))
            innings = _floatish(stat.get("innings"))
            if games <= 0 and starts <= 0 and innings <= 0:
                continue
            prev = positions.get(pos)
            if prev:
                prev["games"] += games
                prev["games_started"] += starts
                prev["innings"] += innings
            else:
                positions[pos] = {
                    "games": games,
                    "games_started": starts,
                    "innings": innings,
                }

    if not positions:
        return key, None, None
    for usage in positions.values():
        usage["games"] = int(usage["games"]) if usage["games"].is_integer() else round(usage["games"], 1)
        usage["games_started"] = (
            int(usage["games_started"])
            if usage["games_started"].is_integer()
            else round(usage["games_started"], 1)
        )
        usage["innings"] = round(usage["innings"], 1)

    return key, {
        "mlbam": row["mlbam"],
        "name": row.get("name"),
        "team": row.get("team"),
        "positions": dict(sorted(positions.items())),
    }, None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=date.today().year)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--limit", type=int, default=0, help="debug cap; 0 = all candidates")
    parser.add_argument("--force", action="store_true", help="bypass StatsAPI cache")
    parser.add_argument("--ttl", type=int, default=24 * 3600)
    args = parser.parse_args()

    candidates = _candidate_rows()
    if args.limit:
        candidates = candidates[: args.limit]

    print(f"fetching MLB fielding positions for {len(candidates)} players, season={args.season} ...")
    started = time.time()
    players: dict[str, dict] = {}
    errors: dict[str, str] = {}
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {
            executor.submit(_fetch_one, row, args.season, force=args.force, ttl=args.ttl): row
            for row in candidates
        }
        for future in as_completed(futures):
            done += 1
            key, entry, error = future.result()
            if entry:
                players[key] = entry
            if error:
                errors[key] = error
            if done % 100 == 0:
                print(f"  {done}/{len(candidates)} ({len(players)} with fielding splits)")

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "season": args.season,
        "source": "MLB StatsAPI people/{mlbam}?hydrate=stats(group=[fielding],type=season,sportId=1,gameType=[R])",
        "candidate_count": len(candidates),
        "count": len(players),
        "error_count": len(errors),
        "players": dict(sorted(players.items())),
    }
    if errors:
        payload["errors"] = dict(sorted(errors.items())[:50])

    OUT.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(
        f"wrote {OUT.relative_to(ROOT)}: {len(players)} players with fielding splits, "
        f"{len(errors)} errors, {time.time() - started:.0f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
