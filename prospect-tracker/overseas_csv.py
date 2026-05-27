# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Overseas (KBO/NPB/CPBL) CSV ingest — mirror of draft_csv.py.

The overseas FG board CSVs share the same 4-file shape as the standard
board (summary/position/pitching/physical) but the summary header carries
distinct columns: Country, Current Team, Proj Team, Proj Bonus, and a
Player Type field that doubles as the league code ('NPB', 'KBO', etc.).

Slug convention: `<year>overseas` (e.g. `2026overseas`). The
fangraphs_csv router inspects the slug and hands these off here instead
of the MiLB pipeline, so amateur, overseas, and MiLB cohorts stay fully
partitioned.

Reuses fangraphs_csv helpers for filename parsing, header normalization,
coercers, encoding-safe reader, and the position/pitching/physical row
parsers (their column shapes match the standard board verbatim).
"""

from __future__ import annotations

import csv
import logging
import re
import shutil
from collections import defaultdict
from datetime import date
from pathlib import Path

from fangraphs_csv import (
    _classify_csv,
    _norm_headers,
    _parse_filename,
    _parse_pitching_row,
    _parse_position_row,
    _parse_physical_row,
    _read_csv_rows,
    _sniff_headers,
    _str_or_none,
    _to_float,
    _to_int,
)
from scrapers import _parse_fv, _parse_fv_full, fix_mojibake, normalize_key
from storage import insert_overseas_snapshots

log = logging.getLogger(__name__)


_BASE = Path(__file__).parent
DROP_DIR = _BASE / "data" / "fangraphs_imports"
PROCESSED_DIR = DROP_DIR / "processed"

_REPORT_MAX_CHARS = 8000


# ---------------------------------------------------------------------------
# Slug parsing — overseas CSVs are <year>overseas (no kind suffix).
# ---------------------------------------------------------------------------

_OVERSEAS_SLUG_RE = re.compile(r"^(?P<year>20\d\d)[-_]?overseas$", re.IGNORECASE)


def is_overseas_slug(slug: str) -> int | None:
    """Return the snapshot year for an overseas slug, else None."""
    if not slug:
        return None
    m = _OVERSEAS_SLUG_RE.match(slug)
    if not m:
        return None
    return int(m.group("year"))


# Recognized league codes from FG's Player Type column. Anything else
# stays in the league field but UI displays the verbatim value (so a
# new league shows up rather than silently disappearing).
_KNOWN_LEAGUES = {"NPB", "NPBF", "KBO", "CPBL", "CUBA", "MLBR"}


def overseas_player_key(league: str | None, player_name: str) -> str:
    """Canonical key for an overseas prospect:
    'overseas_<league>_<normalized_name>'. League namespacing prevents
    cross-league name collisions until a player is signed to an MLB org
    (at which point promotion rewrites the key to the MiLB canonical
    form)."""
    league_slug = (league or "other").lower().replace(" ", "_")
    return f"overseas_{league_slug}_{normalize_key(player_name)}"


# ---------------------------------------------------------------------------
# Overseas-specific summary parser
# ---------------------------------------------------------------------------

# Summary header (FG overseas):
#   Name, Pos, Player Type, ETA, Age, Country, Current Team,
#   Proj Team, Proj Bonus, Ht, Wt, B, T, FV, Risk, Report, Video, PlayerId
#
# Proj Bonus is shipped as either a raw integer ("8500000"),
# a $-prefixed string ("$8,500,000"), or blank when FG hasn't
# committed to a number. `_to_usd` handles all three.
def _to_usd(v) -> int | None:
    s = _str_or_none(v)
    if s is None:
        return None
    digits = re.sub(r"[^\d]", "", s)
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def _parse_overseas_summary_row(raw: dict, snapshot_year: int) -> dict | None:
    """Parse one summary-<year>overseas.csv row into a normalized dict."""
    row = _norm_headers(raw)
    name = _str_or_none(row.get("name"))
    if not name:
        return None
    name = fix_mojibake(name)
    league_raw = _str_or_none(row.get("player type"))
    # Normalize: FG occasionally writes 'npb' (lowercase) for farm teams
    league = league_raw.upper() if league_raw else None
    if league and league not in _KNOWN_LEAGUES:
        # Keep the verbatim value but surface a log so a new league
        # gets noticed and added to _KNOWN_LEAGUES if it's recurring.
        log.info("overseas_csv: unfamiliar league code '%s' for %s",
                 league_raw, name)
    pkey = overseas_player_key(league, name)
    _fv_val, _fv_plus = _parse_fv_full(_str_or_none(row.get("fv")) or "")
    return {
        "player_key":     pkey,
        "player_name":    name,
        "fg_player_id":   _str_or_none(row.get("playerid")),
        "position":       _str_or_none(row.get("pos")),
        "league":         league,
        "country":        _str_or_none(row.get("country")),
        "current_team":   _str_or_none(row.get("current team")),
        "proj_team":      _str_or_none(row.get("proj team")),
        "proj_bonus_usd": _to_usd(row.get("proj bonus")),
        "eta_year":       _to_int(row.get("eta")),
        "snapshot_year":  snapshot_year,
        "fv":             _fv_val,
        "fv_plus":        _fv_plus,
        "risk":           _str_or_none(row.get("risk")),
        "age":            _to_float(row.get("age")),
        "height":         _str_or_none(row.get("ht") or row.get("height")),
        "weight":         _to_int(row.get("wt") or row.get("weight")),
        "bats":           _str_or_none(row.get("b") or row.get("bats")),
        "throws":         _str_or_none(row.get("t") or row.get("throws")),
        "report":         _str_or_none(row.get("report")),
        "video_url":      _str_or_none(row.get("video")),
    }


# ---------------------------------------------------------------------------
# Join: merge summary + position + pitching + physical by player_key
# ---------------------------------------------------------------------------

def _join_overseas_set(summary_rows: list[dict],
                       position_rows: list[dict],
                       pitching_rows: list[dict],
                       physical_rows: list[dict]) -> list[dict]:
    """Merge per-type rows on player_key. Summary is the spine."""
    by_key: dict[str, dict] = {s["player_key"]: s for s in summary_rows if s}
    # Map MiLB-style normalize_key → overseas player_key for each summary
    # row, so we can re-key the position/pitching/physical rows (those
    # use bare normalize_key per fangraphs_csv).
    name_to_okey: dict[str, str] = {}
    for s in summary_rows:
        if s:
            name_to_okey[normalize_key(s["player_name"])] = s["player_key"]

    def _rekey(rows):
        out: dict[str, dict] = {}
        for r in rows:
            if not r:
                continue
            mp = r.get("player_key")
            if not mp:
                continue
            target = name_to_okey.get(mp)
            if target:
                out[target] = r
        return out

    pos_by_key  = _rekey(position_rows)
    pit_by_key  = _rekey(pitching_rows)
    phys_by_key = _rekey(physical_rows)

    merged: list[dict] = []
    for key, summ in by_key.items():
        m = dict(summ)
        if key in pos_by_key:
            m["_position"] = pos_by_key[key]
        if key in pit_by_key:
            m["_pitching"] = pit_by_key[key]
        if key in phys_by_key:
            m["_physical"] = phys_by_key[key]
        merged.append(m)
    return merged


# ---------------------------------------------------------------------------
# Snapshot emission
# ---------------------------------------------------------------------------

def _merged_to_snapshot_dict(m: dict,
                             snapshot_date: str,
                             interval_label: str) -> dict:
    tools: dict = {}
    extras: dict = {}

    pos = m.get("_position") or {}
    pit = m.get("_pitching") or {}
    if pos.get("tools_future"):
        tools.update(pos["tools_future"])
        if pos.get("tools_present"):
            extras["tools_present"] = pos["tools_present"]
    if pit.get("tools_future"):
        tools.update(pit["tools_future"])
        if pit.get("tools_present"):
            cur = extras.get("tools_present") or {}
            cur.update(pit["tools_present"])
            extras["tools_present"] = cur

    for k in ("tj_date", "fb_type", "sits", "tops", "rpm_fb", "rpm_break"):
        v = pit.get(k)
        if v is not None:
            extras[k] = v

    phys = m.get("_physical") or {}
    for k in ("frame", "athl", "levers", "arm", "perf", "delivery"):
        v = phys.get(k)
        if v is not None:
            extras[k] = v

    for k in ("age", "height", "weight", "bats", "throws", "fg_player_id",
              "video_url"):
        v = m.get(k)
        if v is not None and v != "":
            extras[k] = v

    if m.get("report"):
        rpt = m["report"]
        from scrapers import _clean_report_prose
        cleaned = _clean_report_prose(rpt)
        if cleaned:
            extras["report"] = cleaned[:_REPORT_MAX_CHARS]

    if extras:
        tools["_extras"] = extras

    # If Proj Team looks like an MLB org code (2-4 caps), treat as signed.
    # Otherwise overseas_active. Posting status is set out-of-band via
    # upsert_overseas_posting.
    proj = m.get("proj_team") or ""
    looks_signed = bool(re.fullmatch(r"[A-Z]{2,4}", proj.strip()))
    status = "signed" if looks_signed else "overseas_active"

    return {
        "source":          "fangraphs",
        "snapshot_date":   snapshot_date,
        "interval_label":  interval_label,
        "player_key":      m["player_key"],
        "player_name":     m["player_name"],
        "position":        m.get("position"),
        "league":          m.get("league"),
        "country":         m.get("country"),
        "current_team":    m.get("current_team"),
        "proj_team":       m.get("proj_team"),
        "proj_bonus_usd":  m.get("proj_bonus_usd"),
        "eta_year":        m.get("eta_year"),
        "fv":              m.get("fv"),
        "fv_plus":         bool(m.get("fv_plus", False)),
        "risk":            m.get("risk"),
        "status":          status,
        "tools":           tools or None,
        "birth_date":      None,
        "bats":            m.get("bats"),
        "throws":          m.get("throws"),
        "height":          m.get("height"),
        "weight":          m.get("weight"),
        "fg_player_id":    m.get("fg_player_id"),
    }


# ---------------------------------------------------------------------------
# Group folders / flat files by slug
# ---------------------------------------------------------------------------

def _group_subfolders(drop_dir: Path) -> list[dict]:
    out: list[dict] = []
    if not drop_dir.is_dir():
        return out
    for sub in sorted(drop_dir.iterdir()):
        if not sub.is_dir():
            continue
        if sub.name == "processed" or sub.name.startswith("."):
            continue
        year = is_overseas_slug(sub.name)
        if year is None:
            continue
        csvs = sorted(p for p in sub.glob("*.csv") if p.is_file())
        if not csvs:
            continue
        grp: dict = {"slug": sub.name, "snapshot_year": year,
                     "_folder": sub, "_unclassified": []}
        for path in csvs:
            headers = _sniff_headers(path)
            ftype = _classify_csv(headers)
            if ftype is None:
                # FG sometimes ships a summary CSV without 'report' on
                # an in-season cycle. Detect overseas summary via Country
                # + Current Team headers.
                norm = {h.strip().lower() for h in headers}
                if "country" in norm and "current team" in norm:
                    ftype = "summary"
            if ftype is None:
                grp["_unclassified"].append(path)
                continue
            grp[ftype] = path
        out.append(grp)
    return out


def _group_flat(drop_dir: Path) -> list[dict]:
    out: dict[str, dict] = defaultdict(dict)
    if not drop_dir.is_dir():
        return []
    for p in sorted(drop_dir.glob("*.csv")):
        parsed = _parse_filename(p.name)
        if not parsed:
            continue
        ftype, slug = parsed
        year = is_overseas_slug(slug)
        if year is None:
            continue
        out[slug][ftype] = p
        out[slug].setdefault("slug", slug)
        out[slug].setdefault("snapshot_year", year)
    return list(out.values())


# ---------------------------------------------------------------------------
# Per-set processor
# ---------------------------------------------------------------------------

def _process_one_set(grp: dict,
                     processed_dir: Path | None = None,
                     snapshot_date_override: str | None = None) -> int:
    slug = grp["slug"]
    year = grp["snapshot_year"]
    if "summary" not in grp:
        log.warning("overseas_csv: skipping '%s' — missing summary CSV (have: %s)",
                    slug, sorted(k for k in grp
                                 if k not in {"slug", "snapshot_year",
                                              "_folder", "_unclassified",
                                              "_files"}))
        return 0

    summary_raw = _read_csv_rows(grp["summary"])
    summary_rows = [r for r in (_parse_overseas_summary_row(x, year)
                                for x in summary_raw) if r]
    position_raw = _read_csv_rows(grp["position"]) if "position" in grp else []
    pitching_raw = _read_csv_rows(grp["pitching"]) if "pitching" in grp else []
    physical_raw = _read_csv_rows(grp["physical"]) if "physical" in grp else []
    position_rows = [r for r in (_parse_position_row(x) for x in position_raw) if r]
    pitching_rows = [r for r in (_parse_pitching_row(x) for x in pitching_raw) if r]
    physical_rows = [r for r in (_parse_physical_row(x) for x in physical_raw) if r]

    if not summary_rows:
        log.warning("overseas_csv: '%s' yielded 0 summary rows", slug)
        return 0

    merged = _join_overseas_set(summary_rows, position_rows, pitching_rows,
                                physical_rows)

    snap_date = snapshot_date_override
    if not snap_date:
        folder = grp.get("_folder")
        if folder:
            snap_date = date.fromtimestamp(folder.stat().st_mtime).isoformat()
        elif grp.get("summary"):
            try:
                snap_date = date.fromtimestamp(grp["summary"].stat().st_mtime).isoformat()
            except OSError:
                snap_date = date.today().isoformat()
        else:
            snap_date = date.today().isoformat()

    interval_label = f"FG {year} Overseas ({snap_date})"

    snap_payloads = [_merged_to_snapshot_dict(m, snap_date, interval_label)
                     for m in merged]
    n = insert_overseas_snapshots(snap_payloads)
    log.info("overseas_csv: '%s' -> %d snapshots (year=%d, date=%s)",
             slug, n, year, snap_date)

    if processed_dir and grp.get("_folder"):
        dest = processed_dir / f"{slug}__{snap_date}"
        try:
            if dest.exists():
                log.info("overseas_csv: '%s' already in processed/, skipping move", slug)
            else:
                shutil.move(str(grp["_folder"]), str(dest))
                log.info("overseas_csv: moved '%s' to processed/", slug)
        except OSError as e:
            log.warning("overseas_csv: could not move '%s' to processed/: %s",
                        slug, e)
    elif processed_dir and any(f in grp for f in ("summary", "position", "pitching", "physical")):
        # Flat layout: move the four CSV files into a new processed/<slug>__<date>/
        dest = processed_dir / f"{slug}__{snap_date}"
        try:
            dest.mkdir(parents=True, exist_ok=True)
            for ftype in ("summary", "position", "pitching", "physical"):
                fp = grp.get(ftype)
                if fp and fp.exists():
                    shutil.move(str(fp), str(dest / fp.name))
            log.info("overseas_csv: archived flat-layout '%s' to processed/", slug)
        except OSError as e:
            log.warning("overseas_csv: could not archive '%s': %s", slug, e)

    return n


# ---------------------------------------------------------------------------
# Orchestrator + backfill
# ---------------------------------------------------------------------------

def ingest_drops(drop_dir: Path | None = None,
                 processed_dir: Path | None = None) -> tuple[int, int]:
    """Scan drop_dir for <year>overseas subfolders + flat
    <type>-<year>overseas.csv files. Returns (snapshots_inserted, sets)."""
    drop_dir = drop_dir or DROP_DIR
    processed_dir = processed_dir or PROCESSED_DIR
    processed_dir.mkdir(parents=True, exist_ok=True)

    groups = _group_subfolders(drop_dir) + _group_flat(drop_dir)
    if not groups:
        log.info("overseas_csv: no overseas drops to ingest")
        return (0, 0)

    snaps_total = 0
    sets = 0
    for grp in groups:
        try:
            n_snap = _process_one_set(grp, processed_dir=processed_dir)
            if n_snap > 0:
                snaps_total += n_snap
                sets += 1
        except Exception as e:
            log.exception("overseas_csv: '%s' crashed: %s", grp.get("slug"), e)

    log.info("overseas_csv: ingested %d snapshots from %d overseas set(s)",
             snaps_total, sets)
    return (snaps_total, sets)


def backfill_processed(processed_dir: Path | None = None) -> tuple[int, int]:
    """Re-read every <year>overseas__<date>/ subfolder under processed/."""
    processed_dir = processed_dir or PROCESSED_DIR
    if not processed_dir.is_dir():
        return (0, 0)

    snaps_total = 0
    sets = 0
    for sub in sorted(processed_dir.iterdir()):
        if not sub.is_dir():
            continue
        base, _, date_part = sub.name.partition("__")
        year = is_overseas_slug(base)
        if year is None:
            continue
        csvs = sorted(p for p in sub.glob("*.csv") if p.is_file())
        if not csvs:
            continue
        grp: dict = {"slug": base, "snapshot_year": year, "_folder": sub,
                     "_unclassified": []}
        for path in csvs:
            headers = _sniff_headers(path)
            ftype = _classify_csv(headers)
            if ftype is None:
                norm = {h.strip().lower() for h in headers}
                if "country" in norm and "current team" in norm:
                    ftype = "summary"
            if ftype is None:
                continue
            grp[ftype] = path
        try:
            n_snap = _process_one_set(grp, processed_dir=None,
                                       snapshot_date_override=date_part or None)
            if n_snap > 0:
                snaps_total += n_snap
                sets += 1
        except Exception as e:
            log.exception("overseas_csv backfill: '%s' crashed: %s", base, e)

    log.info("overseas_csv: backfilled %d snapshots from %d processed set(s)",
             snaps_total, sets)
    return (snaps_total, sets)
