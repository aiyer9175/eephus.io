# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Draft → MiLB promotion.

After the draft happens, each pick needs to surface in the MiLB-side
data model too — primarily through the existing `acquisitions` table so
the Active prospect cards can show "Drafted 2024 R1 #7 by STL". Two
triggers signal a player is "promoted":

  A. **FG post-draft CSV present** — already parsed by draft_csv.py;
     surfaces as `draft_results` rows with `team IS NOT NULL` and
     `source='fg_draft_csv'`.

  B. **MLB Stats API draft endpoint** — `scrape_mlb_draft_tracker(year)`
     returns the authoritative pick + bonus + slot per year; surfaces
     as `draft_results` rows with `source='mlb_stats_api'`.

This module orchestrates the post-promotion bookkeeping:
  1. Upsert into `acquisitions` (method='draft', round/pick/bonus/team/school)
  2. Link the draft player_key → MiLB-style key via `draft_canonical_keys`
  3. Flip draft_snapshots.status from 'draft_active' to 'drafted'

It is idempotent. Safe to re-run after every ingest cycle.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Iterable

from scrapers import normalize_key
from storage import (
    connect,
    link_draft_to_milb,
    load_draft_canonical_keys,
    load_draft_players,
    load_draft_results,
    upsert_acquisitions,
)

log = logging.getLogger(__name__)


def _milb_key_from_name(name: str) -> str:
    """The canonical MiLB-side key for a drafted player. Matches
    scrapers.normalize_key — exactly what `insert_snapshots` will key on
    once the player surfaces in an affiliate roster scrape."""
    return normalize_key(name)


def _better_draft_record(a: dict, b: dict) -> dict:
    """Pick the canonical draft record between two candidates for the
    same MiLB key.

    SIGNED beats UNSIGNED unconditionally — an HS prospect who didn't
    sign and was re-drafted out of college should always read as
    "drafted by the college team" because that's how they actually
    entered pro ball.

    Among same-signed records, the NEWER draft year wins. (A re-signed
    player who was drafted twice but signed both times is rare — the
    canonical entry should still be the latest.)
    """
    a_signed = bool(a.get("_signed"))
    b_signed = bool(b.get("_signed"))
    if a_signed != b_signed:
        return a if a_signed else b
    a_year = a.get("year") or 0
    b_year = b.get("year") or 0
    return a if a_year >= b_year else b


def promote_drafted_players(year: int | None = None) -> dict:
    """Promote every draft_results row whose team is known.

    For each unique (draft_year, player_key) with a `team`:
      1. Upsert into acquisitions(method='draft', year, round_label,
         pick_overall, bonus_usd, team_name, school)
      2. Add a draft_canonical_keys mapping (draft_<year>_<name> →
         normalize_key(name))
      3. Flip the draft_snapshots row's status to 'drafted'

    Returns a dict with counts. Idempotent — re-running is a no-op
    aside from updated_at timestamps."""
    results = load_draft_results(draft_year=year)
    if not results:
        log.info("promote_drafted_players: no draft_results to process")
        return {"acquisitions": 0, "linked": 0, "status_flipped": 0}

    # Pull draft_players for name + school lookups when results rows
    # don't carry them.
    by_key = load_draft_players(draft_year=year)
    already_linked = set(load_draft_canonical_keys().keys())

    acquisitions: dict[str, dict] = {}
    links: list[tuple[str, str]] = []
    for r in results:
        draft_key = r.get("player_key")
        if not draft_key:
            # The FG CSV path always supplies a key; the API path always
            # does too. Anything without one is unmatchable.
            continue
        name = r.get("player_name") or (by_key.get(draft_key) or {}).get("player_name")
        if not name:
            continue
        milb_key = _milb_key_from_name(name)
        if not milb_key:
            continue
        if draft_key not in already_linked:
            links.append((draft_key, milb_key))

        school = r.get("school") or (by_key.get(draft_key) or {}).get("school")
        # `_signed` is an internal flag used by the merge logic below;
        # stripped before upsert (the acquisitions table doesn't carry
        # a signed column — a non-null bonus_usd or downstream
        # transaction inference covers that).
        rec = {
            "method":       "draft",
            "year":         r.get("draft_year"),
            "round_label":  r.get("round_label"),
            "pick_round":   r.get("pick_in_round"),
            "pick_overall": r.get("pick_overall"),
            "bonus_usd":    r.get("bonus_usd"),
            "team_name":    r.get("team"),
            "school":       school,
            "signing_date": None,
            "_signed":      bool(r.get("signed")),
            "_draft_key":   draft_key,
        }
        # Multi-draft prospects (HS draft → didn't sign → re-drafted out
        # of college, e.g. Gage Jump 2021 SDP → 2024 ATH) used to land
        # here with a field-by-field merge that produced a frankenstein
        # record: 2024's bonus stitched onto 2021's team / round / year
        # because non-null fields from the LATER iteration overwrote
        # the earlier ones blindly. New rule:
        #   1. SIGNED record always wins over UNSIGNED.
        #   2. Among same-signed records, NEWER year wins.
        # Each draft entry is a distinct event — never field-merge them.
        existing = acquisitions.get(milb_key)
        if existing is None:
            acquisitions[milb_key] = rec
        else:
            if _better_draft_record(rec, existing) is rec:
                acquisitions[milb_key] = rec

    n_link = 0
    for dk, mk in links:
        try:
            link_draft_to_milb(dk, mk)
            n_link += 1
        except sqlite3.Error as e:
            log.warning("promote: link %s -> %s failed: %s", dk, mk, e)

    # Strip the internal `_signed` / `_draft_key` keys before persisting —
    # the acquisitions table schema doesn't carry them and upsert would
    # silently drop them anyway, but cleaning up here keeps the
    # intermediate shape obviously canonical.
    for _rec in acquisitions.values():
        _rec.pop("_signed", None)
        _rec.pop("_draft_key", None)
    n_ac = upsert_acquisitions(acquisitions) if acquisitions else 0

    # Flip status on draft_snapshots for any draft_key we now have linked.
    n_status = 0
    if links:
        with connect() as con:
            for dk, _ in links:
                cur = con.execute(
                    """UPDATE draft_snapshots
                       SET status = 'drafted'
                       WHERE player_key = ? AND status != 'drafted'""",
                    (dk,),
                )
                n_status += cur.rowcount

    summary = {"acquisitions": n_ac, "linked": n_link, "status_flipped": n_status}
    log.info("promote_drafted_players(year=%s): %s", year, summary)
    return summary


def detect_milb_promotions(roster_keys: Iterable[str]) -> int:
    """Trigger B — when a player appears in any MLB affiliate roster, mark
    them as 'drafted' even if no draft_results row exists yet.

    `roster_keys` should be the set of player_keys currently appearing in
    any affiliate roster (already normalized via scrapers.normalize_key).
    Compares against draft_players where promoted_key IS NULL.

    Returns the number of newly-linked players. Conservative: only
    matches when the MiLB key equals normalize_key(draft player_name)."""
    if not roster_keys:
        return 0
    roster_set = set(roster_keys)

    n_link = 0
    with connect() as con:
        rows = con.execute(
            "SELECT player_key, player_name FROM draft_players WHERE promoted_key IS NULL"
        ).fetchall()
    for r in rows:
        milb_key = _milb_key_from_name(r["player_name"])
        if milb_key in roster_set:
            try:
                link_draft_to_milb(r["player_key"], milb_key)
                with connect() as con:
                    con.execute(
                        "UPDATE draft_snapshots SET status='drafted' "
                        "WHERE player_key=? AND status='draft_active'",
                        (r["player_key"],),
                    )
                n_link += 1
            except sqlite3.Error as e:
                log.warning("detect_milb_promotions: %s failed: %s",
                            r["player_key"], e)

    if n_link:
        log.info("detect_milb_promotions: linked %d players via roster match", n_link)
    return n_link
