# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Audit F12 and F09 step 1, both fixed 2026-09-04.

F12: xfv_grade_healthy was computed only through vf.outcome_implied_fv while the
served grade on a constant-anchor row is replaced by route_floor_grade with the
provisional map. The two maps disagree by -7.0 FV at WAR 0.0, so on the routed
cohort the card put two scales side by side: measured on data/xfv.json by_player
(kind=="active"), 218 rows carried both grade_basis=="provisional_capped" and a
non-null xfv_grade_healthy, and 192 of them rendered the "healthy" grade BELOW the
served grade. Dropping a penalty cannot lower a grade, so that ordering alone
proves the basis mismatch.

THE INVARIANT PINNED HERE: where xfv_grade_healthy is not null it is on the same
basis as xfv_grade and is >= xfv_grade.

F09 step 1: _odds_grade (vf.realized_implied_fv) is what p_bucket, p_bust,
surplus_mm, dist and the band are read at, and it reached no artifact, so a served
probability could not be reproduced from data/xfv.json. It is now emitted as
xfv_grade_odds by all three scoring seams and whitelisted by efv_export._entry.
"""

from __future__ import annotations

import inspect
import json

import pytest

import efv_export as ex
import efv_score as es
import value_framework as vf


_ROUTED_KEY = "synthetic_routed_row"
_PROVISIONAL = 40.1          # what efv_ungraded's map says about this player


@pytest.fixture
def provisional_map(monkeypatch):
    """Pin _provisional_grades' cache so the routing predicate is exercised
    without reading the previous run's xfv_ungraded.json sidecar."""
    monkeypatch.setattr(es, "_prov_grades_cache", {_ROUTED_KEY: _PROVISIONAL})
    monkeypatch.setattr(es, "SERVE_PROVISIONAL_FOR_CONSTANT_COHORT", True)
    return {_ROUTED_KEY: _PROVISIONAL}


# ---- F12: the counterfactual rides the served grade's basis -------------------

def test_routed_row_serves_the_counterfactual_on_the_routed_basis(provisional_map):
    """Synthetic ROUTED row, counterfactual still on the floor knot.

    Served: constant anchor, flagship grade on the knot, so route_floor_grade
    substitutes the provisional grade. The provisional map carries no injury tilt
    (efv_ungraded applies none), so the healthy answer is that same number, and the
    invariant holds with equality. Before the fix this row served the knot (20.0)
    beside a served 40.1."""
    knot = es._outcome_floor_knot()
    served = es.route_floor_grade(_ROUTED_KEY, knot, True)
    assert served == _PROVISIONAL                      # the row really does route
    healthy = es.route_healthy_grade(_ROUTED_KEY, knot, knot, served is not None)
    assert healthy == _PROVISIONAL
    assert healthy >= served                           # THE INVARIANT
    assert healthy != knot                             # and not the other scale


def test_routed_row_emits_null_when_the_counterfactual_leaves_the_floor(provisional_map):
    """Synthetic ROUTED row whose healthy WAR clears the knot.

    The provisional grade is a per-player constant with no state for "healthy", and
    the flagship value (24.6 here, the live cameron_nelson case) is on the other
    scale and below the served 40.1. Null is the only honest answer."""
    knot = es._outcome_floor_knot()
    served = es.route_floor_grade(_ROUTED_KEY, knot, True)
    healthy = es.route_healthy_grade(_ROUTED_KEY, 24.6, 24.6, served is not None)
    assert healthy is None                             # never 24.6 beside a served 40.1


def test_unrouted_row_keeps_the_flagship_counterfactual(provisional_map):
    """Synthetic NON-ROUTED row: served and healthy are both the flagship map, so
    the counterfactual passes through untouched and stays above the served grade."""
    war = 1.2
    inj = 0.70
    served_war = es._apply_war_tilt(war, inj)
    served = vf.outcome_implied_fv(served_war, exposure_seasons=es.TARGET_SEASONS)
    flagship_healthy = vf.outcome_implied_fv(war, exposure_seasons=es.TARGET_SEASONS)
    assert es.route_floor_grade(_ROUTED_KEY, served, False) is None   # not routed
    healthy = es.route_healthy_grade(_ROUTED_KEY, flagship_healthy, flagship_healthy,
                                     False)
    assert healthy == flagship_healthy
    assert healthy >= served                           # THE INVARIANT


def test_a_row_with_no_penalty_stays_null(provisional_map):
    """No injury tilt means no counterfactual, on either basis. A null here means
    "not hurt"; the routed null above means "the routed basis cannot express it"."""
    assert es.route_healthy_grade(_ROUTED_KEY, None, None, True) is None
    assert es.route_healthy_grade(_ROUTED_KEY, None, None, False) is None


def test_run_live_uses_the_shipped_predicate():
    """The wiring, not a copy of it: the unit tests above are only worth their
    runtime if run_live routes the counterfactual through this function."""
    src = inspect.getsource(es.run_live)
    assert "route_healthy_grade(" in src
    assert "_healthy_uncorrected" in src


# ---- F09 step 1: the odds key reaches the artifact ----------------------------

def _scored_row(**over):
    s = {"player_key": "synthetic_odds_row", "kind": "active", "position": "SS",
         "consensus_fv": 45.0, "xfv_grade": 41.9, "xfv_war_6yr": 1.2,
         "p_bucket": {"bust": 0.5}, "surplus_mm": 3.1, "p_bust": 0.5}
    s.update(over)
    return s


def test_entry_whitelist_carries_the_odds_key():
    """_entry is a WHITELIST: a field it does not name never reaches data/xfv.json."""
    e = ex._entry(_scored_row(xfv_grade_odds=61.712), "hit", "active")
    assert e["xfv_grade_odds"] == 61.712
    assert e["xfv_grade"] == 41.9                      # and the two stay distinct


def test_entry_serializes_a_row_without_the_odds_key():
    """A scored file written before 2026-09-04 has no such field; the export must
    not grow a wall of nulls or raise on it."""
    e = ex._entry(_scored_row(), "hit", "active")
    assert "xfv_grade_odds" not in e
    json.dumps(e)


@pytest.mark.parametrize("seam", ["run", "run_live", "run_backgrade"])
def test_every_scoring_seam_emits_the_odds_key(seam):
    """All three seams compute _odds_grade and all three must publish it, or the
    reproducibility hole stays open on whichever cohort that seam writes."""
    src = inspect.getsource(getattr(es, seam))
    assert '"xfv_grade_odds"' in src
