# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Served-artifact contract for data/defense_leaderboards.json (DEM+).

DEM+ is on the 100 + 10z ruler, so the anchor invariant is an unweighted mean of
100 and a sample sd of 10 over the POOL rows, and every row must reproduce its
own number from the served scale block. No value band: bands on '+' metrics
are banned (an honest 145 must print). Everything below holds by construction.

Two owner decisions (2026-09-11) are pinned on the served file too: club framing
rolls up (decision 17, dem_plus.TEAM_ROLLUP_FRAMING), and Def's positional term
is our ladder pro-rated by innings, with FanGraphs' own as pos_runs_fg (decision
18). A file built before either fails here until defense_export is re-run.

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


def test_the_club_framing_rollup_matches_the_constant_and_the_rows():
    """The served file says what dem_plus.TEAM_ROLLUP_FRAMING says. On (the
    served state since owner decision 17), each club's team_frm_runs is the sum
    of its catcher rows' framing and each catcher slot carries his own; off, no
    club-level number carries framing and no slot does."""
    d = _doc()
    inc = dem_plus.TEAM_ROLLUP_FRAMING
    assert (d.get("team_rollup_framing") or {}).get("included") is inc, (
        "the served file predates the framing flag it should carry: re-run defense_export")
    by: dict = {}
    for r in d["fielders"]:
        by.setdefault(r["team"], []).append(r)
    frm_by_id = {r["mlbam"]: r["frm_runs"] for r in d["fielders"] if r.get("frm_runs") is not None}
    for t in d["teams"]:
        assert t.get("rollup_includes_catchers") is inc, t["team"]
        slots = t.get("alignment") or []
        if not inc:
            assert "team_frm_runs" not in t
            assert all("frm_runs" not in s for s in slots)
            continue
        frm = [r["frm_runs"] for r in by.get(t["team"]) or [] if r.get("frm_runs") is not None]
        if not frm:
            assert t.get("team_frm_runs") is None, t["team"]
        else:
            # rows serve framing at 1 dp; the club sums unrounded values
            assert t["team_frm_runs"] == pytest.approx(sum(frm), abs=0.051 * len(frm) + 0.051), t["team"]
        for s in slots:
            if s["pos"] == "C" and s.get("mlbam") in frm_by_id:
                assert s["frm_runs"] == pytest.approx(frm_by_id[s["mlbam"]], abs=0.051), t["team"]
            elif s["pos"] != "C":
                assert "frm_runs" not in s, (t["team"], s["pos"])


def test_def_is_our_ladder_by_innings_and_fangraphs_rides_beside_it():
    """pos_runs (inside Def) = sum over C to RF of the served ladder rung x the
    row's innings there / the served innings per 650 PA; DH never enters.
    pos_runs_fg is FanGraphs' published positional and sits in no sum."""
    d = _doc()
    pm = d.get("positional") or {}
    assert pm.get("basis") == "our_ladder", (
        "the served file predates the our-ladder Def term: re-run defense_export")
    if not pm.get("available"):
        for r in d["fielders"]:
            assert "pos_runs" not in r and "def_runs" not in r, r["name"]
        return
    assert pm["dh_excluded"] is True and pm["fg_column"] == "pos_runs_fg"
    assert set(pm["values"]) == set(dem_plus.DEF_POSITIONS)
    lad, conv = pm["values"], pm["inn_per_650pa"]
    assert conv > 0
    n_fg = 0
    for r in d["fielders"]:
        want = sum(lad[p] * inn / conv for p, inn in (r.get("pos_inn") or {}).items())
        # pos_inn is served at 1 dp and pos_runs at 1 dp
        assert r["pos_runs"] == pytest.approx(want, abs=0.06), r["name"]
        n_fg += int(r.get("pos_runs_fg") is not None)
    assert n_fg >= 0.9 * len(d["fielders"]), "FanGraphs' positional went missing from the board"


def test_the_served_ladder_is_the_position_fit_artifact():
    """By reference, never a copy: the rungs and the conversion on the board are
    the ones data/positional_fit.json states."""
    d = _doc()
    pm = d.get("positional") or {}
    p = ROOT / "data" / "positional_fit.json"
    if not pm.get("available") or not p.exists():
        pytest.skip("no ladder on the board or no positional_fit.json")
    fit = json.loads(p.read_text(encoding="utf-8"))["fit"]
    assert pm["values"] == {k: fit["ladder"]["values"][k] for k in dem_plus.DEF_POSITIONS}, (
        "positional_fit.json moved since the board was built: re-run defense_export")
    assert pm["inn_per_650pa"] == pytest.approx(fit["inn_per_650pa"])
