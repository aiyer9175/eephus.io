# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Baseball Savant custom leaderboard: plate-discipline and batted-ball DISPLAY columns.

WHY THIS EXISTS
    The /mlbstats/ Hitter, Starter and Reliever boards carried no plate-discipline
    or contact columns at all, and the Starter board had no SwStr% (the Starter
    record carries none; only the reliever board has a Baseball-Reference one).
    One Savant CSV per side and season returns them for every MLB player,
    keyed by MLBAM id, so the join is exact.

DISPLAY ONLY
    Nothing here feeds HEM+, SEM+, REM+, eWAR, the betting model or any other
    fitted or validated number. Using one of these columns inside a model is a
    model change and needs its own registered attempt.

WHAT IS PINNED
    SELECTIONS is the exact Savant field list requested. COLUMNS maps each served
    key to its Savant field and names its denominator. `linedrives_avg` and
    `oppo_percent` came back empty on the 2026-09-24 probe, so neither is asked
    for. A response whose header lacks any requested field, or whose rows name a
    different season, is REFUSED: it never overwrites a good cache and it joins
    nothing.

    The one derived column is the Starter board's SwStr%:
        swstr_pct = whiff_percent * swing_percent / 10000
    (whiffs per swing times swings per pitch = whiffs per pitch). The reliever
    board keeps its Baseball-Reference SwStr%, which is a different count, so the
    reliever join does not derive it.

NETWORK MANNERS
    One request per side and season, >= 1 second apart, cached raw under
    .cache/savant_custom/. The current season refreshes once a day; a past
    season is final. Every failure is soft: a failed fetch falls back to the
    cache and then to an empty join. Nothing here raises.

Run:  python savant_leaderboards.py [season]     # fetch both sides, print join-ready counts
"""
from __future__ import annotations

import csv
import datetime as _dt
import io
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / ".cache" / "savant_custom"

SOURCE = "Baseball Savant custom leaderboard"
# The exact field list requested, in order. Never add linedrives_avg or
# oppo_percent: both returned empty for every row (2026-09-24 probe).
SELECTIONS = (
    "pa", "whiff_percent", "swing_percent", "oz_swing_percent",
    "iz_contact_percent", "f_strike_percent", "sweet_spot_percent",
    "pull_percent", "fastball_avg_speed",
)
URL = ("https://baseballsavant.mlb.com/leaderboard/custom?year={year}&type={side}"
       "&filter=&min=1&selections={sel}&chart=false&x=pa&y=pa&r=no"
       "&chartType=beeswarm&sort=pa&sortDir=desc&csv=true")
UA = "eephus.io mlbstats display columns (arkndjl@gmail.com)"
LIVE_TTL_S = 24 * 3600
_MIN_INTERVAL = 1.05
_last_request = [0.0]

# served key -> (Savant field, scale, denominator the header names, sides).
# scale 0.01 turns Savant's percent into the board's fraction (fPct renders it).
COLUMNS = {
    "whiff_pct": ("whiff_percent", 0.01, "swings", ("batter", "pitcher")),
    "chase_pct": ("oz_swing_percent", 0.01, "pitches outside the zone", ("batter", "pitcher")),
    "z_contact_pct": ("iz_contact_percent", 0.01, "swings at pitches in the zone", ("batter", "pitcher")),
    "sweet_spot_pct": ("sweet_spot_percent", 0.01, "batted balls", ("batter",)),
    "pull_pct": ("pull_percent", 0.01, "batted balls", ("batter",)),
    "f_strike_pct": ("f_strike_percent", 0.01, "plate appearances", ("pitcher",)),
    "fb_velo": ("fastball_avg_speed", 1.0, "fastballs thrown", ("pitcher",)),
}
# The one derived column and its formula, pinned by test_savant_leaderboards.
DERIVED = {
    "swstr_pct": ("whiff_percent * swing_percent / 10000",
                  "pitches (whiffs per swing times swings per pitch)"),
}


def _throttle() -> None:
    wait = _MIN_INTERVAL - (time.monotonic() - _last_request[0])
    if wait > 0:
        time.sleep(wait)
    _last_request[0] = time.monotonic()


def cache_path(season: int, side: str) -> Path:
    return CACHE_DIR / f"custom_{side}_{int(season)}.csv"


def shape_ok(text: str, season: int) -> bool:
    """True when the CSV carries every requested field and only the asked season.

    Savant has served a season-inert page before (the catcher-framing
    leaderboard ignored its season parameter), so the season is checked on the
    rows, not trusted from the URL."""
    if not text or not text.strip():
        return False
    rdr = csv.DictReader(io.StringIO(text))
    head = set(rdr.fieldnames or ())
    if "player_id" not in head or "year" not in head:
        return False
    if any(f not in head for f in SELECTIONS):
        return False
    n = 0
    for r in rdr:
        if str(r.get("year") or "").strip() != str(int(season)):
            return False
        n += 1
    return n > 0


def fetch_text(season: int, side: str, *, force: bool = False) -> str:
    """Raw CSV text for one side-season, or "" when there is nothing usable."""
    path = cache_path(season, side)
    cached = ""
    if path.exists():
        try:
            cached = path.read_text(encoding="utf-8-sig")
        except OSError:
            cached = ""
    fresh = False
    if cached:
        try:
            fresh = (int(season) < _dt.date.today().year
                     or (time.time() - path.stat().st_mtime) < LIVE_TTL_S)
        except OSError:
            fresh = False
    if cached and fresh and not force and shape_ok(cached, season):
        return cached
    url = URL.format(year=int(season), side=side, sel=",".join(SELECTIONS))
    try:
        _throttle()
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as resp:
            text = resp.read().decode("utf-8-sig", errors="replace")
    except (urllib.error.URLError, OSError, TimeoutError, ValueError) as exc:
        print(f"  [warn] savant custom {side} {season} fetch failed ({exc}); using cache")
        return cached if shape_ok(cached, season) else ""
    if not shape_ok(text, season):
        print(f"  [warn] savant custom {side} {season}: response shape changed; refused")
        return cached if shape_ok(cached, season) else ""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError:
        pass
    return text


def _pct(v) -> Optional[float]:
    try:
        s = str(v).replace("%", "").strip()
        return float(s) if s else None
    except (TypeError, ValueError):
        return None


def parse(text: str) -> dict[int, dict]:
    """CSV text -> {mlbam: {served key: value}}. Empty cells stay absent."""
    out: dict[int, dict] = {}
    if not text:
        return out
    for r in csv.DictReader(io.StringIO(text)):
        try:
            mid = int(r["player_id"])
        except (KeyError, TypeError, ValueError):
            continue
        out[mid] = {f: _pct(r.get(f)) for f in SELECTIONS}
    return out


def _fetched_at(season: int, side: str) -> Optional[str]:
    try:
        ts = cache_path(season, side).stat().st_mtime
    except OSError:
        return None
    return _dt.datetime.fromtimestamp(ts).isoformat(timespec="seconds")


def join(rows: list[dict], season: int, side: str, *, derive_swstr: bool = False,
         loader: Optional[Callable[[int, str], str]] = None) -> dict:
    """Stamp the Savant display columns onto board rows by `mlbam`.

    Returns the provenance block the payload serves under `savant_custom`.
    `loader(season, side)` supplies the CSV text (tests pass one); the default
    is fetch_text. A key is written only when Savant has a value for it."""
    text = (loader or fetch_text)(int(season), side)
    raw = parse(text)
    keys = [k for k, spec in COLUMNS.items() if side in spec[3]]
    if derive_swstr:
        keys.append("swstr_pct")
    n = nq = qual = 0
    for r in rows:
        if r.get("qualified"):
            qual += 1
        mid = r.get("mlbam")
        try:
            src = raw.get(int(mid)) if mid is not None else None
        except (TypeError, ValueError):
            src = None
        if not src:
            continue
        hit = False
        for k, (field, scale, _den, sides) in COLUMNS.items():
            if side not in sides:
                continue
            v = src.get(field)
            if v is None:
                continue
            r[k] = round(v * scale, 4) if scale != 1.0 else round(v, 1)
            hit = True
        if derive_swstr:
            w, s = src.get("whiff_percent"), src.get("swing_percent")
            if w is not None and s is not None:
                r["swstr_pct"] = round(w * s / 10000.0, 4)
                hit = True
        if hit:
            n += 1
            if r.get("qualified"):
                nq += 1
    cols = {k: {"field": COLUMNS[k][0], "per": COLUMNS[k][2]} for k in keys if k in COLUMNS}
    if derive_swstr:
        cols["swstr_pct"] = {"formula": DERIVED["swstr_pct"][0], "per": DERIVED["swstr_pct"][1]}
    return {
        "available": bool(raw),
        "source": SOURCE,
        "source_url": URL.format(year=int(season), side=side, sel=",".join(SELECTIONS)),
        "season": int(season),
        "side": side,
        "fetched_at": _fetched_at(int(season), side) if loader is None else None,
        "n_source_rows": len(raw),
        "n_board": len(rows),
        "n_joined": n,
        "n_qualified": qual,
        "n_qualified_joined": nq,
        "columns": cols,
        "use": "display only; no model reads these columns",
    }


def main(argv: list[str]) -> int:
    season = int(argv[1]) if len(argv) > 1 else _dt.date.today().year
    for side in ("batter", "pitcher"):
        text = fetch_text(season, side, force=True)
        print(f"  {side} {season}: {len(parse(text))} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
