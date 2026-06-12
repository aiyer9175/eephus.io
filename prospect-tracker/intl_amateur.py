# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""International-amateur FV routing (owner directive 2026-06-12).

Source boards that cover the international market mix two populations:

  * true OVERSEAS pros (NPB / KBO / CPBL veterans working toward a
    posting) - they belong in the Overseas section; and
  * INTERNATIONAL AMATEUR free agents (the July-2 class teenagers) -
    they are (or become) ordinary tracked prospects, and a board FV for
    them belongs on the PROSPECT's source history, never in Overseas.

This module owns the second population:

  match_player(name)        -> tracked player_key (exact normalized-key
                               match against the players table)
  attach_fv_snapshots(rows) -> insert per-source FV snapshots onto the
                               matched prospects (storage.insert_snapshots
                               dedupes on source+date+player, so re-runs
                               are no-ops)
  reassign_from_overseas()  -> drain every INT'L AMATEUR row that ever
                               landed in the overseas tables: matched
                               rows become prospect snapshots, ALL rows
                               leave the overseas store, the unmatched
                               remainder is written to
                               data/intl_amateur_unmatched.json so no
                               grade is silently dropped (most unmatched
                               names are future signees - re-run after
                               their class lands and they will match).

Run: python intl_amateur.py          (drain + report)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from scrapers import Snapshot, normalize_key, fix_mojibake

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
UNMATCHED_PATH = DATA_DIR / "intl_amateur_unmatched.json"

IFA_LEAGUE_CODES = {"INT'L AMATEUR", "INTL AMATEUR", "INTERNATIONAL AMATEUR",
                    "IFA", "INT'L"}


def is_ifa_league(league: str | None) -> bool:
    return bool(league) and league.strip().upper() in IFA_LEAGUE_CODES


def _player_index() -> dict[str, str]:
    """normalized key -> player_key for every tracked player."""
    import storage
    with storage.connect() as con:
        rows = con.execute("SELECT player_key, player_name FROM players").fetchall()
    idx: dict[str, str] = {}
    for key, name in rows:
        idx[key] = key
        nk = normalize_key(fix_mojibake(name or ""))
        idx.setdefault(nk, key)
    return idx


def match_player(name: str, index: dict[str, str] | None = None) -> str | None:
    idx = index if index is not None else _player_index()
    return idx.get(normalize_key(fix_mojibake(name or "")))


def attach_fv_snapshots(rows: list[dict], source: str = "fangraphs") -> tuple[int, list[dict]]:
    """rows: [{player_name, fv, fv_plus?, position?, snapshot_date,
    interval_label, country?, proj_team?, snapshot_year?}]. Returns
    (n_inserted, unmatched_rows)."""
    import storage
    idx = _player_index()
    snaps: list[Snapshot] = []
    unmatched: list[dict] = []
    for r in rows:
        if r.get("fv") is None:
            continue
        key = match_player(r.get("player_name") or "", idx)
        if key is None:
            unmatched.append(r)
            continue
        snaps.append(Snapshot(
            source=source,
            snapshot_date=str(r["snapshot_date"]),
            interval_label=str(r.get("interval_label") or f"{source} intl board"),
            player_key=key,
            player_name=r.get("player_name") or key,
            position=r.get("position"),
            org=None,
            rank=r.get("rank"),
            fv=float(r["fv"]),
            status="active",
            tools=r.get("tools"),
        ))
    n = storage.insert_snapshots(snaps) if snaps else 0
    log.info("intl_amateur: %d FV snapshots attached (%s), %d unmatched",
             n, source, len(unmatched))
    return n, unmatched


def reassign_from_overseas(persist_report: bool = True) -> dict:
    """Drain INT'L AMATEUR rows out of the overseas store (they are not
    overseas pros). Matched names get their board FV as a prospect
    snapshot at the board's era date; everything leaves overseas."""
    import storage
    placeholders = ",".join("?" for _ in IFA_LEAGUE_CODES)
    codes = sorted(IFA_LEAGUE_CODES)
    with storage.connect() as con:
        rows = [dict(r) for r in con.execute(
            f"""SELECT source, snapshot_date, interval_label, player_key,
                       player_name, position, country, proj_team, fv
                FROM overseas_snapshots
                WHERE UPPER(COALESCE(league,'')) IN ({placeholders})""",
            codes).fetchall()]
    attach_rows = [{
        "player_name": r["player_name"],
        "fv": r["fv"],
        "position": r["position"],
        "snapshot_date": r["snapshot_date"],
        "interval_label": (r["interval_label"] or "").replace("Overseas", "Int'l Board"),
        "country": r["country"],
        "proj_team": r["proj_team"],
    } for r in rows]
    n_attached, unmatched = attach_fv_snapshots(attach_rows, source="fangraphs")

    with storage.connect() as con:
        n_snap = con.execute(
            f"DELETE FROM overseas_snapshots WHERE UPPER(COALESCE(league,'')) IN ({placeholders})",
            codes).rowcount
        n_play = con.execute(
            f"""DELETE FROM overseas_players WHERE UPPER(COALESCE(league,'')) IN ({placeholders})
                AND player_key NOT IN (SELECT DISTINCT player_key FROM overseas_snapshots)""",
            codes).rowcount
    out = {"drained_snapshots": n_snap, "drained_players": n_play,
           "fv_attached": n_attached, "unmatched": len(unmatched)}
    if persist_report:
        existing = []
        try:
            existing = json.loads(UNMATCHED_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        seen = {(e.get("player_name"), e.get("snapshot_date")) for e in existing}
        for u in unmatched:
            sig = (u.get("player_name"), u.get("snapshot_date"))
            if sig not in seen:
                existing.append(u)
                seen.add(sig)
        UNMATCHED_PATH.write_text(json.dumps(existing, indent=1, ensure_ascii=False),
                                  encoding="utf-8")
    log.info("intl_amateur: drained %d overseas snapshot rows (%d players), "
             "attached %d, unmatched %d", n_snap, n_play, n_attached, len(unmatched))
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(json.dumps(reassign_from_overseas(), indent=1))
