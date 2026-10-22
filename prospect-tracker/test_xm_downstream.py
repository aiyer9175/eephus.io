# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The xM$ downstream lab (docs/xm/XM_DOWNSTREAM.md, task
XM_4_DOWNSTREAM_TESTS): its pure pieces, the registered constants, and the
dry run of the whole reporting path on the fixture."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import xm_downstream_lab as L  # noqa: E402


def test_registered_constants():
    assert L.SEED == 20261019 and L.BOOT_B == 4000
    assert L.SHARES == {3: {1: 0.40, 2: 0.60, 3: 0.80},
                        4: {1: 0.25, 2: 0.40, 3: 0.60, 4: 0.80}}
    assert L.SHARE_OTHER == 0.80
    assert L.PLANT_A_BETA == 0.25 and L.PLANT_B_SLOPE == -2.0
    assert L.PLANT_C == {"a": -0.3, "b": -0.1, "sd": 0.30}
    assert L.PLANT_D_BETA == 0.5 and L.PERM_SHARE_CAP == 0.60
    assert (L.HOLM_FIRST, L.HOLM_SECOND) == (0.025, 0.05)
    assert L.FIRST_XM_WINTER == 2017 and L.MIN_TRAIN_ROWS_XM == 100
    assert L.EXT_MIN_TRAIN == 20 and L.COTS_SERVICE_THROUGH == 2025
    # the artifact lives under data/_labs/, which ships in neither deploy consumer
    assert L.OUT_PATH.relative_to(ROOT).as_posix() == \
        "data/_labs/xm_downstream/xm_downstream_eval.json"
    doc = (ROOT / L.GATE_DOC).read_text(encoding="utf-8")
    assert "Registration status: REGISTERED" in doc


def test_arb_share_and_feature():
    assert L.arb_share(1, False) == 0.40
    assert L.arb_share(3, None) == 0.80
    assert L.arb_share(1, True) == 0.25
    assert L.arb_share(4, True) == 0.80
    assert L.arb_share(4, False) == 0.80          # a step outside the chain
    assert L.arb_share(None, False) == 0.80
    # share x AAV above the minimum, the minimum otherwise, and a missing AAV
    assert L.xm_arb_value(20e6, 0.40, 740_000) == pytest.approx(math.log(8.0))
    assert L.xm_arb_value(1e6, 0.25, 740_000) == pytest.approx(math.log(0.74))
    assert L.xm_arb_value(None, 0.40, 740_000) == pytest.approx(math.log(0.74))


def test_cluster_lb_detects_a_real_gap_and_not_a_tie():
    rng = np.random.default_rng(1)
    base = rng.uniform(1, 2, 400)
    cl = [i // 2 for i in range(400)]
    good = L.cluster_lb(base + 0.5, base, cl, B=500)
    assert good["improvement"] == pytest.approx(0.5) and good["lb05"] > 0.4
    tie = L.cluster_lb(base, base, cl, B=500)
    assert tie["improvement"] == 0.0 and tie["lb05"] == 0.0
    assert good["clusters"] == 200
    assert L.cluster_lb([], [], [])["lb05"] is None


def test_logit_fit_recovers_a_slope():
    rng = np.random.default_rng(2)
    x = rng.normal(0, 1, 4000)
    y = (rng.random(4000) < L.logit_pred([-1.0, -2.0], x)).astype(int)
    w, info = L.logit_fit(x, y)
    assert info["converged"]
    assert w[0] == pytest.approx(-1.0, abs=0.15) and w[1] == pytest.approx(-2.0, abs=0.2)
    p = L.logit_pred(w, x)
    assert L.auc(p, y) > 0.8
    assert L.brier([0.5, 0.5], [0, 1]).tolist() == [0.25, 0.25]


def test_parse_salary_note_skips_options_and_expands_ranges():
    acuna = ("19 :$1M, 20 :$1M, 21 :$5M, 22 :$15M, 23 :$17M, 24 :$17M, 25 :$17M, "
             "26 :$17M, 27 :$17M club option ($10M buyout), 28:$17M club option")
    sal, opt = L.parse_salary_note(acuna)
    assert sal == {2019: 1e6, 2020: 1e6, 2021: 5e6, 2022: 15e6, 2023: 17e6, 2024: 17e6,
                   2025: 17e6, 2026: 17e6}
    assert opt == 2
    julio = ("23 :$4M, 24 :$10M, 25-29 :$18M annually, 30-34 : $90M player option "
             "paying $18M annually")
    sal, opt = L.parse_salary_note(julio)
    assert sal == {2023: 4e6, 2024: 10e6, **{y: 18e6 for y in range(2025, 2030)}}
    assert opt == 1
    assert L.parse_salary_note("signed extension with Atlanta 4/2/19") is None
    assert L.parse_salary_note("earned additional $576,627 from 2023 pre-arbitration "
                               "bonus pool") is None


def test_service_and_extension_row():
    assert L.service_years(["agent: x", "ML service: 6.029"]) == pytest.approx(6 + 29 / 172)
    assert L.service_years(["President, 9/06"]) is None
    player = {"name": "Sean Murphy", "sheet": "atlanta-braves", "facts": ["ML service: 6.029"]}
    contract = {"label": "6 years/$73M (2023-28), plus 2029 club option", "years": 6,
                "total_usd": 73e6, "first_season": 2023, "last_season": 2028,
                "notes": ["signed extension with Atlanta 12/27/22 (avoided arbitration)",
                          "23 :$4M, 24 :$9M, 25 :$15M, 26 :$15M, 27 :$15M, 28 :$15M, "
                          "29 :$15M club option (no buyout)"]}
    row, why = L.extension_row(player, contract, 669221, {2019, 2020, 2021, 2022, 2023,
                                                          2024, 2025})
    assert why == "ok"
    assert row["svc0"] == pytest.approx(3 + 29 / 172, abs=1e-4)
    assert row["F"] == 2026 and row["ctrl"] == 3 and row["n_bought"] == 3
    assert row["bought_aav"] == 15e6 and row["sign_date"] == "2022-12-27"
    assert row["in_season"] is False and row["spread"] is False
    # an in-season signing (8/16/22 for a contract starting 2023) is flagged
    harris = {"name": "Michael Harris II", "facts": ["ML service: 4.000"]}
    hc = {"first_season": 2023, "last_season": 2030, "total_usd": 72e6,
          "notes": ["signed extension with Atlanta 8/16/22",
                    "23 :$5M, 24 :$5M, 25 :$8M, 26 :$8M, 27 :$9M, 28 :$10M, 29 :$10M, "
                    "30 :$12M, 31 :$15M club option ($5M buyout)"]}
    row, _ = L.extension_row(harris, hc, 671739, {2022, 2023, 2024, 2025})
    assert row["F"] == 2028 and row["ctrl"] == 5 and row["in_season"] is True
    assert row["bought_aav"] == pytest.approx((10e6 + 10e6 + 12e6) / 3)
    # no per-year note: the total spread evenly
    spread = dict(hc, notes=["signed extension with Atlanta 3/1/23"])
    row, _ = L.extension_row(harris, spread, 671739, {2022, 2023, 2024, 2025})
    assert row["spread"] is True and row["bought_aav"] == pytest.approx(9e6)
    # six years of service at S0 is not a pre-free-agency extension
    vet = {"name": "Vet", "facts": ["ML service: 9.000"]}
    assert L.extension_row(vet, contract, 1, {2023, 2024, 2025})[1] == "service_6_plus"
    assert L.extension_row({"facts": []}, contract, 1, set())[1] == "no_service"


def test_club_demand_is_min_of_room_and_need_then_z():
    orgs = ("AAA", "BBB", "CCC")
    z, info = L.club_demand({"AAA": 30e6, "BBB": 5e6}, {"AAA": 200e6, "BBB": 200e6,
                                                         "CCC": None}, 220e6, orgs)
    assert info["raw_musd"] == [20.0, 5.0, 0.0] and info["unknown_payroll"] == 1
    assert sum(z) == pytest.approx(0.0, abs=1e-9)
    assert z[0] > z[1] > z[2]
    assert L.club_demand({}, {"AAA": 1e9, "BBB": 1e9, "CCC": 1e9}, 220e6, orgs)[0] == [0.0] * 3


def test_holm_c3_needs_a_rejection_and_a_small_perm_share():
    n = 300
    draws = np.random.default_rng(7).integers(0, n, (2000, n))
    rr = {"N": np.full(n, 0.20), "NX": np.full(n, 0.30), "NX_PERM": np.full(n, 0.21)}
    ll = {"N": np.full(n, 3.3), "NX": np.full(n, 3.2), "NX_PERM": np.full(n, 3.29)}
    M = {"mrr": {"N": 0.20, "NX": 0.30, "NX_PERM": 0.21},
         "log_loss": {"N": -3.3, "NX": -3.2, "NX_PERM": -3.29}}
    out = L.holm_c3(rr, ll, M, draws)
    assert out["pass"] and set(out["holm_rejected"]) == {"mrr", "log_loss"}
    M2 = {"mrr": {"N": 0.20, "NX": 0.30, "NX_PERM": 0.29},
          "log_loss": {"N": -3.3, "NX": -3.2, "NX_PERM": -3.21}}
    assert not L.holm_c3(rr, ll, M2, draws)["pass"]     # the permuted twin does it too
    same = {"N": rr["N"], "NX": rr["N"], "NX_PERM": rr["N"]}
    assert not L.holm_c3(same, {"N": ll["N"], "NX": ll["N"], "NX_PERM": ll["N"]}, M, draws)["pass"]


def test_sign_check_counts_opposite_signs_and_missing_prices():
    cols = ["key", "name", "mlbam", "pop", "club", "ctrl", "ctrl_src", "msur_xm", "msur_fair"]
    doc = {"columns": cols, "players": {
        "1": ["a", "A", 1, "mlb", "NYY", 3, "salary_path", 10, -5],
        "2": ["b", "B", 2, "mlb", "NYY", 3, "salary_path", -10, -5],
        "3": ["c", "C", 3, "mlb", "NYY", 3, "salary_path", 7, 7],
        "4": ["d", "D", 4, "mlb", "NYY", 0, "pending_free_agent", None, None],
        "5": ["e", "E", 5, "mlb", "NYY", 3, "salary_path", 7, 7]}}
    out = L.sign_check(doc, {1: -100.0, 2: -1.0, 3: 0.0})
    assert out["n_joined"] == 3 and out["n_no_tm_price"] == 1
    assert out["n_opposite_sign"] == 1 and out["by_direction"] == {"xm_pos_tm_neg": 1}
    assert out["top_disagreements"][0]["key"] == "a"
    assert out["top_disagreements"][0]["abs_gap"] == 110
    assert L.tm_prices({"players": {"x": {"mlbam": "7", "proj": {"surNpv": 5}},
                                    "y": {"mlbam": "8", "proj": {}}}}) == {7: 5.0}


def test_permute_in_cells_keeps_each_cell_multiset():
    vals = {(i, 2020 + i % 2): float(i) for i in range(20)}
    cell = {k: k[1] for k in vals}
    out = L.permute_in_cells(vals, cell, 5)
    for c in (2020, 2021):
        assert sorted(v for k, v in out.items() if cell[k] == c) == \
            sorted(v for k, v in vals.items() if cell[k] == c)
    assert out != vals


def test_norm_name():
    assert L.norm_name("Ronald Acuña Jr.") == "ronald acuna"
    assert L.norm_name("Michael Harris II") == "michael harris"
    assert L.norm_name("J.D. Martinez") == "jd martinez"


def test_dry_run_writes_every_step_in_the_registered_order(tmp_path):
    out = tmp_path / "xm_downstream_eval.json"
    assert L.main(["--dry-run", "--out", str(out)]) == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["dry_run"] is True and "fixture_note" in doc
    assert doc["order"] == ["engine_and_frames", "A_reproduction", "planted", "A", "B", "C",
                            "D", "E"]
    assert doc["A_reproduction"]["pass"] and doc["A_reproduction"]["max_rel_diff"] == 0.0
    for t in "ABCD":
        assert doc[t]["verdict"] in ("PASS", "FAIL", "VOID")
        assert "planted_ok" in doc["planted"][t]
    # the nulls the fixture carries reach the counts
    assert doc["A_frame"]["rows_no_xm_league_min"] > 0
    assert doc["B_frame"]["by_winter"]["2019"]["accepted"] == 0
    assert doc["C_frame"]["counts"]["drop_no_service"] == 1
    assert doc["C_frame"]["spread_no_per_year_note"] > 0
    assert doc["E"]["n_no_tm_price"] == 1
    assert doc["served_changes"] == "none"
