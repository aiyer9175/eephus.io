# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Guards on the park-factor display sidecar.

The load-bearing ones: the model path stays off, the display is unclamped, and
the venue table never quietly includes the pooled non-venue.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import park_factors_export as P

ROOT = Path(__file__).parent


@pytest.fixture(scope="module")
def built():
    return P.build(json.loads(P.SRC_PATH.read_text(encoding="utf-8")))


def test_model_path_stays_off():
    """This sidecar is sanctioned only because efv_park_line is gated off
    under the registered W2 M-FAIL verdict."""
    import efv_park_line as E
    assert E.PARKLINE_HIT_DEFAULT is False
    assert E.PARKLINE_PIT_DEFAULT is False


def test_source_artifact_is_not_modified(built):
    src = json.loads(P.SRC_PATH.read_text(encoding="utf-8"))
    assert len(src["venues"]) == 202
    assert len(src["team_seasons"]) == 1211
    assert src["stop_d"]["pass"] is True
    assert built["source"]["artifact"] == "data/milb_park_factors.json"


def test_display_values_are_unclamped(built):
    """The [0.90, 1.10] and [0.80, 1.25] bounds are model application clamps.
    Applying them to the display would compress real ballparks."""
    lo, hi = built["method"]["application_clamps"]["run_pf"]
    runs = [v["run"] for v in built["venues"] if v["run"] is not None]
    outside = [x for x in runs if x < lo or x > hi]
    assert len(outside) == 13, "the display must carry the measured value"
    assert max(runs) == 1.209                     # Hodgetown, not 1.100
    hrs = [v["hr"] for v in built["venues"] if v["hr"] is not None]
    assert max(hrs) == 1.428 and min(hrs) == 0.73


def test_pooled_non_venue_excluded_and_declared(built):
    ids = {v["id"] for v in built["venues"]}
    assert P.POOLED_NON_VENUE not in ids
    assert len(built["venues"]) == 201
    excl = built["meta"]["excluded"][0]
    assert excl["venue_id"] == P.POOLED_NON_VENUE
    assert excl["team_seasons"] == 133 and excl["home_games"] == 3975


def test_extremes_still_reproduce_the_registered_doc(built):
    ex = built["verification"]["gates_extremes"]
    assert ex and all(v["match"] for v in ex.values())
    assert ex["Hodgetown"]["run_pf"] == 1.209
    assert ex["Hodgetown"]["hr_pf"] == 1.428


def test_single_season_factors_are_withheld_on_evidence(built):
    """Single-season YoY sits under the 0.50 stability bar; the multi-season
    aggregate clears it. Only the window ships."""
    v = built["verification"]
    yoy = [x["spearman"] for x in v["yoy_single_season_spearman"]["run_pf"].values()]
    assert max(yoy) < 0.50
    assert v["split_half_window_spearman"]["run_pf"]["spearman"] >= 0.50
    assert v["split_half_window_spearman"]["hr_pf"]["spearman"] >= 0.50
    row = built["venues"][0]
    assert "run" in row and "wr" in row
    assert not any(k in row for k in ("season_run", "run_season", "s"))


def test_rows_are_labeled_and_light(built):
    n_seasons = len(built["meta"]["seasons"])
    for v in built["venues"]:
        assert v["lvl"] and v["name"] and v["team"]
        assert len(v["wr"]) == len(v["wh"]) == len(v["gs"]) == n_seasons
        if v["stale"]:
            assert v["run_pct"] is None and v["hr_pct"] is None
    assert P.OUT_PATH.stat().st_size < P.SRC_PATH.stat().st_size / 4


def test_half_up_rounding():
    assert P._r3(1.2085) == 1.209
    assert P._r3(0.8395) == 0.84
    assert P._r3(None) is None
