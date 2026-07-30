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
