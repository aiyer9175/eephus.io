# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eWAR's pitching bases S2b and R2 (pitch_basis.py, tools/pitch_basis_build.py,
the part 11.3 columns of tools/build_swar.py), on fixtures.

The invariants of docs/ebr-2026-09-30/EBR_GATE.md part 11.3.1:
  (1) every K infinite gives S2b's Delta = S2's Delta on every row;
  (2) S2b's Delta sums to 0 per season within 1e-9 wins under both home-run
      variants (and R2's Delta too, 11.2.8);
  (3) a nopp row carries 0;
  (4) the runner terms net to zero, so a season's RA* sums to its R;
  (5) a build leaves data/ewar.json untouched (test_swar.py's invariant 8 runs
      the same build, part 11.3 included).
Plus the runner reading of 11.3.3 on a hand-walked half-inning, the term
arithmetic, the constants' fit rule and their frozen log. Nothing here reads
real data, and nothing relates a term to any next-season quantity.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import pitch_basis as PB
import swar

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import build_swar as B  # noqa: E402
import pitch_basis_fit as FIT  # noqa: E402
from test_swar import PITCHERS, SEASON, FixtureInputs  # noqa: E402

W = {"ubb": 0.69, "hbp": 0.72, "1b": 0.88, "2b": 1.25, "3b": 1.58, "hr": 2.03}


def _build(k_consts=None):
    return B.build([SEASON], inp=FixtureInputs(), out_path=None, log=lambda *a: None, k_consts=k_consts)


@pytest.fixture(scope="module")
def built():
    return _build()


# --------------------------------------------------------------------------
# the term arithmetic
# --------------------------------------------------------------------------

def test_contact_count_value_and_denominator():
    ln = PB.PitchLine(mlbam=1, ip=180, ab=650, h=150, doub=30, trip=3, hr=20, bb=50, ibb=5,
                      hbp=6, sf=5, so=200, r=70)
    assert PB.contact_count(ln) == 650 - 200 + 5
    assert PB.singles(ln) == 150 - 30 - 3 - 20
    assert PB.contact_value(ln, W) == pytest.approx(0.88 * 97 + 1.25 * 30 + 1.58 * 3 + 2.03 * 20)
    assert PB.woba_denominator(ln) == 650 + 50 - 5 + 5 + 6
    assert PB.runners_allowed(ln) == 150 + 50 + 6 - 20
    assert PB.contact_count(PB.PitchLine(mlbam=2, ab=3, so=5)) == 0.0


def test_the_three_terms_and_the_shrink():
    a = PB.PitchLine(mlbam=1, ip=180, ab=650, h=150, doub=30, trip=3, hr=20, bb=50, ibb=5, hbp=6, sf=5, so=200, r=70)
    b = PB.PitchLine(mlbam=2, ip=60, ab=220, h=45, doub=9, trip=1, hr=5, bb=20, ibb=1, hbp=2, sf=2, so=70, r=22)
    lg = PB.league([a, b], W)
    assert lg.lc == pytest.approx((PB.contact_value(a, W) + PB.contact_value(b, W))
                                  / (PB.contact_count(a) + PB.contact_count(b)))
    x = PB.savant_gap_runs(0.310, 0.300, PB.woba_denominator(a), 1.2)
    assert x == pytest.approx(0.010 * PB.woba_denominator(a) / 1.2)
    assert PB.savant_gap_runs(None, 0.3, 100, 1.2) == 0.0
    t = PB.terms(a, W, lg, 1.2, hr_count=a.hr, x_runs=x, fld_share=1.5, ra_star_value=68.0)
    # contact quality is expected contact runs less the home-run runs the arm carries
    assert t["cq"] == pytest.approx(t["xc"] - t["hstar"])
    assert t["xc"] == pytest.approx(PB.actual_contact_runs(a, W, lg, 1.2) + x)
    assert t["bab"] == pytest.approx(-x + 1.5)
    assert t["lob"] == pytest.approx(68.0 - PB.events_runs(a, W, lg, 1.2))
    # shrink toward a zero prior; an unset K (infinite) gives 0
    assert PB.shrink(10.0, 300.0, 100.0) == pytest.approx(7.5)
    assert PB.shrink(10.0, 300.0, None) == 0.0 and PB.shrink(10.0, 0.0, 5.0) == 0.0
    assert PB.blend_runs(t) == 0.0
    g = PB.blend_runs(t, 1191.0, 5981.0, 1893.0)
    assert g == pytest.approx(PB.shrink(t["cq"], t["c"], 1191.0) + PB.shrink(t["bab"], t["c"], 5981.0)
                              + PB.shrink(t["lob"], t["n"], 1893.0))
    assert PB.dfip_blend(0.10, g, 180.0) == pytest.approx(0.10 + 9.0 * g / 180.0)
    assert PB.dfip_blend(0.10, g, 0.0) == 0.0


def test_ra_star_ra9_star_and_the_club_share():
    assert PB.ra_star(10, bqs=2, e_bq=1.1, irs=1, e_ir=0.7) == pytest.approx(10 - 2 + 1.1 + 1 - 0.7)
    assert PB.ra9_star(45.0, 1.05, 700, 3.0, 180.0) == pytest.approx(9 * (45.0 / 1.05 + 3.0) / 180.0)
    assert PB.ra9_star(45.0, 1.0, 700, 3.0, 0.0) is None
    club = PB.club_runs({1: 10.0, 2: -4.0}, {1: {"A": 900.0, "B": 300.0}, 2: {"B": 500.0}})
    assert club == pytest.approx({"A": 7.5, "B": 2.5 - 4.0})
    shares = PB.pitcher_shares({7: 400.0, 8: 100.0}, {7: {"A": 60.0, "B": 40.0}, 8: {}})
    assert shares[7] == pytest.approx({"A": 240.0, "B": 160.0}) and shares[8] == {}
    assert PB.defense_share(shares[7], {"A": 6.0, "B": -2.0}, {"A": 6000.0, "B": 6000.0}) == pytest.approx(
        240.0 * 6.0 / 6000.0 + 160.0 * -2.0 / 6000.0)
    out = PB.repin({1: 0.4, 2: -0.1, 3: 0.9}, {1: 100.0, 2: 50.0, 3: 2.0}, out_rule=[3])
    assert out[3] == 0.0 and out[1] + out[2] == pytest.approx(0.0, abs=1e-12)


# --------------------------------------------------------------------------
# the runner reading of part 11.3.3, on a hand-walked half-inning
# --------------------------------------------------------------------------

P = {(1, 1): 0.25, (2, 1): 0.40, (3, 1): 0.65, (2, 2): 0.22, (3, 2): 0.29, (1, 0): 0.38}


def _half():
    """p1: single (A), walk (B); p2 enters with A on 2B, B on 1B, one out:
    double (C) scores A, B to 3B; p3 enters with B on 3B, C on 2B, one out:
    sac fly scores B, then a strikeout."""
    return [
        PB.Play(ab=0, pitcher=11, outs=0, bases=(None, None, None), batter=101, reached=True),
        PB.Play(ab=1, pitcher=11, outs=0, bases=(101, None, None), batter=102, reached=False),
        PB.Play(ab=2, pitcher=11, outs=1, bases=(101, None, None), batter=103, reached=True),
        PB.Play(ab=3, pitcher=12, outs=1, bases=(103, 101, None), batter=104, reached=True, scorers=(101,)),
        PB.Play(ab=4, pitcher=13, outs=1, bases=(None, 104, 103), batter=105, reached=False, scorers=(103,)),
        PB.Play(ab=5, pitcher=13, outs=2, bases=(None, 104, None), batter=106, reached=False),
    ]


def test_the_runner_terms_follow_each_runner_and_net_to_zero():
    acc: dict = {}
    PB.half_runner_terms(_half(), P, acc)
    # p1 left A (2B) and B (1B) with one out; both scored after he left
    assert acc[11] == pytest.approx({"ir": 0, "irs": 0, "bq": 2, "bqs": 2, "e_ir": 0, "e_bq": 0.40 + 0.25})
    # p2 inherited both, A scored on his watch; he left B (3B) and his own C (2B)
    assert acc[12] == pytest.approx({"ir": 2, "irs": 1, "bq": 2, "bqs": 0, "e_ir": 0.65, "e_bq": 0.65 + 0.40})
    # p3 inherited B and C; B scored on his watch
    assert acc[13] == pytest.approx({"ir": 2, "irs": 1, "bq": 0, "bqs": 0, "e_ir": 1.05, "e_bq": 0})
    gap = PB.accounting_gap(acc)
    assert gap["e_bq_minus_e_ir"] == pytest.approx(0.0, abs=1e-12) and gap["irs_minus_bqs"] == 0
    # RA* = R - BQS + E_BQ + (IRS - E_IR) sums to the runs charged (2, both to p1)
    r = {11: 2.0, 12: 0.0, 13: 0.0}
    tot = sum(PB.ra_star(r[j], acc[j]["bqs"], acc[j]["e_bq"], acc[j]["irs"], acc[j]["e_ir"]) for j in r)
    assert tot == pytest.approx(2.0)
    # the middle pitcher is credited E at his exit minus E at his entry on the runner he handed on
    assert PB.ra_star(0, acc[12]["bqs"], acc[12]["e_bq"], acc[12]["irs"], acc[12]["e_ir"]) == pytest.approx(
        1.0 + (0.65 + 0.40) - 0.65)


def test_a_pinch_runner_takes_the_replaced_runners_owner_and_a_placed_runner_the_first_pitcher():
    plays = [
        PB.Play(ab=0, pitcher=21, outs=0, bases=(None, 900, None), batter=201, reached=True),
        PB.Play(ab=1, pitcher=21, outs=0, bases=(201, 900, None), batter=202, reached=False),
        PB.Play(ab=2, pitcher=22, outs=1, bases=(301, 900, None), batter=203, reached=False, scorers=(301, 900)),
    ]
    acc: dict = {}
    c = PB.half_runner_terms(plays, P, acc, subs={301: 201})
    assert c["missing_owner"] == 1                      # the placed runner 900
    assert acc[21]["bq"] == 2 and acc[21]["bqs"] == 2   # 301 (for 201) and 900 both his
    assert acc[22]["ir"] == 2 and acc[22]["irs"] == 2
    assert PB.accounting_gap(acc)["irs_minus_bqs"] == 0


def test_the_p_table_is_the_share_that_scored():
    t = PB.p_table([(1, 0, True), (1, 0, False), (1, 0, False), (3, 2, True)])
    assert t == {(1, 0): pytest.approx(1 / 3), (3, 2): 1.0}


# --------------------------------------------------------------------------
# the build on fixtures (invariants 1 to 3 and the preview columns)
# --------------------------------------------------------------------------

def _pitchers(payload):
    return payload["seasons"][str(SEASON)]["pitchers"]


def test_invariant_1_every_k_infinite_gives_s2bs_delta_equal_to_s2s():
    out = _build(k_consts=(None, None, None))
    for x in _pitchers(out):
        for v in swar.HR_VARIANTS:
            assert x["parts"]["pb_" + v]["delta"] == pytest.approx(x["parts"][v]["delta"], abs=2e-6)


def test_invariants_2_and_3_zero_sum_and_nopp(built):
    rows = _pitchers(built)
    for key in [PB.BLEND_PREFIX + v for v in swar.HR_VARIANTS] + [PB.REALIZED_KEY]:
        assert abs(built["seasons"][str(SEASON)]["checks"]["pitch_basis"]["zero_sum"][key]) <= 1e-9
        assert sum(x["parts"][key]["delta"] for x in rows) == pytest.approx(0.0, abs=1e-5)
    nopp = [x for x in rows if x["nopp"]]
    assert nopp and all(x["parts"][k]["delta"] == 0.0 for x in nopp
                        for k in [PB.BLEND_PREFIX + v for v in swar.HR_VARIANTS] + [PB.REALIZED_KEY])


def test_the_blend_moves_rows_once_the_constants_are_set(built):
    rows = [x for x in _pitchers(built) if not x["nopp"]]
    moved = [x for x in rows for v in swar.HR_VARIANTS
             if abs(x["parts"]["pb_" + v]["delta"] - x["parts"][v]["delta"]) > 1e-6]
    assert moved
    for x in rows:
        t = x["parts"]["pb_hr_fwar"]
        assert t["g"] == pytest.approx(PB.blend_runs(t, *PB.constants()), abs=1e-5)
        assert x["parts"]["pb_hr_fwar"]["test"] == pytest.approx(x["fwar"] + x["parts"]["pb_hr_fwar"]["delta"], abs=2e-6)
        assert x["parts"]["realized"]["value"] == pytest.approx(x["fwar"] + x["parts"]["realized"]["delta"], abs=2e-6)


def test_without_a_runner_record_ra_star_is_r_and_ra9_star_is_set(built):
    blk = built["seasons"][str(SEASON)]
    assert blk["census"]["pb_runner_record"] == 0
    stats = {p[0]: p for p in PITCHERS}
    for x in _pitchers(built):
        assert x["runner_terms"] is None
        if x["nopp"]:
            assert x["ra9_star"] is None
            continue
        assert x["ra_star"] == pytest.approx(round(stats[x["mlbam"]][3] * 0.48 + stats[x["mlbam"]][8] * 0.5))
        assert x["ra9_star"] is not None
    assert built["pitch_basis"]["constants"] == {"k_cq": PB.K_CQ, "k_bab": PB.K_BAB, "k_lob": PB.K_LOB}
    assert built["schema"] == swar.SWAR_VERSION == "swar/2"


def test_a_build_without_frozen_constants_stops(monkeypatch):
    monkeypatch.setattr(PB, "K_LOB", None)
    with pytest.raises(B.BuildStop):
        B.build([SEASON], inp=FixtureInputs(), out_path=None, log=lambda *a: None)


# --------------------------------------------------------------------------
# the constants (part 11.3.2)
# --------------------------------------------------------------------------

def test_the_constants_are_frozen_with_their_fit_log():
    assert (PB.K_CQ, PB.K_BAB, PB.K_LOB) == (1191.0, 5981.0, 1893.0)
    log = PB.K_FIT_LOG
    assert log["fit_seasons"] == [2016, 2017, 2018] and log["task"] == "EWAR_PITCH_BASIS"
    assert {log[t]["k"] for t in ("cq", "bab", "lob")} == {1191.0, 5981.0, 1893.0}
    for t in ("cq", "bab", "lob"):
        r, hm = log[t]["r"], log[t]["hm"]
        # r and hm are logged rounded, so the rule reproduces k to within 0.5 percent
        assert log[t]["k"] == pytest.approx(hm * (1 - r) / r, rel=5e-3)


def test_the_fit_reads_the_three_terms_only_and_reproduces_the_rule():
    rows = {}
    for y in (2016, 2017, 2018, 2019):
        rows[y] = {}
        for i in range(60):
            c, n = 300.0 + i, 120.0 + i
            rows[y][i] = {"ip": 60.0 + i, "c": c, "n": n,
                          "cq": c * (0.01 * (i % 7) + 0.001 * y % 3),
                          "bab": c * 0.002 * ((i * y) % 5), "lob": n * 0.01 * (i % 3)}
        rows[y][999] = {"ip": 20.0, "c": 50.0, "n": 20.0, "cq": 1.0, "bab": 1.0, "lob": 1.0}
    out = FIT.fit(rows)
    assert set(out) == {"cq", "bab", "lob"}
    for t, res in out.items():
        assert res["n_pairs"] == 180 and res["n_players"] == 60
        assert 0.05 <= res["r"] <= 0.95
        assert res["k"] == float(round(res["hm"] * (1 - res["r"]) / res["r"]))
    src = (ROOT / "tools" / "pitch_basis_fit.py").read_text(encoding="utf-8")
    for banned in ("fwar\"]", "\"test\"", "ra9_star", "\"delta\""):
        assert banned not in src
    payload = {"seasons": {"2016": {"pitchers": [{"mlbam": 1, "ip": 70.0, "fwar": 2.0,
                                                  "parts": {"pb_hr_fwar": {"cq": 1.0, "bab": 2.0, "lob": 3.0,
                                                                           "c": 300.0, "n": 100.0,
                                                                           "test": 9.9, "delta": 9.9}}}]}}}
    assert FIT.term_rows(payload) == {2016: {1: {"ip": 70.0, "cq": 1.0, "bab": 2.0, "lob": 3.0,
                                                 "c": 300.0, "n": 100.0}}}


def test_the_skill_core_relates_no_season_to_another():
    for path in (ROOT / "pitch_basis.py", ROOT / "tools" / "pitch_basis_build.py"):
        src = path.read_text(encoding="utf-8")
        assert "season + 1" not in src and "y + 1" not in src and "fg_leaderboards" not in src
    assert json.loads(json.dumps(PB.K_FIT_LOG)) == PB.K_FIT_LOG
