# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""League-wide innings-by-position from StatsAPI -> data/fielding_innings.json.

OAA and fielding_runs_prevented are COUNTING stats. Turning them into a rate that
a conversion model can move between positions needs the exposure denominator, and
the only complete one is defensive innings at that specific position.

One request per season returns every (player, position) split for the whole
league, joins to MLBAM at 100%, and is per-SEASON rather than per-career, which is
what an as-of-date model needs:

  https://statsapi.mlb.com/api/v1/stats?stats=season&group=fielding
      &season=YYYY&sportId=1&playerPool=All&limit=6000

NOTE ON INNINGS FORMAT: StatsAPI reports innings in baseball notation, where
".1" means one third and ".2" means two thirds. 12.2 innings is 12 + 2/3, NOT
12.2. Converted here once, at ingest.

Run:  python fielding_innings.py [--first 2016] [--last YYYY] [--force-last]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import functools
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / ".cache" / "statsapi_field"
OUT = DATA_DIR / "fielding_innings.json"

FIRST_SEASON = 2000
URL = ("https://statsapi.mlb.com/api/v1/stats?stats=season&group=fielding"
       "&season={y}&sportId=1&playerPool=All&limit=6000")
UA = "eephus.io positional-fit research (arkndjl@gmail.com)"
_MIN_INTERVAL = 1.05
_last_request = [0.0]


def innings_to_float(v) -> float:
    """'132.2' -> 132.667. Baseball thirds, not decimals."""
    if v in (None, ""):
        return 0.0
    s = str(v).strip()
    try:
        whole, _, frac = s.partition(".")
        base = float(whole or 0)
        if frac == "1":
            return base + 1.0 / 3.0
        if frac == "2":
            return base + 2.0 / 3.0
        return float(s)
    except ValueError:
        return 0.0


def _throttle() -> None:
    wait = _MIN_INTERVAL - (time.monotonic() - _last_request[0])
    if wait > 0:
        time.sleep(wait)
    _last_request[0] = time.monotonic()


def fetch_season(year: int, force: bool = False) -> dict:
    """Raw StatsAPI doc for one season. Cached; fail-soft."""
    path = CACHE_DIR / f"fld_{year}.json"
    if path.exists() and not force:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    try:
        _throttle()
        req = urllib.request.Request(URL.format(y=year), headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=90) as resp:
            doc = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, TimeoutError, ValueError) as exc:
        if path.exists():
            print(f"  [warn] {year} fetch failed ({exc}); using cache")
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return {}
        print(f"  [warn] {year} fetch failed ({exc}); no cache, skipping")
        return {}
    if not doc.get("stats"):
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")
    return doc


def parse_season(doc: dict) -> dict:
    """-> {mlbam(str): {POS: {'g','gs','inn'}}}"""
    out: dict[str, dict] = {}
    for block in doc.get("stats", []):
        for sp in block.get("splits", []):
            try:
                mid = str(sp["player"]["id"])
                pos = sp["position"]["abbreviation"]
            except (KeyError, TypeError):
                continue
            st = sp.get("stat", {})
            slot = out.setdefault(mid, {}).setdefault(
                pos, {"g": 0, "gs": 0, "inn": 0.0})
            slot["g"] += int(st.get("games") or st.get("gamesPlayed") or 0)
            slot["gs"] += int(st.get("gamesStarted") or 0)
            slot["inn"] += innings_to_float(st.get("innings"))
    for byp in out.values():
        for v in byp.values():
            v["inn"] = round(v["inn"], 1)
    return out


def build(first: int = FIRST_SEASON, last: int | None = None,
          force: bool = False, force_last: bool = False) -> dict:
    last = last or (_dt.date.today().year if _dt.date.today().month >= 4
                    else _dt.date.today().year - 1)
    seasons = {}
    for y in range(first, last + 1):
        d = parse_season(fetch_season(y, force=force or (force_last and y == last)))
        if d:
            seasons[str(y)] = d
        print(f"  {y}: {len(d)} players, "
              f"{sum(len(v) for v in d.values())} player-position rows")
    return {
        "generated_from": "MLB StatsAPI /api/v1/stats?stats=season&group=fielding (sportId=1, playerPool=All)",
        "generated_at": _dt.date.today().isoformat(),
        "first_season": first,
        "last_season": last,
        "innings_note": "innings converted from baseball thirds (.1=1/3, .2=2/3) to decimal at ingest",
        "n_seasons": len(seasons),
        "seasons": seasons,
    }


@functools.lru_cache(maxsize=1)
def _payload() -> dict:
    try:
        return json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"seasons": {}}


def innings_for(mlbam: int | str, season: int, pos: str | None = None):
    """Offline lookup: {POS: {'g','gs','inn'}} or, with pos, the innings float."""
    rec = _payload().get("seasons", {}).get(str(season), {}).get(str(mlbam), {})
    if pos is None:
        return rec
    return float((rec.get(pos) or {}).get("inn", 0.0))


def primary_position(mlbam: int | str, season: int, exclude_dh: bool = True) -> str | None:
    """Most-innings defensive position that season (games break ties for DH)."""
    rec = innings_for(mlbam, season)
    cand = {p: v for p, v in rec.items()
            if p != "P" and not (exclude_dh and p == "DH")}
    if not cand:
        return None
    return max(cand.items(), key=lambda kv: (kv[1]["inn"], kv[1]["g"]))[0]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--first", type=int, default=FIRST_SEASON)
    ap.add_argument("--last", type=int, default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--force-last", action="store_true")
    a = ap.parse_args()
    payload = build(a.first, a.last, force=a.force, force_last=a.force_last)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    _payload.cache_clear()
    print(f"wrote {OUT} -- {payload['n_seasons']} seasons "
          f"{payload['first_season']}-{payload['last_season']}")


if __name__ == "__main__":
    main()
