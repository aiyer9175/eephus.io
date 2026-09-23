# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The manager entity: dark until the network ingest (mgmt_managers.py, Wave C) lands.

Until then the Managers tab renders the club-season rows under a blocker, the
ejection rows that name a manager with an mlbam id are published as the ingest's
validation FIXTURE (a count, never a source), and the split rule a mid-season change
will apply is pinned as a pure function so the ingest cannot land with a different
one."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import mgmt_decisions as MD  # noqa: E402

BOARD = ROOT / "data" / "management_board.json"
ART = ROOT / "data" / "management_decisions.json"
MANAGERS = ROOT / "data" / "managers.json"
CORPUS = ROOT / ".cache" / "pbp_corpus"


@pytest.fixture(scope="module")
def board():
    if not BOARD.exists():
        pytest.skip("run python mgmt_export.py")
    return json.loads(BOARD.read_text(encoding="utf-8"))


def test_the_tab_is_dark_with_a_blocker_until_the_ledger_exists(board):
    m = board["managers"]
    if MANAGERS.exists() and m.get("live"):
        assert m["rows"], "a live manager block carries rows"
        return
    assert m["live"] is False
    assert "M-MWAR-2" in m["blocked_on"]
    assert "no manager entity anywhere on disk" in m["why"]
    assert m["fixture"]["ejection_named_managers"] > 0
    assert m["rows_until_then"] == "clubs.rows"
    assert board["sections"]["managers"]["live"] is False
    js = (ROOT / "assets" / "management.js").read_text(encoding="utf-8")
    assert "function renderManagers" in js and "renderBoard()" in js, (
        "the Managers tab renders the club-season board under the blocker")
    assert "rows_until_then" in m


def test_ejection_named_managers_agree_with_the_ledger(board):
    """The fixture. 92 of 173 ejection rows on 2025 name a manager with an id; the
    ledger, once it lands, must name the same manager for that club on that date."""
    if not ART.exists():
        pytest.skip("run python mgmt_decisions.py")
    art = json.loads(ART.read_text(encoding="utf-8"))
    fx = art["managers_fixture"]
    assert fx["ejection_named_managers"] >= 92
    assert board["managers"]["fixture"]["ejection_named_managers"] == fx["ejection_named_managers"]
    p = MD.parse_ejection("Athletics manager Mark Kotsay ejected by HP umpire John Bacon.")
    assert p == {"club_name": "Athletics", "role": "manager", "name": "Mark Kotsay", "interim": False}
    p2 = MD.parse_ejection("Nationals interim manager Miguel Cairo ejected by 1B umpire X Y.")
    assert p2["interim"] is True and p2["club_name"] == "Nationals"
    p3 = MD.parse_ejection("Braves first baseman Matt Olson ejected by HP umpire Brock Ballou.")
    assert p3["role"] == "first baseman" and p3["name"] == "Matt Olson"
    ev_path = CORPUS / "events" / "2025" / "events-2025.parquet"
    if ev_path.exists():
        import pandas as pd
        ev = pd.read_parquet(ev_path, columns=["event_type", "description", "player_id"])
        ej = ev[ev["event_type"] == "ejection"]
        mgr = [(d, pid) for d, pid in zip(ej["description"], ej["player_id"])
               if (MD.parse_ejection(str(d)) or {}).get("role") == "manager"]
        assert len(mgr) == 92
        assert all(pid == pid for _, pid in mgr), "every named manager carries an mlbam id"
    if MANAGERS.exists():
        led = json.loads(MANAGERS.read_text(encoding="utf-8"))
        if led.get("status") == "built":
            assert led.get("fixture_check", {}).get("agree") == led.get("fixture_check", {}).get("checked")


def test_an_ejection_with_no_role_word_is_attributed_off_the_club_nickname():
    """58 corpus rows carry no role word. The club is the nickname that opens the
    description, resolved against the game's two clubs only; the strict parser is
    untouched, so the manager count the fixture publishes cannot move."""
    p = MD.parse_ejection_loose("Twins Ryan Jeffers ejected by HP umpire Jordan Baker.", {"MIN", "NYY"})
    assert p == {"club_name": "Twins", "club": "MIN", "role": "other", "name": "Ryan Jeffers", "interim": False}
    p2 = MD.parse_ejection_loose("Red Sox Nate Eaton ejected by 2B umpire Vic Carapazza.", {"BOS", "CHW"})
    assert p2["club"] == "BOS" and p2["name"] == "Nate Eaton"
    p3 = MD.parse_ejection_loose("Phillies ejected by 3B umpire .", {"PHI", "NYM"})
    assert p3["club"] == "PHI" and p3["role"] == "unnamed" and p3["name"] is None
    p4 = MD.parse_ejection_loose(
        "Angels coordinator, run production Tim Laker ejected by HP umpire Mike Estabrook.", {"LAA", "HOU"})
    assert p4["club"] == "LAA" and p4["name"] == "coordinator, run production Tim Laker"
    p5 = MD.parse_ejection_loose("D-backs ejected by HP umpire .", {"ARI", "SFG"})
    assert p5["club"] == "ARI"
    # the other two clubs in the league never claim the row
    assert MD.parse_ejection_loose("Twins Ryan Jeffers ejected by HP umpire Jordan Baker.", {"NYY", "BOS"}) is None
    assert MD.parse_ejection("Twins Ryan Jeffers ejected by HP umpire Jordan Baker.") is None
    assert MD.parse_ejection_loose("Manager visits the mound.", {"MIN", "NYY"}) is None


def test_a_mid_season_change_splits_the_agent_at_the_correct_game():
    first, second = MD.split_agent_at_change([11, 12, 13, 14, 15], 13)
    assert first == [11, 12, 13] and second == [14, 15]
    first, second = MD.split_agent_at_change([11, 12, 13], 99)
    assert first == [11, 12, 13] and second == []
    first, second = MD.split_agent_at_change([11, 12, 13], 11)
    assert first == [11] and second == [12, 13]
    assert len(first) + len(second) == 3
