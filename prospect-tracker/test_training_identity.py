# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""DS-13 (docs/efv-v2/DRIVER_SYSTEM_V2.md, bug B8): no eFV training row rests on
an unadjudicated critical identity collision.

Five hitter bust rows sat on data/identity_collisions.json's critical list. Three
were not busts at all: michael_perez is the ARI/TBR catcher who debuted in 2018 (the
record carried no id, so the bust guard could not see his career), miguel_gomez is
the SFG infielder listed in 2018 after his 2017 debut (the record carried a 2019 WSN
pitcher's id), and enmanuel_rodriguez is a misspelled second key for the Twins
outfielder the board holds as emmanuel_rodriguez. Two were busts on the wrong human:
david_rodriguez carried a 2003-born KCR pitcher's id and a 2023 ATL draftee's
acquisitions row, adrian_hernandez merged the Mets outfielder with the Blue Jays
pitcher of the same name. efv_dataset.TRAINING_IDENTITY adjudicates each from
evidence that reads no outcome column, and the matrix builder applies it.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import efv_dataset as E

ROOT = Path(__file__).parent
COLLISIONS = ROOT / "data" / "identity_collisions.json"


def _matrix_keys():
    out = {}
    for side in ("hit", "pit"):
        p = E.matrix_path(side)
        if not p.exists():
            pytest.skip("matrices not built")
        for r in json.loads(p.read_text(encoding="utf-8")):
            out[r["player_key"]] = r
    return out


def test_rebind_replaces_the_id_birth_date_and_foreign_points():
    rec = {"player_key": "adrian_hernandez", "mlbam_id": 681753,
           "birth_date": "2000-01-22",
           "points": [{"snapshot_date": "2021-07-30"}, {"snapshot_date": "2022-01-22"}]}
    out = E.adjudicated_record(rec)
    assert out["mlbam_id"] == 677600 and out["birth_date"] == "2001-02-08"
    assert [p["snapshot_date"] for p in out["points"]] == ["2021-07-30"]
    assert rec["mlbam_id"] == 681753 and len(rec["points"]) == 2      # input untouched


def test_exclude_and_pass_through():
    assert E.adjudicated_record({"player_key": "enmanuel_rodriguez"}) is None
    rec = {"player_key": "someone_else", "mlbam_id": 1}
    assert E.adjudicated_record(rec) is rec


def test_every_adjudication_states_its_evidence():
    for k, adj in E.TRAINING_IDENTITY.items():
        assert adj["action"] in ("rebind", "exclude"), k
        assert len(adj.get("evidence") or "") > 40, k
        assert "—" not in adj["evidence"] and "–" not in adj["evidence"], k
        if adj["action"] == "rebind":
            assert isinstance(adj["mlbam_id"], int) and adj.get("birth_date"), k


def test_no_training_key_is_an_unadjudicated_critical_collision():
    """The DS-13 gate: the critical collision list, restricted to training keys
    that are not adjudicated, is empty."""
    if not COLLISIONS.exists():
        pytest.skip("identity_collisions.json not built")
    critical = set(json.loads(COLLISIONS.read_text(encoding="utf-8"))["critical_player_keys"])
    keys = _matrix_keys()
    assert sorted(k for k in critical if k in keys and k not in E.TRAINING_IDENTITY) == []


def test_the_matrix_carries_each_adjudication():
    keys = _matrix_keys()
    for k, adj in E.TRAINING_IDENTITY.items():
        if adj["action"] == "exclude":
            assert k not in keys, k
        elif k in keys:
            r = keys[k]
            assert r["mlbam_id"] == adj["mlbam_id"], k
            assert r["birth_date"] == adj["birth_date"], k
            if adj.get("points_through"):
                assert r["cutoff"] <= adj["points_through"], k
            if "acquisition" in adj:
                assert r["pick_overall"] == (adj["acquisition"] or {}).get("pick_overall"), k
    # the two debuted players rebound onto their own ids leave the bust pool
    for k in ("michael_perez", "miguel_gomez"):
        assert not (k in keys and keys[k].get("kind") == "bust"), k
