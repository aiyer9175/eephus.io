# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Tests for etools.py (docs/tools-2026-10/ETOOLS_GATE.md). Fixtures only: no database,
no cache, no label is read."""
from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest

import etools as E

SRC = Path(E.__file__).read_text(encoding="utf-8")


def test_flag_is_dark_and_preview_off_the_webroot():
    assert E.ETOOLS_ON is False
    assert "_labs" in E.EVAL_PATH.parts and "_labs" in E.ATLAS_PATH.parts
    assert ".cache" in E.PREVIEW_PATH.parts
    assert E.SERVED_PATH.name == "etools.json"


def test_development_years_exclude_the_reserved_lists():
    assert 2020 not in E.DEV_YEARS and 2021 not in E.DEV_YEARS
    assert max(E.DEV_YEARS) == 2024 and min(E.DEV_YEARS) == 2011
    with pytest.raises(E.GuardError):
        E.guard_years([2019, 2020])
    E.guard_years([2011, 2024])


def test_no_fv_grouping_key():
    with pytest.raises(E.GuardError):
        E.guard_no_fv(["group", "fv_band"])
    E.guard_no_fv(["group", "level", "age_band"])


def test_source_never_calls_the_banned_entry_points():
    tree = ast.parse(SRC)
    names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    names |= {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    for banned in ("run_backtest", "run_monthly", "build_site"):
        assert banned not in names
    assert "urlopen" not in SRC and "requests." not in SRC


def test_gate_sha_rejects_garbage():
    assert not E.gate_sha_ok(None)
    assert not E.gate_sha_ok("not-a-sha")
    assert not E.gate_sha_ok("0000000")


def test_constants_match_the_gate():
    assert E.SEED == 20261023 and E.PERM_SEED == 20261024 and E.B == 2000
    assert E.Q_ADMIT == 0.10 and E.R_CAP == 0.6 and E.MAX_SUB == 3 and E.POOL_MIN == 100
    assert E.LAST_UM_SEASON == 2024 and E.MAX_DEBUT_YEAR == 2024
    gate = (Path(E.ROOT) / E.GATE_DOC).read_text(encoding="utf-8")
    assert "Registration status: REGISTERED" in gate
    for tool, spec in E.TOOLS.items():
        for c in spec["cands"]:
            assert c in gate, (tool, c)


def test_fold_is_player_disjoint():
    year = np.array([2011, 2011, 2012, 2012, 2013])
    pid = np.array([1, 2, 1, 3, 4])
    tr = E.fold_train_mask(year, pid, 2011)
    # player 1 appears in 2012: excluded from 2011's training rows
    assert tr.tolist() == [False, False, False, True, True]


def test_tip_is_monotone_and_inverse_is_flat_beyond():
    rng = np.random.default_rng(1)
    g = rng.choice([30, 40, 45, 50, 55, 60, 70], 2000).astype(float)
    y = 0.01 * g + rng.normal(0, 0.05, g.size)
    tip = E.fit_tip(g, y)
    assert tip is not None
    assert all(b >= a for a, b in zip(tip["stat"], tip["stat"][1:]))
    inv = E.tip_inverse(tip, np.array([-10.0, 10.0]))
    assert inv[0] == pytest.approx(min(tip["grade"]))
    assert inv[1] == pytest.approx(max(tip["grade"]))


def test_pava():
    assert E.pava_increasing([1, 3, 2, 4], [1, 1, 1, 1]) == [1, 2.5, 2.5, 4]


def test_etool_equals_consensus_without_a_candidate():
    gc = np.array([45.0, 50.0, 55.0])
    Z = np.array([[np.nan], [np.nan], [np.nan]])
    fit = {"lines": [(0.0, 0.1, True)], "c": [3.0]}
    assert E.etool_apply(gc, Z, fit).tolist() == gc.tolist()
    Z2 = np.array([[1.0], [np.nan], [-1.0]])
    out = E.etool_apply(gc, Z2, fit)
    assert out[1] == 50.0 and out[0] != 45.0


def test_display_rounds_up_to_five():
    assert E.display_grade(50.1) == 55
    assert E.display_grade(50.0) == 50
    assert E.display_grade(19.0) == 20
    assert E.display_grade(None) is None


def test_parse_mph():
    assert E.parse_mph("94-97") == pytest.approx(95.5)
    assert E.parse_mph("98") == 98.0
    assert E.parse_mph(None) is None


def test_zmetric_shrinks_and_reads_only_before_the_board_year():
    rng = np.random.default_rng(3)
    lines = {}
    for pid in range(400):
        talent = rng.normal()
        for s in (2015, 2016, 2017, 2018):
            e = float(rng.integers(150, 500))
            lines[(pid, s, "AA")] = (0.3 + 0.02 * talent + rng.normal(0, 0.03), e, None)
    z = E.ZMetric("t", lines, 100.0)
    k = z.k_at(2018)
    assert k is not None and k > 0
    v = z.asof(5, 2018)                 # reads 2015 to 2017 only
    lines2 = dict(lines)
    lines2[(5, 2018, "AA")] = (9.0, 400.0, None)
    z2 = E.ZMetric("t", lines2, 100.0)
    z2._k[2017] = z.k_at(2017)
    assert z2.asof(5, 2018) == pytest.approx(v, rel=1e-6, abs=1e-9) or abs(z2.asof(5, 2018) - v) < 0.05


def test_within_rho_and_bootstrap_agree():
    rng = np.random.default_rng(4)
    n = 400
    year = rng.choice([2011, 2012, 2013], n)
    pid = np.arange(n)
    x = rng.normal(size=n)
    y = x + rng.normal(size=n)
    r = E.within_rho(x, y, year)
    W = np.ones((3, n))
    assert np.allclose(E.within_rho(x, y, year, W), r)


def test_dry_run_completes_on_fixtures():
    out = E.dry_run()
    assert set(out["tools"]) == set(E.TOOLS)
    assert out["atlas_rows"] > 0
    assert out["tools"]["field"] in ("NO SUB-DRIVER", "NOT PASS (no upper-minors label, gate 5.2)")


def test_bh_q():
    q = E.bh_q([0.01, 0.04, None, 0.5])
    assert q[2] is None and q[0] <= q[1] <= q[3]
