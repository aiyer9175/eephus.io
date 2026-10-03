# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""tools/efv_fwar_epoch_arms.py on fixtures: the clause (i) arm set of the fWAR label epoch.

No matrix build, no database, no cache read: efv_dataset.build_matrix is replaced by a
fake that records the flag state it was called under and returns rows carrying it, so
every assertion about "which factor this arm reverts" is read off what the build SAW.
Nothing here writes under the repository; the output directory is a tmp_path.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
from pathlib import Path

import pytest

import efv_dataset as ed
import efv_model as em

ROOT = Path(__file__).resolve().parent


def _driver():
    """Loaded by path. Importing it must do nothing and leave every flag at its default."""
    spec = importlib.util.spec_from_file_location(
        "_efv_fwar_epoch_arms", ROOT / "tools" / "efv_fwar_epoch_arms.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert ed.NEVER_RESOLUTION_ARM_R is False and ed.SERVICE_ALIGNED_WINDOW is False
    assert em.NEUTRAL_MILB_IMPUTE is False and ed.LABEL_SEASONS_KEY == "seasons"
    return mod


def _snapshot():
    return {"efv_dataset.LABEL_SEASONS_KEY": ed.LABEL_SEASONS_KEY,
            "efv_dataset.RESOLVED_THROUGH": ed.RESOLVED_THROUGH,
            "efv_dataset.NEVER_RESOLUTION_ARM_R": ed.NEVER_RESOLUTION_ARM_R,
            "efv_dataset.SERVICE_ALIGNED_WINDOW": ed.SERVICE_ALIGNED_WINDOW,
            "efv_model.NEUTRAL_MILB_IMPUTE": em.NEUTRAL_MILB_IMPUTE}


@pytest.fixture
def fake_build(monkeypatch):
    """build_matrix replaced by a recorder. Rows carry the flag state and one NEGATIVE
    resolved label, so the no-flooring assertion has something to bite on."""
    seen = []

    def _fake(side):
        snap = _snapshot()
        seen.append((side, snap))
        rows = [
            {"player_key": f"{side}_neg", "kind": "debuted", "target_resolved": -1.4,
             "target_censored": -1.4, "censored": False, "weight": 1.0, "saw": snap},
            {"player_key": f"{side}_star", "kind": "debuted", "target_resolved": 12.0,
             "target_censored": 12.0, "censored": False, "weight": 1.0, "saw": snap},
            {"player_key": f"{side}_cens", "kind": "debuted", "target_resolved": 1.0,
             "target_censored": 2.0, "censored": True, "weight": 0.5, "saw": snap},
            {"player_key": f"{side}_bust", "kind": "bust", "target_resolved": 0.0,
             "target_censored": 0.0, "censored": False, "weight": 1.0,
             "bust_recent": False, "saw": snap},
            {"player_key": f"{side}_bust_c", "kind": "bust", "target_resolved": 0.0,
             "target_censored": 0.0, "censored": False, "weight": 0.5,
             "bust_recent": True, "saw": snap},
        ]
        acct = {"debuted_window_shifted": 3 if snap["efv_dataset.SERVICE_ALIGNED_WINDOW"] else 0,
                "label_seasons_key_fallback_rows": 0}
        if snap["efv_dataset.NEVER_RESOLUTION_ARM_R"]:
            acct["arm_r"] = {"resolved_to_censored": 2, "censored_to_resolved": 1}
        return rows, acct

    monkeypatch.setattr(ed, "build_matrix", _fake)
    return seen


@pytest.fixture
def step_f(monkeypatch):
    """The state EPOCH_RUN's RT commit leaves at step F: the clock reads 2026."""
    monkeypatch.setattr(ed, "RESOLVED_THROUGH", 2026)


@pytest.fixture
def labs(monkeypatch, tmp_path):
    """OUT_DIR under a tmp labs root, so the guard's geometry is exercised without a
    single byte under the repository."""
    d = _driver()
    root = tmp_path / "data" / "_labs"
    monkeypatch.setattr(d, "LABS_ROOT", root)
    monkeypatch.setattr(d, "OUT_DIR", root / "fwar_epoch_arms")
    return d


# ---------------------------------------------------------------------------
# the arm set
# ---------------------------------------------------------------------------

def test_the_arm_set_is_e0_estar_and_one_leave_one_out_arm_per_factor():
    d = _driver()
    assert d.ARMS == ("E0", "Estar", "F1", "F2", "F3", "F4", "F5")
    assert tuple(d.FACTORS) == ("F1", "F2", "F3", "F4", "F5")
    assert "F6" not in d.FACTORS          # F-DEF is a bundle arm inside step M, not a matrix
    assert d.OWNER_DECISION_FACTORS == ("F1", "F2") and d.CANDIDATE_FACTORS == ("F3", "F4", "F5")
    assert d.SEED == 20260807
    assert d.E0_RESOLVED_THROUGH == 2025 and d.ESTAR_RESOLVED_THROUGH == 2026
    assert d.INCUMBENT_LABEL_KEY == "seasons_ewar_v2" and d.CANDIDATE_LABEL_KEY == "seasons"


def test_seven_arms_per_side_each_differing_from_estar_in_exactly_one_named_factor(step_f):
    d = _driver()
    estar = d.arm_factor_values("Estar")
    assert estar == {"F1": "seasons", "F2": 2026, "F3": True, "F4": True, "F5": True}
    e0 = d.arm_factor_values("E0")
    assert e0 == {"F1": "seasons_ewar_v2", "F2": 2025, "F3": False, "F4": False, "F5": False}
    assert sum(1 for f in d.FACTORS if estar[f] != e0[f]) == 5
    for fid in d.FACTORS:
        v = d.arm_factor_values(fid)
        diff = [f for f in d.FACTORS if v[f] != estar[f]]
        assert diff == [fid], (fid, diff)
        assert v[fid] == e0[fid]
        assert d.factor_reverted(fid) == fid
    assert d.factor_reverted("E0") is None and d.factor_reverted("Estar") is None
    assert len(d.ARMS) == 7


def test_estar_reads_resolved_through_off_the_module_and_only_f2_overrides_it(step_f):
    d = _driver()
    assert d.arm_factor_values("Estar")["F2"] == 2026
    assert d.arm_factor_values("F2")["F2"] == 2025
    assert d.arm_factor_values("F3")["F2"] == 2026
    assert d.arm_factor_values("E0")["F2"] == 2025


def test_estar_refuses_a_clock_the_rt_commit_has_not_moved(fake_build, monkeypatch):
    """Before EPOCH_RUN's RT commit the constant reads 2025; Estar must not be built on
    it, or F2 would differ from Estar in nothing."""
    d = _driver()
    monkeypatch.setattr(ed, "RESOLVED_THROUGH", 2025)
    with pytest.raises(d.ArmRefused, match="RESOLVED_THROUGH reads 2025"):
        d.build_arm("hit", "Estar")
    # E0 and F2 pin 2025 themselves and build on either clock
    rows, acct, values = d.build_arm("hit", "E0")
    assert values["F2"] == 2025 and rows[0]["saw"]["efv_dataset.RESOLVED_THROUGH"] == 2025


def test_build_arm_sets_every_flag_for_the_build_and_restores_all_of_them(fake_build, step_f):
    d = _driver()
    before = _snapshot()
    for arm in d.ARMS:
        rows, acct, values = d.build_arm("pit", arm)
        saw = rows[0]["saw"]
        assert saw == d.flags_by_attribute(values), arm
        assert _snapshot() == before, f"{arm} leaked a flag"
    # Estar's build saw everything on, on the candidate label, at 2026
    estar_saw = [s for side, s in fake_build if s["efv_dataset.NEVER_RESOLUTION_ARM_R"]
                 and s["efv_dataset.SERVICE_ALIGNED_WINDOW"] and s["efv_model.NEUTRAL_MILB_IMPUTE"]
                 and s["efv_dataset.LABEL_SEASONS_KEY"] == "seasons"
                 and s["efv_dataset.RESOLVED_THROUGH"] == 2026]
    assert len(estar_saw) == 1


def test_flags_are_restored_even_when_the_build_fails(monkeypatch, step_f):
    d = _driver()
    before = _snapshot()

    def _boom(side):
        raise RuntimeError("no build in tests")
    monkeypatch.setattr(ed, "build_matrix", _boom)
    with pytest.raises(RuntimeError):
        d.build_arm("hit", "Estar")
    assert _snapshot() == before


# ---------------------------------------------------------------------------
# a FAILED ARM
# ---------------------------------------------------------------------------

def test_an_omitted_factor_is_out_of_estar_and_has_no_arm(fake_build, step_f, labs):
    d = labs
    m = d.build_side("hit", list(d.ARMS), {"F3": "BUST2 union invariant failed at step F: 7 rows"},
                     write=True)
    assert "F3" not in m["arms"] and set(m["arms"]) == {"E0", "Estar", "F1", "F2", "F4", "F5"}
    assert m["omitted"]["F3"]["attribution"] == "UNAVAILABLE"
    assert "never inferred" in m["omitted"]["F3"]["note"]
    # Estar carries every OTHER admitted factor; Arm R sits at its E0 value everywhere
    assert m["arms"]["Estar"]["factor_values"] == {
        "F1": "seasons", "F2": 2026, "F3": False, "F4": True, "F5": True}
    assert all(e["factor_values"]["F3"] is False for e in m["arms"].values())
    with pytest.raises(d.ArmRefused, match="omitted"):
        d.build_arm("hit", "F3", ("F3",))


def test_an_omission_needs_a_reason(fake_build, step_f, labs):
    d = labs
    with pytest.raises(d.ArmRefused, match="reason"):
        d.build_side("hit", ["E0"], {"F3": "  "}, write=False)
    with pytest.raises(d.ArmRefused, match="not a factor"):
        d.arm_factor_values("Estar", ("F9",))


# ---------------------------------------------------------------------------
# where it writes, and what it never touches
# ---------------------------------------------------------------------------

def test_default_output_sits_under_data_labs_and_never_at_a_served_path():
    d = _driver()
    assert d.OUT_DIR == ROOT / "data" / "_labs" / "fwar_epoch_arms"
    assert d.LABS_ROOT == ROOT / "data" / "_labs"
    for side in ("hit", "pit"):
        canon = ed.matrix_path(side)
        paths = {d.arm_path(side, a) for a in d.ARMS}
        assert len(paths) == 7 and canon not in paths
        assert all(p.parent == d.OUT_DIR for p in paths)
        assert all(p.name != canon.name and p.name != ed.live_matrix_path(side).name
                   for p in paths)
        # one level below data/_labs/, two below data/: nothing at the depth that ships
        assert all(p.parent.parent.parent == ROOT / "data" for p in paths)


def test_the_path_guard_refuses_outside_served_and_database_paths(labs, tmp_path):
    d = labs
    with pytest.raises(d.ArmRefused, match="outside"):
        d.assert_lab_path(tmp_path / "data" / "xfv_hitter_matrix__E0.json")
    with pytest.raises(d.ArmRefused, match="outside"):
        d.assert_lab_path(ROOT / "data" / "xfv_hitter_matrix.json")
    with pytest.raises(d.ArmRefused, match="served matrix name"):
        d.assert_lab_path(d.OUT_DIR / "xfv_hitter_matrix.json")
    with pytest.raises(d.ArmRefused, match="database"):
        d.assert_lab_path(d.OUT_DIR / "prospects.db")
    # OUT_DIR must be a proper subdirectory of the labs root, never the root itself
    d.OUT_DIR = d.LABS_ROOT
    with pytest.raises(d.ArmRefused, match="subdirectory"):
        d.assert_lab_path(d.LABS_ROOT / "x.json")


def test_the_builder_never_calls_the_writers():
    d = _driver()
    src = inspect.getsource(d)
    assert "ed.run(" not in src and "efv_dataset.run(" not in src
    assert "upsert" not in src and "storage.connect" not in src
    assert "sqlite3" not in src
    assert "matrix_path(side).write" not in src
    # part 9 and the gate are never written
    assert "FWAR_LABEL_EPOCH_GATE.md" in src and ".md\").write" not in src


def test_a_full_side_writes_seven_files_and_a_manifest_with_flags_and_hashes(
        fake_build, step_f, labs):
    d = labs
    m = d.build_side("pit", list(d.ARMS), {}, write=True)
    files = sorted(p.name for p in d.OUT_DIR.iterdir())
    assert files == sorted([f"xfv_pitcher_matrix__{a}.json" for a in d.ARMS] + ["manifest_pit.json"])
    assert set(m["arms"]) == set(d.ARMS) and m["omitted"] == {}
    assert m["seed"] == 20260807 and m["scored_years"] == list(em.SCORED_YEARS)
    assert m["resolved_through_at_build"] == 2026
    for arm, e in m["arms"].items():
        blob = (d.OUT_DIR / e["file"]).read_text(encoding="utf-8")
        assert d._sha256_blob(blob) == e["sha256"] and len(e["sha256"]) == 64
        assert e["rows"] == 5 and set(e["flags"]) == set(_snapshot())
        assert e["resolved_through"] in (2025, 2026) and e["label_seasons_key"] in ("seasons", "seasons_ewar_v2")
        assert "label_provider" in e and "census" in e
    assert m["arms"]["E0"]["label_provider"].startswith("ewar_v2 (career_war.seasons_ewar_v2")
    assert m["arms"]["F1"]["label_provider"].startswith("ewar_v2 (career_war.seasons_ewar_v2")
    assert "career_war.seasons," in m["arms"]["Estar"]["label_provider"]
    # the manifest round-trips and every arm's flags differ from Estar's in one place or none
    saved = json.loads((d.OUT_DIR / "manifest_pit.json").read_text(encoding="utf-8"))
    estar = saved["arms"]["Estar"]["flags"]
    for arm, e in saved["arms"].items():
        diff = [k for k in estar if e["flags"][k] != estar[k]]
        assert len(diff) == (0 if arm == "Estar" else (5 if arm == "E0" else 1)), (arm, diff)


def test_no_l1_flooring_anywhere_a_negative_label_stays_negative(fake_build, step_f, labs):
    d = labs
    d.build_side("hit", list(d.ARMS), {}, write=True)
    for arm in d.ARMS:
        rows = json.loads(d.arm_path("hit", arm).read_text(encoding="utf-8"))
        neg = next(r for r in rows if r["player_key"] == "hit_neg")
        assert neg["target_resolved"] == -1.4 and neg["target_censored"] == -1.4
    src = inspect.getsource(d)
    assert "max(0" not in src and "max(0.0" not in src
    c = d.census(rows, {}, d.arm_factor_values("Estar"))
    assert c["resolved_debuted_labels_below_zero"] == 1
    assert c["busts"] == 2 and c["busts_excluded_from_pool"] == 1 and c["busts_resolved"] == 1


def test_no_write_builds_the_census_and_leaves_the_directory_absent(fake_build, step_f, labs):
    d = labs
    m = d.build_side("hit", ["E0", "Estar"], {}, write=False)
    assert not d.OUT_DIR.exists()
    assert set(m["arms"]) == {"E0", "Estar"} and "file" not in m["arms"]["E0"]
    assert m["arms"]["Estar"]["census"]["window_shifted"] == 3
    assert m["arms"]["Estar"]["census"]["arm_r"]["resolved_to_censored"] == 2
    assert m["arms"]["E0"]["census"]["window_shifted"] == 0 and "arm_r" not in m["arms"]["E0"]["census"]


def test_the_cli_refuses_an_omit_without_its_reason(fake_build, step_f, labs):
    d = labs
    with pytest.raises(d.ArmRefused):
        d.main(["--side", "hit", "--arm", "E0", "--omit", "F3", "--no-write"])
