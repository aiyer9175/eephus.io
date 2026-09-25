# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Home Top Movers, the sidebar spotlight and the wire keep eFV floor
crossings apart from re-grades.

eFV 20.0 is the model floor. A step with an endpoint there is the player
reaching or leaving the floor route, not a re-grade. On the 2026-09-23 board
all 5 served Top Movers rows and 34 of 79 /news/ grade rows were floor
crossings printed as "+24" or "-19 FV". efv_alerts._at_floor is the one
predicate; these tests pin that the home surfaces use it and that a step row
names the grade that moved (eFV)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

import build_site

RECENT = (date.today() - timedelta(days=20)).isoformat()
EARLIER = (date.today() - timedelta(days=200)).isoformat()


@pytest.fixture(autouse=True)
def ledger_path(tmp_path, monkeypatch):
    p = tmp_path / "wire_fv_first_seen.json"
    monkeypatch.setattr(build_site, "_WIRE_FV_LEDGER", p)
    return p


def _player(key, frm, to):
    delta = round(to - frm, 1)
    return {
        "player_key": key, "player_name": key.replace("_", " ").title(),
        "org": "CLE", "position": "SS", "status": "active",
        "stock": {"basis": "xfv", "delta": delta,
                  "direction": "up" if delta > 0 else "down",
                  "from_label": f"eFV {frm:.1f}", "to_label": f"eFV {to:.1f}",
                  "from_date": EARLIER, "to_date": RECENT},
    }


FLOOR_UP = _player("floor_riser", 20.0, 44.1)
FLOOR_DOWN = _player("floor_faller", 45.7, 20.0)
REGRADE_UP = _player("real_riser", 41.0, 45.2)
REGRADE_DOWN = _player("real_faller", 48.0, 44.6)
PLAYERS = [FLOOR_UP, FLOOR_DOWN, REGRADE_UP, REGRADE_DOWN]


def test_floor_predicate_is_the_alerts_one():
    assert build_site._mover_at_floor(FLOOR_UP)
    assert build_site._mover_at_floor(FLOOR_DOWN)
    assert not build_site._mover_at_floor(REGRADE_UP)
    # The shared gate still admits floor steps: efv_alerts caps them, so the
    # exclusion must live at the home call sites, not in the gate.
    assert build_site._genuine_mover_step(FLOOR_UP) == 24


def test_spotlight_skips_floor_crossings_and_reads_efv():
    html = build_site._spotlight_html(PLAYERS, {})
    assert "Floor Riser" not in html and "Floor Faller" not in html
    assert ("+4 eFV" in html) or ("-3 eFV" in html)
    assert " FV</span>" not in html


def test_wire_rows_label_efv_and_name_floor_crossings():
    events = build_site._collect_events(PLAYERS, [], [])
    vals = {e[4]: e[7] for e in events if e[1] in ("up", "down")}
    assert vals["real_riser"] == "+4 eFV"
    assert vals["real_faller"] == "-3 eFV"
    assert vals["floor_riser"] == "off eFV floor"
    assert vals["floor_faller"] == "to eFV floor"
    # Re-grades rank ahead of floor crossings on the same day.
    order = [e[4] for e in events]
    assert order.index("real_riser") < order.index("floor_riser")


def test_home_top_movers_carry_no_floor_endpoint():
    page = build_site.build_home([], {"players": PLAYERS, "graduates": []})
    start = page.index("Top Movers")
    block = page[start:page.index("</section>", start)]
    assert "Real Riser" in block and "Real Faller" in block
    assert "Floor Riser" not in block and "Floor Faller" not in block
