# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Tests for etools_mfr.py (docs/tools-2026-10/ETOOLS_AMENDMENT_3.md). Fixtures only: no
database, no cache, no label is read."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import etools as E
import etools_mfr as M

SRC = Path(M.__file__).read_text(encoding="utf-8")


def _st():
    rows = []
    # player 1: SS at A+ 2021 and AA 2022, AAA 2023; player 2: C; player 3: CF; player 4: 2B thin
    for pid, pos, season, sport, inn, rr, ar in (
            (1, 6, 2021, 13, 400, 4.0, 0.0), (1, 6, 2022, 12, 500, 3.0, 0.0), (1, 6, 2023, 11, 300, 2.0, 0.0),
            (1, 4, 2022, 12, 100, 1.0, 0.0),
            (2, 2, 2021, 12, 600, 5.0, 0.0), (2, 3, 2021, 12, 100, 1.0, 0.0),
            (3, 8, 2021, 12, 500, -2.0, 1.5), (3, 8, 2022, 11, 450, 1.0, -0.5), (3, 8, 2025, 11, 450, 9.0, 9.0),
            (4, 4, 2021, 14, 40, 1.0, 0.0),
            (5, 6, 2021, 12, 300, -3.0, 0.0), (6, 6, 2021, 12, 250, 1.0, 0.0),
            (7, 8, 2021, 12, 300, 1.0, -1.0), (8, 7, 2021, 12, 300, 0.0, 2.0), (9, 9, 2021, 12, 300, 0.5, 0.5)):
        rows.append({"pid": pid, "season": season, "sport": sport, "pos": pos, "inn": float(inn),
                     "range_runs": rr, "arm_runs": ar})
    k = {t: {p: {"k": 300.0} for p in spec["groups"]} for t, spec in M.TOOLS_MFR.items()}
    return M.MFR(st=pd.DataFrame(rows), factors={11: 1.0, 12: 0.5, 13: 0.25, 14: 0.1, 16: 0.05}, k=k)


def test_frame_years_and_guards():
    assert M.YEARS == (2022, 2023, 2024)
    assert not set(M.YEARS) & set(E.RESERVED_BOARD_YEARS)
    with pytest.raises(E.GuardError):
        M.guard_years([2021])
    with pytest.raises(E.GuardError):
        M.guard_years([2019])
    M.guard_years([2022, 2024])


def test_registered_tools_is_temporary():
    before = set(E.TOOLS)
    with M.registered_tools():
        assert {"field_mfr", "throw_mfr"} <= set(E.TOOLS)
    assert set(E.TOOLS) == before


def test_asof_reads_only_seasons_before_the_board_year():
    m = _st()
    a = m.asof("field_mfr", 2023)
    # player 1 primary SS over 2021-2022: (0.25 x 4 + 0.5 x 3) / (900 + 300) x 1000
    assert a[1]["pos"] == "SS" and a[1]["last_season"] == 2022
    assert a[1]["v"] == pytest.approx(1000 * (0.25 * 4.0 + 0.5 * 3.0) / 1200)
    # the 2025 season of player 3 is never read at board year 2023
    assert a[3]["last_season"] == 2022
    assert all(v["last_season"] < 2023 for v in a.values())


def test_catchers_and_thin_records_carry_no_candidate():
    m = _st()
    a = m.asof("field_mfr", 2022)
    assert 2 not in a                     # primary position C: excluded (EW3-44)
    assert 4 not in a                     # 40 innings: under the 50-inning floor


def test_arm_candidate_is_outfield_only_and_z_within_group():
    m = _st()
    a = m.asof("throw_mfr", 2022)
    assert set(a) <= {3, 7, 8, 9}
    assert 1 not in a and 5 not in a
    cf = [v for v in a.values() if v["group"] == "CF"]
    assert np.mean([v["z"] for v in cf]) == pytest.approx(0.0, abs=1e-9)


def test_um_label_reads_double_a_and_triple_a_from_y_to_2024():
    m = _st()
    u = m.um_label("field_mfr", 2022)
    # player 1: SS at AA 2022 (500) and AAA 2023 (300); A+ 2021 never read
    assert u[1] == pytest.approx(1000 * (0.5 * 3.0 + 1.0 * 2.0) / 800)
    # player 3: CF AAA 2022 only (450 innings); 2025 is after the 2024 cap
    assert u[3] == pytest.approx(1000 * 1.0 / 450)
    assert 5 not in u                     # no line at or after 2022


def test_zero_comparator_is_exactly_consensus():
    fr = M.fixture_frames(n_players=200)["field_mfr"]
    name = "mfr_range"
    zero = M._with_cand(fr, name, np.where(np.isfinite(fr.cands[name]), 0.0, np.nan))
    ev = M.forced_etool(zero, name, Bn=60)
    for lb in M.LABELS:
        assert ev["labels"][lb]["d"] == 0.0


def test_null_permutes_within_year_and_group_and_keeps_missingness():
    fr = M.fixture_frames(n_players=200)["field_mfr"]
    c = fr.cands["mfr_range"]
    nc = M.null_candidate(fr, "mfr_range")
    assert np.array_equal(np.isfinite(c), np.isfinite(nc))
    for Y in np.unique(fr.year):
        for g in set(fr.group.tolist()) - {""}:
            mk = (fr.year == Y) & (fr.group == g) & np.isfinite(c)
            assert sorted(c[mk]) == pytest.approx(sorted(nc[mk]))


def test_planted_candidate_follows_the_real_missingness():
    fr = M.fixture_frames(n_players=200)["throw_mfr"]
    pc = M.planted_candidate(fr, "mfr_arm", M.LABELS)
    assert np.array_equal(np.isfinite(pc), np.isfinite(fr.cands["mfr_arm"]))


def test_dry_run_reports_every_tool_with_a_verdict():
    out = M.dry_run()
    assert set(out) == {"field_mfr", "throw_mfr"}
    for v in out.values():
        assert v["verdict"]


def test_a_strong_fixture_passes_and_its_null_does_not():
    res = M.evaluate({"throw_mfr": M.fixture_frames(n_players=600, signal=1.5)["throw_mfr"]},
                     Bn=200, perm=20, log=lambda *_a: None)
    v = res["throw_mfr"]
    assert v["verdict"] == "PASS"
    assert v["null_comparator"]["etool"]["verdict"] != "PASS"


def test_run_refuses_an_unregistered_sha(monkeypatch, tmp_path):
    monkeypatch.setattr(M, "OUT_PATH", tmp_path / "reads.json")
    with pytest.raises(E.GuardError):
        M.run("0000000")


def test_run_refuses_when_spent(monkeypatch, tmp_path):
    p = tmp_path / "reads.json"
    p.write_text('{"spent": true, "spent_at": "x"}', encoding="utf-8")
    monkeypatch.setattr(M, "OUT_PATH", p)
    with pytest.raises(E.GuardError):
        M.run("e1c13320")


def test_no_banned_calls_and_lab_output():
    for bad in ("run_backtest(", "run_monthly", "build_site", "requests.get", "urlopen"):
        assert bad not in SRC.split('"""', 2)[2]
    assert "_labs" in M.OUT_PATH.parts
