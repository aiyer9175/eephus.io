# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""AAA Stuff+ contracts - the in-house pitch-quality model's artifact
shapes (sidecar + eval) and the feature conventions the model card
promises (physics only, arm-side signing, no result leakage)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import stuff_plus_aaa as spa

ROOT = Path(__file__).parent


def test_features_are_physics_only():
    """The model card's core claim: no pitch-type identity, no results.
    Anything that smells like an outcome or a label in the feature list
    is leakage."""
    banned = ("run", "exp", "result", "event", "woba", "babip", "pitch_type")
    for f in spa.FEATURES:
        assert not any(b in f.lower() for b in banned), f
    assert "velo" in spa.FEATURES and "spin" in spa.FEATURES


def test_featurize_signs_arm_side_and_keeps_label_out():
    """LHP horizontal components mirror so arm-side run reads the same
    sign both ways; the label rides separately from the feature vector."""
    base = {"release_speed": "95.0", "release_spin_rate": "2400",
            "release_extension": "6.5", "pfx_x": "-1.2", "pfx_z": "1.4",
            "release_pos_x": "-2.0", "release_pos_z": "5.8",
            "arm_angle": "35", "delta_run_exp": "-0.05"}
    rhp = spa._featurize({**base, "p_throws": "R"}, primary_velo=95.0)
    lhp = spa._featurize({**base, "p_throws": "L",
                          "pfx_x": "1.2", "release_pos_x": "2.0"},
                         primary_velo=95.0)
    assert rhp is not None and lhp is not None
    x_r, lab_r = rhp
    x_l, lab_l = lhp
    assert len(x_r) == len(spa.FEATURES)
    assert lab_r == lab_l == -0.05
    # mirrored LHP kinematics produce identical arm-side features except
    # the handedness flag itself
    assert x_r[:-1] == x_l[:-1]
    assert (x_r[-1], x_l[-1]) == (1.0, 0.0)
    # unparseable label or velo drops the pitch entirely
    assert spa._featurize({**base, "delta_run_exp": ""}, 95.0) is None
    assert spa._featurize({**base, "release_speed": None}, 95.0) is None


def test_sidecar_shape():
    if not spa.OUT_PATH.exists():
        pytest.skip("stuff_plus_aaa.json not generated on this machine")
    d = json.loads(spa.OUT_PATH.read_text(encoding="utf-8"))
    players = d["players"]
    assert d["n_scored"] == len(players) > 200
    for mid, row in players.items():
        assert mid.isdigit(), mid
        assert set(row) == {"stuff_plus", "n_pitches", "season"}, mid
        assert 40 <= row["stuff_plus"] <= 160, (mid, row)
        assert row["n_pitches"] >= 50 and row["season"] in spa.SEASONS
    # the scale promise: shrunk scores center near 100 on the pool scale
    vals = [r["stuff_plus"] for r in players.values()]
    mean = sum(vals) / len(vals)
    assert 90 <= mean <= 110, mean


def test_eval_artifact_shape():
    if not spa.EVAL_PATH.exists():
        pytest.skip("stuff_plus_aaa_eval.json not generated on this machine")
    d = json.loads(spa.EVAL_PATH.read_text(encoding="utf-8"))
    so = d["season_out_validation"]
    assert so["n_valid_pitchers"] >= 20
    assert so["pitch_level_r"] is not None
    fg = d["forward_gate"]
    assert {"n_era", "r_vs_mlb_era_inv", "n_k", "r_vs_mlb_kpct"} <= set(fg)
    assert "delta_run_exp" in d["conventions"]["model"]
