# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Auto-ingest FanGraphs board CSV exports — v3, four-CSV report sets.

A complete FanGraphs board report is FOUR CSVs sharing the same PlayerId:

  * summary    — Top 100, FV, Risk/Trend, signing info, scouting report
  * position   — hitter tools w/ pres/fut, Versa, Con Style, Hard Hit%,
                 Avg EV / Max EV
  * pitching   — pitch tools, TJ Date, FB Type, Sits/Tops, RPM FB / RPM Break
  * physical   — Frame, Athl, Levers, Arm, Perf, Delivery

Two supported drop layouts (both work; mix and match freely):

  1. **Subfolder per report set** (preferred — simplest naming):

        data/fangraphs_imports/<slug>/<any-name>.csv  × 4 files

     Folder name is the slug. Files inside can have any name; their
     type (summary / position / pitching / physical) is detected from
     the column-header signature.

  2. **Legacy flat layout** (still supported):

        data/fangraphs_imports/<type>-<slug>.csv

     Filename pattern: `summary-2025_Updated.csv`, etc. Type comes from
     the prefix.

Publish date is auto-detected from the row-level decimal Age column:
``snapshot_date = birth_date + age × 365.25 days``. We use birth dates
already on file (storage.load_birth_dates) and take the median across
matched players. Falls back to file mtime when too few birth dates align.

Tool grades come as "<present> / <future>" strings. The future grade
lands at the top of `snapshot.tools` (consensus.py expects future-as-
canonical). Present grades + all non-grade extras nest under
``_extras`` in the same JSON blob.

**After dropping new CSVs**: run `python run_monthly.py --rebuild-only`
to push the new data to `data/timeseries.json` (and therefore the
website) without waiting through the full monthly pipeline.
"""

from __future__ import annotations

import csv
import logging
import re
import shutil
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import median

from scrapers import Snapshot, normalize_key, fix_mojibake, _parse_fv, _parse_fv_full

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_BASE = Path(__file__).parent
DROP_DIR = _BASE / "data" / "fangraphs_imports"
PROCESSED_DIR = DROP_DIR / "processed"

_REPORT_MAX_CHARS = 8000


# ---------------------------------------------------------------------------
# Filename parsing
# ---------------------------------------------------------------------------

# <type>-<slug>.csv, case-insensitive. Type is one of summary, position,
# pitching, physical (or physicalattributes, which aliases to physical).
_FILENAME_RE = re.compile(
    r"^(summary|position|pitching|scouting|physical(?:attributes)?)-([\w-]+)\.csv$",
    re.IGNORECASE,
)


def _parse_filename(name: str) -> tuple[str, str] | None:
    """Return ``(type, slug)`` for a valid FG-CSV filename, or None.
    ``type`` is one of {summary, position, pitching, scouting, physical}.
    ``physicalattributes-<slug>.csv`` aliases to type=physical. The
    new-format ``scouting-<slug>.csv`` (2017-2018 boards) is a single file
    carrying BOTH hitter and pitcher tool grades, used where the per-type
    position/pitching files don't exist."""
    m = _FILENAME_RE.match(name)
    if not m:
        return None
    raw_type = m.group(1).lower()
    if raw_type == "physicalattributes":
        raw_type = "physical"
    return raw_type, m.group(2).lower()


# ---------------------------------------------------------------------------
# Coercers
# ---------------------------------------------------------------------------

_BLANK = {"", "—", "-", "n/a", "na", "null"}


def _str_or_none(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip().strip('"')
    if not s or s.lower() in _BLANK:
        return None
    return s


def _to_int(v) -> int | None:
    s = _str_or_none(v)
    if s is None:
        return None
    s = s.replace(",", "").replace("$", "").strip()
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def _to_float(v) -> float | None:
    s = _str_or_none(v)
    if s is None:
        return None
    s = s.replace(",", "").replace("$", "").strip().rstrip("%")
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _to_grade(v) -> float | None:
    """Single 20-80 grade. Out-of-range returns None so typos surface."""
    g = _to_float(v)
    if g is None:
        return None
    if g < 20 or g > 80:
        return None
    return g


def _parse_grade_pair(v) -> tuple[float | None, float | None]:
    """Parse FanGraphs '<present> / <future>' tool-grade strings.

    Returns ``(present, future)`` as floats in [20, 80], or None per slot
    when missing/invalid. A single value ("45") is treated as future-only.
    """
    s = _str_or_none(v)
    if s is None:
        return (None, None)
    if "/" not in s:
        return (None, _to_grade(s))
    parts = [p.strip() for p in s.split("/", 1)]
    present = _to_grade(parts[0]) if parts[0] else None
    future = _to_grade(parts[1]) if len(parts) > 1 and parts[1] else None
    return (present, future)


def _to_pct(v) -> float | None:
    """0.5 / "0.5" / "50%" / "50" → 0.5 (decimal). None on parse failure."""
    s = _str_or_none(v)
    if s is None:
        return None
    has_pct = s.endswith("%")
    raw = s.rstrip("%").strip()
    try:
        f = float(raw)
    except (TypeError, ValueError):
        return None
    if has_pct or f > 1.0:
        f = f / 100.0
    if f < 0 or f > 1:
        return None
    return round(f, 4)


_DATE_FORMATS = (
    "%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y",
    "%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y",
)


def _to_iso_date(v) -> str | None:
    s = _str_or_none(v)
    if s is None:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Encoding-safe CSV reader
# ---------------------------------------------------------------------------

def _read_csv_rows(path: Path) -> list[dict]:
    """Read a CSV into header-keyed dicts. Tries a few common encodings."""
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


def _norm_headers(row: dict) -> dict:
    """Return a copy of ``row`` with headers stripped + lowercased."""
    out = {}
    for k, v in row.items():
        if k is None:
            continue
        out[str(k).strip().lower()] = v
    return out


# Two different humans whose names slug the same, where the newcomer carries
# NO FanGraphs PlayerId - so neither _compute_fg_canonical_owners (which needs
# two distinct PIDs) nor scrapers._SPLIT_KEYS (which needs an MLBAM id in hand)
# can separate them, and the newcomer lands on the incumbent's key on EVERY
# board drop. Org is the only discriminator the CSV carries.
#
# carlos_castillo: the Angels OF (mlbam 837825, b.2008-09-15) vs the incumbent
# Pirates RHP (mlbam 807962, b.2006-02-04). Repaired once by
# tools/repair_carlos_castillo_collision.py after the 2026-07-23 board, then
# RE-MERGED by the 2026-08-02 board because the repair fixed the stored rows
# but nothing stopped the next ingest re-minting the bare key. Registered in
# scrapers._SPLIT_KEYS[("carlos_castillo", 837825)] -> the same target.
# The incumbent is never re-keyed; only the newcomer is routed.
_FG_ORG_SPLIT_KEYS: dict[tuple[str, str], str] = {
    ("carlos_castillo", "LAA"): "carlos_castillo_laa",
    # 2026-09-30 (census M02-11, tools/repair_identity_split_2026_09_30.py).
    # A board drop that lists only ONE of two same-slug humans has no PID
    # collision inside the drop, so the canonical-owner pass hands him the
    # bare key: the DET RHP Michael Massey (sa3037259, mlbam 695602) landed
    # on the KCR 2B's key from the 2026-07-23 and 2026-08-02 boards, and the
    # MIL SS Jose Rodriguez (sa3075073, mlbam 836624) is one MIL-only drop
    # away from the TOR RHP's key. The incumbents never played for DET / MIL.
    ("michael_massey", "DET"): "michael_massey__sa3037259",
    ("jose_rodriguez", "MIL"): "jose_rodriguez_836624",
}


def _row_id(row: dict) -> tuple[str, str | None]:
    """Compute (player_key, fg_player_id) join keys from a normalized row."""
    name = _str_or_none(row.get("name") or row.get("player"))
    if name is None:
        return ("", None)
    name = fix_mojibake(name)
    pid = _str_or_none(row.get("playerid") or row.get("player id"))
    key = normalize_key(name)
    org = (_str_or_none(row.get("org")) or "").strip().upper()
    key = _FG_ORG_SPLIT_KEYS.get((key, org), key)
    return (key, pid)


# ---------------------------------------------------------------------------
# Per-type row parsers
# ---------------------------------------------------------------------------

_TOOL_HITTER_COLS = (
    # (csv_header, canonical_tool_key)
    ("hit",       "hit"),
    ("game pwr",  "game_pwr"),
    ("raw pwr",   "raw_pwr"),
    ("spd",       "speed"),
    ("fld",       "field"),
    # v4 (2017-2020 new format) — the position CSV now carries Arm as a
    # pres/fut tool grade (it lived in the standalone physical CSV before).
    # Maps to the canonical 'throw' tool. Absent in 2021-2024 position
    # exports, so this is a no-op there (missing → None).
    ("arm",       "throw"),
    # FG publishes pitch_sel and bat_ctrl as single-value 20-80 grades
    # (no "/" split). They sit alongside the standard hitter tools as
    # first-class canonical keys — see scrapers.HITTER_TOOL_KEYS.
    ("pitch sel", "pitch_sel"),
    ("bat ctrl",  "bat_ctrl"),
)

_TOOL_PITCHER_COLS = (
    ("fb",  "fb"),
    ("sl",  "sl"),
    ("cb",  "cb"),
    ("ch",  "ch"),
    ("cmd", "cmd"),
)


def _parse_summary_row(raw: dict) -> dict | None:
    """Parse one row of summary-<slug>.csv. Returns a dict keyed by the
    canonical fields the rest of the pipeline cares about, or None when
    the row is missing the minimum identity columns."""
    row = _norm_headers(raw)
    pkey, fg_id = _row_id(row)
    if not pkey:
        return None

    name_clean = fix_mojibake(_str_or_none(row.get("name")) or "")
    _fv_val, _fv_plus = _parse_fv_full(_str_or_none(row.get("fv")) or "")
    return {
        "player_key":   pkey,
        "fg_player_id": _to_int(fg_id) if fg_id else None,
        # Raw string FG PlayerId preserved so cross-CSV disambiguation
        # can tell apart alphanumeric IDs (e.g. "sa3007992") that the
        # int-coerced field collapses to None.
        "fg_player_id_str": fg_id if fg_id else None,
        "player_name":  name_clean,
        "position":     _str_or_none(row.get("pos")),
        "org":          _str_or_none(row.get("org")),
        "rank":         _to_int(row.get("top 100")) or _to_int(row.get("rank")),
        "org_rank":     _to_int(row.get("org rk")),
        "fv":           _fv_val,
        "fv_plus":      _fv_plus,
        "current_level": _str_or_none(row.get("current level")),
        "eta_year":     _to_int(row.get("eta")),
        "risk":         _str_or_none(row.get("risk")),
        "trend":        _str_or_none(row.get("trend")),
        "age":          _to_float(row.get("age")),
        "height":       _str_or_none(row.get("ht") or row.get("height")),
        "weight":       _to_int(row.get("wt") or row.get("weight")),
        "bats":         _str_or_none(row.get("b") or row.get("bats")),
        "throws":       _str_or_none(row.get("t") or row.get("throws")),
        "sign_year":    _to_int(row.get("sign yr")),
        "sign_market":  _str_or_none(row.get("sign mkt")),
        "sign_org":     _str_or_none(row.get("sign org")),
        "bonus":        _to_int(row.get("bonus")),
        "signed_from":  _str_or_none(row.get("signed from")),
        "report":       _str_or_none(row.get("report")),
        "video_url":    _str_or_none(row.get("video")),
    }


def _parse_position_row(raw: dict) -> dict | None:
    """Hitter scouting board row. Tool grades arrive as 'pres / fut'."""
    row = _norm_headers(raw)
    pkey, fg_id = _row_id(row)
    if not pkey:
        return None
    out: dict = {
        "player_key":   pkey,
        "fg_player_id": _to_int(fg_id) if fg_id else None,
    }
    # Tools: (present, future) per slot.
    tools_fut: dict[str, float] = {}
    tools_pres: dict[str, float] = {}
    for hdr, key in _TOOL_HITTER_COLS:
        pres, fut = _parse_grade_pair(row.get(hdr))
        if fut is not None:
            tools_fut[key] = fut
        if pres is not None:
            tools_pres[key] = pres
    out["tools_future"] = tools_fut
    out["tools_present"] = tools_pres
    # Position scouting also publishes a few non-grade extras.
    # pitch_sel and bat_ctrl are now canonical hitter tools (parsed via
    # _TOOL_HITTER_COLS above) — no longer extracted here.
    out["contact_style"] = _str_or_none(row.get("con style"))
    out["versa"]         = _str_or_none(row.get("versa"))
    out["hard_hit_pct"]  = _to_pct(row.get("hard hit%"))
    # Older FG exports (2021-2024) publish raw exit-velo columns
    # alongside Hard Hit%. Land as decimal MPH in extras.
    out["avg_ev"]        = _to_float(row.get("avg ev"))
    out["max_ev"]        = _to_float(row.get("max ev"))
    # v4 (2017-2020 new format, draft boards) — physical grades folded into
    # the position CSV. None when the columns are absent (2021-2024 boards).
    out["frame"]         = _to_int(row.get("frame"))
    out["athl"]          = _to_int(row.get("athl"))
    out["perf"]          = _to_int(row.get("perf"))
    return out


def _parse_pitching_row(raw: dict) -> dict | None:
    row = _norm_headers(raw)
    pkey, fg_id = _row_id(row)
    if not pkey:
        return None
    out: dict = {
        "player_key":   pkey,
        "fg_player_id": _to_int(fg_id) if fg_id else None,
    }
    tools_fut: dict[str, float] = {}
    tools_pres: dict[str, float] = {}
    for hdr, key in _TOOL_PITCHER_COLS:
        pres, fut = _parse_grade_pair(row.get(hdr))
        if fut is not None:
            tools_fut[key] = fut
        if pres is not None:
            tools_pres[key] = pres
    out["tools_future"]  = tools_fut
    out["tools_present"] = tools_pres
    out["tj_date"]       = _to_iso_date(row.get("tj date"))
    out["fb_type"]       = _str_or_none(row.get("fb type"))
    out["sits"]          = _str_or_none(row.get("sits"))
    out["tops"]          = _str_or_none(row.get("tops"))
    # Statcast-style spin columns from older boards (2021-2024).
    out["rpm_fb"]        = _to_int(row.get("rpm fb"))
    out["rpm_break"]     = _to_int(row.get("rpm break"))
    # v4 (2017-2020 new format, draft boards) — physical grades folded into
    # the pitching CSV. None when absent (2021-2024 boards).
    out["frame"]         = _to_int(row.get("frame"))
    out["athl"]          = _to_int(row.get("athl"))
    out["perf"]          = _to_int(row.get("perf"))
    return out


def _parse_scouting_row(raw: dict) -> dict | None:
    """New-format consolidated scouting CSV (2017-2018 boards): one row per
    player carrying BOTH hitter tools (Hit/Game Pwr/Raw Pwr/Spd/Fld/Arm) and
    pitcher grades (FB/SL/CB/CH/CMD). FV is NOT here (it's on the summary
    row). A hitter has the hitter columns filled; a pitcher the pitch columns.
    Emits the same {tools_future, tools_present} shape as position/pitching so
    it merges through the same join path."""
    row = _norm_headers(raw)
    pkey, fg_id = _row_id(row)
    if not pkey:
        return None
    tools_fut: dict[str, float] = {}
    tools_pres: dict[str, float] = {}
    for hdr, key in (_TOOL_HITTER_COLS + _TOOL_PITCHER_COLS):
        pres, fut = _parse_grade_pair(row.get(hdr))
        if fut is not None:
            tools_fut[key] = fut
        if pres is not None:
            tools_pres[key] = pres
    return {
        "player_key":   pkey,
        "fg_player_id": _to_int(fg_id) if fg_id else None,
        "tools_future": tools_fut,
        "tools_present": tools_pres,
    }


def _parse_physical_row(raw: dict) -> dict | None:
    row = _norm_headers(raw)
    pkey, fg_id = _row_id(row)
    if not pkey:
        return None
    return {
        "player_key":   pkey,
        "fg_player_id": _to_int(fg_id) if fg_id else None,
        "frame":        _to_int(row.get("frame")),
        "athl":         _to_int(row.get("athl")),
        "levers":       _str_or_none(row.get("levers")),
        "arm":          _to_grade(row.get("arm")),
        "delivery":     _str_or_none(row.get("delivery")),
    }


_TYPE_PARSERS = {
    "summary":  _parse_summary_row,
    "position": _parse_position_row,
    "pitching": _parse_pitching_row,
    "scouting": _parse_scouting_row,
    "physical": _parse_physical_row,
}


# ---------------------------------------------------------------------------
# Auto-detect publish date
# ---------------------------------------------------------------------------

# FanGraphs publishes on a stable annual cycle. The slug names the user
# (or auto-classifier) puts on each report set encode which publication
# they belong to:
#
#   * Report     — preseason, late January / mid-February
#   * Updated    — trade deadline, late July / early August
#   * Graduated  — post-season, early November
#
# Hand-curated dates for each (year, kind) we've seen. Anything not in
# the table falls back to the type-defaults below, then to age-based
# back-solve if the slug doesn't match either pattern.
FG_PUBLICATION_CALENDAR: dict[tuple[int, str], str] = {
    # 2017-2020 historical backfill. FG's preseason board lands mid-Feb and
    # the trade-deadline update late-Jul/early-Aug; the exact day is
    # approximate but the YEAR (what the backtest buckets on) is exact.
    (2017, "report"):    "2017-02-15",
    (2018, "report"):    "2018-02-15",
    (2018, "updated"):   "2018-08-01",
    (2019, "report"):    "2019-02-13",
    (2019, "updated"):   "2019-07-31",
    (2020, "report"):    "2020-02-13",
    (2020, "updated"):   "2020-08-01",
    # 2021
    (2021, "report"):    "2021-02-26",
    (2021, "updated"):   "2021-07-30",
    (2021, "graduated"): "2021-11-08",
    # 2022
    (2022, "report"):    "2022-02-24",
    (2022, "updated"):   "2022-08-02",
    (2022, "graduated"): "2022-11-09",
    # 2023
    (2023, "report"):    "2023-02-23",
    (2023, "updated"):   "2023-08-01",
    (2023, "graduated"): "2023-11-06",
    # 2024
    (2024, "report"):    "2024-02-14",
    (2024, "updated"):   "2024-08-01",
    (2024, "graduated"): "2024-11-13",
    # 2025
    (2025, "report"):    "2025-02-13",
    (2025, "updated"):   "2025-07-31",
    (2025, "graduated"): "2025-11-13",
    # 2026
    (2026, "report"):    "2026-02-12",
    # Owner-confirmed publish date for the mid-season Updated board. Without
    # this entry the slug falls through to _FG_TYPE_DEFAULTS and dates itself
    # 2026-07-30, three days early, which would slot it AHEAD of the
    # 2026-07-23 trade-deadline drop by less than it should and mis-stamp the
    # FV-history point. The age back-solve is not the arbiter here: FG's Age
    # column is age as of EXPORT, so it reads 2026-08-02/03 for a board
    # published on the 2nd (median 08-03, p25 08-02 over 1,178 matched birth
    # dates) - which is why the calendar outranks it in _detect_publish_date.
    (2026, "updated"):   "2026-08-02",
}

# Slugs not in the table get this month/day per kind as a safe default.
_FG_TYPE_DEFAULTS: dict[str, tuple[int, int]] = {
    "report":    (2, 14),
    "updated":   (7, 30),
    "graduated": (11, 6),
}

# Slug parser: captures the publication year + kind from slugs like
# `2025updated`, `2025-updated`, `2024_Report`, `2023Graduated`,
# `2025graduates` (FG's later naming convention also accepts).
_FG_SLUG_RE = re.compile(
    r"^(?P<year>\d{4})[-_]?(?P<kind>report|updated|graduated|graduates)$",
    re.IGNORECASE,
)

# Explicit publish dates for TEAM-ARTICLE boards (slug -> ISO date). These
# articles don't match the FG board calendar, and the age-back-solve fallback
# can land a few days off the actual drop, so when we know the publish date we
# pin it here. Add an entry per ingested team article.
_ARTICLE_PUBLISH_DATES: dict[str, str] = {
    "tampa_bay_rays_2026": "2026-06-26",
}


def _resolve_calendar_date(slug: str) -> str | None:
    """Try to resolve `slug` to an FG publish date via the calendar
    table or the per-kind month/day defaults. Returns None when the
    slug doesn't match the (year, kind) pattern."""
    if not slug:
        return None
    m = _FG_SLUG_RE.match(slug)
    if not m:
        return None
    year = int(m.group("year"))
    kind = m.group("kind").lower()
    if kind == "graduates":
        kind = "graduated"  # FG used both names across years
    # Calendar table hit?
    iso = FG_PUBLICATION_CALENDAR.get((year, kind))
    if iso:
        return iso
    # Fallback: per-kind month/day defaults.
    md = _FG_TYPE_DEFAULTS.get(kind)
    if md is None:
        return None
    month, day = md
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _detect_publish_date(slug: str,
                         summary_rows: list[dict],
                         birth_dates: dict[str, str],
                         fallback_mtime: float | None = None,
                         today: date | None = None) -> str | None:
    """Resolve a publish date for one report set.

    Control flow:
      1. If `slug` matches `<year><kind>` (report/updated/graduated),
         return the hardcoded FG calendar date. This is the authoritative
         path — FG's cycle is stable, so we know within a few days when
         each board landed.
      2. Otherwise back-calculate `snapshot_date = birth_date + age ×
         365.25` from the summary rows, median across matched players.
      3. Final fallback: the latest CSV's file mtime.
    """
    today = today or date.today()
    # Calendar path — wins when the slug matches.
    cal = _resolve_calendar_date(slug)
    if cal is not None:
        log.info("fangraphs_csv: publish date %s for slug '%s' via "
                 "FG calendar table", cal, slug)
        return cal
    pinned = _ARTICLE_PUBLISH_DATES.get(slug)
    if pinned is not None:
        log.info("fangraphs_csv: publish date %s for slug '%s' via "
                 "article-publish-date override", pinned, slug)
        return pinned
    earliest = date(2018, 1, 1)
    estimates: list[date] = []
    for row in summary_rows:
        pkey = row.get("player_key")
        age = row.get("age")
        if not pkey or age is None or age <= 0 or age > 60:
            continue
        bd_iso = birth_dates.get(pkey)
        if not bd_iso:
            continue
        try:
            bd = date.fromisoformat(bd_iso)
        except ValueError:
            continue
        days = age * 365.25
        est = bd + timedelta(days=days)
        if earliest <= est <= today + timedelta(days=2):
            estimates.append(est)

    # ≥2 estimates is enough for a meaningful median; real FG exports
    # carry hundreds of rows so this gate is satisfied trivially. Less
    # than 2 estimates falls through to the mtime fallback. Single-row
    # edge cases (where one stale birth date could skew the result)
    # also fall through — better to use mtime than trust one estimate.
    if len(estimates) >= 2:
        ord_vals = sorted(d.toordinal() for d in estimates)
        med = ord_vals[len(ord_vals) // 2]
        result = date.fromordinal(med)
        log.info("fangraphs_csv: auto-detected publish date %s "
                 "(median of %d age-back-solves)",
                 result.isoformat(), len(estimates))
        return result.isoformat()

    if fallback_mtime is not None:
        result = date.fromtimestamp(fallback_mtime)
        if earliest <= result <= today + timedelta(days=2):
            log.warning("fangraphs_csv: only %d age-based date estimates "
                        "available; falling back to file mtime → %s",
                        len(estimates), result.isoformat())
            return result.isoformat()

    log.warning("fangraphs_csv: could not determine publish date "
                "(%d estimates, no usable mtime)", len(estimates))
    return None


# ---------------------------------------------------------------------------
# Join four CSVs into per-player merged dicts
# ---------------------------------------------------------------------------

def _join_report_set(summary_rows: list[dict],
                     position_rows: list[dict],
                     pitching_rows: list[dict],
                     physical_rows: list[dict],
                     scouting_rows: list[dict] | None = None) -> list[dict]:
    """Join the four per-type row lists by FG PlayerId (preferred) with
    a name-key fallback. Summary is the spine — only summary players
    appear in the output. Other rows that don't match are dropped with
    a debug log.

    When two summary rows share the same name-key but have different FG
    PlayerIds (e.g. "Julio Rodríguez" the M's superstar vs. "Julio
    Rodriguez" the SFG SIRP — both normalize to `julio_rodriguez`), the
    higher-FV row wins the bare key and the loser is dropped with a
    warning. This trades off completeness for accuracy: the prominent
    prospect users actually look up keeps the canonical key, instead of
    being silently overwritten by an org-filler with the same name."""
    by_pid: dict[int, dict] = {}
    by_key: dict[str, dict] = {}
    for r in summary_rows:
        if r is None:
            continue
        pk = r["player_key"]
        existing = by_key.get(pk)
        if existing is not None:
            # Same name-key appearing twice in a single summary CSV is
            # always a collision — two distinct humans normalize to the
            # same key (e.g. "Julio Rodríguez" and "Julio Rodriguez").
            # We can't rely on fg_player_id mismatch alone because
            # non-MLB prospects have alphanumeric IDs like "sa829387"
            # that get coerced to None by `_to_int()`, so both rows look
            # PID-less. Higher-FV row wins the bare key; loser is logged.
            ex_fv = existing.get("fv") or 0
            new_fv = r.get("fv") or 0
            keep, drop = (r, existing) if new_fv > ex_fv else (existing, r)
            log.warning(
                "fangraphs_csv: name-key collision on %s — keeping "
                "fg_id=%s fv=%s org=%s, dropping fg_id=%s fv=%s org=%s",
                pk, keep.get("fg_player_id"), keep.get("fv"), keep.get("org"),
                drop.get("fg_player_id"), drop.get("fv"), drop.get("org"),
            )
            by_key[pk] = keep
        else:
            by_key[pk] = r
        if r.get("fg_player_id") is not None:
            by_pid[r["fg_player_id"]] = by_key[pk]

    def _lookup(other_row: dict) -> dict | None:
        if other_row is None:
            return None
        pid = other_row.get("fg_player_id")
        if pid is not None and pid in by_pid:
            return by_pid[pid]
        return by_key.get(other_row.get("player_key"))

    for r in position_rows or []:
        host = _lookup(r)
        if host is None:
            continue
        host.setdefault("_position", r)
    for r in pitching_rows or []:
        host = _lookup(r)
        if host is None:
            continue
        host.setdefault("_pitching", r)
    for r in physical_rows or []:
        host = _lookup(r)
        if host is None:
            continue
        host.setdefault("_physical", r)
    for r in scouting_rows or []:
        host = _lookup(r)
        if host is None:
            continue
        host.setdefault("_scouting", r)

    return list(by_key.values())


# ---------------------------------------------------------------------------
# Build a Snapshot from a merged row
# ---------------------------------------------------------------------------

def _build_snapshot(merged: dict, slug: str, snapshot_date: str) -> Snapshot:
    """Convert a merged summary+position+pitching+physical row into one
    Snapshot. Future grades land canonically; present grades + all
    non-grade fields land under ``_extras``."""
    tools_future: dict[str, float] = {}
    tools_present: dict[str, float] = {}
    pos_block = merged.get("_position") or {}
    pit_block = merged.get("_pitching") or {}
    phys_block = merged.get("_physical") or {}
    scout_block = merged.get("_scouting") or {}

    # Consolidated 2017-2018 scouting CSV carries both hitter + pitcher tools.
    tools_future.update(scout_block.get("tools_future") or {})
    tools_future.update(pos_block.get("tools_future") or {})
    tools_future.update(pit_block.get("tools_future") or {})
    tools_present.update(scout_block.get("tools_present") or {})
    tools_present.update(pos_block.get("tools_present") or {})
    tools_present.update(pit_block.get("tools_present") or {})

    extras: dict = {}

    # Summary extras. fg_player_id_str is carried alongside the int id so the
    # "View on FanGraphs" source link resolves for minor leaguers too - their
    # FG ids are alphanumeric ("sa3007992"), which _to_int collapses to None.
    for k in ("risk", "trend", "eta_year", "current_level", "org_rank",
              "age", "height", "weight", "bats", "throws",
              "sign_year", "sign_market", "sign_org", "bonus",
              "signed_from", "video_url", "fg_player_id", "fg_player_id_str"):
        v = merged.get(k)
        if v is not None and v != "":
            extras[k] = v
    rpt = merged.get("report")
    if rpt:
        from scrapers import _clean_report_prose
        cleaned = _clean_report_prose(rpt)
        if cleaned:
            extras["report"] = cleaned[:_REPORT_MAX_CHARS]

    # Position-block extras. pitch_sel and bat_ctrl now ride as
    # canonical hitter tools in tools_future (see _TOOL_HITTER_COLS).
    for k in ("contact_style", "versa", "hard_hit_pct", "avg_ev", "max_ev"):
        v = pos_block.get(k)
        if v is not None and v != "":
            extras[k] = v

    # Pitching-block extras.
    for k in ("tj_date", "fb_type", "sits", "tops", "rpm_fb", "rpm_break"):
        v = pit_block.get(k)
        if v is not None and v != "":
            extras[k] = v

    # Physical-block extras. frame/athl/perf may now arrive folded into the
    # position/pitching CSV (new format) instead of a standalone physical CSV.
    # (arm in the new position CSV is the 'throw' TOOL, already in tools_future
    # above — not surfaced here as a physical extra.)
    for k in ("frame", "athl", "perf"):
        v = phys_block.get(k)
        if v is None:
            v = pos_block.get(k) if pos_block.get(k) is not None else pit_block.get(k)
        if v is not None and v != "":
            extras[k] = v
    for k in ("levers", "arm", "delivery"):
        v = phys_block.get(k)
        if v is not None and v != "":
            extras[k] = v

    if tools_present:
        extras["present"] = tools_present

    tools_payload: dict | None = None
    if tools_future or extras:
        tools_payload = dict(tools_future)
        if extras:
            tools_payload["_extras"] = extras

    return Snapshot(
        source="fangraphs",
        snapshot_date=snapshot_date,
        interval_label=slug,
        player_key=merged["player_key"],
        player_name=merged["player_name"],
        position=merged.get("position"),
        org=merged.get("org"),
        rank=merged.get("rank") or merged.get("org_rank"),
        fv=merged.get("fv"),
        status="active",
        tools=tools_payload,
        fv_plus=bool(merged.get("fv_plus", False)),
    )


# ---------------------------------------------------------------------------
# Group files by slug
# ---------------------------------------------------------------------------

def _group_drops(files: list[Path]) -> list[dict]:
    """Walk a list of *.csv paths, group by (slug), return one entry
    per slug as a dict with keys for whichever types are present. Files
    whose names don't match the convention are reported via a sentinel
    'unparseable' list returned alongside."""
    groups: dict[str, dict] = defaultdict(dict)
    for p in files:
        parsed = _parse_filename(p.name)
        if not parsed:
            groups.setdefault("__unparseable__", {}).setdefault("_files", []).append(p)
            continue
        ftype, slug = parsed
        groups[slug][ftype] = p
        groups[slug].setdefault("slug", slug)
    return [g for slug, g in sorted(groups.items()) if slug != "__unparseable__"] + (
        [{"slug": "__unparseable__", "_files": groups["__unparseable__"]["_files"]}]
        if "__unparseable__" in groups else []
    )


# ---------------------------------------------------------------------------
# Content-based CSV type classifier
# ---------------------------------------------------------------------------

def _classify_csv(headers: list[str] | set[str]) -> str | None:
    """Decide which of {summary, position, pitching, physical} a CSV is
    by looking at its header set. Returns None when no signature
    matches. Used by the subfolder layout where files can have any name.

    Signatures (normalized to lowercase + stripped):
      summary  → has 'report' column (the long scouting prose)
      position → has 'hit' + at least one of {pitch sel, versa, con style}
      pitching → has 'fb type' OR 'tj date'
      physical → has both 'frame' and 'athl'
    """
    norm = {str(h).strip().lower() for h in (headers or [])}
    if "report" in norm:
        return "summary"
    # New-format consolidated scouting CSV: hitter tools AND pitch grades in
    # one file, no FV. Distinguish from pitching (no 'tj date'/'fb type') and
    # from position (no 'pitch sel'/'versa'/'con style'). Check before the
    # pitching/position signatures so it isn't mis-claimed.
    if ("hit" in norm and "fb" in norm and "cmd" in norm
            and "tj date" not in norm and "fb type" not in norm
            and "pitch sel" not in norm and "versa" not in norm):
        return "scouting"
    if "fb type" in norm or "tj date" in norm:
        return "pitching"
    if "hit" in norm and (
        "pitch sel" in norm or "versa" in norm or "con style" in norm
    ):
        return "position"
    if "frame" in norm and "athl" in norm:
        return "physical"
    return None


def _sniff_headers(path: Path) -> list[str]:
    """Read just the first line of a CSV to get its header list. Returns
    an empty list when the file can't be decoded with any known
    encoding."""
    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            with path.open(encoding=enc, newline="") as f:
                reader = csv.reader(f)
                try:
                    return next(reader)
                except StopIteration:
                    return []
        except UnicodeDecodeError:
            continue
    return []


def _group_subfolders(drop_dir: Path) -> list[dict]:
    """Walk one-level-deep subfolders of the drop dir. Each subfolder
    is one report set; the folder name is the slug; the CSVs inside
    auto-classify by content. Returns a list of group dicts identical
    in shape to those produced by `_group_drops()`."""
    out: list[dict] = []
    if not drop_dir.is_dir():
        return out
    for sub in sorted(drop_dir.iterdir()):
        if not sub.is_dir():
            continue
        if sub.name == "processed":
            continue
        if sub.name.startswith("."):
            continue
        csvs = sorted(p for p in sub.glob("*.csv") if p.is_file())
        if not csvs:
            continue
        grp: dict = {"slug": sub.name, "_is_subfolder": True,
                     "_folder": sub, "_unclassified": []}
        for path in csvs:
            headers = _sniff_headers(path)
            ftype = _classify_csv(headers)
            if ftype is None:
                grp["_unclassified"].append(path)
                continue
            if ftype in grp:
                # Two files of the same type in one report set — keep the
                # newer mtime, log the duplicate.
                log.warning("fangraphs_csv: duplicate %s CSV in '%s' "
                            "(%s and %s); keeping the newer file",
                            ftype, sub.name, grp[ftype].name, path.name)
                if path.stat().st_mtime > grp[ftype].stat().st_mtime:
                    grp[ftype] = path
                continue
            grp[ftype] = path
        out.append(grp)
    return out


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def ingest_drops(today: date | None = None,
                 drop_dir: Path | None = None,
                 processed_dir: Path | None = None,
                 birth_dates: dict[str, str] | None = None,
                 called_from_run_monthly: bool = False) -> tuple[int, int]:
    """Scan the drop folder, group CSVs by slug, ingest each report set.

    Two layouts supported (use whichever is more convenient — they can
    coexist in the same drop folder):

    1. **Subfolder per report set** (preferred): each report set lives
       in its own subfolder. Folder name = slug. CSVs inside can have
       any name; their type is detected from the column headers via
       `_classify_csv()`.

    2. **Legacy flat layout**: CSVs at the root of the drop folder
       named `<type>-<slug>.csv` (e.g. `summary-2025_Updated.csv`).

    On success, the whole subfolder (layout 1) or the individual files
    (layout 2) move into `processed/<slug>__<date>/` so the same drop
    isn't re-ingested on a subsequent run.

    **IMPORTANT: This only writes to the snapshots DB.** The frontend
    serves `data/timeseries.json`, which is regenerated by
    `export_timeseries_json()` inside `run_monthly.py`. If you call
    `ingest_drops()` directly (not via `run_monthly.py`), you MUST
    follow up with `python run_monthly.py --rebuild-only` to refresh
    the JSON. The function prints a reminder line when this is needed.

    Args:
      called_from_run_monthly: pass True from inside `run_monthly.py`
        so the standalone-rebuild hint is suppressed.

    Returns ``(snapshots_inserted, report_sets_processed)``.
    """
    today = today or date.today()
    drop_dir = drop_dir or DROP_DIR
    processed_dir = processed_dir or PROCESSED_DIR
    drop_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    # Lazy DB import so unit tests can stub insert_snapshots without
    # paying for the DB connection on import.
    from storage import insert_snapshots, load_birth_dates
    if birth_dates is None:
        try:
            birth_dates = load_birth_dates()
        except Exception:
            log.exception("fangraphs_csv: load_birth_dates failed; "
                          "falling back to mtime-only date detection")
            birth_dates = {}

    # Two-pass collection: subfolders first (new layout), then loose
    # CSVs at the drop-dir root (legacy <type>-<slug>.csv pattern).
    groups: list[dict] = []
    groups.extend(_group_subfolders(drop_dir))
    loose_files = sorted(p for p in drop_dir.glob("*.csv") if p.is_file())
    if loose_files:
        groups.extend(_group_drops(loose_files))

    if not groups:
        return 0, 0

    # Cross-CSV canonical-owner map. Pre-scan every summary CSV so the
    # build path can suffix the player_key when a row's fg_player_id
    # doesn't match the dominant owner of that name across all cycles.
    # This prevents two distinct humans sharing a name (e.g. Julio
    # Rodríguez M's CF vs. Julio Rodriguez SFG SIRP) from merging into
    # one prospect profile.
    summary_groups = [g for g in groups if g.get("summary")]
    canonical_owners = _compute_fg_canonical_owners(summary_groups)
    if canonical_owners:
        log.info("fangraphs_csv: %d cross-CSV name collisions detected; "
                 "disambiguating by fg_player_id", len(canonical_owners))

    # Slug-router gate: hand any <year>draft slug off to draft_csv. Done
    # before any per-set processing so amateur prospect rows can never land
    # in the MiLB snapshots table. The handoff happens once per ingest
    # call regardless of how many draft sets are present — draft_csv has
    # its own subfolder walker.
    try:
        from draft_csv import is_draft_slug, ingest_drops as _draft_ingest
        draft_groups = [g for g in groups if is_draft_slug(g.get("slug", ""))]
    except ImportError:
        draft_groups = []
    if draft_groups:
        log.info("fangraphs_csv: %d draft set(s) detected; routing to draft_csv",
                 len(draft_groups))
        try:
            _draft_ingest(drop_dir=drop_dir, processed_dir=processed_dir)
        except Exception:
            log.exception("fangraphs_csv: draft_csv ingest crashed")
        draft_slugs = {g["slug"] for g in draft_groups}
        groups = [g for g in groups if g.get("slug") not in draft_slugs]

    # Same routing pattern for <year>overseas slugs → overseas_csv. Keeps
    # KBO/NPB pros out of the MiLB snapshots table.
    try:
        from overseas_csv import is_overseas_slug, ingest_drops as _overseas_ingest
        overseas_groups = [g for g in groups if is_overseas_slug(g.get("slug", ""))]
    except ImportError:
        overseas_groups = []
    if overseas_groups:
        log.info("fangraphs_csv: %d overseas set(s) detected; routing to overseas_csv",
                 len(overseas_groups))
        try:
            _overseas_ingest(drop_dir=drop_dir, processed_dir=processed_dir)
        except Exception:
            log.exception("fangraphs_csv: overseas_csv ingest crashed")
        overseas_slugs = {g["slug"] for g in overseas_groups}
        groups = [g for g in groups if g.get("slug") not in overseas_slugs]

    inserted_total = 0
    sets_processed = 0
    for grp in groups:
        if grp.get("slug") == "__unparseable__":
            for p in grp.get("_files", []):
                log.warning("fangraphs_csv: skipping %s — filename does "
                            "not match <type>-<slug>.csv and no recognized "
                            "header signature", p.name)
            continue
        slug = grp["slug"]
        if "summary" not in grp:
            present = sorted(k for k in grp
                             if k not in {"slug", "_is_subfolder", "_folder",
                                          "_unclassified"})
            log.warning("fangraphs_csv: skipping report set '%s' — missing "
                        "summary CSV (have: %s)", slug, present)
            continue
        n, ok = _process_one_set(grp, slug, birth_dates, today,
                                 processed_dir, insert_snapshots,
                                 canonical_owners=canonical_owners)
        if ok:
            inserted_total += n
            sets_processed += 1

    log.info("fangraphs_csv: ingested %d snapshots from %d report-set(s)",
             inserted_total, sets_processed)

    # Reminder for standalone callers: just writing to the DB isn't
    # enough — the timeseries.json export must be rebuilt for the
    # website to see the new data.
    if inserted_total > 0 and not called_from_run_monthly:
        log.info("fangraphs_csv: %d new snapshots inserted into the DB. "
                 "Run 'python run_monthly.py --rebuild-only' to push the "
                 "new data into data/timeseries.json so the website "
                 "picks it up.", inserted_total)
    return inserted_total, sets_processed


# ---------------------------------------------------------------------------
# Cross-CSV player_key disambiguation
# ---------------------------------------------------------------------------

def _compute_fg_canonical_owners(groups: list[dict]) -> dict[str, str]:
    """Pre-scan every summary CSV across all report sets, return a map
    ``{player_key: canonical_fg_player_id_str}`` for keys that need
    disambiguation.

    The canonical owner of a colliding name-key is the FG PlayerId with
    the most cycle appearances (tiebreak: highest max FV across cycles).
    Snapshots whose fg_player_id differs from the canonical owner get
    their player_key suffixed with the PID at build time, so two distinct
    humans sharing a name never end up merged on the same prospect.

    Players whose name-key has only one PID across the entire run aren't
    added to the map — no disambiguation needed.
    """
    # {pkey: {pid_str: (cycle_count, max_fv)}}
    seen: dict[str, dict[str | None, list[float]]] = {}
    for grp in groups:
        path = grp.get("summary")
        if path is None:
            continue
        for raw in _read_csv_rows(path):
            try:
                parsed = _parse_summary_row(raw)
            except Exception:
                continue
            if not parsed:
                continue
            pkey = parsed["player_key"]
            pid = parsed.get("fg_player_id_str")
            fv = parsed.get("fv") or 0.0
            seen.setdefault(pkey, {}).setdefault(pid, []).append(fv)

    owners: dict[str, str] = {}
    for pkey, by_pid in seen.items():
        # Only PIDs that are non-None can be canonical owners. A row
        # with a known PID always wins over a PID-less duplicate so
        # the unknown-PID rows get suffixed (with the literal token
        # "noid") and the known person keeps the bare key.
        if len(by_pid) <= 1:
            continue
        # Score: (cycle_count, max_fv) — bigger wins. Sort by the
        # score tuple only (PIDs can be None, which is not orderable
        # against str in Python 3).
        scored = [((len(fvs), max(fvs)), pid) for pid, fvs in by_pid.items()]
        scored.sort(key=lambda x: x[0], reverse=True)
        canonical_pid = scored[0][1]
        if canonical_pid is not None:
            owners[pkey] = canonical_pid
        else:
            # Edge case: every PID is None for this pkey (multiple un-IDed
            # humans share a name). Use a sentinel so all of them get
            # suffixed with "__noid_<index>" by the suffix logic later.
            owners[pkey] = "__all_noid__"
    return owners


def _disambiguate_key(player_key: str,
                      row_pid_str: str | None,
                      canonical_owners: dict[str, str]) -> str:
    """Return the player_key the snapshot should be stored under.

    Bare key when this row's PID matches the canonical owner (or no
    canonical owner exists for this name). Suffixed key when the row is
    for a different human than the canonical owner — e.g. the SFG SIRP
    Julio Rodriguez becomes `julio_rodriguez__sa3007992` while the
    Mariners CF (PID 23697, canonical) keeps `julio_rodriguez`.
    """
    canonical = canonical_owners.get(player_key)
    if canonical is None:
        return player_key
    if canonical == "__all_noid__":
        # Every collision row is PID-less. Suffix all of them with a
        # short hash of the player_name so they stay distinct.
        suffix = (row_pid_str or "noid").replace("/", "_")
        return f"{player_key}__{suffix}"
    if row_pid_str == canonical:
        return player_key
    suffix = (row_pid_str or "noid").replace("/", "_")
    return f"{player_key}__{suffix}"


def _process_one_set(grp: dict, slug: str, birth_dates: dict[str, str],
                     today: date, processed_dir: Path,
                     insert_fn,
                     canonical_owners: dict[str, str] | None = None) -> tuple[int, bool]:
    """Parse the four CSVs in one slug-group, build snapshots, insert,
    move files to processed/. Returns (n_inserted, success)."""
    parsed_by_type: dict[str, list[dict]] = {}
    mtimes: list[float] = []
    for ftype in ("summary", "position", "pitching", "scouting", "physical"):
        path = grp.get(ftype)
        if path is None:
            parsed_by_type[ftype] = []
            continue
        try:
            mtimes.append(path.stat().st_mtime)
        except OSError:
            pass
        raw_rows = _read_csv_rows(path)
        parser = _TYPE_PARSERS[ftype]
        parsed: list[dict] = []
        skipped = 0
        for r in raw_rows:
            try:
                p = parser(r)
            except Exception:
                log.exception("fangraphs_csv: parser crashed on %s row", ftype)
                skipped += 1
                continue
            if p is None:
                skipped += 1
                continue
            parsed.append(p)
        if skipped:
            log.info("fangraphs_csv: %s — skipped %d unparseable rows in %s",
                     path.name, skipped, ftype)
        parsed_by_type[ftype] = parsed

    summary_rows = parsed_by_type["summary"]
    if not summary_rows:
        log.warning("fangraphs_csv: report set '%s' produced 0 summary rows", slug)
        return 0, False

    fallback_mtime = max(mtimes) if mtimes else None
    snapshot_date = _detect_publish_date(
        slug, summary_rows, birth_dates,
        fallback_mtime=fallback_mtime, today=today,
    )
    if not snapshot_date:
        log.warning("fangraphs_csv: report set '%s' — could not determine "
                    "publish date; leaving files in place", slug)
        return 0, False

    merged = _join_report_set(
        summary_rows,
        parsed_by_type["position"],
        parsed_by_type["pitching"],
        parsed_by_type["physical"],
        parsed_by_type.get("scouting"),
    )
    owners = canonical_owners or {}
    snapshots = []
    for m in merged:
        snap = _build_snapshot(m, slug, snapshot_date)
        if owners:
            disambiguated = _disambiguate_key(
                snap.player_key, m.get("fg_player_id_str"), owners,
            )
            if disambiguated != snap.player_key:
                log.info(
                    "fangraphs_csv: disambiguating %s → %s "
                    "(fg_pid=%s differs from canonical %s)",
                    snap.player_key, disambiguated,
                    m.get("fg_player_id_str"), owners.get(snap.player_key),
                )
                # dataclasses.replace would be cleaner but Snapshot is
                # an @dataclass(frozen=False) so direct assignment works.
                snap = snap.__class__(
                    source=snap.source,
                    snapshot_date=snap.snapshot_date,
                    interval_label=snap.interval_label,
                    player_key=disambiguated,
                    player_name=snap.player_name,
                    position=snap.position,
                    org=snap.org,
                    rank=snap.rank,
                    fv=snap.fv,
                    status=snap.status,
                    tools=snap.tools,
                )
        snapshots.append(snap)
    try:
        n = insert_fn(snapshots)
    except Exception:
        log.exception("fangraphs_csv: insert_snapshots failed on slug %s", slug)
        return 0, False

    # Move the whole report set into `processed/<slug>__<date>/`.
    # Subfolder layout: rename the entire folder. Flat layout: move
    # each typed CSV one at a time + any unclassified loose files that
    # came along for the ride.
    set_dest = processed_dir / f"{slug}__{snapshot_date}"
    if grp.get("_is_subfolder") and grp.get("_folder"):
        try:
            shutil.move(str(grp["_folder"]), str(set_dest))
        except Exception:
            log.exception("fangraphs_csv: could not move folder %s "
                          "to processed/", grp["_folder"])
    else:
        set_dest.mkdir(parents=True, exist_ok=True)
        for ftype in ("summary", "position", "pitching", "scouting", "physical"):
            src = grp.get(ftype)
            if src is None:
                continue
            try:
                shutil.move(str(src), str(set_dest / src.name))
            except Exception:
                log.exception("fangraphs_csv: could not move %s to processed/",
                              src.name)
    log.info("fangraphs_csv: ingested %d snapshots from report-set "
             "(slug=%s, date=%s, rows=%d)",
             n, slug, snapshot_date, len(snapshots))
    return n, True


# ---------------------------------------------------------------------------
# One-shot: backfill publish dates on already-ingested fangraphs snapshots
# ---------------------------------------------------------------------------

def backfill_fg_player_ids(db_path: Path | None = None) -> dict:
    """One-shot migration: FanGraphs boards ingested before 2026-06-25 stored no
    FanGraphs PlayerId for alphanumeric ("sa...") minor-league ids - the int-only
    field collapsed them to None, and fg_player_id_str was not persisted yet - so
    the "View on FanGraphs" scouting-report links are missing for those players.

    This rebuilds a player_key -> FG id map by re-parsing the processed summary
    CSVs, then stamps ``_extras.fg_player_id_str`` into any fangraphs snapshot
    whose tools_json lacks a FG id. Idempotent: rows that already carry an id are
    skipped, and existing _extras keys are preserved. Run once, then re-export
    (scout_reports.json regenerates the ``_ids.fangraphs`` map). Returns a summary
    ``{"csv_ids", "examined", "updated"}``."""
    import sqlite3
    import json as _json
    import glob
    from contextlib import closing
    from storage import DB_PATH
    path = db_path or DB_PATH

    # 1) canonical player_key -> FG id (string form preferred so "sa..." survives),
    #    latest CSV wins.
    id_map: dict[str, str] = {}
    csv_paths = sorted(glob.glob(str(_BASE / "data" / "fangraphs_imports" / "processed"
                                     / "**" / "summary-*.csv"), recursive=True))
    csv_paths += sorted(glob.glob(str(_BASE / "data" / "fangraphs_articles" / "summary-*.csv")))
    for cp in csv_paths:
        for raw in _read_csv_rows(Path(cp)):
            p = _parse_summary_row(raw)
            if not p:
                continue
            fid = p.get("fg_player_id_str") or (
                str(p["fg_player_id"]) if p.get("fg_player_id") is not None else None)
            if p.get("player_key") and fid:
                id_map[p["player_key"]] = fid

    # 2) stamp the id into fangraphs snapshots that have none.
    n_updated = n_examined = 0
    with closing(sqlite3.connect(str(path))) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT id, player_key, tools_json FROM snapshots WHERE source = 'fangraphs'"
        ).fetchall()
        for r in rows:
            n_examined += 1
            fid = id_map.get(r["player_key"])
            if not fid:
                continue
            try:
                tj = _json.loads(r["tools_json"]) if r["tools_json"] else {}
            except (ValueError, TypeError):
                continue
            ex = tj.get("_extras")
            if not isinstance(ex, dict):
                ex = {}
                tj["_extras"] = ex
            if ex.get("fg_player_id_str") or ex.get("fg_player_id") is not None:
                continue   # already linkable - idempotent
            ex["fg_player_id_str"] = fid
            con.execute("UPDATE snapshots SET tools_json = ? WHERE id = ?",
                        (_json.dumps(tj), r["id"]))
            n_updated += 1
        con.commit()
    return {"csv_ids": len(id_map), "examined": n_examined, "updated": n_updated}
