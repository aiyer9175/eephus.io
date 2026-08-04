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

import json
import logging
import sqlite3
from datetime import date
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

    Among UNSIGNED records, the NEWER draft year wins (a re-drafted
    prospect's latest entry point is canonical).

    Among SIGNED records, the OLDER draft year wins: a signed player is
    a pro and cannot re-enter the draft, so two signed records for one
    MiLB key can only be a NAME COLLISION between different people —
    the incumbent (earlier) pro keeps the key. (Jake Bennett: the 2022
    WSN pick was being clobbered by 2026's TOR pick of a different
    Jake Bennett.)
    """
    a_signed = bool(a.get("_signed"))
    b_signed = bool(b.get("_signed"))
    if a_signed != b_signed:
        return a if a_signed else b
    a_year = a.get("year") or 0
    b_year = b.get("year") or 0
    if a_signed:  # both signed -> collision -> older wins
        return a if a_year <= b_year else b
    return a if a_year >= b_year else b


def _tjstats_extras_ids() -> dict[str, int]:
    """{player_key: mlbam_id} harvested from the TJStats snapshot `_extras`
    blob (tjstats.ingest_board stamps the board's MLBAM id there).

    A key that carries TWO different ids across snapshots is DROPPED rather
    than picked between: that is the ambiguous identity class, and guessing
    there is how two people get fused.
    """
    try:
        with connect() as con:
            rows = con.execute(
                "SELECT player_key, tools_json FROM snapshots "
                "WHERE source = 'tjstats' AND tools_json IS NOT NULL"
            ).fetchall()
    except sqlite3.Error:
        return {}
    seen: dict[str, set[int]] = {}
    for r in rows:
        key = r["player_key"]
        if not key:
            continue
        try:
            tools = json.loads(r["tools_json"]) or {}
        except (TypeError, ValueError):
            continue
        extras = tools.get("_extras") if isinstance(tools, dict) else None
        if not isinstance(extras, dict):
            continue
        try:
            mid = int(extras.get("mlbam_id"))
        except (TypeError, ValueError):
            continue
        if mid > 0:
            seen.setdefault(key, set()).add(mid)
    return {k: next(iter(v)) for k, v in seen.items() if len(v) == 1}


def _harvest_known_mlbam_ids(pairs: Iterable[tuple[str, str]],
                             by_key: dict[str, dict]) -> dict[str, int]:
    """{milb_key: mlbam_id} for draftees whose MLBAM id is ALREADY known
    somewhere in the system, ready for `storage.bind_player_ids`.

    Three id sources existed and none of them reached the id layer, which is
    the residue of the negative-cache bug that left the whole 2026 draft
    class without stats:

      * `draft_players.mlbam_id` - written straight from the MLB draft API,
        populated for 136 of the 565 signed 2026 draftees;
      * the `mlbam_id` TJStats stamps into its snapshot `_extras` blob;
      * `player_photos`, which needs no harvest because it IS the durable
        binding table - `bind_player_ids` reads it to decide what to skip.

    `pairs` is (draft_key, milb_key) for draftees that have ALREADY cleared
    every identity guard in `seed_signed_draftees`. Nothing else may be
    passed: binding an id onto a key that failed a collision guard (the two
    Jake Bennetts) is exactly the fusion those guards exist to prevent.

    A milb key whose sources DISAGREE, or that two different draft keys both
    claim, is dropped rather than guessed at - the same rule
    `bind_player_ids` applies to a key already bound to another id.

    The ID SIDE of that rule is enforced here too, because bind_player_ids
    only enforces the KEY side: its `ON CONFLICT(mlbam_id) DO UPDATE SET
    player_key` would happily REPOINT an id row that already belongs to a
    different key. Measured on the live DB 2026-08-03: MLBAM 814385 is bound
    to 'jackson_natili' while the draft API spells the same pick
    'jack_natili', so an unguarded harvest would have moved that id onto the
    draft slug. Two spellings of one identity is a merge decision, not a
    seeding decision, so the candidate is dropped and logged.
    """
    wanted = [(dk, mk) for dk, mk in pairs if dk and mk]
    if not wanted:
        return {}
    tj = _tjstats_extras_ids()
    cand: dict[str, set[int]] = {}
    for dk, mk in wanted:
        for raw in ((by_key.get(dk) or {}).get("mlbam_id"), tj.get(mk)):
            try:
                mid = int(raw)
            except (TypeError, ValueError):
                continue
            if mid > 0:
                cand.setdefault(mk, set()).add(mid)
    if not cand:
        return {}

    # {mlbam_id: player_key} already durably bound, for the id-side guard.
    try:
        from storage import load_mlbam_player_keys
        owned: dict[int, str] = {}
        for mid_s, key in load_mlbam_player_keys().items():
            try:
                owned[int(mid_s)] = key
            except (TypeError, ValueError):
                continue
    except Exception:                                     # noqa: BLE001
        log.exception("draft id seed: durable binding index unavailable - "
                      "refusing to bind without the id-side guard")
        return {}

    out: dict[str, int] = {}
    for mk, ids in cand.items():
        if len(ids) != 1:
            log.warning("draft id seed: %s has conflicting known ids %s - "
                        "not binding", mk, sorted(ids))
            continue
        mid = next(iter(ids))
        holder = owned.get(mid)
        if holder is not None and holder != mk:
            log.warning("draft id seed: MLBAM %d is already bound to %r, not "
                        "%r - not rebinding", mid, holder, mk)
            continue
        out[mk] = mid
    return out


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


def seed_signed_draftees(year: int | None = None) -> int:
    """Surface SIGNED draftees on the MiLB active board immediately.

    Promotion alone only writes the acquisitions bridge; a drafted player
    used to appear in their new org's system only once an org SOURCE
    (Pipeline org list, FG board, affiliate roster / game logs) published
    them — a days-to-weeks lag after signing. This seeds one MiLB-side
    snapshot per signed, draft-board-graded pick:

        source='draft_signing' (SYNTHETIC — grade_normalization passes it
        through raw, never quantile-maps it: the Pineda lesson),
        org = the drafting club, fv = the draft-board consensus (mean of
        latest FV per draft source), dated today.

    Real org sources supersede/blend via normal consensus once they pick
    the player up. Guards:
      * only the CURRENT year's class (older signed draftees are already
        tracked or graduated — a stale seed would resurrect them),
      * only signed picks with a known team,
      * only picks a draft board actually graded (no fabricated grades),
      * SKIP any milb_key that already has ANY real MiLB snapshot
        (leaked '<year>draft' board rows excepted) — that identity is
        either already surfaced by an org source or a name-collided
        incumbent pro (e.g. the two Jake Bennetts); never seed onto it,
      * SKIP any milb_key whose earliest signed pick is an earlier year
        (same collision, acquisitions side).

    Also binds every ALREADY-KNOWN MLBAM id for the draftees that clear
    those guards (see `_harvest_known_mlbam_ids`), through the same durable
    `storage.bind_player_ids` path the pipeline uses at 2a. Until this,
    a signed draftee's stats depended entirely on name-search resolution
    even when the draft API had handed us his id at ingest.

    Idempotent: UNIQUE(source, interval_label, player_key) upserts, and
    bind_player_ids never repoints an existing binding.
    Returns the number of snapshots written."""
    from scrapers import Snapshot
    from storage import insert_snapshots

    results = [r for r in load_draft_results(draft_year=year)
               if r.get("signed") and r.get("team") and r.get("player_key")]
    if not results:
        return 0

    by_key = load_draft_players(draft_year=year)
    canon = load_draft_canonical_keys()

    # Earliest SIGNED year per milb key across ALL years (collision guard).
    earliest_signed: dict[str, int] = {}
    for r in load_draft_results(draft_year=None):
        if not r.get("signed"):
            continue
        mk = canon.get(r.get("player_key")) or _milb_key_from_name(r.get("player_name") or "")
        yr = r.get("draft_year") or 0
        if mk and (mk not in earliest_signed or yr < earliest_signed[mk]):
            earliest_signed[mk] = yr

    try:
        from trades import canonical_org
    except ImportError:
        canonical_org = lambda t: t  # noqa: E731

    today = date.today().isoformat()
    seeds: list[Snapshot] = []
    # (draft_key, milb_key) for every draftee that clears the IDENTITY guards
    # below. Collected even when no board grade exists (fv is None): a missing
    # grade is a reason not to fabricate a snapshot, not a reason to leave a
    # known id on the floor.
    bindable: list[tuple[str, str]] = []
    with connect() as con:
        for r in results:
            dk = r["player_key"]
            yr = r.get("draft_year") or 0
            if yr < date.today().year:
                continue  # only the current class — never resurrect old draftees
            name = r.get("player_name") or (by_key.get(dk) or {}).get("player_name")
            if not name:
                continue
            mk = canon.get(dk) or _milb_key_from_name(name)
            if not mk:
                continue
            if earliest_signed.get(mk, yr) < yr:
                continue  # an earlier signed pick owns this key (collision)
            # interval_label GLOB filter: historical flat draft-board drops
            # leaked org-less amateur rows into snapshots under
            # '<year>draft' labels — those are the DRAFTEE, not a
            # pre-existing pro, so they must not block the seed.
            # ANCHOR HARDENING (2026-07-25), yield 0 today. The guard means
            # "a real MiLB source already owns this identity", but it matched
            # ANY source except draft_signing -- including performance_ingest,
            # which is not a source at all but the auto-discovery stamp (a flat
            # FV 35 constant; grade_normalization._SYNTHETIC_SOURCES refuses to
            # treat it as a graded outlet). A signed draftee who accumulated
            # 40 PA / 15 IP before this step ran would therefore have been
            # denied his REAL published draft-board FV in favour of the
            # constant. MEASURED against the live DB 2026-07-25: the old and
            # new guards select the identical 49 current-class seeds, so this
            # blocks nobody today (ingest ordering happens to keep them apart).
            # Kept because a synthetic stamp must never outrank a real grade,
            # and the ordering that currently saves us is incidental.
            pre = con.execute(
                "SELECT 1 FROM snapshots WHERE player_key=? "
                "AND source NOT IN ('draft_signing', 'performance_ingest', 'auto_detect') "
                "AND interval_label NOT GLOB '20[0-9][0-9]draft' LIMIT 1",
                (mk,),
            ).fetchone()
            if pre:
                continue  # identity already tracked by a real MiLB source
            bindable.append((dk, mk))
            fv = _draft_board_consensus_fv(dk)
            if fv is None:
                continue  # no board grade — nothing honest to seed
            meta = by_key.get(dk) or {}
            seeds.append(Snapshot(
                source="draft_signing",
                snapshot_date=today,
                interval_label=f"{yr} Draft Class",
                player_key=mk,
                player_name=name,
                position=meta.get("position") or r.get("position"),
                org=canonical_org(r.get("team")) or r.get("team"),
                rank=None,
                fv=float(fv),
                status="active",
            ))

    n = insert_snapshots(seeds) if seeds else 0

    # Bind the ids we ALREADY hold, through the durable path (player_photos)
    # rather than a private cache format. Same caller shape as run_monthly's
    # step 2a: best-effort, never fatal to the seed itself. bind_player_ids
    # refuses to repoint a key that is already bound to a different id, so a
    # bad harvest cannot fuse two identities.
    n_bound = 0
    try:
        from storage import bind_player_ids
        known_ids = _harvest_known_mlbam_ids(bindable, by_key)
        if known_ids:
            n_bound = bind_player_ids(known_ids)
    except Exception:                                     # noqa: BLE001
        log.exception("draft id seeding failed - continuing")

    log.info("seed_signed_draftees(year=%s): %d signed draftees seeded, "
             "%d known MLBAM ids bound", year, n, n_bound)
    return n


def _draft_board_consensus_fv(draft_key: str) -> float | None:
    """Mean of the LATEST FV per draft source for one draft prospect
    (fangraphs / mlb_pipeline_draft / espn_draft), None if never graded."""
    with connect() as con:
        rows = con.execute(
            """SELECT source, fv FROM draft_snapshots
               WHERE player_key=? AND fv IS NOT NULL
               ORDER BY snapshot_date""",
            (draft_key,),
        ).fetchall()
    latest: dict[str, float] = {}
    for r in rows:
        latest[r["source"]] = float(r["fv"])  # later rows overwrite = latest
    if not latest:
        return None
    return round(sum(latest.values()) / len(latest), 1)


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
