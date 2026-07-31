# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""Baseball Savant arm strength ingest -> data/savant_arm.json.

WHY THIS EXISTS
    Scouted arm grades are opinions; this leaderboard is a radar reading. Savant
    publishes the average and maximum throw velocity a fielder produced, BROKEN
    OUT BY THE POSITION HE THREW FROM, which is the same within-player-season
    variation the positional-conversion work already leans on in savant_oaa.py.
    An arm that plays at 88 mph from RF and 84 from 2B is a different projection
    problem than one number per player can express, so we keep the split.

    It also gives the amateur/prospect side a professional anchor: a 70-grade arm
    in a report can be checked against the mph distribution the majors actually
    throw at that position.

WHAT IS AND IS NOT AVAILABLE
    Coverage starts in 2020, measured by probing, not assumed. 2015 through 2019
    all return a zero-byte body; this feed is much newer than OAA (2016) because
    it depends on the Hawk-Eye install, not the older Statcast radar.

    There is no arm_c column. Catcher throwing lives on a separate pop-time
    leaderboard, so catchers only appear here when they logged throws at another
    position -- Salvador Perez is in the 2025 file with primary_position=2 and
    every one of his 114 qualifying throws recorded at 1B. Pitchers never appear.

    `team_name` is present in the header but is the literal string "NA" on every
    row in every season, so it is not carried into the payload.

GOTCHAS (all measured, all handled here)
    * THE YEAR PARAM IS `year`, NOT `season`. Passing `season=` is accepted and
      SILENTLY IGNORED: the server returns the default (current) year instead of
      erroring. Measured 2026-07-30 -- `season=2021`, and a request with no year
      param at all, both returned bytes identical to `year=2026`. A loop written
      with `season=` therefore yields ONE year of data stamped as many, and looks
      completely healthy while doing it. Build the URL only through build_url().
    * The `year` column is not in the CSV at all, so the season cannot be read
      back out of the response. We stamp it ourselves from the request.
    * `minThrows=q` and `minThrows=1` return the SAME rows (395 in 2025). Unlike
      the OAA leaderboard there is no hidden qualified/unqualified split to
      choose between, so the documented `q` is kept.

NETWORK MANNERS
    Identifying User-Agent, >= 1 request/second/host, every response cached to
    .cache/savant_arm/ as raw CSV, and every failure is soft: a fetch error falls
    back to the cache and, failing that, to an empty list. A bad year logs and
    the loop continues. Nothing here raises.

Run:  python savant_arm_strength.py                 # incremental, uses cache
      python savant_arm_strength.py --force-last    # refetch only the current season
      python savant_arm_strength.py --force         # refetch everything
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
CACHE_DIR = ROOT / ".cache" / "savant_arm"
OUT = DATA_DIR / "savant_arm.json"

FIRST_SEASON = 2020  # probed: 2015-2019 return an empty body
BASE = ("https://baseballsavant.mlb.com/leaderboard/arm-strength"
        "?type=player&year={y}&minThrows=q&csv=true")
UA = "eephus.io positional-fit research (arkndjl@gmail.com)"
_MIN_INTERVAL = 1.05  # seconds between requests to baseballsavant.mlb.com
_last_request = [0.0]

# CSV column suffix -> our abbreviation. INF and OF are Savant's own rollups of
# the seven fielding positions, not extra positions a player can occupy.
_POS_SUFFIX = {"1b": "1B", "2b": "2B", "3b": "3B", "ss": "SS",
               "lf": "LF", "cf": "CF", "rf": "RF", "inf": "INF", "of": "OF"}
ARM_POSITIONS = ("1B", "2B", "3B", "SS", "LF", "CF", "RF")
ARM_GROUPS = ("INF", "OF")

# primary_position_name is blank for catchers (the one code with no arm column),
# so the numeric code carries the fallback.
_PRIMARY_NAME = {"1": "Pitcher", "2": "Catcher", "3": "First Baseman",
                 "4": "Second Baseman", "5": "Third Baseman", "6": "Shortstop",
                 "7": "Left Fielder", "8": "Center Fielder", "9": "Right Fielder",
                 "10": "Designated Hitter"}


def current_season(today: _dt.date | None = None) -> int:
    """Latest season worth asking for. Before April there is nothing new yet."""
    d = today or _dt.date.today()
    return d.year if d.month >= 4 else d.year - 1


def build_url(year: int) -> str:
    """The one place a season becomes a URL. See the `season=` gotcha above."""
    return BASE.format(y=year)


# --------------------------------------------------------------------- fetch
def _cache_path(year: int) -> Path:
    return CACHE_DIR / f"arm_{year}.csv"


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
    url = build_url(year)
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
        # An error page, a pre-2020 empty body, or a truncated response. Do not
        # overwrite a good cache with it.
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


def _int(v):
    n = _num(v)
    return None if n is None else int(n)


def parse_rows(text: str, year: int) -> list[dict]:
    """CSV text -> normalized rows. `year` is stamped by us (see the gotchas)."""
    if not text.strip():
        return []
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        try:
            mlbam = int(r["player_id"])
        except (KeyError, TypeError, ValueError):
            continue
        code = (r.get("primary_position") or "").strip()
        row = {
            "mlbam": mlbam,
            "season": year,
            "name": (r.get("fielder_name") or "").strip(),
            "primary": ((r.get("primary_position_name") or "").strip()
                        or _PRIMARY_NAME.get(code, "")),
            "primary_code": code,
        }
        v = _num(r.get("arm_overall"))
        if v is not None:
            row["all"] = round(v, 1)
        v = _num(r.get("max_arm_strength"))
        if v is not None:
            row["max"] = round(v, 1)
        n = _int(r.get("total_throws"))
        if n is not None:
            row["n"] = n
        # Per position: velocity only exists where he actually threw, and the
        # throw counts are zero-filled, so both are dropped when empty.
        arm, thr = {}, {}
        for suffix, pos in _POS_SUFFIX.items():
            v = _num(r.get(f"arm_{suffix}"))
            if v is not None:
                arm[pos] = round(v, 1)
            n = _int(r.get(f"total_throws_{suffix}"))
            if n:
                thr[pos] = n
        if arm:
            row["arm"] = arm
        if thr:
            row["thr"] = thr
        if "all" not in row and not arm:
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
            slot = by_player.setdefault(key, {})
            slot[str(year)] = {k: v for k, v in r.items()
                               if k not in ("mlbam", "season", "name")}
        pos_seen = sum(len(r.get("arm", {}) or {}) for r in rows)
        print(f"  {year}: {len(rows)} players, {pos_seen} player-position reads")
    n_pseasons = sum(len(s) for s in by_player.values())
    n_pos = sum(len(v.get("arm", {}) or {})
                for s in by_player.values() for v in s.values())
    return {
        "_meta": {
            "source": "Baseball Savant arm-strength leaderboard (type=player, minThrows=q)",
            "source_url": BASE,
            "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
            "first_season": first,
            "last_season": last,
            "years": [y for y in range(first, last + 1) if counts.get(str(y))],
            "units": "mph",
            "positions": list(ARM_POSITIONS),
            "groups": list(ARM_GROUPS),
            "blind_spots": ["C (throwing lives on the pop-time leaderboard)", "P"],
            "field_key": {"all": "arm_overall average throw velocity",
                          "max": "max_arm_strength",
                          "n": "total throws",
                          "arm": "avg throw velocity by position thrown from",
                          "thr": "throws by position thrown from",
                          "primary": "primary position name",
                          "primary_code": "primary position numeric code"},
            "n_players": len(by_player),
            "n_player_seasons": n_pseasons,
            "n_player_position_reads": n_pos,
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


def arm_for(mlbam: int | str, season: int, pos: str | None = None):
    """Offline lookup.

    pos given  -> avg throw velocity in mph from that position, or None.
    pos None   -> the whole season record {'all','max','n','arm','thr',...} or {}.
    """
    rec = _payload().get("by_mlbam", {}).get(str(mlbam), {}).get(str(season))
    if not rec:
        return None if pos else {}
    if pos:
        return (rec.get("arm") or {}).get(pos.upper())
    return rec


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
    meta = payload["_meta"]
    print(f"wrote {OUT} -- {meta['n_players']} players, "
          f"{meta['n_player_seasons']} player-seasons, "
          f"{meta['n_player_position_reads']} player-position reads, "
          f"{meta['first_season']}-{meta['last_season']}")


if __name__ == "__main__":
    main()
