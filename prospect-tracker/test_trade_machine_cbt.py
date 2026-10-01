# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The Trade Machine's CBT block (owner answer M27-4, 2026-09-25).

Per side, the club's CBT position before and after the trade for the 2026
prorated remainder (days left in the regular season over its length) and for
2027 (the 2026 threshold carried forward, labelled). Display only. The tax
arithmetic in assets/trademachine.js must agree with
ledger_export.computed_cbt_bill, the schedule the Ledger prints, on the
fa_cba rates; the sidecar must carry exactly the Ledger's per-club figures.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
JS = ROOT / "assets" / "trademachine.js"
START = "// ---- CBT context (owner answer M27-4"
END = "// ---- end CBT context"

CAL = {"start": "2026-03-25", "end": "2026-09-27", "days": 187}


def _region() -> str:
    src = JS.read_text(encoding="utf-8").replace("\r\n", "\n")
    i, j = src.index(START), src.index(END)
    return src[i:j]


@pytest.fixture(scope="module")
def ctx():
    MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer
    c = MiniRacer()
    c.eval(_region())
    return c


def _call(ctx, fn, *args):
    return json.loads(ctx.eval(f"JSON.stringify({fn}({', '.join(json.dumps(a) for a in args)}))"))


def _rules():
    import fa_cba
    return fa_cba.cbt_tax_rates(), fa_cba.cbt_surcharge_tiers()


def _cbt_fixture(tax26=240_000_000, tax27=230_000_000, tier26="1st-Time", tier27="Non-Tax"):
    rates, tiers = _rules()
    return {
        "season_now": 2026, "class_year": 2027,
        "calendar": {"2026": dict(CAL)},
        "rates": rates, "surcharge_tiers_usd": list(tiers),
        "brackets": {"under": "under the threshold", "base": "base bracket (up to 20M over)",
                     "surcharge_1": "first surcharge (20-40M over)",
                     "surcharge_2": "second surcharge (40-60M over)",
                     "surcharge_3": "third surcharge (60M+ over)"},
        "payor_basis": {"spotrac": "Spotrac 2027 page", "spotrac_2026": "Spotrac 2026 page"},
        "clubs": {"AAA": {
            "2026": {"tax_payroll_usd": tax26, "threshold_usd": 244_000_000, "carry_forward": False,
                     "tier": tier26, "tier_basis": "spotrac_2026"},
            "2027": {"tax_payroll_usd": tax27, "threshold_usd": 244_000_000, "carry_forward": True,
                     "tier": tier27, "tier_basis": "spotrac"}}},
    }


# --------------------------------------------------------------------------- #
# the tax arithmetic: one schedule, two languages
# --------------------------------------------------------------------------- #

def test_js_bill_matches_the_ledger_schedule_on_the_fa_cba_rates(ctx):
    import ledger_export as L
    rates, tiers = _rules()
    T = 244_000_000
    problems = []
    for tier in ("Non-Tax", "1st-Time", "2nd-Time", "3+-Time"):
        for over_m in (-30, -0.5, 0, 0.5, 10, 20, 20.5, 33, 40, 47, 60, 61, 95):
            tax = T + int(over_m * 1_000_000)
            py = L.computed_cbt_bill(tax, T, tier, rates, tiers)
            js = _call(ctx, "_tmCbtBill", tax, T, tier, rates, tiers)
            if js["bracket"] != py["bracket"] or abs(js["bill"] - py["bill_usd"]) > 1:
                problems.append((tier, over_m, js, py))
    assert not problems, problems


# --------------------------------------------------------------------------- #
# proration
# --------------------------------------------------------------------------- #

def test_days_left_counts_today_and_closes_after_the_final_day(ctx):
    assert _call(ctx, "_tmCbtDaysLeft", CAL, "2026-02-01") == {"left": 187, "len": 187}
    assert _call(ctx, "_tmCbtDaysLeft", CAL, "2026-03-25") == {"left": 187, "len": 187}
    assert _call(ctx, "_tmCbtDaysLeft", CAL, "2026-08-01") == {"left": 58, "len": 187}
    assert _call(ctx, "_tmCbtDaysLeft", CAL, "2026-09-27") == {"left": 1, "len": 187}
    assert _call(ctx, "_tmCbtDaysLeft", CAL, "2026-09-28") == {"left": 0, "len": 187}
    assert _call(ctx, "_tmCbtDaysLeft", None, "2026-08-01") is None


def test_proration_arithmetic_on_a_fixture(ctx):
    """A first-time payor at $240M takes in a $30M AAV on 2026-08-01 (58 of 187
    days left): 2026 tax payroll moves by 30M x 58/187, and the marginal tax
    is the first-time base rate on the part above $244M. For 2027 the full
    AAV moves, against the carried-forward threshold."""
    cbt = _cbt_fixture()
    proj_in = {"aav": 30_000_000, "thru": 2028,
               "salPath": [[2027, 30_000_000, 30_000_000, 30_000_000, "signed", "contract", 0]]}
    ctx.eval(f"var __P = {json.dumps(proj_in)};")
    side = json.loads(ctx.eval(
        "JSON.stringify(_tmCbtSide('AAA', [{kind:'mlb', key:'x'}], [], function(){return __P;}, "
        f"{json.dumps(cbt)}, '2026-08-01'))"))
    s26, s27 = side["seasons"]
    moved = 30_000_000 * 58 / 187
    assert s26["daysLeft"] == 58 and s26["days"] == 187 and s26["prorated"] is True
    assert abs(s26["moved"] - moved) < 1e-6
    assert abs(s26["after"] - (240_000_000 + moved)) < 1e-6
    assert s26["bracketBefore"] == "under" and s26["bracketAfter"] == "base"
    assert abs(s26["marginal"] - 0.20 * (240_000_000 + moved - 244_000_000)) < 1e-3
    assert round(moved) == 9_304_813
    # 2027: the full AAV, $230M -> $260M, 16M over at the Non-Tax (first-time) base rate.
    assert s27["moved"] == 30_000_000 and s27["after"] == 260_000_000
    assert s27["carry"] is True and s27["bracketAfter"] == "base"
    assert abs(s27["marginal"] - 0.20 * 16_000_000) < 1e-6
    lines = json.loads(ctx.eval(
        f"JSON.stringify(_tmCbtLines({json.dumps(side)}, {json.dumps(cbt)}))"))
    assert lines[0]["text"].startswith("2026, prorated remainder: tax payroll $240.0M to $249.3M; "
                                       "58 of 187 regular-season days left; threshold $244.0M; "
                                       "bracket: under the threshold to base bracket (up to 20M over); "
                                       "marginal tax +$1.1M on $9.3M of prorated AAV moved in (net)")
    assert "the 2026 figure carried forward (no 2027 threshold is published)" in lines[1]["text"]
    assert "marginal tax +$3.2M on $30.0M of AAV moved in (net)" in lines[1]["text"]


def test_the_sending_club_moves_the_other_way(ctx):
    cbt = _cbt_fixture(tax26=270_000_000, tier26="2nd-Time")
    ctx.eval("var __Q = {aav: 25000000, thru: 2026, salPath: []};")
    side = json.loads(ctx.eval(
        "JSON.stringify(_tmCbtSide('AAA', [], [{kind:'mlb', key:'y'}], function(){return __Q;}, "
        f"{json.dumps(cbt)}, '2026-03-25'))"))
    s26, s27 = side["seasons"]
    assert s26["moved"] == -25_000_000 and s26["after"] == 245_000_000
    assert s26["bracketBefore"] == "surcharge_1" and s26["bracketAfter"] == "base"
    assert s26["marginal"] < 0
    assert s27["moved"] == 0, "a contract ending in 2026 moves nothing in 2027"
    lines = json.loads(ctx.eval(
        f"JSON.stringify(_tmCbtLines({json.dumps(side)}, {json.dumps(cbt)}))"))
    assert "on $25.0M of prorated AAV moved out (net)" in lines[0]["text"]
    assert "187 of 187 regular-season days left" in lines[0]["text"]


def test_closed_season_wording_after_the_last_day(ctx):
    """After the final regular-season day (today, 2026-10-01) the 2026 line
    reads the closed sentence, never a zero figure, and 2027 still prints."""
    cbt = _cbt_fixture()
    ctx.eval("var __R = {aav: 30000000, thru: 2028, salPath: [[2027, 30000000, 30000000, 30000000, 'signed', 'contract', 0]]};")
    for today in ("2026-09-28", "2026-10-01", "2026-12-31"):
        side = json.loads(ctx.eval(
            "JSON.stringify(_tmCbtSide('AAA', [{kind:'mlb', key:'x'}], [], function(){return __R;}, "
            f"{json.dumps(cbt)}, {json.dumps(today)}))"))
        lines = json.loads(ctx.eval(
            f"JSON.stringify(_tmCbtLines({json.dumps(side)}, {json.dumps(cbt)}))"))
        assert lines[0]["text"] == "2026 closed: the trade does not change 2026 tax payroll", today
        assert "$0" not in lines[0]["text"]
        assert lines[1]["text"].startswith("2027: tax payroll $230.0M to $260.0M"), today


def test_charge_rules(ctx):
    ch = lambda item, proj, season: _call(ctx, "_tmCbtCharge", item, proj, season, 2026)  # noqa: E731
    signed = {"aav": 20_000_000, "thru": 2028,
              "salPath": [[2027, 22_000_000, 0, 0, "signed", "contract", 0]]}
    assert ch({"kind": "prospect"}, None, 2026) == {"usd": 0, "known": True}
    assert ch({"kind": "mlb"}, None, 2026) == {"usd": 0, "known": False}
    assert ch({"kind": "mlb"}, signed, 2026) == {"usd": 20_000_000, "known": True}
    assert ch({"kind": "mlb"}, signed, 2027) == {"usd": 20_000_000, "known": True}, "AAV, not the year's salary"
    arb = {"aav": None, "thru": None, "salPath": [[2027, 6_000_000, 0, 0, "ARB 2", "arb_ladder", 0]]}
    assert ch({"kind": "mlb"}, arb, 2026) == {"usd": 0, "known": False}
    assert ch({"kind": "mlb"}, arb, 2027) == {"usd": 0, "known": True}, \
        "a projected arbitration year is not in Spotrac's 2027 tax payroll"
    opt = dict(signed, salOpt=[[2027, "club"]])
    assert ch({"kind": "mlb"}, opt, 2027) == {"usd": 0, "known": True}, "a club option year is not guaranteed"
    ending = {"aav": 9_000_000, "thru": 2026, "salPath": []}
    assert ch({"kind": "mlb"}, ending, 2027) == {"usd": 0, "known": True}


def test_a_side_club_needs_one_sending_club(ctx):
    ctx.eval("var __canon = function(o){ return o ? String(o).toUpperCase() : null; };")
    one = json.loads(ctx.eval("JSON.stringify(_tmCbtClubOf([{org:'nym'},{org:'NYM'}], __canon))"))
    two = json.loads(ctx.eval("JSON.stringify(_tmCbtClubOf([{org:'NYM'},{org:'LAD'}], __canon))"))
    none = json.loads(ctx.eval("JSON.stringify(_tmCbtClubOf([], __canon))"))
    assert one == {"club": "NYM"} and two == {"club": None, "why": "mixed"} and none["why"] == "none"


def test_the_cbt_block_never_touches_a_trade_value():
    """Display only: no function in the block reads a trade value, so the
    evaluator's totals and verdict cannot move with it."""
    reg = _region()
    assert ".mm" not in reg and "_tmTotal" not in reg and "BALANCED_THRESHOLD_MM" not in reg


# --------------------------------------------------------------------------- #
# the sidecar is the Ledger's figures, copied
# --------------------------------------------------------------------------- #

def test_served_sidecar_matches_the_ledger_board():
    board = json.loads((ROOT / "data" / "ledger_board.json").read_text(encoding="utf-8"))
    side = json.loads((ROOT / "data" / "trade_cbt.json").read_text(encoding="utf-8"))
    assert side["generated_at"] == board["generated_at"], "the sidecar is one board vintage"
    assert set(side["clubs"]) == set(board["clubs"]) and len(side["clubs"]) == 30
    for c, blocks in side["clubs"].items():
        for s in ("2026", "2027"):
            src = board["clubs"][c]["cbt"][s]
            for k, v in blocks[s].items():
                assert v == src[k], (c, s, k)
    assert side["rates"] == board["cba"]["rates"]
    assert side["surcharge_tiers_usd"] == board["cba"]["surcharge_tiers_usd"]
    assert side["clubs"]["NYY"]["2027"]["carry_forward"] is True
    assert side["source"]["thresholds"] and side["source"]["payroll"]


def test_slice_and_calendar_on_fixtures(tmp_path, monkeypatch):
    import ledger_export as L
    (tmp_path / "season_2026.json").write_text(json.dumps({"seasons": [
        {"seasonId": "2026", "regularSeasonStartDate": "2026-03-25",
         "regularSeasonEndDate": "2026-09-27"}]}), encoding="utf-8")
    cal = L.season_calendar_on_disk(2026, tmp_path)
    assert cal == CAL
    assert L.season_calendar_on_disk(2025, tmp_path) is None
    board = json.loads((ROOT / "data" / "ledger_board.json").read_text(encoding="utf-8"))
    out = L.write_trade_cbt(board, tmp_path / "trade_cbt.json", calendar_dir=tmp_path)
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["calendar"]["2026"] == CAL
    assert "2026-03-25 to 2026-09-27" in doc["source"]["calendar"]


def test_conftest_redirects_the_second_output():
    import ledger_export as L
    assert ROOT / "data" / "trade_cbt.json" != L.TRADE_CBT_OUT, \
        "conftest must redirect ledger_export.TRADE_CBT_OUT under pytest"
