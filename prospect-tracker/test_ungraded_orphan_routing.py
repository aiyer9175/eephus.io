# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The board / provisional PARTITION (owner decision, 2026-07-30).

Removing `baseballamerica_statcast_by_age`'s fabricated FV 40 dropped seven players
off the served board because that snapshot was their only row in the database. The
owner's decision was to route them to the provisional path (`efv_ungraded`) rather
than invent a replacement consensus FV, and to fix it at the SEAM so the behaviour is
a general rule rather than seven special cases.

The seam turned out to be already general: `efv_ungraded.flagship_owns` and
`consensus.compute_consensus_point` are exact complements, so a rostered player with
production and no scout grade already routes to the provisional pool. What was missing
was a test saying so, which is this file. If a future change makes a player without a
scout grade fail BOTH predicates, they vanish from the product entirely and silently,
and that is the failure these tests exist to catch.
"""

from __future__ import annotations

import pytest

import efv_ungraded
from consensus import compute_consensus_point
from scrapers import Snapshot


def _snap(**kw):
    """One identity-only snapshot, shaped like the row baseballamerica_statcast_by_age
    now emits: real player, real org and position, no FV and no rank."""
    base = dict(source="baseballamerica_statcast_by_age", snapshot_date="2026-06-03",
                interval_label="BA Statcast by Age 2026", player_key="orphan",
                player_name="Orphan Guy", position="C", org="CIN",
                rank=None, fv=None, status="active")
    base.update(kw)
    return Snapshot(**base)


# --------------------------------------------------------------------------- #
# half 1: an identity-only snapshot produces NO consensus point
# --------------------------------------------------------------------------- #
def test_a_snapshot_with_no_fv_and_no_rank_produces_no_consensus_point():
    # This is why the seven left the board: their single snapshot stopped voting, so
    # the player has no consensus point, so storage's `if not p.points` ejects them.
    assert compute_consensus_point([_snap()], event_date="2026-06-03") is None


def test_a_snapshot_with_an_fv_does_produce_a_consensus_point():
    # The control: put the fabricated grade back and the same player is board-eligible
    # again. That is the whole mechanism the seven orphans exposed.
    pt = compute_consensus_point([_snap(fv=40.0)], event_date="2026-06-03")
    assert pt is not None and pt.consensus_fv_raw is not None


# --------------------------------------------------------------------------- #
# half 2: no consensus grade means the PROVISIONAL path owns the row
# --------------------------------------------------------------------------- #
def test_flagship_owns_exactly_the_rows_that_carry_a_consensus_grade():
    assert efv_ungraded.flagship_owns({"fv_raw": 38.33}) is True
    assert efv_ungraded.flagship_owns({"fv_raw": 20.0}) is True     # a low grade is still a grade
    assert efv_ungraded.flagship_owns({"fv_raw": None}) is False
    assert efv_ungraded.flagship_owns({}) is False
    assert efv_ungraded.flagship_owns(None) is False


def test_the_partition_has_no_gap_and_no_overlap():
    # Every roster row is on exactly one side. A row the flagship does not own is a
    # provisional candidate, and vice versa: there is no third state where a player
    # with production simply disappears.
    rows = [{"fv_raw": 45.0}, {"fv_raw": None}, {}, {"fv_raw": 0.0}]
    owned = [r for r in rows if efv_ungraded.flagship_owns(r)]
    provisional = [r for r in rows if not efv_ungraded.flagship_owns(r)]
    assert len(owned) + len(provisional) == len(rows)
    assert not [r for r in owned if r in provisional]
    # fv_raw 0.0 is a GRADE, not a missing one: `is not None`, never truthiness.
    assert {"fv_raw": 0.0} in owned


def test_a_fabricated_grade_moves_a_player_to_the_wrong_side_of_the_partition():
    """The seven orphans, in miniature.

    A player whose only snapshot carries a fabricated FV reads as flagship-owned. Take
    the fabrication away and the same player is a provisional candidate. Nothing else
    about them changed, which is the whole point: the fix was removing the fabrication,
    not adding a rule.
    """
    with_fabrication = {"player_key": "jacob_friend", "fv_raw": 38.33}
    without = {"player_key": "jacob_friend", "fv_raw": None}
    assert efv_ungraded.flagship_owns(with_fabrication) is True
    assert efv_ungraded.flagship_owns(without) is False


# ---------------------------------------------------------------------------
# CATALOG PIN. data_catalog.py names THIS file as the shape pin for
# xfv_ungraded.json, and until now nothing here mentioned that artifact, so
# /sources/ rendered the row with no receipt at all - a claimed citation the
# page could not show. The fix the ratchet asks for is this test, not a
# repointed pinned_by.
def test_xfv_ungraded_json_carries_the_shape_the_catalog_promises():
    """xfv_ungraded.json: provisional grades for players no public source has
    graded, addressable by player_key and by mlbam id."""
    import json
    from pathlib import Path
    p = Path(__file__).resolve().parent / "data" / "xfv_ungraded.json"
    if not p.exists():
        pytest.skip("xfv_ungraded.json not built in this tree")
    d = json.loads(p.read_text(encoding="utf-8"))
    assert set(d) >= {"meta", "by_player", "by_mlbam"}
    assert isinstance(d["by_player"], dict) and isinstance(d["by_mlbam"], dict)
    if d["by_player"]:
        grade = next(iter(d["by_player"].values()))
        # the row's whole promise is "still carries a number"
        assert isinstance(grade, (int, float, dict)), type(grade)


# --------------------------------------------------------------------------- #
# PV-07 (owner answers PG-Q1 / PG-Q2, 2026-09-25): a SECOND partition, on the board.
# flagship_owns asks "is there a consensus grade?", and the fabricated performance
# anchor (performance_ingest, FV 35) answers yes. The board section asks "has any LABEL
# source ever graded him?", and that anchor answers no. The two predicates are different
# on purpose: a routed row keeps its flagship-owned eFV entry (trade values and farm
# points keep their inputs) while it leaves the shared rank for the section.
# --------------------------------------------------------------------------- #
def test_a_performance_anchor_row_is_flagship_owned_but_in_the_section():
    import storage
    anchor_only = {"fv_raw": 35.0, "points": [
        {"per_source": {"performance_ingest": {"fv_published": 35.0}},
         "sources_contributing": ["performance_ingest"]}]}
    assert efv_ungraded.flagship_owns(anchor_only) is True
    assert storage.row_in_prov_section(anchor_only) is True
    graded = {"fv_raw": 40.0, "points": [{"per_source": {"fangraphs": {"fv_published": 40.0}}}]}
    assert efv_ungraded.flagship_owns(graded) is True
    assert storage.row_in_prov_section(graded) is False


def test_the_board_partition_has_no_gap_and_no_overlap():
    """Every served active row is ranked or in the section, never both, never neither."""
    import json
    from pathlib import Path
    import storage
    p = Path(__file__).resolve().parent / "data" / "timeseries.json"
    if not p.exists():
        pytest.skip("timeseries.json not built in this tree")
    doc = json.loads(p.read_text(encoding="utf-8"))
    if "prov_section" not in doc:
        pytest.skip("payload predates the section")
    actives = [r for r in doc["players"] if r.get("board_key_tail") is not None]
    ranked = {r["player_key"] for r in actives if r.get("overall_rank") is not None}
    section = {r["player_key"] for r in actives if storage.row_in_prov_section(r)}
    assert not ranked & section
    assert ranked | section == {r["player_key"] for r in actives}


# --------------------------------------------------------------------------- #
# Owner ask 5 (Q9_10, 2026-10-08): what each side of the partition PRINTS. A flagship-
# owned row eFV abstains on prints its consensus grade labelled (C mark, rounded up); a
# provisional row prints its eFV and never a consensus number; an orphan with neither
# prints no number at all. gradeBlock is the one resolver every display reads.
# --------------------------------------------------------------------------- #
def test_each_side_of_the_partition_prints_its_own_labelled_grade():
    from test_efv_display_helpers import make_js_ctx
    import json
    js = make_js_ctx()

    def gb(row):
        return json.loads(js.eval("JSON.stringify(gradeBlock(%s))" % row))

    owned = gb('{player_key: "o", fv_close: 38.33}')
    assert owned["basis"] == "consensus" and owned["label"] == "39"     # rounded UP
    assert owned["consTip"] == "Consensus FV (no eFV for this player)"
    prov = gb('{player_key: "p", _xfv_entry: {xfv_grade: 31.6, xfv_ungraded: true}, '
              '_x: {xfv_grade: 31.6, xfv_ungraded: true}}')
    assert prov["basis"] == "efv" and prov["label"] == "32" and prov["provisional"]
    orphan = gb('{player_key: "x"}')
    assert orphan["basis"] == "none" and orphan["label"] is None
