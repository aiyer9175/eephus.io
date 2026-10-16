# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Fixture tests for SDR_CATCHER_GATE (tools/sdr_catcher_gate.py). Offline; no
real data. The fixture carries nulls on purpose (catchers without a B-Ref row,
missing seasons, a missing variant value) so the dry run exercises every path.
The planted, null and playing-time worlds of the registration's part 6 are
checked on the fixture's design here; the real-design run is the tool's
--simulate."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import sdr_catcher_gate as C  # noqa: E402


def fixture_inputs(seed: int = 11, n: int = 70) -> "C.Inputs":
    rng = np.random.default_rng(seed)
    talent = {9000 + i: rng.normal() for i in range(n)}
    drop, fg, rf, nd, ns = [], [], [], [], []
    for s in range(2017, 2027):
        for pid, t in talent.items():
            if rng.random() < 0.15:
                continue                                    # missing season
            inn = float(rng.uniform(300, 1200)) if s != 2020 else float(rng.uniform(300, 450))
            sdr = (t + rng.normal(scale=0.7)) * inn / 1000
            drop.append({"player_id": pid, "season": s, "innings": inn, "sdr_runs": sdr,
                         "framing_runs": (t + rng.normal()) * inn / 1000,
                         "player_name": f"C{pid}", "primary_position": "C"})
            fg.append({"player_id": pid, "season": s, "Inn": inn,
                       "DRS": (t + rng.normal()) * inn / 1000,
                       "FRP": (t + rng.normal(scale=1.2)) * inn / 1000,
                       "fFRP": (t + rng.normal()) * inn / 1000,
                       "bFRP": 0.0 if s < 2018 else rng.normal() * inn / 1000,
                       "tFRP": rng.normal() * inn / 1000})
            nd.append({"player_id": pid, "season": s,
                       "sdr_runs": np.nan if pid % 13 == 0 else sdr + rng.normal(scale=0.1)})
            ns.append({"player_id": pid, "season": s, "sdr_runs": sdr * 0.9})
            if pid % 7 != 0:                                # some lack a B-Ref row
                rf.append({"player_id": pid, "season": s,
                           "runs_field": rng.normal() * inn / 1000, "inn": inn})
        for k in range(5):                                  # FG-only backups under the floor
            fg.append({"player_id": 8000 + k, "season": s, "Inn": 120.0, "DRS": 0.0, "FRP": 0.0,
                       "fFRP": 0.0, "bFRP": 0.0, "tFRP": 0.0})
    return C.Inputs(drop=pd.DataFrame(drop), fg=pd.DataFrame(fg), rfield=pd.DataFrame(rf),
                    variants={"no_drs": pd.DataFrame(nd), "no_statcast": pd.DataFrame(ns)},
                    meta={"fixture": True})


def test_dry_run_reports_every_block_on_fixture_with_nulls():
    res = C.evaluate(fixture_inputs(), b=40)
    assert res["verdict"] in {"PASS", "PARTIAL", "FAIL"}
    for k in ("E1", "E2"):
        c = res["clauses"][k]
        assert c["n_pairs"] > 0 and c["left_out_missing"] >= 0
        assert "holm" in c and "twin" in c and isinstance(c["passes"], bool)
        assert "zero_comparator" in c and "playing_time" in c
    assert set(res["reported"]) == {"R1_consecutive_pairs", "R2_full_sdr_on_targets",
                                    "R3_total_cell", "R4_without_2020",
                                    "R5_components_on_e1_pairs", "R6_board"}
    assert res["reported"]["R6_board"]["season"] == 2026


def test_e1_pairs_are_two_seasons_apart_and_e2_one():
    rows = C.build_rows(fixture_inputs())
    p1, _ = C.e1_frame(rows)
    assert set(p1.season) <= set(C.E1_SEASONS)
    chk = p1.merge(rows[["player_id", "season", "sdr_rate"]].assign(season=lambda d: d.season - 2),
                   on=["player_id", "season"], suffixes=("", "_chk"))
    assert np.allclose(chk.sdr_rate_n, chk.sdr_rate_chk)
    p2, _ = C.e2_frame(rows, C.target_rows(fixture_inputs()))
    assert set(p2.season) <= set(C.E2_SEASONS)
    assert (p2.inn_t >= C.INN_FLOOR).all()          # the backups under the floor never target


def test_blocking_before_2018_is_not_a_reading():
    rows = C.build_rows(fixture_inputs())
    assert rows[rows.season < 2018].bfrp_rate.isna().all()
    assert rows[rows.season >= 2018].bfrp_rate.notna().any()


def test_twin_permutes_runs_within_season_and_keeps_innings():
    rows = C.build_rows(fixture_inputs())
    t = C.permute_runs(rows, 3)
    for c in C.RUN_COLS:
        a = rows.groupby("season")[c].apply(lambda x: sorted(x.dropna()))
        b = t.groupby("season")[c].apply(lambda x: sorted(x.dropna()))
        assert (a == b).all()
    assert np.allclose(rows.inn, t.inn)
    assert not np.allclose(rows.sdr.to_numpy(), t.sdr.to_numpy())
    # the three run columns move together (one draw)
    i = t.index[t.sdr_nodrs.notna()]
    assert np.allclose(t.loc[i, "sdr_nosc"], t.loc[i, "sdr"] * 0.9)


def test_planted_null_and_playing_time_worlds_behave_on_fixture_design():
    sims = C.run_simulations(fixture_inputs(n=90), b=200)
    assert sims["checks"]["planted_reads_pass"], sims["planted"]
    assert sims["checks"]["null_reads_fail"]
    assert sims["checks"]["playing_time_not_pass"]
    assert sims["checks"]["pt_stops_both_clauses"]


def test_all_zero_candidate_reads_nothing():
    inp = fixture_inputs()
    inp.drop["sdr_runs"] = 0.0
    for v in inp.variants.values():
        v["sdr_runs"] = 0.0
    res = C.evaluate(inp, b=30, with_reported=False)
    assert res["verdict"] == "FAIL"
    assert not res["clauses"]["E1"]["passes"] and not res["clauses"]["E2"]["passes"]


def test_rule_needs_every_condition():
    ok = {"beats_both_at_point": True, "lb_d_above_0": True, "clears_zero": True, "clears_pt": True}
    assert C._e1_ok(ok)
    for k in ok:
        assert not C._e1_ok({**ok, k: False})
    ok2 = {"gap_positive_lb": True, "clears_zero": True, "clears_pt": True}
    assert C._e2_ok(ok2)
    for k in ok2:
        assert not C._e2_ok({**ok2, k: False})
