# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The FanGraphs WAR frame, one formula at a time, on synthetic rows (plan W1.1).

Every test here pins one library formula or one measured convention on numbers a
reader can check by hand. The last group reads the eval artifact if it has been
built and asserts the gate numbers are RECORDED (row counts behind every share,
a verdict that agrees with its share), never that they pass: the pitching side
does not clear the gate from disk, and a test that demanded it would be a lie.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import fwar_frame as F

ROOT = Path(__file__).resolve().parent
ARTIFACT = ROOT / "data" / "fwar_replica_eval.json"

#: The 2011 FanGraphs Guts row (weights, scale) and league totals the solved
#: artifact reproduces (league_constants.py): lgwOBA .316, lgR/PA .11233.
W2011 = {"ubb": 0.694, "hbp": 0.726, "1b": 0.890, "2b": 1.270, "3b": 1.611, "hr": 2.086}


# --------------------------------------------------------------------------
# Batting
# --------------------------------------------------------------------------

def test_woba_denominator_excludes_ibb_and_is_not_pa():
    # 100 AB, 10 BB (2 intentional), 1 HBP, 3 SF; 30 H = 20 1B, 6 2B, 1 3B, 3 HR
    num, den = F.woba_parts(bb=10, ibb=2, hbp=1, h=30, d=6, t=1, hr=3, ab=100, sf=3, weights=W2011)
    assert den == 100 + 8 + 3 + 1
    want = 0.694 * 8 + 0.726 * 1 + 0.890 * 20 + 1.270 * 6 + 1.611 * 1 + 2.086 * 3
    assert num == pytest.approx(want)
    assert F.woba(num, den) == pytest.approx(want / 112)
    assert F.woba(0.0, 0.0) is None


def test_wraa_is_the_rate_gap_over_the_scale_times_pa():
    assert F.wraa(0.366, 0.316, 1.264, 600) == pytest.approx(0.05 / 1.264 * 600)
    assert F.wraa(0.316, 0.316, 1.264, 600) == 0.0


def test_wrc_adds_back_league_runs_per_pa():
    assert F.wrc(0.316, 0.316, 1.264, 0.112, 500) == pytest.approx(56.0)


def test_batting_runs_prices_park_and_league_per_stint():
    """A traded hitter: wRAA is linear in events so it needs no split; the park and
    league terms need only each stint's PA."""
    lg_rpa = 0.12
    stints = [(400, 1.10, 0.121), (200, 0.95, 0.118)]
    got = F.batting_runs(10.0, stints, lg_rpa)
    want = (10.0
            + (lg_rpa - 1.10 * lg_rpa) * 400 + (lg_rpa - 0.121) * 400
            + (lg_rpa - 0.95 * lg_rpa) * 200 + (lg_rpa - 0.118) * 200)
    assert got == pytest.approx(want)
    # a hitter in a hitters' park loses runs, one in a pitchers' park gains
    assert F.park_runs(600, lg_rpa, 1.10) < 0 < F.park_runs(600, lg_rpa, 0.95)


def test_implied_pf_inverts_the_park_term():
    lg_rpa, pa, pf, wr, lt = 0.118, 550, 1.063, 7.5, -0.4
    batting = wr + F.park_runs(pa, lg_rpa, pf) + lt
    assert F.implied_pf(batting, wr, lt, lg_rpa, pa) == pytest.approx(pf)
    assert F.implied_pf(batting, wr, lt, lg_rpa, 0) is None


# --------------------------------------------------------------------------
# Baserunning
# --------------------------------------------------------------------------

def test_wsb_reproduces_the_published_2024_ohtani_value():
    """Lane C2 section 4.1: SB 59, CS 4, opportunities 175, runCS -0.405,
    lgwSB 0.007893 -> FanGraphs wBsR 8.799."""
    got = F.wsb(sb=59, cs=4, singles=175, bb=0, hbp=0, ibb=0, rcs=-0.405, lg_wsb=0.007893)
    assert got == pytest.approx(8.799, abs=0.001)


def test_run_cs_is_negative_and_lg_wsb_pools_mlb():
    rcs = F.run_cs(lg_runs=20808, lg_outs=130582)
    assert rcs == pytest.approx(-(2 * 20808 / 130582 + 0.075))
    assert rcs < 0
    rate = F.lg_wsb_rate(3279, 1261, 28000, 14000, 1500, 1100, rcs)
    assert rate == pytest.approx((3279 * 0.2 + 1261 * rcs) / (28000 + 14000 + 1500 - 1100))


def test_baserunning_adds_the_consumed_part():
    assert F.baserunning(1.2, 3.9) == pytest.approx(5.1)


# --------------------------------------------------------------------------
# Positional, league, replacement, RPW
# --------------------------------------------------------------------------

def test_positional_is_innings_over_1458_times_the_ladder():
    assert F.positional({"SS": 1458.0}) == pytest.approx(7.5)
    assert F.positional({"C": 729.0, "1B": 729.0}) == pytest.approx(0.0)
    assert F.positional({}, dh_inn=1458.0) == pytest.approx(-17.5)
    # pitching innings carry no rung; a StatsAPI DH row (innings 0) is ignored in
    # favour of the explicit DH innings
    assert F.positional({"P": 200.0, "DH": 0.0, "LF": 145.8}) == pytest.approx(-0.75)


def test_dh_innings_never_go_negative():
    assert F.dh_innings(1300.0, 1210.0) == pytest.approx(90.0)
    assert F.dh_innings(1200.0, 1210.3) == 0.0


def test_pitcher_batting_credit_zeroes_the_average_pitcher_batter():
    rep = 0.029
    c = F.pitcher_batting_rate(pool_wraa=-720.0, pool_pa=6000.0, replacement_per_pa=rep)
    assert c == pytest.approx(0.12 - 0.029)
    # the average pitcher-batter: wRAA/PA + c + replacement/PA == 0
    assert -720.0 / 6000.0 + c + rep == pytest.approx(0.0)
    assert F.pitcher_batting_rate(0.0, 0.0, rep) is None


def test_league_adjustment_zeroes_the_league_it_is_computed_on():
    runs = [12.0, -4.0, 30.0]
    pas = [600.0, 300.0, 100.0]
    rate = F.league_adjustment_rate(sum(runs), sum(pas))
    adj = [F.league_adjustment([(p, rate)]) for p in pas]
    assert sum(runs) + sum(adj) == pytest.approx(0.0)
    assert F.league_adjustment([(400, 0.004), (200, 0.002)]) == pytest.approx(2.0)
    assert F.league_adjustment_rate(10.0, 0.0) is None


def test_replacement_is_570_per_2430_games_at_the_season_rpw():
    """2011: 2,429 games, RPW 9.4536, lgPA 185,245 (every PA, pitchers batting
    included) -> the feed's 0.029077 runs per PA."""
    assert F.replacement_per_pa(2429, 9.4536, 185245) == pytest.approx(0.029077, abs=5e-7)
    assert F.replacement_runs(600, 2429, 9.4536, 185245) == pytest.approx(600 * 0.0290773, abs=1e-3)
    pos, pit = F.replacement_totals(2430)
    assert (pos, pit) == (pytest.approx(570.0), pytest.approx(430.0))
    pos20, pit20 = F.replacement_totals(898)
    assert pos20 + pit20 == pytest.approx(1000.0 * 898 / 2430)


def test_runs_per_win_closed_form_reproduces_2011():
    assert F.runs_per_win(20808, 43527.33) == pytest.approx(9.4536, abs=1e-4)


def test_hitter_rar_and_war():
    rar = F.hitter_rar(10.0, 1.0, -2.0, 3.0, 2.5, 1.5, 20.0)
    assert rar == pytest.approx(36.0)
    assert F.hitter_war(rar, 9.0) == pytest.approx(4.0)


# --------------------------------------------------------------------------
# Pitchers
# --------------------------------------------------------------------------

def test_fip_reproduces_the_2016_stroman_line():
    """IP 204, HR 21, BB 54, HBP 4, K 166, cFIP 3.147 -> 3.710 (lane C5)."""
    assert F.fip(21, 54, 4, 166, 204.0, 3.147) == pytest.approx(3.710, abs=0.001)
    assert F.fip(0, 0, 0, 0, 0.0, 3.1) is None


def test_iffip_constant_keeps_league_iffip_at_league_era():
    """With IFFB counted as a strikeout the constant moves so the MLB ifFIP still
    equals lgERA: the constant part cancels in RAAP9."""
    lg = dict(lg_hr=5000, lg_bb=15000, lg_hbp=1700, lg_k=36000, lg_ip=43000.0)
    c_plain = F.fip_constant(4.10, **lg)
    c_if = F.fip_constant(4.10, lg_iffb=4700, **lg)
    assert c_if == pytest.approx(c_plain + 2 * 4700 / 43000.0)
    lgfip = F.fip(lg["lg_hr"], lg["lg_bb"], lg["lg_hbp"], lg["lg_k"], lg["lg_ip"], c_if, iffb=4700)
    assert lgfip == pytest.approx(4.10)


def test_fipr9_is_additive_not_multiplicative():
    assert F.fipr9(3.71, 4.52, 4.19) == pytest.approx(3.71 + 0.33)
    assert F.fipr9(3.71, 4.52, 4.19) != pytest.approx(3.71 * 4.52 / 4.19)
    assert F.pfipr9(4.161, 1.01) == pytest.approx(4.12, abs=0.001)
    assert F.raap9(4.56, 4.12) == pytest.approx(0.44)


def test_the_library_worked_example_chain():
    """Stroman 2016 on the WAR-for-pitchers page: AL FIPR9 4.56, pFIPR9 4.12,
    204 IP in 32 games, all starts -> dRPW 9.61 and "WAR" 3.76. The own-league
    FIPR9 inside dRPW is what lands 9.61 (MLB's 4.52 would give 9.57)."""
    d = F.dynamic_rpw(204.0, 32.0, 4.56, 4.12)
    assert d == pytest.approx(9.61, abs=0.005)
    assert F.dynamic_rpw(204.0, 32.0, 4.52, 4.12) == pytest.approx(9.57, abs=0.005)
    w = F.pitcher_war_prime(F.raap9(4.56, 4.12), d, F.replacement_level(32, 32), 204.0)
    assert w == pytest.approx(3.76, abs=0.01)


def test_dynamic_rpw_collapses_to_the_league_value_for_an_average_pitcher():
    lg = 4.40
    assert F.dynamic_rpw(180.0, 30.0, lg, lg) == pytest.approx((lg + 2.0) * 1.5)
    # a better pitcher needs fewer runs per win
    assert F.dynamic_rpw(180.0, 30.0, lg, 3.0) < F.dynamic_rpw(180.0, 30.0, lg, 5.0)


def test_replacement_level_is_continuous_in_start_share():
    assert F.replacement_level(30, 30) == pytest.approx(0.12)
    assert F.replacement_level(0, 60) == pytest.approx(0.03)
    assert F.replacement_level(10, 20) == pytest.approx(0.075)


def test_leverage_levers_the_whole_relief_quantity():
    assert F.leverage_multiplier(1.8) == pytest.approx(1.4)
    assert F.leverage_multiplier(None) == 1.0
    lg = 4.4
    ln = F.role_line(60.0, 60.0, False, lg, lg, lg, 1.8)
    # an exactly average reliever: RAAP9 0, so the line is replacement only, and
    # FanGraphs levers that replacement part too
    assert ln["war0"] == pytest.approx(0.03 * 60.0 / 9.0 * 1.4)
    st = F.role_line(180.0, 30.0, True, lg, lg, lg, 1.8)
    assert st["war0"] == pytest.approx(0.12 * 180.0 / 9.0), "starters are never levered"
    assert F.role_line(0.0, 0.0, False, lg, lg, lg, 1.0)["war0"] == 0.0


def test_blended_line_matches_role_pricing_for_a_pure_role():
    lg = 4.3
    a = F.blended_line(70.0, 65.0, 0.0, lg, lg, 3.9, 1.5)
    b = F.role_line(70.0, 65.0, False, lg, lg, 3.9, 1.5)
    assert a["war0"] == pytest.approx(b["war0"])


def test_warip_pins_the_pitcher_total():
    lines = [[F.role_line(200.0, 32.0, True, 4.4, 4.4, 3.6, None)],
             [F.role_line(65.0, 70.0, False, 4.4, 4.4, 3.2, 1.7)],
             [F.role_line(120.0, 25.0, True, 4.4, 4.4, 5.1, None)]]
    target = 10.0
    w = F.warip(target, sum(ln[0]["war0"] for ln in lines), 385.0)
    total = sum(F.pitcher_war(ln, w)[0] for ln in lines)
    assert total == pytest.approx(target)


def test_pitcher_rar_is_war_times_its_own_dynamic_rpw():
    ln = F.role_line(180.0, 30.0, True, 4.4, 4.4, 3.8, None)
    war, rar = F.pitcher_war([ln], 0.0)
    assert rar == pytest.approx(war * ln["drpw"])


def test_pf_from_fip_minus_inverts_the_fip_minus_formula():
    fipv, lgfip, pf = 3.6, 4.15, 1.04
    fip_minus = 100.0 * (fipv + (fipv - fipv * pf)) / lgfip
    assert F.pf_from_fip_minus(fip_minus, fipv, lgfip) == pytest.approx(pf)
    assert F.pf_from_fip_minus(90.0, 0.0, 4.1) is None


# --------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------

def test_gate_row_counts_and_verdict():
    g = F.gate_row([0.5] * 99 + [1.5])
    assert (g["n"], g["n_within"], g["share_within"], g["verdict"]) == (100, 99, 0.99, "PASS")
    g = F.gate_row([0.5] * 98 + [1.5, -2.0])
    assert g["verdict"] == "FAIL" and g["max"] == 2.0
    assert F.gate_row([])["verdict"] == "NO_ROWS"
    assert F.gate_row([float("nan"), 0.2])["n"] == 1
    assert F.gate_row([1.0])["n_within"] == 1, "exactly 1.0 run is inside the tolerance"


# --------------------------------------------------------------------------
# The artifact records its gate numbers (skip until built)
# --------------------------------------------------------------------------

def _artifact():
    try:
        return json.loads(ARTIFACT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pytest.skip("data/fwar_replica_eval.json not built")


def test_the_artifact_records_every_season_and_component():
    art = _artifact()
    seasons = art["seasons"]
    assert {str(y) for y in range(2011, 2027)} <= set(seasons)
    for s, blk in seasons.items():
        for side, comps in (("hitters", ("wraa", "batting", "wsb", "bsr", "positional",
                                         "league", "replacement", "rar", "war_runs")),
                            ("pitchers", ("fip_runs", "rar", "war_runs"))):
            table = blk[side]["components"]
            for comp in comps:
                g = table[comp]
                for k in ("n", "n_within", "share_within", "mae", "max", "verdict"):
                    assert k in g, f"{s} {side}.{comp} lacks {k}"
                assert 0 <= g["n_within"] <= g["n"]
                if g["n"]:
                    assert (g["verdict"] == "PASS") == (g["share_within"] >= art["gate"]["share"]), (
                        f"{s} {side}.{comp}: verdict disagrees with its own share")


def test_the_artifact_labels_what_it_consumed():
    art = _artifact()
    text = " ".join(art["consumed"]).lower()
    for word in ("ubr", "fielding", "framing", "gmli", "park factor"):
        assert word in text, f"consumed input '{word}' is not labelled"
    assert art["gate"]["tolerance_runs"] == 1.0 and art["gate"]["share"] == 0.99
