# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The served board number is not the model's number, and the file has to say by how much.

`xfv_grade` is the board: the displayed grade, the sort key and the basis of
overall_rank (storage.BOARD_GRADE_FIELD). `xfv_war_6yr` is the model leg the eval
scores. `rank_war` is the guarded blend. Three objects, and until this pass
data/xfv.json published two of them and no measurement of the distance between any
pair.

MEASURED on the live scored rows, and it reproduces what the plan recorded:

    flagship map (outcome_pooled)    0 inversions over 432,851 hitter and 446,254
                                     pitcher untied pairs. Exactly monotone.
    provisional cap                  inverts against the model's own predicted WAR
                                     on 25.4% of hitter and 49.2% of pitcher untied
                                     pairs, served to 51% and 58% of the board.

Half is what independence looks like. That is the design (a player with no
professional record is graded off a prior), not a defect, and it bounds what a
head-to-head over the whole board covers.

THE FIELD NAME IS THE TRAP. A first pass measured `xfv_grade_quantile`, the RETIRED
map kept only to price surplus, and reported near-total collapse: 3 distinct values
across 1,387 provisional pitchers with zero inversions. Every number in that reading
was real and none of it described the board. These tests pin the census onto
`xfv_grade`.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

import efv_export as ee

HERE = Path(__file__).parent


def _brute(pairs):
    n = len(pairs)
    u = d = 0
    for i in range(n):
        for j in range(i + 1, n):
            xi, yi = pairs[i]
            xj, yj = pairs[j]
            if xi == xj or yi == yj:
                continue
            u += 1
            if (xi < xj) != (yi < yj):
                d += 1
    return u, d


def test_the_inversion_counter_matches_brute_force_on_tie_heavy_data():
    """It is a Fenwick tree with tie bookkeeping. Do not trust it, check it.

    Ties are the whole difficulty: the provisional cap puts 46% of a side on one
    grade, so a counter that mishandles them is not slightly wrong, it is wrong on
    the majority of the pairs that matter.
    """
    rng = random.Random(7)
    for _ in range(200):
        n = rng.randrange(2, 40)
        k = rng.choice([2, 3, 5, 50])          # small k => tie-heavy
        pairs = [(rng.randrange(k), rng.randrange(k)) for _ in range(n)]
        u, d, _rho = ee._untied_inversions(pairs)
        assert (u, d) == _brute(pairs), pairs


def test_the_inversion_counter_survives_the_degenerate_cases():
    assert ee._untied_inversions([]) == (0, 0, None)
    assert ee._untied_inversions([(1.0, 2.0)]) == (0, 0, None)
    # a constant column has no untied pairs and no defined rho
    assert ee._untied_inversions([(1.0, 5.0), (1.0, 3.0), (1.0, 9.0)]) == (0, 0, None)
    assert ee._untied_inversions([(1.0, 5.0), (2.0, 5.0), (3.0, 5.0)]) == (0, 0, None)
    u, d, rho = ee._untied_inversions([(i, i) for i in range(50)])
    assert (u, d, rho) == (1225, 0, 1.0)
    u, d, rho = ee._untied_inversions([(i, -i) for i in range(50)])
    assert (u, d, rho) == (1225, 1225, -1.0)


def test_the_census_reads_the_served_grade_not_the_retired_map():
    src = Path(ee.__file__).read_text(encoding="utf-8")
    i = src.index("def _map_leg(")
    body = src[i:src.index("def _serve_vs_eval_census(")]
    assert 'r["xfv_grade"]' in body, (
        "the map leg no longer reads xfv_grade, the served board number")
    assert "xfv_grade_quantile" not in body.split('"""')[2], (
        "the map leg reads the RETIRED quantile map. That column is kept to price "
        "surplus; measuring it reports near-total collapse and says nothing about "
        "what the board displays")


def test_the_entry_carries_the_blend_when_the_row_has_one():
    """rank_war reaches the file, and reaches it the way the whitelist requires.

    _entry is a field whitelist under a byte-identity contract that
    test_board_basis_coherence pins: a row carrying neither grade_basis nor
    board_sort_key must not GROW a null for them. A first pass added rank_war and
    grade_basis unconditionally to the main dict, which duplicated an existing
    conditional emit and put a null on every bare row. It rides with the other
    two now, conditionally.
    """
    full = ee._entry({"player_key": "pk", "xfv_grade": 20.0, "rank_war": 3.21,
                      "grade_basis": "provisional_capped"}, "hit", "active")
    assert full["rank_war"] == 3.21, (
        "the guarded blend is not exported, so no reader can check the board "
        "against the quantity the model actually produced")
    assert full["grade_basis"] == "provisional_capped", (
        "without the routing basis the census cannot be split, and pooling the "
        "flagship map with the provisional cap hides the whole finding")
    bare = ee._entry({"player_key": "pk", "xfv_grade": 40.0}, "hit", "resolved")
    assert "rank_war" not in bare, (
        "a row with no blend grew a null rank_war; rows that carry neither field "
        "must stay byte-identical")


def test_the_census_shape_holds_on_a_synthetic_board():
    """Runs with no artifact on disk, so it pins the shape rather than the data."""
    by = {}
    for i in range(60):
        by[f"h{i}"] = {"side": "H", "kind": "active", "rank_war": i * 0.1,
                       "xfv_war_6yr": i * 0.1, "xfv_grade": 40.0 + i * 0.1,
                       "grade_basis": "outcome_pooled"}
    for i in range(40):
        by[f"p{i}"] = {"side": "P", "kind": "active", "rank_war": i * 0.1,
                       "xfv_war_6yr": i * 0.1, "xfv_grade": 35.0,
                       "grade_basis": "provisional_capped"}
    c = ee._serve_vs_eval_census(by)
    h = c["sides"]["H"]
    assert h["n_active"] == 60
    assert h["blend_vs_model_leg"]["inverted"] == 0
    assert h["map"]["outcome_pooled"]["inverted"] == 0
    assert h["map"]["outcome_pooled"]["distinct_displayed_grades"] == 60
    p = c["sides"]["P"]["map"]["provisional_capped"]
    # a fully collapsed column: no untied pairs, so inverted_share is None and the
    # flat-case fields are the only ones carrying information
    assert p["distinct_displayed_grades"] == 1
    assert p["modal_share"] == 1.0
    assert p["tied_pair_share"] == 1.0
    assert p["inverted_share"] is None
    assert "read_a_flat_column_correctly" in c


def test_the_served_artifact_carries_the_census_once_it_is_regenerated():
    """Skips until the next regen; data/xfv.json is under a golden-hash tripwire.

    The census and the two new fields are additive and land on the box's next
    rebuild_only. Rewriting the artifact on a dev machine to make this test go
    green would churn a tracked file whose golden reconciliation is a box
    operation, which is why the code was verified through run(persist=False).
    """
    p = HERE / "data" / "xfv.json"
    if not p.exists():
        pytest.skip("data/xfv.json not built on this machine")
    meta = json.loads(p.read_text(encoding="utf-8")).get("meta") or {}
    if "serve_vs_eval_census" not in meta:
        pytest.skip("artifact predates the census; it lands at the next regen")
    c = meta["serve_vs_eval_census"]
    assert set(c["sides"]) <= {"H", "P"} and c["sides"]
    for side, blk in c["sides"].items():
        for basis, leg in (blk.get("map") or {}).items():
            assert leg["grade_field"] == "xfv_grade", (
                f"{side}/{basis} was measured on {leg['grade_field']}, not the board")
            if leg["untied_pairs"]:
                assert 0.0 <= leg["inverted_share"] <= 1.0
