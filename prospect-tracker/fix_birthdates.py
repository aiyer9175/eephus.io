#!/usr/bin/env python3
"""
One-time birth date cleanup.

Three passes:
  1. Clear birth dates that are clearly wrong (born before 1994 — fetched
     for the wrong player back when the MLBAM ID cache contained bad IDs).
  2. Bulk-fill from the full MLB+MiLB player index: we already fetch the
     index for MLBAM ID resolution; every entry carries a birth date.
     Matched by MLBAM ID first, then by normalized name.
  3. Individual /people/{id} API calls for any prospect that still has a
     valid cached ID but wasn't found in the current-season index (60-day
     IL, recently graduated, etc.).

Run once:
    py -3 fix_birthdates.py
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
import unicodedata
from pathlib import Path

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s fix_birthdates: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

DB_PATH      = Path(__file__).parent / "prospects.db"
CACHE_FILE   = Path(__file__).parent / ".cache" / "mlbam_ids.json"
MLB_API      = "https://statsapi.mlb.com/api/v1"
RATE_LIMIT   = 0.3   # seconds between individual API calls
BAD_YEAR_CUTOFF = "1994"   # born before this → treat as wrong


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9\s]", "", s)
    s = re.sub(r"\s+", "_", s)
    return s


def _build_index(season: int) -> tuple[dict[int, str], dict[str, tuple[int, str]]]:
    """
    Returns:
      by_id   : {mlbam_id: birth_date}
      by_name : {norm_name: (mlbam_id, birth_date)}
    """
    by_id:   dict[int, str]               = {}
    by_name: dict[str, tuple[int, str]]   = {}

    for sport_id in (16, 14, 13, 12, 11, 1):
        url = f"{MLB_API}/sports/{sport_id}/players?season={season}"
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            people = resp.json().get("people", [])
        except Exception as e:
            log.warning("index fetch failed (sportId=%s): %s", sport_id, e)
            time.sleep(RATE_LIMIT)
            continue
        for p in people:
            pid  = int(p["id"])
            bd   = p.get("birthDate") or ""
            name = p.get("fullName", "")
            if bd:
                by_id[pid] = bd
            if name:
                by_name[_norm(name)] = (pid, bd)
        log.info("sportId=%s: %d players", sport_id, len(people))
        time.sleep(RATE_LIMIT)

    return by_id, by_name


def _fetch_birth_date_api(mlbam_id: int) -> str | None:
    """Fetch birth date from /people/{id}."""
    try:
        r = requests.get(f"{MLB_API}/people/{mlbam_id}", timeout=15)
        r.raise_for_status()
        people = r.json().get("people", [])
        if people:
            return people[0].get("birthDate") or None
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row

    # Load ID cache
    id_cache: dict[str, int | None] = json.loads(CACHE_FILE.read_text()) if CACHE_FILE.exists() else {}
    valid_ids = {k: v for k, v in id_cache.items() if v is not None}

    # All active prospect keys + names
    rows = con.execute(
        """SELECT DISTINCT s.player_key, s.player_name
           FROM snapshots s
           WHERE s.status != 'graduated'"""
    ).fetchall()
    prospects = {r["player_key"]: r["player_name"] for r in rows}
    log.info("%d non-graduated prospect keys", len(prospects))

    # Current birth dates in DB
    existing_bds: dict[str, str] = dict(
        con.execute("SELECT player_key, birth_date FROM players WHERE birth_date IS NOT NULL").fetchall()
    )

    # ── Pass 1: clear bad birth dates ──────────────────────────────────────
    bad_keys = [k for k, v in existing_bds.items()
                if k in prospects and v[:4] < BAD_YEAR_CUTOFF]
    if bad_keys:
        con.executemany(
            "UPDATE players SET birth_date = NULL WHERE player_key = ?",
            [(k,) for k in bad_keys],
        )
        con.commit()
        log.info("Pass 1: cleared %d bad birth dates (pre-%s)", len(bad_keys), BAD_YEAR_CUTOFF)
        for k in bad_keys:
            del existing_bds[k]
    else:
        log.info("Pass 1: no bad birth dates to clear")

    # ── Pass 2: bulk-fill from full player index ────────────────────────────
    from datetime import date
    season = date.today().year
    log.info("Pass 2: building full player index for %d...", season)
    by_id, by_name = _build_index(season)
    log.info("  index has %d by-ID entries, %d by-name entries", len(by_id), len(by_name))

    upserted_p2 = 0
    still_missing: list[tuple[str, str, int | None]] = []   # (key, name, mlbam_id|None)

    for key, name in prospects.items():
        if key in existing_bds:
            continue   # already have a birth date

        bd: str | None = None
        mlbam_id = valid_ids.get(key)

        # Try by MLBAM ID
        if mlbam_id and mlbam_id in by_id:
            bd = by_id[mlbam_id]

        # Try by normalized name
        if not bd:
            entry = by_name.get(_norm(name))
            if entry:
                bd = entry[1]

        if bd:
            # Upsert into players table
            con.execute(
                """INSERT INTO players (player_key, player_name, birth_date)
                   VALUES (?, ?, ?)
                   ON CONFLICT(player_key)
                   DO UPDATE SET birth_date = excluded.birth_date""",
                (key, name, bd),
            )
            existing_bds[key] = bd
            upserted_p2 += 1
        else:
            still_missing.append((key, name, mlbam_id))

    con.commit()
    log.info("Pass 2: filled %d birth dates from player index", upserted_p2)
    log.info("Pass 2: %d prospects still missing a birth date", len(still_missing))

    # ── Pass 3: individual API calls for prospects with cached IDs ──────────
    with_id    = [(k, n, mid) for k, n, mid in still_missing if mid is not None]
    without_id = [(k, n)      for k, n, mid in still_missing if mid is None]

    log.info("Pass 3: %d individual API lookups (have ID, not in current index)...", len(with_id))
    upserted_p3 = 0
    for i, (key, name, mlbam_id) in enumerate(with_id, 1):
        bd = _fetch_birth_date_api(mlbam_id)
        if bd:
            con.execute(
                """INSERT INTO players (player_key, player_name, birth_date)
                   VALUES (?, ?, ?)
                   ON CONFLICT(player_key)
                   DO UPDATE SET birth_date = excluded.birth_date""",
                (key, name, bd),
            )
            upserted_p3 += 1
        if i % 50 == 0:
            con.commit()
            log.info("  ... %d / %d done (%d found)", i, len(with_id), upserted_p3)
        time.sleep(RATE_LIMIT)

    con.commit()
    log.info("Pass 3: filled %d more birth dates via individual API calls", upserted_p3)

    # ── Summary ──────────────────────────────────────────────────────────────
    final_bds = dict(
        con.execute("SELECT player_key, birth_date FROM players WHERE birth_date IS NOT NULL").fetchall()
    )
    active_final = {k: v for k, v in final_bds.items() if k in prospects}
    remaining = len(prospects) - len(active_final)

    log.info("")
    log.info("=== SUMMARY ===")
    log.info("Active prospects with birth date: %d / %d", len(active_final), len(prospects))
    log.info("Still missing:                    %d", remaining)
    if without_id:
        log.info("No ID cached (can't auto-fetch):  %d", len(without_id))
        log.info("  Run 'py -3 run_monthly.py' (without --skip-stats) to attempt ID resolution for these.")
    con.close()


if __name__ == "__main__":
    main()
