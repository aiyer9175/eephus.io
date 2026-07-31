# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
#
# Tommy John Surgery List (c) the MLBPlayerAnalysis community sheet,
# maintained by Jon Roegele / the public "Tommy John Surgery List"
# Google Sheet. eephus.io consumes the published CSV export with
# attribution and runs parsing + as-of feature derivation only.

"""Tommy John (UCL reconstruction) surgery-list ingestion.

WHAT THIS IS
  The public community-maintained Tommy John Surgery List, published as
  a Google-Sheets CSV export. One row per surgery (a pitcher can appear
  multiple times - re-tears / revisions), keyed for our purposes on the
  native `mlbamid` column, which is the join spine used everywhere in
  this repo. Fill rate on mlbamid is ~99.5% (2696/2711 at ingest).

SOURCE GOTCHA (verified live 2026-07-24, HTTP 200, text/csv, ~391 KB)
  Row 1 of the export is a DONATIONS BANNER, not the header. The REAL
  header is row 2 (Player, TJ Surgery Date, Team, Level, Position,
  Throws, ... mlbamid, fgid, ... Post-TJ MLB G, Active, Year, Month,
  Day, ...). The header itself spans several physical lines because a
  few late columns carry quoted embedded newlines, so this MUST be
  parsed with the csv module, never split line-by-line. We locate the
  header ROBUSTLY by scanning the first rows for the one that contains
  both `Player` and `mlbamid` rather than trusting a fixed index.

PIPELINE
  fetch   the CSV export, identifying UA `eephus-io/1.0`, disk-cached
          to .cache/tj_surgery/ with a TTL (the sheet updates roughly
          daily). Fail-soft: on any network/parse error we fall back to
          the last good cache and never raise into a caller.
  parse   skip the banner, resolve the header, emit clean per-surgery
          records (ISO date from the Year/Month/Day columns, numeric
          coercion of recovery months / Post-TJ MLB G / Active).
  land    data/tj_surgery.json - provenance block + `players`, a compact
          map mlbamid(str) -> chronologically sorted list of surgeries
          [{year, date, level, recovery_months, active, post_tj_mlb_g}].

AS-OF FEATURES (leakage-safe, offline)
  tj_features(mlbam, cutoff_iso) reads the landed json and counts ONLY
  surgeries whose Year is STRICTLY BEFORE the cutoff year - the pitcher's
  decision point (debut date, or a prospect's last list point). This is
  what eFV would consume; it is pure and touches no network.

Run: python tj_surgery.py            (fetch + land + print summary)
     python tj_surgery.py --no-fetch (rebuild json from cache only)

NOTE: landing only. This module is deliberately NOT wired into
run_monthly.py / build_site.py / efv_*.py - that is owner integration.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import sys
import time
import urllib.request
from datetime import date, datetime
from pathlib import Path

log = logging.getLogger(__name__)

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
OUT_PATH = DATA_DIR / "tj_surgery.json"
CACHE_DIR = ROOT / ".cache" / "tj_surgery"
CACHE_CSV = CACHE_DIR / "tj_list.csv"
CACHE_META = CACHE_DIR / "meta.json"
SAMPLE_PATH = DATA_DIR / "sources" / "samples" / "tj_list_verify.csv"
SAMPLE_META = DATA_DIR / "sources" / "samples" / "tj_list_verify.meta.json"

# The ONLY verified endpoint (re-probe before trusting). Google issues a
# 307 to a googleusercontent host; urllib follows it transparently.
SOURCE_URL = ("https://docs.google.com/spreadsheets/d/"
              "1gQujXQQGOVNaiuwSN680Hq-FDVsCwvN-3AazykOBON0/export?format=csv")
USER_AGENT = "eephus-io/1.0"

TTL_S = 12 * 3600        # sheet updates ~daily; a 12h TTL is polite + fresh
THROTTLE_S = 3.0         # minimum spacing between live fetches (politeness)
TIMEOUT_S = 90

# Column headers we consume (exact strings from the sheet's row-2 header).
_C_PLAYER = "Player"
_C_DATE = "TJ Surgery Date"
_C_LEVEL = "Level"
_C_RECOV = "Recovery Time (months)"
_C_MLBAM = "mlbamid"
_C_POSTG = "Post-TJ MLB G"
_C_ACTIVE = "Active"
_C_YEAR = "Year"
_C_MONTH = "Month"
_C_DAY = "Day"

_last_fetch = 0.0


# --------------------------------------------------------------------------- #
# fetch (disk-cached, fail-soft)
# --------------------------------------------------------------------------- #
def _throttle() -> None:
    global _last_fetch
    dt = time.time() - _last_fetch
    if dt < THROTTLE_S:
        time.sleep(THROTTLE_S - dt)
    _last_fetch = time.time()


def fetch_csv(fetch: bool = True) -> str | None:
    """Return the raw CSV text, disk-cached under .cache/tj_surgery/.

    Fresh cache (within TTL) is served without a request. A live fetch
    writes both the CSV and a meta sidecar (status/bytes/fetched_at). On
    ANY error we fail soft to the last good cache and return None only if
    no cache has ever landed.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if CACHE_CSV.exists():
        age = time.time() - CACHE_CSV.stat().st_mtime
        if not fetch or age <= TTL_S:
            return CACHE_CSV.read_text(encoding="utf-8")
    if not fetch:
        return CACHE_CSV.read_text(encoding="utf-8") if CACHE_CSV.exists() else None

    _throttle()
    req = urllib.request.Request(SOURCE_URL, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            raw = r.read()
            status = getattr(r, "status", 200)
        text = raw.decode("utf-8", errors="replace")
        # Guard against a redirect/interstitial masquerading as success:
        # a valid export always carries the mlbamid header somewhere early.
        if "mlbamid" not in text[:4000]:
            raise ValueError("payload missing mlbamid header - not the CSV export")
        CACHE_CSV.write_text(text, encoding="utf-8")
        CACHE_META.write_text(json.dumps({
            "url": SOURCE_URL,
            "http_status": int(status),
            "bytes": len(raw),
            "fetched_at": datetime.now().isoformat(timespec="seconds"),
        }, indent=2), encoding="utf-8")
        log.info("tj_surgery: fetched %d bytes (HTTP %s)", len(raw), status)
        return text
    except Exception as e:                                    # noqa: BLE001
        log.warning("tj_surgery: fetch failed (%s); falling back to cache", e)
        return CACHE_CSV.read_text(encoding="utf-8") if CACHE_CSV.exists() else None


# --------------------------------------------------------------------------- #
# parse
# --------------------------------------------------------------------------- #
def _find_header(rows: list[list[str]]) -> int:
    """Index of the real header row - the first row carrying BOTH `Player`
    and `mlbamid`. Skips the row-1 donations banner robustly."""
    for i, row in enumerate(rows[:6]):
        cells = {c.strip() for c in row}
        if _C_PLAYER in cells and _C_MLBAM in cells:
            return i
    raise ValueError("tj_surgery: could not locate header row (Player + mlbamid)")


def _to_int(v: str) -> int | None:
    v = (v or "").strip()
    return int(v) if v.lstrip("-").isdigit() else None


def _to_float(v: str) -> float | None:
    v = (v or "").strip()
    try:
        return float(v)
    except ValueError:
        return None


def _iso_date(year: str, month: str, day: str, fallback: str) -> str | None:
    """Build YYYY-MM-DD from the split Year/Month/Day columns (every row has
    them). Falls back to parsing the M/D/YYYY `TJ Surgery Date`, then to
    year-only (mid-year 07-01 to minimize month bias)."""
    y, m, d = _to_int(year), _to_int(month), _to_int(day)
    if y and m and d:
        try:
            return date(y, m, d).isoformat()
        except ValueError:
            pass
    fb = (fallback or "").strip()
    if fb:
        try:
            return datetime.strptime(fb, "%m/%d/%Y").date().isoformat()
        except ValueError:
            pass
    if y:
        return date(y, 7, 1).isoformat()
    return None


def parse_records(raw: str) -> list[dict]:
    """Parse the raw CSV into flat per-surgery dicts, skipping the banner.

    Only rows with a numeric mlbamid become records (that is our join
    key; ~0.5% of rows carry no id and are dropped from the keyed store)."""
    rows = list(csv.reader(io.StringIO(raw)))
    h = _find_header(rows)
    header = [c.strip() for c in rows[h]]
    idx = {c: i for i, c in enumerate(header)}

    def cell(row: list[str], col: str) -> str:
        i = idx.get(col)
        return row[i].strip() if i is not None and i < len(row) else ""

    out: list[dict] = []
    for row in rows[h + 1:]:
        if not any(c.strip() for c in row):
            continue                                    # blank trailer row
        mlbam = cell(row, _C_MLBAM)
        year = _to_int(cell(row, _C_YEAR))
        rec = {
            "mlbamid": mlbam if mlbam.isdigit() else None,
            "player": cell(row, _C_PLAYER),
            "year": year,
            "date": _iso_date(cell(row, _C_YEAR), cell(row, _C_MONTH),
                              cell(row, _C_DAY), cell(row, _C_DATE)),
            "level": cell(row, _C_LEVEL) or None,
            "recovery_months": _to_float(cell(row, _C_RECOV)),
            "active": _to_int(cell(row, _C_ACTIVE)),
            "post_tj_mlb_g": _to_int(cell(row, _C_POSTG)),
        }
        out.append(rec)
    return out


def build_store(records: list[dict]) -> dict[str, list[dict]]:
    """Collapse flat records into mlbamid -> chronological surgery list.

    Keeps only id-bearing rows. Each surgery carries the compact tuple the
    landed json exposes; the list is sorted oldest -> newest so index -1 is
    always the most recent surgery."""
    store: dict[str, list[dict]] = {}
    for r in records:
        mid = r["mlbamid"]
        if not mid:
            continue
        store.setdefault(mid, []).append({
            "year": r["year"],
            "date": r["date"],
            "level": r["level"],
            "recovery_months": r["recovery_months"],
            "active": r["active"],
            "post_tj_mlb_g": r["post_tj_mlb_g"],
        })
    for mid, surgs in store.items():
        # sort by ISO date when present, else by year; None sinks to the top
        surgs.sort(key=lambda s: (s.get("date") or f"{s.get('year') or 0:04d}-00-00"))
    return store


# --------------------------------------------------------------------------- #
# run / land
# --------------------------------------------------------------------------- #
def run(persist: bool = True, fetch: bool = True) -> dict:
    """Fetch (or read cache), parse, build the keyed store, land the json."""
    raw = fetch_csv(fetch=fetch)
    if raw is None:
        log.error("tj_surgery: no data available (no network, no cache)")
        return {"players": {}, "n_rows": 0, "n_players": 0}
    records = parse_records(raw)
    id_rows = [r for r in records if r["mlbamid"]]
    store = build_store(records)
    fill = round(len(id_rows) / len(records), 4) if records else 0.0
    payload = {
        "generated_at": date.today().isoformat(),
        "source": SOURCE_URL,
        "attribution": "Tommy John Surgery List (public community sheet)",
        "join_key": "mlbamid (native MLBAM player id)",
        "n_rows": len(records),
        "n_players": len(store),
        "mlbamid_fill_rate": fill,
        "as_of_rule": ("tj_features counts surgeries with Year STRICTLY "
                       "BEFORE the cutoff year (leakage-safe)"),
        "players": store,
    }
    if persist and store:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(payload, separators=(",", ":")),
                            encoding="utf-8")
        log.info("tj_surgery: wrote %s (%d players, %d surgeries)",
                 OUT_PATH, len(store), len(records))
    return payload


# --------------------------------------------------------------------------- #
# as-of feature helper (pure, offline)
# --------------------------------------------------------------------------- #
_STORE_CACHE: dict[str, list[dict]] | None = None


def _load_store() -> dict[str, list[dict]]:
    """Load the landed json's `players` map once, memoized."""
    global _STORE_CACHE
    if _STORE_CACHE is None:
        try:
            doc = json.loads(OUT_PATH.read_text(encoding="utf-8"))
            _STORE_CACHE = doc.get("players", {})
        except (OSError, ValueError):
            _STORE_CACHE = {}
    return _STORE_CACHE


def _reset_cache() -> None:
    """Drop the memoized store (test hook / after a re-land)."""
    global _STORE_CACHE
    _STORE_CACHE = None


def _cutoff_year(cutoff_iso: str) -> int:
    """Year of a cutoff string ('YYYY-MM-DD' or bare 'YYYY')."""
    s = (cutoff_iso or "").strip()
    if len(s) >= 4 and s[:4].isdigit():
        return int(s[:4])
    raise ValueError(f"tj_surgery: unparseable cutoff '{cutoff_iso}'")


def _parse_cutoff_date(cutoff_iso: str) -> date:
    s = (cutoff_iso or "").strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    # last resort: year floor
    return date(_cutoff_year(cutoff_iso), 1, 1)


def tj_features(mlbam, cutoff_iso: str, store: dict | None = None) -> dict:
    """Leakage-safe, as-of Tommy John features for one player.

    Counts ONLY surgeries whose Year is STRICTLY BEFORE the cutoff year
    (the pitcher's decision point - a debut date or a prospect's last
    list point). Pure + offline: reads the landed json only.

    Returns
      tj_pre                    1 if any pre-cutoff surgery else 0
      tj_count_pre              number of pre-cutoff surgeries
      months_since_last_tj_pre  months from the most-recent pre-cutoff
                                surgery to the cutoff date, else None
    """
    store = _load_store() if store is None else store
    surgs = store.get(str(mlbam)) or []
    cy = _cutoff_year(cutoff_iso)
    pre = [s for s in surgs if isinstance(s.get("year"), int) and s["year"] < cy]

    months_since = None
    if pre:
        cutoff_d = _parse_cutoff_date(cutoff_iso)
        # most recent pre-cutoff surgery by date (fallback to year-mid)
        def _sdate(s: dict) -> date:
            d = s.get("date")
            if d:
                try:
                    return datetime.strptime(d, "%Y-%m-%d").date()
                except ValueError:
                    pass
            return date(int(s["year"]), 7, 1)
        last = max(pre, key=_sdate)
        days = (cutoff_d - _sdate(last)).days
        months_since = round(days / 30.4375, 1)

    return {
        "tj_pre": 1 if pre else 0,
        "tj_count_pre": len(pre),
        "months_since_last_tj_pre": months_since,
    }


# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    do_fetch = "--no-fetch" not in sys.argv
    rep = run(fetch=do_fetch)
    n_surg = sum(len(v) for v in rep["players"].values())
    print(f"rows landed        : {rep.get('n_rows')}")
    print(f"distinct players   : {rep.get('n_players')}")
    print(f"total surgeries    : {n_surg}")
    print(f"mlbamid fill rate  : {rep.get('mlbamid_fill_rate')}")
    multi = sum(1 for v in rep["players"].values() if len(v) > 1)
    print(f"multi-surgery pitchers: {multi}")
