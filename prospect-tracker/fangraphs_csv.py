"""Auto-ingest FanGraphs board CSV exports dropped into the program folder.

The user exports a FanGraphs board view ("Top 100", "Org PIT", "Draft
2026", etc.) directly from FanGraphs as a CSV and drops the file into
``data/fangraphs_imports/``. The filename encodes the list scope + the
snapshot date so the parser can map a single CSV to a single Snapshot
batch with the right `(source, interval_label, snapshot_date)` triple.

Filename syntax::

    fangraphs_<list>_<YYYY-MM-DD>.csv

where ``<list>`` is e.g. ``top100``, ``org-PIT``, ``pos-SS``,
``draft-2026``, ``intl-2026``, or any free-form slug.

Two CSV column shapes are supported, automatically:

1. Standard board export (the sample format) — 23 cols including FV,
   rank, ETA, Risk, Trend, physical info, report text, video URL, FG
   PlayerId. No tool grades.

2. Scouting Summary view — adds per-tool 20-80 grades plus an optional
   "Contact" qualitative descriptor.

The auto-scraper is column-flexible: it picks up whichever fields the
CSV actually carries. Tool grades land in the snapshot's `tools` field;
non-grade extras (Risk, ETA, Report, Video, PlayerId, physical info,
Contact style) ride on a reserved ``_extras`` key inside the same JSON
blob so no schema migration is needed.
"""

from __future__ import annotations

import csv
import logging
import re
import shutil
from datetime import date, datetime
from pathlib import Path

from scrapers import Snapshot, normalize_key, fix_mojibake, _parse_fv, ALL_TOOL_KEYS

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_BASE = Path(__file__).parent
DROP_DIR = _BASE / "data" / "fangraphs_imports"
PROCESSED_DIR = DROP_DIR / "processed"

# Cap on stored scouting-report length so a multi-page report doesn't
# bloat the snapshots row. The frontend shows the first paragraph
# inline + a collapse for the rest; 8000 chars is enough for that.
_REPORT_MAX_CHARS = 8000


# ---------------------------------------------------------------------------
# Filename parsing
# ---------------------------------------------------------------------------

# fangraphs_<list-slug>_<YYYY-MM-DD>.csv. The list slug accepts word
# characters + dashes so org codes ("org-PIT") and year-stamped boards
# ("draft-2026") both work.
_FILENAME_RE = re.compile(r"^fangraphs_([\w-]+)_(\d{4}-\d{2}-\d{2})\.csv$",
                          re.IGNORECASE)


def _parse_filename(name: str) -> tuple[str, str] | None:
    """Return (list_slug, snapshot_date_iso) for a valid FG-CSV filename,
    or None for anything that doesn't match the convention. The slug is
    lowercased; the date keeps its YYYY-MM-DD ISO form."""
    m = _FILENAME_RE.match(name)
    if not m:
        return None
    slug = m.group(1).lower()
    date_iso = m.group(2)
    # Validate the date — a typo like 2026-13-01 should be rejected.
    try:
        datetime.strptime(date_iso, "%Y-%m-%d")
    except ValueError:
        return None
    return slug, date_iso


# ---------------------------------------------------------------------------
# Column normalization
# ---------------------------------------------------------------------------

# Map of normalized (lower, stripped) header → canonical snapshot field.
# Multiple FG column names can resolve to the same canonical field
# (e.g., "hit", "hit pres", "hit fut" all become "hit"). Tool grades use
# the canonical keys from `scrapers.ALL_TOOL_KEYS`.
_HEADER_MAP: dict[str, str] = {
    # Identity + ranking
    "name":          "player_name",
    "player":        "player_name",
    "org":           "org",
    "team":          "org",
    "pos":           "position",
    "position":      "position",
    "fv":            "fv",
    "top 100":       "rank",
    "top 200":       "rank",
    "rank":          "rank",
    "org rk":        "org_rank",
    "org rank":      "org_rank",
    # Lifecycle context
    "current level": "current_level",
    "level":         "current_level",
    "eta":           "eta_year",
    "status":        "status",
    # Profile context
    "risk":          "risk",
    "trend":         "trend",
    "age":           "age",
    "ht":            "height",
    "height":        "height",
    "wt":            "weight",
    "weight":        "weight",
    "b":             "bats",
    "bats":          "bats",
    "t":             "throws",
    "throws":        "throws",
    # Signing info
    "sign yr":       "sign_year",
    "sign mkt":      "sign_market",
    "sign org":      "sign_org",
    "bonus":         "bonus",
    "signed from":   "signed_from",
    # Narrative + FG id
    "report":        "report",
    "video":         "video_url",
    "playerid":      "fg_player_id",
    "player id":     "fg_player_id",
    "contact":       "contact_style",
    "contact style": "contact_style",
    # Hitter tools (canonical + common variants)
    "hit":           "hit",
    "hit pres":      "hit",
    "hit fut":       "hit",
    "game":          "game_pwr",
    "game pwr":      "game_pwr",
    "game pres":     "game_pwr",
    "game fut":      "game_pwr",
    "raw":           "raw_pwr",
    "raw pwr":       "raw_pwr",
    "raw pres":      "raw_pwr",
    "raw fut":       "raw_pwr",
    "spd":           "speed",
    "speed":         "speed",
    "fld":           "field",
    "field":         "field",
    "thr":           "throw",
    # Pitcher tools
    "fb":            "fb",
    "fastball":      "fb",
    "sl":            "sl",
    "slider":        "sl",
    "cb":            "cb",
    "curveball":     "cb",
    "curve":         "cb",
    "ch":            "ch",
    "changeup":      "ch",
    "cmd":           "cmd",
    "command":       "cmd",
    "ct":            "ct",
    "cutter":        "ct",
    "sp":            "sp",
    "splitter":      "sp",
}


def _normalize_row(raw_row: dict) -> dict:
    """Rebuild a CSV row keyed by canonical field names. Headers that
    don't appear in the header map are dropped silently — the scraper
    is forward-compatible with FG adding new columns."""
    out: dict = {}
    for k, v in raw_row.items():
        if k is None:
            continue
        canon = _HEADER_MAP.get(str(k).strip().lower())
        if canon is None:
            continue
        out[canon] = v
    return out


# ---------------------------------------------------------------------------
# Coercion helpers
# ---------------------------------------------------------------------------

_BLANK = {"", "—", "-", "n/a", "na", "null"}


def _str_or_none(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s or s.lower() in _BLANK:
        return None
    return s


def _to_int(v) -> int | None:
    s = _str_or_none(v)
    if s is None:
        return None
    # Strip thousands separators + trailing decimal noise.
    s = s.replace(",", "").replace("$", "")
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def _to_float(v) -> float | None:
    s = _str_or_none(v)
    if s is None:
        return None
    s = s.replace(",", "").replace("$", "")
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _to_grade(v) -> float | None:
    """Coerce to a 20-80 tool grade. Out-of-range values return None so
    typos surface rather than silently degrading the dataset."""
    g = _to_float(v)
    if g is None:
        return None
    if g < 20 or g > 80:
        return None
    return g


# ---------------------------------------------------------------------------
# Row → Snapshot
# ---------------------------------------------------------------------------

# Canonical fields that count as "tool grade." Matches scrapers.ALL_TOOL_KEYS
# plus a couple of common FG additions (cutter, splitter).
_TOOL_FIELDS = set(ALL_TOOL_KEYS) | {"ct", "sp"}

# Non-grade extras that we want to preserve per snapshot. They land
# inside the snapshot's `tools` dict under the reserved `_extras` key.
_EXTRA_FIELDS = (
    "risk", "trend", "eta_year", "current_level", "org_rank",
    "age", "height", "weight", "bats", "throws",
    "sign_year", "sign_market", "sign_org", "bonus", "signed_from",
    "report", "video_url", "fg_player_id", "contact_style",
)


def _parse_row(raw_row: dict, list_slug: str, snapshot_date: str) -> Snapshot | None:
    """Convert one normalized-header CSV row to a Snapshot, or None if
    the row is missing the minimum required fields (Name)."""
    row = _normalize_row(raw_row)
    name = _str_or_none(row.get("player_name"))
    if not name:
        return None
    name = fix_mojibake(name)
    key = normalize_key(name)

    # Rank: prefer the explicit Top-N column, fall back to org_rank.
    rank = _to_int(row.get("rank"))
    if rank is None:
        rank = _to_int(row.get("org_rank"))

    fv = _parse_fv(_str_or_none(row.get("fv")) or "")

    # Tool grades — only land when the column was present AND the
    # parsed grade is in [20, 80].
    tools: dict[str, float] = {}
    for k in _TOOL_FIELDS:
        if k not in row:
            continue
        g = _to_grade(row.get(k))
        if g is not None:
            tools[k] = g

    # Extras blob — typed coercion for numeric extras, raw string for
    # textual ones. Truncate the report to keep snapshot rows small.
    extras: dict = {}
    if "risk" in row:           extras["risk"]           = _str_or_none(row.get("risk"))
    if "trend" in row:          extras["trend"]          = _str_or_none(row.get("trend"))
    if "eta_year" in row:       extras["eta_year"]       = _to_int(row.get("eta_year"))
    if "current_level" in row:  extras["current_level"]  = _str_or_none(row.get("current_level"))
    if "org_rank" in row:       extras["org_rank"]       = _to_int(row.get("org_rank"))
    if "age" in row:            extras["age"]            = _to_float(row.get("age"))
    if "height" in row:         extras["height"]         = _str_or_none(row.get("height"))
    if "weight" in row:         extras["weight"]         = _to_int(row.get("weight"))
    if "bats" in row:           extras["bats"]           = _str_or_none(row.get("bats"))
    if "throws" in row:         extras["throws"]         = _str_or_none(row.get("throws"))
    if "sign_year" in row:      extras["sign_year"]      = _to_int(row.get("sign_year"))
    if "sign_market" in row:    extras["sign_market"]    = _str_or_none(row.get("sign_market"))
    if "sign_org" in row:       extras["sign_org"]       = _str_or_none(row.get("sign_org"))
    if "bonus" in row:          extras["bonus"]          = _to_int(row.get("bonus"))
    if "signed_from" in row:    extras["signed_from"]    = _str_or_none(row.get("signed_from"))
    if "video_url" in row:      extras["video_url"]      = _str_or_none(row.get("video_url"))
    if "fg_player_id" in row:   extras["fg_player_id"]   = _to_int(row.get("fg_player_id"))
    if "contact_style" in row:  extras["contact_style"]  = _str_or_none(row.get("contact_style"))
    if "report" in row:
        rpt = _str_or_none(row.get("report"))
        if rpt and len(rpt) > _REPORT_MAX_CHARS:
            rpt = rpt[:_REPORT_MAX_CHARS]
        if rpt:
            extras["report"] = rpt

    # Drop None-valued extras so re-serialized JSON is compact.
    extras = {k: v for k, v in extras.items() if v is not None and v != ""}

    # Merge tools + extras into one dict that lands in snapshot.tools.
    # `_extras` only appears when something to surface exists.
    tools_payload: dict | None = None
    if tools or extras:
        tools_payload = dict(tools)
        if extras:
            tools_payload["_extras"] = extras

    # Status defaults to "active" — graduations are detected by the
    # downstream pipeline using career-threshold rules, not the FG
    # board's Current Level column.
    return Snapshot(
        source="fangraphs",
        snapshot_date=snapshot_date,
        interval_label=list_slug,
        player_key=key,
        player_name=name,
        position=_str_or_none(row.get("position")),
        org=_str_or_none(row.get("org")),
        rank=rank,
        fv=fv,
        status=(_str_or_none(row.get("status")) or "active").lower(),
        tools=tools_payload,
    )


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def _read_csv_rows(path: Path) -> list[dict]:
    """Read a CSV into a list of header-keyed dict rows, trying a few
    common encodings (Windows exports occasionally arrive as cp1252)."""
    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            with path.open(encoding=enc, newline="") as f:
                reader = csv.DictReader(f)
                return list(reader)
        except UnicodeDecodeError:
            continue
    log.warning("fangraphs_csv: could not decode %s with any known encoding",
                path.name)
    return []


def parse_csv(path: Path) -> tuple[list[Snapshot], str | None]:
    """Parse a single FG-CSV file into a list of Snapshots.

    Returns ``(snapshots, error)``. ``error`` is None on success or a
    short reason string when the file should stay in the drop folder
    (bad filename, missing Name column, no rows). Files that parse but
    skip individual rows still return success — the per-row skip is
    logged but doesn't fail the file.
    """
    parsed = _parse_filename(path.name)
    if not parsed:
        return [], f"filename does not match fangraphs_<list>_<YYYY-MM-DD>.csv"
    list_slug, snapshot_date = parsed

    rows = _read_csv_rows(path)
    if not rows:
        return [], "no rows or unreadable encoding"

    # Sanity: every supported FG export has SOME identity column. If
    # none of the rows have a recognizable Name header, the file is
    # almost certainly not a FG board export — bail without touching it.
    sample_headers = {str(k).strip().lower() for k in (rows[0] or {}).keys()}
    if not (sample_headers & {"name", "player"}):
        return [], "missing Name/Player column"

    snapshots: list[Snapshot] = []
    skipped = 0
    for r in rows:
        snap = _parse_row(r, list_slug, snapshot_date)
        if snap is None:
            skipped += 1
            continue
        snapshots.append(snap)
    if skipped:
        log.info("fangraphs_csv: %s — skipped %d rows missing required fields",
                 path.name, skipped)
    return snapshots, None


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def ingest_drops(today: date | None = None,
                 drop_dir: Path | None = None,
                 processed_dir: Path | None = None) -> tuple[int, int]:
    """Scan the drop folder, parse each `fangraphs_*.csv` file, and
    insert the resulting snapshots into the DB. Successfully ingested
    files move into ``processed/`` with an `.imported.<timestamp>`
    suffix. Files that fail to parse stay in the drop folder + log a
    warning.

    Returns ``(snapshots_inserted, files_processed)``.
    """
    today = today or date.today()
    drop_dir = drop_dir or DROP_DIR
    processed_dir = processed_dir or PROCESSED_DIR
    drop_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    # Lazy import keeps `fangraphs_csv` standalone for unit tests that
    # don't want to touch the DB layer.
    from storage import insert_snapshots

    files = sorted(p for p in drop_dir.glob("*.csv") if p.is_file())
    if not files:
        return 0, 0

    inserted_total = 0
    files_processed = 0
    for path in files:
        try:
            snaps, err = parse_csv(path)
        except Exception:
            log.exception("fangraphs_csv: parse_csv crashed on %s", path.name)
            continue
        if err is not None:
            log.warning("fangraphs_csv: skipping %s (%s)", path.name, err)
            continue
        try:
            n = insert_snapshots(snaps)
        except Exception:
            log.exception("fangraphs_csv: insert_snapshots failed on %s", path.name)
            continue
        inserted_total += n
        files_processed += 1
        # Move the file to processed/ with a timestamp so a future run
        # can see what's been picked up but doesn't re-import.
        stamp = today.strftime("%Y%m%d") + "-" + datetime.now().strftime("%H%M%S")
        dest = processed_dir / f"{path.name}.imported.{stamp}"
        try:
            shutil.move(str(path), str(dest))
        except Exception:
            log.exception("fangraphs_csv: could not move %s to processed/",
                          path.name)
        log.info("fangraphs_csv: ingested %d snapshots from %s "
                 "(%d total rows)", n, path.name, len(snaps))

    log.info("fangraphs_csv: ingested %d snapshots from %d file(s)",
             inserted_total, files_processed)
    return inserted_total, files_processed
