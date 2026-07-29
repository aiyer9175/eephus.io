# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""Baseball Savant Outs Above Average ingest -> data/savant_oaa.json.

WHY THIS EXISTS
    The positional-conversion model needs a per-POSITION fielding read, not a
    per-player one. Savant's OAA leaderboard exposes a `pos=` parameter that
    returns one row per (player, position, season); querying all eight defensive
    codes gives WITHIN-player-season observations at two or more positions, which
    is the identifying variation a conversion matrix is fit on.

    DRS is proprietary (Sports Info Solutions) and both FanGraphs and
    Baseball-Reference refuse scripted clients, so OAA plus the Baseball-Reference
    defensive runs already on disk (data/mlb_def_history.json) are the sanctioned
    substrate.

WHAT IS AND IS NOT AVAILABLE
    Catcher (pos=2) returns ZERO rows every year -- catcher framing/blocking is a
    different Savant leaderboard and did not answer probes. Pitchers and DH have
    no OAA. So this file covers 1B, 2B, 3B, SS, LF, CF, RF only.

GOTCHAS (both measured, both handled here)
    * With `min=q` the `year` column comes back EMPTY. `split=yes` populates it.
      We stamp the year ourselves regardless.
    * `min=q` (qualified) returns roughly half the rows of `min=1`. We use min=1.

NETWORK MANNERS
    Identifying User-Agent, >= 1 request/second/host, every response cached to
    .cache/savant_oaa/ as raw CSV, and every failure is soft: a fetch error falls
    back to the cache and, failing that, to an empty list. Nothing here raises.

Run:  python savant_oaa.py                 # incremental, uses cache
      python savant_oaa.py --force-last    # refetch only the current season
      python savant_oaa.py --force         # refetch everything
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
CACHE_DIR = ROOT / ".cache" / "savant_oaa"
OUT = DATA_DIR / "savant_oaa.json"

FIRST_SEASON = 2016  # Statcast OAA begins here
BASE = ("https://baseballsavant.mlb.com/leaderboard/outs_above_average"
        "?type=Fielder&startYear={y}&endYear={y}&split=yes&team=&range=year"
        "&min=1&pos={pos}&roles=&viz=hide&csv=true")
UA = "eephus.io positional-fit research (arkndjl@gmail.com)"
_MIN_INTERVAL = 1.05  # seconds between requests to baseballsavant.mlb.com
_last_request = [0.0]

# Savant position codes -> our abbreviations. 2 (C) is queried for completeness
# and is expected to return zero rows; keeping it documents the blind spot.
POS_CODE = {2: "C", 3: "1B", 4: "2B", 5: "3B", 6: "SS", 7: "LF", 8: "CF", 9: "RF"}
OAA_POSITIONS = ("1B", "2B", "3B", "SS", "LF", "CF", "RF")

# CSV column -> compact key in the payload.
_FIELDS = {
    "outs_above_average": "oaa",
    "fielding_runs_prevented": "frp",
    "outs_above_average_infront": "in",
    "outs_above_average_behind": "bk",
    "outs_above_average_lateral_toward3bline": "l3",
    "outs_above_average_lateral_toward1bline": "l1",
    "outs_above_average_rhh": "rhh",
    "outs_above_average_lhh": "lhh",
}
_RATE_FIELDS = {
    "actual_success_rate_formatted": "sr_act",
    "adj_estimated_success_rate_formatted": "sr_exp",
}


def current_season(today: _dt.date | None = None) -> int:
    """Latest season worth asking for. Before April there is nothing new yet."""
    d = today or _dt.date.today()
    return d.year if d.month >= 4 else d.year - 1


# --------------------------------------------------------------------- fetch
def _cache_path(year: int, code: int) -> Path:
    return CACHE_DIR / f"oaa_{year}_pos{code}.csv"


def _throttle() -> None:
    wait = _MIN_INTERVAL - (time.monotonic() - _last_request[0])
    if wait > 0:
        time.sleep(wait)
    _last_request[0] = time.monotonic()


def fetch_raw(year: int, code: int, force: bool = False) -> str:
    """Raw CSV text for one (season, position). Cached; fail-soft to cache/empty."""
    path = _cache_path(year, code)
    if path.exists() and not force:
        try:
            return path.read_text(encoding="utf-8-sig")
        except OSError:
            pass
    url = BASE.format(y=year, pos=code)
    try:
        _throttle()
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as resp:
            text = resp.read().decode("utf-8-sig", errors="replace")
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        if path.exists():
            print(f"  [warn] {year} pos{code} fetch failed ({exc}); using cache")
            try:
                return path.read_text(encoding="utf-8-sig")
            except OSError:
                return ""
        print(f"  [warn] {year} pos{code} fetch failed ({exc}); no cache, skipping")
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


def parse_rows(text: str, year: int, pos: str) -> list[dict]:
    """CSV text -> normalized rows. `year` is stamped by us (see module docstring)."""
    if not text.strip():
        return []
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        try:
            mlbam = int(r["player_id"])
        except (KeyError, TypeError, ValueError):
            continue
        row = {"mlbam": mlbam, "season": year, "pos": pos,
               "name": (r.get("last_name, first_name") or "").strip(),
               "primary_pos": (r.get("primary_pos_formatted") or "").strip()}
        for src, dst in _FIELDS.items():
            v = _num(r.get(src))
            if v is not None:
                row[dst] = v
        for src, dst in _RATE_FIELDS.items():
            v = _num(r.get(src))
            if v is not None:
                row[dst] = round(v / 100.0, 4)
        if "oaa" not in row and "frp" not in row:
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
        for code, pos in POS_CODE.items():
            rows = parse_rows(fetch_raw(year, code, force=f), year, pos)
            counts[f"{year}:{pos}"] = len(rows)
            for r in rows:
                key = str(r["mlbam"])
                if r.get("name"):
                    names[key] = r["name"]
                slot = by_player.setdefault(key, {})
                slot.setdefault(str(year), {})[pos] = {
                    k: (round(v, 4) if isinstance(v, float) else v)
                    for k, v in r.items()
                    if k not in ("mlbam", "season", "pos", "name", "primary_pos")}
                if r.get("primary_pos"):
                    slot[str(year)].setdefault("_primary", r["primary_pos"])
        print(f"  {year}: " + " ".join(
            f"{p}={counts[f'{year}:{p}']}" for p in POS_CODE.values()))
    n_rows = sum(1 for s in by_player.values() for v in s.values()
                 for k in v if not k.startswith("_"))
    n_pseasons = sum(len(s) for s in by_player.values())
    return {
        "generated_from": "Baseball Savant outs_above_average leaderboard (min=1, split=yes, per pos=)",
        "generated_at": _dt.date.today().isoformat(),
        "first_season": first,
        "last_season": last,
        "positions": list(OAA_POSITIONS),
        "blind_spots": ["C (leaderboard returns zero rows)", "DH", "P"],
        "field_key": {"oaa": "outs above average", "frp": "fielding runs prevented",
                      "in": "infront", "bk": "behind", "l3": "lateral toward 3B line",
                      "l1": "lateral toward 1B line", "rhh": "vs RHH", "lhh": "vs LHH",
                      "sr_act": "actual success rate", "sr_exp": "adj estimated success rate"},
        "n_players": len(by_player),
        "n_player_seasons": n_pseasons,
        "n_player_position_seasons": n_rows,
        "rows_by_season_pos": counts,
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


def oaa_for(mlbam: int | str, season: int, pos: str | None = None):
    """Offline lookup.

    pos given  -> {'oaa':..,'frp':..,directional splits} or None.
    pos None   -> {POS: {...}} for every position the player fielded that season
                  (the '_primary' bookkeeping key is stripped).
    """
    rec = _payload().get("by_mlbam", {}).get(str(mlbam), {}).get(str(season))
    if not rec:
        return None if pos else {}
    if pos:
        return rec.get(pos)
    return {k: v for k, v in rec.items() if not k.startswith("_")}


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
    print(f"wrote {OUT} -- {payload['n_players']} players, "
          f"{payload['n_player_position_seasons']} player-season records, "
          f"{payload['first_season']}-{payload['last_season']}")


if __name__ == "__main__":
    main()
