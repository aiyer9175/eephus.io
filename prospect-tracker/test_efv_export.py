# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""eFV export (efv_export.py) + dataset as-of leakage guard unit tests.

  1. Headline contract: the exported xfv_grade IS the pure-model (realized) grade
     -- identical to xfv_grade_realized, and DISTINCT from the quantile-blend map
     (xfv_grade_quantile). Driven through _entry with synthetic scored rows, then
     re-checked read-only on the committed artifact.
  2. Golden fingerprint tripwire on data/xfv.json (volatile-key-stripped content
     hash). An intentional eFV ship updates the constant below WITH a changelog note.
  3. _asof_point leakage guard: a future points[] entry (dated after the decision /
     debut date) must NOT change the as-of consensus FV -- future information ignored.

Read-only on committed files; no writes into data/.
"""
import json
from pathlib import Path

import pytest

import efv_export
from efv_export import _entry
from efv_dataset import _asof_point, _prior_features

DATA = Path(efv_export.__file__).parent / "data"


# --------------------------------------------------------------------------
# 1. Headline contract: xfv_grade == realized (pure model), quantile is distinct
# --------------------------------------------------------------------------
def test_entry_headline_is_pure_model_grade():
    # a scored row where the realized grade and the quantile map DIVERGE
    s = {
        "player_key": "test.player", "position": "SS",
        "xfv_grade": 48.3,                    # realized_implied_fv(E[6yr WAR]) -- the headline
        "xfv_grade_display": 55.0,            # rank->consensus-scale quantile map (must differ)
        "consensus_fv": 50.0,
        "xfv_minus_consensus": -1.7,
        "xfv_minus_consensus_display": 5.0,
        "xfv_war_6yr": 6.4, "p_bucket": {"star": 0.1}, "surplus_mm": 12.0,
        "band_p10_mm": -1.0, "band_p90_mm": 40.0, "p_bust": 0.3,
    }
    e = _entry(s, "hit", "active")
    # headline grade IS the pure realized grade (no consensus blend, no quantile remap)
    assert e["xfv_grade"] == 48.3
    assert e["xfv_grade_realized"] == 48.3          # alias -- byte-identical to headline
    assert e["xfv_grade"] == e["xfv_grade_realized"]
    # the quantile-blend value is preserved SEPARATELY and is distinct here
    assert e["xfv_grade_quantile"] == 55.0
    assert e["xfv_grade"] != e["xfv_grade_quantile"]
    # the minus-consensus deltas track their respective grades
    assert e["xfv_minus_consensus"] == -1.7                 # realized - consensus
    assert e["xfv_minus_consensus_quantile"] == 5.0         # quantile - consensus
    assert e["side"] == "H" and e["kind"] == "active"


def test_entry_side_tag_and_optional_fields():
    base = {"player_key": "p", "xfv_grade": 40.0, "xfv_grade_display": 40.0,
            "consensus_fv": 45.0, "xfv_minus_consensus": -5.0,
            "xfv_minus_consensus_display": -5.0}
    assert _entry(base, "pit", "resolved")["side"] == "P"
    # optional blocks appear only when present on the scored row
    assert "injury_factor" not in _entry(base, "hit", "active")
    assert _entry({**base, "injury_factor": 0.7}, "hit", "active")["injury_factor"] == 0.7
    assert _entry({**base, "xfv_provisional": True}, "hit", "active")["xfv_provisional"] is True


def test_committed_artifact_headline_alias_contract():
    """Read-only: in the shipped artifact, xfv_grade IS xfv_grade_realized for every
    player, and the quantile field is present + differs for the vast majority."""
    doc = json.loads((DATA / "xfv.json").read_text(encoding="utf-8"))
    bp = doc["by_player"]
    assert len(bp) > 1000
    both = 0
    distinct = 0
    for e in bp.values():
        assert e.get("xfv_grade") == e.get("xfv_grade_realized"), "headline != realized alias"
        if e.get("xfv_grade") is not None and e.get("xfv_grade_quantile") is not None:
            both += 1
            if abs(e["xfv_grade"] - e["xfv_grade_quantile"]) > 1e-9:
                distinct += 1
    assert both > 1000
    # the two scales genuinely differ in production (they are not the same number)
    assert distinct > 0.5 * both


# --------------------------------------------------------------------------
# 2. Golden fingerprint tripwire
# --------------------------------------------------------------------------
# GOLDEN eFV ARTIFACT FINGERPRINT (volatile-key-stripped content hash of data/xfv.json).
# This is a deliberate tripwire: it goes red when the flagship export changes. An
# INTENTIONAL eFV ship (model/feature/calibration change) updates this constant in the
# SAME commit, alongside a CHANGELOG / memory note describing what moved and why. An
# UNEXPECTED red here means the committed artifact drifted without a sanctioned ship.
_GOLDEN_XFV_SHA256 = "3a04b22a72526e8641abaaa100f4b230c6f3d7b78cdc5797c2eb3d692c8f0729"


def test_xfv_golden_fingerprint():
    from tools.pipeline_artifact_diff import fingerprint_file
    fp = fingerprint_file(DATA / "xfv.json", None)   # whole-doc hash, volatile keys stripped
    assert fp is not None and "sha256" in fp, "xfv.json missing/unreadable"
    assert fp["sha256"] == _GOLDEN_XFV_SHA256, (
        "data/xfv.json fingerprint changed. If this is an intentional eFV ship, update "
        "_GOLDEN_XFV_SHA256 in this test + record the change; otherwise the artifact "
        "drifted unexpectedly.")


# --------------------------------------------------------------------------
# 3. _asof_point leakage guard -- future points must be ignored
# --------------------------------------------------------------------------
def _rec(points):
    return {"player_key": "leak.test", "points": points}


def test_asof_point_ignores_future_points():
    cutoff = "2023-01-01"                    # e.g. a debut date / decision date
    past = [
        {"snapshot_date": "2022-02-01", "consensus_fv_raw": 45},
        {"snapshot_date": "2022-08-01", "consensus_fv_raw": 50},
    ]
    future = {"snapshot_date": "2023-08-01", "consensus_fv_raw": 65}   # AFTER the cutoff

    pt_clean = _asof_point(_rec(list(past)), cutoff)
    pt_with_future = _asof_point(_rec(past + [future]), cutoff)
    assert pt_clean is not None and pt_with_future is not None
    # same as-of point selected -> same as-of consensus FV, future entry ignored
    assert pt_clean["snapshot_date"] == "2022-08-01"
    assert pt_with_future["snapshot_date"] == "2022-08-01"
    assert pt_clean["consensus_fv_raw"] == pt_with_future["consensus_fv_raw"] == 50


def test_prior_features_asof_consensus_unaffected_by_future():
    """The downstream feature block reads the as-of consensus FV + a leakage-free
    fv_trend; adding a future snapshot changes neither."""
    cutoff = "2023-01-01"
    past = [
        {"snapshot_date": "2022-02-01", "consensus_fv_raw": 45},
        {"snapshot_date": "2022-08-01", "consensus_fv_raw": 50},
    ]
    future = {"snapshot_date": "2023-08-01", "consensus_fv_raw": 65}

    rec_clean, rec_future = _rec(list(past)), _rec(past + [future])
    pt_clean = _asof_point(rec_clean, cutoff)
    pt_future = _asof_point(rec_future, cutoff)
    f_clean = _prior_features(rec_clean, pt_clean, "hit")
    f_future = _prior_features(rec_future, pt_future, "hit")

    assert f_clean["consensus_fv_raw"] == f_future["consensus_fv_raw"] == 50.0
    # fv_trend is net consensus movement up to AND INCLUDING the decision point only
    assert f_clean["fv_trend"] == f_future["fv_trend"] == pytest.approx(5.0)  # 50 - 45, not 65


def test_asof_point_bust_uses_final_point():
    # cutoff=None (bust path) -> the final snapshot, regardless of ordering in the list
    rec = _rec([
        {"snapshot_date": "2021-05-01", "consensus_fv_raw": 40},
        {"snapshot_date": "2020-05-01", "consensus_fv_raw": 35},
        {"snapshot_date": "2022-05-01", "consensus_fv_raw": 45},
    ])
    assert _asof_point(rec, None)["snapshot_date"] == "2022-05-01"
    assert _asof_point(_rec([]), None) is None
