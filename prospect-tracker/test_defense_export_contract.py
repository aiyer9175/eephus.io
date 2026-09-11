# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Served-artifact contract for data/defense_leaderboards.json (DEM+).

DEM+ is on the 100 + 10z ruler, so the anchor invariant is an unweighted mean of
100 and a sample sd of 10 over the POOL rows, and every row must reproduce its
own number from the served scale block. No value band: bands on '+' metrics
are banned (an honest 145 must print). Everything below holds by construction.

Skips when the artifact is absent, so the suite never triggers an export.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

import pytest

import dem_plus

ROOT = Path(__file__).parent
DATA = ROOT / "data" / "defense_leaderboards.json"
VERDICTS = {"validated", "provisional", "unvalidated", "deprecated"}

pytestmark = pytest.mark.skipif(
    not DATA.exists(), reason="defense_leaderboards.json not generated")


def _doc() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


def _pool(d):
    return [r for r in d["fielders"] if (r.get("inn") or 0) >= dem_plus.POOL_MIN_INN]


def test_top_level_shape():
    d = _doc()
    for k in ("season", "as_of", "verdict", "frame", "published_fielding", "innings",
              "scale", "team_basis", "pool", "fielders", "teams"):
        assert k in d, f"missing top-level key {k}"
    assert d["verdict"] in VERDICTS
    assert d["scale"]["convention"] == "100 + 10z"
    assert d["scale"]["k_inn"] == dem_plus.K_INN


def test_the_pool_anchors_at_100_with_sd_10():
    rows = _pool(_doc())
    raws = [r["dem_plus_raw"] for r in rows]
    assert len(raws) >= 30
    assert statistics.mean(raws) == pytest.approx(100.0, abs=0.5)
    assert statistics.stdev(raws) == pytest.approx(10.0, abs=0.5)


def test_every_row_reproduces_its_number_from_the_served_scale():
    d = _doc()
    mu, sd = d["scale"]["pool_mean_rate"], d["scale"]["pool_sd_rate"]
    for r in d["fielders"]:
        want = 100.0 + 10.0 * (r["rate_1000_shrunk"] - mu) / sd
        # rate_1000_shrunk is served at 4 dp and mu/sd at 4 dp
        assert r["dem_plus_raw"] == pytest.approx(want, abs=0.1), r["name"]
        assert r["dem_plus"] == int(round(r["dem_plus_raw"])) or abs(
            r["dem_plus"] - r["dem_plus_raw"]) <= 0.51


def test_the_run_columns_sum():
    for r in _doc()["fielders"]:
        assert r["fld_total"] == pytest.approx(r["fld_runs"] + (r.get("frm_runs") or 0.0), abs=0.11)
        if r.get("pos_runs") is not None:
            assert r["def_runs"] == pytest.approx(r["fld_total"] + r["pos_runs"], abs=0.11)


def test_framing_only_on_rows_that_caught():
    for r in _doc()["fielders"]:
        if "frm_runs" in r:
            assert (r.get("pos_inn") or {}).get("C", 0) > 0, r["name"]


def test_framing_disclosure_is_consistent():
    pf = _doc()["published_fielding"]
    assert pf["n_framing_without_c_innings"] == 0
    if pf["framing_available"]:
        assert pf["n_catchers_with_framing"] >= 0.5 * pf["n_catchers_c200"]


def test_board_sorted_and_teams_unique_and_sorted():
    d = _doc()
    raws = [r["dem_plus_raw"] for r in d["fielders"]]
    assert raws == sorted(raws, reverse=True)
    teams = [t["team"] for t in d["teams"]]
    assert len(teams) == len(set(teams))
    assert len(teams) == 30
    tv = [t["team_dem_plus_raw"] for t in d["teams"]]
    assert tv == sorted(tv, reverse=True)


def test_team_dem_plus_matches_its_innings_weighted_fielders():
    d = _doc()
    by: dict = {}
    for r in d["fielders"]:
        by.setdefault(r["team"], []).append(r)
    for t in d["teams"]:
        rows = by.get(t["team"]) or []
        if not t.get("rollup_includes_catchers"):
            rows = [r for r in rows if not (r.get("pos_inn") or {}).get("C")]
        den = sum(r["inn"] for r in rows)
        want = sum(r["dem_plus_raw"] * r["inn"] for r in rows) / den
        assert t["team_dem_plus_raw"] == pytest.approx(want, abs=1.0), t["team"]


def test_qualified_split_partitions_the_board():
    d = _doc()
    q = sum(1 for r in d["fielders"] if r["qualified"])
    assert q == d["pool"]["n_qualified"]
    assert q + d["pool"]["n_provisional"] == len(d["fielders"])
    for r in d["fielders"]:
        assert r["qualified"] == (r["inn"] >= dem_plus.QUALIFY_MIN_INN)


def test_no_war_column_and_so_no_ewar_vintage():
    """ewar_vintage dates an eWAR numerator; this board carries none, and must
    carry the block if and only if a WAR column ever appears."""
    d = _doc()
    has_war = any(k.startswith(("war", "ewar")) for r in d["fielders"] for k in r)
    assert ("ewar_vintage" in d) == has_war


def test_alignment_slots_are_valid_positions():
    for t in _doc()["teams"]:
        pos = [s["pos"] for s in t.get("alignment") or []]
        assert len(pos) == len(set(pos))
        assert set(pos) <= set(dem_plus.DEF_POSITIONS)


def test_no_club_level_framing_while_the_rollup_withholds_it():
    """Until the catch_frame_rate read is recorded no club-level number carries
    framing (dem_plus.TEAM_ROLLUP_FRAMING); each catcher's own row still does."""
    d = _doc()
    if dem_plus.TEAM_ROLLUP_FRAMING:
        pytest.skip("team framing rollup enabled")
    for t in d["teams"]:
        assert "team_frm_runs" not in t
        assert t.get("rollup_includes_catchers") is False
        for s in t.get("alignment") or []:
            assert "frm_runs" not in s
