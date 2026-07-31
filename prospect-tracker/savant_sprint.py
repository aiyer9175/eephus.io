# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""Baseball Savant Sprint Speed ingest -> data/savant_sprint.json.

WHY THIS EXISTS
    There is no public MiLB tracking data of any kind, so sprint speed is one of
    only TWO measured athletic signals we can join to a player at all (arm
    strength is the other). Everything else on the defensive side is either a
    scout grade or an outcome count.

    It is the second range indicator for the outfield-projection work in
    positional_fit.py. OAA says how many outs a fielder actually made; sprint
    speed says how much ground he can cover. The two disagree precisely where a
    conversion candidate lives, so a range read that leans on only one of them
    cannot tell a slow corner bat with good routes from a burner with bad ones.

WHAT IS AND IS NOT AVAILABLE
    2015+, one season earlier than OAA. One row per PLAYER-SEASON, not per
    position: `position` is the player's primary position, NOT a split, so unlike
    savant_oaa.py this feed carries no within-player-season variation and cannot
    identify a conversion matrix on its own.

    It does cover CATCHERS, who return zero rows on the OAA leaderboard in every
    season, so it is the only Statcast defensive-adjacent feed that sees them.

    min=10 competitive runs keeps roughly 510 to 570 players a season.

GOTCHAS (all measured, all handled here)
    * The parameter is `year`, NOT `season`. Same convention as the arm-strength
      endpoint: `season=` is accepted and SILENTLY IGNORED, so the server returns
      the default (current) year and a loop written with season= produces one
      season of data stamped as twelve. We stamp the year ourselves regardless.
    * `hp_to_1b` is empty on roughly 12% of rows every season, because home to
      first is only clocked on the plays that produce it. Missing, not zero.
    * `position` is empty for true utility players (10 rows in 2015, 1 in 2024).
      The row is still a real speed observation, so we keep it and drop the key.

NETWORK MANNERS
    Identifying User-Agent, >= 1 request/second/host, every response cached to
    .cache/savant_sprint/ as raw CSV, and every failure is soft: a fetch error
    falls back to the cache and, failing that, to an empty list. Nothing here
    raises.

Run:  python savant_sprint.py                 # incremental, uses cache
      python savant_sprint.py --force-last    # refetch only the current season
      python savant_sprint.py --force         # refetch everything
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import functools
import io
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / ".cache" / "savant_sprint"
OUT = DATA_DIR / "savant_sprint.json"

FIRST_SEASON = 2015  # Statcast sprint speed begins here
# `year`, never `season` -- see the docstring gotcha. min is competitive runs.
BASE = "https://baseballsavant.mlb.com/leaderboard/sprint_speed?year={y}&min=10&csv=true"
UA = "eephus.io positional-fit research (arkndjl@gmail.com)"
_MIN_INTERVAL = 1.05  # seconds between requests to baseballsavant.mlb.com
_last_request = [0.0]

# CSV column -> compact key in the payload. Split by type so runs/bolts/age stay
# ints in the JSON instead of picking up a stray .0.
_FLOAT_FIELDS = {
    "sprint_speed": "ft_s",
    "hp_to_1b": "hp1",
}
_INT_FIELDS = {
    "competitive_runs": "runs",
    "bolts": "bolts",
    "age": "age",
}
_TEXT_FIELDS = {
    "position": "pos",
    "team": "team",
}
_FIELD_KEY = {
    "ft_s": "sprint speed, feet per second (30 ft/s is elite, 27 average)",
    "hp1": "home to first, seconds (absent on ~12% of rows)",
    "runs": "competitive runs in the sample",
    "bolts": "runs at 30 ft/s or better",
    "age": "age that season",
    "pos": "primary position, not a split (empty for utility players)",
    "team": "team abbreviation",
}


def current_season(today: _dt.date | None = None) -> int:
    """Latest season worth asking for. Before April there is nothing new yet."""
    d = today or _dt.date.today()
    return d.year if d.month >= 4 else d.year - 1


# --------------------------------------------------------------------- fetch
def _cache_path(year: int) -> Path:
    return CACHE_DIR / f"sprint_{year}.csv"


def _throttle() -> None:
    wait = _MIN_INTERVAL - (time.monotonic() - _last_request[0])
    if wait > 0:
        time.sleep(wait)
    _last_request[0] = time.monotonic()


def fetch_raw(year: int, force: bool = False) -> str:
    """Raw CSV text for one season. Cached; fail-soft to cache/empty."""
    path = _cache_path(year)
    if path.exists() and not force:
        try:
            return path.read_text(encoding="utf-8-sig")
        except OSError:
            pass
    url = BASE.format(y=year)
    try:
        _throttle()
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as resp:
            text = resp.read().decode("utf-8-sig", errors="replace")
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        if path.exists():
            print(f"  [warn] {year} fetch failed ({exc}); using cache")
            try:
                return path.read_text(encoding="utf-8-sig")
            except OSError:
                return ""
        print(f"  [warn] {year} fetch failed ({exc}); no cache, skipping")
        return ""
    if "player_id" not in text.split("\n", 1)[0]:
        # An error page or an empty body. Do not overwrite a good cache with it.
        if path.exists():
            return path.read_text(encoding="utf-8-sig")
        return ""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text


def _num(v):
    try:
        return float(str(v).replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def parse_rows(text: str, year: int) -> list[dict]:
    """CSV text -> normalized rows. `year` is stamped by us (see the gotcha)."""
    if not text.strip():
        return []
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        try:
            mlbam = int(r["player_id"])
        except (KeyError, TypeError, ValueError):
            continue
        row = {"mlbam": mlbam, "season": year,
               "name": (r.get("last_name, first_name") or "").strip()}
        for src, dst in _TEXT_FIELDS.items():
            v = (r.get(src) or "").strip()
            if v:
                row[dst] = v
        for src, dst in _FLOAT_FIELDS.items():
            v = _num(r.get(src))
            if v is not None:
                row[dst] = round(v, 2)
        for src, dst in _INT_FIELDS.items():
            v = _num(r.get(src))
            if v is not None:
                row[dst] = int(v)
        if "ft_s" not in row:
            # No speed means no observation, whatever else the row carries.
            continue
        out.append(row)
    return out


def build(first: int = FIRST_SEASON, last: int | None = None,
          force: bool = False, force_last: bool = False) -> dict:
    last = last or current_season()
    by_player: dict[str, dict] = {}
    names: dict[str, str] = {}
    counts: dict[str, int] = {}
    for year in range(first, last + 1):
        f = force or (force_last and year == last)
        rows = parse_rows(fetch_raw(year, force=f), year)
        counts[str(year)] = len(rows)
        if not rows:
            print(f"  {year}: no rows")
            continue
        for r in rows:
            key = str(r["mlbam"])
            if r.get("name"):
                names[key] = r["name"]
            by_player.setdefault(key, {})[str(year)] = {
                k: v for k, v in r.items()
                if k not in ("mlbam", "season", "name")}
        print(f"  {year}: {len(rows)} players")
    # _meta mirrors savant_arm.json key for key: positional_fit reads the two
    # athletic feeds through the same loader, so they must not drift apart.
    return {
        "_meta": {
            "source": "Baseball Savant sprint_speed leaderboard (min=10 competitive runs)",
            "source_url": BASE,
            "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
            "first_season": first,
            "last_season": last,
            "years": [y for y in range(first, last + 1) if counts.get(str(y))],
            "units": "ft/s",
            "grain": "one row per player-season; pos is primary position, not a split",
            "blind_spots": ["P", "anyone under 10 competitive runs"],
            "field_key": _FIELD_KEY,
            "n_players": len(by_player),
            "n_player_seasons": sum(len(s) for s in by_player.values()),
            "rows_by_season": counts,
        },
        "names": names,
        "by_mlbam": by_player,
    }


# ------------------------------------------------------------ offline access
@functools.lru_cache(maxsize=1)
def _payload() -> dict:
    try:
        return json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"by_mlbam": {}, "names": {}}


def sprint_for(mlbam: int | str, season: int | str | None = None):
    """Offline lookup.

    season given -> {'ft_s':..,'runs':..,'bolts':..,'hp1':..,'pos':..} or None.
    season None  -> {SEASON: {...}} for every season the player was tracked.
    """
    byyr = _payload().get("by_mlbam", {}).get(str(mlbam))
    if not byyr:
        return None if season else {}
    if season:
        return byyr.get(str(season))
    return dict(byyr)


def speed_for(mlbam: int | str, season: int | str):
    """Just the feet-per-second number, which is the indicator callers want."""
    rec = sprint_for(mlbam, season)
    return rec.get("ft_s") if rec else None


def player_name(mlbam: int | str) -> str:
    return _payload().get("names", {}).get(str(mlbam), "")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--first", type=int, default=FIRST_SEASON)
    ap.add_argument("--last", type=int, default=None)
    ap.add_argument("--force", action="store_true", help="refetch every season")
    ap.add_argument("--force-last", action="store_true",
                    help="refetch only the current season (the nightly default)")
    a = ap.parse_args()
    payload = build(a.first, a.last, force=a.force, force_last=a.force_last)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    _payload.cache_clear()
    m = payload["_meta"]
    print(f"wrote {OUT} -- {m['n_players']} players, "
          f"{m['n_player_seasons']} player-seasons, "
          f"{m['first_season']}-{m['last_season']}")


if __name__ == "__main__":
    main()
