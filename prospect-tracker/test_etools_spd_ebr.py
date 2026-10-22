# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Tests for etools_spd_ebr.py (docs/tools-2026-10/ETOOLS_AMENDMENT_5.md). Fixtures only:
no database, no cache, no label is read."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

import etools as E
import etools_spd_ebr as S

SRC = Path(S.__file__).read_text(encoding="utf-8")
FIELDS = ["mlbam", "level", "season", "pa", "starts_on_base", "opp_sb", "opp_xb", "opp_dp",
          "sb", "pk", "xb_adv", "xb_oob", "dp", "ebr", "w_n", "w"]


def _row(pid, lv, s, pa, sb=0.0, pk=0.0, adv=0.0, oob=0.0, dp=0.0):
    return [pid, lv, s, pa, 0, 0, 0, 0, sb, pk, adv, oob, dp, sb + pk + adv + oob + dp, 0, 0.0]


def _ebr(extra_rows=(), rel=0.4):
    rows = []
    rng = np.random.default_rng(3)
    for s in (2021, 2022, 2023):
        for i in range(40):
            rows.append(_row(100 + i, "single_a", s, 200 + i, sb=float(rng.normal()), adv=float(rng.normal())))
    rows += list(extra_rows)
    units = {"single_a|2021": {"complete": True}, "single_a|2022": {"complete": True},
             "single_a|2023": {"complete": True}, "aa|2024": {"complete": False}}
    reliability = {k: {"spearman_brown": rel} for k in units}
    return S.EbrMilb(rows=rows, fields=FIELDS, units=units, reliability=reliability)


def test_registered_tools_is_temporary_and_names_both_subdrivers():
    before = set(E.TOOLS)
    with S.registered_tools():
        assert E.TOOLS[S.TOOL]["cands"] == ["sb_rel", "ebr_milb"]
    assert set(E.TOOLS) == before


def test_candidate_leaves_double_plays_out_and_keeps_the_four_components():
    assert S.COMPONENTS == ("sb", "pk", "xb_adv", "xb_oob")
    a = _ebr([_row(1, "single_a", 2023, 300, dp=9.0)])
    b = _ebr([_row(1, "single_a", 2023, 300, dp=-9.0)])
    assert a.asof(1, 2024)[0] == pytest.approx(b.asof(1, 2024)[0])


def test_asof_reads_only_seasons_before_the_board_year():
    m = _ebr([_row(1, "single_a", 2021, 300, sb=3.0), _row(1, "single_a", 2023, 300, sb=-3.0)])
    v22, last22 = m.asof(1, 2022)
    assert last22 == 2021 and v22 > 0
    v24, last24 = m.asof(1, 2024)
    assert last24 == 2023
    assert m.asof(1, 2021) == (None, None)


def test_floor_incomplete_units_and_unreliable_units():
    m = _ebr([_row(2, "single_a", 2023, 149, sb=5.0), _row(3, "aa", 2024, 400, sb=5.0)])
    assert m.asof(2, 2024) == (None, None)            # under 150 PA
    assert m.asof(3, 2025) == (None, None)            # incomplete unit never read
    assert 2024 not in m.complete_seasons()
    low = _ebr(rel=0.05)
    assert all("dropped" in v for v in low.unit_stats.values())
    assert low.asof(100, 2024) == (None, None)


def test_z_within_unit_shrink_and_marcel_weights():
    m = _ebr()
    st = m.unit_stats[("single_a", 2023)]
    assert st["k"] == pytest.approx(st["nbar"] * 0.6 / 0.4)
    zs = [z for pid in range(100, 140) for (s, _lv, z, pa, _k) in m.player[pid] if s == 2023]
    pas = [pa for pid in range(100, 140) for (s, _lv, _z, pa, _k) in m.player[pid] if s == 2023]
    assert np.average(zs, weights=pas) == pytest.approx(0.0, abs=1e-9)
    # one line: value = z x E / (E + k), E = PA (weight 5 of 5)
    pid = 100
    s, _lv, z, pa, k = [x for x in m.player[pid] if x[0] == 2021][0]
    v, _ = m.asof(pid, 2022)
    assert v == pytest.approx(z * pa / (pa + k))


def test_frame_years_are_development_years_with_an_asof_season():
    m = _ebr()
    assert m.frame_years() == (2022, 2023, 2024)
    assert not set(m.frame_years()) & set(E.RESERVED_BOARD_YEARS)
    with pytest.raises(E.GuardError):
        S.guard_years([2021], (2021, 2022))
    with pytest.raises(E.GuardError):
        S.guard_years([2025], (2024,))


def test_bsr_label_window_and_floor():
    bsr = {5: {2023: (2.0, 200.0), 2024: (1.0, 250.0), 2025: (3.0, 300.0), 2026: (9.0, 600.0)}}
    v = S.bsr_label(5, 2022, bsr)
    assert v == pytest.approx(600.0 * 6.0 / 750.0)    # 2023 to 2025, first three after Y
    assert S.bsr_label(5, 2025, {5: {2026: (1.0, 299.0)}}) is None


def test_zero_comparator_is_an_exact_identity_on_fixtures():
    fr = S.fixture_frame(n_players=200)
    zf = S._with_cand(fr, np.where(np.isfinite(fr.cands[S.CAND]), 0.0, np.nan))
    ar = S.arms(zf)
    assert np.nanmax(np.abs(ar["A2"] - ar["A1"])) < 1e-9          # floating point only
    cmp = S.compare(zf, ar, Bn=0)
    assert all(cmp[lb]["A2_vs_A1"]["d"] == 0.0 for lb in S.LABELS_ALL if cmp[lb]["A2_vs_A1"].get("computable"))


def test_rule_needs_all_three_and_counts_computability():
    ok = {"computable": True, "lb95": 0.01}
    no = {"computable": True, "lb95": -0.01}
    cmp = {"mlb": {"A2_vs_A1": ok, "A2_vs_A0": ok}, "um": {"A2_vs_A0": ok}}
    assert S.rule(cmp)["pass"]
    cmp["mlb"]["A2_vs_A1"] = no
    assert not S.rule(cmp)["pass"]
    cmp["mlb"]["A2_vs_A1"] = {"computable": False}
    assert not S.rule(cmp)["computable"]


def test_fixture_read_recovers_a_real_signal_and_rejects_none():
    strong = S.evaluate(S.fixture_frame(signal=1.0, n_players=600), Bn=200, perm=5, log=lambda *_a: None)
    assert strong["verdict"] == "PASS" and strong["planted"]["recovered"]
    assert not strong["null_comparator"]["void"]
    none = S.evaluate(S.fixture_frame(signal=0.0, n_players=600), Bn=200, perm=5, log=lambda *_a: None)
    assert none["verdict"].startswith("NOT PASS")
    assert none["zero_comparator"]["d_A2_vs_A1"]["mlb"] == 0.0


def test_mde_projection_scales_with_players():
    ref = {"mlb": {"sd": 0.004, "players": 400}, "um": {"sd": 0.004, "players": 400}}
    out = S.mde_projection({"mlb": {"players": 100}, "um": {"players": 0}}, ref)
    assert out["mlb"]["mde"] == pytest.approx(S.Z_MDE * 0.004 * 2.0, abs=1e-4)
    assert out["um"]["mde"] is None
    assert S.Z_MDE == pytest.approx(1.6449 + 0.8416)


def test_not_computable_counts_stop_before_any_statistic():
    fr = S.fixture_frame(n_players=40)
    c = S.counts(fr)
    assert not c["computability"]["mlb"]["computable"]


def test_isolation_bans_and_copy():
    assert "backtest.run_backtest(" not in SRC and "run_monthly(" not in SRC
    assert "import requests" not in SRC and "urlopen" not in SRC
    assert "—" not in SRC and "–" not in SRC
    for p in Path(S.ROOT).glob("efv_*.py"):
        assert "etools_spd_ebr" not in p.read_text(encoding="utf-8", errors="replace")
    assert S.OUT_PATH.parent == E.LAB_DIR
    assert math.isclose(S.PLANT_RHO, 0.25) and S.NULL_SEED == 20261025 and S.PLANT_SEED == 20261026
