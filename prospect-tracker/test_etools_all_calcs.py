# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""ETOOLS_ALL_CALCS (owner decision EW3-30; docs/tools-2026-10/ETOOLS_ALL_CALCS.md).

Pins:
  * the shown-grade map the server builds is the one prospx toolGradesShown builds: each
    passing eTool in place of its consensus grade, the one Power grade on game power's
    eTool, every other tool consensus;
  * the eTool composite is the unchanged formula on that map; the served payload carries
    the eTool composites, the consensus grades in `grades` and the consensus composites
    under `composite_cons`;
  * flag off (ETOOLS_COMPOSITE_ON False) reproduces the consensus payload byte for byte
    and adds no field;
  * one player reads the same tool on the card, the flags and the composite input;
  * the consensus FVStuff+ the trade-value policy reads is the number it read before
    (R-TV kept it), and the cohort pass reproduces it under composite_cons;
  * the per-tool flags print the shown grade; the Alchemy Lab starter shape reads it;
  * amateurs: no eTool, nothing moves;
  * the registered re-read runner's statistic on a fixture, and the registry and glossary
    rows exist.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import etool_composite as ETC  # noqa: E402
import storage as S  # noqa: E402
import stat_flags as SF  # noqa: E402

HIT_CONS = {"hit": 45.0, "game_pwr": 50.0, "raw_pwr": 60.0, "pwr": 55.0, "speed": 55.0, "field": 50.0,
            "throw": 55.0, "pitch_sel": 45.0, "bat_ctrl": 40.0}
HIT_REC = {"mlbam": 1, "side": "hit",
           "tools": {"hit": {"etool": 61.66, "shown": 62, "consensus": 45.0},
                     "game_pwr": {"etool": 52.74, "shown": 53, "consensus": 48.5},
                     "pitch_sel": {"etool": 56.37, "shown": 56, "consensus": 45.0}}}
PIT_CONS = {"fb": 55.0, "sl": 50.0, "ch": 45.0, "cmd": 45.0}
PIT_REC = {"mlbam": 2, "side": "pit", "tools": {"fb": {"etool": 63.4, "shown": 63}, "cmd": {"etool": 41.2, "shown": 41}}}
PAYLOAD = {"players": {"hitter_a": HIT_REC, "pitcher_b": PIT_REC}}


@pytest.fixture(autouse=True)
def _flag_on(monkeypatch):
    monkeypatch.setattr(ETC, "ETOOLS_COMPOSITE_ON", True)
    yield


def test_shown_map_mirrors_the_site_resolver():
    shown, used = ETC.shown_grades(HIT_CONS, HIT_REC)
    assert used == ["game_pwr", "hit", "pitch_sel"]
    assert shown["hit"] == 61.66 and shown["pitch_sel"] == 56.37
    assert shown["game_pwr"] == 52.74 and shown["pwr"] == 52.74       # the Power grade reads ePOW
    for k in ("raw_pwr", "speed", "field", "throw", "bat_ctrl"):      # no eTool: consensus
        assert shown[k] == HIT_CONS[k]
    assert HIT_CONS["hit"] == 45.0                                   # the input map is not mutated
    printed, _ = ETC.shown_grades(HIT_CONS, HIT_REC, value="shown")
    assert printed["hit"] == 62 and printed["pwr"] == 53
    same, none = ETC.shown_grades(HIT_CONS, None)
    assert same is HIT_CONS and none == []


def test_record_matching_by_key_then_mlbam_and_flag_off(monkeypatch):
    doc = dict(PAYLOAD)
    assert ETC.etool_record("hitter_a", None, payload=doc) is HIT_REC
    assert ETC.etool_record("renamed_key", 2, payload=doc) is PIT_REC
    assert ETC.etool_record("nobody", 999, payload=doc) is None
    monkeypatch.setattr(ETC, "ETOOLS_COMPOSITE_ON", False)
    assert ETC.etool_record("hitter_a", 1, payload=doc) is None


def _served(cons_grades, rec, is_p, extras=None, bucket=None):
    """The storage export's path (the _shown_tool_payload closure), on fixtures."""
    cons = S._compute_tool_composites(cons_grades, is_p, player_extras=extras, position_bucket=bucket)
    if not ETC.ETOOLS_COMPOSITE_ON:
        return cons
    shown, used = ETC.shown_grades(cons_grades, rec if ETC.ETOOLS_COMPOSITE_ON else None)
    et = S._compute_tool_composites(shown, is_p, player_extras=extras, position_bucket=bucket) if used else None
    return ETC.with_consensus_reference(et, cons, used)


def test_etool_composite_is_the_same_formula_on_the_shown_grades():
    extras = {"frame": 1, "athl": 0}
    out = _served(HIT_CONS, HIT_REC, False, extras, "IF")
    shown, _ = ETC.shown_grades(HIT_CONS, HIT_REC)
    want = S._compute_tool_composites(shown, False, player_extras=extras, position_bucket="IF")
    cons = S._compute_tool_composites(HIT_CONS, False, player_extras=extras, position_bucket="IF")
    for k in ETC.COMPOSITE_KEYS:
        assert out[k] == want[k]
        assert out["composite_cons"][k] == cons[k]
    assert out["grades"] == cons["grades"]                 # the per-tool resolver reads consensus here
    assert out["composite_basis"] == "etools" and out["etool_keys"] == ["game_pwr", "hit", "pitch_sel"]
    assert out["composite_overall"] != cons["composite_overall"]
    assert out["composite_def"] == cons["composite_def"]   # field, arm, run: no eTool
    pit = _served(PIT_CONS, PIT_REC, True)
    assert pit["composite_cmd"] == 41.0 and pit["composite_cons"]["composite_cmd"] == 45.0


def test_flag_off_reproduces_the_consensus_payload(monkeypatch):
    monkeypatch.setattr(ETC, "ETOOLS_COMPOSITE_ON", False)
    for grades, rec, is_p in ((HIT_CONS, HIT_REC, False), (PIT_CONS, PIT_REC, True)):
        out = _served(grades, rec, is_p)
        cons = S._compute_tool_composites(grades, is_p)
        assert json.dumps(out, sort_keys=True) == json.dumps(cons, sort_keys=True)
        assert "composite_cons" not in out and "composite_basis" not in out


def test_no_etool_on_file_keeps_consensus_with_its_reference():
    out = _served(HIT_CONS, None, False)
    cons = S._compute_tool_composites(HIT_CONS, False)
    for k in ETC.COMPOSITE_KEYS:
        assert out[k] == cons[k] == out["composite_cons"][k]
    assert out["composite_basis"] == "consensus" and "etool_keys" not in out


def test_one_player_reads_the_same_tool_everywhere():
    """The card prints the eTool's whole grade; the flag prints the same grade; the
    composite reads the same eTool (at 2 dp, cleaned to the half grade)."""
    out = _served(HIT_CONS, HIT_REC, False)
    flag_grades, _ = ETC.shown_grades(out["grades"], HIT_REC, value="shown")
    flags = SF.compute_tool_flags(out, False, grades=flag_grades)
    hit_flag = [f for f in flags if f["stat"] == "Hit"]
    assert hit_flag and hit_flag[0]["value"] == HIT_REC["tools"]["hit"]["shown"] == 62
    assert hit_flag[0]["note"].startswith("62 hit")
    shown, _ = ETC.shown_grades(HIT_CONS, HIT_REC)
    assert S._round_half(shown["hit"]) == 61.5
    # without the shown grades the 45 consensus hit grade raises no flag
    assert not [f for f in SF.compute_tool_flags(out, False) if f["stat"] == "Hit"]


def test_cohort_pass_keeps_the_consensus_index_exactly():
    pays = []
    for i, fb in enumerate((50.0, 55.0, 60.0, 65.0, 45.0)):
        cons_grades = {"fb": fb, "sl": 50.0, "cmd": 50.0}
        rec = {"side": "pit", "tools": {"fb": {"etool": fb + 5.0, "shown": int(fb + 5)}}} if i % 2 == 0 else None
        pays.append({"tools": _served(cons_grades, rec, True)})
    old = [{"tools": S._compute_tool_composites(p["tools"]["grades"], True)} for p in pays]
    S._attach_tool_plus_indices(pays)
    S._attach_tool_plus_indices(old)
    for p, o in zip(pays, old):
        assert p["tools"]["composite_cons"]["composite_stuff_plus"] == o["tools"]["composite_stuff_plus"]
        assert p["tools"]["composite_cons"]["composite_cmd_plus"] == o["tools"]["composite_cmd_plus"]


def test_trade_value_policy_reads_the_consensus_index():
    import bayes_trade_value as BT
    assert BT.POLICY_STUFF_PLUS_BASIS == "consensus"
    tools = {"composite_stuff_plus": 120, "composite_cons": {"composite_stuff_plus": 108}}
    assert BT._policy_stuff_plus(tools) == 108
    assert BT._policy_stuff_plus({"composite_stuff_plus": 120}) == 120     # flag off / older export


def test_alchemy_lab_shape_reads_the_shown_grades():
    import pal_conversion as pc
    import pal_export as PE
    p = {"position": "SP", "tools": {"fb": 50.0, "sl": 50.0, "cmd": 45.0},
         "tools_shown": {"fb": 60, "sl": 50.0, "cmd": 58}}
    assert PE._shape_tools(p) is p["tools_shown"]
    a = pc.prospect_role_fit(PE._shape_tools(p), "SP")["starter_shape"]
    b = pc.prospect_role_fit(p["tools"], "SP")["starter_shape"]
    assert a != b
    assert PE._shape_tools({"tools": {"fb": 50.0}}) == {"fb": 50.0}


def test_amateurs_have_no_etool_so_nothing_moves():
    """Draft, IFA and overseas players have no minor-league line, so no eTool: their
    composites (draft and overseas Tool+, the mock draft's grades, the IFA at-signing
    line) are built by their own exporters from the consensus grades, which read no
    eTool, so no number of theirs moves."""
    for mod in ("draft_export.py", "overseas_export.py", "mock_draft.py", "ifa_export.py"):
        src = (ROOT / mod).read_text(encoding="utf-8")
        assert "etool" not in src.lower(), mod


def test_reread_statistic_on_a_fixture():
    import numpy as np
    import etools as E
    import etools_all_calcs_reread as R
    fr = E.fixture_frames()["hit"]
    adm = list(E.TOOLS["hit"]["cands"][:2])
    Z = np.column_stack([fr.cands[c] for c in adm])
    y = fr.y["mlb"]
    pe, pc_, folds = R.tip_fold_preds(fr.gc, Z, fr.y, y, fr.year, fr.pid, E.etool_fit, E.etool_apply,
                                      E.fit_tip, E.fold_train_mask)
    m = np.isfinite(pe) & np.isfinite(pc_) & np.isfinite(y)
    assert m.sum() > 100 and not set(np.unique(fr.year[m])) & {2020, 2021}
    rec = R.tip_verdict(np.abs(pe[m] - y[m]), np.abs(pc_[m] - y[m]), fr.pid[m], Bn=200)
    assert rec["verdict"] in ("NON-INFERIOR", "NOT NON-INFERIOR")
    assert rec["margin"] == pytest.approx(0.05 * rec["mae_consensus"], abs=1e-5)
    # a table read at its own knots is flat beyond the last one
    tip = {"grade": [40.0, 50.0, 60.0], "stat": [1.0, 2.0, 3.0]}
    assert list(R.tip_read_at(tip, np.array([30.0, 55.0, 70.0]))) == [1.0, 2.5, 3.0]


def test_registry_and_glossary_rows():
    reg = json.loads((ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))
    row = [m for m in reg["models"] if m["model_id"] == "etool_composite"]
    assert row and row[0]["verdict"] == "unvalidated"
    for mid in ("tool_implied_production", "mlb_projections_prospects_statline", "fv_stuff_plus",
                "composite_cmd_plus", "tbs_prospect", "farm_grades"):
        r = [m for m in reg["models"] if m["model_id"] == mid][0]
        assert "ETOOLS_ALL_CALCS 2026-10-15:" in r["notes"], mid
    glo = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    ids = {e["id"]: e for e in glo["entries"]}
    assert "etool_composite" in ids
    for gid in ("tool", "o_tool", "d_tool", "stuff_grade_plus"):
        assert "etool_composite" in ids[gid]["seeAlso"], gid


def test_storage_wires_the_shown_grades():
    src = (ROOT / "storage.py").read_text(encoding="utf-8")
    assert "tools_payload = _shown_tool_payload(is_pitcher)" in src
    assert "hitter_payload = _shown_tool_payload(False)" in src
    assert "pitcher_payload = _shown_tool_payload(True)" in src
    assert "compute_tool_flags(tools_payload, is_pitcher, grades=_flag_grades)" in src
    assert "tools, _ = _ETC.shown_grades(dict(tools), _etc_rec(p.player_key))" in src   # board tiebreak
    assert "_farm_grades, _ = _ETC.shown_grades(" in src                                 # farm Tool Quality


def test_registered_doc_is_committed_registered():
    doc = (ROOT / "docs" / "tools-2026-10" / "ETOOLS_ALL_CALCS.md").read_text(encoding="utf-8")
    assert "\nRegistration status: REGISTERED\n" in doc.replace("\r\n", "\n")
    assert "### 4.1 R-TIP" in doc and "### 4.3 R-TV" in doc
