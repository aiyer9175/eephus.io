# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""salary_path.py, the control-window salary path (ask C, 2026-09-16).

Sixteen pure tests. Every input is built inline, the raise estimator is
injected, and nothing here reads an artifact, so these fail on a rule change
rather than on a nightly regen.

They pin the rules the whole change turns on:
  * a contracted season is never re-priced (rules 1 and its second lock);
  * class closure derives K as max(3 or 4 by super-two, the LAST OBSERVED
    class) and never runs off an unpriced grid step;
  * the tender cliff is backward induction over the CONTINUATION value, on
    ARBITRATION seasons only;
  * the salary band is named for the SURPLUS it carries and is ordered
    ascending, so a low salary reads as a high surplus and not the reverse.
"""
from __future__ import annotations

import pytest

import salary_path as sp

FIRST, H = 2027, 5
LM = dict(sp.LEAGUE_MIN_CURATED)


def _raise(prior_usd, cls, season, s2, lm_usd):
    """A deterministic stand-in for the board's banded estimator: a flat 1.6x
    raise, banded 22% + 8 points a rung, floored at the league minimum. The
    SHAPE is what these tests pin; the fitted multipliers are the board's and
    are gated by GATE A, not here."""
    pred = max(float(prior_usd) * 1.6, float(lm_usd))
    spread = 0.22 + 0.08 * (cls - 1)
    return int(pred), int(pred * (1 - spread)), int(pred * (1 + spread))


def _steps(*rows):
    """(season, usd, tok) triples -> board-row steps."""
    return [{"season": s, "usd": u, "lo": u, "hi": u, "tok": tok} for s, u, tok in rows]


def _row(steps):
    return {"m": 1, "steps": steps}


def _path(**kw):
    kw.setdefault("first_season", FIRST)
    kw.setdefault("horizon", H)
    kw.setdefault("league_min", LM)
    kw.setdefault("raise_fn", _raise)
    kw.setdefault("mode", "full")
    return sp.salary_path(1, **kw)


def _srcs(p):
    return [c["src"] for c in p["seasons"]]


# --------------------------------------------------------------------- 1-2
def test_1_a_contracted_season_is_never_re_priced():
    """RULE 1 IS ABSOLUTE. This is test_gate_c_never_overwrites_a_real_contract
    moved from the ROW to the SEASON, and it is the single invariant the whole
    change turns on."""
    p = _path(contract={"salary_by_year": {2027: 9_500_000}, "signed_through": 2027},
              board_row=_row(_steps((2027, 4_000_000, "ARB 2"), (2028, 6_000_000, "ARB 3"))))
    assert p["seasons"][0]["src"] == "contract"
    assert p["seasons"][0]["usd"] == 9_500_000
    assert p["seasons"][1]["src"] == "arb_ladder"


def test_2_the_ladder_takes_over_the_season_after_thru():
    p = _path(contract={"salary_by_year": {2026: 1_000_000}, "signed_through": 2026},
              board_row=_row(_steps((2027, 916_000, "ARB 1"), (2028, 1_530_000, "ARB 2"))))
    assert _srcs(p)[:2] == ["arb_ladder", "arb_ladder"]
    assert p["src_mix"] == "arb_ladder+class_closure"   # ARB 2 in 2028 closes to ARB 3
    assert _path(mode="ladder",
                 contract={"salary_by_year": {2026: 1_000_000}, "signed_through": 2026},
                 board_row=_row(_steps((2027, 916_000, "ARB 1"),
                                       (2028, 1_530_000, "ARB 2"))))["src_mix"] == "arb_ladder"


# --------------------------------------------------------------------- 3-7
def test_3_closure_extends_arb_1_to_arb_2_and_arb_3_then_stops():
    p = _path(board_row=_row(_steps((2028, 1_000_000, "ARB 1"))))
    got = [(c["season"], c["tok"], c["src"]) for c in p["seasons"] if c["usd"]]
    assert got == [(2028, "ARB 1", "arb_ladder"),
                   (2029, "ARB 2", "class_closure"),
                   (2030, "ARB 3", "class_closure")]
    assert p["last_controlled"] == 2030


def test_4_closure_extends_to_arb_4_for_a_super_two_row():
    p = _path(board_row=_row(_steps((2027, 1_000_000, "ARB 1 (S2)"))))
    toks = [c["tok"] for c in p["seasons"] if c["usd"]]
    assert toks == ["ARB 1 (S2)", "ARB 2 (S2)", "ARB 3 (S2)", "ARB 4 (S2)"]


def test_5_a_prearb_only_grid_is_not_extended():
    """Inventing an arbitration START year without service time is the shape of
    a prior failure in this tree. 266 projection veterans are in this state."""
    p = _path(board_row=_row(_steps((2027, 780_000, "PRE-ARB"), (2028, 780_000, "PRE-ARB"))))
    assert [c["src"] for c in p["seasons"] if c["usd"]] == ["arb_ladder"] * 2
    assert p["truncated"] == "prearb_grid"
    assert p["last_controlled"] == 2028


def test_6_an_arb_4_row_with_no_s2_marker_gains_nothing_and_never_a_negative():
    """R3. Four served rows end on ARB 4 with no (S2). K = 4 if s2 else 3 gives
    them add = -1, which would UNPRICE a season the grid observed."""
    p = _path(board_row=_row(_steps((2027, 5_000_000, "ARB 4"))))
    assert [c["tok"] for c in p["seasons"] if c["usd"]] == ["ARB 4"]
    assert not [c for c in p["seasons"] if c["src"] == "class_closure"]
    closed = sp.class_closure(_steps((2027, 5_000_000, "ARB 4")),
                              horizon_last=2031, raise_fn=_raise, league_min=LM)
    assert closed == []


def test_7_an_unpriced_last_grid_step_blocks_closure_and_says_why():
    """R3's precondition. 87 board rows carry an entirely unpriced grid; closure
    chains off a SALARY, so it cannot run where the whole window has none. 72 of
    those 87 DO have one, on a contract season beside the hole - see 7b - and 11
    are genuinely unpriceable on the served board."""
    steps = _steps((2027, None, "ARB 2"), (2028, None, "ARB 3"))
    p = _path(board_row=_row(steps))
    assert p["truncated"] == "no_prior_salary"
    assert p["last_controlled"] is None
    assert sp.class_closure(steps, horizon_last=2031, raise_fn=_raise,
                            league_min=LM) == []


def test_7b_an_unpriced_grid_beside_a_contract_season_closes_off_the_contract():
    """THE ANCHOR IS THE PATH, NOT THE GRID. 59 arbitration-eligible rows shipped
    one priced season and a served line reading "no prior salary on file" printed
    beside the contracted salary it could have raised from (Elly De La Cruz, Andy
    Pages, Otto Lopez, Miguel Vargas). The grid steps are unpriced; the contract
    season one year earlier is not."""
    steps = _steps((2028, None, "ARB 2"), (2029, None, "ARB 3"))
    p = _path(contract={"salary_by_year": {2027: 5_000_000}, "signed_through": 2027},
              board_row=_row(steps))
    assert p["truncated"] is None, "the window IS established: the contract prices it"
    assert [c["src"] for c in p["seasons"] if c["usd"]] == [
        "contract", "class_closure", "class_closure"]
    got = [(c["season"], c["tok"]) for c in p["seasons"] if c["usd"]]
    assert got == [(2027, "signed"), (2028, "ARB 2"), (2029, "ARB 3")], got
    assert p["last_controlled"] == 2029
    # the class comes off the GRID's own token line, not off a rung counter:
    # cls(s) = k_last + (s - last_grid_season), so an anchor BEFORE the last
    # grid step walks forward into the tokens the grid already published.
    assert p["seasons"][1]["cls"] == 2 and p["seasons"][2]["cls"] == 3
    # and rule 1 still wins the season it prices
    assert p["seasons"][0]["usd"] == 5_000_000


def test_7c_the_cba_maximum_cut_floors_an_award_beside_a_contract_the_board_never_saw():
    """CBA Article VI: a cut of more than 20 percent is not an award. The board
    chains each step off the PANEL's prior salary and does not know about an
    extension, which put 14 served rows a step below their own previous season -
    Brice Turang $9.90M in 2027 against a projected $5.95M in 2028. It fires only
    where the prior season is CONTRACTED; two board-chained steps are left alone
    so clause C5' keeps being able to fail on them."""
    p = _path(contract={"salary_by_year": {2027: 9_900_000}, "signed_through": 2027},
              board_row=_row(_steps((2028, 5_951_000, "ARB 3"))))
    c = p["seasons"][1]
    assert c["src"] == "arb_ladder" and c.get("cba_floor") is True
    assert c["usd"] == 7_920_000 == int(round(0.80 * 9_900_000))
    assert c["lo"] <= c["usd"] <= c["hi"]
    assert p["cba_floored"] == 1
    # a board step that does NOT cut a contract is untouched
    q = _path(contract={"salary_by_year": {2027: 4_000_000}, "signed_through": 2027},
              board_row=_row(_steps((2028, 5_951_000, "ARB 3"))))
    assert q["seasons"][1]["usd"] == 5_951_000 and q["cba_floored"] == 0


# -------------------------------------------------------------------- 8-12
def test_8_the_cliff_cuts_on_the_continuation_not_on_one_season():
    """R1, worked in the module docstring. The forward rule cut [+10,-1,-30] at
    index 0 and paid $0; backward induction pays $10.0M and cuts at index 1."""
    npv, cut = sp.tender_cliff([10e6, -1e6, 30e6], [True] * 3)
    assert cut is None and round(npv / 1e6, 1) == 35.3
    npv, cut = sp.tender_cliff([10e6, -1e6, -30e6], [True] * 3)
    assert cut == 1 and round(npv / 1e6, 1) == 10.0


def test_9_the_club_tenders_through_the_good_year_and_walks_after_it():
    """R1's counterexample. The forward rule pays $0 here."""
    npv, cut = sp.tender_cliff([-5e6, 30e6, -40e6], [True] * 3)
    assert cut == 2 and round(npv / 1e6, 1) == 23.0
    fwd, fcut = sp.forward_cliff([-5e6, 30e6, -40e6], [True] * 3)
    assert fcut == 0 and fwd == 0
    assert npv > fwd


def test_10_a_negative_prearb_season_is_never_cut():
    """R2. A club options or designates a pre-arbitration player; it does not
    decline to tender him, and 52.1% of the added money is pre-arb, so a
    cliff that fired there would label the wrong mechanism on the majority."""
    p = _path(board_row=_row(_steps((2027, 780_000, "PRE-ARB"),
                                    (2028, 780_000, "PRE-ARB"))))
    assert not any(sp.is_cuttable(c) for c in p["seasons"])
    npv, cut = sp.apply_cliff(p, [-40e6, -40e6, None, None, None])
    assert cut is None and p["cut_season"] is None
    assert npv < 0


def test_11_the_cliff_never_cuts_a_guaranteed_season():
    """A club cannot walk away from money it owes. That asymmetry against
    guaranteed money is economically correct and the copy says so."""
    p = _path(contract={"salary_by_year": {2027: 30_000_000, 2028: 30_000_000},
                        "signed_through": 2028},
              board_row=None)
    assert not any(sp.is_cuttable(c) for c in p["seasons"])
    npv, cut = sp.apply_cliff(p, [-20e6, -20e6, None, None, None])
    assert cut is None and npv < 0


def test_12_the_floor_never_lowers_a_total():
    """C7'a as arithmetic: max(0, .) propagates backwards, so the floored value
    is never below the raw NPV, on any path."""
    import random
    rnd = random.Random(20260917)
    for _ in range(300):
        d = [rnd.uniform(-5e7, 5e7) for _ in range(5)]
        cut = [rnd.random() < 0.6 for _ in range(5)]
        floored, _ = sp.tender_cliff(d, cut)
        raw = sum(x / (1.07 ** t) for t, x in enumerate(d))
        assert floored >= raw - 1e-6
        fwd, _ = sp.forward_cliff(d, cut)
        assert floored >= fwd - 1e-6        # C7'b, the same property


# ------------------------------------------------------------------- 13-16
def test_13_the_salary_band_is_named_for_the_surplus_and_is_ordered():
    """R5. A LOW salary gives a HIGH surplus, so surSalLo is the surplus at the
    HIGH award. The band moves ONLY through salary: WAR is held at the mean."""
    p = _path(board_row=_row([{"season": 2027, "usd": 5_000_000,
                               "lo": 3_900_000, "hi": 6_100_000, "tok": "ARB 2"}]))
    c = p["seasons"][0]
    assert c["lo"] < c["usd"] < c["hi"]
    value = 40_000_000

    def npv_at(sal):
        return sp.tender_cliff([value - sal, 0, 0, 0, 0],
                               [sp.is_cuttable(x) for x in p["seasons"]])[0]
    sur = npv_at(c["usd"])
    sur_lo, sur_hi = npv_at(c["hi"]), npv_at(c["lo"])
    assert sur_lo <= sur <= sur_hi
    assert sur_hi - sur_lo == pytest.approx(c["hi"] - c["lo"])


def test_14_a_cut_season_carries_no_surplus_and_the_npv_still_reconciles():
    """The published invariant: surNpv is EXACTLY the NPV of the non-null `sur`
    entries, because W[0] is the discounted sum of the seasons before the cut."""
    p = _path(board_row=_row(_steps((2027, 1_000_000, "ARB 2"),
                                    (2028, 20_000_000, "ARB 3"),
                                    (2029, 30_000_000, "ARB 4"))))
    d = [10e6, -25e6, -25e6, None, None]
    npv, cut = sp.apply_cliff(p, d)
    assert cut == 1 and p["cut_season"] == 2028
    assert [c["cut"] for c in p["seasons"]] == [False, True, True, True, True]
    sur = [None if (cut is not None and t >= cut) else x for t, x in enumerate(d)]
    assert npv == pytest.approx(sum(x / (1.07 ** t)
                                    for t, x in enumerate(sur) if x is not None))


def test_15_the_path_is_stamped_and_never_exceeds_its_horizon():
    p = _path(board_row=_row(_steps((2027, 1_000_000, "ARB 1"))), vintage="2026-09-16")
    assert p["vintage"] == "2026-09-16"
    assert len(p["seasons"]) == H
    assert max(c["season"] for c in p["seasons"]) == FIRST + H - 1
    # A never-debuted prospect reaches this module with no board row and no
    # contract, and comes back with nothing priced. docs/ARBITRATION_GATE.md
    # section 6 keeps the clemens_2026 ladder for that population on purpose.
    empty = _path(board_row=None, contract=None)
    assert sp.payload_path(empty) is None and empty["src_mix"] is None


def test_16_an_option_season_is_stamped_and_is_not_re_priced():
    """R8/D10. Measured on data/contract_options.json: 0 club options fall
    inside 2027-2031 and 9 player-option seasons do, so nothing declinable is
    mispriced today and the exposure that exists runs the other way."""
    p = _path(contract={"salary_by_year": {2029: 35_000_000, 2030: 35_000_000},
                        "signed_through": 2030},
              opts={"player": [2030], "club": []})
    c = [x for x in p["seasons"] if x["season"] == 2030][0]
    assert c["opt"] == "player"
    assert c["src"] == "contract" and c["usd"] == 35_000_000
    assert sp.payload_options(p) == [[2030, "player"]]


# ---------------------------------------------------------------- the flag
def test_the_off_mode_is_a_revert_and_not_a_re_implementation():
    """`SALARY_PATH_MODE = "off"` is the whole failure response registered in
    docs/ARBITRATION_GATE.md section 11e, so it has to keep working: a row the
    contract join left entirely unpriced takes the whole board ladder, and a
    row with any contract price takes nothing from the board."""
    board = _row(_steps((2027, 916_000, "ARB 1"), (2028, 1_530_000, "ARB 2")))
    off = _path(mode="off", board_row=board)
    assert [c["src"] for c in off["seasons"] if c["usd"]] == ["arb_ladder"] * 2
    assert off["truncated"] is None
    priced = _path(mode="off", board_row=board,
                   contract={"salary_by_year": {2026: 1_000_000}, "signed_through": 2026})
    assert not [c for c in priced["seasons"] if c["usd"]]
    # and the flag itself is one of the four the gate doc names
    assert sp.SALARY_PATH_MODE in sp.MODES


def test_the_served_mode_is_full_and_the_ladder_stages_are_nested():
    """Owner decision, 2026-09-16: served ON, fully. The stages must nest, so a
    failed clause can step DOWN one level without a code change."""
    assert sp.SALARY_PATH_MODE == "full"
    board = _row(_steps((2027, 1_000_000, "ARB 1")))
    n = {m: len([c for c in _path(mode=m, board_row=board)["seasons"] if c["usd"]])
         for m in sp.MODES}
    assert n["off"] >= 1 and n["ladder"] == 1 and n["closure"] == 3 and n["full"] == 3


def test_a_contract_that_buys_out_the_whole_grid_ends_the_closure_question():
    """The 135 rows signed through 2028 or later measured an add of exactly $0.
    Without this guard, closure chains a projected award off seasons the club
    is paying contracted dollars for, and 3 of them move by $67M."""
    p = _path(contract={"salary_by_year": {2027: 8e6, 2028: 10e6}, "signed_through": 2028},
              board_row=_row(_steps((2027, 4_000_000, "ARB 2"), (2028, 6_000_000, "ARB 3"))))
    assert [c["src"] for c in p["seasons"] if c["usd"]] == ["contract", "contract"]
    assert p["last_controlled"] == 2028
