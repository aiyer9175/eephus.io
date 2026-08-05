# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Org-assignment authority tests.

THE BUG THIS PINS (owner-reported 2026-08-05): Alexander Frias was served as a
Brewers prospect, ranked 5th in the Brewers system, days after St. Louis traded
for him. Nothing was missing from our data - MLB's transaction feed carried the
trade on 2026-08-03 and his Palm Beach (STL) activation on 08-05, and our own
`trades` table held the correct `mlb_api` row. He was shown on the wrong club
because `consensus._latest_meta` resolves org as "whatever the newest snapshot
says", and on 08-04 the newest snapshot was MLB Pipeline's *Brewers* Top 30,
which had not yet dropped him. A publisher's refresh lag therefore outranked the
league's own record. 178 players were in that state when the fix was written.

Two levels of guard, because the bug had two halves:

  1. The resolver must read MLB's feed correctly (`authoritative_org_map`).
  2. The SERVED artifact must not contradict it. That is the one that would
     have caught the original defect, because everything upstream was already
     correct - only the export was wrong.

The served check is deliberately one-directional: it fires only when the
authoritative event is NEWER than every snapshot behind the served org. A
fresher scouting org is still allowed to win, which is the behavior the
scouting sources are actually good for."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
TIMESERIES = ROOT / "data" / "timeseries.json"


@pytest.fixture(scope="module")
def auth_map():
    storage = pytest.importorskip("storage")
    if not (ROOT / "prospects.db").is_file():
        pytest.skip("prospects.db not present")
    m = storage.authoritative_org_map()
    if not m:
        pytest.skip("no transaction rows to reconcile against")
    return m


def test_authoritative_orgs_are_canonical_three_letter_codes(auth_map):
    """An unresolvable affiliate ('Somerset Patriots') must be SKIPPED, never
    guessed at - a wrong org is worse than a stale one."""
    bad = {k: v for k, v in list(auth_map.items())[:4000] if len(v[0]) > 4}
    assert not bad, f"non-canonical orgs leaked into the map: {list(bad.items())[:5]}"


def test_authoritative_map_covers_a_meaningful_share(auth_map):
    assert len(auth_map) > 1000, (
        f"only {len(auth_map)} players resolved; the transaction feed is probably "
        "empty or the payload shape changed"
    )


@pytest.mark.skipif(not TIMESERIES.is_file(), reason="timeseries.json not built")
def test_served_orgs_do_not_contradict_a_newer_mlb_transaction(auth_map):
    """THE REGRESSION GUARD.

    For every served player, if MLB's feed places them on a club as of a date
    LATER than every snapshot behind the served org, the served org must agree.
    """
    payload = json.loads(TIMESERIES.read_text(encoding="utf-8"))
    players = payload.get("players") or payload
    if isinstance(players, dict):
        players = list(players.values())

    violations = []
    for p in players:
        key = p.get("player_key")
        served = p.get("org")
        rec = auth_map.get(key)
        if not rec or not served:
            continue
        auth_org, auth_date = rec
        if auth_org == served:
            continue
        newest_snap = max(
            (pt.get("snapshot_date", "") for pt in (p.get("points") or [])),
            default="",
        )
        if auth_date > newest_snap:
            violations.append({
                "player": key, "served": served, "mlb_says": auth_org,
                "mlb_date": auth_date, "newest_snapshot": newest_snap,
            })

    assert not violations, (
        f"{len(violations)} player(s) are served on a club MLB's transaction feed "
        f"contradicts with a NEWER event. First 5: {violations[:5]}"
    )
