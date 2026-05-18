#!/usr/bin/env python3
"""
Audit cached MLBAM IDs against the MLB Stats API.

Reads `.cache/mlbam_ids.json` and for every (player_key, mlbam_id) pair we
have cached, batch-fetches the corresponding `/people/{id}` record from
the MLB API and verifies the returned fullName matches the player_name we
have for that key in the DB.

A mismatch means we cached an ID that points to a different person — e.g.
`max_clark -> 820072` resolved to "Alex Clark" (a different person). That
breaks every subsequent stat-line / birth-date fetch for that prospect.

The script:
  1. Loads all (player_key, mlbam_id) pairs.
  2. Batches them into /people?personIds=... groups of 100.
  3. For each, normalises the API fullName and our player_name, then
     compares. Allows for: accent-stripping, suffix-stripping, alias
     translations, and last-name-only fallback (for nickname cases like
     "Dom Keegan" vs "Dominic Keegan").
  4. Prints a mismatch report.
  5. With --fix, nulls the offending cache entries so the next run will
     re-resolve them through the full resolver chain.

Usage:
    py -3 audit_mlbam_ids.py            # dry-run, report only
    py -3 audit_mlbam_ids.py --fix      # also clear bad cache entries
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
import unicodedata
from pathlib import Path

import requests

ROOT          = Path(__file__).parent
CACHE_FILE    = ROOT / ".cache" / "mlbam_ids.json"
DB_PATH       = ROOT / "prospects.db"
MLB_API       = "https://statsapi.mlb.com/api/v1"
BATCH_SIZE    = 100      # /people?personIds=... limit
RATE_LIMIT_S  = 0.4

# Same aliases as in stats.py — names we KNOW map to MLB API's preferred form.
_NAME_ALIASES = {
    "leodalis_de_vries": "Leo De Vries",
    "dominic_keegan":    "Dom Keegan",
    "leonardo_bernal":   "Leo Bernal",
    "markevian_hence":   "Tink Hence",
    "samuel_stafura":    "Sammy Stafura",
    "zachary_root":      "Zach Root",
}

_SUFFIX_RE = re.compile(r"\s+(jr\.?|sr\.?|ii|iii|iv)$", re.IGNORECASE)


def normalize(name: str) -> str:
    """Strip accents, lowercase, drop punctuation/suffixes, collapse spaces."""
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().strip()
    s = _SUFFIX_RE.sub("", s)
    s = re.sub(r"[^a-z0-9\s]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s


def names_match(expected: str, actual: str, player_key: str) -> bool:
    """True if expected name and API-returned fullName are the same person."""
    e = normalize(expected)
    a = normalize(actual)
    if e == a:
        return True
    # Try alias for this key
    alias = _NAME_ALIASES.get(player_key)
    if alias and normalize(alias) == a:
        return True
    # Last-name-only fallback (handles Dom vs Dominic, J.C. vs JC, etc.)
    e_parts = e.split()
    a_parts = a.split()
    if e_parts and a_parts and e_parts[-1] == a_parts[-1]:
        # Last names match; also require first-letter match on first name
        if e_parts[0] and a_parts[0] and e_parts[0][0] == a_parts[0][0]:
            return True
    return False


def fetch_people_batch(ids: list[int]) -> dict[int, dict]:
    """Fetch /people?personIds=... and return {id: person_record}."""
    if not ids:
        return {}
    csv = ",".join(str(i) for i in ids)
    url = f"{MLB_API}/people?personIds={csv}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    out: dict[int, dict] = {}
    for p in resp.json().get("people", []):
        out[int(p["id"])] = p
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit cached MLBAM IDs.")
    ap.add_argument("--fix", action="store_true",
                    help="Null out cache entries whose name doesn't match.")
    args = ap.parse_args()

    # Load cache
    cache: dict[str, int | None] = json.loads(CACHE_FILE.read_text())
    valid: dict[str, int] = {k: v for k, v in cache.items() if v is not None}
    print(f"Auditing {len(valid)} cached MLBAM IDs "
          f"(of {len(cache)} cache entries total)...")

    # Load player_names from DB so we have the expected name per key
    con = sqlite3.connect(DB_PATH)
    expected_names: dict[str, str] = {}
    rows = con.execute(
        """SELECT player_key, player_name FROM
              (SELECT player_key, player_name FROM snapshots
               UNION SELECT player_key, player_name FROM players)
           WHERE player_key IN ({seq})""".format(
                seq=",".join("?" * len(valid))
           ),
        list(valid.keys()),
    ).fetchall()
    for k, n in rows:
        # Prefer the first one we see; for prospects, the name is consistent
        expected_names.setdefault(k, n)
    con.close()

    # Batch fetch
    id_to_key: dict[int, str] = {v: k for k, v in valid.items() if k in expected_names}
    ids_sorted = sorted(id_to_key.keys())
    print(f"Resolved expected names for {len(id_to_key)} entries.")
    print(f"Fetching /people in batches of {BATCH_SIZE} "
          f"({(len(ids_sorted) + BATCH_SIZE - 1) // BATCH_SIZE} batches)...")

    api_records: dict[int, dict] = {}
    for i in range(0, len(ids_sorted), BATCH_SIZE):
        batch = ids_sorted[i:i + BATCH_SIZE]
        try:
            api_records.update(fetch_people_batch(batch))
        except Exception as e:
            print(f"  batch {i // BATCH_SIZE + 1} failed: {e}")
        time.sleep(RATE_LIMIT_S)
        if (i // BATCH_SIZE + 1) % 5 == 0:
            print(f"  {min(i + BATCH_SIZE, len(ids_sorted))} / {len(ids_sorted)} fetched")

    print(f"Got {len(api_records)} person records.")

    # Compare
    mismatches: list[tuple[str, int, str, str]] = []
    missing_in_api: list[tuple[str, int]] = []
    for pid in ids_sorted:
        key      = id_to_key[pid]
        expected = expected_names[key]
        rec      = api_records.get(pid)
        if rec is None:
            missing_in_api.append((key, pid))
            continue
        actual = rec.get("fullName", "")
        if not names_match(expected, actual, key):
            mismatches.append((key, pid, expected, actual))

    # Report
    print()
    print("=" * 72)
    print(f"  Audit summary")
    print("=" * 72)
    print(f"  Total cached IDs checked:    {len(ids_sorted)}")
    print(f"  Name mismatches (BAD ID):    {len(mismatches)}")
    print(f"  Not found in API:            {len(missing_in_api)}")
    print(f"  OK:                          {len(ids_sorted) - len(mismatches) - len(missing_in_api)}")

    if mismatches:
        print()
        print("Mismatches (cached ID points to a DIFFERENT person):")
        print(f"  {'player_key':30} {'mlbam_id':>9}  expected -> actual")
        for key, pid, expected, actual in mismatches:
            print(f"  {key:30} {pid:>9}  {expected!r} -> {actual!r}")

    if missing_in_api:
        print()
        print("Cached IDs that the API doesn't have a record for:")
        for key, pid in missing_in_api[:10]:
            print(f"  {key:30} -> {pid}")
        if len(missing_in_api) > 10:
            print(f"  ... and {len(missing_in_api) - 10} more")

    # Fix
    if args.fix and (mismatches or missing_in_api):
        for key, _, _, _ in mismatches:
            cache[key] = None
        for key, _ in missing_in_api:
            cache[key] = None
        CACHE_FILE.write_text(json.dumps(cache, indent=2, sort_keys=True))
        print()
        print(f"--fix: nulled {len(mismatches) + len(missing_in_api)} bad cache entries.")
        print("       Re-run 'py -3 run_monthly.py' to re-resolve them.")
    elif mismatches or missing_in_api:
        print()
        print("Re-run with --fix to null these entries so they get re-resolved.")

    return 0 if not mismatches else 1


if __name__ == "__main__":
    sys.exit(main())
