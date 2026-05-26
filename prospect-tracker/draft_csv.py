"""Draft prospect CSV ingest — mirror of fangraphs_csv.py for amateurs.

The draft-class FG board CSVs have the SAME 4-file shape as the standard
board (summary/position/pitching/physical), but the summary header is
different and lacks the `Org` / `Org Rk` columns that the MiLB pipeline
depends on. Routing those rows through fangraphs_csv would pollute the
MiLB queries with amateur prospects (no MLB org, no MiLB level, NCAA
stats incompatible with RPS+).

Slug convention: `<year>draft` (e.g. `2024draft`, `2026draft`). The
ingest router in run_monthly inspects the slug and hands these off
here instead of fangraphs_csv.ingest_drops().

Reuses fangraphs_csv helpers (filename parsing, header normalization,
coercers, encoding-safe reader, position/pitching/physical row parsers)
so the four sub-CSV shapes stay in lockstep with the MiLB ingest.
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
    _parse_grade_pair,
    _parse_pitching_row,
    _parse_position_row,
    _parse_physical_row,
    _read_csv_rows,
    _row_id,
    _sniff_headers,
    _str_or_none,
    _to_float,
    _to_grade,
    _to_int,
)
from scrapers import _parse_fv, _parse_fv_full, fix_mojibake, normalize_key
from storage import (
    insert_draft_snapshots,
    upsert_draft_results,
)

log = logging.getLogger(__name__)


_BASE = Path(__file__).parent
DROP_DIR = _BASE / "data" / "fangraphs_imports"
PROCESSED_DIR = DROP_DIR / "processed"

_REPORT_MAX_CHARS = 8000


# ---------------------------------------------------------------------------
# Slug parsing — draft CSVs are <year>draft (no kind suffix).
# ---------------------------------------------------------------------------

_DRAFT_SLUG_RE = re.compile(r"^(?P<year>20\d\d)[-_]?draft$", re.IGNORECASE)


def is_draft_slug(slug: str) -> int | None:
    """Return the draft year for a draft slug, or None if not a draft slug."""
    if not slug:
        return None
    m = _DRAFT_SLUG_RE.match(slug)
    if not m:
        return None
    return int(m.group("year"))


def draft_player_key(draft_year: int, player_name: str) -> str:
    """Canonical key for an amateur prospect: 'draft_<year>_<name_slug>'.
    Keeps amateurs out of the MiLB player_key namespace so a hypothetical
    pro with the same name never collides until promotion."""
    name_slug = normalize_key(player_name)
    return f"draft_{draft_year}_{name_slug}"


# ---------------------------------------------------------------------------
# Draft-specific summary parser
# ---------------------------------------------------------------------------

# Draft summary header (FG):
#   Pre-draft:  Rank, Top 100, Trend, Name, Pos, Player Type, Age, Ht, Wt, B, T,
#               School, College Commit, FV, Risk, Report, Video, PlayerId
#   Post-draft: Rank, Top 100, Pick,  Name, Pos, Player Type, Age, Ht, Wt, B, T,
#               School, College Commit, FV, Risk, Report, Video, PlayerId
# `Pick` column carries "<overall>/<org>" (e.g. "7/STL").
_PICK_RE = re.compile(r"^\s*(\d{1,3})\s*/\s*([A-Z]{2,4})\s*$")


def _parse_pick_cell(cell: str | None) -> tuple[int | None, str | None]:
    if not cell:
        return (None, None)
    m = _PICK_RE.match(str(cell).strip())
    if not m:
        return (None, None)
    return (int(m.group(1)), m.group(2))


def _parse_draft_summary_row(raw: dict, draft_year: int) -> dict | None:
    """Parse one summary-<year>draft.csv row into a normalized dict."""
    row = _norm_headers(raw)
    pkey_milb, fg_id = _row_id(row)  # MiLB-style key — used only for FG ID
    name = _str_or_none(row.get("name"))
    if not name:
        return None
    name = fix_mojibake(name)
    pkey = draft_player_key(draft_year, name)
    rank = _to_int(row.get("rank"))
    pick_overall, pick_team = _parse_pick_cell(row.get("pick"))
    _fv_val, _fv_plus = _parse_fv_full(_str_or_none(row.get("fv")) or "")
    return {
        "player_key":    pkey,
        "player_name":   name,
        "fg_player_id":  fg_id,
        "position":      _str_or_none(row.get("pos")),
        "school":        _str_or_none(row.get("school")),
        "college_commit": _str_or_none(row.get("college commit")),
        "player_type":   _str_or_none(row.get("player type")),
        "draft_year":    draft_year,
        "rank":          rank,
        "top_100":       _to_int(row.get("top 100")),
        "fv":            _fv_val,
        "fv_plus":       _fv_plus,
        "risk":          _str_or_none(row.get("risk")),
        "age":           _to_float(row.get("age")),
        "height":        _str_or_none(row.get("ht") or row.get("height")),
        "weight":        _to_int(row.get("wt") or row.get("weight")),
        "bats":          _str_or_none(row.get("b") or row.get("bats")),
        "throws":        _str_or_none(row.get("t") or row.get("throws")),
        "report":        _str_or_none(row.get("report")),
        "video_url":     _str_or_none(row.get("video")),
        "pick_overall":  pick_overall,
        "pick_team":     pick_team,
        "trend":         _str_or_none(row.get("trend")),
    }


# ---------------------------------------------------------------------------
# Join: merge summary + position + pitching + physical by player_key
# ---------------------------------------------------------------------------

def _join_draft_set(summary_rows: list[dict],
                    position_rows: list[dict],
                    pitching_rows: list[dict],
                    physical_rows: list[dict],
                    draft_year: int) -> list[dict]:
    """Merge the per-type rows on player_key. Summary is the spine."""
    by_key: dict[str, dict] = {s["player_key"]: s for s in summary_rows if s}

    # Position/pitching/physical use MiLB-style normalize_key, not the
    # draft_<year>_ prefixed key. Re-key them so the join lines up.
    def _rekey(rows):
        out: dict[str, dict] = {}
        for r in rows:
            if not r:
                continue
            mp = r.get("player_key")
            if not mp:
                continue
            # MiLB-style key is normalize_key(name). Find the matching
            # draft row by reversing the prefix.
            target = f"draft_{draft_year}_{mp}"
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
# Snapshot/results emission
# ---------------------------------------------------------------------------

def _merged_to_snapshot_dict(m: dict,
                             snapshot_date: str,
                             interval_label: str) -> dict:
    """Build the insert payload for draft_snapshots from a merged record."""
    tools: dict = {}
    extras: dict = {}

    # Hitter tools (position CSV)
    pos = m.get("_position") or {}
    pit = m.get("_pitching") or {}
    if pos.get("tools_future"):
        tools.update(pos["tools_future"])
        if pos.get("tools_present"):
            extras["tools_present"] = pos["tools_present"]
    if pit.get("tools_future"):
        tools.update(pit["tools_future"])
        if pit.get("tools_present"):
            # Don't clobber a hitter's present tools (rare two-way edge case)
            cur = extras.get("tools_present") or {}
            cur.update(pit["tools_present"])
            extras["tools_present"] = cur

    # Pitching-specific extras
    for k in ("tj_date", "fb_type", "sits", "tops", "rpm_fb", "rpm_break"):
        v = pit.get(k)
        if v is not None:
            extras[k] = v

    # Physical extras
    phys = m.get("_physical") or {}
    for k in ("frame", "athl", "levers", "arm", "perf", "delivery"):
        v = phys.get(k)
        if v is not None:
            extras[k] = v

    # Summary extras
    for k in ("age", "height", "weight", "bats", "throws", "fg_player_id",
              "trend", "pick_overall", "pick_team", "top_100", "video_url"):
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

    status = "drafted" if m.get("pick_overall") else "draft_active"

    return {
        "source":          "fangraphs",
        "snapshot_date":   snapshot_date,
        "interval_label":  interval_label,
        "player_key":      m["player_key"],
        "player_name":     m["player_name"],
        "position":        m.get("position"),
        "school":          m.get("school"),
        "college_commit":  m.get("college_commit"),
        "player_type":     m.get("player_type"),
        "draft_year":      m["draft_year"],
        "rank":            m.get("rank"),
        "fv":              m.get("fv"),
        "fv_plus":         bool(m.get("fv_plus", False)),
        "risk":            m.get("risk"),
        "status":          status,
        "tools":           tools or None,
        # Promoted to draft_players too
        "birth_date":      None,  # FG doesn't ship DOB in summary
        "bats":            m.get("bats"),
        "throws":          m.get("throws"),
        "height":          m.get("height"),
        "weight":          m.get("weight"),
        "fg_player_id":    m.get("fg_player_id"),
    }


def _merged_to_result_row(m: dict) -> dict | None:
    """When the summary row carries a Pick column, emit a draft_results row."""
    pick = m.get("pick_overall")
    team = m.get("pick_team")
    if pick is None or not team:
        return None
    # Round derivation: 1-30=R1, 31-60=R2, ... approximate; the post-draft
    # FG CSV doesn't carry the round label directly. The MLB tracker
    # scraper (later) carries authoritative round/pick_in_round.
    round_num = ((pick - 1) // 30) + 1 if pick <= 600 else None
    round_label = str(round_num) if round_num else None
    return {
        "draft_year":   m["draft_year"],
        "pick_overall": pick,
        "round_label":  round_label,
        "pick_in_round": ((pick - 1) % 30) + 1 if round_num else None,
        "team":         team,
        "player_key":   m["player_key"],
        "player_name":  m["player_name"],
        "school":       m.get("school"),
        "slot_usd":     None,   # joined in from build_draft_pools later
        "bonus_usd":    None,   # populated by scrape_mlb_draft_tracker later
        "signed":       1 if pick else 0,  # FG CSV only lists signed picks
        "source":       "fg_draft_csv",
    }


# ---------------------------------------------------------------------------
# Group folders by slug (subfolder layout)
# ---------------------------------------------------------------------------

def _group_subfolders(drop_dir: Path) -> list[dict]:
    """Walk subfolders of drop_dir whose name matches `<year>draft`.
    Returns a list of dicts with keys for each CSV type detected."""
    out: list[dict] = []
    if not drop_dir.is_dir():
        return out
    for sub in sorted(drop_dir.iterdir()):
        if not sub.is_dir():
            continue
        if sub.name == "processed" or sub.name.startswith("."):
            continue
        year = is_draft_slug(sub.name)
        if year is None:
            continue
        csvs = sorted(p for p in sub.glob("*.csv") if p.is_file())
        if not csvs:
            continue
        grp: dict = {"slug": sub.name, "draft_year": year,
                     "_folder": sub, "_unclassified": []}
        for path in csvs:
            headers = _sniff_headers(path)
            ftype = _classify_csv(headers)
            # The draft summary CSV doesn't always trip the standard
            # summary classifier (some pre-draft CSVs ship without a
            # 'report' column on certain rows). Treat any file with
            # 'School' + 'College Commit' as a draft summary.
            if ftype is None:
                norm = {h.strip().lower() for h in headers}
                if "school" in norm and "college commit" in norm:
                    ftype = "summary"
            if ftype is None:
                grp["_unclassified"].append(path)
                continue
            grp[ftype] = path
        out.append(grp)
    return out


def _group_flat(drop_dir: Path) -> list[dict]:
    """Flat-layout: <type>-<year>draft.csv files at drop_dir root."""
    out: dict[str, dict] = defaultdict(dict)
    if not drop_dir.is_dir():
        return []
    for p in sorted(drop_dir.glob("*.csv")):
        parsed = _parse_filename(p.name)
        if not parsed:
            continue
        ftype, slug = parsed
        year = is_draft_slug(slug)
        if year is None:
            continue
        out[slug][ftype] = p
        out[slug].setdefault("slug", slug)
        out[slug].setdefault("draft_year", year)
    return list(out.values())


# ---------------------------------------------------------------------------
# Per-set processor
# ---------------------------------------------------------------------------

def _process_one_set(grp: dict,
                     processed_dir: Path | None = None,
                     snapshot_date_override: str | None = None) -> tuple[int, int]:
    """Process one draft set. Returns (snapshots_inserted, results_inserted)."""
    slug = grp["slug"]
    year = grp["draft_year"]
    if "summary" not in grp:
        log.warning("draft_csv: skipping '%s' — missing summary CSV (have: %s)",
                    slug, sorted(k for k in grp
                                 if k not in {"slug", "draft_year", "_folder",
                                              "_unclassified"}))
        return (0, 0)

    summary_raw = _read_csv_rows(grp["summary"])
    summary_rows = [r for r in (_parse_draft_summary_row(x, year)
                                for x in summary_raw) if r]
    position_raw = _read_csv_rows(grp["position"]) if "position" in grp else []
    pitching_raw = _read_csv_rows(grp["pitching"]) if "pitching" in grp else []
    physical_raw = _read_csv_rows(grp["physical"]) if "physical" in grp else []
    position_rows = [r for r in (_parse_position_row(x) for x in position_raw) if r]
    pitching_rows = [r for r in (_parse_pitching_row(x) for x in pitching_raw) if r]
    physical_rows = [r for r in (_parse_physical_row(x) for x in physical_raw) if r]

    if not summary_rows:
        log.warning("draft_csv: '%s' yielded 0 summary rows", slug)
        return (0, 0)

    merged = _join_draft_set(summary_rows, position_rows, pitching_rows,
                             physical_rows, year)

    snap_date = snapshot_date_override
    if not snap_date:
        # Use the slug folder mtime as a best-effort publish date — FG
        # draft articles publish on a known cadence (preseason ~Feb,
        # midseason ~May, pre-draft ~July, post-draft ~July/August).
        folder = grp.get("_folder")
        if folder:
            snap_date = date.fromtimestamp(folder.stat().st_mtime).isoformat()
        else:
            snap_date = grp["summary"].parent.name.split("__")[-1] if "__" in grp["summary"].parent.name \
                        else date.today().isoformat()

    interval_label = f"FG {year} Draft ({snap_date})"

    snap_payloads = [_merged_to_snapshot_dict(m, snap_date, interval_label) for m in merged]
    result_payloads = [r for r in (_merged_to_result_row(m) for m in merged) if r]

    n_snap = insert_draft_snapshots(snap_payloads)
    n_res  = upsert_draft_results(result_payloads) if result_payloads else 0

    log.info("draft_csv: '%s' -> %d snapshots, %d results (year=%d, date=%s)",
             slug, n_snap, n_res, year, snap_date)

    if processed_dir and grp.get("_folder"):
        dest = processed_dir / f"{slug}__{snap_date}"
        try:
            if dest.exists():
                log.info("draft_csv: '%s' already in processed/, skipping move", slug)
            else:
                shutil.move(str(grp["_folder"]), str(dest))
                log.info("draft_csv: moved '%s' to processed/", slug)
        except OSError as e:
            log.warning("draft_csv: could not move '%s' to processed/: %s",
                        slug, e)

    return (n_snap, n_res)


# ---------------------------------------------------------------------------
# Orchestrator + backfill
# ---------------------------------------------------------------------------

def ingest_drops(drop_dir: Path | None = None,
                 processed_dir: Path | None = None) -> tuple[int, int]:
    """Scan drop_dir for <year>draft subfolders + flat <type>-<year>draft.csv
    files. Returns (snapshots_inserted, sets_processed)."""
    drop_dir = drop_dir or DROP_DIR
    processed_dir = processed_dir or PROCESSED_DIR
    processed_dir.mkdir(parents=True, exist_ok=True)

    groups = _group_subfolders(drop_dir) + _group_flat(drop_dir)
    if not groups:
        log.info("draft_csv: no draft drops to ingest")
        return (0, 0)

    snaps_total = 0
    sets = 0
    for grp in groups:
        try:
            n_snap, _ = _process_one_set(grp, processed_dir=processed_dir)
            if n_snap > 0:
                snaps_total += n_snap
                sets += 1
        except Exception as e:
            log.exception("draft_csv: '%s' crashed: %s", grp.get("slug"), e)

    log.info("draft_csv: ingested %d snapshots from %d draft set(s)",
             snaps_total, sets)
    return (snaps_total, sets)


def backfill_processed(processed_dir: Path | None = None) -> tuple[int, int]:
    """Re-read every <year>draft__<date>/ subfolder under processed/ into
    the draft_* tables. Idempotent — UNIQUE constraints prevent dupes.
    Returns (snapshots_inserted, sets_processed)."""
    processed_dir = processed_dir or PROCESSED_DIR
    if not processed_dir.is_dir():
        log.warning("draft_csv: processed dir not found at %s", processed_dir)
        return (0, 0)

    snaps_total = 0
    sets = 0
    for sub in sorted(processed_dir.iterdir()):
        if not sub.is_dir():
            continue
        # Folders look like `2024draft__2024-07-11`. Split on `__`.
        base, _, date_part = sub.name.partition("__")
        year = is_draft_slug(base)
        if year is None:
            continue
        csvs = sorted(p for p in sub.glob("*.csv") if p.is_file())
        if not csvs:
            continue
        grp: dict = {"slug": base, "draft_year": year, "_folder": sub,
                     "_unclassified": []}
        for path in csvs:
            headers = _sniff_headers(path)
            ftype = _classify_csv(headers)
            if ftype is None:
                norm = {h.strip().lower() for h in headers}
                if "school" in norm and "college commit" in norm:
                    ftype = "summary"
            if ftype is None:
                continue
            grp[ftype] = path
        try:
            n_snap, _ = _process_one_set(grp, processed_dir=None,
                                          snapshot_date_override=date_part or None)
            if n_snap > 0:
                snaps_total += n_snap
                sets += 1
        except Exception as e:
            log.exception("draft_csv backfill: '%s' crashed: %s", base, e)

    log.info("draft_csv: backfilled %d snapshots from %d processed set(s)",
             snaps_total, sets)
    return (snaps_total, sets)


# ---------------------------------------------------------------------------
# Manual draft_results.csv fallback
# ---------------------------------------------------------------------------

# Columns: year, pick_overall, team, player_name, school, bonus_usd, signed
def ingest_manual_results(csv_path: Path) -> int:
    """Load a manual draft_results.csv. Useful when MLB.com's tracker is
    slow to update or wrong. Each row is upserted into draft_results."""
    if not csv_path.exists():
        return 0
    rows: list[dict] = []
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            year = _to_int(r.get("year"))
            pick = _to_int(r.get("pick_overall"))
            team = _str_or_none(r.get("team"))
            name = _str_or_none(r.get("player_name"))
            if not (year and pick and team and name):
                continue
            rows.append({
                "draft_year":   year,
                "pick_overall": pick,
                "round_label":  _str_or_none(r.get("round_label")),
                "pick_in_round": _to_int(r.get("pick_in_round")),
                "team":         team,
                "player_key":   draft_player_key(year, name),
                "player_name":  fix_mojibake(name),
                "school":       _str_or_none(r.get("school")),
                "slot_usd":     _to_int(r.get("slot_usd")),
                "bonus_usd":    _to_int(r.get("bonus_usd")),
                "signed":       1 if (r.get("signed") or "").strip().lower() in {"1", "true", "yes", "y"} else 0,
                "source":       "manual",
            })
    return upsert_draft_results(rows)
