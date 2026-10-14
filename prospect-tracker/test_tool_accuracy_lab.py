# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential

"""tools/tool_accuracy_lab.py: the look P, W and T runner of
docs/tools-2026-10/TOOL_IMPLIED_PRODUCTION_GATE.md (TL_4_TOOL_LAB_BUILD).

Pins: the R-LV and R-VM guards raise; a source scan finds no grouping by a
future-value grade; forced equal weights give d exactly 0 on fixtures; a
shuffled outcome collapses rho on fixtures; a spent look is refused; the dry run
with None values completes for every look; the k_m constants match the gate's
Part 4 table once it is amended.
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
LAB_PATH = ROOT / "tools" / "tool_accuracy_lab.py"
GATE = ROOT / "docs" / "tools-2026-10" / "TOOL_IMPLIED_PRODUCTION_GATE.md"


@pytest.fixture(scope="module")
def lab():
    spec = importlib.util.spec_from_file_location("tool_accuracy_lab", LAB_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- guards ----------------------------------------------------------------
def test_rlv_guard_raises_without_the_record(lab):
    with pytest.raises(lab.GuardError):
        lab.guard_board_years([2019, 2020], None)
    with pytest.raises(lab.GuardError):
        lab.guard_board_years([2021], "deadbeef")
    lab.guard_board_years([2017, 2018, 2019, 2022], None)
    assert lab.rlv_record_exists(None) is False
    assert lab.rlv_record_exists("not-a-sha") is False


def test_rlv_record_commit_is_recognised(lab):
    # gate Part 0.3: the record is the EFV_V3_BACKTEST.md section 5.1 entry at 1c73c420
    if lab._git("cat-file", "-e", "1c73c420^{commit}") is None:
        pytest.skip("commit 1c73c420 is not in this history")
    assert lab.rlv_record_exists("1c73c420") is True
    lab.guard_board_years([2020, 2021], "1c73c420")


def test_rvm_guard_raises(lab):
    with pytest.raises(lab.GuardError):
        lab.guard_debut_years([2024, 2025])
    with pytest.raises(lab.GuardError):
        lab.guard_debut_years([2026])
    lab.guard_debut_years([2016, 2024, None])


def test_universe_drops_reserved_debuts_and_asserts(lab):
    import efv_identity
    idx = efv_identity.NameIndex()
    idx.add("Alpha Beta", 11, 2015, "hitting", 300)
    idx.add("Gamma Delta", 12, 2015, "hitting", 300)
    grades = {(2022, "fangraphs"): {"alpha": {"hit": 50.0, "game_pwr": 55.0},
                                    "gamma": {"hit": 45.0}},
              (2022, "mlb_pipeline"): {"alpha": {"hit": 55.0}, "gamma": {"hit": 50.0}}}
    debuts = [{"player_key": "alpha", "player_name": "Alpha Beta", "mlbam_id": 11, "position": "SS",
               "debut_date": "2023-05-01"},
              {"player_key": "gamma", "player_name": "Gamma Delta", "mlbam_id": 12, "position": "SS",
               "debut_date": "2025-04-01"}]
    uni = lab.Universe((2022,), None, grades=grades, debuts=debuts, index=idx)
    assert list(uni.rows) == [(2022, 11)]
    assert uni.counts["debut_after_frame"] == 1
    assert uni.rows[(2022, 11)]["consensus"]["hit"] == 52.5
    # the frozen-row loader refuses an R-VM debut and an R-LV grade point
    lab.guard_debut_years([int(d["debut_date"][:4]) for d in debuts[:1]])
    with pytest.raises(lab.GuardError):
        lab.guard_debut_years([int(d["debut_date"][:4]) for d in debuts])


def test_frozen_rows_loader_refuses_reserved_rows(lab, tmp_path, monkeypatch):
    p = tmp_path / "grade_rows_frozen.json"
    monkeypatch.setattr(lab, "FROZEN_ROWS", p)
    with pytest.raises(lab.GuardError):
        lab.load_frozen_rows()
    base = {"mlbam": 1, "side": "hit", "debut_date": "2019-06-01", "snapshot_date": "2018-02-01",
            "tools_consensus": {"hit": 50}}
    p.write_text(json.dumps({"rows": [dict(base, debut_date="2025-06-01")]}), encoding="utf-8")
    with pytest.raises(lab.GuardError):
        lab.load_frozen_rows()
    p.write_text(json.dumps({"rows": [dict(base, snapshot_date="2020-02-01")]}), encoding="utf-8")
    with pytest.raises(lab.GuardError):
        lab.load_frozen_rows()
    p.write_text(json.dumps({"rows": [base]}), encoding="utf-8")
    assert lab.load_frozen_rows() == [base]


def test_source_scan_finds_no_grouping_by_a_future_value_grade(lab):
    src = LAB_PATH.read_text(encoding="utf-8")
    forbidden = re.compile(r"""["']fv["']|consensus_fv|fv_tier|fv_cell|fv_bin|fv_high|fv_low|"""
                           r"""\bfv_\w+|\w+_fv\b|by_fv|fv_label""")
    hits = [ln.strip() for ln in src.splitlines() if forbidden.search(ln)]
    assert hits == [], hits
    with pytest.raises(lab.GuardError):
        lab.guard_no_grade_grouping(["grade", "fv_cell"])
    lab.guard_no_grade_grouping(["grade", "tool", "bin"])
    if lab.FROZEN_ROWS.exists():
        doc = json.loads(lab.FROZEN_ROWS.read_text(encoding="utf-8"))
        for r in doc["rows"][:200]:
            lab.guard_no_grade_grouping(r.keys())
            assert set(r) == {"mlbam", "side", "debut_date", "snapshot_date", "tools_consensus"}


# --- estimator controls on fixtures ------------------------------------------
def test_forced_equal_weights_give_d_exactly_zero(lab):
    fx = lab.fixtures(3)
    by_year, sources = fx["w_by_year"], lab.ARMS["A_fg_vs_pipeline"]
    ones = {s: 1.0 for s in sources}
    s = lab.BA2.score(lab.BA2.ab_pass(by_year, sources, lab.MIN_LAG_YEARS, weight_override=ones,
                                      allow_flat=True))
    assert s["n"] > 0 and s["d_rho"] == 0.0 and s["d_auc"] == 0.0
    cell = lab.w_cell(by_year, sources, boot=20, perm=12, controls=True)
    assert cell["C64_forced_equal_identity"]["passes"] is True
    assert cell["C0_numpy_equivalence_check"]["identical_to_1e12"] is True


def test_shuffled_outcome_collapses_rho(lab):
    fx = lab.fixtures(3)
    by_year, sources = fx["w_by_year"], lab.ARMS["A_fg_vs_pipeline"]
    real = lab.BA2.score(lab.BA2.ab_pass(by_year, sources, lab.MIN_LAG_YEARS))
    shuffled = lab.BA2.shuffled_outcome_null_np(by_year, sources, lab.MIN_LAG_YEARS, lab.W_SEED)
    assert real["weighted"]["spearman"] > 0.25
    assert lab.shuffled_collapsed(shuffled) is True
    if shuffled.get("n"):
        assert abs(shuffled["weighted"]["spearman"]) < real["weighted"]["spearman"] / 2.0
    assert lab.shuffled_collapsed({"n": 400, "weighted": {"spearman": 0.6}}) is False


# --- one-look rules ------------------------------------------------------------
def test_spent_look_is_refused(lab, tmp_path, monkeypatch):
    art = tmp_path / "power_composite_eval.json"
    monkeypatch.setitem(lab.ARTIFACT, "P", art)
    assert lab.look_spent("P") is None or "Part 8" in lab.look_spent("P")
    art.write_text(json.dumps({"look": "P", "spent": True}), encoding="utf-8")
    assert "look record" in lab.look_spent("P")
    with pytest.raises(lab.GuardError):
        lab.main(["--look", "P", "--gate-sha", "0" * 40])
    assert not art.read_text(encoding="utf-8").startswith("{\n \"generated_at")


def test_look_modes_refuse_without_a_registered_gate_sha(lab, tmp_path, monkeypatch):
    for look in ("P", "W"):
        monkeypatch.setitem(lab.ARTIFACT, look, tmp_path / f"{look}.json")
    with pytest.raises(lab.GuardError):
        lab.main(["--look", "P"])
    with pytest.raises(lab.GuardError):
        lab.main(["--look", "W", "--gate-sha", "not-a-sha"])
    assert lab.gate_sha_ok(None) is False
    assert lab.gate_sha_ok("0" * 40) is False


def test_dry_run_with_none_values_completes_for_every_look(lab, tmp_path):
    for look in ("P", "W", "T"):
        rec = lab.dry_run(look, tmp_path, boot=12, perm=8)
        assert rec["dry_run"] is True and rec["reads_real_rows"] is False
        assert lab.SURVIVORSHIP in rec["record_text"]
        assert Path(rec["path"]).exists()
    p = json.loads((tmp_path / "dry_run_P.json").read_text(encoding="utf-8"))
    assert p["result"]["verdict"]["serve"] in ("C0", "C1", "C2")
    w = json.loads((tmp_path / "dry_run_W.json").read_text(encoding="utf-8"))
    assert set(w["result"]["primaries"]) == {"hit", "speed", "field", "throw"}
    assert all(v["verdict"] == "secondary: no verdict" for v in w["result"]["secondaries"].values())
    t = json.loads((tmp_path / "dry_run_T.json").read_text(encoding="utf-8"))
    assert set(t["result"]["primary"]) == {c["cell"] for c in lab.T_PRIMARY}
    assert all(c["verdict"] in ("PASS", "FAIL", "NOT COMPUTABLE") for c in t["result"]["primary"].values())


def test_fixtures_carry_none_values(lab):
    fx = lab.fixtures(7)
    assert any(r["iso"] is None for r in fx["p_rows"])
    assert any(r["raw"] is None for r in fx["p_rows"])
    assert any(v.get("velo") is None for v in fx["t_fit"]["sp"].values())


# --- Part T mechanics --------------------------------------------------------------
def test_incumbent_reading_rules(lab):
    rows = lab.T_INCUMBENT["game_pwr__iso"]["rows"]
    assert lab.interp_table(rows, 45) == pytest.approx((0.089 + 0.140) / 2)
    assert lab.interp_table(rows, 10) == 0.0 and lab.interp_table(rows, 95) == 0.294
    sb = lab.T_INCUMBENT["speed__sb_per600"]["rows"]
    assert lab.interp_table(sb, 40) == 4.5 and lab.interp_table(sb, 25) == 0.0
    hr = lab.T_INCUMBENT["game_pwr__hr_per600"]["rows"]
    assert lab.interp_table(hr, 80) == 40.0


def test_mde_fold_leaves_the_held_out_season_out_of_the_fit(lab):
    fx = lab.fixtures(2)
    cell = lab.T_PRIMARY[1]                                       # game_pwr to ISO
    rows = lab.t_cell_rows(cell, fx["grade_rows"], fx["t_fit"], lab.T_FIT_SEASONS)
    tbl_all = lab.t_fit_candidate(cell, rows)
    tbl_wo = lab.t_fit_candidate(cell, rows, exclude_season=2019)
    assert tbl_all.n_rows >= tbl_wo.n_rows
    out = lab.t_mde_cell(cell, rows, fx["t_fit"], lab.T_FIT_SEASONS)
    assert out["folds_used"] >= lab.T_MIN_FOLDS and out["mde95"] is not None
    assert all(f["season"] != lab.T_HOLDOUT_SEASON for f in out["folds"])
    with pytest.raises(lab.GuardError):
        lab.guard_fit_seasons([2015, 2026], lab.T_FIT_SEASONS)
    with pytest.raises(lab.GuardError):
        lab.guard_fit_seasons([2020], lab.T_FIT_SEASONS)


def test_holm_step_down(lab):
    out = lab.holm({"a": 0.001, "b": 0.03, "c": None, "d": 0.2})
    assert out["a"]["rejected"] is True and out["a"]["step"] == 1
    assert out["b"]["rejected"] is False                          # 0.03 > 0.05 / 2
    assert out["c"]["step"] is None and out["a"]["m"] == 3


# --- Part 4: k_m pinned to the gate ------------------------------------------------
def test_k_m_matches_the_gate_part_4_table(lab):
    text = GATE.read_text(encoding="utf-8")
    m = re.search(r"^## Part 4\..*?$(.*?)(?=^## |\Z)", text, re.S | re.M)
    assert m, "the gate has no Part 4"
    body = m.group(1)
    if "PENDING: written by TL_4_TOOL_LAB_BUILD" in body and "| stat |" not in body:
        pytest.skip("Part 4 not yet amended")
    rows = {}
    for ln in body.splitlines():
        if not ln.startswith("| ") or ln.startswith("| stat") or ln.startswith("|---"):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        rows[cells[0]] = cells[-1]
    assert rows, "no Part 4 table rows"
    for stat, spec in lab.K_M.items():
        assert stat in rows, stat
        if spec["value"] is None:
            assert rows[stat].startswith("NOT COMPUTABLE"), stat
        else:
            assert float(rows[stat]) == pytest.approx(spec["value"], abs=1e-4), stat
    if lab.K_M_RECEIPT.exists():
        receipt = json.loads(lab.K_M_RECEIPT.read_text(encoding="utf-8"))
        for stat, spec in lab.K_M.items():
            assert receipt["stats"][stat].get("k_m") == spec["value"], stat
