# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Identity age sweep: find keys whose stored birth_date and whose stored
MLB career cannot belong to the same human.

WHY THIS EXISTS
---------------
On 2026-08-04 three rows reached the trade board at a published price while
being two different humans under one key. The clearest was `kelvin_herrera`:
a live DSL arm born in 2007 welded to a 2011 MLB debut and a career-WAR map
that ends in 2020. Nothing about that record was null, so every existing
guard read it as coherent.

The shipped monitor (identity_audit.py -> data/identity_collisions.json)
CANNOT see this class. Its detectors count humans per name slug in the
CURRENT roster feed and check the CURRENT binding in player_photos. The
retired half of a retired-plus-current pair is not on any current roster, so
the slug looks singular and every detector passes. The evidence that the key
holds two humans is not in the roster feed at all - it is in the arithmetic
between two fields the platform already stores:

    players.birth_date          (the CURRENT human, from the roster feed)
    career_war.seasons          (the RETIRED human's MLB career, from bbref)

If the birth_date implies the player was 13 years old in his last MLB season,
that is not a data-quality wobble; it is two humans. This sweep is that one
arithmetic check, run over every key in career_war.

It is deliberately independent of debuts.json, which is why it can run while
the pipeline is mid-rebuild: the DB is the input, opened READ-ONLY.

RELATIONSHIP TO THE OTHER TWO FIXES
-----------------------------------
  * storage._roster_status_with_derived_seasons (R5.3) backfills
    roster_status.mlb_seasons from this same career_war season map, which is
    what lets the trade board's inactive-drop rule see these rows at all.
  * bayes_trade_value._identity_age_incoherence (2026-08-04) is the belt and
    braces at pricing time: it refuses to publish a price for a row whose
    implied age at its last MLB season is impossible.
  * This sweep is the population-level view neither of those gives: it names
    every key in the class, priced or not, board or not, so a repair can be
    scoped instead of guessed.

READ-ONLY BY DEFAULT. The DB is opened with a file:...?mode=ro URI and the
tool writes nothing unless --emit is passed explicitly.

USAGE
    python tools/identity_age_sweep.py                  # print the ledger
    python tools/identity_age_sweep.py --limit 40
    python tools/identity_age_sweep.py --format json    # machine-readable
    python tools/identity_age_sweep.py --emit           # WRITES the artifact
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "prospects.db"
DEFAULT_OUT = ROOT / "data" / "identity_age_sweep.json"

# The plausible band for a player's age during a season in which he appeared
# in an MLB game. Both bounds are deliberately far outside the real record so
# that a hit is an ARITHMETIC IMPOSSIBILITY, not a judgement call:
#   youngest MLB appearance ever  : Joe Nuxhall, 15.5 (1944, wartime)
#   oldest MLB appearance ever    : Satchel Paige, 59.2 (1965, one exhibition
#                                   start), then Jamie Moyer at 49.5 (2012)
# A modern key landing outside [17, 50] is not a rare veteran; it is two
# humans sharing one key.
MIN_PLAUSIBLE_AGE = 17.0
MAX_PLAUSIBLE_AGE = 50.0

# A season is only a season if it is a real year. Guards against a junk key
# ("career", "total", "") reaching the arithmetic.
MIN_SEASON = 1870

DAYS_PER_YEAR = 365.2425


# ---------------------------------------------------------------------------
# DB access - strictly read-only
# ---------------------------------------------------------------------------

def ro_connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Open prospects.db READ-ONLY. Raises sqlite3.Error if unavailable."""
    con = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _query(con: sqlite3.Connection, sql: str, args: tuple = ()) -> list:
    """SELECT that returns [] instead of raising when a table is missing."""
    try:
        return con.execute(sql, args).fetchall()
    except sqlite3.Error:
        return []


# ---------------------------------------------------------------------------
# Pure helpers (kept free of DB access so they are directly testable)
# ---------------------------------------------------------------------------

def season_years(payload: dict | None, *, max_season: int | None = None) -> list[int]:
    """Sorted list of real season years from a career_war payload.

    The payload shape is {"seasons": {"2023": 1.5, ...}, "career_war": ...}
    (see the career_war schema comment in storage.py). A list of years is
    also accepted so a caller can pass a bare season list."""
    if not isinstance(payload, dict):
        return []
    seasons = payload.get("seasons")
    if isinstance(seasons, dict):
        raw = list(seasons.keys())
    elif isinstance(seasons, (list, tuple)):
        raw = list(seasons)
    else:
        return []
    cap = max_season if max_season is not None else date.today().year + 1
    out: list[int] = []
    for y in raw:
        try:
            yi = int(y)
        except (TypeError, ValueError):
            continue
        if MIN_SEASON <= yi <= cap:
            out.append(yi)
    return sorted(set(out))


def parse_iso_date(s: str | None) -> date | None:
    """'YYYY-MM-DD' (or a longer ISO timestamp) -> date, else None."""
    if not s or not isinstance(s, str):
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def age_in_season(birth: date, season: int) -> float:
    """Age in years on July 1 of `season` - the standard mid-season
    reference. Returns a signed float: negative means the player had not
    been born yet when that MLB season was played, which is the loudest
    possible form of the defect."""
    return (date(season, 7, 1) - birth).days / DAYS_PER_YEAR


def classify(implied_last: float,
             min_age: float = MIN_PLAUSIBLE_AGE,
             max_age: float = MAX_PLAUSIBLE_AGE) -> tuple[str | None, float]:
    """(reason, gap) for the implied age at the LAST MLB season.

    `gap` is how many years outside the plausible band the row sits, and is
    the sort key for "worst offender". Returns (None, 0.0) when plausible."""
    if implied_last < min_age:
        return "age_at_last_mlb_season_below_floor", round(min_age - implied_last, 2)
    if implied_last > max_age:
        return "age_at_last_mlb_season_above_ceiling", round(implied_last - max_age, 2)
    return None, 0.0


# ---------------------------------------------------------------------------
# The sweep
# ---------------------------------------------------------------------------

def sweep(db_path: Path = DB_PATH,
          min_age: float = MIN_PLAUSIBLE_AGE,
          max_age: float = MAX_PLAUSIBLE_AGE) -> dict:
    """Walk every key in career_war and return the ledger.

    Ledger row fields:
      player_key, player_name, birth_date, org, position, board_status
      first_mlb_season, last_mlb_season, n_mlb_seasons, career_war
      implied_age_last, implied_age_first
      reason, gap_years
      roster_mlb_seasons  : how many seasons the ROSTER FEED supplied for
                            this key (0 means the inactive-drop rule was
                            structurally blind to it before R5.3)
      latest_career_stats_season / latest_career_stats_level : the most
                            recent row of ANY level on the same key, which is
                            usually the live human standing on the fused key
    """
    con = ro_connect(db_path)
    try:
        cw_rows = _query(con, "SELECT player_key, payload_json FROM career_war")
        players = {
            r["player_key"]: r for r in
            _query(con, "SELECT player_key, player_name, birth_date, org, "
                        "position FROM players")
        }
        # SQLite resolves bare columns alongside MAX() from the row that
        # produced the max, so this is the latest-dated snapshot per key.
        statuses = {
            r["player_key"]: r["status"] for r in
            _query(con, "SELECT player_key, status, MAX(snapshot_date) AS d "
                        "FROM snapshots GROUP BY player_key")
        }
        rs_rows = {
            r["player_key"]: r["payload_json"] for r in
            _query(con, "SELECT player_key, payload_json FROM roster_status")
        }

        scanned = 0
        unscorable_no_birth = 0
        unscorable_no_seasons = 0
        hits: list[dict] = []

        for row in cw_rows:
            key = row["player_key"]
            scanned += 1
            try:
                payload = json.loads(row["payload_json"])
            except (TypeError, ValueError):
                payload = None
            years = season_years(payload)
            if not years:
                unscorable_no_seasons += 1
                continue
            prow = players.get(key)
            birth = parse_iso_date(prow["birth_date"] if prow else None)
            if birth is None:
                unscorable_no_birth += 1
                continue

            implied_last = age_in_season(birth, years[-1])
            implied_first = age_in_season(birth, years[0])
            reason, gap = classify(implied_last, min_age, max_age)
            if reason is None:
                continue

            # How many seasons the roster feed itself supplied. 0 here means
            # this row was invisible to the trade board's inactive-drop rule
            # before the R5.3 backfill, because that rule keys on
            # roster_status.mlb_seasons.
            n_roster_seasons = 0
            try:
                rs = json.loads(rs_rows.get(key) or "{}")
                if isinstance(rs, dict):
                    n_roster_seasons = len(rs.get("mlb_seasons") or [])
            except (TypeError, ValueError):
                pass

            hits.append({
                "player_key":        key,
                "player_name":       (prow["player_name"] if prow else None),
                "birth_date":        birth.isoformat(),
                "org":               (prow["org"] if prow else None),
                "position":          (prow["position"] if prow else None),
                "board_status":      statuses.get(key),
                "first_mlb_season":  years[0],
                "last_mlb_season":   years[-1],
                "n_mlb_seasons":     len(years),
                "career_war":        (payload or {}).get("career_war"),
                "implied_age_last":  round(implied_last, 1),
                "implied_age_first": round(implied_first, 1),
                "reason":            reason,
                "gap_years":         gap,
                "roster_mlb_seasons": n_roster_seasons,
            })

        # Second, targeted pass: the most recent career_stats row on each
        # FLAGGED key. career_stats payloads are large, so only the hits are
        # loaded. A recent MiLB row under a career that ended years ago is
        # the live human standing on the fused key.
        _attach_latest_stats(con, hits)
    finally:
        con.close()

    hits.sort(key=lambda h: (-h["gap_years"], h["player_key"]))
    by_reason: dict[str, int] = {}
    for h in hits:
        by_reason[h["reason"]] = by_reason.get(h["reason"], 0) + 1

    return {
        "generated_at": date.today().isoformat(),
        "db": str(db_path),
        "plausible_age_band": [min_age, max_age],
        "summary": {
            "career_war_keys_scanned":  scanned,
            "unscorable_no_birth_date": unscorable_no_birth,
            "unscorable_no_seasons":    unscorable_no_seasons,
            "hits":                     len(hits),
            "by_reason":                by_reason,
            # The subset the trade board could not see before the R5.3
            # backfill: no roster-fed seasons at all.
            "hits_invisible_to_inactive_rule":
                sum(1 for h in hits if not h["roster_mlb_seasons"]),
        },
        "hits": hits,
    }


def _attach_latest_stats(con: sqlite3.Connection, hits: list[dict]) -> None:
    """Decorate each hit with the most recent career_stats season/level on
    the same key. Mutates `hits` in place; silent when the table is absent."""
    if not hits:
        return
    keys = [h["player_key"] for h in hits]
    rows = {}
    # Chunk the IN clause so a large hit list cannot blow the variable limit.
    for i in range(0, len(keys), 400):
        chunk = keys[i:i + 400]
        qmarks = ",".join("?" * len(chunk))
        for r in _query(con,
                        "SELECT player_key, payload_json FROM career_stats "
                        f"WHERE player_key IN ({qmarks})", tuple(chunk)):
            rows[r["player_key"]] = r["payload_json"]
    for h in hits:
        latest_season, latest_level = None, None
        try:
            payload = json.loads(rows.get(h["player_key"]) or "[]")
        except (TypeError, ValueError):
            payload = []
        for r in payload if isinstance(payload, list) else []:
            if not isinstance(r, dict):
                continue
            try:
                yr = int(r.get("season"))
            except (TypeError, ValueError):
                continue
            if latest_season is None or yr > latest_season:
                latest_season, latest_level = yr, r.get("level")
        h["latest_career_stats_season"] = latest_season
        h["latest_career_stats_level"] = latest_level


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def format_report(ledger: dict, limit: int = 25) -> str:
    s = ledger["summary"]
    lo, hi = ledger["plausible_age_band"]
    out: list[str] = []
    out.append("IDENTITY AGE SWEEP - implied age at the last MLB season on each "
               "career_war key")
    out.append(f"  db            : {ledger['db']}")
    out.append(f"  plausible band: {lo:.0f} to {hi:.0f} years on July 1 of the season")
    out.append("")
    out.append(f"  career_war keys scanned : {s['career_war_keys_scanned']}")
    out.append(f"  no birth_date on file   : {s['unscorable_no_birth_date']}")
    out.append(f"  no usable season map    : {s['unscorable_no_seasons']}")
    out.append(f"  IMPOSSIBLE BINDINGS     : {s['hits']}")
    for reason, n in sorted(s["by_reason"].items()):
        out.append(f"      {reason}: {n}")
    out.append("  of those, with an EMPTY roster-fed mlb_seasons list "
               f"(invisible to the inactive rule): {s['hits_invisible_to_inactive_rule']}")
    out.append("")
    if not ledger["hits"]:
        out.append("  no impossible bindings found.")
        return "\n".join(out)
    out.append(f"  worst offenders (by years outside the band, top {limit}):")
    hdr = (f"    {'player_key':<28} {'name':<24} {'born':<11} "
           f"{'MLB seasons':<13} {'age@last':>8} {'gap':>6}  status/last-stats")
    out.append(hdr)
    out.append("    " + "-" * (len(hdr) - 4))
    for h in ledger["hits"][:limit]:
        span = f"{h['first_mlb_season']}-{h['last_mlb_season']}"
        tail = f"{h.get('board_status') or '?'}"
        if h.get("latest_career_stats_season"):
            tail += (f", stats thru {h['latest_career_stats_season']}"
                     f" {h.get('latest_career_stats_level') or ''}".rstrip())
        if not h["roster_mlb_seasons"]:
            tail += ", roster seasons EMPTY"
        out.append(f"    {(h['player_key'] or '')[:28]:<28} "
                   f"{(h['player_name'] or '')[:24]:<24} "
                   f"{h['birth_date']:<11} {span:<13} "
                   f"{h['implied_age_last']:>8.1f} {h['gap_years']:>6.1f}  {tail}")
    if len(ledger["hits"]) > limit:
        out.append(f"    ... and {len(ledger['hits']) - limit} more")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Flag player keys whose birth_date and MLB career cannot "
                    "belong to the same human. Read-only unless --emit.")
    ap.add_argument("--db", default=str(DB_PATH),
                    help="path to prospects.db (opened read-only)")
    ap.add_argument("--min-age", type=float, default=MIN_PLAUSIBLE_AGE,
                    help="floor for a plausible age in an MLB season")
    ap.add_argument("--max-age", type=float, default=MAX_PLAUSIBLE_AGE,
                    help="ceiling for a plausible age in an MLB season")
    ap.add_argument("--limit", type=int, default=25,
                    help="how many worst offenders to print")
    ap.add_argument("--format", choices=("text", "json"), default="text",
                    help="text report (default) or the raw ledger as JSON")
    ap.add_argument("--emit", action="store_true",
                    help="WRITE the ledger artifact (default is read-only)")
    ap.add_argument("--out", default=str(DEFAULT_OUT),
                    help="artifact path used only with --emit")
    args = ap.parse_args(argv)

    # Player names carry accents; a cp1252 Windows console would otherwise
    # raise UnicodeEncodeError mid-report. Degrade the glyph, never the run.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    try:
        ledger = sweep(Path(args.db), args.min_age, args.max_age)
    except sqlite3.Error as exc:
        print(f"identity_age_sweep: cannot read {args.db}: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(ledger, indent=2, sort_keys=False))
    else:
        print(format_report(ledger, args.limit))

    if args.emit:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
        print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
