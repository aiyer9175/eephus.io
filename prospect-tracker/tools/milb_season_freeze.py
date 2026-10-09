# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Freeze and pin the 2026 MiLB season inputs (task SG_1; the efv2026 plan's N2 and N3,
the surrogate gate draft's precondition Q2 and its section 11 pins). Reads no outcome.

WHY. The 2026 season lines live in .cache/milb_stats/ (gitignored, a 20-hour TTL on the
current season, milb_history._SEASON_TTL_SEC), so a registered 2026 read could not be
reproduced once the cache moves. This tool writes, from the cache, with no fetch:

  data/milb_season_frozen/2026/{hitting,pitching}_{11,12,13,14,16}.json
        byte-for-byte copies of the ten 2026 AAA to rookie season files, after each file's
        row count and PA or BF total match the 2026-09-30 refetch (EXPECTED_2026);
  data/milb_season_frozen/2026/mlb_event_ids_{hitting,pitching}.json
        ONLY the sorted person ids with a 2026 regular-season MLB (sport 1) line: the
        debut event, no stat column of the reserved 2026 debut cohort;
  data/efv_surrogate_pins_2026.json
        sha256, rows, exposure and cache mtime of each frozen file; the event-id files'
        sha256 and counts and a hash over the source files' id column; the season dates;
        a canonical content hash per transfer-season file (2010 to 2019, 2021 to 2025;
        sport 1 as ids only); the transaction-feed months 2026-07 to 2026-09;
  data/milb_norms_2026_pure.json
        the pure 2026 level norms per side and level, from the FROZEN copy, with
        milb_history.level_norms_from_rows (the qualifier and median league_norms uses)
        and NO current-year blend, beside the blend the served path reads today.

The canonical hash projects each row onto HASH_FIELDS (every field league_norms reads is in
it), sorts by (person id, sport, league) with the projected row as the tiebreak, and hashes
the compact JSON, so it is the same on any box whatever the cache file's bytes or line
endings. test_milb_season_freeze.py recomputes it from the cache with fetch=False and fails
on drift, and re-hashes the frozen copy.

Run:
    python tools/milb_season_freeze.py --check    # verify, write nothing
    python tools/milb_season_freeze.py --write    # write the files above
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import milb_history as mh  # noqa: E402

DATA_DIR = ROOT / "data"
FROZEN_DIR = DATA_DIR / "milb_season_frozen" / "2026"
PINS_PATH = DATA_DIR / "efv_surrogate_pins_2026.json"
NORMS_PATH = DATA_DIR / "milb_norms_2026_pure.json"
TX_DIR = ROOT / ".cache" / "mlb_transactions"

SCHEMA = 1
SEASON = 2026
GROUPS = ("hitting", "pitching")
FROZEN_SPORTS = (11, 12, 13, 14, 16)
LEVELS = ("AAA", "AA", "A+", "A", "CPX", "DSL")

#: (sport, group): (rows, PA or BF total) of the 2026-09-30 refetch, which matched the
#: cache fetched 2026-09-27 key for key (efv2026 lane refetch_compare.json).
EXPECTED_2026 = {
    (11, "hitting"): (927, 171799), (11, "pitching"): (1268, 171799),
    (12, "hitting"): (830, 156270), (12, "pitching"): (1044, 156270),
    (13, "hitting"): (837, 151429), (13, "pitching"): (1090, 151429),
    (14, "hitting"): (979, 151705), (14, "pitching"): (1328, 151705),
    (16, "hitting"): (1602, 163736), (16, "pitching"): (2062, 163736),
}

#: Last scheduled regular-season dates, 2026. Sport level: StatsAPI /api/v1/seasons
#: (fetched 2026-09-30). The rookie leagues by league: the regular-season schedule's last
#: final game (fetched 2026-09-30), since the sport-16 season row carries the DSL's date.
SEASON_DATES_2026 = {
    "source": ("StatsAPI /api/v1/seasons?sportId=<id>&season=2026 and, for the sport-16 "
               "leagues, /api/v1/schedule?sportId=16 regular season, both fetched "
               "2026-09-30 by the efv2026 lane (statsapi_seasons_2026.json, "
               "schedule_compare.json)"),
    "by_sport": {
        "1": {"level": "MLB", "start": "2026-03-25", "end": "2026-09-27"},
        "11": {"level": "AAA", "start": "2026-03-27", "end": "2026-09-20"},
        "12": {"level": "AA", "start": "2026-04-02", "end": "2026-09-13"},
        "13": {"level": "A+", "start": "2026-04-02", "end": "2026-09-06"},
        "14": {"level": "A", "start": "2026-04-02", "end": "2026-09-06"},
        "16": {"level": "rookie", "start": "2026-05-02", "end": "2026-08-18"},
    },
    "by_league_sport16": {
        "ACL": {"start": "2026-05-02", "end": "2026-07-23"},
        "FCL": {"start": "2026-05-02", "end": "2026-07-23"},
        "DSL": {"start": "2026-06-01", "end": "2026-08-18"},
    },
}

TRANSFER_SEASONS = tuple(range(2010, 2020)) + tuple(range(2021, 2026))
TRANSFER_SPORTS = (11, 12, 13, 14, 15, 16)

#: (pinned name, cache row key). Sport comes from the file name, never the row.
HASH_FIELDS = (
    ("id", "mlbam"), ("level", "level"), ("league", "league"),
    ("pa", "pa"), ("bf", "bf"), ("ab", "ab"), ("h", "h"), ("2b", "doubles"),
    ("3b", "triples"), ("hr", "hr"), ("bb", "bb"), ("so", "so"), ("hbp", "hbp"),
    ("sf", "sf"), ("ip", "ip"), ("g", "g"), ("gs", "gs"), ("age", "age"),
    ("avg", "avg"), ("obp", "obp"), ("slg", "slg"), ("ops", "ops"), ("era", "era"),
)

#: The transaction-feed months SG_1 completed in the cache (the efv2026 lane's refetch
#: copies; the cache had ended at 2026-07-24).
TX_MONTHS = ("2026_07", "2026_08", "2026_09")


class FreezeError(RuntimeError):
    pass


def _no_fetch(url):
    raise FreezeError(f"milb_season_freeze never fetches: {url}")


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _compact(obj) -> bytes:
    return json.dumps(obj, separators=(",", ":"), sort_keys=True,
                      ensure_ascii=True).encode("utf-8")


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def cache_path(group: str, sport: int, season: int) -> Path:
    return mh.CACHE_DIR / f"{group}_{sport}_{season}.json"


def frozen_path(group: str, sport: int) -> Path:
    return FROZEN_DIR / f"{group}_{sport}.json"


def event_ids_path(group: str) -> Path:
    return FROZEN_DIR / f"mlb_event_ids_{group}.json"


def exposure(rows: list[dict], group: str) -> float:
    key = "pa" if group == "hitting" else "bf"
    return sum(_num(r.get(key)) for r in rows)


def canonical_rows(rows: list[dict], sport: int) -> list[list]:
    """Rows projected onto HASH_FIELDS with the sport inserted after the id, sorted by
    (person id, sport, league) and then by the projected row."""
    out = []
    for r in rows:
        proj = [r.get(k) for _, k in HASH_FIELDS]
        proj.insert(1, int(sport))
        out.append(proj)
    out.sort(key=lambda p: (p[0] if isinstance(p[0], int) else -1, p[1],
                            str(p[3] or ""), _compact(p)))
    return out


def canonical_hash(rows: list[dict], sport: int) -> str:
    return _sha(_compact(canonical_rows(rows, sport)))


def id_column(rows: list[dict]) -> list[int]:
    """The id column, sorted, duplicates kept (a player with two lines appears twice)."""
    return sorted(int(r["mlbam"]) for r in rows if r.get("mlbam") is not None)


def id_column_hash(rows: list[dict]) -> str:
    return _sha(_compact(id_column(rows)))


def read_cache(sport: int, season: int, group: str) -> list[dict]:
    """One cached season file through milb_history.season_splits with fetch=False (the
    sport-16 DSL / CPX level re-derived on read, as every consumer sees it)."""
    saved = mh._fetch
    mh._fetch = _no_fetch
    try:
        return mh.season_splits(sport, season, group, fetch=False)
    finally:
        mh._fetch = saved


def read_frozen(group: str, sport: int) -> list[dict]:
    rows = json.loads(frozen_path(group, sport).read_text(encoding="utf-8"))
    return mh._relevel(rows, sport)


def check_2026_cache() -> list[str]:
    """Problems with the ten 2026 cache files against EXPECTED_2026 (empty when clean)."""
    bad = []
    for (sport, group), (n, expo) in sorted(EXPECTED_2026.items()):
        p = cache_path(group, sport, SEASON)
        if not p.exists():
            bad.append(f"{p.name}: missing")
            continue
        rows = json.loads(p.read_text(encoding="utf-8"))
        got = (len(rows), exposure(rows, group))
        if got != (n, float(expo)):
            bad.append(f"{p.name}: rows {got[0]} exposure {got[1]:.0f}, expected {n} / {expo}")
    return bad


def transfer_hashes() -> dict:
    """{season: {group: {sport: {rows, sha256 | id_sha256}}}} over the transfer seasons.
    Sport 1 is hashed over its id column only; sport 15 only where its file is non-empty."""
    out: dict = {}
    for season in TRANSFER_SEASONS:
        for group in GROUPS:
            cell = out.setdefault(str(season), {}).setdefault(group, {})
            rows1 = read_cache(1, season, group)
            cell["1"] = {"rows": len(rows1), "id_sha256": id_column_hash(rows1)}
            for sport in TRANSFER_SPORTS:
                rows = read_cache(sport, season, group)
                if sport == 15 and not rows:
                    continue
                cell[str(sport)] = {"rows": len(rows),
                                    "sha256": canonical_hash(rows, sport)}
    return out


def _mtime(p: Path) -> dict:
    ts = p.stat().st_mtime
    return {"local": datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds"),
            "utc": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")}


def tx_receipts() -> dict:
    out = {}
    for ym in TX_MONTHS:
        p = TX_DIR / f"tx_{ym}.json.gz"
        if not p.exists():
            out[ym] = {"present": False}
            continue
        with gzip.open(p, "rt", encoding="utf-8") as fh:
            tx = json.load(fh).get("transactions") or []
        days = sorted(str(t.get("date"))[:10] for t in tx if t.get("date"))
        out[ym] = {"file": p.name, "sha256": _sha(p.read_bytes()),
                   "transactions": len(tx), "first_date": days[0] if days else None,
                   "last_date": days[-1] if days else None,
                   "fetched": _mtime(p)}
    return out


def pure_norms_from_frozen() -> dict:
    """{group: {level: pure norm | None}} from the frozen copy."""
    out: dict = {}
    for group in GROUPS:
        rows_by_level: dict[str, list[dict]] = {lv: [] for lv in LEVELS}
        for sport in FROZEN_SPORTS:
            for r in read_frozen(group, sport):
                if r.get("level") in rows_by_level:
                    rows_by_level[r["level"]].append(r)
        out[group] = {lv: mh.level_norms_from_rows(rows_by_level[lv], group)
                      for lv in LEVELS}
    return out


def served_blend_today() -> dict:
    """What milb_history.league_norms serves for 2026 on the day this runs (the cache read
    with fetch=False, blended with 2025 while the calendar reads 2026)."""
    saved = mh._fetch
    mh._fetch = _no_fetch
    try:
        mh.league_norms.cache_clear()
        return {g: {lv: mh.league_norms(SEASON, lv, g, fetch=False) for lv in LEVELS}
                for g in GROUPS}
    finally:
        mh._fetch = saved


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def _pretty(obj) -> bytes:
    return (json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=True) + "\n").encode("utf-8")


def freeze(today: date | None = None) -> dict:
    """Copy the 2026 files, write the event-id sets, the pins and the pure norms."""
    bad = check_2026_cache()
    if bad:
        raise FreezeError("2026 cache differs from the 2026-09-30 refetch: " + "; ".join(bad))
    today = today or date.today()
    frozen = {}
    for (sport, group) in sorted(EXPECTED_2026):
        src = cache_path(group, sport, SEASON)
        raw = src.read_bytes()
        dst = frozen_path(group, sport)
        if dst.exists() and dst.read_bytes() != raw:
            raise FreezeError(f"{dst.name} is frozen and differs from the cache; not rewritten")
        _write(dst, raw)
        rows = json.loads(raw.decode("utf-8"))
        frozen[dst.name] = {"sport": sport, "group": group, "sha256": _sha(raw),
                            "bytes": len(raw), "rows": len(rows),
                            "exposure": exposure(rows, group),
                            "exposure_field": "pa" if group == "hitting" else "bf",
                            "cache_file": f".cache/milb_stats/{src.name}",
                            "cache_mtime": _mtime(src)}
    events = {}
    for group in GROUPS:
        src = cache_path(group, 1, SEASON)
        rows = json.loads(src.read_text(encoding="utf-8"))
        ids = sorted(set(id_column(rows)))
        data = _compact(ids) + b"\n"
        _write(event_ids_path(group), data)
        events[event_ids_path(group).name] = {
            "group": group, "sha256": _sha(data), "ids": len(ids),
            "source_rows": len(rows), "source_id_column_sha256": id_column_hash(rows),
            "source_cache_file": f".cache/milb_stats/{src.name}",
            "source_cache_mtime": _mtime(src)}
    pins = {
        "schema": SCHEMA,
        "produced_by": "tools/milb_season_freeze.py --write",
        "pinned_on": today.isoformat(),
        "what_this_is": ("SG_1 pins for the 2026 MiLB season inputs (efv2026 PLAN.md N2, N3; "
                         "the surrogate gate draft's s11). Inputs only: no outcome, score or "
                         "label is read or stored here. NOT served."),
        "line_endings": ("data/milb_season_frozen/**, data/efv_surrogate_*.json and "
                         "data/milb_norms_2026_pure.json are -text in .gitattributes, so "
                         "each sha256 is the committed bytes on every machine"),
        "season_dates_2026": SEASON_DATES_2026,
        "frozen_2026": frozen,
        "frozen_2026_check": ("rows and PA or BF total equal the 2026-09-30 refetch for "
                              "every file (EXPECTED_2026)"),
        "mlb_event_ids_2026": events,
        "mlb_event_ids_note": ("sport 1 (MLB) 2026 lines are reduced to the sorted, "
                               "deduplicated person ids with a regular-season line; the "
                               "source id-column hash keeps duplicates; no MLB stat column "
                               "enters the tree"),
        "transfer_hash_method": {
            "fields": ["id", "sport"] + [n for n, _ in HASH_FIELDS[1:]],
            "cache_keys": {n: k for n, k in HASH_FIELDS if n != k},
            "sort": "person id, sport, league, then the projected row's compact JSON",
            "encoding": "compact JSON (sort_keys, ASCII) of the list of projected rows, sha256",
            "read": "milb_history.season_splits(sport, season, group, fetch=False)",
            "sport_1": "id column only (sorted, duplicates kept), sha256 of its compact JSON",
            "sport_15": "only where the file is non-empty",
        },
        "transfer_seasons": transfer_hashes(),
        "transactions_2026": {
            "note": ("the league transaction feed months SG_1 completed in "
                     ".cache/mlb_transactions/ from the efv2026 lane's 2026-09-30 refetch "
                     "(the cache had ended at 2026-07-24; tx_2026_07 replaced). "
                     "efv_drivers DS-09 reads the feed through December of V - 1, so no "
                     "row at V 2026 or earlier reads these months; V 2027 rows will. The "
                     "2026-09 file was fetched on its own last day, so the nightly's "
                     "mlb_events refresh may refetch it once, and this receipt then "
                     "records what SG_1 added, not the later file"),
            "months": tx_receipts(),
        },
        "pure_norms_file": NORMS_PATH.name,
    }
    norms = {
        "schema": SCHEMA,
        "produced_by": "tools/milb_season_freeze.py --write",
        "season": SEASON,
        "what_this_is": ("Pure 2026 MiLB level norms per side and level, from the frozen copy "
                         "data/milb_season_frozen/2026/, with milb_history.level_norms_from_rows "
                         "(lines with at least 100 PA or BF, the median of each rate, four "
                         "places, None under 30 lines) and NO current-year blend. NOT served."),
        "pure": pure_norms_from_frozen(),
        "served_blend_on_pin_date": {
            "date": today.isoformat(),
            "rule": ("milb_history.league_norms blends the current season with the prior at "
                     "w = n_cur / (n_cur + n_prior) while the calendar reads the season; the "
                     "blend ends 2027-01-01, when the served 2026 norms become these pure "
                     "norms with no new data"),
            "norms": served_blend_today(),
        },
    }
    norms_bytes = _pretty(norms)
    _write(NORMS_PATH, norms_bytes)
    pins["pure_norms_sha256"] = _sha(norms_bytes)
    _write(PINS_PATH, _pretty(pins))
    return pins


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="verify the 2026 cache; write nothing")
    g.add_argument("--write", action="store_true", help="write the frozen copy and pins")
    a = ap.parse_args(argv)
    bad = check_2026_cache()
    for b in bad:
        print("MISMATCH", b)
    if a.check or bad:
        print("2026 cache:", "clean" if not bad else f"{len(bad)} mismatches")
        return 1 if bad else 0
    pins = freeze()
    print(f"wrote {len(pins['frozen_2026'])} frozen files, "
          f"{len(pins['mlb_event_ids_2026'])} event-id files, "
          f"{sum(len(c) for s in pins['transfer_seasons'].values() for c in s.values())} "
          f"transfer hashes, {PINS_PATH.name}, {NORMS_PATH.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
