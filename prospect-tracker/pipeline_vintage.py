# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MLB Pipeline point-in-time prospect VINTAGES via the open GraphQL host.

This is a NATIVE point-in-time archive: for each past season YYYY, the query
returns the MLB Pipeline Top-100 board exactly as it stood that year (grades and
ranks as-of that vintage, not back-revised), keyed on the MLBAM player id. That
is the anti-leakage capability the eFV model wants for its most-weighted
pre-debut feature: a scout consensus snapshot dated strictly before outcome.

SOURCE (undocumented, treat as fragile):
  POST https://data-graph.mlb.com/graphql   (open, unauthenticated, JSON body)
  getPlayerRankingsFromSelection(limit:100, slug:"sel-pr-YYYY-top100")
  Verified 2026-07-24 for slugs sel-pr-2011-top100 .. sel-pr-2026-top100.
  Anchors: 2021 #1 = Wander Franco (677551), 2026 #1 = Jesus Made (815908).

  Rank/eta/position/mlbam come back for every entry. The 20-80 tool grades live
  in a lazy list field on each board entry (introspection is disabled on this
  host); the exact selection set was recovered from the mlb.com/milb/prospects
  Apollo cache + error-oracle field probing (see report / registry):
      playerEntity {
        gradesHitting  { key value }   # keys: Hit Power Run Arm Field Overall
        gradesPitching { key value }   # keys: Fastball Curveball Slider
                                       #       Changeup Control Overall
      }
  "Overall" is the Future Value (FV). Grade coverage is PARTIAL per vintage
  (older boards expose grades for only a subset of the 100); rank/pos/eta/id is
  full. Values arrive as strings ("80"); we coerce numerics to int.

OUTPUT (all local; owner wires this into the model layer, not this module):
  .cache/pipeline_vintage/{year}.json  raw GraphQL response, past years frozen
  data/pipeline_vintages.json          normalized per-year board records

This module ONLY ingests. It is deliberately NOT imported by run_monthly.py /
consensus.py / efv_dataset.py. Fail-soft: a year that will not fetch is skipped
and any previously landed copy of it is preserved.

Run: python pipeline_vintage.py
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)

# --- source ------------------------------------------------------------------
GRAPHQL_URL = "https://data-graph.mlb.com/graphql"
# Identifying UA per the source-owner courtesy rule (this host is undocumented).
USER_AGENT = "eephus.io-prospect-tracker/1.0 (+https://eephus.io; arkndjl@gmail.com)"
SLUG_TMPL = "sel-pr-{year}-top100"
MIN_YEAR = 2011           # oldest slug that resolves on the host
DEFAULT_YEARS = range(2015, 2027)   # 2015..2026 inclusive (deliverable default)

# --- paths -------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
CACHE_DIR = _HERE / ".cache" / "pipeline_vintage"
OUT_PATH = _HERE / "data" / "pipeline_vintages.json"

# --- politeness --------------------------------------------------------------
_MIN_REQUEST_GAP_S = 1.1   # host is fragile: keep it under one request / second
_CURRENT_TTL_H = 24.0      # newest board can still move; refetch if stale
_TIMEOUT_S = 30
_last_request_ts = 0.0

# Canonical tool order for readability if a consumer wants a fixed vector.
HIT_TOOLS = ("hit", "power", "run", "arm", "field", "overall")
PIT_TOOLS = ("fastball", "slider", "curveball", "changeup", "control", "overall")

_QUERY = (
    '{getPlayerRankingsFromSelection(limit:100,slug:"%s"){'
    'rank playerEntity{position eta player{id fullName} '
    'gradesHitting{key value} gradesPitching{key value}}}}'
)


# --- network -----------------------------------------------------------------
def _rate_limit() -> None:
    """Block until at least _MIN_REQUEST_GAP_S has elapsed since the last POST."""
    global _last_request_ts
    wait = _MIN_REQUEST_GAP_S - (time.time() - _last_request_ts)
    if wait > 0:
        time.sleep(wait)
    _last_request_ts = time.time()


def _post(slug: str) -> dict:
    """POST one board query. Returns parsed JSON. Raises on transport error."""
    body = json.dumps({"query": _QUERY % slug}).encode("utf-8")
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    _rate_limit()
    with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
        raw = resp.read()
    return json.loads(raw.decode("utf-8"))


# --- cache -------------------------------------------------------------------
def _cache_path(year: int) -> Path:
    return CACHE_DIR / f"{year}.json"


def _cache_is_fresh(year: int, max_year: int) -> bool:
    """Past vintages are frozen forever; only the newest board carries a TTL."""
    p = _cache_path(year)
    if not p.exists():
        return False
    if year < max_year:
        return True
    age_h = (time.time() - p.stat().st_mtime) / 3600.0
    return age_h < _CURRENT_TTL_H


def _load_cached(year: int) -> dict | None:
    p = _cache_path(year)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _fetch_year(year: int, max_year: int) -> dict | None:
    """Return the raw GraphQL payload for a year, cache-first. Fail-soft -> None."""
    if _cache_is_fresh(year, max_year):
        cached = _load_cached(year)
        if cached is not None:
            return cached
    try:
        payload = _post(SLUG_TMPL.format(year=year))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        log.warning("pipeline_vintage: fetch failed for %s (%s); using any cache", year, exc)
        return _load_cached(year)  # stale cache beats nothing
    if payload.get("errors") and not (payload.get("data") or {}).get("getPlayerRankingsFromSelection"):
        log.warning("pipeline_vintage: GraphQL errors for %s: %s", year, payload["errors"])
        return _load_cached(year)
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(year).write_text(json.dumps(payload), encoding="utf-8")
    except OSError as exc:
        log.warning("pipeline_vintage: could not write cache for %s (%s)", year, exc)
    return payload


# --- normalize ---------------------------------------------------------------
def _to_int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _grades_from(entity: dict):
    """Flatten gradesHitting / gradesPitching into {tool: grade} + fv + side.

    A prospect populates exactly one side (the other is null/[]). Returns
    (grades_dict, side) or (None, None) when no grades are published.
    """
    for field, side in (("gradesHitting", "hit"), ("gradesPitching", "pit")):
        lst = entity.get(field) or []
        if not lst:
            continue
        grades = {}
        for item in lst:
            key = (item.get("key") or "").strip().lower()
            if not key:
                continue
            iv = _to_int(item.get("value"))
            grades[key] = iv if iv is not None else item.get("value")
        if grades:
            return grades, side
    return None, None


def _normalize_board(payload: dict) -> list[dict]:
    """Turn a raw GraphQL payload into ranked records. Robust to shape drift."""
    rows = ((payload or {}).get("data") or {}).get("getPlayerRankingsFromSelection") or []
    out = []
    for r in rows:
        pe = r.get("playerEntity") or {}
        player = pe.get("player") or {}
        mlbam = player.get("id")
        grades, side = _grades_from(pe)
        rec = {
            "rank": r.get("rank"),
            "mlbam": int(mlbam) if isinstance(mlbam, (int, str)) and str(mlbam).isdigit() else None,
            "name": player.get("fullName"),
            "pos": pe.get("position"),
            "eta": pe.get("eta"),
        }
        if grades:
            rec["grades"] = grades
            rec["side"] = side
            fv = grades.get("overall")
            if fv is not None:
                rec["fv"] = fv
        out.append(rec)
    out.sort(key=lambda x: (x["rank"] is None, x["rank"]))
    return out


# --- build -------------------------------------------------------------------
def build(years=DEFAULT_YEARS, out_path: Path = OUT_PATH) -> dict:
    """Ingest each vintage board and land data/pipeline_vintages.json. Fail-soft.

    Preserves any previously landed year that fails to fetch this run.
    Returns a summary dict (also embedded as _meta in the output file).
    """
    years = sorted({int(y) for y in years if int(y) >= MIN_YEAR})
    if not years:
        raise ValueError("no valid years >= %d requested" % MIN_YEAR)
    max_year = max(years)

    # Start from any prior landing so a bad network run never regresses coverage.
    existing = {}
    if out_path.exists():
        try:
            existing = (json.loads(out_path.read_text(encoding="utf-8")) or {}).get("vintages", {})
        except (OSError, ValueError):
            existing = {}

    vintages = dict(existing)
    per_year = {}
    for year in years:
        payload = _fetch_year(year, max_year)
        board = _normalize_board(payload) if payload else []
        if board:
            vintages[str(year)] = board
        elif str(year) in vintages:
            board = vintages[str(year)]  # keep prior landing; count it below
        with_id = sum(1 for r in board if r.get("mlbam"))
        with_grades = sum(1 for r in board if r.get("grades"))
        per_year[str(year)] = {
            "players": len(board),
            "with_mlbam": with_id,
            "with_grades": with_grades,
        }

    total = sum(len(v) for v in vintages.values())
    total_id = sum(1 for v in vintages.values() for r in v if r.get("mlbam"))
    meta = {
        "source": GRAPHQL_URL,
        "query": "getPlayerRankingsFromSelection(slug=sel-pr-YYYY-top100)",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "years": [int(y) for y in sorted(vintages, key=int)],
        "per_year": per_year,
        "mlbam_fill_rate": round(total_id / total, 4) if total else 0.0,
        "note": ("Point-in-time MLB Pipeline Top-100 vintages. Grade coverage is "
                 "partial per year; rank/pos/eta/mlbam is full. Overall grade = FV."),
    }
    payload_out = {"_meta": meta, "vintages": vintages}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload_out, indent=2), encoding="utf-8")
    log.info("pipeline_vintage: landed %d years, %d players, mlbam fill %.1f%%",
             len(vintages), total, 100 * meta["mlbam_fill_rate"])
    return meta


# --- offline helpers ---------------------------------------------------------
def _load_landed(path: Path = OUT_PATH) -> dict:
    try:
        return (json.loads(Path(path).read_text(encoding="utf-8")) or {}).get("vintages", {})
    except (OSError, ValueError):
        return {}


def vintage_board(year: int, path: Path = OUT_PATH) -> list[dict]:
    """Pure/offline: the landed Top-100 vintage for a year (empty if not landed)."""
    return list(_load_landed(path).get(str(int(year)), []))


def player_vintages(mlbam, path: Path = OUT_PATH) -> list[dict]:
    """Pure/offline: every landed board appearance for one MLBAM id, oldest first.

    Returns [{year, rank, pos, eta, name, grades?, fv?, side?}, ...].
    """
    try:
        want = int(mlbam)
    except (TypeError, ValueError):
        return []
    landed = _load_landed(path)
    hits = []
    for year, board in landed.items():
        for r in board:
            if r.get("mlbam") == want:
                row = {"year": int(year)}
                row.update({k: v for k, v in r.items() if k != "mlbam"})
                hits.append(row)
                break
    hits.sort(key=lambda x: x["year"])
    return hits


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    summary = build()
    print(json.dumps(summary, indent=2))
