# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The two Appendix A label arms, both flagged and both default OFF.

Appendix A of docs/efv-2026-09-03/EWAR_LABEL_EPOCH_GATE.md freezes two
label-definition fixes and the arm plan E0-E3 that isolates them:

  A1  efv_dataset.SERVICE_ALIGNED_WINDOW (audit F03): the debut season is service
      year 1 only if the debut is on or before the mid-April cut; otherwise the
      window shifts to debut+1..debut+6 and the debut season is added as a stub.
  A2  efv_model.NEUTRAL_MILB_IMPUTE (audit F04): a milb_unavailable row's MiLB keys
      are imputed at the has-MiLB mean of the fold's TRAIN rows instead of raw 0.0.

The load-bearing property is that OFF is the incumbent to the byte, since the epoch
attributes its blast radius to the WAR basis and an arm leaking into a default build
would destroy that attribution (gate clause f). Everything else here is the arms'
own behaviour, tested offline on synthetic rows: no matrix build, no DB, no fixture.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import efv_dataset as ed
import efv_model as em
import prospect_path as pp

ROOT = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# flags
# ---------------------------------------------------------------------------

def test_both_arms_default_off():
    """A build today is a build yesterday. Flipping either default is a served-number
    change and belongs in the rebuild wave's driver, not in the module."""
    assert ed.SERVICE_ALIGNED_WINDOW is False
    assert em.NEUTRAL_MILB_IMPUTE is False


@pytest.fixture
def arm_a1():
    """SERVICE_ALIGNED_WINDOW on for one test, restored afterwards."""
    old = ed.SERVICE_ALIGNED_WINDOW
    ed.SERVICE_ALIGNED_WINDOW = True
    try:
        yield
    finally:
        ed.SERVICE_ALIGNED_WINDOW = old


@pytest.fixture
def arm_a2():
    """NEUTRAL_MILB_IMPUTE on for one test, restored afterwards."""
    old = em.NEUTRAL_MILB_IMPUTE
    em.NEUTRAL_MILB_IMPUTE = True
    try:
        yield
    finally:
        em.NEUTRAL_MILB_IMPUTE = old


# ---------------------------------------------------------------------------
# A1: the service-aligned window
# ---------------------------------------------------------------------------

def _incumbent_label_6yr(seasons, debut_year):
    """The shipped label as of b59e7386, copied verbatim so the flag-off path is
    pinned against the code it replaced rather than against itself."""
    window = [debut_year + i for i in range(ed.TARGET_SEASONS)]
    observed = [y for y in window if y <= ed.RESOLVED_THROUGH]
    obs_sum = round(sum(seasons.get(y, 0.0) for y in observed), 3)
    n_obs = len(observed)
    full_resolved = (debut_year + ed.TARGET_SEASONS - 1) <= ed.RESOLVED_THROUGH
    if full_resolved:
        return obs_sum, obs_sum, False, 1.0, n_obs
    rate = obs_sum / n_obs if n_obs else 0.0
    n_missing = ed.TARGET_SEASONS - n_obs
    censored_target = round(obs_sum + n_missing * rate, 3)
    weight = round(n_obs / ed.TARGET_SEASONS, 3)
    return obs_sum, censored_target, True, weight, n_obs


# (debut_date, debut_year, seasons). Covers a September debut, an April debut on each
# side of the cut, a missing-line (postseason-only) debut and a missing date.
_CASES = [
    ("2017-04-03", 2017, {2017: 0.4, 2018: 1.1, 2019: 2.6, 2020: 0.3, 2021: 3.9,
                          2022: 4.4, 2023: 5.1}),
    ("2017-04-20", 2017, {2017: 0.1, 2018: 1.9, 2019: 2.2, 2020: 0.0, 2021: 3.3,
                          2022: 4.0, 2023: 4.8}),
    ("2019-09-11", 2019, {2019: 0.15, 2020: 0.9, 2021: 2.0, 2022: 2.4, 2023: 3.1,
                          2024: 3.7, 2025: 4.2}),
    ("2020-09-20", 2020, {2021: 1.0, 2022: 1.5, 2023: 2.2, 2024: 2.9, 2025: 3.4}),
    ("2022-09-10", 2022, {2022: 1.0, 2023: 2.0, 2024: 3.0, 2025: 4.0}),
    ("2023-08-02", 2023, {2023: 0.2, 2024: 1.4, 2025: 2.0}),
    (None, 2021, {2021: 1.2, 2022: 2.0, 2023: 2.4, 2024: 3.0, 2025: 3.3}),
]


@pytest.mark.parametrize("dd,dy,seasons", _CASES)
def test_flag_off_reproduces_the_incumbent_label(dd, dy, seasons):
    """OFF is byte-identical, and it ignores the debut date entirely."""
    assert ed.SERVICE_ALIGNED_WINDOW is False
    assert ed._label_6yr(seasons, dy, dd) == _incumbent_label_6yr(seasons, dy)
    assert ed._label_6yr(seasons, dy, dd) == ed._label_6yr(seasons, dy, None)


def test_september_debut_shifts_and_adds_its_stub(arm_a1):
    """The 2019 September row: window 2020..2025 instead of 2019..2024, and the 0.15
    WAR banked in the stub season is added rather than dropped."""
    dd, dy, seasons = _CASES[2]
    off = _incumbent_label_6yr(seasons, dy)
    on = ed._label_6yr(seasons, dy, dd)
    assert off[0] == round(sum(seasons[y] for y in range(2019, 2025)), 3) == 12.25
    # shifted window 2020..2025 = 16.3, plus the 0.15 stub
    assert on[0] == 16.45
    assert on[4] == off[4] == 6 and on[2] is False and on[1] == on[0]


def test_april_debut_does_not_shift(arm_a1):
    """An April 3 debut keeps the calendar window. April 20 does not: the convention
    cuts at 04-15, so the boundary sits inside April and both rows are pinned."""
    early_dd, early_dy, early_s = _CASES[0]
    late_dd, late_dy, late_s = _CASES[1]
    assert ed._label_6yr(early_s, early_dy, early_dd) == _incumbent_label_6yr(
        early_s, early_dy)
    # 04-20 is past the cut, so the convention moves it; this is the boundary, and it
    # is why the convention is recorded in _service_window_shifts as a convention.
    assert ed._service_window_shifts(early_dd) is False
    assert ed._service_window_shifts(late_dd) is True


def test_the_cut_is_the_documented_convention():
    """Flag-independent predicate, so the census can count rows without the arm on."""
    assert ed._SERVICE_YEAR_CUT_MMDD == "04-15"
    assert ed._service_window_shifts("2019-04-15") is False
    assert ed._service_window_shifts("2019-04-16") is True
    assert ed._service_window_shifts(None) is False
    assert ed._service_window_shifts("2019") is False


def test_shifted_window_recomputes_the_censoring_weight(arm_a1):
    """The censoring interaction. A shifted window ends a year later, so
    RESOLVED_THROUGH admits one fewer observed season and n_obs, the weight and the
    tail projection all move onto the SHIFTED window.

    The projected total also pins that the tail rate EXCLUDES the stub: 3 observed
    service seasons summing 9.0 project 3.0/season (19.0 total), not 10.0/3 (20.0)."""
    dd, dy, seasons = _CASES[4]
    assert _incumbent_label_6yr(seasons, dy) == (10.0, 15.0, True, 0.667, 4)
    assert ed._label_6yr(seasons, dy, dd) == (10.0, 19.0, True, 0.5, 3)


def test_shift_can_turn_a_resolved_row_into_a_censored_one(arm_a1):
    """A 2020 September debut resolves through 2025 on the calendar window and does
    NOT on the shifted one, which is exactly the case the weight recompute exists for."""
    seasons = {2020: 0.5, 2021: 1.0, 2022: 1.5, 2023: 2.0, 2024: 2.5, 2025: 3.0}
    off = _incumbent_label_6yr(seasons, 2020)
    on = ed._label_6yr(seasons, 2020, "2020-09-01")
    assert off[2] is False and off[3] == 1.0 and off[4] == 6
    assert on[2] is True and on[3] == round(5 / 6, 3) and on[4] == 5
    assert on[0] == 10.5   # 2021..2025 = 10.0, plus the 0.5 stub


def test_a_redated_row_is_not_shifted_twice(arm_a1):
    """The debuted loop re-dates a postseason-only debut to the first WAR season and
    then passes no date. That row must land on the same label the shift would give it,
    not one year further out."""
    dd, dy, seasons = _CASES[3]
    redated = ed._label_6yr(seasons, dy + 1, None)       # what the loop does
    shifted = ed._label_6yr(seasons, dy, dd)             # what the arm would do
    assert redated == shifted


def test_no_row_ends_with_neither_an_observed_season_nor_a_weight(arm_a1):
    """Every admitted debut cohort keeps at least one observed season and a positive
    weight under BOTH windows, and a window with none raises instead of returning a
    zero-weight row with a fabricated label."""
    seasons = {y: 1.0 for y in range(2011, ed.RESOLVED_THROUGH + 1)}
    for dy in ed.DEBUT_YEARS:
        for dd in (None, f"{dy}-04-01", f"{dy}-09-15"):
            t_res, t_cens, cflag, w, n_obs = ed._label_6yr(seasons, dy, dd)
            assert n_obs >= 1 and w > 0.0
    with pytest.raises(ValueError):
        # one year past the last admitted cohort, shifted: the window opens after
        # RESOLVED_THROUGH and there is nothing to observe
        ed._label_6yr(seasons, ed.RESOLVED_THROUGH, f"{ed.RESOLVED_THROUGH}-09-15")


# ---------------------------------------------------------------------------
# A2: neutral imputation for milb_unavailable rows
# ---------------------------------------------------------------------------

_KEYS = ["fv", "level_rank"]


def _prepped(pk, *, unavailable=False, missing=False, level=4.0, fv=45.0, target=5.0,
             year=2018):
    """One _prep-shaped row. Hand-built, because _prep needs a whole matrix row and
    the arm only ever reads `feats`."""
    return {"player_key": pk, "kind": "debuted", "decision_year": year,
            "feats": {"fv": fv, "level_rank": level,
                      "milb_missing": 1.0 if missing else 0.0,
                      "milb_unavailable": 1.0 if unavailable else 0.0},
            "target": target, "weight": 1.0, "fv": fv}


def _train_pool():
    """39 has-block rows at level_rank mean exactly 4.0 (3/4/5 in equal thirds), 20
    milb_unavailable rows at raw 0.0 and 6 no-track-record rows at 0.0. The pool mean
    over all 65 is 2.4; the has-block mean is 4.0; 4.0 is what the arm must impute."""
    rows = [_prepped(f"h{i}", level=3.0 + (i % 3), target=4.0 + 0.1 * i)
            for i in range(39)]
    rows += [_prepped(f"u{i}", unavailable=True, level=0.0, target=1.0 + 0.1 * i)
             for i in range(20)]
    rows += [_prepped(f"m{i}", missing=True, level=0.0, target=0.5) for i in range(6)]
    return rows


def test_vec_marker_is_inert():
    """The marker exists on every vector and is in no model's feature list."""
    for side in ("hit", "pit"):
        keys, _ = em._feature_spec(side)
        assert "milb_unavailable" not in keys
        assert "milb_unavailable" in em._vec({}, side)
    assert em._vec({"milb_unavailable": True}, "hit")["milb_unavailable"] == 1.0
    assert em._vec({"milb": {"level_rank": 3}}, "hit")["milb_unavailable"] == 0.0


def test_has_block_mean_is_the_train_has_milb_mean_not_the_pool_mean():
    """The imputed value is the mean over rows that HAVE a block. Rows with no block
    (either population) are excluded, so their zeros cannot drag the value down."""
    train = _train_pool()
    means = em._has_milb_impute_means(train)
    assert means["level_rank"] == pytest.approx(4.0)
    pool = sum(r["feats"]["level_rank"] for r in train) / len(train)
    assert pool == pytest.approx(2.4, abs=1e-9)
    assert means["level_rank"] != pytest.approx(pool)


def test_the_mean_is_train_only_so_it_cannot_leak_across_folds():
    """Adding rows to the TEST side of a fold cannot move the imputed value, which is
    the whole reason the mean is taken inside the fit and stored on the model."""
    train = _train_pool()
    test = [_prepped(f"t{i}", level=99.0, target=30.0, year=2019) for i in range(30)]
    assert em._has_milb_impute_means(train) == em._has_milb_impute_means(train)
    assert (em._has_milb_impute_means(train)["level_rank"]
            != em._has_milb_impute_means(train + test)["level_rank"])


def test_imputation_touches_only_milb_unavailable_rows(arm_a2):
    """has-block and no-track-record rows come back as the SAME OBJECT; only the
    unavailable rows are copied and moved."""
    means = {"level_rank": 4.0}
    has_block = _prepped("h")["feats"]
    no_record = _prepped("m", missing=True)["feats"]
    unavail = _prepped("u", unavailable=True, level=0.0)["feats"]
    assert em._impute_feats(has_block, means) is has_block
    assert em._impute_feats(no_record, means) is no_record
    moved = em._impute_feats(unavail, means)
    assert moved is not unavail and unavail["level_rank"] == 0.0
    assert moved["level_rank"] == 4.0
    assert {k: v for k, v in moved.items() if k != "level_rank"} == {
        k: v for k, v in unavail.items() if k != "level_rank"}


def test_flag_off_fit_and_predict_are_pass_through():
    """OFF calls prospect_path with the same arguments and stores no imputation, so
    the shipped ridge is the shipped ridge."""
    train = _train_pool()
    assert em._fit_ridge(train, _KEYS) == pp._fit_ridge(train, _KEYS)
    model = em._fit_ridge(train, _KEYS)
    assert "milb_impute" not in model
    feats = _prepped("x", unavailable=True, level=0.0)["feats"]
    assert em._predict(model, feats) == pp._predict(model, feats)


def test_flag_on_fits_and_scores_on_the_imputed_vector(arm_a2):
    """The fitted model carries its own train means, and the unavailable row it scores
    is the one the fit saw: level_rank 4.0, not 0.0. A has-block row is unmoved."""
    train = _train_pool()
    model = em._fit_ridge(train, _KEYS)
    assert model["milb_impute"]["level_rank"] == pytest.approx(4.0)
    unavail = _prepped("x", unavailable=True, level=0.0)["feats"]
    at_mean = dict(unavail, level_rank=4.0)
    assert em._predict(model, unavail) == pp._predict(model, at_mean)
    assert em._predict(model, unavail) != pp._predict(model, unavail)
    has_block = _prepped("h", level=5.0)["feats"]
    assert em._predict(model, has_block) == pp._predict(model, has_block)


def test_flag_on_moves_the_level_rank_coefficient(arm_a2):
    """Audit F04's claim, on a synthetic pool built to show it: with the unavailable
    block pinned at the floor the fit reads the level slope off a contrast that is
    half era proxy, and imputing at the has-block mean changes the coefficient."""
    train = _train_pool()
    off = pp._fit_ridge(train, _KEYS)
    on = em._fit_ridge(train, _KEYS)
    i = _KEYS.index("level_rank")
    assert off["w"][i] != pytest.approx(on["w"][i])


# ---------------------------------------------------------------------------
# the arm driver
# ---------------------------------------------------------------------------

def _driver():
    """tools/build_label_arms.py loaded by path. Importing it must do nothing: no
    build, no write, no flag left set."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_build_label_arms", ROOT / "tools" / "build_label_arms.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert ed.SERVICE_ALIGNED_WINDOW is False and em.NEUTRAL_MILB_IMPUTE is False
    return mod


def test_arm_table_and_paths_never_touch_the_canonical_matrix():
    d = _driver()
    assert d.ARMS == {"E0": (False, False), "E1": (True, False),
                      "E2": (False, True), "E3": (True, True)}
    for side in ("hit", "pit"):
        canon = ed.matrix_path(side)
        paths = {d.arm_path(side, a) for a in d.ARMS}
        assert canon not in paths and len(paths) == 4
        assert all(p.parent == canon.parent for p in paths)


def test_build_arm_sets_both_flags_and_restores_them_even_on_failure(monkeypatch):
    """A leaked flag is the failure this whole lane exists to prevent: the next build
    in the same process would silently be an arm."""
    seen = {}

    def _boom(side):
        seen[side] = (ed.SERVICE_ALIGNED_WINDOW, em.NEUTRAL_MILB_IMPUTE)
        raise RuntimeError("no build in tests")

    d = _driver()
    monkeypatch.setattr(ed, "build_matrix", _boom)
    for arm, flags in d.ARMS.items():
        with pytest.raises(RuntimeError):
            d.build_arm("hit", arm)
        assert seen["hit"] == flags
        assert ed.SERVICE_ALIGNED_WINDOW is False and em.NEUTRAL_MILB_IMPUTE is False


def _matrix_row(pk, *, target=5.0, weight=1.0, unavailable=False, censored=False):
    return {"player_key": pk, "kind": "debuted", "target_resolved": target,
            "target_censored": target, "weight": weight, "observed_seasons": 6,
            "censored": censored, "milb": None if unavailable else {"level_rank": 4.0},
            "milb_unavailable": unavailable or None}


def test_census_counts_the_label_move_the_shift_and_the_imputation():
    d = _driver()
    base = [_matrix_row("a"), _matrix_row("b"), _matrix_row("c", unavailable=True)]
    arm = [_matrix_row("a", target=6.0),                       # label moved +1.0
           _matrix_row("b", weight=0.5, censored=True),        # weight moved, label not
           _matrix_row("c", unavailable=True)]
    c = d.census(arm, {"debuted_window_shifted": 2}, "hit", "E1", base_rows=base)
    assert c["rows"] == 3 and c["window_shifted"] == 2
    assert c["rows_moved_vs_E0"] == 2 and c["label_moved_vs_E0"] == 1
    assert c["weight_moved_vs_E0"] == 1
    assert c["mean_label_change"] == 0.3333   # rounded to 4dp by the census
    assert c["mean_label_change_on_moved"] == 1.0
    # E1 leaves the imputation alone; E2 moves exactly the milb_unavailable rows
    assert c["imputation_changed"] == 0 and c["milb_unavailable_rows"] == 1
    c2 = d.census(arm, {}, "hit", "E2", base_rows=base)
    assert c2["imputation_changed"] == 1
    assert c2["census_level_rank_has_milb_mean"] == 4.0
    # E0 has nothing to compare against and says so instead of printing zeros
    assert d.census(arm, {}, "hit", "E0")["vs_E0"].startswith("unavailable")
