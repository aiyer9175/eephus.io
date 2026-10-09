# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""EV-03 modern-signal retention: per-season, as-of-dated snapshots.

WHY THIS EXISTS. The prospects.db tables statcast_metrics, zone_metrics,
pitch_arsenals, sabermetrics and statlines are keyed by player_key alone, so
they hold ONE season (2026 today) and every new season overwrites the last.
The sidecars stuff_plus_aaa.json (aStuff+) and statcast_aaa_hitters.json keep
only the latest qualified season per player. The as-of history of every
modern prospect signal therefore lived only in .cache/ files, and a pruned
cache would erase the vintage record a future gate needs (eFV v2 program,
docs/efv-v2/PROGRAM.md 3.4 EV-03, driver D6).

WHAT IT WRITES. data/signal_snapshots/<season>/<signal>.json, one file per
signal per season, plus data/signal_snapshots/manifest.json (sizes, row
counts, as-of dates). Each season file is columnar ("columns" + one "rows"
line per record, constant columns hoisted into "constants") so it stays
compact and diffs line by line. Every row keeps its own fetch date when the
source has one; the file carries "as_of" (the newest source date in it) and
"snapshot_taken_at".

  statlines          DB statlines (season line per player)
  sabermetrics       DB sabermetrics (wRC+, wOBA, FIP family, WAR)
  pitch_arsenals     DB pitch_arsenals (mix and velo per pitch type)
  zone_metrics       DB zone_metrics, one row per player and level
  statcast_metrics   DB statcast_metrics, one row per player and level,
                     season AGGREGATES only: coverage counts, contact quality
                     scalars and spray, pitch-type summary, stuff baseline.
                     The per-event lists (hit_locations, rolling_xwoba,
                     outings, pitch_plot, recent games) are dropped; they are
                     about 99.8% of the payload and remain rebuildable from
                     the game-feed cache.
  astuff_plus        data/stuff_plus_aaa.json (aStuff+, per pitch type too)
  aaa_pitch_physics  data/aaa_physics.json (AAA pitch physics per season)
  swing_plus         data/swing_plus.json (per-season Swing+, MLB only)
  alevel_signals     data/statcast_alevel_signals.json (A-ball whiff, FB velo)
  savant_minors      .cache/savant_minors/{batter,pitcher}_<season>.csv
                     (Savant minors AAA Statcast aggregates, both sides)

THE RETENTION RULE (tested). The live season is the newest of: the seasons in
the DB signal tables and the seasons already on disk. A file for a season
EARLIER than the live season is written once and then frozen: no later run
rewrites it, whatever the sources say. A live-season file is merged, never
truncated: a new pull replaces the rows it carries (same key) and keeps every
row it does not, so a player who drops out of a table mid-season keeps his
last as-of row. A sidecar that keeps only the latest season per player
(aStuff+) contributes its older-season rows to that season's file with
completeness "partial_latest_season_only", written once. An AAA source dated
by its own fetch (savant_minors, aaa_pitch_physics) whose OLDEST source date
precedes that season's last scheduled AAA regular-season date reads
"partial_in_season": the file holds an in-season cut, not the season.

NOT SERVED. These files sit under data/ at depth two, which neither deploy
consumer ships (deploy/nightly-build.sh and the workflow name their shard
directories one by one), they are not in deploy/publish_paths.txt, and they
have no data_catalog.py row. test_snapshot_modern_signals.py pins all three.

SAVANT MINORS 2021-2022. check_savant_history() is a one-off, read-only probe
(no cache write) of whether the Savant minors statcast search returns seasons
before 2023. Its recorded answer is SAVANT_HISTORY_CHECK below; the monthly
step never fetches.

Run:
    python tools/snapshot_modern_signals.py                 # snapshot now
    python tools/snapshot_modern_signals.py --check-savant-history
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import os
import re
import sqlite3
import sys
from datetime import date, datetime, timezone
from pathlib import Path

log = logging.getLogger("snapshot_modern_signals")

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SNAP_DIR = DATA_DIR / "signal_snapshots"
DB_PATH = ROOT / "prospects.db"
SAVANT_CACHE = ROOT / ".cache" / "savant_minors"

SCHEMA = 1
MANIFEST = "manifest.json"
COMPLETE = "complete"
PARTIAL = "partial_latest_season_only"
IN_SEASON = "partial_in_season"

#: Last scheduled AAA regular-season date by season (StatsAPI /api/v1/seasons, sportId 11;
#: the 2026 value fetched 2026-09-30 and pinned in data/efv_surrogate_pins_2026.json by
#: tools/milb_season_freeze.py). A season not listed reads September 30.
AAA_SEASON_END = {2026: "2026-09-20"}
#: AAA sources dated by their own fetch. A season file whose OLDEST source date precedes
#: that season's AAA end holds an in-season cut, so it reads IN_SEASON, not complete.
SEASON_CUT_SIGNALS = ("savant_minors", "aaa_pitch_physics")

DB_TABLES = ("statlines", "sabermetrics", "pitch_arsenals", "zone_metrics",
             "statcast_metrics")

# Recorded answer of the one read-only check (python tools/
# snapshot_modern_signals.py --check-savant-history, run 2026-09-24).
SAVANT_HISTORY_CHECK = {
    "checked_on": "2026-09-24",
    "question": "Does the Savant minors statcast search return seasons 2021-2022?",
    "answer": "yes",
    "request": ("arkmetric_forward_eval.SAVANT, player_type=batter, group_by=name, "
                "min_pas=100, one request per season, nothing cached"),
    "rows": {"2021": 169, "2022": 737},
    "reference_rows_2023_to_2026_batter_cache": {"2023": 722, "2024": 707,
                                                 "2025": 723, "2026": 495},
    "not_answered": ("which levels the 2021-2022 rows cover; the aggregate CSV "
                     "has no level column, and no further fetch was made"),
}

# statcast_metrics keys that are per-event lists or plot payloads. Dropped
# from the snapshot: season aggregates are the signal, the events are not.
_SC_DROP_TOP = {"pitch_plot", "recent_games", "standout_games", "level_splits",
                "season"}
_SC_DROP_CQ = {"hit_locations", "rolling_xwoba"}
_SC_DROP_PM = {"outings"}


# --------------------------------------------------------------------------
# small helpers

def _day(v) -> str | None:
    """The YYYY-MM-DD part of a date or timestamp string."""
    if not v:
        return None
    return str(v)[:10]


def _num(v):
    """CSV cell to int / float (4 decimals) / str / None."""
    if v is None:
        return None
    s = str(v).strip()
    if s == "":
        return None
    try:
        f = float(s)
    except ValueError:
        return s
    if f.is_integer() and "." not in s and "e" not in s.lower():
        return int(f)
    return round(f, 4)


def _mtime_day(p: Path) -> str:
    return datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).date().isoformat()


class Batch:
    """Rows of one signal for one season, plus how they were sourced."""

    def __init__(self, key: tuple[str, ...], source: str, as_of: str | None,
                 completeness: str = COMPLETE, meta: dict | None = None):
        self.key = key
        self.source = source
        self.as_of = as_of
        self.completeness = completeness
        self.meta = meta or {}
        self.rows: list[dict] = []
        # {source part: YYYY-MM-DD it was fetched or generated}, for the in-season rule
        self.source_dates: dict[str, str] = {}


def _batches() -> dict:
    return {}


def _add(out: dict, season: int, signal: str, row: dict, *, key, source,
         as_of=None, completeness=COMPLETE, meta=None) -> None:
    b = out.setdefault((signal, int(season)),
                       Batch(tuple(key), source, as_of, completeness, meta))
    b.rows.append(row)
    ra = _day(row.get("fetched_at"))
    if ra and (b.as_of is None or ra > b.as_of):
        b.as_of = ra


# --------------------------------------------------------------------------
# collectors: each returns {(signal, season): Batch}

def _compact_statcast(d: dict) -> dict:
    row = {k: v for k, v in d.items() if k not in _SC_DROP_TOP}
    cov = row.get("coverage")
    if isinstance(cov, dict):
        row["coverage"] = {k: v for k, v in cov.items() if k != "venues"}
    cq = row.get("contact_quality")
    if isinstance(cq, dict):
        row["contact_quality"] = {k: v for k, v in cq.items() if k not in _SC_DROP_CQ}
    pm = row.get("pitch_movement")
    if isinstance(pm, dict):
        pm = {k: v for k, v in pm.items() if k not in _SC_DROP_PM}
        ps = pm.get("pitch_summary")
        if isinstance(ps, list):
            pm["pitch_summary"] = [_pitch_cells(p) for p in ps if isinstance(p, dict)]
        sb = pm.get("stuff_baseline")
        if isinstance(sb, dict):
            pm["stuff_baseline"] = {k: v for k, v in sb.items() if k != "pitch_name"}
        row["pitch_movement"] = pm
    return row


# pitch_movement.pitch_summary is stored as one list per pitch type in this
# column order (the file's meta repeats it). pitch_name is dropped: it is a
# fixed label of pitch_type.
PITCH_SUMMARY_COLUMNS = (
    "pitch_type", "count", "usage_pct", "avg_velo", "max_velo", "avg_hb",
    "avg_ivb", "avg_spin", "avg_stuff_plus", "avg_extension",
    "avg_release_height", "avg_plate_height", "avg_vaa",
    "usage_L_count", "usage_L_pct", "usage_R_count", "usage_R_pct")


def _pitch_cells(p: dict) -> list:
    side = p.get("usage_by_batter_side") or {}
    flat = dict(p)
    for h in ("L", "R"):
        s = side.get(h) or {}
        flat[f"usage_{h}_count"] = s.get("count")
        flat[f"usage_{h}_pct"] = s.get("usage_pct")
    return [flat.get(c) for c in PITCH_SUMMARY_COLUMNS]


def _compact_zone(d: dict) -> dict:
    return {k: v for k, v in d.items() if k not in ("level_splits", "season")}


def _flatten(d: dict, prefix: str = "") -> dict:
    """Nested dicts become dotted columns (contact_quality.avg_ev), so the
    columnar file names each field once instead of once per row. Lists stay
    as cells."""
    out = {}
    for k, v in d.items():
        name = f"{prefix}{k}"
        if isinstance(v, dict) and v:
            out.update(_flatten(v, name + "."))
        else:
            out[name] = v
    return out


def _level_rows(d: dict, compact) -> list[dict]:
    """The primary row plus each level split, deduplicated."""
    prim = _flatten(compact(d))
    prim["row"] = "primary"
    out = [prim]
    seen = {json.dumps({k: v for k, v in prim.items() if k != "row"}, sort_keys=True)}
    for s in d.get("level_splits") or []:
        if not isinstance(s, dict):
            continue
        r = _flatten(compact(s))
        sig = json.dumps(r, sort_keys=True)
        if sig in seen:
            continue
        seen.add(sig)
        r["row"] = "split"
        out.append(r)
    return out


def collect_db(db_path: Path) -> dict:
    out = _batches()
    if not db_path.exists():
        log.warning("no DB at %s; DB signals skipped", db_path)
        return out
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        for table in DB_TABLES:
            try:
                cur = con.execute(
                    f"SELECT player_key, season, payload_json FROM {table}")
            except sqlite3.Error as e:
                log.warning("table %s unreadable: %s", table, e)
                continue
            for pk, season, payload in cur:
                try:
                    d = json.loads(payload)
                except (TypeError, ValueError):
                    continue
                if not isinstance(d, dict):
                    continue
                d.setdefault("player_key", pk)
                src = f"prospects.db {table}"
                if table == "statcast_metrics":
                    for r in _level_rows(d, _compact_statcast):
                        _add(out, season, table, r,
                             key=("player_key", "row", "level"), source=src,
                             meta={"pitch_summary_columns": list(PITCH_SUMMARY_COLUMNS),
                                   "dropped": sorted((_SC_DROP_TOP - {"level_splits", "season"})
                                                     | _SC_DROP_CQ | _SC_DROP_PM
                                                     | {"venues"})})
                elif table == "zone_metrics":
                    for r in _level_rows(d, _compact_zone):
                        _add(out, season, table, r,
                             key=("player_key", "row", "level"), source=src)
                else:
                    r = {k: v for k, v in d.items() if k != "season"}
                    if table == "pitch_arsenals":
                        for p in r.get("pitches") or []:
                            if isinstance(p, dict) and isinstance(p.get("avg_speed"), float):
                                p["avg_speed"] = round(p["avg_speed"], 2)
                    _add(out, season, table, r, key=("player_key",), source=src)
    finally:
        con.close()
    return out


def db_seasons(db_path: Path) -> set[int]:
    if not db_path.exists():
        return set()
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    got: set[int] = set()
    try:
        for table in DB_TABLES:
            try:
                got |= {int(s) for (s,) in con.execute(
                    f"SELECT DISTINCT season FROM {table}") if s is not None}
            except sqlite3.Error:
                continue
    finally:
        con.close()
    return got


def _load(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def collect_sidecars(data_dir: Path) -> dict:
    out = _batches()

    st = _load(data_dir / "stuff_plus_aaa.json")
    if isinstance(st, dict) and isinstance(st.get("players"), dict):
        players = st["players"]
        top = max((int(r["season"]) for r in players.values()
                   if isinstance(r, dict) and r.get("season")), default=None)
        meta = {"model": st.get("model"), "pool": st.get("pool")}
        for mid, r in players.items():
            if not isinstance(r, dict) or not r.get("season"):
                continue
            s = int(r["season"])
            row = {"mlbam_id": int(mid)}
            row.update({k: v for k, v in r.items() if k != "season"})
            _add(out, s, "astuff_plus", row, key=("mlbam_id",),
                 source="data/stuff_plus_aaa.json",
                 as_of=_day(st.get("generated_at")),
                 completeness=COMPLETE if s == top else PARTIAL, meta=meta)

    ph = _load(data_dir / "aaa_physics.json")
    if isinstance(ph, dict) and isinstance(ph.get("players"), dict):
        for mid, seasons in ph["players"].items():
            if not isinstance(seasons, dict):
                continue
            for s, r in seasons.items():
                if not (str(s).isdigit() and isinstance(r, dict)):
                    continue
                row = {"mlbam_id": int(mid)}
                row.update(r)
                _add(out, int(s), "aaa_pitch_physics", row, key=("mlbam_id",),
                     source="data/aaa_physics.json",
                     as_of=_day(ph.get("generated_at")),
                     meta={"registration": ph.get("registration")})
                if _day(ph.get("generated_at")):
                    out[("aaa_pitch_physics", int(s))].source_dates[
                        "aaa_physics.json"] = _day(ph.get("generated_at"))

    sw = _load(data_dir / "swing_plus.json")
    if isinstance(sw, dict) and isinstance(sw.get("players"), dict):
        for mid, r in sw["players"].items():
            if not isinstance(r, dict):
                continue
            for s, v in (r.get("seasons") or {}).items():
                if not (str(s).isdigit() and isinstance(v, dict)):
                    continue
                row = {"mlbam_id": int(mid), "name": r.get("name")}
                row.update(v)
                _add(out, int(s), "swing_plus", row, key=("mlbam_id",),
                     source="data/swing_plus.json",
                     as_of=_day(sw.get("generated_at")),
                     meta={"model": sw.get("model"),
                           "data_boundary": sw.get("data_boundary")})

    al = _load(data_dir / "statcast_alevel_signals.json")
    if isinstance(al, dict) and isinstance(al.get("by_mlbam"), dict):
        for mid, r in al["by_mlbam"].items():
            if not isinstance(r, dict):
                continue
            s = r.get("season") or al.get("season")
            if not s:
                continue
            row = {"mlbam_id": int(mid)}
            row.update({k: v for k, v in r.items() if k != "season"})
            _add(out, int(s), "alevel_signals", row, key=("mlbam_id",),
                 source="data/statcast_alevel_signals.json",
                 as_of=_day(al.get("generated_at")),
                 meta={"frozen_coefficients": al.get("frozen_coefficients")})
    return out


# Savant minors columns kept: everything except the fielder start depths.
def _savant_keep(col: str) -> bool:
    return not (col.startswith("pos") and col.endswith("_int_start_distance"))


def collect_savant(cache_dir: Path) -> dict:
    out = _batches()
    if not cache_dir.is_dir():
        return out
    for p in sorted(cache_dir.glob("*_*.csv")):
        side, _, s = p.stem.partition("_")
        if side not in ("batter", "pitcher") or not s.isdigit():
            continue
        text = p.read_text(encoding="utf-8-sig", errors="replace")
        for r in csv.DictReader(io.StringIO(text)):
            mid = _num(r.get("player_id"))
            if not isinstance(mid, int):
                continue
            row = {"side": side, "mlbam_id": mid}
            for k, v in r.items():
                if k and k != "player_id" and _savant_keep(k):
                    row[k] = _num(v)
            _add(out, int(s), "savant_minors", row, key=("side", "mlbam_id"),
                 source=".cache/savant_minors (Savant statcast-search-minors, min 100 PA)",
                 as_of=_mtime_day(p))
            b = out[("savant_minors", int(s))]
            if (b.as_of or "") < _mtime_day(p):
                b.as_of = _mtime_day(p)
            b.source_dates[side] = _mtime_day(p)
    return out


def season_end(season: int) -> str:
    """The last scheduled AAA regular-season date of `season` (AAA_SEASON_END)."""
    return AAA_SEASON_END.get(int(season), f"{int(season)}-09-30")


def mark_season_cut(signal: str, season: int, batch: Batch) -> None:
    """Record the source dates of a SEASON_CUT_SIGNALS batch in its meta, and mark it
    IN_SEASON when its oldest source date precedes the season's AAA end."""
    if signal not in SEASON_CUT_SIGNALS or not batch.source_dates:
        return
    batch.meta = dict(batch.meta, source_dates=dict(sorted(batch.source_dates.items())),
                      season_end=season_end(season))
    if batch.completeness == COMPLETE and min(batch.source_dates.values()) < season_end(season):
        batch.completeness = IN_SEASON


# --------------------------------------------------------------------------
# encode / decode

def _keyof(row: dict, key: tuple[str, ...]) -> str:
    return json.dumps([row.get(k) for k in key])


def encode(signal: str, season: int, batch: Batch, rows: list[dict],
           taken_at: str) -> str:
    rows = sorted(rows, key=lambda r: _keyof(r, batch.key))
    cols = sorted({k for r in rows for k in r})
    consts = {}
    if len(rows) > 1:
        for c in cols:
            vals = {json.dumps(r.get(c), sort_keys=True) for r in rows}
            if len(vals) == 1 and c not in batch.key and all(c in r for r in rows):
                consts[c] = rows[0][c]
    cols = [c for c in cols if c not in consts]
    head = {
        "schema": SCHEMA,
        "signal": signal,
        "season": season,
        "as_of": batch.as_of,
        "snapshot_taken_at": taken_at,
        "source": batch.source,
        "completeness": batch.completeness,
        "key": list(batch.key),
        "served": False,
        "n_rows": len(rows),
        "meta": batch.meta,
        "constants": consts,
        "columns": cols,
    }
    sep = (",", ":")
    lines = [json.dumps(head, sort_keys=True, separators=sep,
                        ensure_ascii=False)[:-1] + ',"rows":[']
    body = [json.dumps([r.get(c) for c in cols], sort_keys=True, separators=sep,
                       ensure_ascii=False) for r in rows]
    lines.append(",\n".join(body))
    lines.append("]}")
    return "\n".join(lines) + "\n"


def decode(text: str) -> tuple[dict, list[dict]]:
    d = json.loads(text)
    cols = d.get("columns") or []
    consts = d.get("constants") or {}
    rows = []
    for vals in d.get("rows") or []:
        r = dict(consts)
        r.update({c: v for c, v in zip(cols, vals)})
        rows.append(r)
    return d, rows


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


def write_signal(snap_dir: Path, signal: str, season: int, batch: Batch,
                 live_season: int, taken_at: str) -> str:
    """Write one season file under the retention rule. Returns the action:
    'frozen' (earlier season on disk, untouched), 'created', 'updated',
    'unchanged'."""
    path = snap_dir / str(season) / f"{signal}.json"
    if path.exists() and season < live_season:
        return "frozen"
    rows = list(batch.rows)
    if path.exists():
        try:
            old_head, old_rows = decode(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            old_head, old_rows = {}, []
        merged = {_keyof(r, batch.key): r for r in old_rows}
        for r in rows:
            merged[_keyof(r, batch.key)] = r
        rows = list(merged.values())
        if old_head.get("as_of") and (batch.as_of is None or old_head["as_of"] > batch.as_of):
            batch.as_of = old_head["as_of"]
        text = encode(signal, season, batch, rows, taken_at)
        old = path.read_text(encoding="utf-8")
        # a re-run with no new data changes only the snapshot date: keep the file
        if _strip_taken(old) == _strip_taken(text):
            return "unchanged"
        _write_atomic(path, text)
        return "updated"
    _write_atomic(path, encode(signal, season, batch, rows, taken_at))
    return "created"


def _strip_taken(text: str) -> str:
    return re.sub(r'"snapshot_taken_at":"[^"]*"', "", text, count=1)


def _manifest(snap_dir: Path, live_season: int, taken_at: str) -> dict:
    files = {}
    for p in sorted(snap_dir.glob("*/*.json")):
        if not p.parent.name.isdigit():
            continue
        try:
            head = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        files[f"{p.parent.name}/{p.name}"] = {
            # LF bytes: core.autocrlf rewrites checkouts to CRLF, and the
            # manifest must not churn because git touched a file
            "bytes": len(p.read_bytes().replace(b"\r\n", b"\n")),
            "n_rows": head.get("n_rows"),
            "as_of": head.get("as_of"),
            "completeness": head.get("completeness"),
        }
    return {
        "schema": SCHEMA,
        "what_this_is": ("EV-03 modern-signal retention (docs/efv-v2/PROGRAM.md 3.4). "
                         "Per-season, as-of-dated snapshots of prospect signals whose "
                         "live sources keep one season. NOT served: depth-two data "
                         "directory neither deploy consumer ships, no catalog row."),
        "retention_rule": ("seasons earlier than live_season are written once and frozen; "
                           "the live season merges by key and never drops a row"),
        "generated_at": taken_at,
        "live_season": live_season,
        "total_bytes": sum(f["bytes"] for f in files.values()),
        "files": files,
        "savant_minors_history_check": SAVANT_HISTORY_CHECK,
    }


def snapshot(*, snap_dir: Path = SNAP_DIR, data_dir: Path = DATA_DIR,
             db_path: Path = DB_PATH, savant_dir: Path = SAVANT_CACHE,
             today: date | None = None) -> dict:
    """Take the snapshot. Returns {"live_season", "actions": {path: action},
    "total_bytes", "n_files"}."""
    today = today or date.today()
    taken_at = today.isoformat()
    batches: dict = {}
    for part in (collect_db(db_path), collect_sidecars(data_dir),
                 collect_savant(savant_dir)):
        batches.update(part)
    on_disk = {int(p.name) for p in snap_dir.glob("*") if p.is_dir() and p.name.isdigit()} \
        if snap_dir.is_dir() else set()
    seasons = db_seasons(db_path) | on_disk
    live = max(seasons) if seasons else today.year
    actions = {}
    for (signal, season), b in sorted(batches.items()):
        if not b.rows:
            continue
        mark_season_cut(signal, season, b)
        actions[f"{season}/{signal}.json"] = write_signal(
            snap_dir, signal, season, b, live, taken_at)
    man = _manifest(snap_dir, live, taken_at)
    mpath = snap_dir / MANIFEST
    old = _load(mpath) if mpath.exists() else None

    def _body(m):
        return {k: v for k, v in (m or {}).items() if k != "generated_at"}
    if not isinstance(old, dict) or _body(old) != _body(man):
        _write_atomic(mpath, json.dumps(man, indent=1, sort_keys=True,
                                        ensure_ascii=False) + "\n")
    return {"live_season": live, "actions": actions,
            "total_bytes": man["total_bytes"], "n_files": len(man["files"])}


def summary_line(res: dict) -> str:
    acts = res.get("actions") or {}
    n = {a: sum(1 for v in acts.values() if v == a)
         for a in ("created", "updated", "unchanged", "frozen")}
    return (f"live {res.get('live_season')}: {n['created']} created, {n['updated']} updated, "
            f"{n['unchanged']} unchanged, {n['frozen']} frozen; "
            f"{res.get('n_files')} files, {res.get('total_bytes', 0) / 1e6:.2f} MB")


# --------------------------------------------------------------------------
# the one read-only history check

def check_savant_history(seasons=(2021, 2022), side: str = "batter") -> dict:
    """Ask the Savant minors search for each season (one request each, the
    same URL the cache uses) and report the row count. Writes nothing."""
    import urllib.request
    sys.path.insert(0, str(ROOT))
    from arkmetric_forward_eval import SAVANT
    out = {}
    for s in seasons:
        url = SAVANT.format(type=side, year=s)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                body = r.read().decode("utf-8-sig", errors="replace")
            rows = list(csv.DictReader(io.StringIO(body)))
            out[str(s)] = {"http": "ok", "rows": len(rows),
                           "bytes": len(body),
                           "first_player": (rows[0].get("player_name") if rows else None)}
        except Exception as e:                                    # noqa: BLE001
            out[str(s)] = {"http": "error", "error": str(e)[:200]}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check-savant-history", action="store_true",
                    help="one read-only Savant minors request per season 2021-2022")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if a.check_savant_history:
        print(json.dumps(check_savant_history(), indent=1))
        return 0
    res = snapshot()
    print(summary_line(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
