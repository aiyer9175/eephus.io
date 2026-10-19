# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""ETOOLS_DVM (owner decision EW3-34): the as-of eTool history and the switch read, built to
docs/farm-attribution-2026-09-25/ETOOLS_DVM_GATE.md. Fixtures only; no outcome is read here.

Pinned:
  * the as-of rule (season S readable from S-10-01) and the look-ahead guard;
  * the stored (K, Bslope) form equals the amendment 2 re-centred eTool for any base grade;
  * the club aggregation mirrors storage's per-tool league pass;
  * the persistence and validity statistics on fixtures, with a planted effect recovered
    and the zero comparator;
  * the runner refuses an unregistered sha and a spent read.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(1, str(ROOT / "tools"))

import etool_history as EH  # noqa: E402
import etools as E  # noqa: E402
import etools_dvm_lab as L  # noqa: E402


def test_season_is_readable_from_the_first_of_october():
    assert EH.readable_season("2024-09-30") == 2023
    assert EH.readable_season("2024-10-01") == 2024
    assert EH.readable_season("2025-01-22") == 2024
    assert EH.readable_season("2026-12-31") == 2026
    assert EH.season_end(2024) == "2024-10-01"


def _fit():
    return EH.Fit("hit", ["k_rw", "ppa_par", "babip_rw"],
                  [(0.65, -0.0065, True), (0.75, -0.0157, True), (0.24, 0.0002, True)],
                  [-82.7, -0.9, -84.1], [0.001, -0.002, 0.0005])


@pytest.mark.parametrize("G", [35.0, 47.5, 60.0])
def test_the_stored_form_is_the_recentred_etool_for_any_base_grade(G):
    fit = _fit()
    z = {"k_rw": 0.21, "ppa_par": 1.02, "babip_rw": None}
    delta = [0.003, -0.01, 0.002]
    params = EH.block_params(fit, z, delta)
    Z = np.array([[0.21, 1.02, np.nan]])
    want, _ = E.etool_centred(np.array([G]), Z, fit.lines, fit.c, delta)
    assert EH.etool_value(G, params) == pytest.approx(float(want[0]), abs=1e-9)


def test_a_player_with_no_subdriver_keeps_the_base_grade():
    assert EH.block_params(_fit(), {"k_rw": None}, [0, 0, 0]) is None
    assert EH.etool_value(52.5, None) == 52.5
    assert EH.etool_value(None, (1.0, 0.1)) is None


def test_the_value_is_clamped_to_the_scale():
    assert EH.etool_value(78.0, (30.0, 0.0)) == 80.0
    assert EH.etool_value(22.0, (-30.0, 0.0)) == 20.0


def test_the_served_reader_swaps_only_the_named_groups_and_power_reads_game_power():
    a = EH.AsOf({"players": {"p": {"t": {"hit": {"2024": [5.0, 0.5]}, "game_pwr": {"2024": [2.0, 0.0]}}}}})
    tools = {"hit": 50.0, "game_pwr": 45.0, "raw_pwr": 60.0, "pwr": 52.5, "speed": 55.0}
    out = a.outlet_tools("p", "2025-03-01", tools, ("hit", "pwr"))
    assert out["hit"] == pytest.approx(30.0)            # 50 x 0.5 + 5
    assert out["pwr"] == pytest.approx(47.0)            # game power's eTool, 45 + 2
    assert out["speed"] == 55.0 and out["game_pwr"] == 45.0
    # a list date before the season's end reads the earlier block (none stored: the grade)
    assert a.outlet_tools("p", "2024-09-01", tools, ("hit",))["hit"] == 50.0
    assert a.outlet_tools("p", "2025-03-01", {"raw_pwr": 60.0, "pwr": 60.0}, ("pwr",))["pwr"] == 60.0


class _Z:
    def __init__(self):
        self.calls = []

    def asof(self, pid, Y):
        self.calls.append(Y)
        return 0.1


def test_the_bank_reads_board_year_s_plus_one_and_refuses_a_future_block():
    bank = EH.SubDrivers.__new__(EH.SubDrivers)
    bank.names = {"hit": ["pbp_swing"]}
    bank.x1_names = {"hit": set(), "pit": set()}
    z = _Z()
    bank.zm = {"hit": {"pbp_swing": z}}
    bank.last_season = 2026
    bank._cache = {}
    assert bank.values(1, "hit", 2023) == {"pbp_swing": 0.1}
    assert z.calls == [2024]
    with pytest.raises(EH.LookAheadError):
        bank.values(1, "hit", 2027)


def test_club_index_mirrors_the_served_per_tool_league_pass():
    import storage as S
    entries = {"AAA": [1.0, 2.0, 3.0], "BBB": [0.0, 0.5, 0.5, 1.0], "CCC": [-1.0, -2.0, 0.0], "DDD": [5.0]}
    got = L.club_index(entries)
    assert got["DDD"] is None                           # fewer than 3 prospects
    vals = {"AAA": (2.0, 3), "BBB": (0.5, 4), "CCC": (-1.0, 3)}
    mu = sum(v for v, _ in vals.values()) / 3
    sd = (sum((v - mu) ** 2 for v, _ in vals.values()) / 3) ** 0.5
    for org, (v, n) in vals.items():
        w = n / (n + 2)
        want = int(round(S._stretch_composite(100 + 10 * (((w * v + (1 - w) * mu) - mu) / sd))))
        assert got[org] == want


def test_persistence_finds_a_persistent_club_effect_and_none_without_one():
    clubs = [f"C{i:02d}" for i in range(30)]
    on = L.read_a(L.fixture_a(clubs=clubs, persistent=1.0), clubs, Bn=200)
    off = L.read_a(L.fixture_a(clubs=clubs, persistent=0.0), clubs, Bn=200)
    assert on["P_C"]["lb95"] > 0.3
    assert off["P_C"]["lb95"] < 0.1
    assert on["n_window_pairs"] == 7


def test_validity_credits_the_gain_that_carries_the_outcome():
    rows = L.fixture_b(signal=0.4)
    st = L.b_stats(rows, L.b_preds(rows), Bn=200, seed=L.SEED)
    assert st["D"]["lb95"] > 0 and st["d_E"]["lb95"] > 0
    assert L.b_rule(st) == (True, True)
    flat = L.fixture_b(signal=0.0)
    st0 = L.b_stats(flat, L.b_preds(flat), Bn=200, seed=L.SEED)
    assert not all(L.b_rule(st0))


def test_the_zero_comparator_cannot_pass_read_b():
    rows = L.fixture_b(signal=0.4)
    rows = dict(rows, gain_E=np.zeros_like(rows["gain_E"]))
    st = L.b_stats(rows, L.b_preds(rows), Bn=200, seed=L.SEED)
    assert not L.b_rule(st)[1]


def test_recovery_b_detects_the_plant_and_not_the_null():
    rows = L.fixture_b(n_players=2000)
    rec = L.recovery_b(rows, R=6, Bn=100, log=lambda *a: None)
    assert rec["PLANT_E"]["rate"] >= 0.8
    assert rec["NULL"]["rate"] <= 0.34 and rec["PLANT_C"]["rate"] <= 0.34


def test_holm():
    assert L.holm([0.01, 0.04, None, 0.03]) == [0.03, 0.06, None, 0.06]


def test_the_runner_refuses_an_unregistered_sha_and_a_spent_read(tmp_path, monkeypatch):
    with pytest.raises(L.GuardError):
        L.read("0000000")
    spent = tmp_path / "read.json"
    spent.write_text(json.dumps({"spent": True, "spent_at": "x"}), encoding="utf-8")
    monkeypatch.setattr(L, "OUT_PATH", spent)
    with pytest.raises(L.GuardError, match="spent"):
        L.read("0000000")


def test_the_gate_is_registered_and_names_the_constants():
    doc = (ROOT / EH.GATE_DOC).read_text(encoding="utf-8")
    assert "Registration status: REGISTERED" in doc
    for s in ("seed 20261031", "-0.05", "B 2000", "R 40", "20261101", "20261102"):
        assert s in doc
    assert L.SEED == 20261031 and L.MARGIN_A == -0.05 and L.B == 2000 and L.REC_R == 40


def test_no_fv_keyed_grouping_in_the_lab():
    src = (ROOT / "tools" / "etools_dvm_lab.py").read_text(encoding="utf-8")
    for bad in ("fv_cell", "by_fv", "fv_bucket", "consensus_fv", "\"fv\""):
        assert bad not in src
