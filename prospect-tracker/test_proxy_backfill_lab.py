"""TL_8 proxy backfill lab: the frame guards, the forward chain and the served constant.

Pure-code tests on synthetic pairs; nothing here reads a Savant file, a debut cohort or
the lab artifact's numbers.
"""
import re
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "tools"))

import efv_proxy  # noqa: E402
import proxy_backfill_lab as L  # noqa: E402
from efv_vintage_frame import R_VM_FIRST_DEBUT_YEAR, ReservedFrameError  # noqa: E402

EMPTY_PART13 = (
    "# gate\n\n## Part 12. What each verdict serves\n\ntext\n\n## Part 13. Results\n\n"
    "EMPTY AT REGISTRATION. The look entry is written here by TL_17, pasted verbatim from "
    "its runner and dated.\nMore registration text.\n")


def test_served_cohort_years_unchanged():
    assert efv_proxy.COHORT_YEARS == (2024, 2025, 2026)


def test_served_defaults_unchanged():
    """The parameters the lab passes default to the served behaviour."""
    import inspect
    bp = inspect.signature(efv_proxy._build_pairs).parameters["cohort_years"].default
    ef = inspect.signature(efv_proxy._eval_forward).parameters["test_years"].default
    assert bp is efv_proxy.COHORT_YEARS
    assert ef == (2025, 2026)


def test_lab_frame_constants():
    assert L.BACKFILL_COHORTS == (2016, 2017, 2018, 2019, 2020, 2021)
    assert L.TEST_YEARS == (2018, 2019, 2020, 2021)
    assert max(L.BACKFILL_COHORTS) < L.HOLDOUT_FIRST_DEBUT_YEAR < R_VM_FIRST_DEBUT_YEAR
    assert 2020 in L.SEASON_FLAGS


@pytest.mark.parametrize("years", [(2025,), (2026,), (2019, 2025), (2030,)])
def test_rvm_always_raises(years, tmp_path):
    """R-VM raises even when a holdout look record and its artifact exist."""
    rec = EMPTY_PART13 + "\n### 2026-12-10: the look, TL_17\n\nresult\n"
    ev = tmp_path / "prospect_statline_eval.json"
    ev.write_text("{}", encoding="utf-8")
    assert L.holdout_look_recorded(rec, ev)
    with pytest.raises(ReservedFrameError):
        L.guard_years(years, (), gate_text=rec, eval_path=ev)
    with pytest.raises(ReservedFrameError):
        L.guard_years((2016, 2017), years, gate_text=rec, eval_path=ev)


def test_rvm_raises_before_any_read(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("a pair was built for a reserved cohort")
    monkeypatch.setattr(efv_proxy, "_build_pairs", boom)
    monkeypatch.setattr(efv_proxy, "_pull_targets", boom)
    with pytest.raises(ReservedFrameError):
        L.run(persist=False, cohort_years=(2020, 2021, 2025), test_years=(2021, 2025))


@pytest.mark.parametrize("y", [2022, 2023, 2024])
def test_holdout_raises_until_the_look_record(y, tmp_path):
    ev = tmp_path / "prospect_statline_eval.json"
    with pytest.raises(L.HoldoutFrameError):
        L.guard_years((2016, y), (y,), gate_text=EMPTY_PART13, eval_path=ev)
    # an amendment or a dev-read freeze under Part 13 is not a look record
    amended = EMPTY_PART13 + "\n### 2026-10-27: amendment, the development-read freeze\n"
    ev.write_text("{}", encoding="utf-8")
    with pytest.raises(L.HoldoutFrameError):
        L.guard_years((2016, y), (y,), gate_text=amended, eval_path=ev)
    # a look heading without the look's artifact still reads as no record
    rec = EMPTY_PART13 + "\n### 2026-12-10: the look, TL_17\n"
    ev.unlink()
    with pytest.raises(L.HoldoutFrameError):
        L.guard_years((2016, y), (y,), gate_text=rec, eval_path=ev)
    ev.write_text("{}", encoding="utf-8")
    L.guard_years((2016, y), (y,), gate_text=rec, eval_path=ev)


def test_holdout_closed_at_head():
    """At registration Part 13 is empty, so the committed gate keeps holdout H closed."""
    text = L.GATE_DOC.read_text(encoding="utf-8")
    assert "## Part 13. Results" in text
    if not L.holdout_look_recorded(text):
        with pytest.raises(L.HoldoutFrameError):
            L.guard_years(L.BACKFILL_COHORTS + (2022,), L.TEST_YEARS)


def test_default_frame_passes_the_guard():
    L.guard_years(L.BACKFILL_COHORTS, L.TEST_YEARS, gate_text=EMPTY_PART13)


def test_test_year_needs_an_earlier_cohort():
    with pytest.raises(ValueError):
        L.guard_years((2018, 2019), (2018,), gate_text=EMPTY_PART13)
    with pytest.raises(ValueError):
        L.guard_years((2016, 2017), (2019,), gate_text=EMPTY_PART13)


def _synthetic_pairs():
    rng = np.random.default_rng(20261009)
    pairs = []
    for y in L.BACKFILL_COHORTS:
        for _ in range(40):
            a = float(rng.normal())
            pairs.append({"key": f"p{y}{_}", "year": y, "x": [float(y), a],
                          "y": 0.30 + 0.01 * a + float(rng.normal(0, 0.01))})
    return pairs


def test_training_strictly_earlier_than_test_year(monkeypatch):
    """Spy on the scaler efv_proxy fits: column 0 carries the debut year, so every fit
    for test year t must see only years below t, and every prediction only year t."""
    seen = []

    class SpyScaler(efv_proxy.StandardScaler):
        def fit(self, X, y=None, sample_weight=None):
            seen.append(("fit", sorted({int(v) for v in np.asarray(X)[:, 0]})))
            return super().fit(X, y)

        def transform(self, X, copy=None):
            seen.append(("transform", sorted({int(v) for v in np.asarray(X)[:, 0]})))
            return super().transform(X)

    monkeypatch.setattr(efv_proxy, "StandardScaler", SpyScaler)
    pairs = _synthetic_pairs()
    out = L.evaluate_side("hit", pairs, ["year", "a"], L.TEST_YEARS)
    fits = [yrs for kind, yrs in seen if kind == "fit"]
    # one fit per test year in the per-year calls, then one per test year in the pooled call
    assert len(fits) == 2 * len(L.TEST_YEARS)
    for t, yrs in zip(list(L.TEST_YEARS) * 2, fits):
        assert yrs and max(yrs) < t, (t, yrs)
        assert yrs == [c for c in L.BACKFILL_COHORTS if c < t]
    for t in L.TEST_YEARS:
        row = out["per_year"][str(t)]
        assert row["train_cohorts"] == [c for c in L.BACKFILL_COHORTS if c < t]
        assert row["train_n"] == 40 * len(row["train_cohorts"])
        assert row["n"] == 40
    assert out["per_year"]["2020"]["flag"].startswith("60-game")
    assert out["per_year"]["2021"]["train_includes_flagged"] == [2020]
    assert out["pooled"]["n"] == 40 * len(L.TEST_YEARS)


def test_check_pairs_rejects_outside_cohorts():
    with pytest.raises(RuntimeError):
        L._check_pairs([{"year": 2022}], L.BACKFILL_COHORTS)
    L._check_pairs([{"year": 2016}, {"year": 2021}], L.BACKFILL_COHORTS)


def test_artifact_path_is_lab_only():
    assert L.OUT_PATH.parent.name == "_labs"
    excl = (ROOT / "deploy" / "data_exclude.txt").read_text(encoding="utf-8")
    assert "proxy_backfill" not in excl


def test_no_fv_cell_grouping():
    """docs/PROSPECT_ANCHOR_GATE.md: no grouping, key or label by consensus-FV level."""
    src = (ROOT / "tools" / "proxy_backfill_lab.py").read_text(encoding="utf-8")
    for tok in ("by_fv", "fv_band", "fv_bin", "fv_cell", "fv_tier", "fv_bucket", "groupby"):
        assert tok not in src, tok
    assert not re.search(r"consensus_fv", src)
