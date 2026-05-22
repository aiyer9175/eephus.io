"""Overseas → MiLB promotion.

When a KBO/NPB prospect signs with an MLB team, they cross from the
`overseas_*` tables into the regular MiLB pipeline. Two triggers, ORed:

  A. **Snapshot has status='signed'** — set by overseas_csv when the FG
     `Proj Team` column carries an MLB org code (e.g., "LAD"). FG ships
     these once a signing is confirmed; until then the cell is blank.

  B. **MLB API affiliate appearance** — when the player surfaces on any
     MLB affiliate roster (mirror of draft_promotion Trigger B).

For each signed overseas player:
  1. Upsert into `acquisitions` with `method='international_fa'`,
     `bonus_usd` from `signed_bonus_usd` or projected fallback.
  2. Link `overseas_canonical_keys` from the overseas key to the MiLB key.
  3. Flip remaining `overseas_active`/`signed` snapshots to `mlb_promoted`.

Also exposes `mark_posted(player_key, posted_date)` for the manual
posting tracker (NPB/KBO postings are rare and worth a hand-curated
ingest path).

Idempotent.
"""

from __future__ import annotations

import csv
import logging
import sqlite3
from datetime import date
from pathlib import Path

from scrapers import normalize_key
from storage import (
    connect,
    link_overseas_to_milb,
    load_overseas_canonical_keys,
    load_overseas_players,
    load_overseas_snapshots,
    upsert_acquisitions,
    upsert_overseas_posting,
)

log = logging.getLogger(__name__)


_POSTING_CSV = Path(__file__).parent / "data" / "overseas_postings.csv"


def _milb_key_from_name(name: str) -> str:
    return normalize_key(name)


def _signed_overseas_keys() -> dict[str, dict]:
    """Return {overseas_key: latest snapshot} for any overseas prospect
    whose most recent snapshot is status='signed'."""
    snaps = load_overseas_snapshots()
    by_key: dict[str, dict] = {}
    for s in sorted(snaps, key=lambda r: r.get("snapshot_date") or ""):
        by_key[s["player_key"]] = s
    return {k: s for k, s in by_key.items() if s.get("status") == "signed"}


def promote_signed_players() -> dict:
    """Promote every signed overseas snapshot into the MiLB-side
    acquisitions table + canonical-keys map. Idempotent."""
    signed = _signed_overseas_keys()
    if not signed:
        log.info("promote_signed_players: nothing to promote")
        return {"acquisitions": 0, "linked": 0, "status_flipped": 0}

    players = load_overseas_players()
    already_linked = set(load_overseas_canonical_keys().keys())

    acquisitions: dict[str, dict] = {}
    links: list[tuple[str, str, dict]] = []
    for okey, snap in signed.items():
        name = snap.get("player_name") or (players.get(okey) or {}).get("player_name")
        if not name:
            continue
        milb_key = _milb_key_from_name(name)
        if not milb_key:
            continue
        if okey not in already_linked:
            links.append((okey, milb_key, snap))
        player = players.get(okey, {})
        bonus = (player.get("signed_bonus_usd") or snap.get("proj_bonus_usd"))
        team = (player.get("signed_team") or snap.get("proj_team"))
        rec = {
            "method":       "international_fa",
            "year":         (player.get("signed_date") or "")[:4]
                            or (snap.get("snapshot_date") or "")[:4],
            "round_label":  None,
            "pick_round":   None,
            "pick_overall": None,
            "bonus_usd":    bonus,
            "team_name":    team,
            "school":       snap.get("current_team"),  # foreign club
            "signing_date": player.get("signed_date"),
        }
        # Convert string year to int when possible.
        try:
            rec["year"] = int(rec["year"]) if rec["year"] else None
        except (TypeError, ValueError):
            rec["year"] = None
        existing = acquisitions.get(milb_key)
        if existing is None:
            acquisitions[milb_key] = rec
        else:
            for k, v in rec.items():
                if v is not None:
                    existing[k] = v

    n_link = 0
    for okey, mkey, snap in links:
        team = (players.get(okey, {}).get("signed_team")
                or snap.get("proj_team"))
        bonus = (players.get(okey, {}).get("signed_bonus_usd")
                 or snap.get("proj_bonus_usd"))
        try:
            link_overseas_to_milb(okey, mkey,
                                  signed_team=team, signed_bonus_usd=bonus,
                                  signed_date=date.today().isoformat())
            n_link += 1
        except sqlite3.Error as e:
            log.warning("promote: link %s -> %s failed: %s", okey, mkey, e)

    n_ac = upsert_acquisitions(acquisitions) if acquisitions else 0

    n_status = 0
    if links:
        with connect() as con:
            for okey, _, _ in links:
                cur = con.execute(
                    """UPDATE overseas_snapshots
                       SET status = 'mlb_promoted'
                       WHERE player_key = ? AND status != 'mlb_promoted'""",
                    (okey,),
                )
                n_status += cur.rowcount

    summary = {"acquisitions": n_ac, "linked": n_link,
               "status_flipped": n_status}
    log.info("promote_signed_players: %s", summary)
    return summary


def detect_milb_promotions(roster_keys) -> int:
    """Trigger B — when a player surfaces on an MLB affiliate roster,
    treat them as signed even if no FG signed-snapshot exists yet.
    `roster_keys` is the set of MiLB-canonical keys currently on
    affiliate rosters (mirror of the draft Trigger B contract)."""
    if not roster_keys:
        return 0
    roster_set = set(roster_keys)

    n_link = 0
    with connect() as con:
        rows = con.execute(
            "SELECT player_key, player_name FROM overseas_players "
            "WHERE promoted_key IS NULL"
        ).fetchall()
    for r in rows:
        milb_key = _milb_key_from_name(r["player_name"])
        if milb_key in roster_set:
            try:
                link_overseas_to_milb(r["player_key"], milb_key,
                                       signed_date=date.today().isoformat())
                with connect() as con:
                    con.execute(
                        "UPDATE overseas_snapshots SET status='mlb_promoted' "
                        "WHERE player_key=? AND status != 'mlb_promoted'",
                        (r["player_key"],),
                    )
                n_link += 1
            except sqlite3.Error as e:
                log.warning("detect_milb_promotions: %s failed: %s",
                            r["player_key"], e)
    if n_link:
        log.info("detect_milb_promotions: linked %d players via roster match", n_link)
    return n_link


def ingest_postings(csv_path: Path | None = None) -> int:
    """Read data/overseas_postings.csv and stamp posting status.

    Columns: player_name, league, posted_date, posting_window_end

    KBO/NPB postings are rare enough (1-3/year) that a hand-curated CSV
    is the cleanest source. Each row marks the matching overseas_players
    entry as 'posted' with the given date."""
    p = csv_path or _POSTING_CSV
    if not p.exists():
        return 0
    n = 0
    players = load_overseas_players()
    name_to_key = {(v.get("player_name") or "").lower(): k
                   for k, v in players.items()}
    with p.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            name = (r.get("player_name") or "").strip()
            if not name:
                continue
            pk = name_to_key.get(name.lower())
            if not pk:
                # Try a normalize_key match across leagues.
                target = _milb_key_from_name(name)
                for k, v in players.items():
                    if _milb_key_from_name(v.get("player_name", "")) == target:
                        pk = k
                        break
            if not pk:
                log.warning("ingest_postings: no match for '%s'", name)
                continue
            posted_date = (r.get("posted_date") or "").strip() or None
            upsert_overseas_posting(pk, posted_date=posted_date)
            n += 1
    if n:
        log.info("ingest_postings: marked %d players as 'posted'", n)
    return n
