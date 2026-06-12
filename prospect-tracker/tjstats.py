# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""
tjstats.py — scraper for TJStats (Thomas Nestico) Top-100 MLB Prospects.

  Source:  https://tjstats.ca/top-100-prospects/

The public page is a React front-end over a custom WordPress REST API
(namespace `tjstats/v1`). We hit that JSON API directly — NO headless browser
is needed. Endpoints (all GET, public, no auth):

  /wp-json/tjstats/v1/major-snapshots      -> [{id, pushed_at, label}]  (the
                                              "View update" dropdown; TJStats's
                                              own effective date per snapshot)
  /wp-json/tjstats/v1/rankings             -> the LIVE/"Today" Top 100 (no FV)
  /wp-json/tjstats/v1/snapshot-rankings/{id} -> a named historical Top 100
  /wp-json/tjstats/v1/scout-batters        -> ALL batter FV + 20-80 tools (bulk)
  /wp-json/tjstats/v1/scout-pitchers       -> ALL pitcher FV + grades (bulk)
  /wp-json/tjstats/v1/bio                  -> ALL bios (bulk)

Join key is `player_id`, which IS the MLBAM id (e.g. 815908 = Jesus Made) — the
same numeric suffix on /player/{slug}-{id}/. Org is `parent_org_id` (an MLBAM
team id). FV lives ONLY in the scout tables (current grades, keyed by
`updated_at`); the rankings/snapshot-rankings payloads carry rank+bio+writeup but
no FV. So a board's FV is the current scout FV joined on MLBAM id — accurate for
the Live board and the most-recent named snapshot, NULL for older snapshots.

Politeness (this is one person's site): clear identifying User-Agent, on-disk
response cache, request throttle, retry with exponential backoff. robots.txt
(checked 2026-06) is `User-agent: * -> Allow: /` with content-signal
`ai-train=no`; we ingest factual rankings/FV for display + analytics (search-like,
not model training) and attribute writeups to TJStats.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)

# ── Endpoints ────────────────────────────────────────────────────────────────
BASE_URL = "https://tjstats.ca/wp-json/tjstats/v1"
SOURCE_PAGE = "https://tjstats.ca/top-100-prospects/"
PLAYER_URL = "https://tjstats.ca/player/{slug}-{mlbam}/"   # for attribution links

SOURCE_KEY = "tjstats"   # per-source grade-storage key (alongside fangraphs, etc.)

# ── Politeness ───────────────────────────────────────────────────────────────
USER_AGENT = ("eephus.io-prospect-tracker/1.0 "
              "(+https://eephus.io; contact: arkndjl@gmail.com)")
_MIN_INTERVAL_S = 1.5          # floor between requests to the same host
_TIMEOUT_S = 30
# Within one pipeline run the Live tables are fetched once and reused (the health
# check force-refreshes first, then the ingest reuses). Runs are hours apart, far
# longer than this TTL, so each run still starts from fresh data — we just never
# pull the same bulk table twice in the same run. The health check passes
# max_age_s=0 explicitly to guarantee it sees the live shape.
_LIVE_TTL_S = 300
CACHE_DIR = Path(__file__).parent / ".cache"
CACHE_DIR.mkdir(exist_ok=True)

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
_SESSION.mount("https://", HTTPAdapter(max_retries=Retry(
    total=4, backoff_factor=0.8, status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"], respect_retry_after_header=True)))
_last_request_ts = 0.0


def _throttle() -> None:
    global _last_request_ts
    dt = time.monotonic() - _last_request_ts
    if dt < _MIN_INTERVAL_S:
        time.sleep(_MIN_INTERVAL_S - dt)
    _last_request_ts = time.monotonic()


def _cache_path(cache_key: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", cache_key)
    return CACHE_DIR / f"tjstats_{safe}.json"


def _get_json(path: str, *, cache_key: str, max_age_s: float | None = None):
    """Throttled, cached, retried GET returning parsed JSON.

    `max_age_s` controls cache reuse: None = use cache if present (immutable
    historical snapshots); 0 = always refetch (the Live board, which must capture
    the current state); a number = reuse cache younger than that many seconds.
    Raises on a non-200 or non-JSON response so callers fail loudly.
    """
    cp = _cache_path(cache_key)
    if cp.exists() and max_age_s != 0:
        age = time.time() - cp.stat().st_mtime
        if max_age_s is None or age <= max_age_s:
            try:
                return json.loads(cp.read_text(encoding="utf-8"))
            except ValueError:
                pass  # corrupt cache -> refetch
    url = f"{BASE_URL}/{path.lstrip('/')}"
    _throttle()
    resp = _SESSION.get(url, timeout=_TIMEOUT_S)
    resp.raise_for_status()
    ctype = resp.headers.get("content-type", "")
    if "json" not in ctype.lower():
        raise ValueError(f"TJStats {path}: expected JSON, got {ctype!r}")
    data = resp.json()
    cp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


# ── Raw endpoint fetchers ────────────────────────────────────────────────────
def fetch_major_snapshots(*, max_age_s: float | None = 3600) -> list[dict]:
    """The snapshot dropdown: [{id, pushed_at, label}] newest-first."""
    data = _get_json("major-snapshots", cache_key="major-snapshots", max_age_s=max_age_s)
    if not isinstance(data, list):
        raise ValueError("TJStats major-snapshots: expected a list")
    return data


def fetch_live_rankings(*, max_age_s: float | None = _LIVE_TTL_S) -> list[dict]:
    """The LIVE/'Today' board. Reused within a run (TTL), fresh across runs."""
    return _get_json("rankings", cache_key="rankings_live", max_age_s=max_age_s)


def fetch_snapshot_rankings(snapshot_id: str | int) -> list[dict]:
    """A named historical board. Immutable, so cached indefinitely."""
    sid = str(snapshot_id)
    return _get_json(f"snapshot-rankings/{sid}", cache_key=f"snapshot_{sid}")


def fetch_scout_batters(*, max_age_s: float | None = _LIVE_TTL_S) -> list[dict]:
    return _get_json("scout-batters", cache_key="scout_batters", max_age_s=max_age_s)


def fetch_scout_pitchers(*, max_age_s: float | None = _LIVE_TTL_S) -> list[dict]:
    return _get_json("scout-pitchers", cache_key="scout_pitchers", max_age_s=max_age_s)


def fetch_bio(*, max_age_s: float | None = _LIVE_TTL_S) -> list[dict]:
    return _get_json("bio", cache_key="bio", max_age_s=max_age_s)


# ── MLBAM team id -> eephus org abbreviation ─────────────────────────────────
# parent_org_id in the payload is the MLBAM franchise id. The 30-team map is
# canonical and stable; run it through canonical_org() downstream for the final
# eephus key (handles ATH/OAK, WSH, etc.). ATH=133 (Athletics), WSH=120 (Nationals).
MLBAM_TEAM_ID_TO_ABBR = {
    "108": "LAA", "109": "ARI", "110": "BAL", "111": "BOS", "112": "CHC",
    "113": "CIN", "114": "CLE", "115": "COL", "116": "DET", "117": "HOU",
    "118": "KC",  "119": "LAD", "120": "WSH", "121": "NYM", "133": "ATH",
    "134": "PIT", "135": "SD",  "136": "SEA", "137": "SF",  "138": "STL",
    "139": "TB",  "140": "TEX", "141": "TOR", "142": "MIN", "143": "PHI",
    "144": "ATL", "145": "CHW", "146": "MIA", "147": "NYY", "158": "MIL",
}

# TJStats 20-80 grade key -> eephus tool key (future grade is the stored value).
# Batters: TJStats gives hit/power/decisions/speed/defense (no separate arm).
# `decisions` (swing decisions) has no clean eephus tool peer, so it rides in the
# sidecar raw grades only, not the consensus tools_json.
_BAT_TOOL_MAP = {"hit": "hit", "power": "game_pwr", "speed": "speed", "defense": "field"}
_PIT_TOOL_MAP = {"fastball": "fb", "slider": "sl", "curveball": "cb", "changeup": "ch",
                 "cutter": "ct", "splitter": "sp", "command": "cmd"}


def _to_float(v):
    try:
        f = float(v)
        return f if f == f else None   # drop NaN
    except (TypeError, ValueError):
        return None


def _index_by_player(rows: list[dict]) -> dict[str, dict]:
    """Last-wins index of a bulk scout/bio table by MLBAM id."""
    out: dict[str, dict] = {}
    for r in rows or []:
        pid = str(r.get("player_id") or "").strip()
        if pid:
            out[pid] = r
    return out


def _org_for(rank_row: dict, bio_row: dict | None) -> str | None:
    """Resolve eephus org: prefer the bio abbreviation, fall back to the
    MLBAM-team-id map. Final normalization is left to canonical_org() at the
    ingest boundary so it matches every other source."""
    abbr = (bio_row or {}).get("abbreviation") or rank_row.get("abbreviation")
    if not abbr:
        abbr = MLBAM_TEAM_ID_TO_ABBR.get(str(rank_row.get("parent_org_id") or ""))
    return abbr or None


# ── Normalize a board (rankings + scout + bio joined on MLBAM id) ────────────
def build_board(rankings: list[dict], batters: list[dict], pitchers: list[dict],
                bio: list[dict], *, with_fv: bool = True) -> list[dict]:
    """Join a ranking list to the scout + bio tables on MLBAM id and normalize.

    `with_fv=False` (historical boards older than the current scout grades) leaves
    fv/grades NULL so we never anachronistically stamp today's FV on an old date.
    Returns one normalized dict per ranked player.
    """
    bat_by = _index_by_player(batters)
    pit_by = _index_by_player(pitchers)
    bio_by = _index_by_player(bio)
    out: list[dict] = []
    for r in rankings:
        pid = str(r.get("player_id") or "").strip()
        if not pid:
            log.warning("tjstats: ranking row missing player_id: %r", r.get("name"))
            continue
        b, p, bi = bat_by.get(pid), pit_by.get(pid), bio_by.get(pid)
        is_pitcher = (p is not None) or (str(r.get("position") or "").upper() in ("P", "RHP", "LHP", "SP", "RP"))
        scout = (p if is_pitcher else b) or {}
        fv = _to_float(scout.get("fv")) if with_fv else None
        tools: dict[str, float] = {}
        raw_grades: dict[str, dict] = {}
        if with_fv and scout:
            tmap = _PIT_TOOL_MAP if is_pitcher else _BAT_TOOL_MAP
            # capture every *_fv / *_pv pair, store the future grade as the tool
            for tj_key, eephus_key in tmap.items():
                fut = _to_float(scout.get(f"{tj_key}_fv"))
                if fut is not None:
                    tools[eephus_key] = fut
            for k, v in scout.items():
                if k.endswith(("_pv", "_fv")) and _to_float(v) is not None:
                    raw_grades[k] = _to_float(v)
        out.append({
            "mlbam_id":   pid,
            "rank":       int(r["rank_value"]) if str(r.get("rank_value") or "").isdigit() else None,
            "prev_rank":  int(r["prev_rank"]) if str(r.get("prev_rank") or "").isdigit() else None,
            "name":       (r.get("name") or "").strip(),
            "position":   (r.get("position") or "").strip() or None,
            "org":        _org_for(r, bi),
            "parent_org_id": str(r.get("parent_org_id") or "") or None,
            "type":       "pitcher" if is_pitcher else "batter",
            "fv":         fv,
            "tools":      tools,
            "raw_grades": raw_grades,
            "eta":        (scout.get("eta") if with_fv else None) or None,
            "risk":       (scout.get("risk") if with_fv else None) or None,
            "age":        r.get("age") or (bi or {}).get("age"),
            "height":     r.get("height") or (bi or {}).get("height"),
            "weight":     r.get("weight") or (bi or {}).get("weight"),
            "bat_side":   r.get("bat_side") or (bi or {}).get("bat_side"),
            "throw_side": r.get("throw_side") or (bi or {}).get("throw_side"),
            "report":     (r.get("report") or "").strip() or None,   # TJStats writeup
        })
    return out


# ── Validation + health check ────────────────────────────────────────────────
class TJStatsValidationError(RuntimeError):
    """Raised on a malformed/short board so the caller SKIPS the write rather
    than corrupting per-source storage with a partial scrape."""


def validate_board(board: list[dict], *, require_fv: bool, expect_min: int = 90) -> None:
    if len(board) < expect_min:
        raise TJStatsValidationError(
            f"only {len(board)} ranked entries (expected ~100, floor {expect_min}) "
            f"— refusing to write a short payload")
    ids = [r["mlbam_id"] for r in board]
    if not all(ids):
        raise TJStatsValidationError("a ranked entry is missing its MLBAM id")
    if len(set(ids)) != len(ids):
        dupes = [i for i in set(ids) if ids.count(i) > 1]
        raise TJStatsValidationError(f"duplicate MLBAM ids in board: {dupes[:5]}")
    ranks = [r["rank"] for r in board if r["rank"] is not None]
    if len(set(ranks)) != len(ranks):
        raise TJStatsValidationError("duplicate ranks in board")
    if require_fv:
        with_fv = [r for r in board if r["fv"] is not None]
        if len(with_fv) < expect_min:
            raise TJStatsValidationError(
                f"only {len(with_fv)}/{len(board)} entries carry an FV — scout-table "
                f"join likely broke")
        offscale = [r["fv"] for r in with_fv if not (20 <= r["fv"] <= 80)]
        if offscale:
            raise TJStatsValidationError(f"off-scale FV values (not 20-80): {offscale[:5]}")


def health_check() -> list[str]:
    """Probe each endpoint and confirm its response shape still matches what the
    parser expects. Returns a list of human-readable problems (empty = healthy)
    so a silent TJStats redesign surfaces loudly instead of zeroing ingestion."""
    problems: list[str] = []
    try:
        snaps = fetch_major_snapshots(max_age_s=0)
        if not snaps or not {"id", "pushed_at", "label"} <= set(snaps[0]):
            problems.append("major-snapshots: missing id/pushed_at/label")
    except Exception as e:
        problems.append(f"major-snapshots: {e}")
    try:
        rk = fetch_live_rankings(max_age_s=0)   # force-fresh so a redesign is seen
        need = {"rank_value", "player_id", "name", "parent_org_id", "report"}
        if not rk or not need <= set(rk[0]):
            problems.append(f"rankings: missing {need - set(rk[0] if rk else {})}")
        elif len(rk) < 90:
            problems.append(f"rankings: only {len(rk)} entries")
    except Exception as e:
        problems.append(f"rankings: {e}")
    for fn, name, fvkey in ((fetch_scout_batters, "scout-batters", "hit_fv"),
                            (fetch_scout_pitchers, "scout-pitchers", "fastball_fv")):
        try:
            rows = fn(max_age_s=0)
            if not rows or "fv" not in rows[0] or fvkey not in rows[0]:
                problems.append(f"{name}: missing fv/{fvkey}")
        except Exception as e:
            problems.append(f"{name}: {e}")
    return problems


# ── High-level scrape entry points (return board + provenance meta) ──────────
def scrape_live_board() -> dict:
    """Scrape the LIVE board. Captures the real scrape moment in UTC — TJStats
    updates continuously, so this timestamp (not a fixed date) is when we saw
    this FV/order. Also captures the page's article:modified_time as a cross-check."""
    captured_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    rankings = fetch_live_rankings()
    batters = fetch_scout_batters()
    pitchers = fetch_scout_pitchers()
    bio = fetch_bio()
    board = build_board(rankings, batters, pitchers, bio, with_fv=True)
    validate_board(board, require_fv=True)
    return {
        "kind": "live",
        "label": f"Live {captured_at[:10]}",   # date-stamped -> per-day idempotency
        "effective_date": captured_at[:10],
        "captured_at": captured_at,             # UTC ISO 8601 — source of truth
        "source_modified_at": _page_modified_time(),
        "source_url": SOURCE_PAGE,
        "board": board,
    }


def scrape_named_snapshot(snap: dict, *, current_scout_date: str | None) -> dict:
    """Scrape one named historical snapshot ({id, pushed_at, label}). FV is only
    attached when this snapshot is the one the current scout grades belong to
    (its pushed_at date == the scout updated_at date); otherwise FV stays NULL so
    we never anachronistically stamp today's grades on an older board."""
    captured_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    pushed = str(snap.get("pushed_at") or "")
    eff_date = pushed[:10] or None
    with_fv = bool(current_scout_date) and eff_date == current_scout_date
    rankings = fetch_snapshot_rankings(snap["id"])
    batters = fetch_scout_batters() if with_fv else []
    pitchers = fetch_scout_pitchers() if with_fv else []
    bio = fetch_bio()
    board = build_board(rankings, batters, pitchers, bio, with_fv=with_fv)
    validate_board(board, require_fv=with_fv)
    return {
        "kind": "named",
        "snapshot_id": str(snap["id"]),
        "label": (snap.get("label") or f"snapshot {snap['id']}").strip(),
        "effective_date": eff_date,
        "captured_at": captured_at,
        "with_fv": with_fv,
        "source_url": SOURCE_PAGE,
        "board": board,
    }


def current_scout_date() -> str | None:
    """The date the current scout grades belong to (max updated_at across the
    scout tables) — used to decide which named snapshot may carry FV."""
    dates: list[str] = []
    for fn in (fetch_scout_batters, fetch_scout_pitchers):
        try:
            for r in fn():
                u = str(r.get("updated_at") or "")[:10]
                if u:
                    dates.append(u)
        except Exception:
            pass
    return max(dates) if dates else None


def _page_modified_time() -> str | None:
    """Best-effort capture of the page's <meta article:modified_time> as a
    cross-check on freshness. Never fatal."""
    try:
        _throttle()
        html = _SESSION.get(SOURCE_PAGE, timeout=_TIMEOUT_S).text
        m = re.search(r'article:modified_time"\s+content="([^"]+)"', html)
        return m.group(1) if m else None
    except Exception:
        return None


# ── Ingest (Parts 2-4): write a board to per-source storage ──────────────────
def ingest_board(scrape: dict) -> dict:
    """Persist one scraped board (live or named snapshot):
      * consensus-relevant rank/FV/tools -> generic `snapshots` (source='tjstats',
        name-slug player_key) so TJStats merges into consensus like every source;
      * full MLBAM-keyed provenance + writeup + raw grades -> `tjstats_snapshots`.
    Both writes upsert, so re-runs are idempotent. The Live board's snapshot_date
    is the capture date (newest -> drives current consensus); named snapshots use
    TJStats's older pushed_at date (-> Time Machine only), so historical ingestion
    cannot move present-day numbers. Returns ingest stats."""
    from storage import (insert_snapshots, upsert_tjstats_snapshots,
                         load_mlbam_player_keys, known_player_keys)
    from scrapers import Snapshot, normalize_key
    from trades import canonical_org

    board = scrape["board"]
    label = scrape["label"]
    eff_date = scrape.get("effective_date") or scrape["captured_at"][:10]
    mlbam_map = load_mlbam_player_keys()
    known = known_player_keys()

    snaps, side = [], []
    n_id = n_name = n_new = 0
    for r in board:
        mlbam = str(r["mlbam_id"])
        name_key = normalize_key(r["name"])
        key = mlbam_map.get(mlbam)            # exact MLBAM-id join first
        if key:
            n_id += 1
            if key != name_key:
                log.info("tjstats: mlbam %s -> key %s (name-slug %s)", mlbam, key, name_key)
        else:                                  # fall back to fuzzy name slug
            key = name_key
            n_name += 1
            if key not in known:
                n_new += 1
                log.info("tjstats: fall-through (no MLBAM match, new key) mlbam=%s key=%s name=%r",
                         mlbam, key, r["name"])
        org = canonical_org(r.get("org")) or r.get("org")
        tools = dict(r.get("tools") or {})
        extras = {"mlbam_id": mlbam}
        for k in ("age", "height", "weight", "bat_side", "throw_side", "eta", "risk"):
            if r.get(k) not in (None, ""):
                extras[k] = r[k]
        tools["_extras"] = extras
        snaps.append(Snapshot(
            source=SOURCE_KEY, snapshot_date=eff_date, interval_label=label,
            player_key=key, player_name=r["name"], position=r.get("position"),
            org=org, rank=r.get("rank"), fv=r.get("fv"), status="active",
            tools=tools, fv_plus=False))
        side.append({
            "mlbam_id": mlbam, "player_key": key, "snapshot_label": label,
            "snapshot_kind": scrape["kind"], "snapshot_id": scrape.get("snapshot_id"),
            "effective_date": eff_date, "captured_at": scrape["captured_at"],
            "source_modified_at": scrape.get("source_modified_at"),
            "source_url": scrape.get("source_url"), "name": r["name"],
            "position": r.get("position"), "org": org, "type": r.get("type"),
            "rank": r.get("rank"), "prev_rank": r.get("prev_rank"), "fv": r.get("fv"),
            "eta": r.get("eta"), "risk": r.get("risk"),
            "grades_json": json.dumps(r["raw_grades"]) if r.get("raw_grades") else None,
            "tools_json": json.dumps(r["tools"]) if r.get("tools") else None,
            "writeup": r.get("report"),
            "with_fv": r.get("fv") is not None,
        })
    # Only the LIVE board enters the generic `snapshots` table (the present-day
    # consensus input). Named historical boards go to the sidecar ONLY: they carry
    # no FV (the API exposes none historically), so they'd add nothing to consensus
    # and would collide on (source, snapshot_date) with the manual-CSV 'TJ <month>'
    # historical rows that DO carry FV. Keeping history out of the shared table is
    # also the strongest form of the ranking-integrity guardrail — historical
    # TJStats data can never touch present-day consensus or farm rankings.
    n_snap = insert_snapshots(snaps) if scrape["kind"] == "live" else 0
    n_side = upsert_tjstats_snapshots(side)
    log.info("tjstats: ingested '%s' (%s) — %d players, %d id-join, %d name-fallback, "
             "%d new -> snapshots=%d sidecar=%d", label, eff_date, len(board), n_id,
             n_name, n_new, n_snap, n_side)
    return {"label": label, "effective_date": eff_date, "captured_at": scrape["captured_at"],
            "n_players": len(board), "id_join": n_id, "name_fallback": n_name,
            "new_players": n_new, "snapshots_written": n_snap, "sidecar_written": n_side,
            "with_fv": scrape.get("with_fv", True)}


def ingest_live() -> dict:
    """Scrape + persist the Live board (the present-day TJStats consensus input)."""
    return ingest_board(scrape_live_board())


def ingest_history() -> list[dict]:
    """Enumerate /major-snapshots and persist each named historical board into the
    point-in-time buckets. Dynamic — a future 'June 2026' drop is picked up with no
    code change. Per-snapshot validation failures are logged and SKIPPED so one bad
    board never aborts the rest."""
    scout_date = current_scout_date()
    results = []
    for s in fetch_major_snapshots():   # reuse the health-check fetch within the run
        try:
            results.append(ingest_board(scrape_named_snapshot(s, current_scout_date=scout_date)))
        except TJStatsValidationError as e:
            log.error("tjstats: SKIP named snapshot %r (id=%s): %s",
                      s.get("label"), s.get("id"), e)
    return results


def run_tjstats_pipeline(*, live: bool = True, history: bool = False) -> dict:
    """Top-level entry for run_monthly / run_daily. Runs a health check first;
    on a detected endpoint/shape change it logs loudly and SKIPS all writes rather
    than corrupting storage. Never raises — a TJStats outage must not abort the
    surrounding pipeline (the caller logs the returned status)."""
    from storage import init_db
    out: dict = {"health": [], "live": None, "history": [], "error": None}
    try:
        init_db()  # idempotent — ensures tjstats_snapshots exists on older DBs
        issues = health_check()
        out["health"] = issues
        if issues:
            log.error("tjstats: HEALTH CHECK FAILED, skipping ingest — %s", issues)
            return out
        if history:
            out["history"] = ingest_history()
        if live:
            out["live"] = ingest_live()
    except Exception as e:           # noqa: BLE001 — courtesy to the parent pipeline
        log.exception("tjstats pipeline error — continuing")
        out["error"] = str(e)
    return out


# ── Snapshot diffs / movers (Part 6) ─────────────────────────────────────────
def compute_snapshot_diff(older_label: str, newer_label: str) -> list[dict]:
    """Rank (and FV, where both carry it) deltas between two stored TJStats
    snapshots, plus board entries/exits. Reads the sidecar, so it diffs any pair.
    rank_delta > 0 = moved UP the board. Sorted biggest riser first. This is the
    data primitive for Top Movers + the editorial layer (wiring it into the
    homepage Top Movers module is a separate surface change — see README)."""
    from storage import load_tjstats_snapshots
    old = {r["mlbam_id"]: r for r in load_tjstats_snapshots(older_label)}
    new = {r["mlbam_id"]: r for r in load_tjstats_snapshots(newer_label)}
    out: list[dict] = []
    for mid, nb in new.items():
        ob = old.get(mid)
        rd = (ob["rank"] - nb["rank"]) if (ob and ob.get("rank") and nb.get("rank")) else None
        fd = (nb["fv"] - ob["fv"]) if (ob and ob.get("fv") is not None and nb.get("fv") is not None) else None
        out.append({"mlbam_id": mid, "name": nb.get("name"), "player_key": nb.get("player_key"),
                    "rank": nb.get("rank"), "prev_rank": (ob or {}).get("rank"),
                    "rank_delta": rd, "fv_delta": fd,
                    "status": "held" if ob else "entered"})
    for mid, ob in old.items():
        if mid not in new:
            out.append({"mlbam_id": mid, "name": ob.get("name"), "player_key": ob.get("player_key"),
                        "rank": None, "prev_rank": ob.get("rank"), "rank_delta": None,
                        "fv_delta": None, "status": "exited"})
    out.sort(key=lambda d: (d["rank_delta"] is None, -(d["rank_delta"] or 0)))
    return out


def latest_snapshot_pair() -> tuple[str | None, str | None]:
    """(older_label, newer_label) for the two most recently dated stored
    snapshots — the default diff window for movers."""
    from storage import tjstats_snapshot_labels
    labs = tjstats_snapshot_labels()   # effective_date DESC
    if len(labs) >= 2:
        return labs[1]["snapshot_label"], labs[0]["snapshot_label"]
    return (None, None)


# How big a board move must be before it becomes wire/source-event news.
# Day-to-day live diffs are mostly ±1-2 rank noise; the TJStats site's own
# movers framing is month-over-month, so the diff runs latest-live vs the
# newest NAMED monthly board (fallback: latest pair). Newsworthiness is
# rank-relative on a top-100: ±10 anywhere, ±5 inside the top 25, and any
# board entry (someone graduated or fell out to make the room).
_MOVER_MIN_RANK_DELTA = 10
_MOVER_TOP25_MIN_DELTA = 5
_MOVER_MAX_ITEMS = 12


def export_movers(out_path: Path | None = None) -> dict | None:
    """Movers sidecar + source events (Part 6 wiring, the README follow-up).

    Diffs the newest live board against the most recent NAMED monthly
    snapshot and persists the big moves twice:
      * data/tjstats_movers.json - the homepage Prospect Wire reads this
        at build time (build_site._collect_events), same pattern as the
        FA events block.
      * source_events upsert (source='tjstats') - the per-player export
        already ships source_events, so cards pick the move up for free.
    Deterministic event keys make the upsert idempotent across reruns.
    """
    from storage import tjstats_snapshot_labels, upsert_source_events
    labs = tjstats_snapshot_labels()
    if not labs:
        return None
    newer = labs[0]
    named = [l for l in labs[1:] if l.get("snapshot_kind") == "named"]
    older = named[0] if named else (labs[1] if len(labs) >= 2 else None)
    if not older:
        return None
    diff = compute_snapshot_diff(older["snapshot_label"], newer["snapshot_label"])
    movers, events = [], []
    for d in diff:
        rd, status = d.get("rank_delta"), d.get("status")
        in_top25 = min(d.get("rank") or 999, d.get("prev_rank") or 999) <= 25
        is_mover = rd is not None and (
            abs(rd) >= _MOVER_MIN_RANK_DELTA
            or (in_top25 and abs(rd) >= _MOVER_TOP25_MIN_DELTA))
        is_entry = status == "entered" and d.get("rank") is not None
        if not (is_mover or is_entry):
            continue
        row = {"player_key": d.get("player_key"), "name": d.get("name"),
               "mlbam_id": d.get("mlbam_id"), "rank": d.get("rank"),
               "prev_rank": d.get("prev_rank"), "rank_delta": rd,
               "fv_delta": d.get("fv_delta"), "status": status}
        movers.append(row)
        if d.get("player_key"):
            events.append({
                "event_key": (f"tjstats|{newer['effective_date']}|board_movement|"
                              f"{d['player_key']}|{d.get('rank')}"),
                "player_key": d["player_key"],
                "player_name": d.get("name"),
                "source": "tjstats",
                "event_date": newer["effective_date"],
                "event_type": "board_movement" if is_mover else "board_entry",
                "rank_before": d.get("prev_rank"),
                "rank_after": d.get("rank"),
                "confidence": 0.9,
                "payload": {"older_board": older["snapshot_label"],
                            "newer_board": newer["snapshot_label"],
                            "rank_delta": rd, "fv_delta": d.get("fv_delta")},
            })
    movers.sort(key=lambda m: -abs(m["rank_delta"] or 0))
    movers = movers[:_MOVER_MAX_ITEMS]
    out = {"as_of": newer["effective_date"],
           "older_board": older["snapshot_label"],
           "newer_board": newer["snapshot_label"],
           "movers": movers}
    p = out_path or (Path(__file__).parent / "data" / "tjstats_movers.json")
    p.write_text(json.dumps(out, indent=1), encoding="utf-8")
    n_ev = upsert_source_events(events) if events else 0
    log.info("tjstats movers: %d wire items, %d source events (%s vs %s)",
             len(movers), n_ev, older["snapshot_label"], newer["snapshot_label"])
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    issues = health_check()
    print("health:", "OK" if not issues else issues)
    live = scrape_live_board()
    print(f"live: {len(live['board'])} players @ {live['captured_at']} "
          f"(modified {live['source_modified_at']})")
    for r in live["board"][:5]:
        print(f"  #{r['rank']:>3} {r['mlbam_id']} FV {r['fv']} {r['type'][:3]} "
              f"{r['position']} {r['org']} {r['name']}")
