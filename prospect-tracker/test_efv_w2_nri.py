# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for the non-roster invitation column (efv_w2_nri.py, EFV4_NRI_ASOF).

1. As of: an entry counts only when its known date (the earliest dated invitation in
   the league feed, else 31 December of the season) is on or before the read; nothing
   known on or after the index's cap is loaded; no id, no read date or a read before
   FIRST_READ gives None.
2. Keys: the list-vintage column reads the outcome-blind id at the row's list date,
   never the record's stored id; reserved list vintages raise.
3. The arms: four timing-head columns (never the skill head), registered in the
   screening lab's wave 2 without touching wave 1, buildable through column_values.
4. Bans: nothing grouped by consensus-FV level, no served exporter imported, no
   em-dash, no column builder reads a label, WAR or debut; the fetch window and the
   look index's gate are enforced.
5. The artifact, when present: development role, the frozen label, every spent block
   labelled, and ledger rows only for the development frames.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import efv_screen_lab as LAB  # noqa: E402
import efv_vintage_frame as F  # noqa: E402
import efv_w2_nri as N  # noqa: E402

SRC = ROOT / "efv_w2_nri.py"
PID = 900101


def _index(rosters, tx, *, season_cap=2024, date_cap="2025-01-01"):
    return N.NriIndex.build(season_cap=season_cap, date_cap=date_cap, rosters=rosters,
                            tx=tx)


@pytest.fixture
def idx():
    """PID on the 2016 list (invited 2015-12-10) and the 2018 list (no dated
    invitation); PID + 1 on the 2017 list, invited 2017-02-20."""
    rosters = {2016: {PID: [147]}, 2017: {PID + 1: [121]}, 2018: {PID: [111]}}
    tx = {PID: [("2015-12-10", "SFA", "x signed free agent y to a minor league contract "
                 "and invited him to spring training."),
                ("2017-06-01", "ASG", "y assigned to z.")],
          PID + 1: [("2017-02-20", "ASG", "x invited non-roster y to spring training.")]}
    return _index(rosters, tx)


# ---------------------------------------------------------------------------
# 1. as of
# ---------------------------------------------------------------------------

def test_an_entry_counts_from_its_dated_invitation(idx):
    assert N.nri_values(PID, "2015-12-09", idx) == {"nri_pre": 0.0, "nri_count_pre": 0.0}
    assert N.nri_values(PID, "2015-12-10", idx) == {"nri_pre": 1.0, "nri_count_pre": 1.0}
    assert N.nri_values(PID + 1, "2017-02-19", idx)["nri_pre"] == 0.0
    assert N.nri_values(PID + 1, "2017-02-20", idx)["nri_pre"] == 1.0


def test_an_undated_entry_counts_only_after_its_season(idx):
    assert N.nri_values(PID, "2018-03-15", idx)["nri_count_pre"] == 1.0
    assert N.nri_values(PID, "2018-12-30", idx)["nri_count_pre"] == 1.0
    assert N.nri_values(PID, "2018-12-31", idx)["nri_count_pre"] == 2.0


def test_the_dating_range_is_the_season_around_the_spring():
    # an invitation two springs earlier does not date a later list entry
    rosters = {2017: {PID: [147]}}
    tx = {PID: [("2015-01-10", "ASG", "x invited non-roster y to spring training.")]}
    ix = _index(rosters, tx)
    assert ix.entries[PID] == [("2017-12-31", 2017, False)]
    assert ix.receipt["2017"] == {"entries": 1, "dated": 0, "past_cap": 0}


def test_the_cap_drops_entries_and_refuses_reads():
    rosters = {2024: {PID: [147]}, 2025: {PID: [147]}}
    tx = {PID: [("2024-12-15", "SFA", "invited him to spring training.")]}
    ix = _index(rosters, tx, season_cap=2025, date_cap="2025-01-01")
    # 2024 is undated (known 2024-12-31), 2025 dated 2024-12-15: both before the cap
    assert [e[1] for e in ix.entries[PID]] == [2025, 2024]
    ix2 = _index(rosters, tx, season_cap=2024, date_cap="2025-01-01")
    assert [e[1] for e in ix2.entries[PID]] == [2024]
    assert N.nri_values(PID, "2025-02-01", ix2) == {"nri_pre": None, "nri_count_pre": None}


def test_no_id_no_date_or_an_early_read_is_none(idx):
    empty = {"nri_pre": None, "nri_count_pre": None}
    assert N.nri_values(None, "2017-02-01", idx) == empty
    assert N.nri_values("abc", "2017-02-01", idx) == empty
    assert N.nri_values(PID, None, idx) == empty
    assert N.nri_values(PID, "2009-12-31", idx) == empty


def test_the_endpoint_list_is_undated_and_said_so():
    rc = N.cache_receipt()
    assert rc["date_parameter_honoured"] is False
    assert rc["dir"] == ".cache/efv4_nri"


# ---------------------------------------------------------------------------
# 2. keys and reserved vintages
# ---------------------------------------------------------------------------

def test_lv_values_read_the_outcome_blind_id_at_the_list_date(idx):
    rows = [{"player_key": "x", "mlbam_id": PID, "record_mlbam_id": 1, "vintage": 2016,
             "asof_date": "2016-02-15"},
            {"player_key": "y", "mlbam_id": None, "record_mlbam_id": PID, "vintage": 2016,
             "asof_date": "2016-02-15"},
            {"player_key": "z", "mlbam_id": PID + 1, "vintage": 2016,
             "asof_date": "2016-02-15"}]
    out = N.lv_values("hit", {"hit": {2016: (rows, [{}, {}, {}])}}, idx)
    assert out[(2016, "x")] == {"nri_pre": 1.0, "nri_count_pre": 1.0}
    assert out[(2016, "y")]["nri_pre"] is None
    assert out[(2016, "z")]["nri_pre"] == 0.0


def test_reserved_list_vintages_raise(idx):
    rows = [{"player_key": "x", "mlbam_id": PID, "vintage": 2020,
             "asof_date": "2020-02-15"}]
    with pytest.raises(F.ReservedFrameError):
        N.lv_values("hit", {"hit": {2020: (rows, [{}])}}, idx)


def test_the_look_index_opens_only_on_the_committed_gate():
    with pytest.raises(F.ReservedFrameError):
        N.look_index(None)
    with pytest.raises(F.ReservedFrameError):
        N.look_index("0" * 40)
    assert N.look_cap() == f"{F.R_VM_FIRST_DEBUT_YEAR}-05-01"
    assert N.DEV_DATE_CAP == f"{F.R_VM_FIRST_DEBUT_YEAR}-01-01"
    assert N.DEV_SEASON_CAP < F.R_VM_FIRST_DEBUT_YEAR


# ---------------------------------------------------------------------------
# 3. the arms and their registration
# ---------------------------------------------------------------------------

def test_the_arms_are_four_timing_columns_registered_in_wave_two():
    names = [a["name"] for a in N.ARMS]
    assert names == ["w2n_nri_pre_hit", "w2n_nri_pre_pit", "w2n_nri_count_pre_hit",
                     "w2n_nri_count_pre_pit"]
    for a in N.ARMS:
        assert a["head"] == "timing" and a["side"] in F.SIDES and not a["retest"]
        assert a["column"]["source"] == "module" and a["column"]["arg"] == a["stat"]
    assert "efv_w2_nri" in LAB.WAVE2_ARM_MODULES
    assert set(names) <= {a["name"] for a in LAB.wave2_candidates()}
    assert [c["name"] for c in LAB.CANDIDATES][:2] == ["txt_skill_hit", "txt_skill_pit"]
    assert LAB.registration_echo()["family_size"] == 7


def test_the_lab_builds_an_arm_through_its_own_column_values(idx, monkeypatch):
    monkeypatch.setattr(N, "default_index", lambda: idx)
    N._LV_MEMO.clear()
    rows = [{"player_key": "x", "mlbam_id": PID, "vintage": 2017,
             "asof_date": "2017-02-15"}]
    frames = {"pit": {2017: (rows, [{}])}}
    arm = next(a for a in N.ARMS if a["name"] == "w2n_nri_count_pre_pit")
    vals = LAB.column_values(arm, frames)
    assert vals == {(2017, "x"): 1.0}
    N._LV_MEMO.clear()
    with pytest.raises(ValueError):
        N.screen_column("nri_later", "pit", frames)


def test_registered_columns_leave_the_v3_menu_as_it_was():
    import efv_v3 as V3
    before = dict(V3.W2_COLUMNS)
    with N.registered_columns():
        cfg = V3.base_config()
        cfg["add"]["hit"]["timing"].append("w2n_nri_pre_hit")
        V3.validate_config(cfg)
        assert V3.W2_COLUMNS["w2n_nri_pre_hit"]["key"].startswith("scr_")
    assert V3.W2_COLUMNS == before


# ---------------------------------------------------------------------------
# 4. bans
# ---------------------------------------------------------------------------

_BANNED_TOKENS = ("groupby", "tier", "bucket", "cell", "stratum", "strata", "by_fv",
                  "fv_band", "fv_bin", "by_consensus", "per_fv", "per_consensus")
_SERVED_EXPORTERS = {"efv_export", "efv_v2_serve", "efv_score", "build_site", "proj_export",
                     "export_trade_values", "efv_alerts", "run_monthly"}


def test_no_consensus_level_grouping_no_exporter_no_emdash():
    src = SRC.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fv_group = re.compile(r"(by|per|group)_?(fv|consensus|grade)")
    for node in ast.walk(tree):
        name = (node.id if isinstance(node, ast.Name) else node.attr
                if isinstance(node, ast.Attribute) else node.name
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)) else node.arg
                if isinstance(node, ast.arg) else None)
        if name:
            low = name.lower()
            assert not any(t in low for t in _BANNED_TOKENS), name
            assert not fv_group.search(low), name
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and len(node.value) < 40:
            assert not any(t in node.value.lower() for t in _BANNED_TOKENS), node.value
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                    else [node.module or ""])
            assert not {m.split(".")[0] for m in mods} & _SERVED_EXPORTERS, mods
    assert "\u2014" not in src and "\u2013" not in src
    for fn in ("nri_values", "lv_values", "screen_column", "load_rosters"):
        body = ast.get_source_segment(src, next(
            n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == fn))
        for banned in ("efv_labels", "w3", "war", "debut", "target", "reached"):
            assert banned not in body.lower(), (fn, banned)


def test_the_fetch_window_is_closed_from_six_to_eleven_utc():
    def at(h):
        return datetime(2026, 10, 9, h, 30, tzinfo=timezone.utc)
    assert N.fetch_window_open(at(5)) and N.fetch_window_open(at(11))
    assert not N.fetch_window_open(at(6)) and not N.fetch_window_open(at(10))
    assert N.CACHE_DIR.name == "efv4_nri"


# ---------------------------------------------------------------------------
# 5. the artifact
# ---------------------------------------------------------------------------

def _artifact():
    if not N.OUT_PATH.exists():
        pytest.skip("read not run on this tree")
    return json.loads(N.OUT_PATH.read_text(encoding="utf-8"))


def test_the_artifact_is_a_development_read_on_the_frozen_label():
    d = _artifact()
    assert d["role"] == "development" and d["adjudicates"] is False
    assert d["selects"] is False and d["exploratory"] is False
    assert d["label"]["provider"] == "fwar"
    assert d["label"]["id"].startswith("fwar@2026-10-02")
    assert d["lv_dev"]["frame"]["folds"] == [2017, 2018, 2019]
    assert all(int(y) < F.R_VM_FIRST_DEBUT_YEAR for y in d["vm_dev"]["frame"]["fold_years"])
    for side, by_stat in d["lv_dev"]["coverage"].items():
        for cov in by_stat.values():
            assert not ({"2020", "2021"} & set(cov)), side
    for a in N.ARMS:
        for fid in ("lv_dev", "vm_dev"):
            blk = d[fid]["arms"][a["name"]]["frame"]
            for comp in ("candidate_vs_efv_v2_base", "candidate_vs_prospx_consensus"):
                leg = blk["deltas"][comp]["spearman"]
                assert leg["delta"] is not None and len(leg["ci95"]) == 2


def test_every_spent_block_is_labelled_and_lands_no_ledger_row():
    d = _artifact()
    sp = d.get("spent")
    if not sp:
        pytest.skip("no spent read in the artifact")
    assert sp["note"] == N.SPENT_NOTE
    assert set(sp["frames"]) == {"lv_res", "vm_pros"}
    for fid, blk in sp["frames"].items():
        assert blk["frame"]["note"] == N.SPENT_NOTE
        for a in blk["arms"].values():
            assert a["frame"]["note"] == N.SPENT_NOTE
    docs = N.ledger_docs(d)
    assert len(docs) == 2 * len(N.ARMS)
    for doc in docs:
        assert doc["role"] == "development"
        assert doc["model_id"].startswith(N.MODEL_PREFIX)
        assert set(doc["frames"]) <= {"lv_dev", "vm_dev"}
