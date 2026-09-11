# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The FanGraphs WAR frame, one formula at a time, on synthetic rows (plan W1.1).

Every test here pins one library formula or one measured convention on numbers a
reader can check by hand. The last group reads the eval artifact if it has been
built and asserts the gate numbers are RECORDED (row counts behind every share,
a verdict that agrees with its share), never that they pass: with FanGraphs'
IFFB, FIP park factor, pitcher framing and Start-IP the pitching side clears
the gate in some seasons and not others (traded pitchers are priced on season
totals), and a test that demanded it would be a lie.

The last section pins the eWAR NIGHTLY (owner decision D11, tools/build_ewar.py
--nightly): the live season is re-priced on that night's inputs, every completed
season is carried byte for byte, generated_at does not move, the eval is never
rewritten, and the state survives the box restoring the committed file.
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


def test_framing_is_charged_back_to_the_pitcher_per_nine():
    """Convention 9: the framing runs earned on a pitcher's pitches are added
    to his park-adjusted FIPR9, so 3 framing runs over 180 innings cost him
    0.15 runs per nine and, for an average starter, about that many runs of RAR."""
    assert F.framing_charge_per9(3.0, 180.0) == pytest.approx(0.15)
    assert F.framing_charge_per9(-2.0, 60.0) == pytest.approx(-0.3)
    assert F.framing_charge_per9(5.0, 0.0) == 0.0
    lg = 4.4
    base = F.role_line(180.0, 30.0, True, lg, lg, lg, None)
    charged = F.role_line(180.0, 30.0, True, lg, lg, lg + F.framing_charge_per9(3.0, 180.0), None)
    war_b, rar_b = F.pitcher_war([base], 0.0)
    war_c, rar_c = F.pitcher_war([charged], 0.0)
    # 3.0 runs off RAAP9, less the 0.18 the replacement part gains because the
    # charge also lifts his dynamic runs per win (0.12 * 20 * 0.075)
    assert rar_b - rar_c == pytest.approx(3.0 - 0.12 * 20.0 * 0.075, abs=1e-9)


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
    for word in ("ubr", "fielding", "framing", "gmli", "park factor", "iffb",
                 "fangraphs guts fip park factor", "start-ip"):
        assert word in text, f"consumed input '{word}' is not labelled"
    assert art["gate"]["tolerance_runs"] == 1.0 and art["gate"]["share"] == 0.99
    assert art["fangraphs_inputs"]["served"] is False


def test_every_pitcher_line_names_its_inputs_and_every_arm_its_row_count():
    """Owner decision 14a: the pitcher line is priced on FanGraphs' IFFB and FIP
    park factor wherever they are cached, and each season says which inputs it
    actually had. The arms are one input apart, so what each input buys is read
    off the table; every share carries its n."""
    art = _artifact()
    for s, blk in art["seasons"].items():
        p = blk["pitchers"]
        for k in ("arm", "runs_leg", "pf_source", "role_innings", "framing_charge"):
            assert k in p, f"{s}: pitcher line lacks {k}"
        prov = art["inputs"]["fangraphs"][s]
        if prov.get("pitching") and prov.get("park_factors"):
            assert p["arm"] == "iffb_fg_pf_framing_fg_role", s
            assert p["runs_leg"].startswith("ifFIP") and p["pf_source"].startswith("fg_fip")
        else:
            assert p["pf_source"].startswith("fip_minus"), f"{s}: uncached season must fall back"
        for arm, v in blk["pitchers_arms"].items():
            assert v["rar"]["n"] > 0 and "share_within" in v["rar"], (s, arm)


def test_the_catcher_framing_cross_check_is_recorded_where_fangraphs_is_cached():
    """Decision 13: FanGraphs CFraming against the feed's framing residual, the
    number the replica and DEM+ price. Recorded (agreement counts and the worst
    rows), never asserted to pass."""
    art = _artifact()
    for s, blk in art["seasons"].items():
        fc = blk["hitters"].get("framing_crosscheck")
        if not art["inputs"]["fangraphs"][s].get("fielding"):
            assert fc is None
            continue
        for k in ("n_both", "n_within_0_01", "max_abs_diff", "only_in_feed", "only_in_fg"):
            assert k in fc, (s, k)
        assert 0 <= fc["n_within_0_01"] <= fc["n_both"]


def test_the_public_artifact_republishes_nothing_of_fangraphs():
    """The eval ships with the site's accountability artifacts. It carries what
    the replica made of FanGraphs' numbers (shares, gaps, row counts, the sha256
    of each cached response), never FanGraphs' park-factor table, a pitcher's
    applied FanGraphs factor or a catcher's CFraming value."""
    art = _artifact()
    for s, blk in art["seasons"].items():
        fg_pf = (blk["pitchers"].get("park_factor") or {}).get("fg_fip") or {}
        assert "team_pf" not in fg_pf, f"{s}: the Guts FIP table is republished"
        if blk["pitchers"].get("pf_source", "").startswith("fg_fip"):
            assert all(r.get("pf") is None for r in blk["pitchers"]["worst_rows"]), s
        for r in ((blk["hitters"].get("framing_crosscheck") or {}).get("worst") or []):
            assert "fg_cframing" not in r and "abs_diff" in r, s
        for kind, prov in (art["inputs"]["fangraphs"].get(s) or {}).items():
            assert set(prov) <= {"fetched_at", "complete", "n_rows", "raw_sha256"}, (s, kind)


def test_the_park_factor_comparison_is_on_the_artifact():
    """The default line prices the Guts FIP factor (decision 14a); with the other
    three inputs in place the leave-one-out FIP- back-solve clears more seasons.
    Both are listed, so the comparison is read off the artifact."""
    art = _artifact()
    arms = art["pitcher_arms_summary"]
    assert art["pitcher_default_arm"] == "iffb_fg_pf_framing_fg_role"
    for name in ("iffb_fg_pf_framing_fg_role", "iffb_loo_pf_framing_fg_role"):
        for comp in ("rar", "war_runs"):
            v = arms[name][comp]
            assert set(v) == {"pass", "fail"} and not set(v["pass"]) & set(v["fail"])
    default = art["summary"]["pitchers.rar"]
    assert arms["iffb_fg_pf_framing_fg_role"]["rar"] == default, "the default arm is the table"


# --------------------------------------------------------------------------
# The eWAR nightly (owner decision D11): live season only, completed seasons
# frozen byte for byte, generated_at carried, the eval never rewritten, the
# state carried across the box's `git checkout -- .`, stale inputs refused
# --------------------------------------------------------------------------

def _season_block(mid: int, season: int, ew: float) -> dict:
    return {"ew": ew, "bw": ew, "ewp": ew, "bwp": ew, "pe": 1.0, "pb": 1.0, "ps": "fip",
            "ip": 50.0, "tm": ["DET"]}


def _payload(seasons, ew_of=lambda mid, s: 1.0, generated_at="2026-09-03T12:35:09",
             cadence=None) -> dict:
    players = {str(m): {str(s): _season_block(m, s, ew_of(m, s)) for s in seasons}
               for m in (100, 200, 300)}
    meta = {"generated_at": generated_at, "seasons": [min(seasons), max(seasons)],
            "by_season": {str(s): {"n_rows": 3, "replacement_scale": 1.0} for s in seasons},
            "pitching": {"by_season": {str(s): {"n_rows": 3, "n_covered": 3, "ip_total": 150.0,
                                                "ip_covered": 150.0} for s in seasons},
                         "n_rows": 3 * len(seasons)},
            "fielding": {"by_season": {}},
            "rpw_by_season": {str(s): 9.7 for s in seasons}}
    if cadence is not None:
        meta["cadence"] = cadence
    return {"model": "ewar_v2", "generated_at": generated_at,
            "seasons": [min(seasons), max(seasons)], "consumers": "x", "field_key": {},
            "meta": meta, "n_player_seasons": 3 * len(seasons), "players": players}


def _be():
    from tools import build_ewar
    return build_ewar


def _fresh(at="2026-09-11T02:00:00"):
    """Input vintages of a healthy night (stats and standings read that night)."""
    return {"fip_source_at": at, "standings_at": at}


def test_the_nightly_plan_freezes_completed_seasons_and_rebuilds_only_the_live_one():
    import datetime as dt
    B = _be()
    prev = _payload(range(2011, 2027))                  # a hand build of 2026-09-03
    plan = B.nightly_plan(prev, dt.date(2026, 9, 11), range(2011, 2027))
    assert plan["frozen_before"] == list(range(2011, 2026)), "complete when it was built"
    assert plan["rebuild"] == [2026] and plan["live"] == 2026 and plan["freeze_now"] == []
    # the freeze pass: the first nightly on or after November 1 prices the live
    # 2026 once more and freezes it
    nightly = _payload(range(2011, 2027), cadence={"mode": "nightly", "live_season": 2026,
                                                   "frozen_seasons": list(range(2011, 2026))})
    plan = B.nightly_plan(nightly, dt.date(2026, 11, 1), range(2011, 2027))
    assert plan["rebuild"] == [2026] and plan["freeze_now"] == [2026] and plan["live"] is None
    assert plan["frozen_after"] == list(range(2011, 2027))
    frozen = _payload(range(2011, 2027), cadence={"mode": "nightly",
                                                  "frozen_seasons": list(range(2011, 2027))})
    assert B.nightly_plan(frozen, dt.date(2026, 12, 1), range(2011, 2027))["rebuild"] == []
    # a new season appears in the frames: it becomes the live season
    plan = B.nightly_plan(frozen, dt.date(2027, 3, 28), range(2011, 2028))
    assert plan["rebuild"] == [2027] and plan["live"] == 2027


def test_a_hand_build_freezes_only_what_was_complete_the_day_it_was_built():
    """The reviewer's failure: the box restores the committed hand build (built
    2026-09-03) before every nightly, so judging completeness by TODAY froze 2026
    at the September numbers from November 1 on, and a completed season's WAR
    moved backwards overnight. Completeness is judged at the build date."""
    import datetime as dt
    import war_source as ws
    B = _be()
    sept = _payload(range(2011, 2027))
    assert ws.ewar_complete_at_build(sept) == list(range(2011, 2026))
    for day in (dt.date(2026, 10, 31), dt.date(2026, 11, 1), dt.date(2027, 1, 15)):
        plan = B.nightly_plan(sept, day, range(2011, 2027))
        assert plan["rebuild"] == [2026], day
    assert B.nightly_plan(sept, dt.date(2026, 11, 1), range(2011, 2027))["freeze_now"] == [2026]
    # a hand build made AFTER the freeze date priced 2026 final: frozen as built
    nov = _payload(range(2011, 2027), generated_at="2026-11-15T10:00:00")
    assert B.nightly_plan(nov, dt.date(2026, 12, 1), range(2011, 2027))["rebuild"] == []


def test_the_merge_carries_every_frozen_season_byte_for_byte():
    import datetime as dt
    import war_source as ws
    B = _be()
    prev = _payload(range(2011, 2027))
    plan = B.nightly_plan(prev, dt.date(2026, 9, 11), range(2011, 2027))
    live = _payload([2026], ew_of=lambda m, s: 2.5)
    new = B.merge_nightly(prev, {2026: live}, plan, now_iso="2026-09-11T03:00:00")
    for s in range(2011, 2026):
        assert ws.ewar_season_digest(new, s) == ws.ewar_season_digest(prev, s), s
    assert ws.ewar_season_digest(new, 2026) != ws.ewar_season_digest(prev, 2026)
    assert new["generated_at"] == prev["generated_at"], "the frozen series' build does not move"
    cad = new["meta"]["cadence"]
    assert cad["mode"] == "nightly" and cad["live_season"] == 2026
    assert cad["live_built_at"] == new["live_built_at"] == "2026-09-11T03:00:00"
    assert cad["frozen_seasons"] == list(range(2011, 2026))
    assert set(cad["frozen_digests"]) == {str(s) for s in range(2011, 2026)}
    assert B.check_nightly(prev, new, plan) == []
    # a second night on the same frames writes the same bytes but for the stamp
    again = B.merge_nightly(new, {2026: live}, B.nightly_plan(new, dt.date(2026, 9, 12),
                                                                range(2011, 2027)),
                            now_iso="2026-09-12T03:00:00")
    def strip(d):
        cad = {**d["meta"]["cadence"], "live_built_at": None}
        return json.dumps({**d, "live_built_at": None, "meta": {**d["meta"], "cadence": cad}},
                          separators=(",", ":"))
    assert strip(again) == strip(new)


def test_the_nightly_refuses_to_move_a_frozen_season_or_the_label_build():
    import datetime as dt
    B = _be()
    prev = _payload(range(2011, 2027))
    plan = B.nightly_plan(prev, dt.date(2026, 9, 11), range(2011, 2027))
    bad = B.merge_nightly(prev, {2019: _payload([2019], ew_of=lambda m, s: 9.9)},
                          {**plan, "rebuild": [2019]}, now_iso="x")
    assert any("2019" in p for p in B.check_nightly(prev, bad, plan))
    moved = B.merge_nightly(prev, {2026: _payload([2026])}, plan, now_iso="x")
    moved["generated_at"] = "2026-09-11T03:00:00"
    assert any("generated_at" in p for p in B.check_nightly(prev, moved, plan))


def test_the_freshness_assertion_reports_a_missed_night_stale_inputs_and_a_tampered_season():
    import datetime as dt
    import war_source as ws
    B = _be()
    prev = _payload(range(2011, 2027))
    hand = ws.ewar_cadence_status(prev, dt.date(2026, 9, 11))
    assert hand["ok"] is False and "hand-built" in hand["problems"][0]
    plan = B.nightly_plan(prev, dt.date(2026, 9, 11), range(2011, 2027))
    new = B.merge_nightly(prev, {2026: _payload([2026], ew_of=lambda m, s: 2.0)}, plan,
                          now_iso="2026-09-11T03:00:00", frames=_fresh())
    assert ws.ewar_cadence_status(new, dt.date(2026, 9, 11))["ok"] is True
    late = ws.ewar_cadence_status(new, dt.date(2026, 9, 13))
    assert late["ok"] is False and "2026-09-11" in late["problems"][0]
    old = B.merge_nightly(prev, {2026: _payload([2026])}, plan, now_iso="2026-09-11T03:00:00",
                          frames=_fresh("2026-09-08T15:30:00"))
    probs = ws.ewar_cadence_status(old, dt.date(2026, 9, 11))["problems"]
    assert any("hours old" in p and "FIP" in p for p in probs), probs
    blind = B.merge_nightly(prev, {2026: _payload([2026])}, plan, now_iso="2026-09-11T03:00:00",
                            frames={"served_stale": {"pit": {"age_days": 2.0}}})
    probs = ws.ewar_cadence_status(blind, dt.date(2026, 9, 11))["problems"]
    assert any("last-good" in p for p in probs) and any("no vintage" in p for p in probs)
    tampered = json.loads(json.dumps(new))
    tampered["players"]["100"]["2019"]["ew"] = 1.01
    assert any("2019" in p for p in ws.ewar_cadence_status(tampered, dt.date(2026, 9, 11))["problems"])


def test_the_carried_copy_wins_only_when_it_descends_from_the_committed_build():
    import datetime as dt
    B = _be()
    hand = _payload(range(2011, 2027))
    plan = B.nightly_plan(hand, dt.date(2026, 9, 11), range(2011, 2027))
    night = B.merge_nightly(hand, {2026: _payload([2026], ew_of=lambda m, s: 2.0)}, plan,
                            now_iso="2026-09-11T03:00:00", frames=_fresh())
    assert B.choose_base(hand, None)[1] == "tracked"
    assert B.choose_base(hand, night)[:2] == (night, "carried")
    # a new hand build was committed: the carried lineage is over
    rebuilt = _payload(range(2011, 2027), generated_at="2026-09-20T09:00:00")
    base, which, notes = B.choose_base(rebuilt, night)
    assert which == "tracked" and "committed build wins" in notes[0]
    # a damaged carry (a frozen season off its digest) is ignored
    broken = json.loads(json.dumps(night))
    broken["players"]["100"]["2015"]["ew"] = 7.0
    assert B.choose_base(hand, broken)[1] == "tracked"
    # a nightly committed from another machine that is at least as new wins
    later = B.merge_nightly(night, {2026: _payload([2026], ew_of=lambda m, s: 2.2)},
                            B.nightly_plan(night, dt.date(2026, 9, 12), range(2011, 2027)),
                            now_iso="2026-09-12T03:00:00", frames=_fresh("2026-09-12T02:00:00"))
    assert B.choose_base(later, night)[1] == "tracked"
    assert B.choose_base(night, later)[1] == "carried"


def _nightly_env(tmp_path, monkeypatch, live_ew):
    """build_ewar.run_nightly on stubs: the artifact and its carried copy under
    tmp_path, frames with every season, a one-season build whose live eWAR is
    live_ew[0] (mutable, so a test can move it night to night), and that night's
    input vintages. No network, no real build."""
    import pandas as pd
    import ewar
    import war_source as ws
    B = _be()
    out, ev, carry = tmp_path / "ewar.json", tmp_path / "ewar_eval.json", tmp_path / "carry.json"
    monkeypatch.setattr(ewar, "_CACHE", None)   # restored after: the step resets the memo
    monkeypatch.setattr(ewar, "OUT", out)
    monkeypatch.setattr(ewar, "EVAL_OUT", ev)
    monkeypatch.setattr(B, "CARRY_PATH", carry)
    frame = pd.DataFrame({"year_ID": list(range(2011, 2027))})
    monkeypatch.setattr(ws, "stint_frame", lambda side, provider="bwar", allow_stale=True: frame)
    monkeypatch.setattr(ws, "served_stale", lambda: {})
    seen = []

    def fake_build(first, last, shrink=True, **kw):
        seen.append((first, last))
        return {"season": first}
    monkeypatch.setattr(ewar, "build", fake_build)
    monkeypatch.setattr(ewar, "export_payload",
                        lambda model: _payload([model["season"]], ew_of=lambda m, s: live_ew[0]))
    vint = {"at": "2026-09-11T02:00:00"}
    monkeypatch.setattr(B, "_warm_standings", lambda season: vint["at"])   # no network
    monkeypatch.setattr(B, "live_fip_corpus", lambda seasons: (
        {}, {"fip_source_by_season": {str(s): {"at": vint["at"]} for s in seasons}}))
    return B, out, ev, carry, seen, vint


def test_the_nightly_writes_the_artifact_and_its_carry_only_and_never_the_eval(tmp_path, monkeypatch):
    """End to end on stubs: the step reads the artifact, prices one season,
    writes data/ewar.json and its carried copy atomically, and leaves
    data/ewar_eval.json alone."""
    import datetime as dt
    import war_source as ws
    live = [3.0]
    B, out, ev, carry, seen, vint = _nightly_env(tmp_path, monkeypatch, live)
    prev = _payload(range(2011, 2027))
    out.write_text(json.dumps(prev, separators=(",", ":")), encoding="utf-8")
    assert B.run_nightly(write=True, today=dt.date(2026, 9, 11)) == 0
    assert seen == [(2026, 2026)], "only the live season is priced"
    assert not ev.exists(), "the nightly never writes the eval"
    assert carry.read_bytes() == out.read_bytes(), "the state is carried outside git"
    new = json.loads(out.read_text(encoding="utf-8"))
    assert all(ws.ewar_season_digest(new, s) == ws.ewar_season_digest(prev, s)
               for s in range(2011, 2026))
    assert new["players"]["100"]["2026"]["ew"] == 3.0
    assert new["meta"]["cadence"]["frames"]["fip_source_at"] == vint["at"]
    first_bytes = out.read_bytes()
    vint["at"] = "2026-11-02T02:00:00"
    assert B.run_nightly(write=True, today=dt.date(2026, 11, 2)) == 0   # the freeze pass
    frozen_bytes = out.read_bytes()
    assert B.run_nightly(write=True, today=dt.date(2026, 11, 3)) == 0   # nothing to price
    assert out.read_bytes() == frozen_bytes, "a fully frozen window is left byte for byte"
    assert first_bytes != frozen_bytes
    # a missing artifact is refused, never rebuilt from nothing
    out.unlink()
    assert B.run_nightly(write=True, today=dt.date(2026, 9, 11)) == 2


def test_the_box_restores_the_committed_build_every_night_and_nothing_moves_backwards(
        tmp_path, monkeypatch):
    """deploy/nightly-build.sh runs `git checkout -- .` before the pipeline, so
    data/ewar.json is the committed hand build at the start of every night. The
    carried copy keeps the nightly's state, a completed season stays frozen at
    its freeze-pass numbers, and without the copy a restored hand build is
    re-priced, never frozen at its September numbers."""
    import datetime as dt
    live = [3.0]
    B, out, ev, carry, seen, vint = _nightly_env(tmp_path, monkeypatch, live)
    committed = json.dumps(_payload(range(2011, 2027)), separators=(",", ":"))

    def box_night(day, ew):
        out.write_text(committed, encoding="utf-8")          # git checkout -- .
        live[0] = ew
        vint["at"] = f"{day.isoformat()}T02:00:00"
        seen.clear()
        return B.run_nightly(write=True, today=day)

    def ew2026():
        return json.loads(out.read_text(encoding="utf-8"))["players"]["100"]["2026"]["ew"]

    assert box_night(dt.date(2026, 10, 31), 3.0) == 0 and ew2026() == 3.0
    assert box_night(dt.date(2026, 11, 1), 4.0) == 0 and ew2026() == 4.0   # the freeze pass
    nov1 = out.read_bytes()
    assert 2026 in json.loads(nov1)["meta"]["cadence"]["frozen_seasons"]
    assert box_night(dt.date(2026, 11, 2), 5.0) == 0
    assert seen == [] and out.read_bytes() == nov1, "frozen: byte-identical night to night"
    assert box_night(dt.date(2026, 11, 3), 6.0) == 0 and out.read_bytes() == nov1
    # the carry is lost (a rebuilt box): the Sep 3 hand build is re-priced, not
    # frozen at 1.0, and 2026 freezes again on that night's numbers
    carry.unlink()
    assert box_night(dt.date(2026, 11, 4), 4.0) == 0
    assert seen == [(2026, 2026)] and ew2026() == 4.0


def test_a_stale_frame_a_stopped_build_or_older_inputs_refuse_and_serve_the_carried_nightly(
        tmp_path, monkeypatch):
    import datetime as dt
    import ewar
    import war_source as ws
    live = [3.0]
    B, out, ev, carry, seen, vint = _nightly_env(tmp_path, monkeypatch, live)
    committed = json.dumps(_payload(range(2011, 2027)), separators=(",", ":"))
    out.write_text(committed, encoding="utf-8")
    assert B.run_nightly(write=True, today=dt.date(2026, 9, 11)) == 0
    good = carry.read_bytes()

    def restored():
        out.write_text(committed, encoding="utf-8")
        live[0] = 9.0

    # 1. war_daily served from the last-good cache
    restored()
    monkeypatch.setattr(ws, "served_stale", lambda: {"pit": {"age_days": 3.0, "rows": 1}})
    assert B.run_nightly(write=True, today=dt.date(2026, 9, 12)) == 2
    assert out.read_bytes() == good, "the carried nightly is served, not the hand build"
    monkeypatch.setattr(ws, "served_stale", lambda: {})
    # 2. an input loader stops the build (ewar raises SystemExit on a bad data file)
    restored()

    def stops(first, last, shrink=True, **kw):
        raise SystemExit("ewar: cannot read data/savant_oaa.json")
    monkeypatch.setattr(ewar, "build", stops)
    assert B.run_nightly(write=True, today=dt.date(2026, 9, 12)) == 2
    assert out.read_bytes() == good
    monkeypatch.setattr(ewar, "build", lambda first, last, shrink=True, **kw: {"season": first})
    # 3. tonight's stats are older than the ones the carried live season used
    restored()
    vint["at"] = "2026-09-09T02:00:00"
    assert B.run_nightly(write=True, today=dt.date(2026, 9, 12)) == 2
    assert out.read_bytes() == good
    # a healthy night moves on
    vint["at"] = "2026-09-12T02:00:00"
    assert B.run_nightly(write=True, today=dt.date(2026, 9, 12)) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["players"]["100"]["2026"]["ew"] == 9.0


def test_the_live_fip_is_reread_tonight_without_touching_the_shared_corpus(monkeypatch):
    """The live FIP comes from that night's StatsAPI pitching lines, priced by
    fa_projection.build_corpus itself in memory: the shared pickle's path,
    WAR/age join and StatsAPI cache keys are never used for it, and a short
    re-read keeps the pickle's rows and says so."""
    import ewar
    import fa_projection as fp
    B = _be()
    base = {"pit": [{"mlbam": m, "season": s, "fip": 4.0} for m in (1, 2, 3) for s in (2025, 2026)],
            "league": {2025: {"era": 4.1}, 2026: {"era": 4.2}}, "hit": []}
    monkeypatch.setattr(ewar, "_corpus", lambda: base)
    real_cache = fp.CORPUS_CACHE
    seen = {}

    def fake_build_corpus(first_season=None, last_season=None, force=False):
        seen["cache"] = fp.CORPUS_CACHE
        seen["maps"] = fp._war_age_maps()
        seen["fetch"] = fp.fa_sources.fetch_statsapi_season_range
        rows = [{"mlbam": m, "season": 2026, "fip": 3.5} for m in (1, 2, 3, 4)]
        return {"pit": rows[:n_rows[0]], "league": {2026: {"era": 4.3}}, "hit": []}
    n_rows = [4]
    monkeypatch.setattr(fp, "build_corpus", fake_build_corpus)
    merged, vint = B.live_fip_corpus([2026])
    assert seen["cache"] != real_cache and seen["maps"] == ({}, {})
    assert seen["fetch"] is B._fetch_live_pitching
    assert fp.CORPUS_CACHE == real_cache and fp.fa_sources.fetch_statsapi_season_range \
        is not B._fetch_live_pitching, "every patch is undone"
    fips = {(r["mlbam"], r["season"]): r["fip"] for r in merged["pit"]}
    assert fips[(1, 2025)] == 4.0 and fips[(1, 2026)] == 3.5 and (4, 2026) in fips
    assert merged["league"][2026]["era"] == 4.3 and merged["league"][2025]["era"] == 4.1
    assert vint["fip_source_by_season"]["2026"]["source"].startswith("StatsAPI")
    n_rows[0] = 1                                  # a truncated read: 1 row against 3
    merged, vint = B.live_fip_corpus([2026])
    assert {r["fip"] for r in merged["pit"] if r["season"] == 2026} == {4.0}
    assert vint["fip_source_by_season"]["2026"]["source"].startswith("fa_corpus.pkl")


def test_the_vintage_block_reads_the_cadence_from_the_artifact(monkeypatch):
    import datetime as dt
    import ewar
    import war_source as ws
    B = _be()
    prev = _payload(range(2011, 2027))
    plan = B.nightly_plan(prev, dt.date(2026, 9, 11), range(2011, 2027))
    new = B.merge_nightly(prev, {2026: _payload([2026])}, plan, now_iso="2026-09-11T03:00:00")
    monkeypatch.setattr(ws, "ewar_frame_diagnostics", lambda: {})
    monkeypatch.setattr(ewar, "_CACHE", new)
    v = ws.ewar_vintage()
    assert v["rebuilds_on_a_schedule"] is True
    assert v["artifact_generated_at"] == "2026-09-11T03:00:00", "the live numerator's build"
    assert v["label_build_at"] == "2026-09-03T12:35:09", "the frozen series' build"
    assert v["cadence"]["live_season"] == 2026 and v["stale"] is None
    monkeypatch.setattr(ewar, "_CACHE", prev)
    assert ws.ewar_vintage()["rebuilds_on_a_schedule"] is False, "a hand build says so"


def test_the_vintage_stamp_comes_from_the_artifact_the_frames_were_transformed_with(monkeypatch):
    """When a frame has been read, the stamp is the one the transform used (its
    receipt), so a seeded or earlier receipt is reported as it is whatever file
    sits on disk now; the receipt of a nightly artifact names the live build."""
    import datetime as dt
    import ewar
    import war_source as ws
    B = _be()
    prev = _payload(range(2011, 2027))
    plan = B.nightly_plan(prev, dt.date(2026, 9, 11), range(2011, 2027))
    new = B.merge_nightly(prev, {2026: _payload([2026])}, plan, now_iso="2026-09-11T03:00:00")
    monkeypatch.setattr(ewar, "_CACHE", new)
    seeded = {"bat": {"artifact_generated_at": "2026-09-03T12:35:09",
                      "bwar_revised": ws.EWAR_STALE_REVISED_MAX + 1, "covered_player_seasons": 9},
              "pit": {"artifact_generated_at": "2026-09-03T12:35:09", "bwar_revised": 0,
                      "covered_player_seasons": 9}}
    monkeypatch.setattr(ws, "ewar_frame_diagnostics", lambda: seeded)
    v = ws.ewar_vintage(as_of="2026-09-11")
    assert v["stale"] is True and v["artifact_generated_at"] == "2026-09-03T12:35:09"
    assert "--nightly" in v["warning"]
    import pandas as pd
    frame = pd.DataFrame({"mlb_ID": [100], "year_ID": [2026], "WAR": [1.0], "IPouts": [150]})
    monkeypatch.setattr(ws, "_EWAR_FRAME_DIAG", {})
    ws._ewar_frame(frame, "pit", door="stint")
    r = ws._EWAR_FRAME_DIAG["pit"]
    assert r["artifact_generated_at"] == "2026-09-11T03:00:00"
    assert r["artifact_label_build_at"] == "2026-09-03T12:35:09"


def test_the_pipeline_prices_the_live_season_before_any_war_reader():
    """WAR_BASIS_RUNBOOK step B's place. Daily: d8b before d9 (the projections
    export and the eFV regen), d9b2 (player cards) and 9e-pre0 (the boards).
    Monthly: 3-pre before 3d-bis (career WAR), the first WAR reader, so the
    monthly's readers are not a night behind; the chained daily skips d8b."""
    src = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    daily = src[src.index("def run_daily("):src.index("\ndef ", src.index("def run_daily(") + 1)]
    i = daily.index('"d8b. eWAR live-season rebuild')
    for later in ('"d9. Rebuild timeseries', '"d9b2. Re-bake MLB player detail',
                  '"9e-pre0. Refresh team leaderboards'):
        assert i < daily.index(later), later
    block = daily[i:daily.index('"d9. Rebuild timeseries')]
    assert '_ewar_nightly_step(log, "daily")' in block
    assert "chained and _EWAR_NIGHTLY_DONE" in block
    main = src[src.index("\ndef main("):]
    j = main.index('"3-pre. eWAR live-season rebuild')
    assert j < main.index("# --- 3a. Fetch career") < main.index("war_source.career_war_bulk(")
    assert '_ewar_nightly_step(log, "monthly")' in main[j:main.index("# --- 3a. Fetch career")]
    helper = src[src.index("def _ewar_nightly_step("):src.index("def run_daily(")]
    assert "run_nightly(write=True)" in helper and "ewar_cadence_status()" in helper
    assert "except (Exception, SystemExit)" in helper


def test_the_pipeline_step_survives_a_systemexit_and_records_the_heartbeat(monkeypatch):
    """ewar's input loaders raise SystemExit, which `except Exception` does not
    catch; one unreadable data file must not end the night."""
    import logging
    import job_heartbeat
    import run_monthly
    B = _be()
    rows = []
    monkeypatch.setattr(job_heartbeat, "record",
                        lambda job, ok, result="", path=None: rows.append((job, ok, result)))

    def stops(write, today=None):
        raise SystemExit("ewar: cannot read data/positional_fit.json")
    monkeypatch.setattr(B, "run_nightly", stops)
    monkeypatch.setattr(run_monthly, "_EWAR_NIGHTLY_DONE", None)
    assert run_monthly._ewar_nightly_step(logging.getLogger("t"), "daily") == 2
    assert rows and rows[-1][0] == "ewar_nightly" and rows[-1][1] is False
    assert "SystemExit" in rows[-1][2] and run_monthly._EWAR_NIGHTLY_DONE is None
