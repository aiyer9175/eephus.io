"""EFV_2026_FOLD_TRAINING: the training-window amendment (docs/efv-v2/EFV_2026_TRAINING.md).

1. Flag off: every bound, path, pool and refusal is the incumbent's, byte for byte.
2. Flag on: the pool gains exactly the 2025 and 2026 debut-class rows, nothing after 2026,
   and the scoring and claim pins do not move.
3. No fit reads an open label window: with the 2026 window open the flag-on bound raises.
4. The fold-matrix builder refuses a build that disagrees with the served matrix.
5. Nothing is grouped by consensus-FV level (PROSPECT_ANCHOR_GATE).

No rater is scored here and no grade-vs-outcome statistic is computed.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

import efv_2026_fold as FOLD
import efv_dataset as D
import efv_v2_model as H
import efv_vintage_frame as F

ROOT = Path(__file__).resolve().parent


def _served_ok() -> bool:
    return all(D.matrix_path(s).exists() for s in F.SIDES)


needs_matrix = pytest.mark.skipif(not _served_ok(), reason="served matrices not on disk")


@pytest.fixture(autouse=True)
def _flag_and_memo(monkeypatch):
    monkeypatch.setattr(F, "EFV_TRAIN_THROUGH_2026", False)
    F._CLOSED_MEMO.clear()
    yield
    F._CLOSED_MEMO.clear()


def _vintage(fetched: str, status: str = "frozen") -> dict:
    blk = {"status": status, "fetched_at": fetched}
    return {"seasons": {"2026": {"hitting": dict(blk), "pitching": dict(blk)}}}


# ---------------------------------------------------------------------------
# 1. flag off
# ---------------------------------------------------------------------------

def test_flag_ships_off_and_the_bound_is_the_incumbent():
    src = (ROOT / "efv_vintage_frame.py").read_text(encoding="utf-8")
    assert "\nEFV_TRAIN_THROUGH_2026: bool = False\n" in src.replace("\r\n", "\n")
    assert F.R_VM_FIRST_DEBUT_YEAR == 2025
    assert F.TRAIN_THROUGH_SEASON == 2026
    assert F.train_end_year() == F.R_VM_FIRST_DEBUT_YEAR


def test_flag_off_reads_the_served_matrix_and_never_the_fold(monkeypatch):
    def boom(side):
        raise AssertionError("the fold matrix was read with the flag off")
    monkeypatch.setattr(F, "fold_matrix_path", boom)
    monkeypatch.setattr(F, "training_matrix_path", boom)
    for side in F.SIDES:
        assert H._matrix_path(side) == D.matrix_path(side)


def test_flag_off_check_years_refuses_2025_with_the_incumbent_message():
    assert H._check_years([2014, 2024]) == [2014, 2024]
    with pytest.raises(F.ReservedFrameError) as e:
        H._check_years([2024, 2025])
    assert str(e.value) == ("years [2025] reach the reserved R-VM cohorts (first 2025); "
                            "see docs/efv-v2/PROGRAM.md s2.4")


@needs_matrix
def test_flag_off_pool_is_the_served_pool(monkeypatch):
    def boom(side):
        raise AssertionError("the fold matrix was read with the flag off")
    monkeypatch.setattr(F, "training_matrix_path", boom)
    for side in F.SIDES:
        rows = json.loads(D.matrix_path(side).read_text(encoding="utf-8"))
        full = [r for r in rows if not (r["kind"] == "bust" and r.get("bust_recent"))]
        want = [d for d in H.V1._prep(full, "target_censored", side)
                if int(d["decision_year"]) < 2025]
        got = [d for d in H.training_rows(side) if int(d["decision_year"]) < F.train_end_year()]
        assert [(d["player_key"], d["decision_year"], d["target"], d["weight"]) for d in got] \
            == [(d["player_key"], d["decision_year"], d["target"], d["weight"]) for d in want]


def test_production_filters_read_the_one_bound():
    for mod in ("efv_v2_serve.py", "efv_v3.py", "efv_v4.py", "efv5_group_drivers.py",
                "efv5_combined.py"):
        src = (ROOT / mod).read_text(encoding="utf-8")
        assert 'int(r["decision_year"]) < F.train_end_year()' in src, mod


# ---------------------------------------------------------------------------
# 2. flag on
# ---------------------------------------------------------------------------

def _synthetic_fold(side: str, tmp_path: Path, n_new: int = 3) -> tuple[Path, list[dict]]:
    """The served matrix plus n_new 2026 debut rows copied from 2025 debut rows under new
    keys (shape only; no label is read by the test)."""
    served = json.loads(D.matrix_path(side).read_text(encoding="utf-8"))
    src = [r for r in served if r["kind"] == "debuted" and int(r["debut_year"]) == 2025][:n_new]
    new = []
    for i, r in enumerate(src):
        x = dict(r, player_key=f"zz_fold_test_{side}_{i}", debut_year=2026,
                 cutoff="2026-06-01", observed_seasons=1, weight=round(1 / 6, 3))
        new.append(x)
    p = tmp_path / f"fold_{side}.json"
    p.write_text(json.dumps(served + new, indent=0), encoding="utf-8")
    return p, new


def _closed_vintage(monkeypatch):
    monkeypatch.setattr(F, "_closed_memoized", lambda s: (True, "closed (test)"))


@needs_matrix
def test_flag_on_adds_exactly_the_2025_and_2026_rows(monkeypatch, tmp_path):
    paths, added = {}, {}
    for side in F.SIDES:
        paths[side], added[side] = _synthetic_fold(side, tmp_path)
    off = {s: {(int(d["decision_year"]), d["player_key"]) for d in H.training_rows(s)
               if int(d["decision_year"]) < F.train_end_year()} for s in F.SIDES}
    _closed_vintage(monkeypatch)
    monkeypatch.setattr(F, "fold_matrix_path", lambda side: paths[side])
    monkeypatch.setattr(F, "EFV_TRAIN_THROUGH_2026", True)
    assert F.train_end_year() == 2027
    for side in F.SIDES:
        assert H._matrix_path(side) == paths[side]
        on = {(int(d["decision_year"]), d["player_key"]) for d in H.training_rows(side)
              if int(d["decision_year"]) < F.train_end_year()}
        assert off[side] <= on
        gained = on - off[side]
        assert {y for y, _k in gained} <= {2025, 2026}
        assert {k for y, k in gained if y == 2026} == {r["player_key"] for r in added[side]}
        assert max(y for y, _k in on) <= F.TRAIN_THROUGH_SEASON


def test_flag_on_check_years_opens_2025_2026_and_refuses_2027(monkeypatch):
    _closed_vintage(monkeypatch)
    monkeypatch.setattr(F, "EFV_TRAIN_THROUGH_2026", True)
    assert H._check_years([2024, 2025, 2026]) == [2024, 2025, 2026]
    with pytest.raises(F.ReservedFrameError, match="after the training window"):
        H._check_years([2027])


def test_flag_on_keeps_every_scoring_and_claim_pin(monkeypatch):
    import efv_model
    import source_backtest as SB
    _closed_vintage(monkeypatch)
    monkeypatch.setattr(F, "EFV_TRAIN_THROUGH_2026", True)
    assert F.reserved_vm_pins() == []
    assert max(efv_model.SCORED_YEARS) < F.R_VM_FIRST_DEBUT_YEAR
    assert max(SB.CANDIDATE_YEARS) < F.R_VM_FIRST_DEBUT_YEAR
    with pytest.raises(F.ReservedFrameError):
        F.guard_vm_request([2025], gate_sha=None)
    with pytest.raises(F.ReservedFrameError):
        F.guard_score_request(2020, gate_sha=None)
    serve = (ROOT / "efv_v2_serve.py").read_text(encoding="utf-8")
    assert "if H.V2_FIRST_SCORED_YEAR <= y < F.R_VM_FIRST_DEBUT_YEAR]" in serve


def test_flag_on_v5_combined_refuses_rather_than_fit_on_missing_columns(monkeypatch):
    import efv5_combined as C
    _closed_vintage(monkeypatch)
    monkeypatch.setattr(F, "EFV_TRAIN_THROUGH_2026", True)
    with pytest.raises(NotImplementedError, match="no candidate-column builder"):
        C.production_train("hit", log=lambda *a: None)


# ---------------------------------------------------------------------------
# 3. the closed-window rule
# ---------------------------------------------------------------------------

def test_label_window_closed_rule():
    ok, _ = F.label_window_closed(2026, resolved_through=2026,
                                  vintage=_vintage("2026-10-02T23:08:19+00:00"))
    assert ok
    for rt, vin in ((2025, _vintage("2026-10-02T23:08:19+00:00")),
                    (2026, _vintage("2026-09-20T00:00:00+00:00")),
                    (2026, _vintage("2026-10-02T23:08:19+00:00", status="absent")),
                    (2026, {"seasons": {}}),
                    (2026, _vintage("not a date"))):
        ok, why = F.label_window_closed(2026, resolved_through=rt, vintage=vin)
        assert not ok, (rt, vin)
        assert why


def test_flag_on_with_an_open_window_reads_nothing(monkeypatch):
    monkeypatch.setattr(F, "EFV_TRAIN_THROUGH_2026", True)
    monkeypatch.setattr(D, "RESOLVED_THROUGH", 2025)
    F._CLOSED_MEMO.clear()
    with pytest.raises(F.ReservedFrameError, match="not closed"):
        F.train_end_year()
    with pytest.raises(F.ReservedFrameError, match="not closed"):
        H._matrix_path("hit")
    with pytest.raises(F.ReservedFrameError, match="not closed"):
        H._check_years([2024])
    # the flag off is untouched by the open window
    monkeypatch.setattr(F, "EFV_TRAIN_THROUGH_2026", False)
    assert F.train_end_year() == 2025


def test_flag_on_without_a_fold_build_refuses(monkeypatch, tmp_path):
    _closed_vintage(monkeypatch)
    monkeypatch.setattr(F, "EFV_TRAIN_THROUGH_2026", True)
    monkeypatch.setattr(F, "fold_matrix_path", lambda side: tmp_path / "missing.json")
    with pytest.raises(F.ReservedFrameError, match="efv_2026_fold.py --build"):
        H._matrix_path("pit")


def test_the_frozen_label_closes_2026_today():
    import fwar_vintage as FV
    if not FV.VINTAGE_PATH.exists():
        pytest.skip("fWAR vintage not on disk")
    ok, why = F.label_window_closed(2026)
    assert ok, why
    assert F.train_end_year(flag=True) == 2027


# ---------------------------------------------------------------------------
# 4. the fold-matrix builder
# ---------------------------------------------------------------------------

def _rows():
    return [{"player_key": "a", "kind": "debuted", "debut_year": 2024, "x": 1},
            {"player_key": "b", "kind": "bust", "x": 2}]


def test_build_fold_adds_only_the_new_cohort():
    served = _rows()
    new = {"player_key": "c", "kind": "debuted", "debut_year": 2026, "x": 3}
    seen = {}

    def builder(side):
        seen["years"] = D.DEBUT_YEARS
        return [dict(r) for r in served] + [new], {}
    rows, rec = FOLD.build_fold("hit", served=served, builder=builder)
    assert seen["years"][-1] == 2026
    assert D.DEBUT_YEARS[-1] == D.RESOLVED_THROUGH - 1      # restored
    assert rows[-1] == new
    assert rec["added_rows"] == 1 and rec["added_by_debut_year"] == {"2026": 1}
    assert rec["shared_rows_identical"] is True


@pytest.mark.parametrize("mutate", ["changed", "missing", "stray_bust", "stray_year"])
def test_build_fold_refuses_a_disagreeing_build(mutate):
    served = _rows()

    def builder(side):
        rows = [dict(r) for r in served]
        if mutate == "changed":
            rows[0]["x"] = 9
        elif mutate == "missing":
            rows = rows[:1]
        elif mutate == "stray_bust":
            rows.append({"player_key": "c", "kind": "bust", "x": 3})
        else:
            rows.append({"player_key": "c", "kind": "debuted", "debut_year": 2027, "x": 3})
        return rows, {}
    with pytest.raises(ValueError, match="disagrees with the served matrix"):
        FOLD.build_fold("hit", served=served, builder=builder)


def test_the_served_matrix_path_is_never_written_by_the_fold_tool():
    tree = ast.parse((ROOT / "efv_2026_fold.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "write_text":
            target = ast.unparse(node.func.value)
            assert "matrix_path" not in target or "fold_matrix_path" in target, target


# ---------------------------------------------------------------------------
# 5. PROSPECT_ANCHOR_GATE
# ---------------------------------------------------------------------------

_FV_GRID = {35, 40, 45, 50, 55, 60, 65, 70, 75, 80}
_BANNED_TOKENS = ("groupby", "tier", "bucket", "cell", "stratum", "strata", "by_fv",
                  "fv_band", "fv_bin")


def test_no_fv_cell_grouping():
    tree = ast.parse((ROOT / "efv_2026_fold.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        name = (node.id if isinstance(node, ast.Name) else
                node.attr if isinstance(node, ast.Attribute) else
                node.name if isinstance(node, (ast.FunctionDef, ast.ClassDef)) else None)
        if name:
            assert not any(t in name.lower() for t in _BANNED_TOKENS), name
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            assert node.value not in _FV_GRID, (node.value, node.lineno)
