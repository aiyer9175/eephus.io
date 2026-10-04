# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""StatsAPI people for one MLB season (bats, throws, birth date, primary
position), cached under .cache/mlb_people/people_<Y>.json.

WHY THIS EXISTS (owner ask 13, 2026-09-30; Part 8 lane league_team_stats,
sections 2 and 8). The League Averages filters split players by their OWN
hand (bats L / R / S, throws L / R), and the season stat lines carry no hand.
The one bulk source is /api/v1/sports/1/players?season=Y, the call
hitter_export.load_bat_side already makes for the live season and keeps for
nothing. This module makes the same call for any season and caches it.

NOT A SERVED INPUT. Nothing on the site reads this module in the patch that
added it; hitter_export.load_bat_side keeps its own live call unchanged.

COVERAGE GATE. A people feed is checked against the season's panel: the
StatsAPI season lines with playerPool=All (.cache/fa_statsapi_{hitting,
pitching}_<Y>.json, read from disk, never fetched here). A hitting row is
covered when its player carries a batSide code, a pitching row when he carries
a pitchHand code. For a COMPLETE season the file is written once and kept, so
a feed covering under MIN_PANEL_COVERAGE (90 percent) of the panel rows, or a
season with no panel on disk to check against, raises Refused and writes
nothing. The live season is refetched daily; a short or unverifiable live feed
is still written and files a red ingest row.

CACHE POLICY. The TTL rule is mlb_team_season's: complete from November 1 of
the season's year, a complete fetch never expires (force=True refetches), a
live one expires after a day. hands() reads disk only and raises NotCached.

Every network read files one row into the ingest-health ledger through
bullpen_export.record_ingest under the source name `mlb_people`.

Usage:
    python mlb_people.py --seasons 2000 2026
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from mlb_team_season import (Refused, NotCached, _default_record, _write_atomic,
                             is_fresh, request_url, season_complete, statsapi_get)

ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / ".cache" / "mlb_people"
PANEL_DIR = ROOT / ".cache"

SOURCE = "mlb_people"
SCHEMA = 1
FIRST_SEASON = 2000
MIN_PANEL_COVERAGE = 0.90
COLUMNS = ("id", "name", "bats", "throws", "birth_date", "pos")

__all__ = ["load", "hands", "panel_rows", "coverage", "parse_people",
           "cache_path", "Refused", "NotCached", "MIN_PANEL_COVERAGE"]


def request_for(season: int) -> tuple[str, dict]:
    return "sports/1/players", {"season": int(season)}


def cache_path(season: int, cache_dir: Optional[Path] = None) -> Path:
    return Path(cache_dir if cache_dir is not None else CACHE_DIR) / f"people_{int(season)}.json"


def parse_people(blob: dict) -> list[list]:
    """[[id, name, bats, throws, birth_date, pos], ...] in COLUMNS order, one
    per person with an id. Refused when the feed holds nobody."""
    people = (blob or {}).get("people") or []
    rows: list[list] = []
    seen: set = set()
    for p in people:
        pid = p.get("id")
        if pid is None:
            continue
        pid = int(pid)
        if pid in seen:
            continue
        seen.add(pid)
        rows.append([
            pid,
            p.get("fullName"),
            (p.get("batSide") or {}).get("code") or None,
            (p.get("pitchHand") or {}).get("code") or None,
            p.get("birthDate") or None,
            (p.get("primaryPosition") or {}).get("abbreviation") or None,
        ])
    if not rows:
        raise Refused(f"people feed holds {len(people)} people and no usable id")
    return rows


def panel_rows(season: int, panel_dir: Optional[Path] = None) -> Optional[dict]:
    """{"hitting": [mlbam per row], "pitching": [mlbam per row]} from the
    season-line caches, or None when either file is absent or unreadable.
    Disk only."""
    d = Path(panel_dir if panel_dir is not None else PANEL_DIR)
    out: dict = {}
    for group in ("hitting", "pitching"):
        try:
            raw = json.loads((d / f"fa_statsapi_{group}_{int(season)}.json")
                             .read_text(encoding="utf-8"))
            splits = ((raw.get("stats") or [{}])[0].get("splits")) or []
        except (OSError, ValueError, AttributeError, IndexError):
            return None
        ids = [int((s.get("player") or {}).get("id")) for s in splits
               if (s.get("player") or {}).get("id") is not None]
        if not ids:
            return None
        out[group] = ids
    return out


def coverage(rows: list[list], panel: dict) -> dict:
    """How many panel rows the feed gives a hand: hitting rows need bats,
    pitching rows need throws."""
    bats = {r[0] for r in rows if r[2]}
    throws = {r[0] for r in rows if r[3]}
    hit = panel.get("hitting") or []
    pit = panel.get("pitching") or []
    hit_ok = sum(1 for i in hit if i in bats)
    pit_ok = sum(1 for i in pit if i in throws)
    n = len(hit) + len(pit)
    return {"hit_rows": len(hit), "hit_with_bats": hit_ok,
            "pit_rows": len(pit), "pit_with_throws": pit_ok,
            "rows": n, "covered": hit_ok + pit_ok,
            "share": round((hit_ok + pit_ok) / n, 4) if n else None}


def _read_doc(season: int, cache_dir: Optional[Path]) -> Optional[dict]:
    try:
        doc = json.loads(cache_path(season, cache_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if doc.get("schema") != SCHEMA or doc.get("season") != int(season):
        return None
    return doc


def load(season: int, *, force: bool = False, cache_dir: Optional[Path] = None,
         panel_dir: Optional[Path] = None, panel: Optional[dict] = None,
         today: Optional[date] = None, now: Optional[float] = None,
         http_get: Optional[Callable[[str, dict], dict]] = None,
         record: Optional[Callable[..., None]] = None) -> dict:
    """The people document for one season: the cache while fresh, else one
    fetch, checked against the season's panel (see COVERAGE GATE). `panel`
    overrides the disk read (a test seam)."""
    season = int(season)
    if season < FIRST_SEASON:
        raise ValueError(f"season {season} precedes FIRST_SEASON {FIRST_SEASON}")
    record = record or _default_record
    if not force:
        doc = _read_doc(season, cache_dir)
        if doc is not None and is_fresh(doc, now):
            return doc
    complete = season_complete(season, today)
    path, params = request_for(season)
    try:
        try:
            blob = (http_get or statsapi_get)(path, params)
        except Exception as exc:         # noqa: BLE001 - any transport failure is a refusal
            raise Refused(f"{season}: people fetch failed ({exc})") from exc
        rows = parse_people(blob)
        pnl = panel if panel is not None else panel_rows(season, panel_dir)
        cov = coverage(rows, pnl) if pnl else None
        if cov is not None and not cov["rows"]:
            cov = None
        short = cov is None or cov["share"] < MIN_PANEL_COVERAGE
        why = ("no panel on disk to check the feed against" if cov is None else
               f"the feed gives a hand to {cov['covered']} of {cov['rows']} panel rows "
               f"({cov['share']:.1%}), under the {MIN_PANEL_COVERAGE:.0%} floor")
        if short and complete:
            raise Refused(f"{season}: {why}")
    except Refused as exc:
        record(SOURCE, ok=False, n_rows=0, message=str(exc))
        raise
    stamp = datetime.fromtimestamp(now if now is not None else time.time(),
                                   tz=timezone.utc).isoformat(timespec="seconds")
    doc = {
        "schema": SCHEMA, "season": season, "fetched_at": stamp,
        "complete": complete, "url": request_url(path, params),
        "n_people": len(rows), "coverage": cov,
        "columns": list(COLUMNS), "rows": rows,
    }
    _write_atomic(cache_path(season, cache_dir), json.dumps(doc, separators=(",", ":")) + "\n")
    if short:
        record(SOURCE, ok=False, n_rows=len(rows), message=f"{season} (live): {why}")
    else:
        record(SOURCE, ok=True, n_rows=len(rows),
               message=f"{season} {'complete' if complete else 'live'}: "
                       f"{cov['covered']} of {cov['rows']} panel rows carry a hand",
               import_fallback=False)
    return doc


def hands(season: int, cache_dir: Optional[Path] = None) -> dict:
    """{mlbam: {"bats": code, "throws": code}} from the cache. NotCached when
    absent; never the network."""
    doc = _read_doc(season, cache_dir)
    if doc is None:
        raise NotCached(f"no cached people for {season} at {cache_path(season, cache_dir)}")
    i = {c: n for n, c in enumerate(doc["columns"])}
    return {r[i["id"]]: {"bats": r[i["bats"]], "throws": r[i["throws"]]} for r in doc["rows"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--seasons", nargs=2, type=int, metavar=("FIRST", "LAST"),
                    required=True)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--cache-dir", type=Path, default=None)
    args = ap.parse_args(argv)
    bad = 0
    for y in range(args.seasons[0], args.seasons[1] + 1):
        try:
            doc = load(y, force=args.force, cache_dir=args.cache_dir)
        except Refused as exc:
            bad += 1
            print(f"{y} REFUSED {exc}")
            continue
        cov = doc.get("coverage") or {}
        print(f"{y} ok complete={doc['complete']} people={doc['n_people']} "
              f"panel_rows={cov.get('rows')} covered={cov.get('covered')} "
              f"share={cov.get('share')} fetched_at={doc['fetched_at']}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
