# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Which MLB players StatsAPI lists as retired (owner answer Q3, 2026-10-22,
'Drop MLB-listed retirees').

StatsAPI's person record carries `active`; a player who has left the game reads
active = false with his lastPlayedDate (Clayton Kershaw: active false, last played
2025-09-28). The projections universe is every player with a recent MLB season,
so a retiree was still projected and still counted in his old club's Team
Outlook (Kershaw: 5Y 0.4 WAR with LAD). A player counts as retired here when
StatsAPI lists him inactive AND he has not played in the current season, so a
record flipped mid-season never removes a player who is on a field this year.

The status of every candidate is cached at .cache/mlb_people_status/status.json and
refreshed once a week per player in batches of 150 ids. A failed fetch keeps the
cache; with no cache at all nothing is dropped (the export never invents a
retirement)."""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

log = logging.getLogger(__name__)

CACHE_PATH = Path(__file__).parent / ".cache" / "mlb_people_status" / "status.json"
URL = "https://statsapi.mlb.com/api/v1/people"
TTL_DAYS = 7
BATCH = 150


def load(path: Path | None = None) -> dict[str, dict]:
    """The cached status rows, {mlbam: {active, lastPlayedDate, fetched}}."""
    p = Path(path or CACHE_PATH)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(rows: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(rows, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, path)


def refresh(mlbams, *, path: Path | None = None, now: float | None = None,
            ttl_days: int = TTL_DAYS) -> dict[str, dict]:
    """Fetch the status of every id whose cached row is missing or older than
    ttl_days, write the cache, and return it. Network failures are logged and
    the cache is returned as it stands."""
    p = Path(path or CACHE_PATH)
    rows = load(p)
    now = time.time() if now is None else now

    def _stale(m: int) -> bool:
        row = rows.get(str(m))
        return row is None or now - float(row.get("fetched") or 0) > ttl_days * 86400

    stale = sorted({int(m) for m in mlbams if m is not None and _stale(int(m))})
    if not stale:
        return rows
    try:
        import requests
        for i in range(0, len(stale), BATCH):
            chunk = stale[i:i + BATCH]
            r = requests.get(URL, params={"personIds": ",".join(map(str, chunk)),
                                          "fields": "people,id,active,lastPlayedDate"},
                             timeout=30)
            r.raise_for_status()
            for person in r.json().get("people") or []:
                rows[str(int(person["id"]))] = {
                    "active": bool(person.get("active")),
                    "lastPlayedDate": person.get("lastPlayedDate"),
                    "fetched": now,
                }
    except Exception:                                          # noqa: BLE001
        log.warning("mlb_people_status: StatsAPI status fetch failed; the cache stands",
                    exc_info=True)
    try:
        _save(rows, p)
    except OSError:
        log.warning("mlb_people_status: cache not written", exc_info=True)
    return rows


def retired_mlbams(rows: dict[str, dict], season: int) -> set[int]:
    """Ids StatsAPI lists inactive who have not played in `season`."""
    out = set()
    for k, v in (rows or {}).items():
        if not v or v.get("active") is not False:
            continue
        last = str(v.get("lastPlayedDate") or "")
        if last[:4].isdigit() and int(last[:4]) >= season:
            continue
        out.add(int(k))
    return out
